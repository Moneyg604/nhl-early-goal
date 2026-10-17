"""Season data from ESPN: every finished game's box score, stored one game per line in data/nba/games_<season>.jsonl.

    python -m nba ingest --back 1      # last season (prior) plus the current one; only days not yet stored are fetched
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .config import DATA_DIR, SEASON_END, SEASON_START
from .espn import parse_game, scoreboard, summary


def season_now(today: date | None = None) -> int:
    """The season a date belongs to (2026-27 is 2027): from the season's first day until the next one starts."""
    today = today or datetime.now(timezone.utc).date()
    for s in sorted(SEASON_START, reverse=True):
        if today >= date.fromisoformat(SEASON_START[s]):
            return s
    return min(SEASON_START)


def games_file(season: int) -> Path:
    return DATA_DIR / f"games_{season}.jsonl"


def load_games(seasons: list[int]) -> list[dict]:
    out = []
    for s in seasons:
        f = games_file(s)
        if f.exists():
            for line in f.read_text().splitlines():
                if line.strip():
                    try:
                        out.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    out.sort(key=lambda g: (g.get("date") or ""))
    return out


def _days_file(season: int) -> Path:
    return DATA_DIR / f"days_{season}.json"


def ingest(seasons: list[int], today: date | None = None, max_days: int = 400, pause: float = 0.25) -> dict:
    """Fetch every finished regular-season (and play-in / playoff) game of the seasons not yet stored."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    today = today or datetime.now(timezone.utc).date()
    counts = {}
    for season in seasons:
        start = date.fromisoformat(SEASON_START.get(season) or f"{season - 1}-10-20")
        end = min(date.fromisoformat(SEASON_END.get(season) or f"{season}-06-30") + timedelta(days=70), today)
        done_days = set()
        df = _days_file(season)
        if df.exists():
            try:
                done_days = set(json.loads(df.read_text()))
            except json.JSONDecodeError:
                done_days = set()
        have = {g["id"] for g in load_games([season])}
        n_new = 0
        d = start
        days = 0
        with games_file(season).open("a") as out:
            while d <= end and days < max_days:
                ds = d.isoformat()
                if ds in done_days:
                    d += timedelta(days=1); continue
                days += 1
                evs = scoreboard(ds)
                time.sleep(pause)
                all_final = True
                for ev in evs:
                    if not ev.get("completed"):
                        all_final = False; continue
                    if ev["id"] in have:
                        continue
                    sm = summary(ev["id"])
                    time.sleep(pause)
                    if not sm:
                        all_final = False; continue
                    g = parse_game(sm)
                    if not g or not g.get("completed"):
                        all_final = False; continue
                    g["season"] = season
                    g["playoff"] = (ev.get("season_type") or g.get("season_type")) not in (2, None)
                    out.write(json.dumps(g, separators=(",", ":")) + "\n")
                    have.add(ev["id"]); n_new += 1
                # a day is finished when every game of it is final and stored (yesterday or earlier)
                if all_final and d < today:
                    done_days.add(ds)
                d += timedelta(days=1)
        df.write_text(json.dumps(sorted(done_days)))
        counts[season] = n_new
        print(f"  nba ingest {season}: {n_new} new games, {len(have)} stored")
    return counts


__all__ = ["ingest", "load_games", "season_now", "games_file"]
