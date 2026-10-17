# NFL research desk runbook (the scheduled Claude session)

This is the protocol the research desk follows every time it runs. It is written so a person can audit it. The
desk's output is one file, `data/nfl/research/<season>-wNN.json`, which the site build merges into the NFL page
(the "Research desk" tab in Best bets) and into the Telegram message. The simulation's numbers are never edited;
the desk's probability is shown beside them, labelled as the desk's, and graded on its own line in Results.

The standard is a professional handicapper's write-up: every selection ships with its inputs, its arithmetic, its
risks and its sources, and nothing is estimated without data behind it.

## 0. Ground rules (standing, never need repeating)

1. No probability without inputs. A number comes from a measured rate and a volume estimate, or it is labelled
   `partial` (one leg of the arithmetic is an estimate) or `unmeasured` (no arithmetic possible; grade C at best).
2. Current-season measured rates override reputation. Last season is a prior, weighted about a third of this season.
3. Show the arithmetic on every selection: volume × rate = mean, the spread of outcomes, and P(side) from it.
4. Do not anchor on DraftKings' price or on the site's number. Derive the desk's probability first, then compare.
   When the desk is more than 8 points from the no-vig market, that is a re-check trigger: find the reason (news
   the market has not priced, weather, a role change) and name it in `inputs`, or move toward the market.
5. Qualitative reads run optimistic. Discount them: a narrative ("revenge game", "must win") is never an input.
6. Verify the starters independently (official injury report plus a beat-writer or team source dated today), never
   from a cached preview. Out and Doubtful players are not candidates. Questionable players are candidates only
   when a same-day source says they are expected to play, and the risk is named.
7. Park and weather go into the arithmetic (volume and efficiency), not into a footnote.
8. Fewer, better selections. Six to twelve across a Sunday slate; two or three for a single-game window. A slate with
   nothing that clears the bar gets an empty `selections` list and a `summary` saying why.
9. DraftKings only. Prices inside the configured band (default 1.35 to 2.20 decimal). The odds feed's DraftKings
   price is `odds_source: "feed"` and must match the feed exactly (the validator compares the line and the price
   with the payload's DraftKings entry: a feed-sourced selection on a different line is rejected); a price read
   today from a page that shows DraftKings' own board is `"draftkings"`; anything else is `"unverified"` and must
   say so. Never list a price you could not see somewhere. When the feed's line is stale and DraftKings has moved,
   re-do the arithmetic at the current line and use `"draftkings"` with the source named.
10. No anytime-touchdown selections (the page has its own TD board). Alternate lines are allowed when a DraftKings
    alt price is found and the arithmetic supports it.
11. Measure the desk honestly: the scorecard grades every selection at the price listed. Do not remove or edit a
    selection after its game has kicked off; a later run may add selections for games still to come and may drop a
    not-yet-started selection when the news changed (say so in `declined`).

## 0b. The desk settings file

`data/nfl/desk_config.json` is the owner's configuration and the desk follows it on every run: `odds_band` (the
price band for selections), `wild_cards` (whether to add a short list of longer-priced plays, their band, how many,
and the probability floor), `markets` (which markets are candidates at all), `selection` (minimum grade and
evidence, minimum desk probability, at most how many per game and in total, one selection per player per market),
`variables` (which research items to run; an item switched off is skipped and the write-up says so) and `alerts`.
Read it first; if the file is missing or broken, the defaults in `nfl/desk.py` apply. The page's "Desk settings"
panel shows the same values and lets the owner filter the view on his own phone; changes he wants the desk itself
to follow go into this file.

Wild cards: when `wild_cards.enabled`, add up to `max` plays priced inside `wild_cards.odds_band` (longer than the
main band: alternate lines, underdog moneylines, player-prop alternates) that the research supports, each with the
same write-up and a desk probability of at least `min_p`. They go in a separate `wild_cards` list in the overlay,
are shown on their own lane, and are graded on their own scorecard line. They are never mixed into `selections`.

## 1. Set-up (mechanical)

1. Make sure the repository is attached and cloned: `Moneyg604/nhl-early-goal` (add it with the repo tool if it is not
   in the session; then `git clone --depth 1 https://github.com/Moneyg604/nhl-early-goal`). Work in the clone.
2. `pip install -r requirements.txt` (only numpy, pandas, pyarrow, requests are needed; skip if already present).
3. Today's date and time in America/Toronto. Read `docs/nfl/weeks.json` for the current week name, then
   `docs/nfl/weeks/<name>.json` (the published payload; also at
   `https://raw.githubusercontent.com/Moneyg604/nhl-early-goal/main/docs/nfl/weeks/<name>.json`).
4. From the payload, build the candidate list for the games that kick off in the window this run covers:
   - every bet in `best_bets.ranked` and `bot.extra` whose `kick` is in the future, with a DraftKings `odds` in the
     band, plus the `bot.cats` picks, `bot.combine.legs`, `bot.leans` and `bot.extra` alternate lines and projected
     props (these have no feed price; they need a DraftKings price from the web before they can be selected);
   - each game's `research`, `qb`, `injuries`, `weather`, `rest`, `lines` blocks: the structured inputs the
     simulation already measured. Use them; do not re-derive EPA from scratch.
   - the existing overlay for this week, if any (`data/nfl/research/<name>.json`): keep the selections whose games
     have started exactly as they are.
5. Which games this run covers: Thursday run = Thursday night; Saturday evening run = all Sunday games;
   Sunday morning run = all Sunday games again (final news) plus Monday night; Monday run = Monday night. Games
   that already kicked off are never re-researched.

## 2. Research (per game, in parallel subagents when available, one scratch JSON fragment per game)

Search the web (one to six words per query; add the date for anything time-sensitive) and read the pages. For each
game, record with its URL and the time you fetched it:

- Availability: the official report (Out, Doubtful, Questionable, with practice participation), plus the latest
  beat-writer or team note on Questionable starters and on the quarterback, the top two running backs, the top
  three receivers, the starting tight end, the kicker, offensive-line starters and the top pass rushers and
  cornerbacks. Note any rookie or backup quarterback starting.
- Weather at kickoff for outdoor and open-roof stadiums: temperature, wind speed and gusts, precipitation chance.
  Wind of 15 mph or more cuts passing volume and efficiency and field-goal range; rain raises fumbles and lowers deep
  throws; a dome means no effect. Note the roof state for retractable stadiums.
- Matchup: opponent pass defense and run defense by EPA per play and success rate (ranks are in the payload under
  `research.<side>.adv.rank_def`), pressure rate against the offense's sack rate allowed, the cornerback expected to
  cover the receiver in question (shadow assignments, slot vs wide), coverage against tight ends, run-stop rate.
- Usage and form (last four games, this season): the quarterback's dropbacks, yards per attempt, air yards;
  each receiver's routes, targets, target share, air-yard share, yards per route run, catch rate; each back's
  carries, carry share, yards per carry, red-zone touches, snap share and the trend. The payload has usage
  shares and recent games under `anytime` and `props`; the web adds routes run and air yards.
- Game script: the current spread and total, pace (seconds per play, neutral pass rate, pass rate over expected
  from the payload), expected plays, who is likely to lead and what that does to passing and rushing volume.
- Line movement: the opening number and the current number for the spread and total, which way it moved, and
  whether the move came with news (an injury) or without (sharp money). Reverse line movement is a note, not a
  reason on its own.
- Situational: rest days (in the payload), travel across time zones, short week, the kicker's recent makes and
  longest make, new coordinator or play-caller, a team eliminated or resting starters (late season).

Write what was found, not what was expected. If a source could not be found for an item, say "unmeasured" for
that item.

## 3. Arithmetic (per candidate; use the formula for its market)

Every selection's `arithmetic` list shows these steps with the numbers filled in. Means come from volume × rate.
Spreads of outcomes use measured game-to-game variation; the defaults below are league-typical and may be
replaced by a measured figure when one is found.

- Passing yards: dropbacks (team plays × pass rate, moved by the game script) × yards per dropback (QB's own this
  season, blended with the opponent's allowed, both relative to the league) = mean. SD about 70 yards (or 0.28 ×
  mean). P(over L) = Φ((mean − L) / SD).
- Passing touchdowns: expected team passing TDs (drives × TD rate × pass-TD share) → Poisson; P(under 1.5) =
  P(0) + P(1).
- Receiving yards: targets (routes run × target rate, or team attempts × target share) × yards per target (player's
  own vs the opponent's allowed per target) = mean. Right-skewed: SD about 0.6 × mean; P(over L) ≈ Φ((mean − L) /
  SD) with a note that the distribution is skewed (a lognormal with the same mean and SD is better when it matters).
- Receptions: targets × catch rate = mean; Poisson or normal with SD ≈ √mean × 1.1.
- Rushing yards: carries (carry share × team rushes, moved by the script: leading teams run more) × yards per
  carry (player's own, adjusted by the opponent's YPC allowed vs league) = mean; SD about 0.5 × mean.
- Kicker field goals: expected tries (drives × field-goal-try rate, from the payload's `research.<side>.offense.fg_rate`
  and the opponent's allowed) × make probability for the kicker and weather = expected makes; Poisson for P(k or more).
- Moneyline and spread: expected margin from the two teams' EPA-based ratings (the payload's `model.margin` is the
  simulation's; the desk's figure adjusts for news the simulation did not see, with the adjustment written down:
  for example "backup QB: −4.5 points, measured effect of new starters"). Home field about +1.5 to +2.5 points.
  Margin SD 13.5. P(cover) = Φ((margin − line) / 13.5); P(win) = Φ(margin / 13.5).
- Totals: expected points from pace × points per drive for both offenses against the opposing defenses (the payload
  shows the possessions and points-per-drive arithmetic on each total card); weather and injuries move the figure.
  Total SD 13.5. P(over L) = Φ((mean − L) / 13.5). Halves: the league first-half share (about 48 to 50%) of the
  total, SD 9.

Then the market comparison: the no-vig market probability (payload `p_market`), the simulation's (`p_model`), the
desk's, and the difference in points. Fair odds = 1 / p. EV at DraftKings' price = p × odds − 1.

## 4. Grade, evidence and the selection

- `evidence`: `measured` when every leg of the arithmetic has a this-season number from a source; `partial` when one
  leg is an estimate; `unmeasured` when the arithmetic could not be done (then grade C and the write-up says what
  is missing).
- `grade`: A = measured, desk probability at least 5 points above the break-even for the price, no open injury or
  weather risk; B = measured or partial, at or above break-even with a named risk; C = thin or unmeasured, or the
  price is poor but the side is right. A is never given on unmeasured evidence.
- `confidence` 0 to 100: how solid the inputs are (sources, sample size, freshness), not how likely the bet is to win.
- `p`: the desk's probability, written to two decimals, between 0.50 and 0.80 for a selection (a probability above
  0.80 at a price in the band means the price is wrong somewhere; re-check).
- `inputs`: the facts used, each with its figure ("Henry 19.3 carries per game last 4, 71% carry share").
- `pros` and `risks`: the case for and the concrete ways it fails (a late scratch, a blowout script, wind).
- `verdict`: one or two sentences a bettor can act on.
- `sources`: every page used, with name, URL and the fetch time (ISO, UTC: `2026-10-18T13:05Z`).
- `declined`: candidates examined and not taken, with the reason (one line each). This is where the site's own
  picks go when the desk disagrees with them.

Rank by `p`. Do not force a count. Across a Sunday slate prefer different games for the top selections.

## 5. File, validate, commit, rebuild

1. Write `data/nfl/research/<season>-wNN.json` in the schema at the top of `nfl/desk.py` (`generated_utc` as
   `YYYY-MM-DD HH:MM UTC`, `analyst` "Claude research desk", `odds_band` [1.35, 2.2]). Keep the selections of
   games that already started from the previous overlay unchanged (same ids, same fields). When the research was
   done per game (one fragment file per game: `{"game_id", "notes", "selections", "declined"}` in a scratch
   directory), assemble and validate in one step:
   `python tools/assemble_desk.py --season <s> --week <w> --frags <dir> --keep data/nfl/research/<s>-wNN.json --summary "<two sentences on the slate>"`
2. `python tools/validate_desk.py data/nfl/research/<season>-wNN.json` and fix every problem it lists. It also
   prints the ranked list the page will show.
3. Commit and push only that file (the config file is the owner's; never edit it from a run):
   `git add data/nfl/research/<season>-wNN.json && git commit -m "desk: week N research <date> <run>" && git pull --rebase origin main && git push origin main`
   (retry the pull/push a few times if the site's bot pushed in between).
4. Rebuild the site so the page and the Telegram message carry the desk:
   `gh workflow run update-nfl.yml --ref main -R Moneyg604/nhl-early-goal -f reason=research`
   The run takes a few minutes; `gh run list -R Moneyg604/nhl-early-goal -w update-nfl.yml -L 1` shows it.
5. Finish with a short note: how many selections, the top three with price and desk chance, and anything that
   needs the owner's attention (a missing price, a game with no usable news). Nothing else.
