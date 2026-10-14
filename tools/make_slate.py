"""Validate and write a slate file from a JSON list of games.

    python tools/make_slate.py 2026-10-14 games.json data/slate-2026-10-14.json

games.json: [{"id": 2026020106, "away": "NYR", "home": "BOS", "startTimeUTC": "2026-10-14T23:00:00Z"}, ...]
Rejects unknown team codes, duplicate ids, ids outside the season, and bad timestamps.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earlygoal.arenas import ARENAS  # noqa: E402

date, src, dst = sys.argv[1], sys.argv[2], sys.argv[3]
games = json.loads(Path(src).read_text())
y, m = int(date[:4]), int(date[5:7])
season = (y * 10000 + y + 1) if m >= 9 else ((y - 1) * 10000 + y)
prefix = str(season)[:4] + "02"
out, seen = [], set()
for g in games:
    gid = int(g["id"])
    away, home = g["away"].upper(), g["home"].upper()
    assert away in ARENAS and home in ARENAS, f"unknown team in {g}"
    assert str(gid).startswith(prefix), f"game id {gid} is not a regular-season id for {season}"
    assert gid not in seen, f"duplicate id {gid}"
    datetime.fromisoformat(g["startTimeUTC"].replace("Z", "+00:00"))
    seen.add(gid)
    out.append({"game_id": gid, "date": date, "season": season, "start_utc": g["startTimeUTC"], "home": home, "away": away,
                "home_id": ARENAS[home][0], "away_id": ARENAS[away][0], "venue": ARENAS[home][1], "state": "FUT"})
out.sort(key=lambda x: x["game_id"])
Path(dst).write_text(json.dumps(out, indent=1))
print(f"{len(out)} games written to {dst}")
