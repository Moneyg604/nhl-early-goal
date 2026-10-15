"""Stadium coordinates and weather at kickoff.

Wind and cold are measured factors in the model (`features.game_context_keys`). For past games nflverse
records the observed temperature and wind; for upcoming outdoor games the forecast for the kickoff hour
comes from Open-Meteo (free, no key). Domes and closed roofs get no weather. When the forecast cannot be
reached the game is simulated without a weather adjustment and the page says so.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from .config import CACHE_DIR

# stadium_id (nflverse) -> (lat, lon, tz)
STADIUMS = {
    "ATL97": (33.7554, -84.4008, "America/New_York"), "BAL00": (39.2780, -76.6227, "America/New_York"),
    "BOS00": (42.0909, -71.2643, "America/New_York"), "BUF00": (42.7738, -78.7870, "America/New_York"),
    "BUF01": (42.7738, -78.7870, "America/New_York"),
    "CAR00": (35.2258, -80.8528, "America/New_York"), "CHI98": (41.8623, -87.6167, "America/Chicago"),
    "CIN00": (39.0955, -84.5161, "America/New_York"), "CLE00": (41.5061, -81.6995, "America/New_York"),
    "DAL00": (32.7473, -97.0945, "America/Chicago"), "DEN00": (39.7439, -105.0201, "America/Denver"),
    "DET00": (42.3400, -83.0456, "America/Detroit"), "GNB00": (44.5013, -88.0622, "America/Chicago"),
    "HOU00": (29.6847, -95.4107, "America/Chicago"), "IND00": (39.7601, -86.1639, "America/Indiana/Indianapolis"),
    "JAX00": (30.3239, -81.6373, "America/New_York"), "KAN00": (39.0489, -94.4839, "America/Chicago"),
    "LAX01": (33.9535, -118.3392, "America/Los_Angeles"), "MIA00": (25.9580, -80.2389, "America/New_York"),
    "MIN01": (44.9737, -93.2581, "America/Chicago"), "NAS00": (36.1665, -86.7713, "America/Chicago"),
    "NOR00": (29.9511, -90.0812, "America/Chicago"), "NYC01": (40.8135, -74.0745, "America/New_York"),
    "PHI00": (39.9008, -75.1675, "America/New_York"), "PHO00": (33.5276, -112.2626, "America/Phoenix"),
    "PIT00": (40.4468, -80.0158, "America/New_York"), "SEA00": (47.5952, -122.3316, "America/Los_Angeles"),
    "SFO01": (37.4030, -121.9700, "America/Los_Angeles"), "TAM00": (27.9759, -82.5033, "America/New_York"),
    "VEG00": (36.0909, -115.1833, "America/Los_Angeles"), "WAS00": (38.9076, -76.8645, "America/New_York"),
    "LON00": (51.5560, -0.2795, "Europe/London"), "LON01": (51.4816, -0.1910, "Europe/London"),
    "LON02": (51.6043, -0.0664, "Europe/London"), "MEX00": (19.3029, -99.1505, "America/Mexico_City"),
    "MUN00": (48.2188, 11.6247, "Europe/Berlin"), "MUN01": (48.2188, 11.6247, "Europe/Berlin"),
    "FRA00": (50.0686, 8.6455, "Europe/Berlin"), "SAO00": (-23.5453, -46.4742, "America/Sao_Paulo"),
    "RIO00": (-22.9121, -43.2302, "America/Sao_Paulo"), "MAD01": (40.4531, -3.6883, "Europe/Madrid"),
    "PAR00": (48.9245, 2.3602, "Europe/Paris"), "MEL00": (-37.8200, 144.9834, "Australia/Melbourne"),
    "DUB00": (53.3352, -6.2285, "Europe/Dublin"),
}

# home team -> stadium id fallback (when the schedule row has none)
HOME_STADIUM = {"ATL": "ATL97", "BAL": "BAL00", "NE": "BOS00", "BUF": "BUF00", "CAR": "CAR00", "CHI": "CHI98", "CIN": "CIN00",
                "CLE": "CLE00", "DAL": "DAL00", "DEN": "DEN00", "DET": "DET00", "GB": "GNB00", "HOU": "HOU00", "IND": "IND00",
                "JAX": "JAX00", "KC": "KAN00", "LAC": "LAX01", "LA": "LAX01", "MIA": "MIA00", "MIN": "MIN01", "TEN": "NAS00",
                "NO": "NOR00", "NYJ": "NYC01", "NYG": "NYC01", "PHI": "PHI00", "ARI": "PHO00", "PIT": "PIT00", "SEA": "SEA00",
                "SF": "SFO01", "TB": "TAM00", "LV": "VEG00", "WAS": "WAS00"}


def kickoff_utc(gameday: str, gametime: str) -> datetime | None:
    """nflverse lists kickoff in US Eastern time."""
    try:
        hh, mm = (gametime or "13:00").split(":")[:2]
        local = datetime.strptime(gameday, "%Y-%m-%d").replace(hour=int(hh), minute=int(mm), tzinfo=ZoneInfo("America/New_York"))
        return local.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def forecast(stadium_id: str, home: str, ko: datetime | None) -> dict | None:
    """Kickoff-hour temperature (F), wind (mph), gusts and precipitation from Open-Meteo, cached for 3 hours.
    Returns None when out of range (more than 15 days ahead) or unreachable."""
    sid = stadium_id if stadium_id in STADIUMS else HOME_STADIUM.get(home)
    if not sid or ko is None:
        return None
    if ko - datetime.now(timezone.utc) > timedelta(days=15):
        return None
    lat, lon, _tz = STADIUMS[sid]
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = CACHE_DIR / f"wx-{sid}-{ko:%Y%m%d%H}.json"
    if key.exists() and time.time() - key.stat().st_mtime < 3 * 3600:
        try:
            return json.loads(key.read_text())
        except json.JSONDecodeError:
            pass
    try:
        import requests  # type: ignore

        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=20, params={
            "latitude": lat, "longitude": lon, "hourly": "temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation_probability,precipitation",
            "wind_speed_unit": "mph", "temperature_unit": "fahrenheit", "timezone": "UTC",
            "start_date": ko.strftime("%Y-%m-%d"), "end_date": (ko + timedelta(hours=4)).strftime("%Y-%m-%d")})
        if not r.ok:
            return None
        h = r.json().get("hourly") or {}
        times = h.get("time") or []
        want = [(ko + timedelta(hours=k)).strftime("%Y-%m-%dT%H:00") for k in range(0, 4)]
        idx = [times.index(w) for w in want if w in times]
        if not idx:
            return None
        avg = lambda name: round(sum(h[name][i] for i in idx if h[name][i] is not None) / max(1, sum(1 for i in idx if h[name][i] is not None)), 1)  # noqa: E731
        out = {"temp": avg("temperature_2m"), "wind": avg("wind_speed_10m"), "gust": avg("wind_gusts_10m"),
               "precip_prob": avg("precipitation_probability"), "precip_mm": avg("precipitation"), "source": "Open-Meteo forecast, kickoff + 3 h"}
        key.write_text(json.dumps(out))
        return out
    except Exception:  # noqa: BLE001
        return None
