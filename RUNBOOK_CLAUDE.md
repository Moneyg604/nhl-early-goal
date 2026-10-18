# Daily update runbook (for the scheduled Claude session)

> **Legacy (NHL only).** This is the older flow that rebuilt a stand-alone claude.ai artifact of the NHL page. The
> GitHub Pages site does not use it: the NHL slate is built by `.github/workflows/update-slate.yml`. Older scheduled
> tasks in the owner's Claude chat may still follow it, so its steps are kept exactly as they were. The NFL research
> desk follows `RUNBOOK_NFL_RESEARCH.md`; the NBA desk follows `RUNBOOK_NBA_RESEARCH.md`. See `START_HERE.md`.

This is what the scheduled task does, step by step, so a human can follow or audit it.

1. Fetch `code/nhl-early-goal.zip` and `days.json` from the published artifact, unzip, `pip install -r requirements.txt`.
2. Today's date in America/Toronto.
3. Fetch the NHL schedule for the date (api-web.nhle.com/v1/schedule/<date>) as a JSON list of {id, away, home, startTimeUTC}; validate with `tools/make_slate.py`.
4. Fetch DailyFaceoff starting goalies as a JSON list of {team, goalie, status}; write with `tools/make_overrides.py`. If unavailable, the usage heuristic projects the starters.
5. Track record: fetch `scorecard.json` and the previous day's page from the artifact, run `python -m earlygoal scorecard --date <date> --source sdv --pages <pages> --scorecard <scorecard.json>` so finished games are scored on the numbers that were published.
6. `python -m earlygoal run --date <date> --source sdv --slate-file data/slate-<date>.json --extra-schedule data/slate-<yesterday>.json --no-dfo`
7. `python -m earlygoal publish --artifact --prior-days prior-days.json`
8. Republish the artifact: page = docs/index.artifact.html, files = days/<date>.html, days.json and scorecard.json (earlier days and the code stay published).

Validators reject unknown team codes, non-regular-season game ids and bad timestamps, so a malformed fetch cannot produce a slate.
