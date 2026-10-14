"""Thin, cached client for the public NHL web API (api-web.nhle.com).

Every response is cached on disk as JSON. Finished games never change, so
their play-by-play is cached forever; schedules and live/pre-game documents
are cached for a short TTL so a re-run within the hour does not re-download
the slate.

Endpoints used:
  /schedule/{YYYY-MM-DD}                 slate for a day (gameWeek[].games[])
  /club-schedule-season/{TEAM}/{season}  every game for a team (rest/travel)
  /gamecenter/{id}/play-by-play          events with timeInPeriod + goalieInNetId
  /gamecenter/{id}/landing               pre-game matchup, goalie season stats
  /gamecenter/{id}/right-rail            officials, team game stats (near tip)
  /roster/{TEAM}/current                 active roster
  /standings/now                         standings snapshot
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from .config import CACHE_DIR, NHL_API

try:  # requests is nicer but not required
    import requests  # type: ignore

    _HAS_REQUESTS = True
except Exception:  # pragma: no cover
    _HAS_REQUESTS = False
    import urllib.request

FOREVER = 10 * 365 * 24 * 3600
SHORT = 45 * 60
MEDIUM = 6 * 3600


class NHLUnavailable(RuntimeError):
    """Raised once the API has failed repeatedly, so callers stop waiting on retries."""


class NHLClient:
    def __init__(self, cache_dir: Path = CACHE_DIR, sleep: float = 0.15, timeout: float = 20.0, max_consecutive_failures: int = 2):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.sleep = sleep
        self.timeout = timeout
        self.requests_made = 0
        self.consecutive_failures = 0
        self.max_consecutive_failures = max_consecutive_failures
        self._session = requests.Session() if _HAS_REQUESTS else None
        if self._session is not None:
            self._session.headers.update({"User-Agent": "earlygoal/0.3 (personal research tool)"})

    # ------------------------------------------------------------------ core
    def _cache_path(self, path: str) -> Path:
        safe = path.strip("/").replace("/", "__").replace("?", "_q_").replace("&", "_")
        return self.cache_dir / f"{safe}.json"

    def get(self, path: str, ttl: float = SHORT, force: bool = False) -> Any:
        cp = self._cache_path(path)
        if cp.exists() and not force:
            age = time.time() - cp.stat().st_mtime
            if age < ttl:
                with cp.open() as f:
                    return json.load(f)
        url = f"{NHL_API}/{path.lstrip('/')}"
        if self.consecutive_failures >= self.max_consecutive_failures:
            raise NHLUnavailable("NHL API unreachable (repeated failures); not retrying")
        try:
            data = self._fetch(url)
        except FileNotFoundError:
            raise
        except Exception:
            self.consecutive_failures += 1
            raise
        self.consecutive_failures = 0
        with cp.open("w") as f:
            json.dump(data, f)
        self.requests_made += 1
        if self.sleep:
            time.sleep(self.sleep)
        return data

    def _fetch(self, url: str) -> Any:
        last_err: Exception | None = None
        for attempt in range(4):
            try:
                if self._session is not None:
                    r = self._session.get(url, timeout=self.timeout)
                    if r.status_code == 404:
                        raise FileNotFoundError(url)
                    r.raise_for_status()
                    return r.json()
                req = urllib.request.Request(url, headers={"User-Agent": "earlygoal/0.3"})
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # type: ignore[attr-defined]
                    return json.loads(resp.read().decode("utf-8"))
            except FileNotFoundError:
                raise
            except Exception as e:  # network hiccup: back off and retry
                last_err = e
                if self.consecutive_failures > 0:
                    break  # the previous request already failed; fail fast
                time.sleep(0.8 * (attempt + 1))
        raise RuntimeError(f"NHL API request failed: {url}: {last_err}")

    # ------------------------------------------------------------- endpoints
    def schedule(self, date: str, force: bool = False) -> list[dict]:
        """All games on a calendar date (YYYY-MM-DD, Eastern-day semantics of the NHL)."""
        data = self.get(f"schedule/{date}", ttl=SHORT, force=force)
        for day in data.get("gameWeek", []):
            if day.get("date") == date:
                return day.get("games", [])
        return []

    def club_schedule(self, team: str, season: int, force: bool = False) -> list[dict]:
        data = self.get(f"club-schedule-season/{team}/{season}", ttl=MEDIUM, force=force)
        return data.get("games", [])

    def play_by_play(self, game_id: int, final: bool = True) -> dict:
        return self.get(f"gamecenter/{game_id}/play-by-play", ttl=FOREVER if final else SHORT)

    def landing(self, game_id: int, final: bool = False) -> dict:
        return self.get(f"gamecenter/{game_id}/landing", ttl=FOREVER if final else SHORT)

    def right_rail(self, game_id: int, final: bool = False) -> dict:
        return self.get(f"gamecenter/{game_id}/right-rail", ttl=FOREVER if final else SHORT)

    def boxscore(self, game_id: int, final: bool = True) -> dict:
        return self.get(f"gamecenter/{game_id}/boxscore", ttl=FOREVER if final else SHORT)

    def roster(self, team: str) -> dict:
        return self.get(f"roster/{team}/current", ttl=MEDIUM)

    def standings(self) -> dict:
        return self.get("standings/now", ttl=MEDIUM)


def mmss_to_minutes(s: str) -> float:
    """'01:34' -> 1.5667 minutes."""
    m, sec = s.split(":")
    return int(m) + int(sec) / 60.0


def game_season(game_id: int) -> int:
    """2026020090 -> 20262027."""
    y = int(str(game_id)[:4])
    return y * 10000 + (y + 1)
