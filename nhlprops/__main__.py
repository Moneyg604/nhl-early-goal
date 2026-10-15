"""python -m nhlprops ingest | backtest | run

    ingest    [--seasons 2023 2024 2025 2026 2027]   skater / team records from the sportsdataverse parquets
    backtest  [--seasons 2024 2025 2026]            walk-forward validation -> data/nhlprops/backtest_latest.json
    run       [--date YYYY-MM-DD]                   props for a day from out/results-<date>.json (the NHL run builds them itself)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import DATA_DIR, OUT_DIR


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="nhlprops")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest"); p.add_argument("--seasons", type=int, nargs="+", default=[2023, 2024, 2025, 2026, 2027]); p.add_argument("--force", action="store_true")
    p = sub.add_parser("backtest"); p.add_argument("--seasons", type=int, nargs="+", default=[2024, 2025, 2026]); p.add_argument("--rebuild-days", type=int, default=7)
    p = sub.add_parser("run"); p.add_argument("--date", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "ingest":
        from .ingest import ingest
        ingest(a.seasons, force=a.force)
    elif a.cmd == "backtest":
        from .backtest import run, save
        res = run(a.seasons, rebuild_days=a.rebuild_days)
        save(res)
        S = res["pooled"]
        for k, v in S.items():
            if isinstance(v, dict) and v.get("n"):
                print(f"{k:12s} n={v['n']:>7,} gain {v['gain']:+.5f} ± {v['se']:.5f}  {v['verdict']}")
        print(f"saved {DATA_DIR / 'backtest_latest.json'} ({res['minutes']} min)")
    elif a.cmd == "run":
        from .pipeline import build_day
        from .report import write
        src = Path("out") / f"results-{a.date}.json"
        if not src.exists():
            sys.exit(f"no NHL results for {a.date} ({src}); run `python -m earlygoal run --date {a.date}` first")
        r = json.loads(src.read_text())
        slate = [{"game_id": g["game_id"], "home": g["home"], "away": g["away"], "start_utc": g.get("start_utc")} for g in r["games"]]
        pp = build_day(a.date, slate, None, None)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        write(pp, OUT_DIR / f"props-{a.date}.html")
        (OUT_DIR / f"props-{a.date}.json").write_text(json.dumps(pp))
        print(f"wrote {OUT_DIR / f'props-{a.date}.html'}")


if __name__ == "__main__":
    main()
