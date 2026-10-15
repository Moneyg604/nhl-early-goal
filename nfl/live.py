"""Live scores and box scores from ESPN's public scoreboard, for the page and for grading during the games.

The page fetches ESPN directly (the endpoint allows cross-origin reads); this module writes the same data
to docs/nfl/live.json from the scheduled job, so the page still has scores when the direct call fails.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone

from .config import ESPN_SCOREBOARD, SITE_DIR

ESPN_TO_NFLVERSE = {"WSH": "WAS", "LAR": "LA", "JAC": "JAX"}
SUFFIX = {"jr", "sr", "ii", "iii", "iv", "v"}


def name_key(name: str) -> str:
    """'Jaxon Smith-Njigba' and 'J.Smith-Njigba' -> 'j.smith-njigba'; suffixes dropped."""
    name = (name or "").strip()
    if not name:
        return ""
    if re.match(r"^[A-Za-z]{1,2}\.[A-Za-z'-]{2,}", name):            # nflverse short form: 'J.Smith-Njigba', 'A.St. Brown'
        first, rest = name.split(".", 1)
    else:                                                    # full form: 'Jaxon Smith-Njigba', 'C.J. Stroud', 'DK Metcalf'
        parts = name.split(" ", 1)
        first, rest = parts[0], (parts[1] if len(parts) > 1 else "")
    toks = [t for t in re.split(r"\s+", rest.replace(".", " ").strip()) if t and t.lower().strip(",") not in SUFFIX]
    return (first[:1] + "." + "".join(toks)).lower()


def _get(url: str, timeout: int = 20) -> dict | None:
    try:
        import requests  # type: ignore
        r = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0"})
        return r.json() if r.ok else None
    except Exception:  # noqa: BLE001
        return None


def parse_event(ev: dict) -> dict:
    comp = (ev.get("competitions") or [{}])[0]
    st = (comp.get("status") or ev.get("status") or {})
    stype = st.get("type") or {}
    out = {"espn": str(ev.get("id")), "state": stype.get("state"), "detail": stype.get("shortDetail") or stype.get("detail"),
           "period": st.get("period"), "clock": st.get("displayClock"), "completed": bool(stype.get("completed"))}
    for c in comp.get("competitors") or []:
        side = c.get("homeAway")
        ab = (c.get("team") or {}).get("abbreviation", "")
        out[side] = ESPN_TO_NFLVERSE.get(ab, ab)
        try:
            out[f"{side}_score"] = int(c.get("score") or 0)
        except ValueError:
            out[f"{side}_score"] = 0
        out[f"{side}_line"] = [int(float(x.get("value") or 0)) for x in (c.get("linescores") or [])]
    sit = comp.get("situation") or {}
    if sit:
        out["possession"] = sit.get("possession"); out["down_distance"] = sit.get("shortDownDistanceText")
    return out


def parse_summary(js: dict) -> dict:
    """Box score: passing by quarterback, field goals made by team, touchdown scorers (rushing + receiving)."""
    box = {"qb": {}, "fg": {}, "td": []}
    for tp in ((js.get("boxscore") or {}).get("players") or []):
        ab = (tp.get("team") or {}).get("abbreviation", "")
        ab = ESPN_TO_NFLVERSE.get(ab, ab)
        for grp in tp.get("statistics") or []:
            keys = grp.get("keys") or []
            for a in grp.get("athletes") or []:
                nm = (a.get("athlete") or {}).get("displayName", "")
                st = dict(zip(keys, a.get("stats") or []))
                if grp.get("name") == "passing":
                    try:
                        box["qb"][name_key(nm)] = {"name": nm, "team": ab, "yds": int(st.get("passingYards", 0) or 0), "td": int(st.get("passingTouchdowns", 0) or 0)}
                    except ValueError:
                        pass
                elif grp.get("name") == "rushing" and str(st.get("rushingTouchdowns", "0")) not in ("0", ""):
                    box["td"].append(name_key(nm))
                elif grp.get("name") == "receiving" and str(st.get("receivingTouchdowns", "0")) not in ("0", ""):
                    box["td"].append(name_key(nm))
                elif grp.get("name") == "kicking":
                    fg = str(st.get("fieldGoalsMade/fieldGoalAttempts", "0/0")).split("/")[0]
                    try:
                        box["fg"][ab] = box["fg"].get(ab, 0) + int(fg)
                    except ValueError:
                        pass
    box["td"] = sorted(set(box["td"]))
    return box


def snapshot(path=None) -> int:
    js = _get(ESPN_SCOREBOARD)
    if not js:
        return 0
    games = {}
    for ev in js.get("events") or []:
        g = parse_event(ev)
        if g["state"] in ("in", "post"):
            s = _get(f"https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event={g['espn']}")
            if s:
                g["box"] = parse_summary(s)
        games[g["espn"]] = g
    out = {"updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "week": (js.get("week") or {}).get("number"),
           "season": (js.get("season") or {}).get("year"), "games": games, "fetched": int(time.time())}
    path = path or SITE_DIR / "live.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        old = json.loads(path.read_text())
        if old.get("games") == json.loads(json.dumps(games)) and old.get("week") == out["week"]:
            return len(games)          # nothing moved: keep the file (and the commit history) as it is
    except Exception:  # noqa: BLE001
        pass
    path.write_text(json.dumps(out, separators=(",", ":")))
    return len(games)


__all__ = ["snapshot", "parse_event", "parse_summary", "name_key"]
