# NBA research desk runbook (the scheduled Claude session)

The NBA desk follows the NFL runbook (`RUNBOOK_NFL_RESEARCH.md`) in every respect that is not sport-specific:
the ground rules in section 0 (no probability without inputs, show the arithmetic, do not anchor, qualitative reads
run optimistic, verify availability independently, the honest scorecard), the write-up fields and grades in
section 4, the commit / rebuild / check steps in section 5 and the owner's spec changes in section 6. What differs
is below.

## The NBA spec (`data/nba/desk_config.json`), read it first

The NBA spec is its own file and differs from the NFL one:

- `odds_rule: "band"`: only DraftKings prices inside `odds_band` (1.35 to 2.20) are eligible.
- `lines: "any"`: DraftKings' posted line, or a DraftKings alternate line when `markets.alts` is true (it is). A price
  you could not confirm on DraftKings may be listed as `"unverified"` (it is labelled on the page and never a Best pick).
- `markets`: ml, spread, total, pts, reb, ast, threes, pra, alts.
- No sections yet. `best`: 3 to 6 Best picks, the strongest evidence of winning, one per player, at most two per game
  (fewer on a one- or two-game night is fine; say so in `summary`).
- `wild_cards`: on, up to 2, prices 2.21 to 4.50, desk chance at least 0.30, in their own `wild_cards` list.
- `selection`: `min_p` 0.52, at most 3 per game and 16 in total, one pick per player per market.
- `instructions`: the owner's plain-English rules (none yet); mandatory when present.

## Files

- Settings: `data/nba/desk_config.json` (band, wild cards, markets `ml spread total pts reb ast threes pra alts`,
  selection rules, the research variables, the nightly Odds API cap).
- Overlay: `data/nba/research/<date>.json`, keyed by the ET date (`"date": "2026-10-20"`, no `"week"`), with
  `"season": 2027` for the 2026-27 season. Everything else as the NFL schema at the top of `nfl/desk.py`.
- Payload: `docs/nba/days.json` names the current day; `docs/nba/days/<date>.json` is the day's payload
  (games with `tip_utc`, `lines`, `injuries`, `model`, `markets`, `research` ratings, `props` with each player's
  projection per stat, and `best_bets.ranked` with every DraftKings-priced market; `bot.extra` holds the model lines
  for props the free credits did not price).
- Validate: `python tools/validate_desk.py data/nba/research/<date>.json --payload docs/nba/days/<date>.json --sport nba`
  (the strict check: the NBA spec, the board and DraftKings' price in the feed; it prints the Best picks and the list).
- Assemble per-game fragments (same fragment shape as the NFL runbook, section 2):
  `python tools/assemble_desk.py --sport nba --date <date> --frags <dir> --keep data/nba/research/<date>.json --summary "..."`
  (optional `--best <id,id,...>` for the desk's own Best-pick order).
- Rebuild: `gh workflow run update-nba.yml --ref main -R Moneyg604/nhl-early-goal -f reason=research`.

## Prices

Game lines (spread, total, moneyline) are DraftKings' own, from ESPN, and are `odds_source: "feed"`. The total's
prices are not in that feed (1.91 each side is assumed on the board), so a selection on a total needs DraftKings'
actual price from a page showing its board today (`"draftkings"`). Player props: the feed prices two games a
night within the credit cap (`"feed"` for those); every other prop needs a DraftKings price read today
(`"draftkings"`), else `"unverified"`. Alternate lines the same.

## Research checklist (per game)

1. Availability: the official injury report (ESPN's is in the payload), the afternoon shootaround and pregame
   notes from beat writers (who is out, questionable, starting, on a minutes limit, back from injury), and the
   second night of a back-to-back (rest days for stars).
2. Minutes: the current rotation (last five games), the starting five, a blowout risk from the spread, overtime
   history is noise.
3. Matchup: the opponent's defensive rating and pace (both in the payload's `research`), rim protection, who guards
   the player, the opponent's defence against the player's position (points, rebounds and assists allowed), home
   and away splits only when the sample is large.
4. Usage and form, last ten games: shots and free throws per game, usage rate, assist rate, rebound rate, minutes
   trend, three-point attempts and rate.
5. Lineup shifts: when a starter is out, who inherits his minutes and shots (the model does not do this yet; the
   desk must).
6. Game script: spread, total, pace, expected possessions.
7. Line movement: the morning number vs the pre-tip number (two pulls a day).
8. Situational: back-to-backs, three games in four nights, travel, altitude (Denver, Utah), rest advantage.

## Arithmetic (per market)

- Points: minutes × points per minute (last ten games, blended with the season) × opponent defensive rating ÷
  league × game pace ÷ league pace = mean; sd from the player's own game log (the payload has the model's mean
  and sd per stat for each player). P(over L) = Φ((mean − L) ÷ sd). Rebounds and assists the same with pace only.
  Threes: attempts × rate, Poisson. PRA: the sum, sd about 0.3 × mean.
- Moneyline and spread: expected margin from the ratings (the payload's `model.margin`), adjusted for who is
  out tonight (a star out is worth 3 to 6 points, written down with the source); home court +2.3; margin sd
  12.6; P(cover) = Φ((margin + line) ÷ 12.6).
- Totals: pace × efficiencies (the payload's `model.total`), adjusted for who is out; sd 18.5.

## Selections

Fewer, better selections: up to the spec's 16 across a full slate, at most three per game, inside the band; up to
two wild cards; then the Best picks (3 to 6, from the selections, by evidence, one per player, at most two per game).
Prefer props on players whose role is stable tonight; decline props on players whose minutes depend on a
game-time decision unless a same-day source settles it.
