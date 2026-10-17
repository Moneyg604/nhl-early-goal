"""Assemble per-game research fragments into one research-desk overlay, then validate it.

    python tools/assemble_desk.py --season 2026 --week 6 --frags <dir with <game_id>.json> [--keep data/nfl/research/2026-w06.json] [--summary "..."]
    python tools/assemble_desk.py --sport nba --date 2026-10-20 --frags <dir> [--keep data/nba/research/2026-10-20.json] [--summary "..."]

Each fragment is {"game_id", "notes": {...}, "selections": [...], "declined": [...]} (the shape a desk analyst writes,
see RUNBOOK_NFL_RESEARCH.md section 2). --keep carries over the selections of games that already kicked off from
the existing overlay, unchanged. The result is written to data/nfl/research/<season>-wNN.json and validated against
the published payload; the ranked list is printed.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nfl.desk import DEFAULT_BAND  # noqa: E402


def _start(g: dict) -> str:
    return g.get("kickoff_utc") or g.get("tip_utc") or ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="nfl", choices=("nfl", "nba"))
    ap.add_argument("--season", type=int)
    ap.add_argument("--week", type=int)
    ap.add_argument("--date", help="NBA: the ET date of the slate")
    ap.add_argument("--frags", required=True)
    ap.add_argument("--keep", help="existing overlay whose started-game selections are kept")
    ap.add_argument("--summary", default="")
    ap.add_argument("--analyst", default="Claude research desk")
    ap.add_argument("--best", help="comma-separated selection ids for the Best Picks list, strongest first (default: derived from the spec's rule)")
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    now_s = now.strftime("%Y-%m-%dT%H:%MZ")
    if a.sport == "nba":
        from nba.desk import overlay_path, validate
        from nba.ingest import season_now
        if not a.date:
            print("--date is required for the NBA desk"); return 2
        pf = ROOT / "docs" / "nba" / "days" / f"{a.date}.json"
        season = a.season or season_now(datetime.strptime(a.date, "%Y-%m-%d").date())
        out = {"v": 1, "season": season, "date": a.date, "generated_utc": now.strftime("%Y-%m-%d %H:%M UTC"), "analyst": a.analyst,
               "odds_band": list(DEFAULT_BAND), "summary": a.summary, "games": {}, "selections": [], "wild_cards": [], "declined": []}
        out_path = overlay_path(a.date)
    else:
        from nfl.desk import overlay_path, validate
        if a.season is None or a.week is None:
            print("--season and --week are required for the NFL desk"); return 2
        pf = ROOT / "docs" / "nfl" / "weeks" / f"{a.season}-w{a.week:02d}.json"
        out = {"v": 1, "season": a.season, "week": a.week, "generated_utc": now.strftime("%Y-%m-%d %H:%M UTC"), "analyst": a.analyst,
               "odds_band": list(DEFAULT_BAND), "summary": a.summary, "games": {}, "selections": [], "wild_cards": [], "declined": []}
        out_path = overlay_path(a.season, a.week)
    payload = json.loads(pf.read_text()) if pf.exists() else None
    games = {g["game_id"]: g for g in (payload or {}).get("games", [])}
    kept = 0
    if a.keep and Path(a.keep).exists():
        old = json.loads(Path(a.keep).read_text())
        for key in ("selections", "wild_cards"):
            for s in old.get(key) or []:
                g = games.get(s["game_id"])
                if g and _start(g) <= now_s:
                    out[key].append(s); kept += 1
        for gid, v in (old.get("games") or {}).items():
            g = games.get(gid)
            if g and _start(g) <= now_s:
                out["games"][gid] = v
        if not a.summary:
            out["summary"] = old.get("summary") or ""
    seen = {s["id"] for s in out["selections"]}
    n_frag = 0
    for f in sorted(Path(a.frags).glob("*.json")):
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            print(f"skip {f.name}: {e}"); continue
        gid = d.get("game_id") or f.stem
        if games and gid not in games:
            print(f"skip {f.name}: {gid} not on this slate"); continue
        if gid in out["games"] and any(s["game_id"] == gid for s in out["selections"] if s["id"] in seen):
            print(f"skip {f.name}: {gid} already kicked off (kept from the previous overlay)"); continue
        n_frag += 1
        notes = d.get("notes") or {}
        if any(notes.get(k) for k in ("notes", "weather", "injuries")):
            out["games"][gid] = {"notes": notes.get("notes") or [], "weather": notes.get("weather") or "", "injuries": notes.get("injuries") or [],
                                 "sources": notes.get("sources") or []}
        for key in ("selections", "wild_cards"):
            for s in d.get(key) or []:
                if s.get("id") in seen:
                    print(f"duplicate selection id {s['id']} in {f.name}; skipped"); continue
                s.setdefault("game_id", gid)
                out[key].append(s); seen.add(s["id"])
        for x in d.get("declined") or []:
            if x.get("label") and x.get("why"):
                out["declined"].append({"id": x.get("id") or "none", "label": x["label"], "why": x["why"], "game_id": gid})
    errs = validate(out, payload)
    if errs:
        print(f"{len(errs)} problem(s) in the assembled overlay:")
        for e in errs:
            print(" -", e)
        bad = Path(a.frags) / "_assembled_invalid.json"
        bad.write_text(json.dumps(out, indent=1, ensure_ascii=False))
        print(f"written for inspection: {bad}")
        return 1
    out["selections"].sort(key=lambda s: (-float(s["p"]), -float(s.get("confidence") or 0)))
    # sections and best picks per the spec (the desk session may pass --best to overrule the derived ranking)
    if a.sport == "nfl":
        from nfl.desk import _sections, load_config
        cfg = load_config()
        sections, best = _sections({}, out["selections"], cfg)
        if a.best:
            ids = {x["id"] for x in out["selections"]}
            best = [i.strip() for i in a.best.split(",") if i.strip() in ids]
        out["sections"] = sections
        out["best"] = best
        spec = {x["key"]: x for x in cfg.get("sections") or []}
        for key, lst in sections.items():
            need = int((spec.get(key) or {}).get("min") or 0)
            if len(lst) < need:
                print(f"note: section {key} has {len(lst)} selection(s), the spec asks for at least {need}")
        bs = cfg.get("best") or {}
        if len(best) < int(bs.get("min") or 0):
            print(f"note: best picks has {len(best)}, the spec asks for at least {bs.get('min')}")
    f = out_path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {f}: {len(out['selections'])} selections and {len(out['wild_cards'])} wild cards ({kept} kept from before), {len(out['declined'])} declined, {n_frag} fragments, {len(out['games'])} games with notes")
    if out.get("best"):
        lab = {x["id"]: x for x in out["selections"]}
        print("best picks: " + "; ".join(f"{lab[i]['label']} ({lab[i]['odds']:.2f}, {float(lab[i]['p'])*100:.0f}%)" for i in out["best"]))
    for i, s in enumerate(out["selections"] + out["wild_cards"], 1):
        print(f"{i:2d}. {s['label']:<46} {float(s['odds']):.2f} {s['odds_source']:<11} desk {float(s['p'])*100:.0f}%  {s['grade']} {s['evidence']:<10} conf {s['confidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
