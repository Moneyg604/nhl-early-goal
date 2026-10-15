"""Turn a simulated game into market probabilities and compact distributions for the page.

Every market comes from the same simulation, so a total, a half total, a team's field goals and a
quarterback's passing all agree with each other. Distributions are stored as probability mass functions
so the page can price any line the book posts (including pushes on whole numbers).
"""
from __future__ import annotations

import math

import numpy as np

from .sim import SimResult


def pmf(x: np.ndarray, lo: int, hi: int, w: np.ndarray | None = None) -> np.ndarray:
    """Probability mass function of rounded values in [lo, hi], optionally with per-simulation weights."""
    x = np.clip(np.rint(x).astype(int), lo, hi) - lo
    if w is None:
        return np.bincount(x, minlength=hi - lo + 1) / max(len(x), 1)
    out = np.bincount(x, weights=w, minlength=hi - lo + 1)
    return out / max(out.sum(), 1e-12)


def wmean(x: np.ndarray, w: np.ndarray | None) -> float:
    return float(np.average(x, weights=w)) if w is not None else float(np.mean(x))


def wquantile(x: np.ndarray, qs, w: np.ndarray | None) -> np.ndarray:
    """Weighted percentiles (qs in 0..100)."""
    if w is None:
        return np.percentile(x, qs)
    o = np.argsort(x); xs = x[o]; ws = w[o]
    c = np.cumsum(ws); c = c / c[-1]
    return np.interp(np.asarray(qs, dtype=float) / 100.0, c, xs)


def wprob(mask: np.ndarray, w: np.ndarray | None) -> float:
    return float(np.average(mask, weights=w)) if w is not None else float(np.mean(mask))


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


def ml_weights(r: SimResult, lines: dict | None) -> tuple[np.ndarray | None, dict]:
    """Per-simulation weights that make the simulated winner and the simulated cover match the market's
    de-vigged moneyline and spread prices.

    The simulated margin is about 7% wider than real NFL margins around the closing spread (sd 13.8 vs 12.9 in
    2023-25), so on its own it understates favourites (a 7.5-point favourite came out near 70% where the market
    says 78%). Walk-forward, the market moneyline beat the raw simulation in both test seasons (log loss 0.5875
    vs 0.5948 in 2024, 0.6094 vs 0.6115 in 2025). Reweighting to the moneyline alone pushed favourites' cover
    probabilities above 50%, which the results did not support, so the spread price is matched as well: three
    groups of simulated games (wins that cover, wins that do not, losses) get one weight each; ties and pushes
    keep their simulated share. Every simulated game keeps its full joint outcome, so same-game parlays and
    the derived markets stay consistent with both prices."""
    lines = lines or {}
    pm, _ = devig2(lines.get("home_ml"), lines.get("away_ml"))
    S = lines.get("spread")
    if pm is None:
        return None, {"applied": False}
    pc, _ = devig2(lines.get("home_spread_odds"), lines.get("away_spread_odds"))
    m = r.margin.astype(float)
    n = len(m)
    P = lambda mask: float(mask.sum()) / n  # noqa: E731
    t = P(m == 0)
    meta = {"applied": True, "market_home": round(pm, 4), "sim_home": round(P(m > 0) / max(1e-9, 1 - t), 4)}
    w = np.ones(n)
    if S is None or pc is None or S == 0 or (isinstance(S, float) and math.isnan(S)):
        ph, pa = P(m > 0), P(m < 0)
        w[m > 0] = (1 - t) * pm / ph; w[m < 0] = (1 - t) * (1 - pm) / pa
        meta["matched"] = "moneyline"
        return w, meta
    q = P(m == S)
    T_win, T_cov = (1 - t) * pm, (1 - q) * pc
    g1 = (m > 0) & (m > S)
    if S > 0:
        g2 = (m > 0) & (m < S); g4 = (m < 0)
        w1 = T_cov / max(P(g1), 1e-9)
        w2 = (T_win - w1 * P(g1) - P((m > 0) & (m == S))) / max(P(g2), 1e-9)
        rest = 1 - t - q - w1 * P(g1) - w2 * P(g2)
        w4 = rest / max(P(g4), 1e-9)
        ws = {"win_cover": w1, "win_no_cover": w2, "loss": w4}
        masks = (g1, g2, g4)
    else:
        g3 = (m < 0) & (m > S); g4 = (m < 0) & (m < S)
        w1 = T_win / max(P(g1), 1e-9)
        w3 = (T_cov - w1 * P(g1) - P((m == 0) & (m > S))) / max(P(g3), 1e-9)
        rest = 1 - t - q - w1 * P(g1) - w3 * P(g3)
        w4 = rest / max(P(g4), 1e-9)
        ws = {"win": w1, "loss_cover": w3, "loss_no_cover": w4}
        masks = (g1, g3, g4)
    if min(ws.values()) <= 0.05 or min(P(mk) for mk in masks) <= 0:
        # the two prices cannot both be met with this simulation's shape: match the moneyline only
        w = np.ones(n); ph, pa = P(m > 0), P(m < 0)
        w[m > 0] = (1 - t) * pm / ph; w[m < 0] = (1 - t) * (1 - pm) / pa
        meta["matched"] = "moneyline"
        return w, meta
    for mask, val in zip(masks, ws.values()):
        w[mask] = val
    meta.update({"matched": "moneyline and spread", "market_cover": round(pc, 4), "weights": {k: round(v, 4) for k, v in ws.items()}})
    return w, meta


def wpmf(x: np.ndarray, lo: int, hi: int, w: np.ndarray | None) -> np.ndarray:
    return pmf(x, lo, hi, w)


def game_markets(r: SimResult, lines: dict | None, key_weights: dict | None = None, w: np.ndarray | None = None) -> dict:
    """Probabilities for the main markets plus the distributions behind them.

    Every market, including the halves, field goals and passing, is read from the same market-reweighted
    simulations (markets.ml_weights) so the page shows one joint distribution; same-game parlays price
    from the same weights."""
    lines = lines or {}
    lo_m, hi_m = -70, 70
    if w is None:
        w, wmeta = ml_weights(r, lines)
    else:
        _, wmeta = ml_weights(r, lines)
    mp = apply_key_numbers(pmf(r.margin, lo_m, hi_m, w), lo_m, key_weights)
    tot = r.total; h1s = r.h1.sum(axis=1); h2s = r.h2.sum(axis=1)
    tp = pmf(tot, 0, 130, w)
    h1 = pmf(h1s, 0, 80, w)
    h2 = pmf(h2s, 0, 90, w)
    v = np.arange(lo_m, hi_m + 1)
    p_home = float(mp[v > 0].sum()); p_away = float(mp[v < 0].sum()); p_tie = float(mp[v == 0].sum())
    out = {
        "ml": {"home": r4(p_home), "away": r4(p_away), "tie": r4(p_tie), "fair_home": fair_odds(p_home, p_tie), "fair_away": fair_odds(p_away, p_tie)},
        "margin_mean": round(float((mp * v).sum()), 2), "total_mean": round(wmean(tot, w), 2),
        "h1_mean": round(wmean(h1s, w), 2), "h2_mean": round(wmean(h2s, w), 2),
        "home_pts": round(wmean(r.pts[:, 0], w), 2), "away_pts": round(wmean(r.pts[:, 1], w), 2),
        "ot": r4(wprob(r.ot, w)), "ml_calibration": wmeta,
        "dist": {"margin": [lo_m + compress(mp)[0], compress(mp)[1]], "total": list(compress(tp)), "h1": list(compress(h1)), "h2": list(compress(h2)),
                 "home_pts": list(compress(pmf(r.pts[:, 0], 0, 80, w))), "away_pts": list(compress(pmf(r.pts[:, 1], 0, 80, w)))},
        "fg": {}, "qb": {},
    }
    # median-style fair lines (the half-point line closest to 50/50)
    for key, arr in (("total", tot), ("h1", h1s), ("h2", h2s)):
        out[f"{key}_fair_line"] = fair_line(arr, w)
    out["spread_fair_line"] = fair_line(r.margin, w)
    s, t = lines.get("spread"), lines.get("total")
    if s is not None and not (isinstance(s, float) and math.isnan(s)):
        ov, pu, un = over_under(mp, lo_m, s)
        out["spread"] = {"line": s, "home_cover": r4(ov), "push": r4(pu), "away_cover": r4(un)}
    if t is not None and not (isinstance(t, float) and math.isnan(t)):
        ov, pu, un = over_under(tp, 0, t)
        out["total"] = {"line": t, "over": r4(ov), "push": r4(pu), "under": r4(un)}
    for i, side in enumerate(("home", "away")):
        f = pmf(r.fgm[:, i], 0, 8, w)
        out["fg"][side] = {"pmf": [round(float(x), 5) for x in f], "mean": round(wmean(r.fgm[:, i], w), 3),
                           "over0.5": r4(f[1:].sum()), "over1.5": r4(f[2:].sum()), "over2.5": r4(f[3:].sum()), "over3.5": r4(f[4:].sum())}
        y = r.yds[:, i]
        qs = wquantile(y, [5, 10, 25, 50, 75, 90, 95], w)
        yp = pmf(y / 5.0, 0, 120, w)                             # 5-yard bins, 0..600
        tdp = pmf(r.ptd[:, i], 0, 8, w)
        out["qb"][side] = {"yds_mean": round(wmean(y, w), 1), "yds_q": [round(float(q), 1) for q in qs], "yds_pmf5": list(compress(yp)),
                           "yds_fair_line": fair_line(y, w), "db_mean": round(wmean(r.db[:, i], w), 1),
                           "td_pmf": [round(float(x), 5) for x in tdp], "td_mean": round(wmean(r.ptd[:, i], w), 3),
                           "td_over0.5": r4(tdp[1:].sum()), "td_over1.5": r4(tdp[2:].sum()), "td_over2.5": r4(tdp[3:].sum())}
    return out


def fair_line(x: np.ndarray, w: np.ndarray | None = None) -> float:
    """The half-point line where over and under are closest to even."""
    med = float(wquantile(x, [50], w)[0])
    cands = [math.floor(med) - 0.5, math.floor(med) + 0.5, math.ceil(med) + 0.5]
    best = min(cands, key=lambda L: abs(wprob(x > L, w) - 0.5))
    return best


def anytime_td(r: SimResult, side: int, players: list[dict], w: np.ndarray | None = None) -> list[dict]:
    """P(player scores at least one offensive touchdown) = 1 - E[(1 - rec share)^passing TDs * (1 - rush share)^rushing TDs]
    over the (market-reweighted) simulations: exact given the shares, and it keeps the game script."""
    n_p = r.ptd[:, side].astype(int); n_r = r.rtd[:, side].astype(int)
    # tabulate the joint (pass, rush) touchdown counts once
    jp = np.zeros((9, 9))
    np.add.at(jp, (np.minimum(n_p, 8), np.minimum(n_r, 8)), np.ones(len(n_p)) if w is None else w)
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


__all__ = ["game_markets", "anytime_td", "pmf", "over_under", "fair_odds", "american_to_prob", "american_to_decimal", "devig2", "fair_line", "apply_key_numbers", "wmean", "wquantile", "wprob", "ml_weights", "wpmf"]
