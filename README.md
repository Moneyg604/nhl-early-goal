# Gill Sports

NHL and NFL research desk (this repository started as Early Goal Desk, the NHL first-5-minute tool; the package is still called `earlygoal`).

**Want it on your phone with no laptop in the loop?** Follow `SETUP.md`: a GitHub repository runs the engine three times a day and publishes the dashboard as an installable web app.

Research engine for the NHL **Under 0.5 goals in the first 5:00** and **first 10:00** markets, plus the 1P and full-game markets. It builds team, goalie and schedule profiles from three seasons of real play-by-play, runs 100,000 Monte Carlo paths per game, and writes a self-contained dashboard that shows every input, the arithmetic behind each number, and the model's own validation on 1,312 real games.

Book prices never enter the ranking. Type your book's price into the dashboard and it shows break-even and EV per game.

## What the validation says (read this first)

Walk-forward on the 2025-26 season, each game predicted only from games played before it, actual starting goalies:

| market | log loss model | league constant | verdict | top quintile hit | bottom quintile hit |
|---|---|---|---|---|---|
| Under 0.5, first 5:00 | 0.6450 | 0.6449 | no ranking edge | 65.3% | 65.6% |
| Under 0.5, first 10:00 | 0.6785 | 0.6781 | no ranking edge | 44.3% | 41.2% |
| FG moneyline (home) | 0.6856 | 0.6922 | beats constant | 64.1% | 47.3% |
| FG home -1.5 | 0.6041 | 0.6118 | beats constant | 42.0% | 22.9% |
| FG away -1.5 | 0.5737 | 0.5800 | beats constant | 33.2% | 19.9% |
| FG over 5.5 | 0.6813 | 0.6824 | beats constant | 62.6% | 53.0% |
| 1P away win | 0.6187 | 0.6223 | beats constant | 37.0% | 25.9% |
| 1P home win, 1P tie | | | no edge | | |

The same result holds on 2024-25 (prior 2023-24), and a direct regression on the early window with tempo, early-goal history, goalie quality, rest, travel and time-zone features was *worse* than the league constant out of sample in both directions (`python -m earlygoal early-signal`). The coefficients flip sign between seasons, which is what noise looks like.

So, for the market you bet daily:

* the true probability of no goal in the first 5:00 is about **66%** (2023-24: 66.0%, 2024-25: 67.5%, 2025-26: 65.5%), and about **42%** for the first 10:00
* nothing measurable before the puck drops moves it by more than a point or two for a given game
* the fair price is about **1.52** for the first-5 under and **2.4** for the first-10 under; at 1.30 you need 76.9% and the long-run EV is roughly −14% per unit no matter which game you pick
* the tool's job for this market is calibration and price discipline, not game selection. The ranking it prints is real but within noise, and the dashboard says so

The simulation does carry information for the full-game markets (moneyline, −1.5 / +1.5, totals) and the 1P away win.

## Quick start

```bash
cd nhl-early-goal
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python -m earlygoal run                 # today's slate: downloads the three season files (~60 MB, first run only), tops up from the NHL API, sims, dashboard
python -m earlygoal run --date 2026-10-14
python -m earlygoal run --days 3        # today, tomorrow and the day after (future days use DailyFaceoff projected starters; the site labels them)
python -m earlygoal run --demo          # synthetic data, no network, to see the layout
python -m earlygoal backtest --season 20252026 --with-sim --save   # rebuilds the validation panel (about a minute)
python -m earlygoal publish             # static site + installable web app in docs/ (what GitHub Pages serves)
python -m earlygoal overrides           # template for confirmed starters
```

A normal daily run takes about 15 seconds after the first download. If the NHL API is unreachable from your network, pass the slate yourself: `--slate-file data/slate-2026-10-13.json` shows the format (game_id, home, away, start_utc).

The dashboard has a table on desktop and a card view on phones (same data, same expandable inputs). Type your book's prices into the price-check box; they are kept in your browser only.

Outputs land in `out/`: `dashboard-<date>.html` (open on any device, nothing external loads), `results-<date>.json` (every number and input), `summary-<date>.csv`.

`data/overrides.json` is where starting goalies go when you have better information than the usage heuristic (DailyFaceoff, beat reporters). Status `confirmed` is what moves a game toward tier A; `expected` and `unconfirmed` are carried through to the dashboard.

## Data

Default source is the sportsdataverse nightly NHL play-by-play release (one parquet per season, built from the NHL API, refreshed through the previous night). The engine downloads 2024-25, 2025-26 and the current season, converts them to compact game records, and tops up any missing recent games from the NHL API (`api-web.nhle.com`). Today's schedule and the DailyFaceoff scrape also come from the network; the scrape is best effort.

`--source api` rebuilds everything from the NHL API instead (about 1,300 requests per season, cached).

## How the numbers are made

For every time bin of the game, each team's goal rate per minute is a chain of multiplicative factors on the league hazard curve for that bin (the first minute is quiet, the last two minutes carry empty-net dynamics):

```
home ice × shot rate for × opponent shot rate against × finishing × opposing goalie × rest / travel context
```

Every factor is measured from event data and shrunk toward the league (current season weight 1.0, last season 0.55, two seasons back 0.25; shrinkage constants in `config.py` were chosen on the backtest). Factors are normalised so each averages exactly 1 across the league. The simulation draws Poisson goals per bin, plays 3-on-3 OT and the shootout, and pulls the goalie in the final two minutes when a team trails by one or two, which is what makes the −1.5 / +1.5 numbers realistic. First-5 and first-10 are also computed analytically (`exp(−Σλ)`) and both are shown with the Monte Carlo error.

Tiers: **A** both profiles measured on 20+ games this season and both goalies confirmed; **B** a goalie only expected or projected, or a profile leaning on last season; **C** an input unmeasured. Every input carries a measured / partial / unmeasured label.

## What the model cannot see

Line deployment, referee tendencies, injuries and late scratches (unless entered in overrides), and anything after the puck drops. None of these showed up as predictive at the team level either; whether they matter at the game level is untested because the data is not public pre-game.

## Layout

```
earlygoal/
  config.py       every knob (shrinkage, priors, bins, tiers)
  ingest_sdv.py   sportsdataverse parquet -> game records (default source)
  ingest.py       NHL API -> game records (top-up and fallback), schedule, rest/travel
  nhl_api.py      cached NHL API client
  arenas.py       coordinates and time zones for travel features
  features.py     league hazard curve, team / goalie profiles, context effects, normalisation
  goalies.py      starter resolution: overrides -> DailyFaceoff -> usage heuristic
  model.py        hazard chain per team per bin, labels, tiers, audit trail
  sim.py          vectorised Monte Carlo
  rank.py         picks, ranking, payload, csv
  report.py       dashboard
  site.py         static site / PWA builder (docs/)
  backtest.py     walk-forward validation (early markets + joint markets)
  early_model.py  research: direct early-window regression (does not beat the constant)
  demo.py         synthetic league for pipeline tests
  cli.py          commands
tests/            pytest
data/             season records, overrides.json, backtest_latest.json (validation panel source)
docs/             the published site (built by `publish`, committed by the GitHub Action)
.github/          the scheduled workflow (see SETUP.md)
```

## Keeping it honest as the season goes

* Re-run `backtest --with-sim --save` monthly on the current season to refresh the validation panel with games the model has actually been scored on.
* Re-run `early-signal` once 40+ games per team exist. If a feature ever beats the constant out of sample in two seasons running, promote it; nothing has so far.
* Track your own tickets against the stated probabilities. If your hit rate on the first-5 under sits near 66%, the model is right and the price is the whole story.

## NFL section (`nfl/`, published under `/nfl/`)

Same site, separate section (the NHL / NFL switch sits next to the title). Markets: moneyline, spread, total,
1st half total, 2nd half total (overtime included), team field goals made, QB passing yards, QB passing
touchdowns, anytime touchdown scorer.

How it works, in one paragraph: every drive of the last three seasons (nflverse play-by-play) is classified by
half, how it started, time left and score margin; a team's offense and defense are its touchdown, field-goal-try
and turnover rates against the league table for the same situations, shrunk toward the league. 100,000 games per
matchup are simulated drive by drive (overtime included), with pace, dropbacks, yards per dropback, the starting
quarterback, the kicker, home field, rest, roof, wind and cold. When the book's spread and total are known the
simulation is anchored to them, so every derived market agrees with the game line the market prices well.

```bash
python -m nfl ingest            # nflverse play-by-play, schedule + lines, injuries, depth charts, rosters
python -m nfl run --weeks 2     # this week (and next week once its lines are out) -> out/nfl/
python -m nfl publish           # docs/nfl/
python -m nfl backtest          # walk-forward validation -> data/nfl/backtest_latest.json, factors.json
python -m nfl scorecard         # grade published leans -> docs/nfl/scorecard.json
python -m nfl live              # ESPN scoreboard + box scores -> docs/nfl/live.json
```

On the page: the Week tab (every game, every market, live ESPN scores and box scores), the Scanner (every
selection the model prices, about 860 a week, with win probability, fair odds, best book price, EV, the backtest
hit rate for that probability band and an S-D grade; filters and sorting; a slip that prices same-game legs
jointly from the simulated games), Research (team stats with league ranks, QB logs, kickers, injuries, snap
shares, the measured factors and every tested change), Results (your bet tracker with ROI, grades and CLV, the
week's graded leans, the track record) and About (validation with log loss, Brier score and calibration).

Moneyline and spread probabilities are each game's simulated outcomes reweighted to the market's vig-free
prices: the simulated margins run about 7% wider than real ones, and the market prices beat the raw simulation
walk-forward. Sportsbook prices come from The Odds API when `ODDS_API_KEY` is set (game lines on every build;
QB yards, TD passes, anytime TD and half totals on the pre-kickoff builds, inside the free plan's credits).

What the walk-forward test says is on the page (About tab) and in `data/nfl/backtest_latest.json`. In short: the
model alone does not beat the closing moneyline, spread or total, so those follow the market; QB passing yards,
QB touchdown passes and anytime touchdowns beat their baselines; half totals and team field goals do not. The
page labels every market with its verdict. Workflows: `update-nfl.yml` (daily, and 75 minutes before each
kickoff window via the keeper), `nfl-revalidate.yml` (monthly), NFL live scores ride on `live-scores.yml`.

## Optional connections (GitHub repository secrets)

Set any of these under Settings > Secrets and variables > Actions, and the next build uses them:

| secret | what it enables |
|---|---|
| `DISCORD_WEBHOOK_URL` | the slate, top picks and goalie changes posted to a Discord channel at every build (morning, update, two hours before puck drop) |
| `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID` | the same message to a Telegram chat |
| `ODDS_API_KEY` | sportsbook prices from The Odds API: NHL moneyline, puck line and total; NFL moneyline, spread, total, QB passing yards and TD passes, anytime TD and half totals; best price per side and the market consensus, with EV against the model |

Nothing else needs configuring. The keeper workflow schedules every job, the monthly revalidation re-tests every switchable factor
(`data/factors.json`) and refreshes the validation panel, and MoneyPuck expected-goals data is fetched on the GitHub runner.
