"""Validate a research-desk overlay against the week's published payload before it is committed.

    python tools/validate_desk.py data/nfl/research/2026-w06.json
    python tools/validate_desk.py data/nfl/research/2026-w06.json --payload docs/nfl/weeks/2026-w06.json

Exit status 0 when the overlay is usable (and prints the selections as the page will rank them), 1 otherwise with
every problem listed. The research session runs this before `git commit`; the site build runs the same checks and
shows the errors on the page instead of the desk when they fail, so a bad file never breaks the build.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nfl.desk import merge, validate  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("overlay")
    ap.add_argument("--payload", help="week payload JSON (default: docs/nfl/weeks/<season>-wNN.json for the overlay's week)")
    a = ap.parse_args(argv)
    try:
        d = json.loads(Path(a.overlay).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"cannot read {a.overlay}: {e}")
        return 1
    pf = Path(a.payload) if a.payload else ROOT / "docs" / "nfl" / "weeks" / f"{d.get('season')}-w{int(d.get('week') or 0):02d}.json"
    payload = None
    if pf.exists():
        payload = json.loads(pf.read_text())
    else:
        print(f"note: no payload at {pf}; checking the overlay's shape only")
    errs = validate(d, payload)
    if errs:
        print(f"{len(errs)} problem(s):")
        for e in errs:
            print(" -", e)
        return 1
    print(f"ok: {len(d['selections'])} selections, {len(d.get('declined') or [])} declined, {len(d.get('games') or {})} games with notes")
    if payload:
        desk = merge(payload, d)
        for i, x in enumerate(desk["selections"], 1):
            b = x.get("board") or {}
            site = f"site {b['p']*100:.0f}%" if b.get("p") is not None else "not on the board"
            print(f"{i:2d}. {x['label']:<44} {x['odds']:.2f}  desk {x['p']*100:.0f}%  {x['grade']} {x['evidence']:<10} {site}  ({x['mu']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
