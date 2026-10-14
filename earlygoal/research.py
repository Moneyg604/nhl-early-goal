"""Research dossier for each game and for the slate: everything the protocol asks for that the data can
actually measure, with sample sizes, plus an explicit list of what it cannot measure.

The dossier is informational. Only factors that improved the walk-forward backtest feed the model; the
rest are shown so the reader can see them, and labelled as such.
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field

from .features import mutual_fatigue
from .ingest import GameRecord

# What the protocol asks for that this data set does not carry. Stated on every page.
NOT_MEASURED = [
    "shot location, expected goals, high-danger and rush/rebound chances (no coordinates in the play-by-play feed used)",
    "forward lines, defence pairs, opening-shift deployment and matchup assignments",
    "injuries, scratches, suspensions and warm-up absences",
    "officials",
    "coaching or tactical changes",
    "market prices (type your book's price into the price check)",
]

# How each research factor is treated. 'model' = feeds the hazard; 'validated' = measured and shown to
# beat the league constant out of sample; 'shown' = measured and displayed, not used; 'unavailable'.
FACTOR_STATUS = [
    ("Early goals for / against, first 5 and first 10 (both teams, two seasons + current)", "model"),
    ("Early shots on goal for / against, first 10 (opponent-adjusted through the opponent's suppression term)", "model"),
    ("Finishing (shooting %), shrunk toward the league", "model"),
    ("Starting goalie save %, shrunk; first-10-minute save % and last-5-start form shown", "model"),
    ("Confirmed vs projected starter (DailyFaceoff, with the reporter who confirmed)", "model"),
    ("Home ice", "model"),
    ("Back-to-back, 3-in-4, travel distance, time zones, rest edge (each side)", "model"),
    ("Both teams on a back-to-back or 3-in-4 (mutual fatigue, first 10 minutes)", "validated"),
    ("Time to first shot and first goal, games with no shot in the first 5", "shown"),
    ("Early penalties taken and drawn (first 10)", "shown"),
    ("Head-to-head meetings: first-goal time, early shots, goalies", "shown"),
    ("Goalie workload: last start, shots faced, consecutive starts, started last night", "shown"),
    ("Previous game went to overtime or a shootout", "shown"),
    ("League base rates by season (first 5 / first 10)", "model"),
    ("Shot attempts, Fenwick, xG, high-danger chances, shot location", "unavailable"),
    ("Lines, pairs, opening deployment, scratches, injuries, officials, coaching", "unavailable"),
]


def _first(events, pred):
    for e in events:
        if pred(e):
            return e.minute
    return None


@dataclass
class ResearchIndex:
    by_team: dict = field(default_factory=lambda: defaultdict(list))        # team -> [GameRecord] by date
    by_goalie: dict = field(default_factory=lambda: defaultdict(list))      # goalie id -> [(date, game_id, team, shots, goals_against)]
    names: dict = field(default_factory=dict)
    schedule_rates: dict = field(default_factory=dict)                        # mutual fatigue table, all seasons
    base_rates: dict = field(default_factory=dict)                            # season -> {games, no_goal_5, no_goal_10}


def build_index(records: list[GameRecord]) -> ResearchIndex:
    ix = ResearchIndex()
    recs = sorted([g for g in records if g.final], key=lambda g: (g.date, g.game_id))
    tab = defaultdict(lambda: [0, 0, 0])
    for g in recs:
        ix.by_team[g.home].append(g)
        ix.by_team[g.away].append(g)
        ix.names.update(g.goalie_names or {})
        for side in ("home", "away"):
            gid = (g.starters or {}).get(side)
            if not gid:
                continue
            team = g.home if side == "home" else g.away
            shots = sum(1 for e in g.events if e.goalie == gid and e.type in ("shot-on-goal", "goal") and e.minute < 60)
            ga = sum(1 for e in g.events if e.goalie == gid and e.type == "goal" and e.minute < 60)
            ix.by_goalie[gid].append((g.date, g.game_id, team, shots, ga))
        goals = [e.minute for e in g.events if e.type == "goal" and e.minute < 65]
        fg = min(goals) if goals else None
        r = g.rest or {}
        rh, ra = r.get("home") or {}, r.get("away") or {}
        if rh and ra:
            k = "both" if mutual_fatigue(rh, ra) else ("one" if (rh.get("b2b") or ra.get("b2b") or rh.get("three_in_four") or ra.get("three_in_four")) else "neither")
            t = tab[k]
            t[0] += 1
            t[1] += fg is None or fg >= 5
            t[2] += fg is None or fg >= 10
        b = ix.base_rates.setdefault(g.season, [0, 0, 0])
        b[0] += 1
        b[1] += fg is None or fg >= 5
        b[2] += fg is None or fg >= 10
    ix.schedule_rates = {k: {"games": n, "no_goal_5": round(a / n, 4) if n else None, "no_goal_10": round(b / n, 4) if n else None} for k, (n, a, b) in tab.items()}
    ix.base_rates = {str(s): {"games": n, "no_goal_5": round(a / n, 4), "no_goal_10": round(b / n, 4)} for s, (n, a, b) in sorted(ix.base_rates.items())}
    return ix


def _early_block(g: GameRecord, team: str) -> dict:
    opp = g.away if g.home == team else g.home
    ev = sorted(g.events, key=lambda e: e.minute)
    goals = [e for e in ev if e.type == "goal" and e.minute < 65]
    fg = goals[0].minute if goals else None
    gf, ga = (g.home_score, g.away_score) if g.home == team else (g.away_score, g.home_score)
    return {
        "date": g.date, "home": g.home, "away": g.away, "opp": opp, "venue_home": g.home == team,
        "score": f"{g.away_score}-{g.home_score}",
        "result": f"{'W' if gf > ga else 'L'} {gf}-{ga}",
        "first_goal_min": None if fg is None else round(fg, 2),
        "first_goal_team": goals[0].team if goals else None,
        "goal_5": bool(fg is not None and fg < 5), "goal_10": bool(fg is not None and fg < 10),
        "team_scored_5": any(e.team == team and e.minute < 5 for e in goals),
        "team_conceded_5": any(e.team != team and e.minute < 5 for e in goals),
        "sog10_for": sum(1 for e in ev if e.team == team and e.type in ("shot-on-goal", "goal") and e.minute < 10),
        "sog10_against": sum(1 for e in ev if e.team != team and e.type in ("shot-on-goal", "goal") and e.minute < 10),
        "first_sog_for": _first(ev, lambda e: e.team == team and e.type in ("shot-on-goal", "goal")),
        "first_sog_against": _first(ev, lambda e: e.team != team and e.type in ("shot-on-goal", "goal")),
        "pen_taken_10": sum(1 for e in ev if e.team == team and e.type == "penalty" and e.minute < 10),
        "pen_drawn_10": sum(1 for e in ev if e.team != team and e.type == "penalty" and e.minute < 10),
        "ended_in": g.ended_in,
        "goalies": {"home": (g.goalie_names or {}).get(str((g.starters or {}).get("home")), ""), "away": (g.goalie_names or {}).get(str((g.starters or {}).get("away")), "")},
    }


def team_timing(ix: ResearchIndex, team: str, date: str, season: int) -> dict:
    """Early-window behaviour of one team, this season and last, from timestamped events."""
    out = {}
    for label, pred in (("this_season", lambda g: g.season == season), ("last_season", lambda g: g.season == season - 10001)):
        games = [g for g in ix.by_team.get(team, []) if g.date < date and pred(g)]
        blocks = [_early_block(g, team) for g in games]
        n = len(blocks)
        if not n:
            out[label] = {"games": 0}
            continue
        fs_for = [b["first_sog_for"] for b in blocks if b["first_sog_for"] is not None]
        fs_ag = [b["first_sog_against"] for b in blocks if b["first_sog_against"] is not None]
        out[label] = {
            "games": n,
            "goal_in_5_share": round(sum(b["goal_5"] for b in blocks) / n, 3),
            "goal_in_10_share": round(sum(b["goal_10"] for b in blocks) / n, 3),
            "scored_in_5_share": round(sum(b["team_scored_5"] for b in blocks) / n, 3),
            "conceded_in_5_share": round(sum(b["team_conceded_5"] for b in blocks) / n, 3),
            "sog10_for_pg": round(sum(b["sog10_for"] for b in blocks) / n, 2),
            "sog10_against_pg": round(sum(b["sog10_against"] for b in blocks) / n, 2),
            "median_first_sog_for": round(statistics.median(fs_for), 2) if fs_for else None,
            "median_first_sog_against": round(statistics.median(fs_ag), 2) if fs_ag else None,
            "no_sog_first5_share": round(sum(1 for b in blocks if b["first_sog_for"] is None or b["first_sog_for"] >= 5) / n, 3),
            "pen_taken_10_pg": round(sum(b["pen_taken_10"] for b in blocks) / n, 2),
            "pen_drawn_10_pg": round(sum(b["pen_drawn_10"] for b in blocks) / n, 2),
            "home_goal_in_5_share": _share([b for b in blocks if b["venue_home"]], "goal_5"),
            "away_goal_in_5_share": _share([b for b in blocks if not b["venue_home"]], "goal_5"),
        }
    recent = [_early_block(g, team) for g in ix.by_team.get(team, []) if g.date < date][-6:]
    out["recent"] = [{"date": b["date"], "opp": b["opp"], "home": b["venue_home"], "score": b["score"], "result": b["result"], "first_goal_min": b["first_goal_min"],
                      "first_goal_team": b["first_goal_team"], "sog10_for": b["sog10_for"], "sog10_against": b["sog10_against"], "ended_in": b["ended_in"]} for b in recent]
    prev = recent[-1] if recent else None
    out["previous_game"] = None if prev is None else {"date": prev["date"], "opp": prev["opp"], "ended_in": prev["ended_in"], "score": prev["score"], "result": prev["result"]}
    return out


def _share(blocks, key):
    return round(sum(b[key] for b in blocks) / len(blocks), 3) if blocks else None


def head_to_head(ix: ResearchIndex, home: str, away: str, date: str, n: int = 6) -> dict:
    meets = [g for g in ix.by_team.get(home, []) if g.date < date and {g.home, g.away} == {home, away}][-n:]
    rows = []
    for g in meets:
        b = _early_block(g, home)
        rows.append({"date": b["date"], "home": g.home, "away": g.away, "score": b["score"], "first_goal_min": b["first_goal_min"], "first_goal_team": b["first_goal_team"],
                     "goal_5": b["goal_5"], "goal_10": b["goal_10"], "sog10_home": b["sog10_for"] if g.home == home else b["sog10_against"],
                     "sog10_away": b["sog10_against"] if g.home == home else b["sog10_for"], "goalies": b["goalies"], "ended_in": b["ended_in"]})
    return {"meetings": rows, "n": len(rows), "no_goal_5": sum(1 for r in rows if not r["goal_5"]), "no_goal_10": sum(1 for r in rows if not r["goal_10"])}


def goalie_workload(ix: ResearchIndex, goalie_id: int | None, team: str, date: str) -> dict | None:
    if not goalie_id:
        return None
    starts = [s for s in ix.by_goalie.get(goalie_id, []) if s[0] < date]
    if not starts:
        return {"starts_on_record": 0}
    from datetime import datetime

    last = starts[-1]
    d0 = datetime.fromisoformat(date)
    days_since = (d0 - datetime.fromisoformat(last[0])).days
    team_games = [g for g in ix.by_team.get(team, []) if g.date < date]
    consec = 0
    for g in reversed(team_games):
        side = "home" if g.home == team else "away"
        if (g.starters or {}).get(side) == goalie_id:
            consec += 1
        else:
            break
    last7 = sum(1 for s in starts if (d0 - datetime.fromisoformat(s[0])).days <= 7)
    return {
        "starts_on_record": len(starts),
        "last_start": last[0], "days_since_last_start": days_since, "started_last_night": days_since == 1,
        "shots_faced_last_start": last[3], "goals_against_last_start": last[4],
        "consecutive_team_starts": consec, "starts_last_7_days": last7,
        "shots_faced_last_3": [s[3] for s in starts[-3:]],
    }


def game_research(ix: ResearchIndex, game: dict, sides: dict, season: int, lp_context_mults: dict) -> dict:
    """Everything measurable about one matchup, for the page. `sides` maps 'home'/'away' to SideInputs."""
    date, home, away = game["date"], game["home"], game["away"]
    rest = {k: (sides[k].rest or {}) for k in ("home", "away")}
    mf = mutual_fatigue(rest["home"], rest["away"])
    sched = {
        k: {"days_rest": rest[k].get("days_rest"), "b2b": bool(rest[k].get("b2b")), "three_in_four": bool(rest[k].get("three_in_four")),
            "games_last_7d": rest[k].get("games_last_7d"), "travel_km": rest[k].get("travel_km"), "tz_shift": rest[k].get("tz_shift"),
            "prev_opponent": rest[k].get("prev_opponent"), "prev_date": rest[k].get("prev_date")}
        for k in ("home", "away")
    }
    return {
        "h2h": head_to_head(ix, home, away, date),
        "timing": {"home": team_timing(ix, home, date, season), "away": team_timing(ix, away, date, season)},
        "goalie_workload": {k: goalie_workload(ix, getattr(sides[k].goalie, "goalie_id", None) if sides[k].goalie else None, sides[k].team, date) for k in ("home", "away")},
        "schedule": {**sched, "mutual_fatigue": mf, "mutual_fatigue_mult": round(lp_context_mults.get("mutual_fatigue_early", 1.0), 4),
                     "league_rates": ix.schedule_rates},
        "not_measured": NOT_MEASURED,
    }


def slate_research(ix: ResearchIndex, lp_context_mults: dict, lp_context_samples: dict, meta: dict) -> dict:
    return {
        "factors": [{"factor": f, "status": s} for f, s in FACTOR_STATUS],
        "base_rates_by_season": ix.base_rates,
        "schedule_rates": ix.schedule_rates,
        "context_effects": {k: round(v, 4) for k, v in (lp_context_mults or {}).items()},
        "context_samples": lp_context_samples or {},
        "not_measured": NOT_MEASURED,
        "sources": {
            "play_by_play": "sportsdataverse nightly release of the NHL play-by-play feed (shots, goals, penalties, timestamps, strength, starters)",
            "schedule": "NHL API schedule (rest, travel and time zones derived from it)",
            "goalies": "DailyFaceoff starting-goalies page, parsed with the reporter and time of each confirmation",
            "data_through": meta.get("data_through"),
        },
    }
