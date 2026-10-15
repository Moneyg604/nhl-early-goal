"""Sportsbook prices from The Odds API (https://the-odds-api.com) when ODDS_API_KEY is set.

Credits: a request costs (markets returned) x (regions). Game lines for the whole slate are one request
(3 credits in one region). Props are per game: quarterback passing yards, passing touchdowns, anytime
touchdown, and the first- and second-half totals (5 credits per game). To stay inside the free plan
(500 credits a month) props are fetched only on the pre-kickoff runs, for the games about to start, and
skipped when fewer than PROP_RESERVE credits remain. Region "us" covers the books available in Ontario
(DraftKings, FanDuel, BetMGM, BetRivers, ...).

For every outcome we keep the best price across books (with the book's name), the number of books, and
the consensus probability (median of each book's vig-free two-way price), so the page can show both the
price you can get and what the market as a whole thinks.

    data/nfl/odds.json            latest snapshot per game key "AWAY@HOME" for the current week
    data/nfl/odds_history.jsonl   every snapshot (opening -> closing, for line movement and CLV)
"""
from __future__ import annotations

import json
import os
import statistics
from datetime import datetime, timezone

from .config import DATA_DIR
from .live import name_key

SPORT = "americanfootball_nfl"
BASE = "https://api.the-odds-api.com/v4/sports/" + SPORT
REGIONS = "us"
# prop markets in priority order (the validated ones first); the monthly budget decides how many are requested per game
PROP_PRIORITY = ["player_pass_yds", "player_pass_tds", "player_anytime_td", "player_reception_yds", "player_rush_yds", "player_receptions",
                 "totals_h1", "totals_h2"]
MONTHLY_CREDITS = 500
NHL_DAILY = 3                 # the NHL morning pull
NFL_LINES_WEEKLY = 6          # two game-line pulls a week


def prop_markets_for_budget(remaining: int | None, games_left: int, days_left: int) -> list[str]:
    """How many prop markets per game the free plan can afford for the rest of the month, after the NHL
    morning pulls and the NFL game-line pulls. Never below the three validated markets while any budget
    remains; nothing when the reserve for the other pulls would be eaten."""
    if remaining is None:
        return PROP_PRIORITY[:3]
    reserve = NHL_DAILY * days_left + NFL_LINES_WEEKLY * (days_left / 7) + 15
    spare = remaining - reserve
    if spare <= 0 or games_left <= 0:
        return []
    per_game = int(spare // games_left)
    return PROP_PRIORITY[:max(0, min(len(PROP_PRIORITY), per_game))] if per_game >= 3 else (PROP_PRIORITY[:3] if spare >= 3 * games_left * 0.5 else [])
ODDS_FILE = DATA_DIR / "odds.json"
HISTORY = DATA_DIR / "odds_history.jsonl"

TEAMS = {"Arizona Cardinals": "ARI", "Atlanta Falcons": "ATL", "Baltimore Ravens": "BAL", "Buffalo Bills": "BUF", "Carolina Panthers": "CAR",
         "Chicago Bears": "CHI", "Cincinnati Bengals": "CIN", "Cleveland Browns": "CLE", "Dallas Cowboys": "DAL", "Denver Broncos": "DEN",
         "Detroit Lions": "DET", "Green Bay Packers": "GB", "Houston Texans": "HOU", "Indianapolis Colts": "IND", "Jacksonville Jaguars": "JAX",
         "Kansas City Chiefs": "KC", "Las Vegas Raiders": "LV", "Los Angeles Chargers": "LAC", "Los Angeles Rams": "LA", "Miami Dolphins": "MIA",
         "Minnesota Vikings": "MIN", "New England Patriots": "NE", "New Orleans Saints": "NO", "New York Giants": "NYG", "New York Jets": "NYJ",
         "Philadelphia Eagles": "PHI", "Pittsburgh Steelers": "PIT", "San Francisco 49ers": "SF", "Seattle Seahawks": "SEA",
         "Tampa Bay Buccaneers": "TB", "Tennessee Titans": "TEN", "Washington Commanders": "WAS"}


def _get(url: str, params: dict) -> tuple[list | dict | None, int | None]:
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


def _two_way(book_prices: list[tuple[float, float]]) -> float | None:
    """Median vig-free probability of the first side over books that quote both sides."""
    ps = [(1 / a) / ((1 / a) + (1 / b)) for a, b in book_prices if a and b and a > 1 and b > 1]
    return round(statistics.median(ps), 4) if ps else None


def parse_game_lines(events: list[dict]) -> dict[str, dict]:
    out = {}
    for ev in events:
        h, a = TEAMS.get(ev.get("home_team", "")), TEAMS.get(ev.get("away_team", ""))
        if not h or not a:
            continue
        best: dict = {}
        pairs: dict = {"ml": [], "spread": {}, "total": {}}
        for bk in ev.get("bookmakers", []):
            title = bk.get("title") or bk.get("key")
            for mk in bk.get("markets", []):
                key = mk.get("key"); oc = mk.get("outcomes", [])
                if key == "h2h":
                    pr = {("home" if TEAMS.get(o.get("name")) == h else "away"): o.get("price") for o in oc}
                    for side, price in pr.items():
                        if price and price > best.get(("ml", side), (0, ""))[0]:
                            best[("ml", side)] = (price, title)
                    if "home" in pr and "away" in pr:
                        pairs["ml"].append((pr["home"], pr["away"]))
                elif key == "spreads":
                    pts = {("home" if TEAMS.get(o.get("name")) == h else "away"): (o.get("point"), o.get("price")) for o in oc}
                    if "home" in pts and "away" in pts:
                        line = pts["home"][0]               # book convention: home spread (negative = home favoured)
                        pairs["spread"].setdefault(line, []).append((pts["home"][1], pts["away"][1]))
                        for side in ("home", "away"):
                            k = ("spread", line, side)
                            if pts[side][1] > best.get(k, (0, ""))[0]:
                                best[k] = (pts[side][1], title)
                elif key == "totals":
                    d = {o.get("name", "").lower(): (o.get("point"), o.get("price")) for o in oc}
                    if "over" in d and "under" in d:
                        line = d["over"][0]
                        pairs["total"].setdefault(line, []).append((d["over"][1], d["under"][1]))
                        for side in ("over", "under"):
                            k = ("total", line, side)
                            if d[side][1] > best.get(k, (0, ""))[0]:
                                best[k] = (d[side][1], title)
        rec = {"home": h, "away": a, "event_id": ev.get("id"), "commence": ev.get("commence_time"), "books": len(ev.get("bookmakers", []))}
        per_book: dict = {"ml": {}, "spread": {}, "total": {}}
        for bk in ev.get("bookmakers", []):
            title = bk.get("title") or bk.get("key")
            for mk in bk.get("markets", []):
                key = mk.get("key"); oc = mk.get("outcomes", [])
                if key == "h2h":
                    per_book["ml"][title] = {("home" if TEAMS.get(o.get("name")) == h else "away"): o.get("price") for o in oc}
                elif key == "spreads":
                    d = {("home" if TEAMS.get(o.get("name")) == h else "away"): o for o in oc}
                    if "home" in d:
                        per_book["spread"][title] = {"line": d["home"].get("point"), "home": d["home"].get("price"), "away": (d.get("away") or {}).get("price")}
                elif key == "totals":
                    d = {o.get("name", "").lower(): o for o in oc}
                    if "over" in d:
                        per_book["total"][title] = {"line": d["over"].get("point"), "over": d["over"].get("price"), "under": (d.get("under") or {}).get("price")}
        if pairs["ml"]:
            rec["ml"] = {"home": best[("ml", "home")][0], "away": best[("ml", "away")][0], "book_home": best[("ml", "home")][1],
                         "book_away": best[("ml", "away")][1], "consensus_home": _two_way(pairs["ml"]), "n": len(pairs["ml"])}
        for mk in ("spread", "total"):
            if pairs[mk]:
                line = max(pairs[mk], key=lambda L: len(pairs[mk][L]))   # the line most books post
                s1, s2 = ("home", "away") if mk == "spread" else ("over", "under")
                rec[mk] = {"line": line, s1: best[(mk, line, s1)][0], s2: best[(mk, line, s2)][0], f"book_{s1}": best[(mk, line, s1)][1],
                           f"book_{s2}": best[(mk, line, s2)][1], f"consensus_{s1}": _two_way(pairs[mk][line]), "n": len(pairs[mk][line])}
        for mk in ("ml", "spread", "total"):
            if mk in rec:
                rec[mk]["books"] = per_book[mk]
        out[f"{a}@{h}"] = rec
    return out


def parse_props(ev: dict) -> dict:
    """Event odds -> {"qb_yds": {key: {...}}, "qb_td": {...}, "atd": {key: {...}}, "h1": {...}, "h2": {...}}."""
    h, a = TEAMS.get(ev.get("home_team", "")), TEAMS.get(ev.get("away_team", ""))
    acc: dict = {}
    for bk in ev.get("bookmakers", []):
        title = bk.get("title") or bk.get("key")
        for mk in bk.get("markets", []):
            key = mk.get("key")
            groups: dict = {}
            for o in mk.get("outcomes", []):
                who = o.get("description") or ""
                groups.setdefault((who, o.get("point")), {})[o.get("name", "").lower()] = o.get("price")
            for (who, point), d in groups.items():
                slot = {"player_pass_yds": "qb_yds", "player_pass_tds": "qb_td", "player_anytime_td": "atd", "totals_h1": "h1", "totals_h2": "h2",
                        "player_reception_yds": "rec_yds", "player_rush_yds": "rush_yds", "player_receptions": "recs"}.get(key)
                if not slot:
                    continue
                k = (slot, name_key(who) if who else "game", point)
                e = acc.setdefault(k, {"name": who, "line": point, "best": {}, "pairs": [], "books": {}})
                e["books"][title] = {sd: pr for sd, pr in d.items() if pr}      # every book's own line and price
                for side, price in d.items():
                    if price and price > e["best"].get(side, (0, ""))[0]:
                        e["best"][side] = (price, title)
                if "over" in d and "under" in d:
                    e["pairs"].append((d["over"], d["under"]))
                if "yes" in d and "no" in d:
                    e["pairs"].append((d["yes"], d["no"]))
    out: dict = {"qb_yds": {}, "qb_td": {}, "atd": {}, "h1": {}, "h2": {}, "rec_yds": {}, "rush_yds": {}, "recs": {}}
    # per player / market keep the line most books post
    by: dict = {}
    for (slot, who, point), e in acc.items():
        by.setdefault((slot, who), []).append(e)
    for (slot, who), es in by.items():
        e = max(es, key=lambda x: (len(x["pairs"]), len(x["best"])))
        rec = {"name": e["name"], "line": e["line"], "n": len(e["pairs"])}
        for side, (price, title) in e["best"].items():
            rec[side] = price; rec[f"book_{side}"] = title
        cons = _two_way(e["pairs"])
        if cons is not None:
            rec["consensus_" + ("yes" if slot == "atd" else "over")] = cons
        # each book's own line (books post different numbers: the page prices the one you can actually bet)
        rec["books"] = {}
        for x in es:
            for title, d in x["books"].items():
                rec["books"][title] = {"line": x["line"], **d}
        if slot in ("h1", "h2"):
            out[slot] = rec
        else:
            out[slot][who] = rec
    out["home"], out["away"] = h, a
    return out


def fetch(reason: str, games_window: list[str] | None = None, api_key: str | None = None, games_left: int = 60) -> dict:
    """Game lines for the slate every call; props for `games_window` ("AWAY@HOME" keys), as many markets per game as
    the month's remaining credits allow (`games_left` = regular-season games still to be played this month)."""
    import calendar

    key = api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        return {}
    events, rem = _get(BASE + "/odds/", {"apiKey": key, "regions": REGIONS, "markets": "h2h,spreads,totals", "oddsFormat": "decimal"})
    if events is None:
        return {}
    snap = parse_game_lines(events)
    now_dt = datetime.now(timezone.utc)
    now = now_dt.strftime("%Y-%m-%dT%H:%MZ")
    days_left = calendar.monthrange(now_dt.year, now_dt.month)[1] - now_dt.day + 1
    markets = prop_markets_for_budget(rem, games_left, days_left) if games_window else []
    props_done = 0
    if games_window and markets:
        print(f"  odds: {rem} credits left, {games_left} games and {days_left} days in the month: {len(markets)} prop markets per game")
        for gk in games_window:
            g = snap.get(gk)
            if not g or not g.get("event_id"):
                continue
            ev, rem = _get(f"{BASE}/events/{g['event_id']}/odds", {"apiKey": key, "regions": REGIONS, "markets": ",".join(markets), "oddsFormat": "decimal"})
            if ev:
                g["props"] = parse_props(ev)
                g["props_fetched"] = now
                props_done += 1
            if rem is not None and rem <= 20:
                print(f"  odds: stopping props, {rem} credits left")
                break
    elif games_window:
        print(f"  odds: props skipped, {rem} credits left this month")
    # merge into the latest file (props from an earlier run are kept until replaced)
    old = {}
    if ODDS_FILE.exists():
        try:
            old = json.loads(ODDS_FILE.read_text())
        except json.JSONDecodeError:
            old = {}
    games = old.get("games", {})
    # drop games that started more than two days ago
    cutoff = datetime.now(timezone.utc).timestamp() - 2 * 86400
    for gk in [k for k, v in games.items() if _ts(v.get("commence")) < cutoff]:
        games.pop(gk)
    for gk, g in snap.items():
        prev = games.get(gk, {})
        if "props" not in g and "props" in prev:
            g["props"] = prev["props"]; g["props_fetched"] = prev.get("props_fetched")
        g["opening"] = prev.get("opening") or {k: g.get(k) for k in ("ml", "spread", "total")}
        g["fetched"] = now
        games[gk] = g
    out = {"updated_utc": now, "credits_remaining": rem, "games": games, "reason": reason}
    ODDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ODDS_FILE.write_text(json.dumps(out, separators=(",", ":")))
    with HISTORY.open("a") as fh:
        for gk, g in snap.items():
            fh.write(json.dumps({"t": now, "game": gk, "ml": g.get("ml"), "spread": g.get("spread"), "total": g.get("total"),
                                 "props": g.get("props") if g.get("props_fetched") == now else None}, separators=(",", ":")) + "\n")
    print(f"odds: {len(snap)} games, props for {props_done}, {rem} credits left this month")
    return out


def _ts(iso: str | None) -> float:
    try:
        return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def for_game(odds: dict, home: str, away: str, kickoff_utc: str | None) -> dict | None:
    """The snapshot for this matchup if its start time is within a day of the scheduled kickoff."""
    g = odds.get(f"{away}@{home}")
    if not g or not kickoff_utc:
        return g
    try:
        k = datetime.strptime(kickoff_utc, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return g
    return g if abs(_ts(g.get("commence")) - k) < 86400 else None


def load() -> dict:
    if not ODDS_FILE.exists():
        return {}
    try:
        return json.loads(ODDS_FILE.read_text()).get("games", {})
    except json.JSONDecodeError:
        return {}


__all__ = ["fetch", "load", "for_game", "parse_game_lines", "parse_props"]
