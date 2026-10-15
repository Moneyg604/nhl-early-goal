"""Player yardage and reception props, drawn game by game from the same simulation as everything else.

For each simulated game the team's passing yards, dropbacks and final margin are already known. This layer adds
    rushes      = team rushes at a level score x team and opponent multipliers + league slope x margin + noise
    rush yards  = rushes x yards per carry (team x opponent) ... per player: his share of the rushes x his own YPC
    rec yards   = his share of the team's passing yards x the simulated passing yards
    receptions  = his share of the team's completions x simulated completions (dropbacks x (1 - sack rate) x comp%)
each with noise measured from 2024-25 player-games (sd = k x sqrt(expected)). Shares come from PlayerProfile.usage().

Returns per player: probability mass functions the page prices at any line, plus the median and a fair line.
"""
from __future__ import annotations

import numpy as np

from .config import CFG, ModelConfig
from .features import Profiles
from .markets import fair_line, fair_odds, pmf, compress
from .sim import SimResult

SACK_RATE = 0.065


def team_rushing(P: Profiles, row: dict, side: str, sim: SimResult, rng: np.random.Generator, cfg: ModelConfig = CFG) -> tuple[np.ndarray, np.ndarray]:
    """Simulated rushing attempts and yards for `side` ("home"/"away")."""
    lt = P.league
    t = row[side]; o = row["away" if side == "home" else "home"]
    tp, op = P.team(t), P.team(o)
    i = 0 if side == "home" else 1
    margin = (sim.pts[:, 0] - sim.pts[:, 1]) * (1 if side == "home" else -1)
    mult = tp.off.rush_mult(lt, cfg) * op.def_.rush_mult(lt, cfg)
    att = (lt.rush_base * mult + lt.rush_slope * margin + rng.standard_normal(sim.n) * lt.rush_sd).clip(8, 60)
    ypc = lt.ypc * tp.off.ypc_mult(lt, cfg) * op.def_.ypc_mult(lt, cfg)
    yds = att * ypc + rng.standard_normal(sim.n) * 1.9 * np.sqrt(att)
    return att, yds


def player_props(P: Profiles, row: dict, side: str, sim: SimResult, cands: list[dict], seed: int = 21, cfg: ModelConfig = CFG) -> list[dict]:
    """Props for the listed candidates (from players.candidates): receiving yards, rushing yards, receptions."""
    rng = np.random.default_rng(seed)
    lt = P.league
    i = 0 if side == "home" else 1
    att, team_ryds = team_rushing(P, row, side, sim, rng, cfg)
    pass_yds = sim.yds[:, i].astype(float)
    comps = sim.db[:, i].astype(float) * (1 - SACK_RATE) * lt.comp_rate
    out = []
    for c in cands:
        pp = P.players.get(c["id"])
        if pp is None:
            continue
        u = pp.usage(cfg)
        rec = {"id": c["id"], "name": c["name"], "pos": c.get("pos", ""), "games": pp.games, "usage": {k: round(v, 3) if isinstance(v, float) else v for k, v in u.items()}}
        # receiving yards
        if u["rec_yds_share"] >= 0.03:
            e = u["rec_yds_share"] * pass_yds
            y = np.maximum(0, e + rng.standard_normal(sim.n) * lt.rec_yds_k * np.sqrt(np.maximum(e, 1)))
            rec["rec_yds"] = _dist(y, 5.0, 100)
        # rushing yards
        if u["car_share"] >= 0.05:
            car = u["car_share"] * att
            e = car * u["ypc"]
            y = np.maximum(0, e + rng.standard_normal(sim.n) * lt.rush_yds_k * np.sqrt(np.maximum(e, 1)))
            rec["rush_yds"] = _dist(y, 5.0, 80)
        # receptions
        if u["rec_share"] >= 0.03:
            e = u["rec_share"] * comps
            y = np.maximum(0, np.rint(e + rng.standard_normal(sim.n) * lt.recs_k * np.sqrt(np.maximum(e, 0.5))))
            rec["recs"] = _dist(y, 1.0, 20)
        if any(k in rec for k in ("rec_yds", "rush_yds", "recs")):
            out.append(rec)
    return out


def _dist(y: np.ndarray, step: float, bins: int) -> dict:
    p = pmf(y / step, 0, bins)
    off, vals = compress(p)
    qs = np.percentile(y, [10, 25, 50, 75, 90])
    return {"pmf": [off, vals], "step": step, "mean": round(float(y.mean()), 1), "q": [round(float(q), 1) for q in qs], "fair_line": fair_line(y)}


def prob_over(d: dict, line: float) -> tuple[float, float, float]:
    """(over, push, under) at `line` for a stored distribution."""
    off, vals = d["pmf"]; step = d["step"]
    v = (np.arange(off, off + len(vals)) * step); p = np.array(vals)
    s = p.sum() or 1.0
    return float(p[v > line].sum() / s), float(p[v == line].sum() / s), float(p[v < line].sum() / s)


__all__ = ["player_props", "team_rushing", "prob_over"]
