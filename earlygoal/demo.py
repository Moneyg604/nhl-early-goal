"""Synthetic data for exercising the full pipeline without network access.

Produces GameRecords with the same shape the ingestion layer writes, from a
generated league with team strengths and goalies. Nothing here is real
hockey data; the dashboard shows a DEMO banner whenever it is used.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta

from .arenas import ARENAS, ALL_TEAMS
from .ingest import Event, GameRecord, rest_context

# Real slate for 2026-10-13 (ids and start times from the NHL schedule API)
SLATE_2026_10_13 = [
    (2026020090, "NJD", "DET", "2026-10-13T22:00:00Z"), (2026020091, "FLA", "CBJ", "2026-10-13T22:15:00Z"),
    (2026020092, "BUF", "MTL", "2026-10-13T22:30:00Z"), (2026020093, "WSH", "CAR", "2026-10-13T22:45:00Z"),
    (2026020094, "SEA", "PHI", "2026-10-13T23:00:00Z"), (2026020095, "TBL", "NYR", "2026-10-13T23:15:00Z"),
    (2026020096, "STL", "OTT", "2026-10-13T23:30:00Z"), (2026020097, "VAN", "NYI", "2026-10-13T23:45:00Z"),
    (2026020098, "PIT", "CHI", "2026-10-14T00:00:00Z"), (2026020099, "MIN", "WPG", "2026-10-14T00:15:00Z"),
    (2026020100, "COL", "DAL", "2026-10-14T00:30:00Z"), (2026020101, "VGK", "NSH", "2026-10-14T00:45:00Z"),
    (2026020102, "TOR", "UTA", "2026-10-14T01:00:00Z"), (2026020103, "CGY", "ANA", "2026-10-14T01:45:00Z"),
    (2026020104, "EDM", "LAK", "2026-10-14T02:30:00Z"), (2026020105, "BOS", "SJS", "2026-10-14T03:00:00Z"),
]

FIRST_NAMES = ["Igor", "Connor", "Jake", "Juuse", "Linus", "Ilya", "Jeremy", "Andrei", "Thatcher", "Sergei", "Jacob", "Stuart",
               "Logan", "Joey", "Filip", "Adin", "Jordan", "Darcy", "Sam", "Ukko", "Lukas", "Jet", "Karel", "Dustin",
               "Vitek", "John", "Alex", "Anthony", "Cam", "Tristan", "Spencer", "Pyotr"]
LAST_NAMES = ["Sheshkin", "Hellbuck", "Oettingar", "Sarsos", "Ullmark", "Sorokov", "Swaymen", "Vasilenko", "Demkov", "Bobrovsk",
              "Markstrand", "Skinnar", "Thompsen", "Daccard", "Gustavsen", "Hillson", "Binningt", "Kuempf", "Montembo", "Luukko",
              "Dostall", "Greaver", "Vejmelk", "Wolfe", "Vanecek", "Gibsonn", "Nedeljko", "Stolarz", "Talbott", "Jarrie",
              "Knightly", "Kochet"]


def _synthetic_league(seed: int) -> dict:
    rng = random.Random(seed)
    teams = {}
    goalie_id = 8470000
    for i, t in enumerate(ALL_TEAMS):
        off = rng.lognormvariate(0.0, 0.10)
        dfn = rng.lognormvariate(0.0, 0.10)
        early = rng.lognormvariate(0.0, 0.12)   # early-game tempo quirk
        g1 = {"id": goalie_id, "name": f"{FIRST_NAMES[i]} {LAST_NAMES[i]}", "sv": min(0.93, max(0.885, rng.gauss(0.907, 0.009))), "share": rng.uniform(0.55, 0.72)}
        g2 = {"id": goalie_id + 1, "name": f"{FIRST_NAMES[(i + 7) % 32]} {LAST_NAMES[(i + 13) % 32]}", "sv": min(0.925, max(0.880, rng.gauss(0.899, 0.009))), "share": 0.0}
        goalie_id += 2
        teams[t] = {"off": off, "def": dfn, "early": early, "goalies": [g1, g2]}
    return teams


def _simulate_game(rng: random.Random, league: dict, gid: int, date: str, start_utc: str, home: str, away: str, starters: dict) -> GameRecord:
    th, ta = league[home], league[away]
    gh = next(g for g in th["goalies"] if g["id"] == starters["home"])
    ga = next(g for g in ta["goalies"] if g["id"] == starters["away"])
    events: list[Event] = []
    score = {home: 0, away: 0}
    for minute in range(60):
        for team, opp, goalie_opp, is_home in ((home, away, ga, True), (away, home, gh, False)):
            # shots on goal per minute ~ 0.5, early minutes slower, home edge
            base = 0.50 * (1.04 if is_home else 0.96)
            if minute < 2:
                base *= 0.65 * league[team]["early"]
            elif minute < 10:
                base *= 0.88 * league[team]["early"]
            lam_sog = base * league[team]["off"] * league[opp]["def"]
            n_sog = rng_poisson(rng, lam_sog)
            n_miss = rng_poisson(rng, lam_sog * 0.45)
            diff = score[team] - score[opp]
            for _ in range(n_sog):
                t = minute + rng.random()
                p_goal = (1 - goalie_opp["sv"])
                if minute >= 58 and diff in (1, 2):
                    p_goal = 0.30   # empty net on the other end
                if minute >= 58 and diff in (-1, -2):
                    p_goal *= 1.5
                goal = rng.random() < p_goal
                events.append(Event(round(t, 4), minute // 20 + 1, "goal" if goal else "shot-on-goal", team, goalie_opp["id"], "1551", "EV"))
                if goal:
                    score[team] += 1
            for _ in range(n_miss):
                events.append(Event(round(minute + rng.random(), 4), minute // 20 + 1, "missed-shot", team, goalie_opp["id"], "1551", "EV"))
            if rng.random() < 0.055:
                events.append(Event(round(minute + rng.random(), 4), minute // 20 + 1, "penalty", team, None, "1551", "EV", 2))
    ended = "REG"
    if score[home] == score[away]:
        if rng.random() < 0.68:
            ended = "OT"
            winner = home if rng.random() < 0.5 else away
            events.append(Event(round(60 + rng.uniform(0, 5), 4), 4, "goal", winner, (ga if winner == home else gh)["id"], "1331", "EV"))
            score[winner] += 1
        else:
            ended = "SO"
            winner = home if rng.random() < 0.5 else away
            score[winner] += 1
    events.sort(key=lambda e: e.minute)
    names = {str(g["id"]): g["name"] for g in th["goalies"] + ta["goalies"]}
    return GameRecord(gid, 0, date, start_utc, home, away, home, True, score[home], score[away], ended, dict(starters), names, events)


def rng_poisson(rng: random.Random, lam: float) -> int:
    l, k, p = pow(2.718281828, -lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def _random_schedule(rng: random.Random, start: datetime, days: int, games_per_day: int, gid0: int) -> list[tuple[int, str, str, str]]:
    sched = []
    gid = gid0
    for d in range(days):
        date = (start + timedelta(days=d)).strftime("%Y-%m-%d")
        pool = ALL_TEAMS[:]
        rng.shuffle(pool)
        n = min(games_per_day, len(pool) // 2)
        for i in range(n):
            away, home = pool[2 * i], pool[2 * i + 1]
            sched.append((gid, date, f"{date}T23:00:00Z", home, away))
            gid += 1
    return sched


def build_demo(seed: int = 7) -> tuple[list[GameRecord], list[GameRecord], list[dict], dict]:
    """Returns (prior_season_games, current_season_games, today's slate, league truth)."""
    rng = random.Random(seed)
    league = _synthetic_league(seed)

    def pick_starter(team: str, team_games_so_far: list[str], date: str) -> int:
        g1, g2 = league[team]["goalies"]
        yesterday = (datetime.fromisoformat(date) - timedelta(days=1)).strftime("%Y-%m-%d")
        if team_games_so_far and team_games_so_far[-1] == yesterday:
            return g2["id"] if rng.random() < 0.8 else g1["id"]
        return g1["id"] if rng.random() < g1["share"] + 0.2 else g2["id"]

    def run_season(sched: list, season: int) -> list[GameRecord]:
        recs = []
        played: dict[str, list[str]] = {t: [] for t in ALL_TEAMS}
        for gid, date, start, home, away in sched:
            starters = {"home": pick_starter(home, played[home], date), "away": pick_starter(away, played[away], date)}
            r = _simulate_game(rng, league, gid, date, start, home, away, starters)
            r.season = season
            recs.append(r)
            played[home].append(date)
            played[away].append(date)
        return recs

    prior_sched = _random_schedule(rng, datetime(2025, 10, 7), 180, 7, 2025020001)
    prior = run_season(prior_sched, 20252026)
    cur_sched = _random_schedule(rng, datetime(2026, 10, 7), 6, 8, 2026020001)
    current = run_season(cur_sched, 20262027)

    # rest/travel context from the synthetic schedules, same code path as production
    def attach_rest(recs: list[GameRecord], extra_future: list[dict]) -> None:
        by_team: dict[str, list[dict]] = {t: [] for t in ALL_TEAMS}
        entries = [{"game_id": r.game_id, "date": r.date, "start_utc": r.start_utc, "home": r.home, "away": r.away, "state": "OFF"} for r in recs] + extra_future
        for e in entries:
            by_team[e["home"]].append(e)
            by_team[e["away"]].append(e)
        ctx: dict[int, dict] = {}
        for t, games in by_team.items():
            games.sort(key=lambda x: (x["date"], x["game_id"]))
            for i, g in enumerate(games):
                side = "home" if g["home"] == t else "away"
                ctx.setdefault(g["game_id"], {})[side] = rest_context(games, i, t)
        for r in recs:
            r.rest = ctx.get(r.game_id, {})
        return ctx

    today = [{"game_id": gid, "date": "2026-10-13", "start_utc": start, "home": home, "away": away, "state": "FUT"} for gid, away, home, start in SLATE_2026_10_13]
    attach_rest(prior, [])
    ctx = attach_rest(current, today)
    slate = []
    for t in today:
        slate.append({**t, "season": 20262027, "home_id": ARENAS[t["home"]][0], "away_id": ARENAS[t["away"]][0], "venue": ARENAS[t["home"]][1], "rest": ctx.get(t["game_id"], {})})
    return prior, current, slate, league
