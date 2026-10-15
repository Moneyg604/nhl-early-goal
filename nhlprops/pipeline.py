"""Build the day's props payload from the slate the NHL model just simulated.

Inputs: the slate (home / away per game), the game models from earlygoal (expected goals and the simulated
team-goal distributions, which already carry goalies, rest, travel and the market anchor), the DailyFaceoff
lineups (who dresses tonight, line and power-play unit, injuries) and the DraftKings prices fetched for the day.
"""
from __future__ import annotations

import json
import time
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np

from .config import CFG, DATA_DIR, MODEL_VERSION, STANDARD_LINES, ModelConfig
from .features import Profiles, build, dressed_last
from .ingest import load
from .model import team_inputs, skater_markets, team_markets, over_under, fair_line, KMAX
from .odds import load as load_odds, for_game, name_key


def _norm(name: str) -> str:
    return name_key(name)


POS_FILE = DATA_DIR / "positions.json"


def positions(teams: list[str], max_age_days: float = 3.0) -> dict[str, str]:
    """Player id -> "F" / "D" from the NHL roster endpoint (reachable from the CI runner), cached in
    data/nhlprops/positions.json. Best effort: missing teams fall back to a usage heuristic."""
    cache: dict = {}
    if POS_FILE.exists():
        try:
            cache = json.loads(POS_FILE.read_text())
        except json.JSONDecodeError:
            cache = {}
    fetched = cache.get("_fetched", {})
    now = time.time()
    try:
        import requests  # type: ignore
        for t in teams:
            if now - fetched.get(t, 0) < max_age_days * 86400:
                continue
            try:
                r = requests.get(f"https://api-web.nhle.com/v1/roster/{t}/current", timeout=15)
                if not r.ok:
                    continue
                d = r.json()
                for grp, pos in (("forwards", "F"), ("defensemen", "D")):
                    for pl in d.get(grp, []):
                        cache[str(pl.get("id"))] = pos
                fetched[t] = now
            except Exception:  # noqa: BLE001
                continue
    except Exception:  # noqa: BLE001
        pass
    cache["_fetched"] = fetched
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        POS_FILE.write_text(json.dumps(cache))
    except OSError:
        pass
    return {k: v for k, v in cache.items() if not k.startswith("_")}


def lineup_skaters(lu: dict | None) -> tuple[list[dict], dict]:
    """Projected skaters from a DailyFaceoff lineup: [{name, pos, line, pp}], and the injury list by name key."""
    if not lu:
        return [], {}
    groups = lu.get("groups") or {}
    out: dict[str, dict] = {}
    for k in ("f1", "f2", "f3", "f4", "d1", "d2", "d3"):
        for e in groups.get(k, []):
            out[_norm(e["name"])] = {"name": e["name"], "pos": "D" if k.startswith("d") else "F", "line": k.upper(), "pp": "",
                                    "toi_last5": e.get("toi_last5"), "shots_last10_pg": e.get("shots_last10_pg")}
    for k in ("pp1", "pp2"):
        for e in groups.get(k, []):
            key = _norm(e["name"])
            if key in out:
                out[key]["pp"] = k.upper()
    inj = {_norm(i["name"]): i for i in (lu.get("injuries") or [])}
    return list(out.values()), inj


def candidates(P: Profiles, sk, team: str, date: str, lu: dict | None, cfg: ModelConfig = CFG) -> tuple[list[dict], str]:
    """Tonight's skaters for `team`: the DailyFaceoff projected lineup when there is one (matched to the records by
    name, injured players removed), otherwise the skaters who dressed in the team's last game."""
    last_ids, last_names = dressed_last(sk, team, date, games=cfg.recent_games)
    pool = {pid: P.skaters[pid] for pid in last_ids if pid in P.skaters}
    by_key = {_norm(S.name): S for S in pool.values()}
    # new arrivals (trades, call-ups): any skater in the records whose last team is this one
    for pid, S in P.skaters.items():
        if S.team == team and pid not in pool:
            by_key.setdefault(_norm(S.name), S)
    all_key = {}
    for S in P.skaters.values():
        all_key.setdefault(_norm(S.name), S)
    proj, inj = lineup_skaters(lu)
    rows = []
    if proj:
        for e in proj:
            key = _norm(e["name"])
            S = by_key.get(key) or all_key.get(key)
            st = (inj.get(key) or {}).get("status", "")
            if st and st.lower() in ("out", "ir", "injured reserve", "ltir", "suspended", "out for season"):
                continue
            if S is None:
                rows.append({"pid": None, "name": e["name"], "pos": e["pos"], "line": e["line"], "pp": e["pp"], "status": st, "unknown": True})
                continue
            rows.append({"pid": S.pid, "name": S.name, "pos": e["pos"], "line": e["line"], "pp": e["pp"], "status": st or "", "S": S})
        return rows, "DailyFaceoff projected lineup"
    # fallback: last game's skaters
    last1, _ = dressed_last(sk, team, date, games=1)
    for pid in sorted(last1):
        S = P.skaters.get(pid)
        if S:
            rows.append({"pid": pid, "name": S.name, "pos": S.pos_hint, "line": "", "pp": "", "status": "", "S": S})
    return rows, "last game's skaters (no projected lineup yet)"


def _price_rows(pmf: list[float], lines: list[float]) -> list[dict]:
    out = []
    for L in lines:
        o, pu, u = over_under(pmf, L)
        out.append({"line": L, "over": round(o / max(1e-9, 1 - pu), 4), "under": round(u / max(1e-9, 1 - pu), 4), "push": round(pu, 4)})
    return out


def build_day(date: str, slate: list[dict], models: list | None, lineups: dict | None, cfg: ModelConfig = CFG, seasons: list[int] | None = None,
              odds: dict | None = None) -> dict:
    t0 = time.time()
    yr = int(date[:4]) + (1 if int(date[5:7]) >= 9 else 0)
    seasons = seasons or [yr - 2, yr - 1, yr]
    sk, tf = load(seasons)
    P = build(sk, tf, date, cfg)
    odds = odds if odds is not None else load_odds()
    POS = positions(sorted({t for g in slate for t in (g["home"], g["away"])}))
    for pid, S in P.skaters.items():
        if str(pid) in POS:
            S.pos_hint = POS[str(pid)]
    games: dict = {}
    for i, g in enumerate(slate):
        home, away = g["home"], g["away"]
        gm = r = None
        if models and i < len(models):
            gm, r = models[i]
        lam = {}; goals_pmf = {}
        for side, team, opp, is_home in (("home", home, away, True), ("away", away, home, False)):
            ti = team_inputs(P, team, opp, is_home, cfg)
            if gm is not None:
                # expected goals from the full game model: regulation + the overtime goal (shootout goals earn no points)
                eh, ea = gm.expected_goals()
                ex = r.extras if r is not None else {}
                p_ot = ex.get("p_reg_tie", 0.0) * ex.get("p_ot_goal", 0.0)
                share = gm.ot_rate_home / max(1e-9, gm.ot_rate_home + gm.ot_rate_away)
                lam[side] = (eh if is_home else ea) + p_ot * (share if is_home else 1 - share)
                dist = ex.get("home_goals_dist" if is_home else "away_goals_dist")
                goals_pmf[side] = dist
                ti["lam_goals"] = lam[side]
            else:
                lam[side] = ti["lam_goals"]
                goals_pmf[side] = None
            ti["_"] = None
            tm = team_markets(P, ti, goals_pmf.get(side))
            cands, src = candidates(P, sk, team, date, (lineups or {}).get(team), cfg)
            book = for_game(odds, home, away, date) or {}
            mk = book.get("markets") or {}
            skaters = []
            for c in cands:
                S = c.get("S")
                if S is None:
                    skaters.append({k: v for k, v in c.items() if k != "S"})
                    continue
                m = skater_markets(P, S, ti, lam[side], cfg)
                row = {k: v for k, v in c.items() if k != "S"}
                row.update({"games": S.games, "last5": S.last5, "rates": m["rates"], "mean": m["mean"], "fair": m["fair"], "pmf": m["pmf"],
                            "prices": {k: _price_rows(m["pmf"][k], STANDARD_LINES[k]) for k in ("sog", "pts", "ast", "blk")},
                            "p_goal": round(over_under(m["pmf"]["goal"], 0.5)[0], 4)})
                key = _norm(S.name)
                row["book"] = {s: mk.get(s, {}).get(key) for s in ("sog", "pts", "ast", "blk", "goal") if mk.get(s, {}).get(key)}
                skaters.append(row)
            skaters.sort(key=lambda x: -(x.get("mean", {}).get("pts", 0) or 0))
            tt_book = mk.get("team_total", {}).get(team)
            games.setdefault(i, {"game_id": g.get("game_id"), "home": home, "away": away, "start_utc": g.get("start_utc"), "sides": {}})
            games[i]["sides"][side] = {"team": team, "opp": opp, "lineup_source": src, "lam_goals": round(lam[side], 3),
                                       "team": team, "markets": tm, "team_total_prices": _price_rows(tm["team_total"], STANDARD_LINES["team_total"]),
                                       "ppg_prices": _price_rows(tm["ppg"], STANDARD_LINES["ppg"]), "book_team_total": tt_book,
                                       "skaters": skaters, "n_lineup": len(skaters)}
        games[i]["book_fetched"] = (for_game(odds, home, away, date) or {}).get("fetched_utc")
        games[i]["book_markets"] = sorted(k for k, v in ((for_game(odds, home, away, date) or {}).get("markets") or {}).items() if v)
    bt = DATA_DIR / "backtest_latest.json"
    fx = DATA_DIR / "factors.json"
    payload = {"date": date, "generated_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"), "model_version": MODEL_VERSION,
               "games": [games[k] for k in sorted(games)], "league": P.league.__dict__, "as_of": P.as_of,
               "data_through": str(sk.date.max()) if len(sk) else None, "n_skaters": len(P.skaters),
               "validation": json.loads(bt.read_text()) if bt.exists() else None, "factors": json.loads(fx.read_text()) if fx.exists() else None,
               "odds": {"date": odds.get("date"), "credits_remaining": odds.get("credits_remaining"), "updated_utc": odds.get("updated_utc"),
                        "games_with_prices": len(odds.get("games", {})) if odds.get("date") == date else 0},
               "lines": STANDARD_LINES, "cfg": cfg.__dict__, "build_seconds": round(time.time() - t0, 1)}
    return payload


__all__ = ["build_day", "candidates", "lineup_skaters"]
