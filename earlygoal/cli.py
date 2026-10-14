"""Command line entry point.

  python -m earlygoal run                          # today's slate: data refresh, 100k sims per game, dashboard
  python -m earlygoal run --date 2026-10-14
  python -m earlygoal run --demo                   # synthetic data, no network
  python -m earlygoal ingest                       # refresh the season files only
  python -m earlygoal backtest                     # walk-forward calibration on the current season
  python -m earlygoal backtest --season 20252026   # a full past season (what the README numbers come from)
  python -m earlygoal early-signal                 # the direct early-window regression test (research)
  python -m earlygoal publish                      # build docs/ (static site + installable web app)
  python -m earlygoal overrides                    # write a data/overrides.json template for starters

Data source: the sportsdataverse nightly play-by-play release (three parquet
files) by default, topped up from the NHL API for any game the release has
not caught up with. `--source api` uses the NHL API only.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import CFG, DATA_DIR, MODEL_VERSION, OUT_DIR, OVERRIDES_FILE, ROOT, prior_seasons_for
from .features import build_profiles
from .goalies import load_overrides, scrape_dailyfaceoff
from .ingest import GameRecord, games_file, ingest_season, load_games, slate_for_date
from .ingest_sdv import attach_rest_from_records, ingest_sdv_season
from .nhl_api import NHLClient
from .pipeline import run_slate
from .rank import write_csv
from .report import write_dashboard


def today_et() -> str:
    return datetime.now(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d")


def season_for(date: str) -> int:
    y, m = int(date[:4]), int(date[5:7])
    return (y * 10000 + y + 1) if m >= 9 else ((y - 1) * 10000 + y)


# ----------------------------------------------------------------- data

def load_season(season: int, source: str, refresh: bool, client: NHLClient | None, up_to_date: str | None = None) -> list[GameRecord]:
    """Season records from the chosen source, with API top-up for the current season."""
    recs: list[GameRecord] = []
    if source in ("sdv", "auto"):
        try:
            recs = ingest_sdv_season(season, force_download=refresh, is_current=up_to_date is not None)
        except Exception as e:  # noqa: BLE001
            print(f"  sportsdataverse download failed for {season} ({e}); falling back to cached records / NHL API", file=sys.stderr)
            recs = load_games(season)
    if not recs and source == "api":
        recs = load_games(season)
    if client is not None and (source in ("api", "auto") or not recs) and up_to_date:
        # top-up: anything final before up_to_date that the release has not caught up with
        try:
            have = {r.game_id for r in recs}
            fresh = ingest_season(client, season, up_to_date=up_to_date, verbose=False, force_schedule=refresh)
            added = [r for r in fresh if r.game_id not in have]
            if added:
                recs = sorted(recs + added, key=lambda r: (r.date, r.game_id))
                attach_rest_from_records(recs)
                with games_file(season).open("w") as fh:
                    for r in recs:
                        fh.write(r.to_json() + "\n")
                print(f"  {season}: +{len(added)} games topped up from the NHL API")
        except Exception as e:  # noqa: BLE001
            print(f"  NHL API top-up skipped ({e})", file=sys.stderr)
    return recs


def load_slate(date: str, client: NHLClient | None, slate_file: str | None, current: list[GameRecord], extra_schedule_files: list[str] | None = None) -> list[dict]:
    if slate_file:
        slate = json.loads(Path(slate_file).read_text())
    elif client is not None:
        try:
            slate = slate_for_date(client, date, force=True)
        except Exception as e:  # noqa: BLE001
            raise SystemExit(f"could not fetch the {date} schedule from the NHL API ({e}). "
                             "Check the connection, or pass --slate-file with the games (see data/slate-2026-10-13.json for the format).")
    else:
        raise SystemExit("no slate: pass --slate-file or allow NHL API access")
    for g in slate:
        g.setdefault("date", date)
        g.setdefault("season", season_for(date))
    # rest/travel from the records themselves (covers the file-based source too); games already played
    # but not yet in the records (yesterday's, when the data release lags) can be supplied as extra files
    future = [{"game_id": g["game_id"], "date": g["date"], "start_utc": g.get("start_utc", f"{date}T23:00:00Z"), "home": g["home"], "away": g["away"], "state": "FUT"} for g in slate]
    known = {r.game_id for r in current} | {g["game_id"] for g in slate}
    for ef in extra_schedule_files or []:
        for g in json.loads(Path(ef).read_text()):
            if g["game_id"] not in known and g["date"] < date:
                future.append({"game_id": g["game_id"], "date": g["date"], "start_utc": g.get("start_utc", f"{g['date']}T23:00:00Z"), "home": g["home"], "away": g["away"], "state": "OFF"})
                known.add(g["game_id"])
    ctx = attach_rest_from_records(current, future)
    for g in slate:
        if not (g.get("rest") or {}).get("home"):
            g["rest"] = ctx.get(g["game_id"], {})
    return slate


# ------------------------------------------------------------- commands

def cmd_ingest(args: argparse.Namespace) -> None:
    date = args.date or today_et()
    client = None if args.source == "sdv" else NHLClient()
    cur = season_for(date)
    for s in prior_seasons_for(cur) + [cur]:
        print(f"Loading {s} ...")
        load_season(s, args.source, refresh=(s == cur), client=client, up_to_date=date if s == cur else None)
    print(f"done; records in {DATA_DIR}")


def cmd_run(args: argparse.Namespace) -> None:
    date = args.date or today_et()
    sims = args.sims
    meta = {"sims": sims, "model_version": MODEL_VERSION}
    if args.demo:
        from .demo import build_demo

        prior, current, slate, _ = build_demo(args.seed or 7)
        lp, teams, goalies = build_profiles(current, prior)
        overrides, dfo = {}, {}
        meta.update({"demo": True, "goalie_source": "usage heuristic (demo)"})
        date = "2026-10-13"
    else:
        client = None if args.source == "sdv" and args.slate_file else NHLClient()
        cur = season_for(date)
        current = load_season(cur, args.source, args.refresh, client, up_to_date=date)
        prior = []
        for s in prior_seasons_for(cur):
            prior += load_season(s, args.source, args.refresh and args.source == "api", client)
        if not prior:
            raise SystemExit(f"no prior-season data for {prior_seasons_for(cur)}; run `python -m earlygoal ingest`")
        if not current:
            print(f"warning: no final games found yet for season {cur}; profiles rest on prior seasons only", file=sys.stderr)
        if args.backfill:
            # re-create the slate of a past date from the records and hide that day's results from the model
            played = [g for g in current if g.date == date]
            if not played:
                raise SystemExit(f"no final games on {date} in the records")
            bf = Path(DATA_DIR / f"slate-{date}-backfill.json")
            bf.write_text(json.dumps([{"game_id": g.game_id, "date": date, "season": cur, "start_utc": g.start_utc, "home": g.home, "away": g.away,
                                       "home_id": 0, "away_id": 0, "venue": g.home, "state": "FUT"} for g in played], indent=1))
            args.slate_file = str(bf)
            current = [g for g in current if g.date < date]
            meta["backfill"] = True
        lp, teams, goalies = build_profiles(current, prior, current_season=cur)
        slate = load_slate(date, client, args.slate_file, current, args.extra_schedule)
        if not slate:
            raise SystemExit(f"no regular-season games on {date}")
        overrides = load_overrides()
        dfo = {} if args.no_dfo else scrape_dailyfaceoff(client, date)
        src = []
        if overrides.get(date) or overrides.get("*"):
            src.append("overrides")
        if dfo:
            src.append("dailyfaceoff")
        src.append("usage heuristic for the rest")
        meta.update({"goalie_source": " + ".join(src), "dfo_teams": len(dfo), "data_through": current[-1].date if current else "n/a"})
        if not dfo and not args.no_dfo:
            print("note: DailyFaceoff scrape returned nothing; goalies come from overrides.json or usage. Put starters in data/overrides.json for tier A.")

    bt = DATA_DIR / "backtest_latest.json"
    if bt.exists():
        meta["validation"] = json.loads(bt.read_text())
    scf = DATA_DIR / "scorecard.json"
    if scf.exists() and not args.demo:
        meta["scorecard"] = json.loads(scf.read_text()).get("summary", {})
    print(f"{date}: {len(slate)} games, profiles from {lp.games} games ({len(current)} this season, data through {meta.get('data_through', 'n/a')}); simulating {sims:,} paths per game ...")
    meta.update({"current_season_games": len(current), "prior_season_games": len(prior)})
    payload, _ = run_slate(slate, lp, teams, goalies, date, overrides=overrides, dfo=dfo, sims=sims, seed=args.seed, meta=meta)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = f"{date}{'-demo' if args.demo else ''}"
    html = write_dashboard(payload, OUT_DIR / f"dashboard-{tag}.html")
    (OUT_DIR / f"results-{tag}.json").write_text(json.dumps(payload, indent=1))
    write_csv(payload["games"], OUT_DIR / f"summary-{tag}.csv")

    print()
    print(f"{'#':>2} {'matchup':<10} {'tier':<4} {'U0.5 F5':>8} {'U0.5 F10':>9} {'1P -0.5':>12} {'1P +0.5':>12} {'FG ML':>12} {'FG -1.5':>12} {'proj':>11}")
    for g in sorted(payload["games"], key=lambda x: x["rank_u05_first5"]):
        m = g["markets"]
        print(f"{g['rank_u05_first5']:>2} {g['matchup']:<10} {g['tier']:<4} {m['u05_first5']['p']*100:7.1f}% {m['u05_first10']['p']*100:8.1f}% "
              f"{m['p1_minus05']['pick']:>5} {m['p1_minus05']['p']*100:5.1f}% {m['p1_plus05']['pick']:>5} {m['p1_plus05']['p']*100:5.1f}% "
              f"{m['fg_ml']['pick']:>5} {m['fg_ml']['p']*100:5.1f}% {m['fg_spread']['pick']:>5} {m['fg_spread']['p']*100:5.1f}% "
              f"{g['projected']['home']:5.2f}-{g['projected']['away']:<5.2f}")
    potd = payload["pick_of_day"]
    if potd:
        print(f"\nPick of the day: {potd['matchup']} {potd['market']} {potd['p']*100:.1f}% (fair {potd['fair']:.2f}, tier {potd['tier']})")
    print(f"\ndashboard: {html}\nresults:   {OUT_DIR / f'results-{tag}.json'}\ncsv:       {OUT_DIR / f'summary-{tag}.csv'}")


def _seasons_for_backtest(args: argparse.Namespace) -> tuple[list[GameRecord], list[GameRecord], int]:
    if args.demo:
        from .demo import build_demo

        prior, current, _, _ = build_demo(args.seed or 7)
        return prior, current, 0
    test_season = args.season or season_for(args.date or today_et())
    prior_seasons = prior_seasons_for(test_season)
    current = load_games(test_season)
    prior = []
    for s in prior_seasons:
        prior += load_games(s)
    if not current:
        raise SystemExit(f"no games on disk for {test_season}; run `python -m earlygoal ingest` first")
    if not prior:
        raise SystemExit(f"no prior-season games on disk for {prior_seasons}")
    return prior, current, test_season


def cmd_backtest(args: argparse.Namespace) -> None:
    from .backtest import print_report, run_backtest

    prior, current, test_season = _seasons_for_backtest(args)
    s = run_backtest(prior, current, start=args.start, end=args.end, projected_goalies=args.projected_goalies, with_sim=args.with_sim, sim_paths=20000)
    print_report(s)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows = s.pop("rows", [])
    s["season"] = test_season
    s["games"] = len(rows)
    (OUT_DIR / f"backtest-{test_season}.json").write_text(json.dumps(s, indent=1, default=float))
    if args.save:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        (DATA_DIR / "backtest_latest.json").write_text(json.dumps(s, indent=1, default=float))
        print(f"saved as the validation panel source: {DATA_DIR / 'backtest_latest.json'}")


def cmd_early_signal(args: argparse.Namespace) -> None:
    """Research check: does a direct regression on the early window beat the league rate out of sample?"""
    from .early_model import evaluate, walk_forward_rows

    prior, current, test_season = _seasons_for_backtest(args)
    y = test_season // 10000
    older = load_games((y - 2) * 10000 + (y - 1))
    train_prior = [g for g in prior if g.season == (y - 1) * 10000 + y]
    rows_train = walk_forward_rows(older, train_prior) if older else []
    rows_test = walk_forward_rows(train_prior, current)
    if not rows_train:
        raise SystemExit("need three seasons on disk for this test (train season walk-forward needs its own prior)")
    for l2 in (10, 30, 100, 300):
        r = evaluate(rows_train, rows_test, l2)
        print(f"\nL2={l2}: train {(y-1)}-{str(y)[2:]} -> test {y}-{str(y+1)[2:]}")
        for w in (5, 10):
            x = r[f"first{w}"]
            print(f"  first {w}: log loss {x['logloss_model']:.5f} vs league constant {x['logloss_base']:.5f}  mean {x['mean_pred']:.3f} actual {x['actual']:.3f}  top-quintile actual {x['top_quintile_actual']:.3f} bottom {x['bottom_quintile_actual']:.3f}")
        print("  coefficients (first 5):", r["coef5"])


def cmd_scorecard(args: argparse.Namespace) -> None:
    """Score previously published days against final results and write data/scorecard.json."""
    from .scorecard import payload_from_page, update_scorecard

    date = args.date or today_et()
    cur = season_for(date)
    client = None if args.source == "sdv" else NHLClient()
    current = load_season(cur, args.source, False, client, up_to_date=date)
    records = {g.game_id: g for g in current}
    payloads = []
    for pth in args.pages or []:
        p = Path(pth)
        if not p.exists():
            print(f"  skip missing {p}", file=sys.stderr)
            continue
        pl = payload_from_page(p) if p.suffix == ".html" else json.loads(p.read_text())
        if pl and pl.get("games") and not (pl.get("meta") or {}).get("demo"):
            payloads.append(pl)
    existing = None
    if args.scorecard and Path(args.scorecard).exists():
        existing = json.loads(Path(args.scorecard).read_text())
    sc = update_scorecard(existing, payloads, records)
    out = DATA_DIR / "scorecard.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(sc, indent=1))
    s = sc["summary"]
    print(f"scorecard: {s['games_scored']} games over {s['days_scored']} days scored; pending days: {sc['pending'] or 'none'}")
    for k, v in s["markets"].items():
        print(f"  {k:<12} n={v['n']:4d}  hit {v['hit_rate']*100:5.1f}%  predicted {v['mean_pred']*100:5.1f}%  brier {v['brier']:.4f}")
    print(f"written: {out}")


def cmd_publish(args: argparse.Namespace) -> None:
    from .site import build_site

    prior = []
    if args.prior_days and Path(args.prior_days).exists():
        prior = json.loads(Path(args.prior_days).read_text()).get("days", [])
    site = build_site(site_dir=Path(args.site_dir) if args.site_dir else ROOT / "docs", keep_days=args.keep_days, prior_days=prior, artifact=args.artifact)
    print(f"site written to {site} (open index.html, or serve the folder from GitHub Pages)")


def cmd_overrides(args: argparse.Namespace) -> None:
    date = args.date or today_et()
    template = {
        "_how": "Keyed by date, then team. starter = goalie name (as on NHL rosters) or playerId. status = confirmed | expected | unconfirmed. Use '*' as the date to apply every day.",
        date: {
            "NYI": {"starter": "Ilya Sorokin", "status": "confirmed", "note": "beat reporter"},
            "VAN": {"starter": "Kevin Lankinen", "status": "expected", "source": "dailyfaceoff"},
        },
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if OVERRIDES_FILE.exists() and not args.force:
        print(f"{OVERRIDES_FILE} exists; use --force to overwrite")
        return
    OVERRIDES_FILE.write_text(json.dumps(template, indent=2))
    print(f"wrote {OVERRIDES_FILE}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="earlygoal", description="NHL early-goal research engine")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ingest", help="download / refresh season play-by-play records")
    a.add_argument("--date", help="reference date (YYYY-MM-DD), default today ET")
    a.add_argument("--source", choices=["auto", "sdv", "api"], default="auto")
    a.set_defaults(fn=cmd_ingest)

    r = sub.add_parser("run", help="research the slate, simulate, write dashboard")
    r.add_argument("--date", help="slate date YYYY-MM-DD, default today ET")
    r.add_argument("--sims", type=int, default=CFG.sims, help="Monte Carlo paths per game (default 100000)")
    r.add_argument("--seed", type=int, default=None)
    r.add_argument("--source", choices=["auto", "sdv", "api"], default="auto")
    r.add_argument("--refresh", action="store_true", help="force re-download of the season files")
    r.add_argument("--slate-file", help="JSON list of games (game_id, home, away, start_utc) instead of the NHL API schedule")
    r.add_argument("--extra-schedule", nargs="*", default=[], help="slate-format files for recent days whose games may not be in the data yet (rest/travel only)")
    r.add_argument("--no-dfo", action="store_true", help="skip the DailyFaceoff starting-goalie scrape")
    r.add_argument("--demo", action="store_true", help="synthetic data, no network")
    r.add_argument("--backfill", action="store_true", help="re-run a past date as if that morning (for scorecard tests); starters projected")
    r.set_defaults(fn=cmd_run)

    b = sub.add_parser("backtest", help="walk-forward calibration of first-5 / first-10 probabilities")
    b.add_argument("--date", help="reference date for season selection")
    b.add_argument("--season", type=int, help="season to test, e.g. 20252026")
    b.add_argument("--start")
    b.add_argument("--end")
    b.add_argument("--projected-goalies", action="store_true", help="use the usage heuristic instead of actual starters")
    b.add_argument("--with-sim", action="store_true", help="also simulate each game (20k paths) to score FG ML / spread / totals")
    b.add_argument("--save", action="store_true", help="store the result as the dashboard's validation panel")
    b.add_argument("--demo", action="store_true")
    b.add_argument("--seed", type=int, default=None)
    b.set_defaults(fn=cmd_backtest)

    e = sub.add_parser("early-signal", help="research: direct early-window regression vs the league rate")
    e.add_argument("--date")
    e.add_argument("--season", type=int)
    e.add_argument("--demo", action="store_true")
    e.add_argument("--seed", type=int, default=None)
    e.set_defaults(fn=cmd_early_signal)

    scp = sub.add_parser("scorecard", help="score published days against final results (track record)")
    scp.add_argument("--date", help="reference date, default today ET")
    scp.add_argument("--source", choices=["auto", "sdv", "api"], default="auto")
    scp.add_argument("--pages", nargs="*", help="published day pages (.html) or results-<date>.json files to score")
    scp.add_argument("--scorecard", help="existing scorecard.json to extend")
    scp.set_defaults(fn=cmd_scorecard)

    pb = sub.add_parser("publish", help="build the static site / installable web app in docs/")
    pb.add_argument("--site-dir", help="output folder (default docs/)")
    pb.add_argument("--keep-days", type=int, default=30)
    pb.add_argument("--prior-days", help="a days.json from a previous publish, so earlier slates stay in the selector")
    pb.add_argument("--artifact", action="store_true", help="also write index.artifact.html (no document skeleton)")
    pb.set_defaults(fn=cmd_publish)

    o = sub.add_parser("overrides", help="write a data/overrides.json template")
    o.add_argument("--date")
    o.add_argument("--force", action="store_true")
    o.set_defaults(fn=cmd_overrides)

    args = ap.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main()
