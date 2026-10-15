"""Turn a simulated game into market probabilities and compact distributions for the page.

Every market comes from the same simulation, so a total, a half total, a team's field goals and a
quarterback's passing all agree with each other. Distributions are stored as probability mass functions
so the page can price any line the book posts (including pushes on whole numbers).
"""
from __future__ import annotations

import math

import numpy as np

from .sim import SimResult


def pmf(x: np.ndarray, lo: int, hi: int) -> np.ndarray:
    x = np.clip(np.rint(x).astype(int), lo, hi) - lo
    return np.bincount(x, minlength=hi - lo + 1) / max(len(x), 1)


def apply_key_numbers(margin_pmf: np.ndarray, lo: int, weights: dict[int, float] | None) -> np.ndarray:
    """Re-weight |margin| values by the measured key-number correction (walk-forward, data/nfl/factors.json)."""
    if not weights:
        return margin_pmf
    m = np.arange(lo, lo + len(margin_pmf))
    w = np.array([weights.get(abs(int(v)), 1.0) for v in m])
    out = margin_pmf * w
    return out / out.sum()


def over_under(p: np.ndarray, lo: int, line: float) -> tuple[float, float, float]:
    """P(over), P(push), P(under) for a pmf starting at value `lo`."""
    v = np.arange(lo, lo + len(p))
    return float(p[v > line].sum()), float(p[v == line].sum()), float(p[v < line].sum())


def fair_odds(p: float, push: float = 0.0) -> float | None:
    """Decimal odds at which a bet with win probability p (and push probability `push`) breaks even."""
    q = p / max(1e-9, 1 - push)
    return round(1 / q, 3) if q > 0 else None


def american_to_prob(a: float | None) -> float | None:
    if a is None or (isinstance(a, float) and math.isnan(a)):
        return None
    return 100 / (a + 100) if a > 0 else -a / (-a + 100)


def american_to_decimal(a: float | None) -> float | None:
    if a is None or (isinstance(a, float) and math.isnan(a)):
        return None
    return round(1 + (a / 100 if a > 0 else 100 / -a), 4)


def devig2(a: float | None, b: float | None) -> tuple[float | None, float | None]:
    pa, pb = american_to_prob(a), american_to_prob(b)
    if pa is None or pb is None:
        return None, None
    s = pa + pb
    return pa / s, pb / s


def r4(x: float) -> float:
    return round(float(x), 4)


def compress(p: np.ndarray, eps: float = 5e-5) -> tuple[int, list[float]]:
    """Trim negligible tails: returns (offset, values) with values rounded to 5 decimals."""
    nz = np.where(p > eps)[0]
    if len(nz) == 0:
        return 0, []
    a, b = int(nz[0]), int(nz[-1])
    return a, [round(float(v), 5) for v in p[a:b + 1]]


def game_markets(r: SimResult, lines: dict | None, key_weights: dict | None = None) -> dict:
    """Probabilities for the main markets plus the distributions behind them."""
    lines = lines or {}
    lo_m, hi_m = -70, 70
    mp = apply_key_numbers(pmf(r.margin, lo_m, hi_m), lo_m, key_weights)
    tp = pmf(r.total, 0, 130)
    h1 = pmf(r.h1.sum(axis=1), 0, 80)
    h2 = pmf(r.h2.sum(axis=1), 0, 90)
    v = np.arange(lo_m, hi_m + 1)
    p_home = float(mp[v > 0].sum()); p_away = float(mp[v < 0].sum()); p_tie = float(mp[v == 0].sum())
    out = {
        "ml": {"home": r4(p_home), "away": r4(p_away), "tie": r4(p_tie), "fair_home": fair_odds(p_home, p_tie), "fair_away": fair_odds(p_away, p_tie)},
        "margin_mean": round(float((mp * v).sum()), 2), "total_mean": round(float(r.total.mean()), 2),
        "h1_mean": round(float(r.h1.sum(axis=1).mean()), 2), "h2_mean": round(float(r.h2.sum(axis=1).mean()), 2),
        "home_pts": round(float(r.pts[:, 0].mean()), 2), "away_pts": round(float(r.pts[:, 1].mean()), 2),
        "ot": r4(r.ot.mean()),
        "dist": {"margin": [lo_m + compress(mp)[0], compress(mp)[1]], "total": list(compress(tp)), "h1": list(compress(h1)), "h2": list(compress(h2)),
                 "home_pts": list(compress(pmf(r.pts[:, 0], 0, 80))), "away_pts": list(compress(pmf(r.pts[:, 1], 0, 80)))},
        "fg": {}, "qb": {},
    }
    # median-style fair lines (the half-point line closest to 50/50)
    for key, arr in (("total", r.total), ("h1", r.h1.sum(axis=1)), ("h2", r.h2.sum(axis=1))):
        out[f"{key}_fair_line"] = fair_line(arr)
    out["spread_fair_line"] = fair_line(r.margin)
    s, t = lines.get("spread"), lines.get("total")
    if s is not None and not (isinstance(s, float) and math.isnan(s)):
        ov, pu, un = over_under(mp, lo_m, s)
        out["spread"] = {"line": s, "home_cover": r4(ov), "push": r4(pu), "away_cover": r4(un)}
    if t is not None and not (isinstance(t, float) and math.isnan(t)):
        ov, pu, un = over_under(tp, 0, t)
        out["total"] = {"line": t, "over": r4(ov), "push": r4(pu), "under": r4(un)}
    for i, side in enumerate(("home", "away")):
        f = pmf(r.fgm[:, i], 0, 8)
        out["fg"][side] = {"pmf": [round(float(x), 5) for x in f], "mean": round(float(r.fgm[:, i].mean()), 3),
                           "over0.5": r4(f[1:].sum()), "over1.5": r4(f[2:].sum()), "over2.5": r4(f[3:].sum()), "over3.5": r4(f[4:].sum())}
        y = r.yds[:, i]
        qs = np.percentile(y, [5, 10, 25, 50, 75, 90, 95])
        yp = pmf(y / 5.0, 0, 120)                                # 5-yard bins, 0..600
        tdp = pmf(r.ptd[:, i], 0, 8)
        out["qb"][side] = {"yds_mean": round(float(y.mean()), 1), "yds_q": [round(float(q), 1) for q in qs], "yds_pmf5": list(compress(yp)),
                           "yds_fair_line": fair_line(y), "db_mean": round(float(r.db[:, i].mean()), 1),
                           "td_pmf": [round(float(x), 5) for x in tdp], "td_mean": round(float(r.ptd[:, i].mean()), 3),
                           "td_over0.5": r4(tdp[1:].sum()), "td_over1.5": r4(tdp[2:].sum()), "td_over2.5": r4(tdp[3:].sum())}
    return out


def fair_line(x: np.ndarray) -> float:
    """The half-point line where over and under are closest to even."""
    med = float(np.median(x))
    cands = [math.floor(med) - 0.5, math.floor(med) + 0.5, math.ceil(med) + 0.5]
    best = min(cands, key=lambda L: abs((x > L).mean() - 0.5))
    return best


def anytime_td(r: SimResult, side: int, players: list[dict]) -> list[dict]:
    """P(player scores at least one offensive touchdown) = 1 - E[(1 - rec share)^passing TDs * (1 - rush share)^rushing TDs]
    over the simulations: exact given the shares, and it keeps the game script (pass-heavy or run-heavy games)."""
    n_p = r.ptd[:, side].astype(int); n_r = r.rtd[:, side].astype(int)
    # tabulate the joint (pass, rush) touchdown counts once
    jp = np.zeros((9, 9))
    np.add.at(jp, (np.minimum(n_p, 8), np.minimum(n_r, 8)), 1)
    jp /= jp.sum()
    a = np.arange(9)
    out = []
    for p in players:
        s_rec, s_rush = p["rec_share"], p["rush_share"]
        none = ((1 - s_rec) ** a)[:, None] * ((1 - s_rush) ** a)[None, :]
        prob = float(1 - (jp * none).sum())
        two = None
        out.append({**p, "p": round(prob, 4), "fair": fair_odds(prob), "two_plus": two})
    out.sort(key=lambda d: -d["p"])
    return out


__all__ = ["game_markets", "anytime_td", "pmf", "over_under", "fair_odds", "american_to_prob", "american_to_decimal", "devig2", "fair_line", "apply_key_numbers"]
