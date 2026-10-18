# NFL research desk runbook (the scheduled Claude session)

This is the protocol the research desk follows every time it runs. It is written so a person can audit it. The
desk's output is one file, `data/nfl/research/<season>-wNN.json`, which the site build merges into the phone app
(`docs/app/`, the Picks tab), the NFL page (the "Research desk" tab in Best bets) and the Telegram message. The
simulation's numbers are never edited; the desk's probability is shown beside them, labelled as the desk's, and
graded on its own lines in Results ("Desk best picks" and "Research desk").

The standard is a professional handicapper's write-up: every selection ships with its inputs, its arithmetic, its
risks and its sources, and nothing is estimated without data behind it.

## 0. Ground rules (standing, never need repeating)

1. No probability without inputs. A number comes from a measured rate and a volume estimate, or it is labelled
   `partial` (one leg of the arithmetic is an estimate) or `unmeasured` (no arithmetic possible; grade C at best).
2. Current-season measured rates override reputation. Last season is a prior, weighted about a third of this season.
3. Show the arithmetic on every selection: volume × rate = mean, the spread of outcomes, and P(side) from it.
4. Do not anchor on DraftKings' price or on the site's number. Derive the desk's probability first, then compare.
   When the desk is more than 8 points from the no-vig market, that is a re-check trigger: re-check every input,
   find the reason (news the market has not priced, weather, a role change) and name it in `inputs`. If no reason
   survives the re-check, lower the confidence and say so; never move the number just because the market disagrees.
5. Qualitative reads run optimistic. Discount them: a narrative ("revenge game", "must win") is never an input.
6. Verify the starters independently (official injury report plus a beat-writer or team source dated today), never
   from a cached preview. Out and Doubtful players are not candidates. Questionable players are candidates only
   when a same-day source says they are expected to play, and the risk is named.
7. Park and weather go into the arithmetic (volume and efficiency), not into a footnote.
8. The honest scorecard: every selection is graded at the price listed. Do not remove or edit a selection after its
   game has kicked off. A later run may add selections for games still to come, and may drop a not-yet-started
   selection when the news changed (say so in `declined`).

## 0b. The owner's spec (`data/nfl/desk_config.json`): read it first, every run

The spec is the owner's. Its keys and its `instructions` override every default in this runbook. Only ground rules
1, 3, 6 and 8 above (inputs, arithmetic, verified starters, the honest scorecard) and the honest labelling of
evidence, sources and prices can never be overridden. If the file is missing or does not parse
(`tools/validate_desk.py` and `tools/assemble_desk.py` refuse to run on a broken spec), stop and tell the owner;
do not run on defaults. A run never edits the spec (section 6 is how the owner's changes are made).

What the current spec says (the file is the authority; this is a reading aid):

- `odds_rule: "ignore"`: evidence chooses every selection. The DraftKings price is reported, never used as a filter
  or a reason. A pick at 1.25 or 3.10 is fine when the research supports it; the write-up says what the price
  implies (break-even, EV at the desk's chance). Under `"band"` only prices inside `odds_band` would be eligible.
- `lines: "draftkings"`: DraftKings' actual posted line only. No alternate lines. A selection's line and price are
  either DraftKings' line in the odds feed (`odds_source: "feed"`) or DraftKings' line read today from a page that
  shows DraftKings' own board, with the URL in `sources` (`"draftkings"`). A line or price you could not confirm on
  DraftKings is not a selection: put it in `declined` with the reason. (`"unverified"` exists only for older files.)
- `markets`: the markets that may be selected at all. Off now: passing touchdowns (`qb_td`), half totals (`h1`,
  `h2`), kicker field goals (`fg`), alternate lines (`alts`); anytime touchdowns are never a desk market (the page
  has its own TD board). A market that is not in the list is off.
- `sections`: the lists the owner sees, in order: QB props (passing yards), Receiving yards and receptions, Rushing
  yards, Moneyline / spreads / totals. Each has a `min` and `max` (1 and 6). Fill a section only with selections the
  research supports, never past its `max`. A section the research cannot fill honestly stays short: name the gap
  in `summary` (and the candidates you rejected in `declined`); never pad it with a pick below `selection.min_evidence`.
- `best`: the Best picks, 3 to 6, the main list the owner acts on: the selections with the strongest evidence of
  actually winning, drawn from the sections, one per player, at most two from the same game, strongest first. A
  Best pick needs a confirmed DraftKings line. On a one- or two-game window (Thursday, Monday) fewer than 3 is
  fine; say so in `summary`.
- `selection`: `min_p` 0.50, `min_evidence` partial, `min_grade` C, at most `max_per_game` 3 per game and
  `max_selections` 24 in total, one selection per player per market.
- `wild_cards.enabled: false`: no wild cards.
- `variables`: the research items to run (section 2 maps each one). An item switched off is skipped and the write-up says so.
- `instructions`: the owner's rules in plain English. They are mandatory.

`tools/validate_desk.py` enforces all of the above before a commit (see section 5).

## 1. Set-up (mechanical)

1. Make sure the repository is attached and cloned: `Moneyg604/nhl-early-goal` (add it with the repo tool if it is not
   in the session; then `git clone --depth 1 https://github.com/Moneyg604/nhl-early-goal`). Work in the clone. If a
   clone from an earlier run is there, `git pull --rebase --autostash origin main` first.
2. `pip install -r requirements.txt` (only numpy, pandas, pyarrow, requests are needed; skip if already present).
3. Today's date and time in America/Toronto. Read `docs/nfl/weeks.json` for the current week name (`current`), then
   `docs/nfl/weeks/<name>.json` (the published payload; also at
   `https://raw.githubusercontent.com/Moneyg604/nhl-early-goal/main/docs/nfl/weeks/<name>.json`).
4. From the payload, build the candidate list for the games this run covers:
   - first drop everything the spec does not allow: a kind whose `markets` value is not true, every anytime-TD
     (`atd`) entry, every alternate line (`alt|…` ids);
   - every bet in `best_bets.ranked` whose `kick` is in the future, plus the `bot.cats` picks, `bot.combine.legs`,
     `bot.leans` and the projected props in `bot.extra` (`proj|…` ids: the simulation's own line, no DraftKings
     price). A projected prop becomes a candidate only on DraftKings' posted line, found on the web, and is re-keyed
     `desk|<kind>|<game_id>|<side>|<DraftKings line>|<player>`;
   - each game's `research`, `qb`, `injuries`, `weather`, `rest`, `lines` blocks: the structured inputs the
     simulation already measured. Use them; do not re-derive EPA from scratch;
   - the existing overlay for this week, if any (`data/nfl/research/<name>.json`): keep the selections whose games
     have started exactly as they are (`--keep` does this).
   The odds feed prices player props only about 75 minutes before each kickoff window, so for receiving, rushing and
   most passing props on the Saturday and Sunday-morning runs the DraftKings line must come from the web (the
   DraftKings Sportsbook page for the game, or an odds page that labels DraftKings' column), with the URL and the
   fetch time in `sources`.
5. Which games this run covers: Thursday run = Thursday's games (and Friday's, when there are any); Saturday evening
   run = any Saturday game still to come and all Sunday games; Sunday morning run = all Sunday games again (final
   news) plus Monday night; Monday run = Monday night. Games that already kicked off are never re-researched; their
   picks stay exactly as published.

## 2. Research (per game, in parallel subagents when available, one fragment per game)

Search the web (one to six words per query; add the date for anything time-sensitive) and read the pages. For each
game, record what you found with its URL and the time you fetched it. The spec's `variables` keys are in brackets.

- Availability [availability]: the official report (Out, Doubtful, Questionable, with practice participation), plus
  the latest beat-writer or team note on Questionable starters and on the quarterback, the top two running backs,
  the top three receivers, the starting tight end, offensive-line starters and the top pass rushers and
  cornerbacks. Note any rookie or backup quarterback starting.
- Weather [weather]: at kickoff for outdoor and open-roof stadiums: temperature, wind speed and gusts,
  precipitation chance. Wind of 15 mph or more cuts passing volume and efficiency; rain raises fumbles and lowers
  deep throws; a dome means no effect. Note the roof state for retractable stadiums.
- Stadium [stadium]: altitude (Denver), surface (turf or grass), dome or open air, travel and time zone for the visitor.
- Matchup [matchup]: opponent pass defense and run defense by EPA per play and success rate (ranks are in the
  payload under `research.<side>.adv.rank_def`), pressure rate against the offense's sack rate allowed, run-stop
  rate, coverage against tight ends, the defense's weak points.
- Man-to-man [cornerbacks]: the cornerback expected to cover the receiver in question (shadow assignments, slot vs wide).
- Usage and form [usage_form], last four games, this season: the quarterback's dropbacks, yards per attempt, air
  yards; each receiver's routes, targets, target share, air-yard share, yards per route run, catch rate; each back's
  carries, carry share, yards per carry, red-zone touches, snap share and the trend. The payload has usage shares
  and recent games under `anytime` and `props`; the web adds routes run and air yards.
- Tendencies [tendencies]: pass rate over expected, pace (seconds per play), neutral pass rate, red-zone usage, how
  the offense attacks this defense.
- Game script [game_script]: the current spread and total, expected plays, who is likely to lead and what that does
  to passing and rushing volume.
- Line movement [line_movement]: the opening number and the current number for the spread and total, which way it
  moved, and whether the move came with news (an injury) or without (sharp money). Reverse line movement is a note,
  not a reason on its own.
- Situational [situational]: rest days (in the payload), short week, new coordinator or play-caller, a team
  eliminated or resting starters (late season).

Write what was found, not what was expected. If a source could not be found for an item, say "unmeasured" for that
item.

Each game's fragment is one JSON file in a scratch directory outside the clone (any name ending `.json`). A game's
fragment replaces that game's earlier picks: re-list (same id, updated fields) every earlier pick you keep, and put
every one you drop in `declined` with the reason. A game with no fragment this run keeps its earlier picks, except
those the current spec no longer allows or whose DraftKings feed price has moved (`assemble_desk.py --keep` moves
those to `declined` and says so).

```json
{"game_id": "2026_06_TEN_IND",
 "notes": {"notes": ["..."], "weather": "...", "injuries": ["..."], "sources": [{"name": "...", "url": "https://...", "fetched": "2026-10-18T13:05Z"}]},
 "selections": [ {selection objects, schema in nfl/desk.py} ],
 "declined": [{"id": "...", "label": "...", "why": "..."}]}
```

## 3. Arithmetic (per candidate; use the formula for its market)

Every selection's `arithmetic` list shows these steps with the numbers filled in. Means come from volume × rate.
Spreads of outcomes use measured game-to-game variation; the defaults below are league-typical and may be replaced
by a measured figure when one is found.

- Passing yards: dropbacks (team plays × pass rate, moved by the game script) × yards per dropback (QB's own this
  season, blended with the opponent's allowed, both relative to the league) = mean. SD about 70 yards (or 0.28 ×
  mean). P(over L) = Φ((mean − L) / SD).
- Receiving yards: targets (routes run × target rate, or team attempts × target share) × yards per target (player's
  own vs the opponent's allowed per target) = mean. Right-skewed: SD about 0.6 × mean; P(over L) ≈ Φ((mean − L) /
  SD) with a note that the distribution is skewed (a lognormal with the same mean and SD is better when it matters).
- Receptions: targets × catch rate = mean; Poisson or normal with SD ≈ √mean × 1.1.
- Rushing yards: carries (carry share × team rushes, moved by the script: leading teams run more) × yards per
  carry (player's own, adjusted by the opponent's YPC allowed vs league) = mean; SD about 0.5 × mean.
- Moneyline and spread: the expected margin from the two teams' EPA-based ratings. The payload's `model.margin` is the
  simulation's home-team margin; the desk's figure adjusts for news the simulation did not see, with the adjustment
  written down (for example "backup QB: −4.5 points, measured effect of new starters"). Home field about +1.5 to
  +2.5 points. The selection's `line` is team-relative (−3.5 for a 3.5-point favourite, +3.5 for the underdog).
  team_margin = model margin for the home side, minus it for the away side. Margin SD 13.5.
  P(cover) = Φ((team_margin + line) / 13.5); P(win) = Φ(team_margin / 13.5).
- Totals: expected points from pace × points per drive for both offenses against the opposing defenses (the payload
  shows the possessions and points-per-drive arithmetic on each total card); weather and injuries move the figure.
  Total SD 13.5. P(over L) = Φ((mean − L) / 13.5).
- Passing touchdowns, half totals and kicker field goals are off in the spec; their formulas are not used.

Then the market comparison, as information: the no-vig market probability (payload `p_market`), the simulation's
(`p_model`), the desk's, and the difference in points. Fair odds = 1 / p. Break-even = 1 / DraftKings' price. EV at
DraftKings' price = p × odds − 1.

## 4. Grade, evidence and the selection

- `evidence`: `measured` when every leg of the arithmetic has a this-season number from a source; `partial` when one
  leg is an estimate; `unmeasured` when the arithmetic could not be done (then grade C and the write-up says what
  is missing). The spec's `min_evidence` is partial: an unmeasured candidate is not a selection.
- `grade` (the strength of the case, not the price): A = measured, no open injury or weather risk, the desk's
  probability at least 0.60; B = measured or partial with a named risk; C = thin evidence. A is never given on
  unmeasured evidence.
- `confidence` 0 to 100: how solid the inputs are (sources, sample size, freshness), not how likely the bet is to win.
- `p`: the desk's probability, two decimals, at least the spec's `min_p` (0.50). Under `odds_rule: "ignore"` there is
  no upper limit from the price (a 0.80 favourite is fine); under `"band"`, a probability above 0.80 at a price in
  the band means something is wrong: re-check.
- `inputs`: the facts used, each with its figure ("Henry 19.3 carries per game last 4, 71% carry share").
- `pros` and `risks`: the case for and the concrete ways it fails (a late scratch, a blowout script, wind).
- `verdict`: one or two sentences a bettor can act on.
- `sources`: every page used, with name, URL and the fetch time (ISO, UTC: `2026-10-18T13:05Z`).
- `declined`: candidates examined and not taken, with the reason (one line each). This is where the site's own picks
  go when the desk disagrees with them, and where a line you could not confirm on DraftKings goes.

Then the lists:

- Sections: for each spec section, its selections strongest first (desk probability, then confidence), never more
  than its `max`. One selection per player per market, at most `max_per_game` per game in total.
- Best picks: from the sections, the selections with the strongest evidence of actually winning, ranked by evidence
  (measured first), then the desk probability, then confidence; one per player, at most two per game, 3 to 6 of them.
  Best picks for games that have already kicked off keep their places (they are graded as published); a later run
  fills only the remaining places.
- Write them into the overlay as `"sections": {"<key>": [ids]}` and `"best": [ids]`, or let `assemble_desk.py` fill
  them by the same rule (pass `--best` to give the desk's own order).
- Prefer different games for the top Best picks across a Sunday slate.

## 5. File, validate, commit, rebuild

1. Write `data/nfl/research/<season>-wNN.json` in the schema at the top of `nfl/desk.py` (`generated_utc` as
   `YYYY-MM-DD HH:MM UTC`, `analyst` "Claude research desk", `odds_band` [1.35, 2.2] is kept for the file format).
   Keep the selections of games that already started from the previous overlay unchanged (same ids, same fields).
   When the research was done per game (one fragment per game, section 2), assemble and validate in one step:
   `python tools/assemble_desk.py --season <s> --week <w> --frags <dir> --keep data/nfl/research/<s>-wNN.json --summary "<two sentences on the slate>"`
   Optional: `--best <id,id,...>` (the desk's own Best-pick order), `--sections <file.json>` (the desk's own section
   lists), `--payload <file>` (a payload other than `docs/nfl/weeks/<s>-wNN.json`). `--keep` keeps every started game's
   picks and their places in the lists, and keeps a not-yet-started pick whose game got no fragment this run.
   Nothing is written unless the result passes the strict check; the problems are printed and the draft is left at
   `<dir>/_assembled_invalid.json`.
2. `git pull --rebase --autostash origin main` (the bot may have rebuilt the payload since the clone; `--autostash`
   keeps your new research file through the pull), then
   `python tools/validate_desk.py data/nfl/research/<season>-wNN.json` and fix every problem it lists (a market the
   spec switched off, an unconfirmed DraftKings line, a section over its maximum, a feed price that moved: re-price it
   at DraftKings' current line or decline it). It prints the Best picks, each section and the full list exactly as
   the app will show them, and notes such as a section short of its minimum.
3. Commit and push only that file (the spec is the owner's; never edit it from a run):
   `git add data/nfl/research/<season>-wNN.json && git commit -m "desk: week N research <date> <run>" && git pull --rebase --autostash origin main && git push origin main`
   (retry the pull/push a few times if the site's bot pushed in between).
4. Rebuild the site so the app, the page and the Telegram message carry the desk:
   `gh workflow run update-nfl.yml --ref main -R Moneyg604/nhl-early-goal -f reason=research`
   The run takes a few minutes; `gh run list -R Moneyg604/nhl-early-goal -w update-nfl.yml -L 1` shows it. When it
   has finished, check that `docs/nfl/weeks/<name>.json` on main has `bot.desk.ok` true (a false one lists its errors
   in `bot.desk.errors`; fix them and repeat from step 2).
5. Finish with a short note: the Best picks (label, DraftKings price, desk chance, grade), any section left short and
   why, and anything that needs the owner's attention (a line you could not confirm, a game with no usable news).
   Nothing else.

After a commit the site build re-checks only the file's structure. A pick that passed here keeps showing after
kickoff and after DraftKings moves (the move shows as a line alert on the pick). A pick still to play that a later
spec change no longer allows is set aside and listed as such, never shown as a pick; a pick whose game has kicked off
keeps the state it had at kickoff (shown and graded, or set aside), whatever the spec says later.

## 6. When the owner changes the spec (a message from the app's Logic tab, or a request in chat)

1. Edit only `data/nfl/desk_config.json`. Keep every key and the `v` number. Append new rules to `instructions`
   (plain English, one rule per entry); switch `markets` and `variables` exactly as asked; never loosen a rule the
   owner did not mention. A market switched on must also be listed in a section's `markets` (passing TDs to the QB
   section, half totals to the game section; for anything else ask the owner which section): a market that is in no
   section stays blocked. Set `updated_utc` to now.
2. `python -m json.tool data/nfl/desk_config.json > /dev/null` (the file must parse). Optionally run
   `python tools/validate_desk.py data/nfl/research/<current week>.json`: in a spec-change run, the problems it lists
   are the picks still to play that the new spec rejects. That is expected: do not edit the research file here; the
   site sets them aside at the next rebuild and the next desk run re-picks. Picks whose games have kicked off keep
   their published state either way.
3. `git add data/nfl/desk_config.json && git commit -m "spec: <what changed>" && git pull --rebase --autostash origin main && git push origin main`
4. `gh workflow run update-nfl.yml --ref main -R Moneyg604/nhl-early-goal -f reason=update` so the app shows the new
   spec. If a desk run is due within the day, or the owner asks, run the desk again for the current week (sections
   1 to 5) under the new spec.
