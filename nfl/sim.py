"""Drive-by-drive Monte Carlo of an NFL game, vectorized over the simulations.

Each simulated drive draws its result (touchdown, field goal made / missed, punt, turnover, turnover on
downs, end of half, defensive touchdown, safety) from the league table for its situation (half, how it
started, time left, score margin), shifted by the two teams' measured effects, then draws how long it
took from the league's duration distribution for that result and time bucket (scaled by both teams'
pace). Points follow from the result, including extra points and two-point tries. Passing comes from
the same drives: dropbacks per drive depend on the drive result and score state; yards per dropback on
the result, the quarterback and the pass defense. Overtime is played when regulation ends tied (both
teams possess unless the first scores... modern rules: both teams get the ball; then sudden death; ten
minutes; ties allowed).

Everything the markets need is recorded per simulation: points by half, field goals made, passing and
rushing touchdowns, the starters' passing yards, dropbacks and touchdown passes.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .features import N_STATES, RES, RES_IDX, LeagueTable

TD, FG, FGM, PUNT, TO, DOWNS, EOH, OPPTD, SAF = (RES_IDX[r] for r in RES)
NEXT_START = np.array([0, 0, 2, 1, 2, 2, 0, 0, 1])   # start category of the next drive after each result (KO, PUNT, TO)


@dataclass
class SideInputs:
    shift: np.ndarray                  # log multipliers on the 9 outcome probabilities when this side has the ball: (9,) or (2 halves, 9)
    pace: float = 1.0                  # drive-duration multiplier when this side has the ball
    make_shift: float = 0.0            # field-goal make logit shift (kicker, weather)
    xp: float = 0.955                  # extra-point make probability
    db_mult: float = 1.0               # dropbacks per drive multiplier
    ypdb_mult: float = 1.0             # passing yards per dropback multiplier
    p_pass_td: float = 0.61            # probability a touchdown is a touchdown pass


@dataclass
class SimResult:
    n: int
    pts: np.ndarray                    # (n, 2) home, away final (with overtime)
    h1: np.ndarray                     # (n, 2) first-half points
    fgm: np.ndarray                    # (n, 2) field goals made (with overtime)
    fga: np.ndarray
    ptd: np.ndarray                    # (n, 2) passing touchdowns
    rtd: np.ndarray                    # (n, 2) rushing touchdowns
    yds: np.ndarray                    # (n, 2) passing yards
    db: np.ndarray                     # (n, 2) dropbacks
    ot: np.ndarray                     # (n,) bool
    drives: np.ndarray                 # (n, 2) offensive drives
    q4_lead_big: np.ndarray = field(default_factory=lambda: np.zeros(0))

    @property
    def h2(self) -> np.ndarray:
        return self.pts - self.h1

    @property
    def total(self) -> np.ndarray:
        return self.pts.sum(axis=1)

    @property
    def margin(self) -> np.ndarray:
        return self.pts[:, 0] - self.pts[:, 1]


def _state(m: np.ndarray) -> np.ndarray:
    return np.where(m <= -9, 0, np.where(m <= -4, 1, np.where(m < 0, 2, np.where(m == 0, 3, np.where(m <= 3, 4, np.where(m <= 8, 5, 6))))))


def _bucket(rem: np.ndarray) -> np.ndarray:
    return np.where(rem < 60, 0, np.where(rem < 150, 1, np.where(rem < 300, 2, np.where(rem < 600, 3, np.where(rem < 900, 4, 5)))))


def _make_share(lt: LeagueTable) -> np.ndarray:
    o = lt.outcome
    return o[..., FG] / np.maximum(o[..., FG] + o[..., FGM], 1e-9)


def simulate(lt: LeagueTable, home: SideInputs, away: SideInputs, n: int = 100_000, seed: int | None = None,
             max_drives_per_half: int = 20) -> SimResult:
    rng = np.random.default_rng(seed)
    sides = (home, away)
    shift = np.stack([np.broadcast_to(np.asarray(s.shift, dtype=float), (2, len(RES))) for s in sides])   # (side, half, 9)
    pace = np.array([s.pace for s in sides])
    mk = np.array([s.make_shift for s in sides])
    xp = np.array([s.xp for s in sides])
    dbm = np.array([s.db_mult for s in sides])
    ym = np.array([s.ypdb_mult for s in sides])
    ppt = np.array([s.p_pass_td for s in sides])
    base_make = _make_share(lt)
    two_rate, two_make = lt.two_rate, lt.two_make
    sd = lt.ypdb_sd

    pts = np.zeros((n, 2), dtype=np.int32)
    h1 = np.zeros((n, 2), dtype=np.int32)
    fgm = np.zeros((n, 2), dtype=np.int16)
    fga = np.zeros((n, 2), dtype=np.int16)
    ptd = np.zeros((n, 2), dtype=np.int16)
    rtd = np.zeros((n, 2), dtype=np.int16)
    yds = np.zeros((n, 2), dtype=np.float32)
    dbs = np.zeros((n, 2), dtype=np.int16)
    drv = np.zeros((n, 2), dtype=np.int16)
    first = rng.integers(0, 2, n)                                      # receives the opening kickoff
    allrows = np.arange(n)

    def run_drive(idx: np.ndarray, off: np.ndarray, start: np.ndarray, rem: np.ndarray, h: int, ot: bool = False):
        """Play one drive for the sims in idx. Returns (result, duration)."""
        m = pts[idx, off] - pts[idx, 1 - off]
        st = _state(m)
        b = _bucket(rem) if not ot else _bucket(rem)
        hh = 1 if (h == 2 or ot) else 0
        p = lt.outcome[hh, start, b, st].copy()                       # (k, 9)
        mk_base = base_make[hh, start, b, st]
        p *= np.exp(shift[off, hh])
        att = p[:, FG] + p[:, FGM]
        lo = np.log(np.clip(mk_base, 1e-4, 1 - 1e-4) / np.clip(1 - mk_base, 1e-4, 1)) + mk[off]
        make = 1 / (1 + np.exp(-lo))
        p[:, FG] = att * make; p[:, FGM] = att * (1 - make)
        if ot:
            p[:, EOH] *= 0.15                                          # ten-minute period: few drives end on the clock
        p /= p.sum(axis=1, keepdims=True)
        u = rng.random(len(idx))
        res = (p.cumsum(axis=1) < u[:, None]).sum(axis=1)
        res = np.minimum(res, len(RES) - 1)
        shape = lt.dur_shape[res, b]
        mean = lt.dur_mean[res, b] * pace[off] * np.where(b >= 3, lt.dur_state[hh][st], 1.0)
        dur = rng.gamma(shape, mean / shape)
        # a drive that would outlast the clock ends the half: scores stand (hurry-up), anything else is the end of the half
        over = (dur >= rem) & ~((res == TD) | (res == FG) | (res == OPPTD) | (res == SAF))
        res = np.where(over, EOH, res)
        dur = np.where((res == EOH) | (dur >= rem), rem, dur)
        # scoring
        o, dfn = off, 1 - off
        is_td = res == TD
        if is_td.any():
            k = idx[is_td]; ok = o[is_td]
            two = rng.random(len(k)) < two_rate
            extra = np.where(two, 2 * (rng.random(len(k)) < two_make), 1 * (rng.random(len(k)) < xp[ok]))
            pts[k, ok] += 6 + extra
            pas = rng.random(len(k)) < ppt[ok]
            ptd[k, ok] += pas; rtd[k, ok] += ~pas
        is_fg = res == FG
        if is_fg.any():
            pts[idx[is_fg], o[is_fg]] += 3
            fgm[idx[is_fg], o[is_fg]] += 1
        is_fa = (res == FG) | (res == FGM)
        if is_fa.any():
            fga[idx[is_fa], o[is_fa]] += 1
        is_opp = res == OPPTD
        if is_opp.any():
            k = idx[is_opp]; dk = dfn[is_opp]
            pts[k, dk] += 6 + (rng.random(len(k)) < 0.95)
        is_saf = res == SAF
        if is_saf.any():
            pts[idx[is_saf], dfn[is_saf]] += 2
        # passing on the drive
        lam = lt.db_tab[res, st] * dbm[o]
        nd = rng.poisson(lam)
        y = nd * lt.ypdb_tab[res] * ym[o] + rng.standard_normal(len(idx)) * sd * np.sqrt(nd)
        y = np.maximum(y, -10.0 * (nd > 0))
        np.add.at(yds, (idx, o), y.astype(np.float32))
        np.add.at(dbs, (idx, o), nd.astype(np.int16))
        np.add.at(drv, (idx, o), 1)
        return res, dur

    for h in (1, 2):
        rem = np.full(n, 1800.0)
        off = np.where(h == 1, first, 1 - first)
        start = np.zeros(n, dtype=np.int64)
        active = np.ones(n, dtype=bool)
        for _ in range(max_drives_per_half):
            idx = allrows[active]
            if len(idx) == 0:
                break
            res, dur = run_drive(idx, off[idx], start[idx], rem[idx], h)
            rem[idx] = rem[idx] - dur
            # possession and start of the next drive
            same = res == OPPTD                                        # defense scored and kicks off back to this offense
            off[idx] = np.where(same, off[idx], 1 - off[idx])
            start[idx] = NEXT_START[res]
            done = (res == EOH) | (rem[idx] <= 0.5)
            active[idx[done]] = False
        if h == 1:
            h1[:] = pts

    # overtime (regular season): ten minutes, both teams possess, then sudden death; may end tied
    tied = pts[:, 0] == pts[:, 1]
    ot_flag = tied.copy()
    if tied.any():
        idx_all = allrows[tied]
        rem = np.full(len(idx_all), 600.0)
        off = rng.integers(0, 2, len(idx_all))
        start = np.zeros(len(idx_all), dtype=np.int64)
        poss = np.zeros(len(idx_all), dtype=np.int64)
        active = np.ones(len(idx_all), dtype=bool)
        for _ in range(8):
            a = np.where(active)[0]
            if len(a) == 0:
                break
            idx = idx_all[a]
            res, dur = run_drive(idx, off[a], start[a], rem[a], 2, ot=True)
            rem[a] -= dur
            poss[a] += 1
            off[a] = np.where(res == OPPTD, off[a], 1 - off[a])
            start[a] = NEXT_START[res]
            diff = pts[idx, 0] != pts[idx, 1]
            over = (rem[a] <= 0.5) | (res == EOH) | (res == OPPTD) | (res == SAF) | ((poss[a] >= 2) & diff)
            active[a[over]] = False
    return SimResult(n=n, pts=pts, h1=h1, fgm=fgm, fga=fga, ptd=ptd, rtd=rtd, yds=yds, db=dbs, ot=ot_flag, drives=drv)


def neutral_side(lt: LeagueTable) -> SideInputs:
    return SideInputs(shift=np.zeros(len(RES)), xp=lt.xp_make, p_pass_td=lt.pass_td_share)


__all__ = ["SideInputs", "SimResult", "simulate", "neutral_side", "N_STATES"]
