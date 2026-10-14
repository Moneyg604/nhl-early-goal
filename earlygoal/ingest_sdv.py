"""Second data source: sportsdataverse's nightly NHL play-by-play releases.

The sportsdataverse project republishes the NHL API play-by-play as one
parquet per season (`play_by_play_lite_<endYear>.parquet`, ~20 MB), updated
daily. Three downloads replace ~1,300 API requests, and the current-season
file is refreshed through the previous night, so this is the default source.
The NHL API path (ingest.py) remains for games the release has not caught up
with yet and for today's schedule.

Release: https://github.com/sportsdataverse/sportsdataverse-data/releases/tag/nhl_pbp_lite
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .arenas import ALL_TEAMS
from .config import DATA_DIR
from .ingest import Event, GameRecord, games_file, rest_context

SDV_URL = "https://github.com/sportsdataverse/sportsdataverse-data/releases/download/nhl_pbp_lite/play_by_play_lite_{end_year}.parquet"
TYPE_MAP = {"GOAL": "goal", "SHOT": "shot-on-goal", "MISSED_SHOT": "missed-shot", "PENALTY": "penalty"}


def sdv_path(season: int) -> Path:
    end_year = season % 10000
    return DATA_DIR / "sdv" / f"play_by_play_lite_{end_year}.parquet"


def download_sdv(season: int, max_age_hours: float = 6.0, force: bool = False, is_current: bool = True) -> Path:
    """Download (or reuse) the season parquet. A current season is refreshed when older than max_age_hours;
    a finished season is never re-downloaded unless forced."""
    import requests  # type: ignore

    p = sdv_path(season)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists() and not force:
        age_h = (time.time() - p.stat().st_mtime) / 3600
        if not is_current or age_h < max_age_hours:
            return p
    url = SDV_URL.format(end_year=season % 10000)
    r = requests.get(url, timeout=300, stream=True)
    if r.status_code == 404:
        if p.exists():
            return p
        raise FileNotFoundError(f"no sportsdataverse file for season {season}: {url}")
    r.raise_for_status()
    tmp = p.with_suffix(".tmp")
    with tmp.open("wb") as f:
        for chunk in r.iter_content(1 << 20):
            f.write(chunk)
    tmp.replace(p)
    return p


def _situation(home_sk: int, away_sk: int, home_in: int, away_in: int) -> str:
    return f"{int(away_in)}{int(away_sk)}{int(home_sk)}{int(home_in)}"


def load_sdv(path: Path, regular_only: bool = True) -> list[GameRecord]:
    """Convert a sportsdataverse lite parquet into GameRecords (final games only)."""
    import pandas as pd

    cols = ["game_id", "season", "season_type", "game_date", "home_abbr", "away_abbr", "event_type", "period", "period_type",
            "game_seconds", "event_team_abbr", "event_goalie_id", "event_goalie_name", "strength_state", "penalty_minutes",
            "home_skaters", "away_skaters", "home_goalie_in", "away_goalie_in", "home_goalie_id", "away_goalie_id",
            "home_goalie", "away_goalie", "home_score", "away_score"]
    df = pd.read_parquet(path, columns=cols)
    if regular_only:
        df = df[df.season_type == "R"]
    df = df.sort_values(["game_id", "game_seconds"], kind="stable")
    records: list[GameRecord] = []
    for gid, g in df.groupby("game_id", sort=True):
        if not (g.event_type == "GAME_END").any():
            continue  # not final
        home, away = g.home_abbr.iloc[0], g.away_abbr.iloc[0]
        season = int(g.season.iloc[0])
        date = str(g.game_date.iloc[0])[:10]
        goalie_names: dict[str, str] = {}
        for hid, hn, aid, an in zip(g.home_goalie_id, g.home_goalie, g.away_goalie_id, g.away_goalie):
            if pd.notna(hid) and hn:
                goalie_names[str(int(hid))] = str(hn)
            if pd.notna(aid) and an:
                goalie_names[str(int(aid))] = str(an)
        for eid, en in zip(g.event_goalie_id, g.event_goalie_name):
            if pd.notna(eid) and en:
                goalie_names.setdefault(str(int(eid)), str(en))
        starters = {"home": None, "away": None}
        hs = g.home_goalie_id.dropna()
        as_ = g.away_goalie_id.dropna()
        if len(hs):
            starters["home"] = int(hs.iloc[0])
        if len(as_):
            starters["away"] = int(as_.iloc[0])

        events: list[Event] = []
        so_goals = {home: 0, away: 0}
        ot_goal = False
        ev = g[g.event_type.isin(TYPE_MAP)]
        for row in ev.itertuples(index=False):
            ptype = row.period_type
            if ptype == "SHOOTOUT":
                if row.event_type == "GOAL" and row.event_team_abbr in so_goals:
                    so_goals[row.event_team_abbr] += 1
                continue
            team = row.event_team_abbr
            if team not in (home, away) or pd.isna(row.game_seconds):
                continue
            minute = float(row.game_seconds) / 60.0
            t = TYPE_MAP[row.event_type]
            if t == "goal" and ptype == "OVERTIME":
                ot_goal = True
            goalie = int(row.event_goalie_id) if (t in ("goal", "shot-on-goal") and pd.notna(row.event_goalie_id)) else None
            ss = str(row.strength_state) if pd.notna(row.strength_state) else ""
            strength = "EV"
            if "v" in ss:
                try:
                    own, opp = ss.split("v")
                    own_i, opp_i = int(own), int(opp)
                    strength = "PP" if own_i > opp_i else ("SH" if own_i < opp_i else "EV")
                except ValueError:
                    pass
            hsk = int(row.home_skaters) if pd.notna(row.home_skaters) else 5
            ask = int(row.away_skaters) if pd.notna(row.away_skaters) else 5
            hin = int(row.home_goalie_in) if pd.notna(row.home_goalie_in) else 1
            ain = int(row.away_goalie_in) if pd.notna(row.away_goalie_in) else 1
            dur = int(row.penalty_minutes) if (t == "penalty" and pd.notna(row.penalty_minutes)) else 0
            events.append(Event(round(minute, 4), int(row.period), t, team, goalie, _situation(hsk, ask, hin, ain), strength, dur))

        last = g.iloc[-1]
        home_score, away_score = int(last.home_score), int(last.away_score)
        if (g.period_type == "SHOOTOUT").any():
            ended = "SO"
            if so_goals[home] > so_goals[away]:
                home_score += 1
            elif so_goals[away] > so_goals[home]:
                away_score += 1
        elif ot_goal:
            ended = "OT"
        else:
            ended = "REG"
        records.append(GameRecord(
            game_id=int(gid), season=season, date=date, start_utc=f"{date}T23:00:00Z", home=home, away=away, venue=home,
            final=True, home_score=home_score, away_score=away_score, ended_in=ended, starters=starters,
            goalie_names=goalie_names, events=events,
        ))
    records.sort(key=lambda r: (r.date, r.game_id))
    return records


def attach_rest_from_records(records: list[GameRecord], extra_future: list[dict] | None = None) -> dict[int, dict]:
    """Rest/travel context from the games themselves (no API needed). Returns the index so a slate can reuse it."""
    by_team: dict[str, list[dict]] = {t: [] for t in ALL_TEAMS}
    entries = [{"game_id": r.game_id, "date": r.date, "start_utc": r.start_utc, "home": r.home, "away": r.away, "state": "OFF"} for r in records]
    entries += extra_future or []
    for e in entries:
        by_team.setdefault(e["home"], []).append(e)
        by_team.setdefault(e["away"], []).append(e)
    ctx: dict[int, dict] = {}
    for t, games in by_team.items():
        games.sort(key=lambda x: (x["date"], x["game_id"]))
        for i, gm in enumerate(games):
            side = "home" if gm["home"] == t else "away"
            ctx.setdefault(gm["game_id"], {})[side] = rest_context(games, i, t)
    for r in records:
        r.rest = ctx.get(r.game_id, {})
    return ctx


def ingest_sdv_season(season: int, force_download: bool = False, verbose: bool = True, is_current: bool = True) -> list[GameRecord]:
    """Download the season parquet, convert, attach rest context, write games_<season>.jsonl.
    Conversion is skipped when the records on disk are newer than the parquet."""
    from .ingest import load_games

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    p = download_sdv(season, force=force_download, is_current=is_current)
    out = games_file(season)
    if out.exists() and out.stat().st_mtime >= p.stat().st_mtime and not force_download:
        recs = load_games(season)
        if recs:
            if verbose:
                print(f"  {season}: {len(recs)} final games on disk (through {recs[-1].date})")
            return recs
    recs = load_sdv(p)
    attach_rest_from_records(recs)
    with games_file(season).open("w") as fh:
        for r in recs:
            fh.write(r.to_json() + "\n")
    if verbose:
        last = recs[-1].date if recs else "n/a"
        print(f"  {season}: {len(recs)} final games from sportsdataverse (through {last})")
    return recs
