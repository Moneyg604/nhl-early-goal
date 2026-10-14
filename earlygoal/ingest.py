"""Ingestion: turn NHL play-by-play documents into compact per-game records.

The records are the only thing the feature layer reads, so the shape is
deliberately simple and stored as JSON lines under data/games_<season>.jsonl.

Per game we keep every goal, shot on goal, missed shot and penalty with its
absolute minute of the game (0-60 for regulation, 60+ for OT), the owning
team, the situation code and (for shots/goals) the goalie in net. That is
enough to rebuild early-scoring rates, shot pace, finishing, goalie quality,
early penalty tendencies and starting goalies without touching the API again.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .arenas import ARENAS, TEAM_ID_TO_ABBREV, travel_between
from .config import CFG, DATA_DIR
from .nhl_api import NHLClient, NHLUnavailable, mmss_to_minutes

FINAL_STATES = {"OFF", "FINAL"}
EVENT_TYPES = {"goal", "shot-on-goal", "missed-shot", "penalty"}


@dataclass
class Event:
    minute: float          # absolute minute of game (period 1 starts at 0)
    period: int
    type: str              # goal | shot-on-goal | missed-shot | penalty
    team: str              # abbrev of event owner
    goalie: int | None     # goalie in net (opponent's) for shots/goals
    situation: str         # e.g. "1551" (away goalie, away skaters, home skaters, home goalie)
    strength: str          # EV | PP | SH from the owner's perspective
    duration: int = 0      # penalty minutes, penalties only


@dataclass
class GameRecord:
    game_id: int
    season: int
    date: str
    start_utc: str
    home: str
    away: str
    venue: str
    final: bool
    home_score: int
    away_score: int
    ended_in: str          # REG | OT | SO | ""
    starters: dict         # {"home": goalie_id, "away": goalie_id}
    goalie_names: dict     # {goalie_id: "First Last"}
    events: list = field(default_factory=list)
    # context, filled from club schedules
    rest: dict = field(default_factory=dict)      # {"home": {...}, "away": {...}}

    def to_json(self) -> str:
        d = asdict(self)
        d["events"] = [asdict(e) if isinstance(e, Event) else e for e in self.events]
        return json.dumps(d)

    @staticmethod
    def from_json(line: str) -> "GameRecord":
        d = json.loads(line)
        d["events"] = [Event(**e) for e in d["events"]]
        return GameRecord(**d)


def _strength(situation: str, owner_is_home: bool) -> str:
    """situationCode 'ABCD' = away goalie, away skaters, home skaters, home goalie."""
    if not situation or len(situation) != 4 or not situation.isdigit():
        return "EV"
    away_sk, home_sk = int(situation[1]), int(situation[2])
    own, opp = (home_sk, away_sk) if owner_is_home else (away_sk, home_sk)
    if own > opp:
        return "PP"
    if own < opp:
        return "SH"
    return "EV"


def parse_play_by_play(pbp: dict) -> GameRecord | None:
    state = pbp.get("gameState", "")
    home = pbp["homeTeam"]
    away = pbp["awayTeam"]
    home_ab, away_ab = home["abbrev"], away["abbrev"]
    home_id, away_id = home["id"], away["id"]
    id_to_ab = {home_id: home_ab, away_id: away_ab}

    goalie_names: dict[int, str] = {}
    for spot in pbp.get("rosterSpots", []):
        if spot.get("positionCode") == "G":
            goalie_names[spot["playerId"]] = f"{spot.get('firstName', {}).get('default', '')} {spot.get('lastName', {}).get('default', '')}".strip()

    events: list[Event] = []
    starters: dict[str, int | None] = {"home": None, "away": None}
    for p in pbp.get("plays", []):
        t = p.get("typeDescKey")
        if t not in EVENT_TYPES:
            continue
        pd = p.get("periodDescriptor", {})
        ptype = pd.get("periodType", "REG")
        if ptype == "SO":
            continue
        period = int(pd.get("number", 1))
        minute = (period - 1) * 20 + mmss_to_minutes(p.get("timeInPeriod", "00:00"))
        d = p.get("details", {})
        owner_id = d.get("eventOwnerTeamId")
        owner = id_to_ab.get(owner_id)
        if owner is None:
            continue
        goalie = d.get("goalieInNetId")
        ev = Event(
            minute=round(minute, 4),
            period=period,
            type=t,
            team=owner,
            goalie=goalie,
            situation=str(p.get("situationCode", "")),
            strength=_strength(str(p.get("situationCode", "")), owner == home_ab),
            duration=int(d.get("duration", 0) or 0) if t == "penalty" else 0,
        )
        events.append(ev)
        # starting goalie = first goalie seen in net for each side
        if goalie and t in ("goal", "shot-on-goal"):
            side = "away" if owner == home_ab else "home"
            if starters[side] is None:
                starters[side] = goalie

    outcome = pbp.get("gameOutcome", {}) or {}
    ended_in = outcome.get("lastPeriodType", "") if state in FINAL_STATES else ""
    venue_ab = home_ab  # neutral-site games are rare; treat venue as home arena
    return GameRecord(
        game_id=pbp["id"],
        season=int(pbp["season"]),
        date=pbp.get("gameDate", ""),
        start_utc=pbp.get("startTimeUTC", ""),
        home=home_ab,
        away=away_ab,
        venue=venue_ab,
        final=state in FINAL_STATES,
        home_score=int(home.get("score", 0) or 0),
        away_score=int(away.get("score", 0) or 0),
        ended_in=ended_in,
        starters=starters,
        goalie_names={str(k): v for k, v in goalie_names.items()},
        events=events,
    )


# ---------------------------------------------------------------- schedules

def team_game_list(client: NHLClient, team: str, season: int, force: bool = False) -> list[dict]:
    """Ordered regular-season games for one team with venue + date."""
    out = []
    for g in client.club_schedule(team, season, force=force):
        if g.get("gameType") != 2:  # regular season only
            continue
        out.append(
            {
                "game_id": g["id"],
                "date": g["gameDate"],
                "start_utc": g.get("startTimeUTC", ""),
                "home": g["homeTeam"]["abbrev"],
                "away": g["awayTeam"]["abbrev"],
                "state": g.get("gameState", ""),
            }
        )
    out.sort(key=lambda x: (x["date"], x["game_id"]))
    return out


def rest_context(team_games: list[dict], idx: int, team: str) -> dict:
    """Rest/travel context for team_games[idx] from the team's own schedule."""
    g = team_games[idx]
    when = datetime.fromisoformat(g["start_utc"].replace("Z", "+00:00")) if g["start_utc"] else datetime.now(timezone.utc)
    venue_now = g["home"]
    if idx == 0:
        return {"days_rest": None, "b2b": False, "three_in_four": False, "travel_km": 0.0, "tz_shift": 0, "games_last_7d": 0, "season_game_no": 1}
    prev = team_games[idx - 1]
    d_now = datetime.fromisoformat(g["date"])
    d_prev = datetime.fromisoformat(prev["date"])
    days = (d_now - d_prev).days
    km, tz = travel_between(prev["home"], venue_now, when)
    three_in_four = idx >= 2 and (d_now - datetime.fromisoformat(team_games[idx - 2]["date"])).days <= 3
    last7 = sum(1 for k in range(max(0, idx - 6), idx) if (d_now - datetime.fromisoformat(team_games[k]["date"])).days <= 7)
    return {
        "days_rest": days - 1,              # 0 = back-to-back
        "b2b": days == 1,
        "three_in_four": bool(three_in_four),
        "travel_km": round(km, 1),
        "tz_shift": tz,
        "games_last_7d": last7,
        "season_game_no": idx + 1,
        "prev_opponent": prev["away"] if prev["home"] == team else prev["home"],
        "prev_date": prev["date"],
    }


def build_schedule_index(client: NHLClient, season: int, force: bool = False) -> dict[int, dict]:
    """game_id -> {'home': {...rest}, 'away': {...rest}} for every regular-season game."""
    index: dict[int, dict] = {}
    for team in ARENAS:
        try:
            games = team_game_list(client, team, season, force=force)
        except NHLUnavailable:
            raise
        except Exception as e:  # noqa: BLE001
            print(f"  ! club schedule {team} {season}: {e}", file=sys.stderr)
            continue
        for i, g in enumerate(games):
            side = "home" if g["home"] == team else "away"
            index.setdefault(g["game_id"], {"date": g["date"], "home": g["home"], "away": g["away"], "state": g["state"], "start_utc": g["start_utc"]})
            index[g["game_id"]][side] = rest_context(games, i, team)
    return index


# ------------------------------------------------------------------ driver

def games_file(season: int) -> Path:
    return DATA_DIR / f"games_{season}.jsonl"


def load_games(season: int) -> list[GameRecord]:
    f = games_file(season)
    if not f.exists():
        return []
    with f.open() as fh:
        return [GameRecord.from_json(line) for line in fh if line.strip()]


def ingest_season(client: NHLClient, season: int, up_to_date: str | None = None, verbose: bool = True, force_schedule: bool = False) -> list[GameRecord]:
    """Fetch every final regular-season game of `season` (cached) and write records."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    index = build_schedule_index(client, season, force=force_schedule)
    existing = {g.game_id: g for g in load_games(season)}
    records: list[GameRecord] = []
    ids = sorted(index)
    n_new = 0
    for i, gid in enumerate(ids):
        meta = index[gid]
        if up_to_date and meta["date"] >= up_to_date:
            continue
        if gid in existing and existing[gid].final:
            records.append(existing[gid])
            continue
        if meta.get("state") not in FINAL_STATES:
            continue
        try:
            pbp = client.play_by_play(gid, final=True)
        except Exception as e:  # noqa: BLE001
            print(f"  ! pbp {gid}: {e}", file=sys.stderr)
            continue
        rec = parse_play_by_play(pbp)
        if rec is None or not rec.final:
            continue
        rec.rest = {"home": meta.get("home", {}), "away": meta.get("away", {})}
        records.append(rec)
        n_new += 1
        if verbose and n_new % 50 == 0:
            print(f"  {season}: {n_new} new games parsed ({i + 1}/{len(ids)} scanned)")
    records.sort(key=lambda r: (r.date, r.game_id))
    with games_file(season).open("w") as fh:
        for r in records:
            fh.write(r.to_json() + "\n")
    if verbose:
        print(f"  {season}: {len(records)} final games on disk ({n_new} new)")
    return records


def slate_for_date(client: NHLClient, date: str, force: bool = False) -> list[dict]:
    """Today's games with rest/travel context for both sides."""
    games = client.schedule(date, force=force)
    season = int(games[0]["season"]) if games else None
    slate = []
    sched_index = build_schedule_index(client, season) if season else {}
    for g in games:
        if g.get("gameType") != 2:
            continue
        gid = g["id"]
        ctx = sched_index.get(gid, {})
        slate.append(
            {
                "game_id": gid,
                "season": season,
                "date": date,
                "start_utc": g.get("startTimeUTC", ""),
                "home": g["homeTeam"]["abbrev"],
                "away": g["awayTeam"]["abbrev"],
                "home_id": g["homeTeam"]["id"],
                "away_id": g["awayTeam"]["id"],
                "venue": (g.get("venue") or {}).get("default", ""),
                "state": g.get("gameState", ""),
                "rest": {"home": ctx.get("home", {}), "away": ctx.get("away", {})},
            }
        )
    return slate
