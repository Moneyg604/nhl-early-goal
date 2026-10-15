"""Publish the NFL section under docs/nfl/.

    docs/nfl/index.html             the current week
    docs/nfl/weeks/<s>-wNN.html     every published week (plus .json payload and .csv summary)
    docs/nfl/weeks.json             list of weeks, newest first
    docs/nfl/live.json              live scoreboard snapshot (written by the live job)
    docs/nfl/scorecard.json         graded leans (written by `python -m nfl scorecard`)

A week that has started keeps the numbers that were on the page before each kickoff: when a game's
kickoff has passed, the newly built page carries that game's previous entry (with the result attached).
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import OUT_DIR, SITE_DIR
from .report import render

DAYSLOT = """<span class="lbl2">Week</span><select id="daysel" aria-label="week">{options}</select><span class="pub">published {published}</span>"""
SCRIPT = """<script>window.NFL_BASE={base!r};(function(){{var s=document.getElementById('daysel'); if(s) s.onchange=function(){{ location.href=this.value; }};}})();</script>"""
HEAD = """<link rel="manifest" href="{root}manifest.webmanifest"><meta name="theme-color" content="#070b12"><link rel="apple-touch-icon" href="{root}apple-touch-icon.png"><link rel="icon" type="image/png" sizes="192x192" href="{root}icon-192.png">"""


def _csv(p: dict) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["game_id", "kickoff_utc", "away", "home", "tier", "spread", "total", "ml_away", "ml_home", "home_cover", "over", "model_margin", "model_total",
                "h1_fair", "h2_fair", "fg_o15_away", "fg_o15_home", "qb_away", "qb_yds_fair_away", "qb_td_o15_away", "qb_home", "qb_yds_fair_home", "qb_td_o15_home",
                "atd_top_away", "atd_top_home"])
    for g in p["games"]:
        mk = g["markets"]; L = g.get("lines") or {}
        a = (g.get("anytime") or {})
        w.writerow([g["game_id"], g.get("kickoff_utc"), g["away"], g["home"], g.get("tier"), L.get("spread"), L.get("total"), mk["ml"]["away"], mk["ml"]["home"],
                    (mk.get("spread") or {}).get("home_cover"), (mk.get("total") or {}).get("over"), g["model"]["margin"], g["model"]["total"],
                    mk["h1_fair_line"], mk["h2_fair_line"], mk["fg"]["away"]["over1.5"], mk["fg"]["home"]["over1.5"],
                    g["qb"]["away"].get("name"), mk["qb"]["away"]["yds_fair_line"], mk["qb"]["away"]["td_over1.5"],
                    g["qb"]["home"].get("name"), mk["qb"]["home"]["yds_fair_line"], mk["qb"]["home"]["td_over1.5"],
                    "; ".join(f"{x['name']} {x['p']}" for x in a.get("away", [])[:3]), "; ".join(f"{x['name']} {x['p']}" for x in a.get("home", [])[:3])])
    return buf.getvalue()


def freeze_started(new: dict, old: dict | None, now: datetime | None = None) -> dict:
    """Keep the pre-kickoff numbers for games that have started; take results from the new build."""
    if not old:
        return new
    now = now or datetime.now(timezone.utc)
    prev = {g["game_id"]: g for g in old.get("games", [])}
    games = []
    for g in new["games"]:
        k = g.get("kickoff_utc")
        started = False
        if k:
            try:
                started = datetime.strptime(k, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) <= now
            except ValueError:
                started = False
        if started and g["game_id"] in prev:
            keep = dict(prev[g["game_id"]])
            for key in ("actual", "score"):
                if g.get(key) is not None:
                    keep[key] = g[key]
            keep["frozen"] = True
            games.append(keep)
        else:
            games.append(g)
    new = dict(new)
    new["games"] = games
    if old.get("picks"):
        # leans whose game has started stay as published
        from .pipeline import picks as make_picks
        try:
            fresh = make_picks(new)
        except (KeyError, TypeError, ValueError):
            return new
        started_ids = {g["game_id"] for g in games if g.get("frozen")}
        merged = {}
        for key in set(fresh) | set(old["picks"]):
            keep = [x for x in old["picks"].get(key, []) if x["game_id"] in started_ids]
            add = [x for x in fresh.get(key, []) if x["game_id"] not in started_ids]
            n = max(len(old["picks"].get(key, [])), len(fresh.get(key, [])))
            merged[key] = (keep + sorted(add, key=lambda x: -x["score"]))[:max(n, len(keep))]
        new["picks"] = merged
    return new


def build_site(out_dir: Path = OUT_DIR, site_dir: Path = SITE_DIR, keep: int = 40) -> Path:
    site_dir.mkdir(parents=True, exist_ok=True)
    wdir = site_dir / "weeks"
    wdir.mkdir(exist_ok=True)
    # new builds from out/nfl/ (freeze games that already kicked off)
    for f in sorted(out_dir.glob("week-*.json")):
        m = re.match(r"week-(\d{4}-w\d{2})\.json$", f.name)
        if not m:
            continue
        name = m.group(1)
        new = json.loads(f.read_text())
        old_f = wdir / f"{name}.json"
        old = json.loads(old_f.read_text()) if old_f.exists() else None
        payload = freeze_started(new, old)
        old_f.write_text(json.dumps(payload, separators=(",", ":")))
        (wdir / f"{name}.csv").write_text(_csv(payload))
        # simulation samples for same-game parlays: started games keep the samples behind their frozen numbers
        sf = out_dir / f"week-{name}.sims.json"
        if sf.exists():
            new_s = json.loads(sf.read_text())
            old_sf = wdir / f"{name}.sims.json"
            if old_sf.exists():
                try:
                    old_s = json.loads(old_sf.read_text())
                    frozen = {g["game_id"] for g in payload["games"] if g.get("frozen")}
                    for gid in frozen:
                        if gid in old_s.get("games", {}):
                            new_s["games"][gid] = old_s["games"][gid]
                except json.JSONDecodeError:
                    pass
            old_sf.write_text(json.dumps(new_s, separators=(",", ":")))
    names = sorted((p.stem for p in wdir.glob("*.json") if not p.name.endswith(".sims.json")), reverse=True)[:keep]
    if not names:
        raise SystemExit("nothing to publish: run `python -m nfl run` first")
    published = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    # the front page: the earliest week that still has a game to play, else the latest week
    current = None
    for n in sorted(names):
        p = json.loads((wdir / f"{n}.json").read_text())
        if any(g.get("actual") is None or g["actual"].get("hs") is None for g in p["games"]):
            current = n
            break
    current = current or names[0]

    def label(n: str) -> str:
        s, w = n.split("-w")
        return f"{s} week {int(w)}"

    def options(sel: str, base: str) -> str:
        return "".join(f'<option value="{base}weeks/{n}.html" {"selected" if n == sel else ""}>{label(n)}{" · now" if n == current else ""}</option>' for n in names)

    for n in names:
        p = json.loads((wdir / f"{n}.json").read_text())
        for target, base, root, nhl in (((wdir / f"{n}.html"), "../", "../../", "../../index.html"),) + ((((site_dir / "index.html"), "./", "../", "../index.html"),) if n == current else ()):
            html = render(p, nhl_href=nhl)
            html = html.replace('<span id="dayslot"></span>', DAYSLOT.format(options=options(n, base), published=published), 1)
            html = html.replace("</title>", "</title>\n" + HEAD.format(root=root), 1)
            html = html.replace("<script id=\"payload\"", SCRIPT.format(base=base) + "\n<script id=\"payload\"", 1)
            target.write_text(html, encoding="utf-8")
    (site_dir / "weeks.json").write_text(json.dumps({"weeks": [{"name": n, "season": int(n.split("-w")[0]), "week": int(n.split("-w")[1])} for n in names],
                                                     "current": current, "published": published}, indent=1))
    if not (site_dir / "scorecard.json").exists():
        (site_dir / "scorecard.json").write_text(json.dumps({"summary": {}, "weeks": {}, "items": [], "updated_utc": published}))
    return site_dir


__all__ = ["build_site", "freeze_started"]
