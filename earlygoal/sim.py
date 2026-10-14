"""Vectorised Monte Carlo over the GameModel (default 100,000 paths per game).

Because the hazards are piecewise constant, goal counts in every bin are
Poisson and can be drawn exactly in one numpy call per bin. The simulation
exists for the joint quantities (period winner, full-game result including
OT/shootout, spread with empty-net dynamics, score distribution). The
first-5 / first-10 probabilities are also available analytically; both are
reported so the Monte Carlo error is visible rather than hidden.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .model import GameModel


@dataclass
class SimResult:
    sims: int
    # headline markets
    p_no_goal_5: float
    p_no_goal_10: float
    p_no_goal_5_analytic: float
    p_no_goal_10_analytic: float
    mc_se_5: float
    mc_se_10: float
    first_goal_minute_hist: list          # P(first goal in [m, m+1)) for m in 0..9
    # first period
    p1_home_win: float
    p1_tie: float
    p1_away_win: float
    p1_total_dist: list                   # P(0), P(1), P(2), P(3+)
    p1_mean_total: float
    # full game
    fg_home_win: float                    # incl OT/SO
    fg_away_win: float
    fg_home_reg_win: float
    fg_away_reg_win: float
    fg_reg_tie: float
    fg_home_cover_m15: float              # home -1.5
    fg_away_cover_m15: float              # away -1.5
    fg_home_cover_p15: float              # home +1.5
    fg_away_cover_p15: float              # away +1.5
    fg_mean_home: float
    fg_mean_away: float
    fg_over_55: float
    fg_over_65: float
    fg_over_45: float                     # total >= 5 (shootout winner credited one goal, as books settle it)
    home_over_15: float                   # home team scores 2+
    away_over_15: float
    p1_under_25: float                    # first period 2 goals or fewer
    fg_total_dist: list                   # P(total = k) for k in 0..10+
    median_score: tuple
    extras: dict = field(default_factory=dict)


def simulate(gm: GameModel, sims: int = 100_000, seed: int | None = None) -> SimResult:
    rng = np.random.default_rng(seed)
    n = sims
    h = np.zeros(n, dtype=np.int16)
    a = np.zeros(n, dtype=np.int16)
    h5 = a5 = h10 = a10 = h20 = a20 = None
    first_goal = np.full(n, 99.0)

    nb = len(gm.bins)
    for i, (s, e) in enumerate(gm.bins):
        length = e - s
        if i == nb - 1:
            # empty-net window (58:00-60:00): rates depend on the score state
            diff = h.astype(np.int32) - a.astype(np.int32)
            lh = np.full(n, gm.lam_home[i])
            la = np.full(n, gm.lam_away[i])
            home_leads = (diff == 1) | (diff == 2)
            away_leads = (diff == -1) | (diff == -2)
            lh[home_leads] = gm.en_leader_home
            la[home_leads] = gm.en_trailer_away
            la[away_leads] = gm.en_leader_away
            lh[away_leads] = gm.en_trailer_home
            gh = rng.poisson(lh * length)
            ga = rng.poisson(la * length)
        else:
            gh = rng.poisson(gm.lam_home[i] * length, n)
            ga = rng.poisson(gm.lam_away[i] * length, n)
        # first-goal timing (only matters inside the first 10 minutes, where bins are 1 minute)
        if e <= 10:
            scored = (gh + ga) > 0
            newly = scored & (first_goal > 98)
            first_goal[newly] = s + rng.uniform(0, length, newly.sum())
        h = h + gh
        a = a + ga
        if e == 5:
            h5, a5 = h.copy(), a.copy()
        if e == 10:
            h10, a10 = h.copy(), a.copy()
        if e == 20:
            h20, a20 = h.copy(), a.copy()

    # ---- overtime / shootout
    reg_diff = h.astype(np.int32) - a.astype(np.int32)
    tied = reg_diff == 0
    n_t = int(tied.sum())
    home_win = reg_diff > 0
    away_win = reg_diff < 0
    ot_goal_rate = gm.ot_rate_home + gm.ot_rate_away
    p_ot_goal = 1 - math.exp(-ot_goal_rate * 5.0)
    share_home = gm.ot_rate_home / ot_goal_rate if ot_goal_rate > 0 else 0.5
    if n_t:
        u = rng.random(n_t)
        ot_scored = u < p_ot_goal
        who = rng.random(n_t) < share_home
        so = rng.random(n_t) < gm.so_home_win
        home_ot = np.where(ot_scored, who, so)
        idx = np.flatnonzero(tied)
        home_win[idx] = home_ot
        away_win[idx] = ~home_ot
        # final score including OT/SO winner gets +1
        h[idx[home_ot]] += 1
        a[idx[~home_ot]] += 1

    final_diff = h.astype(np.int32) - a.astype(np.int32)
    total = h.astype(np.int32) + a.astype(np.int32)
    t5 = h5 + a5
    t10 = h10 + a10
    p5 = float((t5 == 0).mean())
    p10 = float((t10 == 0).mean())
    p1d = h20.astype(np.int32) - a20.astype(np.int32)
    p1t = h20.astype(np.int32) + a20.astype(np.int32)

    hist = [float(((first_goal >= m) & (first_goal < m + 1)).mean()) for m in range(10)]
    tot_dist = [float((total == k).mean()) for k in range(10)] + [float((total >= 10).mean())]

    return SimResult(
        sims=n,
        p_no_goal_5=p5,
        p_no_goal_10=p10,
        p_no_goal_5_analytic=gm.p_no_goal_before(5),
        p_no_goal_10_analytic=gm.p_no_goal_before(10),
        mc_se_5=math.sqrt(p5 * (1 - p5) / n),
        mc_se_10=math.sqrt(p10 * (1 - p10) / n),
        first_goal_minute_hist=hist,
        p1_home_win=float((p1d > 0).mean()),
        p1_tie=float((p1d == 0).mean()),
        p1_away_win=float((p1d < 0).mean()),
        p1_total_dist=[float((p1t == 0).mean()), float((p1t == 1).mean()), float((p1t == 2).mean()), float((p1t >= 3).mean())],
        p1_mean_total=float(p1t.mean()),
        fg_home_win=float(home_win.mean()),
        fg_away_win=float(away_win.mean()),
        fg_home_reg_win=float((reg_diff > 0).mean()),
        fg_away_reg_win=float((reg_diff < 0).mean()),
        fg_reg_tie=float(tied.mean()),
        fg_home_cover_m15=float((final_diff >= 2).mean()),
        fg_away_cover_m15=float((final_diff <= -2).mean()),
        fg_home_cover_p15=float((final_diff >= -1).mean()),
        fg_away_cover_p15=float((final_diff <= 1).mean()),
        fg_mean_home=float(h.mean()),
        fg_mean_away=float(a.mean()),
        fg_over_55=float((total > 5.5).mean()),
        fg_over_65=float((total > 6.5).mean()),
        fg_over_45=float((total > 4.5).mean()),
        home_over_15=float((h >= 2).mean()),
        away_over_15=float((a >= 2).mean()),
        p1_under_25=float((p1t <= 2).mean()),
        fg_total_dist=tot_dist,
        median_score=(int(np.median(h)), int(np.median(a))),
        extras={
            "p_ot_goal": p_ot_goal,
            "p_reg_tie": float(tied.mean()),
            "exp_goals_reg_home": gm.expected_goals()[0],
            "exp_goals_reg_away": gm.expected_goals()[1],
        },
    )
