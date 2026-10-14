"""Arena coordinates, time zones and NHL team ids, used for travel and rest features."""
from __future__ import annotations

import math
from datetime import datetime
from zoneinfo import ZoneInfo

# abbrev: (team_id, arena, lat, lon, IANA tz)
ARENAS: dict[str, tuple[int, str, float, float, str]] = {
    "ANA": (24, "Honda Center", 33.8078, -117.8765, "America/Los_Angeles"),
    "BOS": (6, "TD Garden", 42.3662, -71.0621, "America/New_York"),
    "BUF": (7, "KeyBank Center", 42.8750, -78.8764, "America/New_York"),
    "CGY": (20, "Scotiabank Saddledome", 51.0374, -114.0519, "America/Edmonton"),
    "CAR": (12, "Lenovo Center", 35.8033, -78.7219, "America/New_York"),
    "CHI": (16, "United Center", 41.8807, -87.6742, "America/Chicago"),
    "COL": (21, "Ball Arena", 39.7487, -105.0077, "America/Denver"),
    "CBJ": (29, "Nationwide Arena", 39.9692, -83.0061, "America/New_York"),
    "DAL": (25, "American Airlines Center", 32.7905, -96.8103, "America/Chicago"),
    "DET": (17, "Little Caesars Arena", 42.3411, -83.0553, "America/Detroit"),
    "EDM": (22, "Rogers Place", 53.5469, -113.4979, "America/Edmonton"),
    "FLA": (13, "Amerant Bank Arena", 26.1584, -80.3256, "America/New_York"),
    "LAK": (26, "Crypto.com Arena", 34.0430, -118.2673, "America/Los_Angeles"),
    "MIN": (30, "Grand Casino Arena", 44.9448, -93.1011, "America/Chicago"),
    "MTL": (8, "Centre Bell", 45.4961, -73.5693, "America/Toronto"),
    "NSH": (18, "Bridgestone Arena", 36.1592, -86.7785, "America/Chicago"),
    "NJD": (1, "Prudential Center", 40.7336, -74.1711, "America/New_York"),
    "NYI": (2, "UBS Arena", 40.7148, -73.7278, "America/New_York"),
    "NYR": (3, "Madison Square Garden", 40.7505, -73.9934, "America/New_York"),
    "OTT": (9, "Canadian Tire Centre", 45.2969, -75.9272, "America/Toronto"),
    "PHI": (4, "Xfinity Mobile Arena", 39.9012, -75.1720, "America/New_York"),
    "PIT": (5, "PPG Paints Arena", 40.4395, -79.9892, "America/New_York"),
    "SJS": (28, "SAP Center at San Jose", 37.3327, -121.9012, "America/Los_Angeles"),
    "SEA": (55, "Climate Pledge Arena", 47.6221, -122.3540, "America/Los_Angeles"),
    "STL": (19, "Enterprise Center", 38.6268, -90.2026, "America/Chicago"),
    "TBL": (14, "Amalie Arena", 27.9427, -82.4518, "America/New_York"),
    "TOR": (10, "Scotiabank Arena", 43.6435, -79.3791, "America/Toronto"),
    "UTA": (59, "Delta Center", 40.7683, -111.9011, "America/Denver"),
    "VAN": (23, "Rogers Arena", 49.2778, -123.1089, "America/Vancouver"),
    "VGK": (54, "T-Mobile Arena", 36.1028, -115.1784, "America/Los_Angeles"),
    "WSH": (15, "Capital One Arena", 38.8981, -77.0209, "America/New_York"),
    "WPG": (52, "Canada Life Centre", 49.8927, -97.1435, "America/Winnipeg"),
}

TEAM_ID_TO_ABBREV = {v[0]: k for k, v in ARENAS.items()}
ALL_TEAMS = sorted(ARENAS)


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def utc_offset_hours(tz: str, when: datetime) -> float:
    off = when.astimezone(ZoneInfo(tz)).utcoffset()
    return off.total_seconds() / 3600.0 if off else 0.0


def travel_between(home_abbrev_prev: str, home_abbrev_now: str, when: datetime) -> tuple[float, int]:
    """Distance (km) and whole time zones crossed between two arena cities."""
    if home_abbrev_prev not in ARENAS or home_abbrev_now not in ARENAS:
        return 0.0, 0
    _, _, la1, lo1, tz1 = ARENAS[home_abbrev_prev]
    _, _, la2, lo2, tz2 = ARENAS[home_abbrev_now]
    km = haversine_km(la1, lo1, la2, lo2)
    tzs = abs(round(utc_offset_hours(tz1, when) - utc_offset_hours(tz2, when)))
    return km, int(tzs)
