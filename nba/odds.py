"""NBA prices. Game lines (spread, total, moneyline) come free from ESPN's DraftKings "pickcenter" block, so The
Odds API is spent only on player props, and only within a nightly credit cap so the free plan (500 credits a month,
shared with the NHL morning pull and the NFL weekend pulls) is never exhausted.

    data/nba/odds.json            latest props snapshot per game key "AWAY@HOME" for the day
    data/nba/odds_history.jsonl   every snapshot (for line movement and closing prices)

Props: one credit per market per game (ten named books count as one region). The nightly cap and the market order
are in data/nba/desk_config.json ("odds": {"credits_per_night": 4, "markets": [...]}); the games priced are the
ones the model lists the most props for (the games with the most usable projections), earliest tip first.
"""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone

from .config import DATA_DIR, ODDS_TEAMS

SPORT = "basketball_nba"
BASE = "https://api.the-odds-api.com/v4/sports/" + SPORT
BOOKMAKERS = "draftkings,fanduel,betmgm,williamhill_us,betrivers,fanatics,pinnacle,bovada,betonlineag,lowvig"
MARKET_SLOT = {"player_points": "pts", "player_rebounds": "reb", "player_assists": "ast", "player_threes": "threes", "player_points_rebounds_assists": "pra"}
DEFAULT_MARKETS = ["player_points", "player_rebounds", "player_assists", "player_threes", "player_points_rebounds_assists"]
ODDS_FILE = DATA_DIR / "odds.json"
HISTORY = DATA_DIR / "odds_history.jsonl"


def _get(url: str, params: dict):
    import requests  # type: ignore
    r = requests.get(url, params=params, timeout=30)
    rem = r.headers.get("x-requests-remaining")
    try:
        rem_i = int(float(rem)) if rem is not None else None
    except ValueError:
        rem_i = None
    if not r.ok:
        print(f"  odds API {r.status_code}: {r.text[:200]}")
        return None, rem_i
    return r.json(), rem_i


def _two_way(pairs) -> float | None:
    ps = [(1 / a) / ((1 / a) + (1 / b)) for a, b in pairs if a and b and a > 1 and b > 1]
    return round(statistics.median(ps), 4) if ps else None


def name_key(n: str) -> str:
    """Full lower-case name (two NBA players often share an initial and a surname)."""
    from nfl.live import full_key
    return full_key(n or "")


def parse_props(ev: dict) -> dict:
    """Event odds -> {"pts": {key: {name, line, over, under, book_over, book_under, consensus_over, n, books}}, ...}."""
    h, a = ODDS_TEAMS.get(ev.get("home_team", "")), ODDS_TEAMS.get(ev.get("away_team", ""))
    acc: dict = {}
    for bk in ev.get("bookmakers", []):
        title = bk.get("title") or bk.get("key")
        for mk in bk.get("markets", []):
            slot = MARKET_SLOT.get(mk.get("key"))
            if not slot:
                continue
            groups: dict = {}
            for o in mk.get("outcomes", []):
                groups.setdefault((o.get("description") or "", o.get("point")), {})[o.get("name", "").lower()] = o.get("price")
            for (who, point), d in groups.items():
                e = acc.setdefault((slot, who, point), {"name": who, "line": point, "best": {}, "pairs": [], "books": {}})
                e["books"][title] = {sd: pr for sd, pr in d.items() if pr}
                for side, price in d.items():
                    if price and price > e["best"].get(side, (0, ""))[0]:
                        e["best"][side] = (price, title)
                if "over" in d and "under" in d:
                    e["pairs"].append((d["over"], d["under"]))
    out: dict = {s: {} for s in MARKET_SLOT.values()}
    by: dict = {}
    for (slot, who, point), e in acc.items():
        by.setdefault((slot, who), []).append(e)
    for (slot, who), es in by.items():
        # DraftKings' own line when it posts one, else the line most books post
        dk = next((x for x in es if "DraftKings" in x["books"]), None)
        e = dk or max(es, key=lambda x: (len(x["pairs"]), len(x["best"])))
        rec = {"name": who, "line": e["line"], "n": len(e["pairs"])}
        for side, (price, title) in e["best"].items():
            rec[side] = price; rec[f"book_{side}"] = title
        cons = _two_way(e["pairs"])
        if cons is not None:
            rec["consensus_over"] = cons
        rec["books"] = {}
        for x in es:
            for title, d in x["books"].items():
                rec["books"][title] = {"line": x["line"], **d}
        out[slot][name_key(who)] = rec
    out["home"], out["away"] = h, a
    return out


def fetch_props(games: list[dict], credits: int, markets: list[str], api_key: str) -> dict:
    """Price the given games (dicts with home/away/tip_utc) within `credits`: markets in order, one game at a time."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    books = {"bookmakers": BOOKMAKERS}
    events, rem = _get(BASE + "/events", {"apiKey": api_key})
    if events is None:
        return {}
    ev_by = {}
    for ev in events:
        h, a = ODDS_TEAMS.get(ev.get("home_team", "")), ODDS_TEAMS.get(ev.get("away_team", ""))
        if h and a:
            ev_by[f"{a}@{h}"] = ev
    snap = load()
    out = dict(snap.get("games") or {})
    spent = 0
    per_game = max(1, min(len(markets), credits // max(1, len(games)))) if games else 0
    for g in games:
        gk = f'{g["away"]}@{g["home"]}'
        ev = ev_by.get(gk)
        if not ev:
            print(f"  odds: no event for {gk}"); continue
        mk = markets[:per_game] if spent + per_game <= credits else markets[:max(0, credits - spent)]
        if not mk:
            break
        d, rem = _get(f"{BASE}/events/{ev['id']}/odds", {"apiKey": api_key, **books, "markets": ",".join(mk), "oddsFormat": "decimal"})
        spent += len(mk)
        if not d:
            continue
        props = parse_props(d)
        out[gk] = {"home": g["home"], "away": g["away"], "event_id": ev["id"], "commence": ev.get("commence_time"), "props": props, "props_fetched": now, "markets": mk}
        with HISTORY.open("a") as f:
            f.write(json.dumps({"t": now, "game": gk, "props": props}, separators=(",", ":")) + "\n")
        if rem is not None and rem < 20:
            print(f"  odds: stopping, {rem} credits left this month"); break
    res = {"updated_utc": now, "credits_remaining": rem, "games": out}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ODDS_FILE.write_text(json.dumps(res, separators=(",", ":")))
    print(f"odds: props for {len(games)} games, {spent} credits spent, {rem} left this month")
    return res


def load() -> dict:
    if ODDS_FILE.exists():
        try:
            return json.loads(ODDS_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def for_game(odds: dict, home: str, away: str, tip_utc: str | None, max_age_h: float = 30.0) -> dict | None:
    g = (odds.get("games") or {}).get(f"{away}@{home}")
    if not g:
        return None
    try:
        age = (datetime.now(timezone.utc) - datetime.strptime(g["props_fetched"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)).total_seconds() / 3600
    except (KeyError, ValueError):
        age = 0
    return g if age <= max_age_h else None


__all__ = ["fetch_props", "load", "for_game", "parse_props", "MARKET_SLOT", "DEFAULT_MARKETS"]
