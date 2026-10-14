"""Turn an NHL scoreboard snapshot into docs/live.json, the facts the dashboard needs to
show live and final results for every market on a slate.

    python tools/make_live.py 2026-10-13 snapshot.json docs/live.json

snapshot.json: JSON array of games, one object each:
  {"id": 2026020090, "state": "FINAL", "period": 4, "timeRemaining": "03:41", "away": "NJD", "home": "DET",
   "awayScore": 5, "homeScore": 4, "lastPeriodType": "OT",
   "goals": [{"period": 1, "time": "06:07", "team": "NJD"}, ...]}

Output per game: state, elapsed minutes of regulation play, first goal minute, first-period score and whether
the first period is complete, final score and how it ended. The page derives hit / miss / pending for each
market from these facts and the picks it already shows.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earlygoal.arenas import ARENAS  # noqa: E402

FINAL_STATES = {"OFF", "FINAL"}
LIVE_STATES = {"LIVE", "CRIT"}


def mmss(s):
    m, sec = str(s).split(":")
    return int(m) + int(sec) / 60.0


def main():
    date, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    games = json.loads(Path(src).read_text())
    out = {}
    for g in games:
        gid = int(g["id"])
        away, home = str(g["away"]).upper(), str(g["home"]).upper()
        assert away in ARENAS and home in ARENAS, f"unknown team in {g}"
        state = str(g.get("state") or "FUT").upper()
        period = g.get("period")
        rem = g.get("timeRemaining")
        goals = []
        for x in g.get("goals") or []:
            p = int(x["period"])
            t = mmss(x["time"])
            assert 1 <= p <= 5 and 0 <= t <= 20, f"bad goal time in {x}"
            team = str(x["team"]).upper()
            assert team in (home, away), f"goal team {team} not in {away}@{home}"
            if p == 5:  # shootout goals do not count as goals
                continue
            goals.append({"period": p, "minute": round((p - 1) * 20 + t, 3) if p <= 3 else round(60 + t, 3), "team": team})
        final = state in FINAL_STATES
        live = state in LIVE_STATES
        elapsed = 0.0
        if final:
            elapsed = 60.0
        elif live and period and rem:
            p = int(period)
            if p <= 3:
                elapsed = (p - 1) * 20 + (20 - mmss(rem))
            else:
                elapsed = 60.0
        # the scoreboard clock can lag the goal feed: never report less play than the goals prove
        if goals:
            elapsed = max(elapsed, max(x["minute"] for x in goals if x["period"] <= 3) if any(x["period"] <= 3 for x in goals) else elapsed)
        p1_done = bool(final or (live and period and int(period) >= 2) or any(x["period"] >= 2 for x in goals))
        if p1_done and not final:
            elapsed = max(elapsed, 20.0)
        p1_home = sum(1 for x in goals if x["period"] == 1 and x["team"] == home)
        p1_away = sum(1 for x in goals if x["period"] == 1 and x["team"] == away)
        first_goal = min((x["minute"] for x in goals), default=None)
        ended = None
        if final:
            lpt = str(g.get("lastPeriodType") or "REG").upper()
            ended = "SO" if lpt == "SO" else ("OT" if lpt == "OT" or (goals and max(x["period"] for x in goals) == 4) else "REG")
        hs = g.get("homeScore")
        as_ = g.get("awayScore")
        out[str(gid)] = {
            "state": state, "live": live, "final": final, "period": period, "time_remaining": rem,
            "elapsed_min": round(elapsed, 2), "home": home, "away": away,
            "home_score": None if hs is None else int(hs), "away_score": None if as_ is None else int(as_),
            "first_goal_min": first_goal, "p1_done": p1_done, "p1_home": p1_home, "p1_away": p1_away,
            "ended_in": ended, "goals": goals,
        }
    now = datetime.now(timezone.utc)
    payload = {"date": date, "updated_utc": now.strftime("%Y-%m-%d %H:%M UTC"),
               "updated_et": now.astimezone(ZoneInfo("America/Toronto")).strftime("%-I:%M %p ET"), "games": out}
    Path(dst).parent.mkdir(parents=True, exist_ok=True)
    Path(dst).write_text(json.dumps(payload, indent=1))
    n_live = sum(1 for v in out.values() if v["live"])
    n_final = sum(1 for v in out.values() if v["final"])
    print(f"{len(out)} games -> {dst}: {n_live} live, {n_final} final, {len(out) - n_live - n_final} not started")


if __name__ == "__main__":
    main()
