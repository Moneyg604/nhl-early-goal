"""Scheduler of last resort for the GitHub workflows.

GitHub's cron can take hours to start on a new repository and may be delayed at any time, and it
cannot fire at a time that depends on the day's schedule. This script runs inside the `keeper`
workflow: it sleeps until the next job is due (the fixed slate updates, a refresh two hours before
the first puck drop, and the live-score snapshots), dispatches it with `gh workflow run`, and hands
over to a fresh keeper run before the 6-hour job limit. Jobs that cron already started are skipped.

    python tools/keeper.py            # loop (needs GH_TOKEN with actions:write)
    python tools/keeper.py --status   # print the next due jobs and whether cron is healthy
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

SLATE_TIMES = ((14, 5, "morning"), (19, 5, "update"), (22, 35, "update"))   # UTC; same as update-slate.yml
LIVE_HOURS = {23, 0, 1, 2, 3, 4, 5, 6}               # live-scores.yml: every 5 minutes in these UTC hours
LIVE_STEP_MIN = 5
HANDOVER_AFTER = 5 * 3600 + 30 * 60                   # hand over well inside the 6-hour job limit
CRON_HEALTHY_WINDOW = timedelta(hours=9)             # longest natural gap between scheduled runs is ~7 h
REPO = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY") or ""


def gh(*args: str) -> str:
    cmd = ["gh", *args]
    if REPO and args and args[0] in ("run", "workflow"):
        cmd += ["--repo", REPO]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  gh {' '.join(args)} failed: {r.stderr.strip()[:300]}", flush=True)
        return ""
    return r.stdout


_T120_CACHE: dict[str, datetime | None] = {}


def t120_for(day: str) -> datetime | None:
    """Two hours before the earliest regular-season puck drop on `day` (UTC), from the NHL schedule; None if no games."""
    if day in _T120_CACHE:
        return _T120_CACHE[day]
    try:
        import json as _json
        import urllib.request

        req = urllib.request.Request(f"https://api-web.nhle.com/v1/schedule/{day}", headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = _json.load(r)
        starts = []
        for wk in data.get("gameWeek", []):
            if wk.get("date") != day:
                continue
            for g in wk.get("games", []):
                if g.get("gameType") == 2 and g.get("startTimeUTC"):
                    starts.append(datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00")))
        t = (min(starts) - timedelta(hours=2)).replace(second=0, microsecond=0) if starts else None
    except Exception as e:  # noqa: BLE001
        print(f"  schedule lookup failed for {day}: {e}", flush=True)
        t = None
    _T120_CACHE[day] = t
    return t


def next_event(now: datetime) -> tuple[datetime, str]:
    """The next due (time, workflow file)."""
    cands: list[tuple[datetime, str]] = []
    for h, m, reason in SLATE_TIMES:
        t = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
        cands.append((t, f"update-slate.yml:{reason}"))
    # monthly revalidation of the backtest, first of the month at 12:00 UTC
    first = now.replace(day=1, hour=12, minute=0, second=0, microsecond=0)
    if first <= now:
        first = (first + timedelta(days=32)).replace(day=1)
    cands.append((first, "revalidate.yml"))
    # a refresh two hours before the first puck drop, today or tomorrow (Eastern days roll at 04:00 UTC-ish; use the UTC date and the next one)
    for d in (now.date(), (now + timedelta(days=1)).date()):
        t = t120_for(d.isoformat())
        if t is not None and t > now:
            cands.append((t, "update-slate.yml:t120"))
    # next 5-minute tick that falls inside the live window
    t = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)
    t += timedelta(minutes=(-t.minute) % LIVE_STEP_MIN)
    for _ in range(24 * 60 // LIVE_STEP_MIN + 1):
        if t.hour in LIVE_HOURS:
            cands.append((t, "live-scores.yml"))
            break
        t += timedelta(minutes=LIVE_STEP_MIN)
    return min(cands)


def runs(workflow: str | None = None, event: str | None = None, limit: int = 5) -> list[dict]:
    args = ["run", "list", "--limit", str(limit), "--json", "createdAt,status,event,name,workflowName"]
    if workflow:
        args += ["--workflow", workflow]
    if event:
        args += ["--event", event]
    out = gh(*args)
    try:
        return json.loads(out) if out else []
    except json.JSONDecodeError:
        return []


def cron_healthy(now: datetime) -> bool:
    for r in runs(event="schedule", limit=3):
        try:
            if now - datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00")) < CRON_HEALTHY_WINDOW:
                return True
        except (KeyError, ValueError):
            pass
    return False


def started_recently(workflow: str, now: datetime, within_s: int = 150) -> bool:
    for r in runs(workflow=workflow, limit=3):
        try:
            if (now - datetime.fromisoformat(r["createdAt"].replace("Z", "+00:00"))).total_seconds() < within_s:
                return True
        except (KeyError, ValueError):
            pass
    return False


def keeper_alive() -> bool:
    return any(r.get("status") in ("in_progress", "queued", "waiting", "pending") for r in runs(workflow="keeper.yml", limit=5))


def dispatch(workflow: str, reason: str | None = None) -> None:
    print(f"{datetime.now(timezone.utc):%H:%M:%S} dispatch {workflow}{' (' + reason + ')' if reason else ''}", flush=True)
    args = ["workflow", "run", workflow, "--ref", "main"]
    if reason:
        args += ["-f", f"reason={reason}"]
    gh(*args)


def main() -> None:
    now = datetime.now(timezone.utc)
    if "--status" in sys.argv:
        print("next:", next_event(now), "| cron healthy:", cron_healthy(now), "| keeper alive:", keeper_alive())
        return
    if "--ensure" in sys.argv:
        # called at the end of the scheduled workflows: make sure a keeper is alive
        if keeper_alive():
            print("a keeper is already running")
        else:
            dispatch("keeper.yml")
        return

    start = time.time()
    print(f"keeper up at {now:%Y-%m-%d %H:%M:%S} UTC", flush=True)
    while True:
        now = datetime.now(timezone.utc)
        due, wf = next_event(now)
        wait = (due - now).total_seconds()
        budget = HANDOVER_AFTER - (time.time() - start)
        if wait > budget:
            # the next job is further away than this run may live: sleep out the budget, then hand over
            print(f"{now:%H:%M:%S} next: {wf} at {due:%H:%M} UTC, beyond this run's budget; handing over in {max(budget,0)/60:.0f} min", flush=True)
            time.sleep(max(0.0, budget))
            break
        print(f"{now:%H:%M:%S} next: {wf} at {due:%H:%M} UTC (in {wait/60:.1f} min)", flush=True)
        time.sleep(max(0.0, wait))
        now = datetime.now(timezone.utc)
        wf_file, _, reason = wf.partition(":")
        if started_recently(wf_file, now):
            print(f"{now:%H:%M:%S} {wf_file} already started (cron or another keeper); skipping", flush=True)
        else:
            dispatch(wf_file, reason or None)
        time.sleep(61)   # never dispatch the same minute twice
    print("handing over to a fresh keeper")
    dispatch("keeper.yml")


if __name__ == "__main__":
    main()
