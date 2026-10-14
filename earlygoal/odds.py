"""Market prices from The Odds API (https://the-odds-api.com), when a key is configured.

The free tier (500 requests a month) covers a handful of calls a day. One call returns every NHL game with
moneyline (h2h), the main total and the puck line from each listed book. We keep, per game and market,
the best price on offer and which book offered it, and write it in the shape `rank.load_odds` reads:

    data/odds.json   {"2026-10-14": {"MTL@WSH": {"fg_ml": {"home": 1.65, "away": 2.30, "book": {...}},
                                                  "fg_spread_m15": {"home": 2.60, "away": 1.50},
                                                  "fg_total": {"line": 6.5, "over": 1.87, "under": 1.95},
                                                  "fetched_utc": "..."}}}

First-5 and first-10 markets are not carried by the odds feeds; those stay with the page's price check.
"""
from __future__ import annotations

import json
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DATA_DIR

API = "https://api.the-odds-api.com/v4/sports/icehockey_nhl/odds/"

TEAM_NAMES = {
    "Anaheim Ducks": "ANA", "Boston Bruins": "BOS", "Buffalo Sabres": "BUF", "Carolina Hurricanes": "CAR", "Columbus Blue Jackets": "CBJ",
    "Calgary Flames": "CGY", "Chicago Blackhawks": "CHI", "Colorado Avalanche": "COL", "Dallas Stars": "DAL", "Detroit Red Wings": "DET",
    "Edmonton Oilers": "EDM", "Florida Panthers": "FLA", "Los Angeles Kings": "LAK", "Minnesota Wild": "MIN", "Montreal Canadiens": "MTL",
    "New Jersey Devils": "NJD", "Nashville Predators": "NSH", "New York Islanders": "NYI", "New York Rangers": "NYR", "Ottawa Senators": "OTT",
    "Philadelphia Flyers": "PHI", "Pittsburgh Penguins": "PIT", "Seattle Kraken": "SEA", "San Jose Sharks": "SJS", "St Louis Blues": "STL",
    "St. Louis Blues": "STL", "Tampa Bay Lightning": "TBL", "Toronto Maple Leafs": "TOR", "Utah Mammoth": "UTA", "Utah Hockey Club": "UTA",
    "Vancouver Canucks": "VAN", "Vegas Golden Knights": "VGK", "Winnipeg Jets": "WPG", "Washington Capitals": "WSH",
}


def _abbrev(name: str) -> str | None:
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    if n in TEAM_NAMES:
        return TEAM_NAMES[n]
    for full, ab in TEAM_NAMES.items():
        if full.split()[-1] == n.split()[-1] and full.split()[0] == n.split()[0]:
            return ab
    return None


def parse_events(events: list[dict], date_et: str | None = None) -> dict[str, dict]:
    """Odds API events -> {"AWAY@HOME": {...}} for games on `date_et` (Eastern date of the start time)."""
    out: dict[str, dict] = {}
    for ev in events:
        home, away = _abbrev(ev.get("home_team", "")), _abbrev(ev.get("away_team", ""))
        if not home or not away:
            continue
        try:
            start = datetime.fromisoformat(str(ev.get("commence_time", "")).replace("Z", "+00:00"))
            d_et = start.astimezone(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d")
        except ValueError:
            d_et = None
        if date_et and d_et != date_et:
            continue
        ml: dict[str, tuple[float, str]] = {}
        pl: dict[str, tuple[float, str]] = {}
        totals: dict[float, dict[str, tuple[float, str]]] = {}
        for bk in ev.get("bookmakers", []):
            title = bk.get("title") or bk.get("key") or "book"
            for mk in bk.get("markets", []):
                key = mk.get("key")
                for oc in mk.get("outcomes", []):
                    price = oc.get("price")
                    if not isinstance(price, (int, float)) or price <= 1:
                        continue
                    if key == "h2h":
                        side = "home" if _abbrev(oc.get("name", "")) == home else ("away" if _abbrev(oc.get("name", "")) == away else None)
                        if side and (side not in ml or price > ml[side][0]):
                            ml[side] = (float(price), title)
                    elif key == "spreads":
                        side = "home" if _abbrev(oc.get("name", "")) == home else ("away" if _abbrev(oc.get("name", "")) == away else None)
                        if side and oc.get("point") == -1.5 and (side not in pl or price > pl[side][0]):
                            pl[side] = (float(price), title)
                    elif key == "totals":
                        pt = oc.get("point")
                        if not isinstance(pt, (int, float)):
                            continue
                        t = totals.setdefault(float(pt), {})
                        s = str(oc.get("name", "")).lower()
                        if s in ("over", "under") and (s not in t or price > t[s][0]):
                            t[s] = (float(price), title)
        rec: dict = {"home_team": home, "away_team": away, "start_utc": ev.get("commence_time"), "date_et": d_et}
        if ml:
            rec["fg_ml"] = {k: v[0] for k, v in ml.items()}
            rec["fg_ml"]["book"] = {k: v[1] for k, v in ml.items()}
        if pl:
            rec["fg_spread_m15"] = {k: v[0] for k, v in pl.items()}
            rec["fg_spread_m15"]["book"] = {k: v[1] for k, v in pl.items()}
        if totals:
            # the main line is the one most books post; take the line with the most complete two-way quote closest to even
            def score(item):
                pt, q = item
                return (-(("over" in q) + ("under" in q)), abs(q.get("over", (2.0,))[0] - q.get("under", (2.0,))[0]))

            line, q = sorted(totals.items(), key=score)[0]
            rec["fg_total"] = {"line": line, "over": q.get("over", (None,))[0], "under": q.get("under", (None,))[0],
                               "book": {k: v[1] for k, v in q.items()}}
            for pt, q2 in totals.items():
                if pt == 5.5 and "over" in q2:
                    rec["fg_over55"] = q2["over"][0]
                if pt == 4.5 and "over" in q2:
                    rec["fg_over45"] = q2["over"][0]
        rec["fetched_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        out[f"{away}@{home}"] = rec
    return out


def fetch(date_et: str, api_key: str | None = None, regions: str = "us,us2,uk,eu", path: Path | None = None) -> dict[str, dict]:
    """Fetch and merge into data/odds.json under `date_et`. Returns that day's block; {} without a key."""
    import requests  # type: ignore

    key = api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        return {}
    r = requests.get(API, params={"regions": regions, "markets": "h2h,totals,spreads", "oddsFormat": "decimal", "apiKey": key}, timeout=30)
    r.raise_for_status()
    day = parse_events(r.json(), date_et)
    p = path or (DATA_DIR / "odds.json")
    all_odds = {}
    if p.exists():
        try:
            all_odds = json.loads(p.read_text())
        except json.JSONDecodeError:
            all_odds = {}
    prev = all_odds.get(date_et, {})
    prev.update(day)
    all_odds[date_et] = prev
    # keep the file small: the last 10 days
    for d in sorted(all_odds)[:-10]:
        del all_odds[d]
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(all_odds, indent=1))
    remaining = r.headers.get("x-requests-remaining")
    print(f"odds: {len(day)} games for {date_et} ({remaining} requests left this month)" if remaining else f"odds: {len(day)} games for {date_et}")
    return day
