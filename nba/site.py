"""Publish the NBA section under docs/nba/.

    docs/nba/index.html          the current day (today's games, else the latest published day)
    docs/nba/days/<date>.html    every published day (plus .json payload)
    docs/nba/days.json           list of days, newest first
    docs/nba/scorecard.json      graded picks (written by `python -m nba scorecard`)

A game that has tipped off keeps the numbers that were on the page before tip-off: when a game has started,
the newly built page carries that game's previous entry (with the result attached), and the day's picks stay as
published (they are graded at the prices shown before tip-off).
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from earlygoal.brand import copy_assets

from .config import OUT_DIR, SITE_DIR
from .report import render

DAYSLOT = """<span class="lbl2">Day</span><select id="daysel" aria-label="day">{options}</select><span class="pub">published {published}</span>"""
SCRIPT = """<script>window.NBA_BASE={base!r};(function(){{var s=document.getElementById('daysel'); if(s) s.onchange=function(){{ location.href=this.value; }};}})();</script>"""
HEAD = """<link rel="manifest" href="{root}manifest.webmanifest"><meta name="theme-color" content="#070b12"><link rel="apple-touch-icon" href="{root}apple-touch-icon.png"><link rel="icon" type="image/png" sizes="192x192" href="{root}icon-192.png"><meta name="apple-mobile-web-app-title" content="Gill Sports"><meta name="apple-mobile-web-app-capable" content="yes">"""


def freeze_started(new: dict, old: dict | None, now: datetime | None = None) -> dict:
    """Keep the pre-tip numbers, board and picks for games that have started; take results from the new build."""
    if not old:
        return new
    now = now or datetime.now(timezone.utc)
    prev = {g["game_id"]: g for g in old.get("games", [])}
    started = set()
    games = []
    for g in new["games"]:
        k = g.get("tip_utc")
        try:
            is_started = bool(k) and datetime.strptime(k, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) <= now
        except ValueError:
            is_started = False
        if is_started and g["game_id"] in prev:
            keep = dict(prev[g["game_id"]])
            for key in ("actual", "live", "state", "status", "completed"):
                if g.get(key) is not None:
                    keep[key] = g[key]
            keep["frozen"] = True
            games.append(keep); started.add(g["game_id"])
        else:
            games.append(g)
    new = dict(new); new["games"] = games
    if started:
        # board rows and picks for started games come from the published build (graded at the price shown before tip)
        old_board = [b for b in (old.get("best_bets") or {}).get("ranked", []) if b["game_id"] in started]
        new_board = [b for b in (new.get("best_bets") or {}).get("ranked", []) if b["game_id"] not in started]
        new["best_bets"] = dict(new.get("best_bets") or {}); new["best_bets"]["ranked"] = new_board + old_board
        picks = dict(new.get("picks") or {})
        for key, lst in (old.get("picks") or {}).items():
            picks[key] = [x for x in (picks.get(key) or []) if x["game_id"] not in started] + [x for x in lst if x["game_id"] in started]
        new["picks"] = picks
        if (old.get("bot") or {}).get("desk") and (new.get("bot") or {}).get("desk") and new["bot"]["desk"].get("ok"):
            od = old["bot"]["desk"]; nd = new["bot"]["desk"]
            for key in ("selections", "wild_cards"):
                nd[key] = [x for x in (nd.get(key) or []) if x["game_id"] not in started] + [x for x in (od.get(key) or []) if x["game_id"] in started]
    return new


def build_site(out_dir: Path | None = None, site_dir: Path | None = None, keep: int = 60) -> Path:
    out_dir = out_dir or OUT_DIR
    site_dir = site_dir or SITE_DIR
    ddir = site_dir / "days"
    ddir.mkdir(parents=True, exist_ok=True)
    for f in sorted(out_dir.glob("day-*.json")):
        new = json.loads(f.read_text())
        name = new["date"]
        old_f = ddir / f"{name}.json"
        old = json.loads(old_f.read_text()) if old_f.exists() else None
        payload = freeze_started(new, old)
        old_f.write_text(json.dumps(payload, separators=(",", ":")))
    names = sorted((p.stem for p in ddir.glob("*.json")), reverse=True)[:keep]
    if not names:
        raise SystemExit("nothing to publish: run `python -m nba run` first")
    published = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    current = None
    for n in sorted(names):
        p = json.loads((ddir / f"{n}.json").read_text())
        if any(not g.get("actual") for g in p["games"]) and p["games"]:
            current = n
            break
    current = current or names[0]

    def options(sel: str, base: str) -> str:
        return "".join(f'<option value="{base}days/{n}.html" {"selected" if n == sel else ""}>{n}{" · now" if n == current else ""}</option>' for n in names)

    for n in names:
        p = json.loads((ddir / f"{n}.json").read_text())
        for target, base, root, nhl in (((ddir / f"{n}.html"), "../", "../../", "../../index.html"),) + ((((site_dir / "index.html"), "./", "../", "../index.html"),) if n == current else ()):
            html = render(p, nhl_href=nhl, root=root)
            html = html.replace('<span id="dayslot"></span>', DAYSLOT.format(options=options(n, base), published=published), 1)
            html = html.replace("</title>", "</title>\n" + HEAD.format(root=root), 1)
            html = html.replace("<script>\nconst P = ", SCRIPT.format(base=base) + "\n<script>\nconst P = ", 1)
            target.write_text(html, encoding="utf-8")
    (site_dir / "days.json").write_text(json.dumps({"days": names, "current": current, "published": published}, indent=1))
    copy_assets(site_dir.parent)
    if not (site_dir / "scorecard.json").exists():
        (site_dir / "scorecard.json").write_text(json.dumps({"summary": {}, "leaderboard": [], "days": {}, "items": [], "updated_utc": published}))
    return site_dir


__all__ = ["build_site", "freeze_started"]
