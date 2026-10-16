"""NFL command line.

    python -m nfl ingest [--back N]          download nflverse files and convert play-by-play (current season always refreshed)
    python -m nfl run [--weeks 2] [--sims N] research + simulate the current week (and the next one when its lines are out)
    python -m nfl publish                    build docs/nfl/ from out/nfl/
    python -m nfl backtest [--seasons ...]   walk-forward validation; writes data/nfl/backtest_latest.json and factors.json
    python -m nfl scorecard                  grade every published week against the results
    python -m nfl live                       ESPN scoreboard snapshot -> docs/nfl/live.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from .config import CFG, DATA_DIR, OUT_DIR


def cmd_ingest(a) -> None:
    from .ingest import fetch_reference, ingest, season_now
    cur = season_now()
    seasons = list(range(cur - a.back, cur + 1))
    t = time.time()
    counts = ingest(seasons, cur)
    fetch_reference(cur)
    print(f"ingest: {counts} in {time.time() - t:.0f}s")


def cmd_run(a) -> None:
    from .ingest import load_schedule, season_now
    from .pipeline import build_week, save_payload
    from .report import render
    from .week import pick_week
    season = a.season or season_now()
    sched = load_schedule()
    if sched is None:
        sys.exit("schedule unavailable")
    wk = a.week or pick_week(sched, season)
    if wk is None:
        print("no regular-season week left to publish")
        return
    reason = os.environ.get("NFL_REASON", "update")
    if os.environ.get("ODDS_API_KEY"):
        try:
            from datetime import datetime, timedelta, timezone

            from .odds import PROPS_AHEAD_HOURS, props_fresh
            from .odds import fetch as fetch_odds
            from .venues import kickoff_utc
            now = datetime.now(timezone.utc)
            s = sched[(sched["season"] == season) & (sched["week"] == wk) & (sched["game_type"] == "REG")]
            window = []
            for r in s.itertuples(index=False):
                k = kickoff_utc(str(r.gameday), str(r.gametime))
                gk = f"{r.away_team}@{r.home_team}"
                # props, once per game: on a pre-kickoff run every game of the next 40 hours not priced in the last
                # 20 (Sunday ~11:45 ET prices Sunday and Monday together); every game of the week on a "props" run.
                # Never a game that has started (the feed would return in-play prices).
                ahead = k is not None and timedelta(minutes=5) <= k - now
                if ahead and (reason == "props" or (reason == "t75" and k - now <= timedelta(hours=PROPS_AHEAD_HOURS) and not props_fresh(gk))):
                    window.append(gk)
            # the odds pull runs on the Wednesday preview, the pre-kickoff builds and an explicit "props" run; props are
            # fetched for the games about to kick off, with the number of markets set by the month's remaining credits
            if reason in ("weekly", "props", "t75") or (reason == "daily" and now.weekday() == 2):
                allg = sched[(sched["season"] == season) & (sched["game_type"] == "REG")]
                games_left = sum(1 for r in allg.itertuples(index=False) if str(r.gameday)[:7] == now.strftime("%Y-%m") and str(r.gameday) >= now.strftime("%Y-%m-%d"))
                fetch_odds(reason, window, games_left=max(games_left, 1))
            else:
                print("odds: not an odds run (lines refresh on Wednesday and before kickoffs)")
        except Exception as e:  # noqa: BLE001
            print(f"odds skipped: {e}")
    weeks = [wk] + [w for w in range(wk + 1, wk + a.weeks) if w <= 18]
    for w in weeks:
        s = sched[(sched["season"] == season) & (sched["week"] == w) & (sched["game_type"] == "REG")]
        if w != wk and s["spread_line"].isna().all():
            print(f"week {w}: no lines yet, skipped")
            continue
        p = build_week(season, w, sims=a.sims, with_weather=not a.no_weather)
        name = save_payload(p)
        html = render(p)
        (OUT_DIR / f"week-{name}.html").write_text(html, encoding="utf-8")
        print(f"week {w}: {len(p['games'])} games in {p['meta']['seconds']}s -> out/nfl/week-{name}.html")


def cmd_publish(a) -> None:
    from .site import build_site
    d = build_site()
    print(f"site: {d}")


def cmd_backtest(a) -> None:
    from . import backtest as B
    res = B.backtest(a.seasons, sims=a.sims, workers=a.workers)
    B.save(res)
    P = res["pooled"]
    fac = {}
    f = DATA_DIR / "factors.json"
    if f.exists():
        try:
            fac = json.loads(f.read_text())
        except json.JSONDecodeError:
            fac = {}
    # blend weights: keep the model's disagreement with the closing line only when it measurably helped
    blend = {}
    for key in ("margin", "total"):
        b = (P.get("blend") or {}).get(key)
        if b and b["w"] > 2 * b["se"]:
            blend[key] = round(max(0.0, min(0.5, b["w"])), 3)
        else:
            blend[key] = 0.0
    fac["blend"] = blend
    kn = B.key_number_check(res["rows"])
    fac["key_numbers"] = kn.get("weights", {}) if kn.get("use") else {}
    fac["key_number_test"] = {k: v for k, v in kn.items() if k != "weights"}
    fac["updated_utc"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    f.write_text(json.dumps(fac, indent=1))
    print(json.dumps({k: (v.get("verdict") if isinstance(v, dict) else v) for k, v in P.items() if k not in ("key_numbers",)}, indent=1))
    print("blend:", blend, "minutes:", res["minutes"])


def cmd_scorecard(a) -> None:
    from .scorecard import build_scorecard
    sc = build_scorecard()
    print(f"scorecard: {sc.get('summary')}")


def cmd_live(a) -> None:
    from .live import snapshot
    n = snapshot()
    print(f"live: {n} games")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="nfl")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest"); p.add_argument("--back", type=int, default=3); p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("run"); p.add_argument("--season", type=int); p.add_argument("--week", type=int); p.add_argument("--weeks", type=int, default=2)
    p.add_argument("--sims", type=int, default=CFG.sims); p.add_argument("--no-weather", action="store_true"); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("publish"); p.set_defaults(fn=cmd_publish)
    p = sub.add_parser("backtest"); p.add_argument("--seasons", type=int, nargs="+", default=[2023, 2024, 2025])
    p.add_argument("--sims", type=int, default=20000); p.add_argument("--workers", type=int, default=4); p.set_defaults(fn=cmd_backtest)
    p = sub.add_parser("scorecard"); p.set_defaults(fn=cmd_scorecard)
    p = sub.add_parser("live"); p.set_defaults(fn=cmd_live)
    a = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    a.fn(a)


if __name__ == "__main__":
    main()
