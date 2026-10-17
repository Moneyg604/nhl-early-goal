"""Assemble per-game research fragments into one research-desk overlay, then validate it.

    python tools/assemble_desk.py --season 2026 --week 6 --frags <dir with <game_id>.json> [--keep data/nfl/research/2026-w06.json] [--summary "..."]

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

from nfl.desk import DEFAULT_BAND, overlay_path, validate  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, required=True)
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--frags", required=True)
    ap.add_argument("--keep", help="existing overlay whose started-game selections are kept")
    ap.add_argument("--summary", default="")
    ap.add_argument("--analyst", default="Claude research desk")
    a = ap.parse_args(argv)
    pf = ROOT / "docs" / "nfl" / "weeks" / f"{a.season}-w{a.week:02d}.json"
    payload = json.loads(pf.read_text()) if pf.exists() else None
    games = {g["game_id"]: g for g in (payload or {}).get("games", [])}
    now = datetime.now(timezone.utc)
    now_s = now.strftime("%Y-%m-%dT%H:%MZ")
    out = {"v": 1, "season": a.season, "week": a.week, "generated_utc": now.strftime("%Y-%m-%d %H:%M UTC"), "analyst": a.analyst,
           "odds_band": list(DEFAULT_BAND), "summary": a.summary, "games": {}, "selections": [], "declined": []}
    kept = 0
    if a.keep and Path(a.keep).exists():
        old = json.loads(Path(a.keep).read_text())
        for s in old.get("selections") or []:
            g = games.get(s["game_id"])
            if g and (g.get("kickoff_utc") or "") <= now_s:
                out["selections"].append(s); kept += 1
        for gid, v in (old.get("games") or {}).items():
            g = games.get(gid)
            if g and (g.get("kickoff_utc") or "") <= now_s:
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
            print(f"skip {f.name}: {gid} not in week {a.week}"); continue
        if gid in out["games"] and any(s["game_id"] == gid for s in out["selections"] if s["id"] in seen):
            print(f"skip {f.name}: {gid} already kicked off (kept from the previous overlay)"); continue
        n_frag += 1
        notes = d.get("notes") or {}
        if any(notes.get(k) for k in ("notes", "weather", "injuries")):
            out["games"][gid] = {"notes": notes.get("notes") or [], "weather": notes.get("weather") or "", "injuries": notes.get("injuries") or [],
                                 "sources": notes.get("sources") or []}
        for s in d.get("selections") or []:
            if s.get("id") in seen:
                print(f"duplicate selection id {s['id']} in {f.name}; skipped"); continue
            s.setdefault("game_id", gid)
            out["selections"].append(s); seen.add(s["id"])
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
    f = overlay_path(a.season, a.week)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {f}: {len(out['selections'])} selections ({kept} kept from before), {len(out['declined'])} declined, {n_frag} fragments, {len(out['games'])} games with notes")
    for i, s in enumerate(out["selections"], 1):
        print(f"{i:2d}. {s['label']:<46} {float(s['odds']):.2f} {s['odds_source']:<11} desk {float(s['p'])*100:.0f}%  {s['grade']} {s['evidence']:<10} conf {s['confidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
