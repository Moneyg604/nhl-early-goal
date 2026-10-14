"""Fetch the NHL scoreboard directly (no LLM in the loop) and write docs/live.json.

    python tools/fetch_live.py [DATE] [out]      # default: today in America/Toronto, docs/live.json

Used by the GitHub Actions live workflow every few minutes during game hours.
Exits 0 with "no games" when the date has no games; exits 1 on network failure.
"""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

URL = "https://api-web.nhle.com/v1/score/now"


def snapshot(date: str) -> list[dict]:
    r = requests.get(URL, timeout=20, headers={"User-Agent": "earlygoal/0.5"})
    r.raise_for_status()
    data = r.json()
    out = []
    for g in data.get("games", []):
        if g.get("gameDate") != date or g.get("gameType") != 2:
            continue
        out.append({
            "id": g["id"], "state": g.get("gameState"), "period": g.get("period"),
            "timeRemaining": (g.get("clock") or {}).get("timeRemaining"),
            "away": g["awayTeam"]["abbrev"], "home": g["homeTeam"]["abbrev"],
            "awayScore": g["awayTeam"].get("score"), "homeScore": g["homeTeam"].get("score"),
            "lastPeriodType": (g.get("gameOutcome") or {}).get("lastPeriodType"),
            "goals": [{"period": x["period"], "time": x["timeInPeriod"], "team": x["teamAbbrev"]} for x in g.get("goals", [])],
        })
    return out


def main():
    now_et = datetime.now(ZoneInfo("America/Toronto"))
    date = sys.argv[1] if len(sys.argv) > 1 else now_et.strftime("%Y-%m-%d")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "docs" / "live.json"
    games = snapshot(date)
    if not games and len(sys.argv) <= 1 and now_et.hour < 4:
        # after midnight: last night's games may still be running
        date = (now_et - timedelta(days=1)).strftime("%Y-%m-%d")
        games = snapshot(date)
    if not games:
        print(f"no games for {date}")
        return
    tmp = out.with_suffix(".snap.json")
    tmp.write_text(json.dumps(games))
    import subprocess

    subprocess.run([sys.executable, str(ROOT / "tools" / "make_live.py"), date, str(tmp), str(out)], check=True)
    tmp.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
