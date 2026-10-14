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


def parse_dailyfaceoff(html: str, date: str | None = None) -> dict[str, dict]:
    """Parse the page's embedded Next.js data: props.pageProps.data[] has one row per game with
    home/away team names, goalie names, a news strength (Confirmed / Expected / Likely / Unconfirmed),
    the reporter it came from and the game date."""
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return {}
    try:
        rows = json.loads(m.group(1))["props"]["pageProps"]["data"]
    except (KeyError, TypeError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for g in rows:
        if date and str(g.get("date", ""))[:10] != date:
            continue
        for side in ("home", "away"):
            team = DFO_TEAM_NAMES.get(g.get(f"{side}TeamName", ""))
            name = g.get(f"{side}GoalieName")
            if not team or not name:
                continue
            status = str(g.get(f"{side}NewsStrengthName") or "Unconfirmed")
            src = g.get(f"{side}NewsSourceName") or ""
            when = str(g.get(f"{side}NewsCreatedAt") or "")[:16].replace("T", " ")
            out[team] = {
                "name": name, "status": status, "source": "dailyfaceoff",
                "note": (f"{status} via {src} {when} UTC" if src else f"{status} on DailyFaceoff").strip(),
                "sv": g.get(f"{side}GoalieSavePercentage"), "date": str(g.get("date", ""))[:10],
            }
    return out


def scrape_dailyfaceoff(client: NHLClient | None, date: str) -> dict[str, dict]:
    """Fetch DailyFaceoff's starting-goalies page and parse it. Best effort: {} on any failure."""
    try:
        import requests  # type: ignore
    except Exception:  # pragma: no cover
        return {}
    try:
        r = requests.get(DFO_URL, timeout=20, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
        })
        r.raise_for_status()
    except Exception:
        return {}
    return parse_dailyfaceoff(r.text, date)


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
        return {"goalie": gp, "status": status, "source": "dailyfaceoff", "note": dfo[team].get("note", "")}

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
