# Start here: how Gill Sports fits together

One repository (`Moneyg604/nhl-early-goal`) runs everything: the NHL desk, the NFL and NBA desks, the research desk
that Claude runs on a schedule, the Telegram messages, and the phone app. GitHub Pages publishes the `docs/` folder.

## The pages

| Page | Address | What it is |
|---|---|---|
| **The phone app (use this)** | `https://moneyg604.github.io/nhl-early-goal/app/` | The research desk's picks, the board, the desk's logic, the record. NFL and NBA. Add it to your home screen. |
| NFL | `…/nhl-early-goal/nfl/` | The full NFL page: every game and market, the scanner, research, results. |
| NBA | `…/nhl-early-goal/nba/` | The full NBA page. |
| NHL | `…/nhl-early-goal/` | The original NHL early-goal desk. |
| NHL props | `…/nhl-early-goal/props/` | NHL player props. |

It is one app. Every page has the same look (navy, gold, the same fonts and cards), the same header, its own sections as
one row of chips under the header, and the same navigation bar: **Desk · NFL · NBA · NHL · Props** at the bottom on a
phone, down the left side on a wide screen. Add it to your home screen from any page: it opens on the Desk, and moving
between sections stays inside the app.

## What runs where

| Who | When | What it does |
|---|---|---|
| **GitHub Actions** (automatic) | NFL daily about 9:20am ET and about 75 minutes before each kickoff window; NBA 10:45am and 4:40pm ET; NHL three times a day; live scores every 5 minutes in the evening | Downloads data, runs the simulations, prices DraftKings markets, rebuilds the site, sends Telegram. Files: `.github/workflows/`. |
| **Your Claude chat** (scheduled tasks) | Thursday 11:33am, Saturday 5:38pm, Sunday 8:41am, Monday 2:37pm ET | The NFL research desk. Each run follows `RUNBOOK_NFL_RESEARCH.md`: researches every game on the web, writes `data/nfl/research/<week>.json`, checks it with `tools/validate_desk.py`, commits it, and starts the NFL rebuild with reason `research`. |
| **You** | Whenever you like | Read the app. Change the desk's rules from the app's Logic tab (it writes the message to send to Claude). |

## The folders

| Folder or file | What is in it | Who edits it |
|---|---|---|
| `docs/app/` | The phone app (one page, plus its install manifest) | Hand-written. Upload it when it changes. |
| `docs/nfl/`, `docs/nba/`, `docs/props/`, `docs/` | The published site | **The GitHub bot.** It rebuilds these every few minutes; never upload them by hand. |
| `data/nfl/desk_config.json` | **The NFL desk's rules (the spec)**: sections, Best picks, markets, odds rule, your plain-English instructions | You (through Claude). |
| `data/nfl/research/` | The desk's write-ups, one file per week | **The scheduled desk runs.** Never upload by hand. |
| `data/nba/desk_config.json`, `data/nba/research/` | The same for the NBA desk | You / the desk runs |
| `nfl/` | NFL engine: data, simulation, odds, the bot's checks (`brain.py`), the research desk merge (`desk.py`), the page (`report.py`), the app feed (`appfeed.py`) | Code |
| `nba/` | NBA engine, same layout | Code |
| `earlygoal/` | NHL engine (the original project; also the shared header in `brand.py`) | Code |
| `nhlprops/` | NHL player props | Code |
| `tools/` | `validate_desk.py` and `assemble_desk.py` (used by the desk runs), the Telegram senders, the scheduler (`keeper.py`) | Code |
| `RUNBOOK_NFL_RESEARCH.md` | **What the scheduled NFL desk does, step by step** | Code (the desk reads it every run) |
| `RUNBOOK_NBA_RESEARCH.md` | The NBA differences | Code |
| `RUNBOOK_CLAUDE.md` | Legacy: the older NHL-only artifact flow (kept unchanged for any old task that still uses it) | Leave it |
| `tests/` | Automated checks (`pytest`) | Code |

## Your friend's rules (the live NFL spec)

- Picks are chosen on evidence. The DraftKings price is shown but never used to choose.
- DraftKings' actual posted lines only. No alternate lines. No over/under on passing touchdowns (also off: half totals, kicker field goals).
- Four sections, 1 to 6 picks each: QB props (passing yards); Receiving yards and receptions; Rushing yards; Moneyline, spreads, totals.
- Best picks: 3 to 6, the strongest evidence of winning, one per player, at most two from the same game.
- Plus the plain-English instructions list. The scheduled desk must follow all of it, and `tools/validate_desk.py` refuses a file that does not.

The site's model ("Bot's picks" on the NFL page and below the desk in Telegram) is a separate layer and does not follow
this spec: its lists still include passing-TD unders and kicker field goals, and its combined top six still uses your
original 1.35 to 2.20 rule.

## What was fixed in this update (October 17, 2026)

**The desk could disappear.** The site re-checked the desk file on every rebuild against fresh odds. Any DraftKings
move after the desk ran, or any game kicking off, made the whole desk vanish from the app, the page and Telegram. Its
record for the week was lost too. Now the full check runs once, before the desk commits. After that, a line move shows
as a red alert on the pick and the desk stays.

**Your friend's rules were not enforced.** The checker accepted passing-TD picks, alternate lines, prices nobody
confirmed on DraftKings, and sections over their maximum. Week 6 had three passing-TD picks, including the two at the
top of the list. One unconfirmed price was also a Best pick. Now the checker refuses all of these before a commit, and
the site sets aside anything already committed that the spec does not allow, including a price never confirmed on
DraftKings. You'll see these in "Set aside by the spec". On the live week 6 file that leaves 15 picks, all on
confirmed DraftKings lines.

**A spec change could rewrite the record.** Changing a rule mid-week could remove picks that had already been played,
or promote a played pick into the Best picks. Now a pick's state at kickoff is final. Shown and graded stays shown and
graded; set aside stays set aside.

**The site would have stopped at week 6.** It moved to the next week only after every game's result had landed on the
page, which never happens for Monday night. It now moves on six hours after the last kickoff. NBA had the same problem
and is fixed the same way.

**Thursday desk runs could never pass.** Best picks need 3 or more, at most two per game, and Thursday has one game. A
short list is now a note, not an error.

**The fragment tool broke Saturday-after-Thursday and Monday runs.** It is rewritten:

- It keeps every started game's picks and their places in the lists.
- It skips fragments for games that have started.
- It keeps earlier picks for games a run didn't re-research.
- It moves an earlier pick to "declined", with the reason, when the spec no longer allows it, its price was never
  confirmed, or DraftKings has moved since. Tonight's run would otherwise have failed on last run's Monday-night
  passing-TD pick.
- It writes nothing unless the result passes the full check.

**Wrong grading.** Every NBA desk spread pick was graded on the wrong side of the number.

**Telegram** now leads with the Best picks, then each section, and says when the price was not used to choose. It no
longer lists banned markets in the desk block. It also failed to load on Python 3.11; that is fixed.

**The NFL page:**

- The desk tab's Game notes now show; they never did before.
- Settings saved on your phone before the spec changed no longer hide picks.
- A rejected desk file now shows its errors instead of "no desk yet".
- Header links on archive pages pointed at missing pages; they are fixed.

**The NBA page crashed on load.** Its Players, Results and About tabs stayed blank, and live scores never updated. This
was already broken in the downloaded copy; it is fixed now.

**One app, one look, one navigation.** The NHL, Props, NFL and NBA pages were drawn in an older near-black style
with a cramped row of section links that ran off a phone screen, while the app had its own design and its own bar.
Now every page uses the app's design and the same bottom bar (Desk, NFL, NBA, NHL, Props), and each page's own
sections sit in the same chip row. The theme lives in one place (`earlygoal/brand.py`), so the bot builds every page
in it from now on. Installing to the home screen opens the Desk and keeps every section inside the app (before, it
opened the NHL page, and the app's own install left the app when you tapped a sport). On the way, three
older bugs were fixed: the NBA page always showed a leftover summary table at the top, the NHL props skater table
squeezed its columns together on a phone, and props archive pages linked to validation files that do not exist.

**The Desk app is rebuilt.** It keeps the same look: navy and gold, the ticket cards, the win-chance ring and the bottom nav.
What's new:

- **Speed:** it loads a trimmed feed (about 0.5 MB instead of 2.3 MB) and shows the last data instantly while it refreshes.
- **Picks:** a summary row (next kickoff, this week's record, the season, line alerts), a game filter, and Best picks
  ranked #1 to #6.
- **Cards:** desk, market and model bars on each card; results and live progress on started picks (for example
  "Jones 142 passing yards so far").
- **Slip:** combines picks with their DraftKings odds and warns when two legs share a game.
- **Board:** shows your spec's markets by default, with search and a game filter.
- **Logic:** shows the next scheduled desk run and writes the message for Claude.
- **Record:** includes a running units chart.
- **Install:** it now installs as its own app; before, the home-screen icon opened the NHL page.

**The runbook the scheduled desk follows is rewritten.** It used to contradict the spec in places: it allowed
alternate lines, asked for 6 to 12 picks, and used price-based grades. It now says the spec wins. It also explains how
to source DraftKings lines for props, how to keep started picks, how to check the rebuild worked, and how to apply your
rule changes (section 6).

## How to upload this update to GitHub

Upload only the files in the update bundle: `gill-sports-upload.zip` in Downloads, or the `upload-to-github` folder
of `gill-sports-handover.zip` (the same files). They are the 34 files this update changed or added, in their folders:

```
.github/workflows/update-nfl.yml      .github/workflows/update-nba.yml      .github/workflows/nfl-revalidate.yml
README.md   START_HERE.md   SETUP.md   RUNBOOK_NFL_RESEARCH.md   RUNBOOK_NBA_RESEARCH.md   RUNBOOK_CLAUDE.md
data/nfl/desk_config.json             data/nba/desk_config.json
docs/app/index.html                   docs/manifest.webmanifest
earlygoal/brand.py   earlygoal/report.py   earlygoal/site.py
nba/desk.py   nba/report.py   nba/scorecard.py   nba/site.py
nfl/appfeed.py   nfl/desk.py   nfl/odds.py   nfl/pipeline.py   nfl/report.py   nfl/site.py
nhlprops/report.py   nhlprops/site.py
tests/test_desk.py   tests/test_nfl.py
tools/assemble_desk.py   tools/notify_nba.py   tools/notify_nfl.py   tools/validate_desk.py
```

On github.com: open the repository, **Add file → Upload files**, drag in the *contents* of the unzipped folder (the
`.github`, `data`, `docs`, `earlygoal`, `nba`, `nfl`, `nhlprops`, `tests`, `tools` folders and the `.md` files). Finder
hides `.github`: press Cmd+Shift+. to show it. GitHub keeps the folder paths and replaces the old files. Check that it
lists 34 files, including the three workflow files, then commit to `main`.

Do **not** upload anything else from the downloaded copy:

- **`docs/`** (except `docs/app/index.html` and `docs/manifest.webmanifest`, which are in the bundle): the bot rebuilds
  it constantly, so an old copy would overwrite newer results. The new look reaches the NFL, NBA, NHL and Props pages
  at their next automatic rebuild (or run Actions → Update NFL / Update NBA / Update slate once).
- **`data/nfl/research/`**: tonight's desk run may already have written a newer week-6 file.
- **The spec files:** if you changed `data/nfl/desk_config.json` since this download, keep your version. This update
  only added the run schedule at the end of it and a new `updated_utc`.

After the upload, the next NFL rebuild picks everything up. That happens at the next desk run, the next pre-kickoff
build, or the daily build. To see it at once, go to Actions → Update NFL → Run workflow (reason `update`).

## A message to paste into your Claude desk chat

Paste this so the chat that owns the scheduled tasks knows what changed:

> The Gill Sports repository was updated (see START_HERE.md and RUNBOOK_NFL_RESEARCH.md). For every scheduled NFL
> desk run from now on: follow RUNBOOK_NFL_RESEARCH.md and data/nfl/desk_config.json exactly, and treat the spec as
> overriding any older wording in the task prompts (no 1.35–2.20 price filter, no alternate lines, no passing
> touchdowns, DraftKings' posted lines only, an unconfirmed price goes to declined). The week file is
> data/nfl/research/<s>-wNN.json, where <s>-wNN is exactly `current` in docs/nfl/weeks.json. Build it with
> tools/assemble_desk.py --keep data/nfl/research/<s>-wNN.json (if it says the file "does not exist yet" on any run but
> the week's first, stop and report), run `git pull --rebase --autostash origin main` and
> `tools/validate_desk.py data/nfl/research/<s>-wNN.json`, fix everything it lists, commit and push only that file, run
> `gh workflow run update-nfl.yml -f reason=research`, and once that run has completed confirm that bot.desk.ok is true
> and bot.desk.generated equals your file's generated_utc in the rebuilt docs/nfl/weeks/<s>-wNN.json. Please update the
> four scheduled task prompts to say this, and keep their times.
