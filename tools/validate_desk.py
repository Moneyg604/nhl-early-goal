"""Validate a research-desk overlay against the spec and the week's published payload before it is committed.

    python tools/validate_desk.py data/nfl/research/2026-w06.json
    python tools/validate_desk.py data/nfl/research/2026-w06.json --payload docs/nfl/weeks/2026-w06.json
    python tools/validate_desk.py data/nba/research/2026-10-20.json --sport nba

Exit status 0 when the overlay is usable, 1 otherwise with every problem listed. This is the strict check: the
owner's spec (data/<sport>/desk_config.json: markets, DraftKings' posted lines only, sections, Best picks, the
selection rules) and DraftKings' price in the odds feed as of now. On success it prints the Best picks, each
section and the full ranked list exactly as the page will show them, plus any notes (a section short of its
minimum, for example). The site build re-checks only the file's structure, so a file that passes here keeps
showing after kickoff and after a line move (the move becomes a line alert on the pick).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("overlay")
    ap.add_argument("--payload", help="payload JSON (default: docs/nfl/weeks/<season>-wNN.json for an NFL week, docs/nba/days/<date>.json for an NBA date)")
    ap.add_argument("--sport", default=None, help="nfl (default) or nba; inferred from the overlay when it has a 'date' key")
    a = ap.parse_args(argv)
    try:
        d = json.loads(Path(a.overlay).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read {a.overlay}: {e}")
        return 1
    if not isinstance(d, dict):
        print("the overlay must be a JSON object")
        return 1
    sport = a.sport or ("nba" if "date" in d and "week" not in d else "nfl")
    if sport == "nba":
        from nba.desk import load_config, merge, notes, validate
        default_pf = ROOT / "docs" / "nba" / "days" / f"{d.get('date')}.json"
    else:
        from nfl.desk import load_config, merge, notes, validate
        try:
            default_pf = ROOT / "docs" / "nfl" / "weeks" / f"{d.get('season')}-w{int(d.get('week') or 0):02d}.json"
        except (TypeError, ValueError):
            default_pf = ROOT / "docs" / "nfl" / "weeks" / "missing.json"
    pf = Path(a.payload) if a.payload else default_pf
    payload = None
    if pf.exists():
        payload = json.loads(pf.read_text())
    else:
        print(f"note: no payload at {pf}; checking the overlay against the spec only (no board or feed checks)")
    errs = validate(d, payload)
    if errs:
        print(f"{len(errs)} problem(s):")
        for e in errs:
            print(" -", e)
        return 1
    print(f"ok: {len(d['selections'])} selections, {len(d.get('wild_cards') or [])} wild cards, {len(d.get('declined') or [])} declined, {len(d.get('games') or {})} games with notes")
    for n in notes(d, payload):
        print("note:", n)
    if payload:
        payload = json.loads(json.dumps(payload))
        desk = merge(payload, d)
        if not desk or not desk.get("ok"):
            print("the merge failed:", (desk or {}).get("errors"))
            return 1
        by = {x["id"]: x for x in desk["selections"]}
        cfg = load_config()

        def row(x):
            b = x.get("board") or {}
            site = f"site {b['p']*100:.0f}%" if b.get("p") is not None else "not on the board"
            return f"{x['label']:<44} {x['odds']:.2f} {x['odds_source']:<10}  desk {x['p']*100:.0f}%  {x['grade']} {x['evidence']:<10} {site}  ({x['mu']})"
        print(f"\n{(cfg.get('best') or {}).get('label') or 'Best picks'} ({len(desk['best'])}){' derived by the spec rule' if desk['spec'].get('derived_best') else ''}:")
        for i, sid in enumerate(desk["best"], 1):
            print(f"{i:2d}. {row(by[sid])}")
        for sp in desk["spec"].get("sections") or []:
            ids = desk["sections"].get(sp.get("key")) or []
            print(f"\n{sp.get('label') or sp.get('key')} ({len(ids)} of {sp.get('min', 0)} to {sp.get('max', '?')}):")
            for i, sid in enumerate(ids, 1):
                print(f"{i:2d}. {row(by[sid])}")
        print("\nEvery selection, as ranked on the page:")
        for i, x in enumerate(desk["selections"], 1):
            print(f"{i:2d}. {row(x)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
