"""ESPN's public NBA site API: the day's schedule and scores, and per game the box score (every player's minutes
and counting stats), the injury report and DraftKings' game lines (the "pickcenter" block).

    events = scoreboard("2026-10-20")          # the day's games, pre / in / post
    game = parse_game(summary(event_id))       # a finished game as the engine stores it
    pre = parse_pregame(summary(event_id))     # lines, injuries and the two rosters' recent box scores for a game to come
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import CACHE_DIR, ESPN_SCOREBOARD, ESPN_SUMMARY

UA = {"User-Agent": "Mozilla/5.0 (compatible; GillSports/1.0; +https://github.com/Moneyg604/nhl-early-goal)"}


def _get(url: str, params: dict | None = None, tries: int = 3) -> dict | None:
    import requests  # type: ignore
    for i in range(tries):
        try:
            r = requests.get(url, params=params, headers=UA, timeout=30)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (404, 400):
                return None
        except Exception as e:  # noqa: BLE001
            if i == tries - 1:
                print(f"  espn: {url} failed: {e}")
        time.sleep(1.5 * (i + 1))
    return None


def scoreboard(date: str) -> list[dict]:
    """The day's events (YYYY-MM-DD, ET calendar day as ESPN counts it)."""
    d = _get(ESPN_SCOREBOARD, {"dates": date.replace("-", ""), "limit": 50})
    out = []
    for ev in (d or {}).get("events", []):
        comp = (ev.get("competitions") or [{}])[0]
        home = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "home"), {})
        away = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "away"), {})
        st = (ev.get("status") or {}).get("type") or {}
        out.append({"id": ev.get("id"), "date": ev.get("date"), "name": ev.get("name"), "state": st.get("state"), "completed": bool(st.get("completed")),
                    "status": st.get("shortDetail") or st.get("name"), "home": (home.get("team") or {}).get("abbreviation"), "away": (away.get("team") or {}).get("abbreviation"),
                    "hs": _int(home.get("score")), "as": _int(away.get("score")), "season": (ev.get("season") or {}).get("year"), "season_type": (ev.get("season") or {}).get("type"),
                    "venue": ((comp.get("venue") or {}).get("fullName")), "neutral": bool(comp.get("neutralSite"))})
    return out


def summary(event_id: str, cache: bool = True) -> dict | None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    f = CACHE_DIR / f"summary_{event_id}.json"
    if cache and f.exists():
        try:
            return json.loads(f.read_text())
        except json.JSONDecodeError:
            pass
    d = _get(ESPN_SUMMARY, {"event": event_id})
    if d is None:
        return None
    st = (((d.get("header") or {}).get("competitions") or [{}])[0].get("status") or {}).get("type") or {}
    if cache and st.get("completed"):
        f.write_text(json.dumps(d, separators=(",", ":")))         # only finished games are cached (pre-game data changes)
    return d


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _split(x: str) -> tuple[int, int]:
    try:
        a, b = str(x).split("-")
        return int(a), int(b)
    except Exception:  # noqa: BLE001
        return 0, 0


def _players(d: dict) -> dict:
    """{team: [player line]} from the box score; a player who did not play is kept with min 0 and dnp True."""
    out: dict = {}
    for side in (d.get("boxscore") or {}).get("players", []):
        team = (side.get("team") or {}).get("abbreviation")
        stats = (side.get("statistics") or [{}])[0]
        keys = stats.get("keys") or []
        rows = []
        for a in stats.get("athletes", []):
            vals = dict(zip(keys, a.get("stats") or []))
            ath = a.get("athlete") or {}
            fgm, fga = _split(vals.get("fieldGoalsMade-fieldGoalsAttempted"))
            tpm, tpa = _split(vals.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
            ftm, fta = _split(vals.get("freeThrowsMade-freeThrowsAttempted"))
            mins = _minutes(vals.get("minutes"))
            dnp = bool(a.get("didNotPlay")) or (not a.get("stats")) or mins is None
            rows.append({"id": str(ath.get("id")), "name": ath.get("displayName"), "pos": ((ath.get("position") or {}).get("abbreviation")) or "",
                         "starter": bool(a.get("starter")), "dnp": dnp, "min": mins or 0.0, "pts": _int(vals.get("points")) or 0,
                         "fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa, "ftm": ftm, "fta": fta, "reb": _int(vals.get("rebounds")) or 0,
                         "ast": _int(vals.get("assists")) or 0, "tov": _int(vals.get("turnovers")) or 0, "stl": _int(vals.get("steals")) or 0,
                         "blk": _int(vals.get("blocks")) or 0, "oreb": _int(vals.get("offensiveRebounds")) or 0, "dreb": _int(vals.get("defensiveRebounds")) or 0,
                         "pf": _int(vals.get("fouls")) or 0})
        out[team] = rows
    return out


def _minutes(x) -> float | None:
    if x in (None, "", "--"):
        return None
    try:
        if ":" in str(x):
            m, s = str(x).split(":")
            return int(m) + int(s) / 60
        return float(x)
    except ValueError:
        return None


def _team_stats(d: dict) -> dict:
    out = {}
    for t in (d.get("boxscore") or {}).get("teams", []):
        team = (t.get("team") or {}).get("abbreviation")
        st = {x.get("name"): x.get("displayValue") for x in t.get("statistics", [])}
        fgm, fga = _split(st.get("fieldGoalsMade-fieldGoalsAttempted"))
        tpm, tpa = _split(st.get("threePointFieldGoalsMade-threePointFieldGoalsAttempted"))
        ftm, fta = _split(st.get("freeThrowsMade-freeThrowsAttempted"))
        out[team] = {"fgm": fgm, "fga": fga, "tpm": tpm, "tpa": tpa, "ftm": ftm, "fta": fta, "reb": _int(st.get("totalRebounds")) or 0,
                     "oreb": _int(st.get("offensiveRebounds")) or 0, "dreb": _int(st.get("defensiveRebounds")) or 0, "ast": _int(st.get("assists")) or 0,
                     "tov": _int(st.get("turnovers")) or _int(st.get("totalTurnovers")) or 0, "stl": _int(st.get("steals")) or 0, "blk": _int(st.get("blocks")) or 0,
                     "pts_paint": _int(st.get("pointsInPaint")), "fast_break": _int(st.get("fastBreakPoints"))}
    return out


def _lines(d: dict, home: str, away: str) -> dict:
    """DraftKings' pregame line from the pickcenter block (spread as the home team's points, total, moneylines)."""
    for pc in d.get("pickcenter") or []:
        prov = ((pc.get("provider") or {}).get("name") or "").lower()
        if "draftkings" not in prov.replace(" ", "") and pc.get("provider"):
            continue
        spread = pc.get("spread")                        # ESPN: negative = home favoured by that much
        home_pts = None if spread is None else float(spread)
        h = pc.get("homeTeamOdds") or {}; a = pc.get("awayTeamOdds") or {}
        return {"spread": home_pts, "total": pc.get("overUnder"), "home_ml": _dec(h.get("moneyLine")), "away_ml": _dec(a.get("moneyLine")),
                "spread_home_odds": _dec(h.get("spreadOdds")), "spread_away_odds": _dec(a.get("spreadOdds")), "book": "DraftKings",
                "details": pc.get("details")}
    return {}


def _dec(am) -> float | None:
    try:
        am = float(am)
    except (TypeError, ValueError):
        return None
    if am == 0:
        return None
    return round(1 + am / 100, 3) if am > 0 else round(1 + 100 / abs(am), 3)


def _injuries(d: dict) -> dict:
    out: dict = {}
    for t in d.get("injuries") or []:
        team = (t.get("team") or {}).get("abbreviation")
        rows = []
        for i in t.get("injuries") or []:
            ath = i.get("athlete") or {}
            det = i.get("details") or {}
            rows.append({"name": ath.get("displayName"), "id": str(ath.get("id")), "pos": ((ath.get("position") or {}).get("abbreviation")) or "",
                         "status": i.get("status"), "injury": det.get("type") or ((i.get("type") or {}).get("description")), "detail": det.get("detail"),
                         "return": det.get("returnDate"), "date": i.get("date")})
        out[team] = rows
    return out


def _header(d: dict) -> dict:
    comp = ((d.get("header") or {}).get("competitions") or [{}])[0]
    home = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "home"), {})
    away = next((c for c in comp.get("competitors", []) if c.get("homeAway") == "away"), {})
    st = (comp.get("status") or {}).get("type") or {}
    return {"id": str(comp.get("id") or (d.get("header") or {}).get("id")), "date": comp.get("date"), "home": (home.get("team") or {}).get("abbreviation"),
            "away": (away.get("team") or {}).get("abbreviation"), "hs": _int(home.get("score")), "as": _int(away.get("score")),
            "q": {"home": [_int(x.get("displayValue")) for x in home.get("linescores") or []], "away": [_int(x.get("displayValue")) for x in away.get("linescores") or []]},
            "completed": bool(st.get("completed")), "state": st.get("state"), "season": ((d.get("header") or {}).get("season") or {}).get("year"),
            "season_type": ((d.get("header") or {}).get("season") or {}).get("type"), "neutral": bool(comp.get("neutralSite"))}


def parse_game(d: dict) -> dict | None:
    """A finished game as the engine stores it (data/nba/games_<season>.jsonl)."""
    h = _header(d)
    if not h.get("home") or not h.get("away"):
        return None
    g = {**h, "players": _players(d), "team": _team_stats(d), "lines": _lines(d, h["home"], h["away"])}
    g["date_local"] = h["date"][:10] if h.get("date") else None
    return g


def parse_pregame(d: dict) -> dict:
    """Lines, injuries and the header for a game not yet played."""
    h = _header(d)
    return {**h, "lines": _lines(d, h.get("home"), h.get("away")), "injuries": _injuries(d)}


def et_date(iso: str) -> str:
    """The ET calendar date of an ISO UTC time (NBA days are ET days)."""
    from zoneinfo import ZoneInfo
    t = datetime.strptime(iso.replace("Z", ""), "%Y-%m-%dT%H:%M").replace(tzinfo=timezone.utc)
    return t.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")


__all__ = ["scoreboard", "summary", "parse_game", "parse_pregame", "et_date"]
