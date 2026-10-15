"""DraftKings (and other book) prices for NHL props from The Odds API, inside the free plan's budget.

The event list is free. Each event's props cost one credit per market requested, so the day's allowance is
spent in priority order (shots on goal, points, anytime goal, team totals, assists, blocked shots), game by game
in start order, until it runs out. The allowance leaves room for the NHL morning game-line pull (3 a day),
the NFL game-line pulls and NFL props for the rest of the month. Every line a book posts is kept, so the page
prices the exact DraftKings number; games that did not fit the budget show the model's fair lines and the
price check instead.

    data/nhlprops/odds.json   {"date": "2026-10-15", "credits_remaining": 412, "games": {"MTL@TOR": {"sog": {name_key: {...}}, ...}}}
"""
from __future__ import annotations

import json
import os
import statistics
import unicodedata
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from .config import DATA_DIR

SPORT = "icehockey_nhl"
BASE = "https://api.the-odds-api.com/v4/sports/" + SPORT
REGIONS = "us"
PRIORITY = ["player_shots_on_goal", "player_points", "player_goal_scorer_anytime", "team_totals", "player_assists", "player_blocked_shots"]
SLOT = {"player_shots_on_goal": "sog", "player_points": "pts", "player_goal_scorer_anytime": "goal", "team_totals": "team_total",
        "player_assists": "ast", "player_blocked_shots": "blk"}
MONTHLY_CREDITS = 500
NHL_LINES_DAILY = 3
NFL_RESERVE_WEEKLY = 40       # game lines plus props on a football weekend
ODDS_FILE = DATA_DIR / "odds.json"
HISTORY = DATA_DIR / "odds_history.jsonl"

from earlygoal.odds import TEAM_NAMES  # noqa: E402


def name_key(name: str) -> str:
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()
    n = "".join(c for c in n if c.isalpha() or c == " ").strip()
    parts = n.split()
    if not parts:
        return ""
    return (parts[0][0] + " " + parts[-1]) if len(parts) > 1 else parts[0]


def _abbrev(name: str) -> str | None:
    n = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return TEAM_NAMES.get(n) or next((ab for full, ab in TEAM_NAMES.items() if full.split()[-1] == n.split()[-1]), None)


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


def _two_way(pairs):
    ps = [(1 / a) / ((1 / a) + (1 / b)) for a, b in pairs if a and b and a > 1 and b > 1]
    return round(statistics.median(ps), 4) if ps else None


def daily_allowance(remaining: int | None, now: datetime | None = None) -> int:
    """Credits the NHL props may spend today."""
    if remaining is None:
        return 0
    now = now or datetime.now(timezone.utc)
    nxt = (now.replace(day=1) + timedelta(days=32)).replace(day=1)
    days_left = max(1, (nxt - now).days + 1)
    reserve = NHL_LINES_DAILY * days_left + NFL_RESERVE_WEEKLY * days_left / 7 + 15
    spare = remaining - reserve
    return int(max(0, spare // days_left))


def parse_event(ev: dict) -> dict:
    """Event odds -> {slot: {key: {name, line, over/under or yes/no best prices, books{title: {side: price, point}}}}}."""
    home, away = _abbrev(ev.get("home_team", "")), _abbrev(ev.get("away_team", ""))
    acc: dict = {}
    for bk in ev.get("bookmakers", []):
        title = bk.get("title") or bk.get("key")
        for mk in bk.get("markets", []):
            slot = SLOT.get(mk.get("key"))
            if not slot:
                continue
            groups: dict = {}
            for o in mk.get("outcomes", []):
                who = o.get("description") or ""
                side = (o.get("name") or "").lower()
                if slot == "team_total":
                    # team totals: name = Over / Under, description = the team
                    who = _abbrev(who) or who
                groups.setdefault((who, o.get("point")), {})[side] = o.get("price")
            for (who, point), d in groups.items():
                k = (slot, name_key(who) if slot != "team_total" else who, point)
                e = acc.setdefault(k, {"name": who, "line": point, "best": {}, "pairs": [], "books": {}})
                e["books"][title] = {sd: pr for sd, pr in d.items() if pr}
                for side, price in d.items():
                    if price and price > e["best"].get(side, (0, ""))[0]:
                        e["best"][side] = (price, title)
                if "over" in d and "under" in d:
                    e["pairs"].append((d["over"], d["under"]))
                if "yes" in d and "no" in d:
                    e["pairs"].append((d["yes"], d["no"]))
    out: dict = {s: {} for s in SLOT.values()}
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
            rec["consensus"] = cons
        books: dict = {}
        for x in es:
            for title, d in x["books"].items():
                cur = books.get(title)
                if cur is None or len(d) > len(cur.get("prices", {})):
                    books[title] = {"line": x["line"], "prices": d}
        rec["books"] = books
        out[slot][who] = rec
    return {"home": home, "away": away, "markets": out, "commence": ev.get("commence_time")}


def fetch(date_et: str, api_key: str | None = None, max_games: int | None = None) -> dict:
    """Fetch the day's props inside the budget and write data/nhlprops/odds.json. Returns the file's content."""
    key = api_key or os.environ.get("ODDS_API_KEY")
    if not key:
        return load()
    events, rem = _get(BASE + "/events", {"apiKey": key})
    if events is None:
        return load()
    todays = []
    for ev in events:
        try:
            start = datetime.fromisoformat(str(ev.get("commence_time", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if start.astimezone(ZoneInfo("America/Toronto")).strftime("%Y-%m-%d") == date_et:
            todays.append((start, ev))
    todays.sort(key=lambda x: x[0])
    prev = load()
    same_day = prev.get("date") == date_et
    games = dict(prev.get("games", {})) if same_day else {}
    spent_before = int(prev.get("spent", 0) or 0) if same_day else 0
    allowance = max(0, daily_allowance(rem + spent_before if rem is not None else None) - spent_before)   # one allowance per day across runs
    spent = 0
    print(f"  nhl props: {len(todays)} games today, {rem} credits left this month, allowance {allowance}")
    for start, ev in todays[: (max_games or len(todays))]:
        home, away = _abbrev(ev.get("home_team", "")), _abbrev(ev.get("away_team", ""))
        if not home or not away:
            continue
        gkey = f"{away}@{home}"
        have = set(k for k, v in (games.get(gkey, {}).get("markets") or {}).items() if v)
        want = [m for m in PRIORITY if SLOT[m] not in have]
        # spread the day's allowance across the slate: the same number of markets for every game, highest priority first
        per_game = max(1, allowance // max(1, len(todays)))
        n = min(len(want), per_game, allowance - spent)
        if n <= 0:
            break
        markets = want[:n]
        data, rem = _get(f"{BASE}/events/{ev['id']}/odds", {"apiKey": key, "regions": REGIONS, "markets": ",".join(markets), "oddsFormat": "decimal"})
        spent += len(markets)
        if data is None:
            continue
        parsed = parse_event(data)
        parsed["fetched_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        parsed["requested"] = markets
        old = games.get(gkey, {})
        merged = {**old, **{k: v for k, v in parsed.items() if k != "markets"}}
        mk = dict(old.get("markets", {}))
        for s, v in parsed["markets"].items():
            if v:
                mk[s] = v
        merged["markets"] = mk
        games[gkey] = merged
        with HISTORY.open("a") as f:
            f.write(json.dumps({"date": date_et, "game": gkey, "fetched_utc": parsed["fetched_utc"], "markets": parsed["markets"]}) + "\n")
    out = {"date": date_et, "credits_remaining": rem, "updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "games": games, "spent": spent_before + spent}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ODDS_FILE.write_text(json.dumps(out, indent=1))
    print(f"  nhl props: {spent} credits spent on {len(games)} games, {rem} left")
    return out


def load() -> dict:
    if ODDS_FILE.exists():
        try:
            return json.loads(ODDS_FILE.read_text())
        except json.JSONDecodeError:
            pass
    return {}


def for_game(odds: dict, home: str, away: str, date_et: str) -> dict | None:
    if odds.get("date") != date_et:
        return None
    return odds.get("games", {}).get(f"{away}@{home}")


__all__ = ["fetch", "load", "for_game", "parse_event", "name_key", "daily_allowance", "PRIORITY", "SLOT"]
