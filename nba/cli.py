"""NBA command line.

    python -m nba ingest [--back 1]          ESPN box scores for last season and this one (only new days)
    python -m nba run [--date YYYY-MM-DD]    the day's slate: lines, model, props, bot, desk -> out/nba/
    python -m nba props [--date ...]         price tonight's props from The Odds API within the nightly credit cap
    python -m nba publish                    build docs/nba/ from out/nba/
    python -m nba scorecard                  grade every published day -> docs/nba/scorecard.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import DATA_DIR, OUT_DIR


def today_et() -> str:
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


def cmd_ingest(a) -> None:
    from .ingest import ingest, season_now
    cur = season_now()
    t = time.time()
    counts = ingest(list(range(cur - a.back, cur + 1)))
    print(f"ingest: {counts} in {time.time() - t:.0f}s")


def cmd_props(a) -> None:
    """Price tonight's props: the games with the most projected players, within the configured credits."""
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        print("props: ODDS_API_KEY not set; skipped"); return
    from .desk import load_config
    from .odds import DEFAULT_MARKETS, fetch_props, load
    from .pipeline import day_games
    cfg = (load_config().get("odds") or {})
    credits = int(cfg.get("credits_per_night") or 4)
    markets = list(cfg.get("markets") or DEFAULT_MARKETS)
    per_night = int(cfg.get("games_per_night") or 2)
    date = a.date or today_et()
    games = [g for g in day_games(date) if g.get("state") == "pre"]
    now = datetime.now(timezone.utc)
    snap = load()
    fresh = set()
    for gk, g in (snap.get("games") or {}).items():
        try:
            if now - datetime.strptime(g["props_fetched"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc) < timedelta(hours=20):
                fresh.add(gk)
        except (KeyError, ValueError):
            pass
    games = [g for g in games if f'{g["away"]}@{g["home"]}' not in fresh]
    if not games:
        print("props: nothing to price (no pre-game slate, or every game priced in the last 20 hours)"); return
    # the games the model has the most to say about: closest spreads first (more full-minute games), earliest tips
    games.sort(key=lambda g: (abs(float((g.get("lines") or {}).get("spread") or 0)), g.get("tip_utc") or ""))
    chosen = games[:per_night]
    fetch_props(chosen, credits, markets, key)


def cmd_run(a) -> None:
    from .pipeline import build_day, save_payload
    from .report import render
    date = a.date or today_et()
    p = build_day(date, with_odds=not a.no_odds)
    name = save_payload(p)
    (OUT_DIR / f"day-{name}.html").write_text(render(p), encoding="utf-8")
    print(f"day {date}: {len(p['games'])} games, {p['best_bets']['n_priced']} priced markets in {p['meta']['seconds']}s -> out/nba/day-{name}.json")


def cmd_publish(a) -> None:
    from .site import build_site
    print(f"site: {build_site()}")


def cmd_scorecard(a) -> None:
    from .scorecard import build_scorecard
    sc = build_scorecard()
    print(f"scorecard: {sc.get('leaderboard')}")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="nba")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("ingest"); p.add_argument("--back", type=int, default=1); p.set_defaults(fn=cmd_ingest)
    p = sub.add_parser("run"); p.add_argument("--date"); p.add_argument("--no-odds", action="store_true"); p.set_defaults(fn=cmd_run)
    p = sub.add_parser("props"); p.add_argument("--date"); p.set_defaults(fn=cmd_props)
    p = sub.add_parser("publish"); p.set_defaults(fn=cmd_publish)
    p = sub.add_parser("scorecard"); p.set_defaults(fn=cmd_scorecard)
    a = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    a.fn(a)


if __name__ == "__main__":
    main()
