"""Starting-goalie resolution with an explicit confidence status.

Order of precedence:
  1. data/overrides.json   -> status "confirmed" (you typed it from a beat
                              reporter / DailyFaceoff / team announcement)
  2. DailyFaceoff scrape    -> status as published there (Confirmed / Expected /
                              Unconfirmed), best effort, may be unavailable
  3. usage heuristic        -> status "projected": the team's most-used goalie,
                              flipped to the backup when the #1 played yesterday

The status is carried through to the dashboard and to the confidence tier.
A starter that is only "projected" caps the tier at B, because the goalie is
the single biggest knob in an early-goal model.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from .config import OVERRIDES_FILE
from .features import GoalieProfile
from .nhl_api import NHLClient

DFO_URL = "https://www.dailyfaceoff.com/starting-goalies/"
DFO_TEAM_NAMES = {
    "Anaheim Ducks": "ANA", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF", "Calgary Flames": "CGY",
    "Carolina Hurricanes": "CAR", "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL",
    "Columbus Blue Jackets": "CBJ", "Dallas Stars": "DAL", "Detroit Red Wings": "DET", "Edmonton Oilers": "EDM",
    "Florida Panthers": "FLA", "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN", "Montreal Canadiens": "MTL",
    "Montréal Canadiens": "MTL", "Nashville Predators": "NSH", "New Jersey Devils": "NJD",
    "New York Islanders": "NYI", "New York Rangers": "NYR", "Ottawa Senators": "OTT", "Philadelphia Flyers": "PHI",
    "Pittsburgh Penguins": "PIT", "San Jose Sharks": "SJS", "Seattle Kraken": "SEA", "St. Louis Blues": "STL",
    "St Louis Blues": "STL", "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR", "Utah Mammoth": "UTA",
    "Utah Hockey Club": "UTA", "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK",
    "Washington Capitals": "WSH", "Winnipeg Jets": "WPG",
}


def load_overrides(path: Path = OVERRIDES_FILE) -> dict:
    if not Path(path).exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _norm(s: str) -> str:
    return re.sub(r"[^a-z]", "", s.lower())


def _find_by_name(name: str, team: str, goalies: dict[int, GoalieProfile]) -> GoalieProfile | None:
    target = _norm(name)
    # exact-ish match on the team first, then league-wide
    for pool in ([g for g in goalies.values() if g.team == team], list(goalies.values())):
        for g in pool:
            if g.name and (_norm(g.name) == target or _norm(g.name.split()[-1]) == target):
                return g
    return None


def scrape_dailyfaceoff(client: NHLClient, date: str) -> dict[str, dict]:
    """Best-effort: returns {TEAM: {'name': 'First Last', 'status': 'Confirmed'|'Expected'|'Unconfirmed'}}."""
    try:
        import requests  # type: ignore
    except Exception:  # pragma: no cover
        return {}
    try:
        r = requests.get(DFO_URL, timeout=15, headers={"User-Agent": "Mozilla/5.0 (research tool)"})
        r.raise_for_status()
        html = r.text
    except Exception:
        return {}
    out: dict[str, dict] = {}
    # Try the Next.js data island first.
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    blobs: list[str] = [m.group(1)] if m else []
    blobs.append(html)
    for blob in blobs:
        for team_name, ab in DFO_TEAM_NAMES.items():
            if ab in out:
                continue
            idx = blob.find(team_name)
            if idx < 0:
                continue
            window = blob[idx : idx + 2500]
            status = None
            for s in ("Confirmed", "Expected", "Likely", "Unconfirmed", "Projected"):
                if s in window:
                    status = s
                    break
            nm = re.search(r'"(?:goalieName|name|playerName)"\s*:\s*"([A-Z][a-zA-Z\'\-\. ]+ [A-Z][a-zA-Z\'\-\. ]+)"', window)
            if nm and status:
                out[ab] = {"name": nm.group(1), "status": status, "source": "dailyfaceoff"}
    return out


def resolve_starter(
    team: str,
    date: str,
    goalies: dict[int, GoalieProfile],
    overrides: dict,
    dfo: dict[str, dict],
    rest: dict,
) -> dict:
    """Pick the starter and return {'goalie': GoalieProfile|None, 'status': str, 'source': str, 'note': str}."""
    ov = (overrides.get(date, {}) or {}).get(team) or (overrides.get("*", {}) or {}).get(team)
    if ov:
        who = ov.get("starter") or ov.get("goalie")
        gp = goalies.get(who) if isinstance(who, int) else _find_by_name(str(who), team, goalies)
        if gp is None and who:
            gp = GoalieProfile(goalie_id=0, name=str(who), team=team)
        st = str(ov.get("status", "confirmed")).lower()
        status = "confirmed" if st == "confirmed" else ("expected" if st in ("expected", "likely", "projected") else "unconfirmed")
        return {"goalie": gp, "status": status, "source": ov.get("source", "override"), "note": ov.get("note", "")}

    if team in dfo:
        gp = _find_by_name(dfo[team]["name"], team, goalies)
        if gp is None:
            gp = GoalieProfile(goalie_id=0, name=dfo[team]["name"], team=team)
        st = dfo[team]["status"].lower()
        status = "confirmed" if st == "confirmed" else ("expected" if st in ("expected", "likely", "projected") else "unconfirmed")
        return {"goalie": gp, "status": status, "source": "dailyfaceoff", "note": ""}

    # heuristic on usage
    pool = [g for g in goalies.values() if g.team == team and (g.starts_cur + g.starts_prior) > 0]
    if not pool:
        return {"goalie": None, "status": "unknown", "source": "none", "note": "no goalie data for team"}
    pool.sort(key=lambda g: (g.starts_cur, g.starts_prior), reverse=True)
    starter = pool[0]
    note = f"most-used goalie ({starter.starts_cur} starts this season)"
    yesterday = (datetime.fromisoformat(date) - timedelta(days=1)).strftime("%Y-%m-%d")
    if rest.get("b2b") and starter.last_start_date == yesterday and len(pool) > 1:
        starter = pool[1]
        note = f"back-to-back and #1 ({pool[0].name}) started yesterday; projecting backup"
    return {"goalie": starter, "status": "projected", "source": "usage-heuristic", "note": note}
