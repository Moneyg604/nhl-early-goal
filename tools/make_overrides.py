"""Write data/overrides.json for a date from a JSON list of starters.

    python tools/make_overrides.py 2026-10-14 starters.json [source-label]

starters.json: [{"team": "NYI", "goalie": "Ilya Sorokin", "status": "Confirmed"}, ...]
Status is mapped to confirmed / expected / unconfirmed; unknown teams are rejected.
Existing entries for other dates are kept.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from earlygoal.arenas import ARENAS  # noqa: E402
from earlygoal.config import OVERRIDES_FILE  # noqa: E402

date, src = sys.argv[1], sys.argv[2]
label = sys.argv[3] if len(sys.argv) > 3 else "dailyfaceoff"
rows = json.loads(Path(src).read_text())
existing = json.loads(OVERRIDES_FILE.read_text()) if OVERRIDES_FILE.exists() else {}
day = {}
for r in rows:
    team = r["team"].upper()
    assert team in ARENAS, f"unknown team {team}"
    st = str(r.get("status", "")).lower()
    status = "confirmed" if st.startswith("conf") else ("expected" if st in ("expected", "likely", "probable", "projected") else "unconfirmed")
    day[team] = {"starter": r["goalie"], "status": status, "source": label}
existing[date] = day
OVERRIDES_FILE.parent.mkdir(parents=True, exist_ok=True)
OVERRIDES_FILE.write_text(json.dumps(existing, indent=1))
print(f"{len(day)} starters written for {date} -> {OVERRIDES_FILE}")
