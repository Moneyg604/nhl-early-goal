"""Measured inputs: the league drive tables and the team, quarterback, kicker and player profiles.

Everything here is computed from the per-game records (ingest.py) with explicit weights and shrinkage, so
every number on the page can be recomputed from the raw play-by-play. A team's offense is "touchdowns
over the touchdowns the league would have scored from the same drive situations", shrunk toward the
league with a fixed number of pseudo-drives; the same shape is used for field-goal tries, turnovers,
pace, dropbacks, passing yards, kicker accuracy and touchdown shares.

A drive situation is (half, how the drive started, time left in the half, score state): a drive after a
turnover with five minutes left while down nine is not the same as a drive after a punt with forty seconds
left while ahead, and the league table keeps them apart (cells with few drives lean on their parent cell).
Team effects are multinomial-logit shifts on top of that table.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .config import CFG, ModelConfig, prior_weight

RES = ("TD", "FG", "FGM", "PUNT", "TO", "DOWNS", "EOH", "OPPTD", "SAF")
RES_IDX = {r: i for i, r in enumerate(RES)}
START_CATS = ("KO", "PUNT", "TO")
START_IDX = {s: i for i, s in enumerate(START_CATS)}
N_BUCKETS = 6          # time left in the half at the start of the drive: <1:00, 1:00-2:30, 2:30-5:00, 5-10, 10-15, more
N_STATES = 7           # offense score margin: down 9+, down 4-8, down 1-3, tied, up 1-3, up 4-8, up 9+
HALF_SECONDS = 1800
SYMMETRIC_CONTEXT = ("dome", "wind15", "cold", "division")   # game-level: apply to both offenses
TEAM_CONTEXT = ("rest_adv", "rest_dis", "short_week")        # team-level: own offense


def start_cat(s: str) -> str:
    if s in ("KICKOFF", "ONSIDE_KICK", "OWN_KICKOFF", "", "nan", "None"):
        return "KO"
    if s.startswith("PUNT") or s.startswith("BLOCKED_PUNT") or s.startswith("MUFFED_PUNT"):
        return "PUNT"
    return "TO"


def bucket_of(rem: float) -> int:
    return 0 if rem < 60 else (1 if rem < 150 else (2 if rem < 300 else (3 if rem < 600 else (4 if rem < 900 else 5))))


def state_of(m: float) -> int:
    return 0 if m <= -9 else (1 if m <= -4 else (2 if m < 0 else (3 if m == 0 else (4 if m <= 3 else (5 if m <= 8 else 6)))))


def annotate_spans(g: dict) -> None:
    """Clock each drive consumed until the next possession began (or the half ended): the drive's own time
    plus its last play, the try and the kickoff. Summed over a half this is exactly 30:00."""
    for h in (1, 2):
        ds = [d for d in g["drives"] if d["h"] == h]
        for i, d in enumerate(ds):
            start = rem_at_start(d)
            nxt = rem_at_start(ds[i + 1]) if i + 1 < len(ds) else 0.0
            d["span"] = max(0.0, start - nxt)
    for d in g["drives"]:
        if d["h"] > 2:
            d["span"] = d["secs"]


def rem_at_start(d: dict) -> float:
    return d["eos"] + d["secs"] - (HALF_SECONDS if d["h"] == 1 else 0)


def shrink_logor(obs: float, exp: float, n: float, k: float) -> float:
    """log odds ratio of observed vs expected successes in n trials, shrunk toward 0 with k pseudo-trials."""
    if n <= 0 or exp <= 0 or exp >= n or obs < 0:
        return 0.0
    obs = min(max(obs, 0.25), n - 0.25)
    lo = math.log(obs / (n - obs)) - math.log(exp / (n - exp))
    return lo * n / (n + k)


def shrink_ratio(obs: float, exp: float, n: float, k: float, floor: float = 0.5, cap: float = 2.0) -> float:
    """observed / expected, shrunk toward 1 (log scale) with k pseudo-trials."""
    if n <= 0 or exp <= 0:
        return 1.0
    r = max(obs, 1e-6) / exp
    return float(min(cap, max(floor, math.exp(math.log(r) * n / (n + k)))))


def logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# ------------------------------------------------------------------------------------------------ league
@dataclass
class LeagueTable:
    seasons: list[int]
    games: int = 0
    drives: int = 0
    outcome: np.ndarray = field(default_factory=lambda: np.zeros((2, 3, N_BUCKETS, N_STATES, len(RES))))
    dur_mean: np.ndarray = field(default_factory=lambda: np.full((len(RES), N_BUCKETS), 120.0))
    dur_shape: np.ndarray = field(default_factory=lambda: np.full((len(RES), N_BUCKETS), 3.0))
    dur_state: np.ndarray = field(default_factory=lambda: np.ones((2, N_STATES)))
    db_tab: np.ndarray = field(default_factory=lambda: np.full((len(RES), N_STATES), 3.0))     # dropbacks per drive
    ypdb_tab: np.ndarray = field(default_factory=lambda: np.full(len(RES), 6.0))               # passing yards per dropback
    ypdb_sd: float = 10.0                                                                     # per sqrt(dropback)
    fg_a: float = 5.9
    fg_b: float = -0.095
    fg_dist_p: np.ndarray = field(default_factory=lambda: np.ones(60) / 60)
    xp_make: float = 0.955
    two_rate: float = 0.06
    two_make: float = 0.48
    pass_td_share: float = 0.6
    ypdb: float = 6.5
    rush_base: float = 25.7       # team rushes per game at a level score
    rush_slope: float = 0.24      # ... per point of final margin
    rush_sd: float = 6.1
    ypc: float = 4.3
    comp_rate: float = 0.645
    rec_yds_k: float = 4.3        # player noise: sd = k * sqrt(expected)
    rush_yds_k: float = 4.1
    recs_k: float = 1.05
    home_logor: dict = field(default_factory=lambda: {"TD": 0.0, "FG": 0.0, "TO": 0.0})
    context: dict = field(default_factory=dict)
    tie_rate: float = 0.058
    total_mean: float = 45.0
    total_sd: float = 13.5
    margin_sd: float = 14.0
    h1_share: float = 0.5
    fg_made_per_team: float = 1.7
    season_counts: dict = field(default_factory=dict)
    hist_total: list = field(default_factory=list)
    hist_h1: list = field(default_factory=list)
    hist_h2: list = field(default_factory=list)

    def fg_make(self, dist):
        return 1.0 / (1.0 + np.exp(-(self.fg_a + self.fg_b * np.asarray(dist, dtype=float))))

    def expected_fg_make_rate(self) -> float:
        d = np.arange(18, 78)
        return float((self.fg_dist_p * self.fg_make(d)).sum())

    def describe(self) -> dict:
        r4 = lambda v: round(v, 4) if isinstance(v, float) else v  # noqa: E731
        return {"seasons": self.seasons, "games": self.games, "drives": self.drives, "total_mean": round(self.total_mean, 2),
                "total_sd": round(self.total_sd, 2), "margin_sd": round(self.margin_sd, 2), "tie_rate": round(self.tie_rate, 4),
                "xp_make": round(self.xp_make, 4), "two_rate": round(self.two_rate, 4), "two_make": round(self.two_make, 3),
                "pass_td_share": round(self.pass_td_share, 3), "ypdb": round(self.ypdb, 3), "fg_make_avg": round(self.expected_fg_make_rate(), 3),
                "fg_made_per_team": round(self.fg_made_per_team, 3), "home": {k: r4(v) for k, v in self.home_logor.items()},
                "context": {k: {kk: r4(vv) for kk, vv in v.items()} for k, v in self.context.items()},
                "h1_share": round(self.h1_share, 4), "season_counts": self.season_counts,
                "outcome_overall": {r: round(float(self._overall()[i]), 4) for i, r in enumerate(RES)}}

    def _overall(self) -> np.ndarray:
        w = self._cell_n if hasattr(self, "_cell_n") else None
        if w is None:
            return self.outcome.mean(axis=(0, 1, 2, 3))
        p = (self.outcome * w[..., None]).sum(axis=(0, 1, 2, 3))
        return p / max(p.sum(), 1e-9)


def _fit_logistic(x: np.ndarray, y: np.ndarray, iters: int = 30) -> tuple[float, float]:
    X = np.column_stack([np.ones_like(x, dtype=float), x.astype(float)])
    beta = np.array([3.0, -0.08])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(X @ beta)))
        g = X.T @ (y - p)
        H = (X * (p * (1 - p))[:, None]).T @ X + np.eye(2) * 1e-6
        step = np.linalg.solve(H, g)
        beta = beta + step
        if np.abs(step).max() < 1e-8:
            break
    return float(beta[0]), float(beta[1])


def build_league(games: list[dict], seasons: list[int], cfg: ModelConfig = CFG) -> LeagueTable:
    lt = LeagueTable(seasons=sorted(set(seasons)))
    counts = np.zeros((2, 3, N_BUCKETS, N_STATES, len(RES)))
    durs: dict[tuple[int, int], list[float]] = defaultdict(list)
    db_acc = np.zeros((len(RES), N_STATES, 2))
    py_acc = np.zeros((len(RES), 2))
    py_res, py_db = [], []
    fg_d, fg_m = [], []
    xp_att = xp_made = two_att = two_made = td_pass = td_rush = 0
    totals, margs, h1s, h2s, ties, fgm_team = [], [], [], [], 0, []
    rush_rows = []; rush_tot = ryds_tot = cmp_tot = att_tot = 0
    season_counts: dict[int, int] = defaultdict(int)
    for g in games:
        season_counts[g["season"]] += 1
        for d in g["drives"]:
            if d["h"] > 2 or d["res"] not in RES_IDX:
                continue
            rem = rem_at_start(d)
            b = bucket_of(rem); s = state_of(d.get("m", 0)); ri = RES_IDX[d["res"]]
            counts[d["h"] - 1, START_IDX[start_cat(d["start"])], b, s, ri] += 1
            durs[(ri, b)].append(min(d["span"], max(rem, 1)))
            if "db" in d:
                db_acc[ri, s, 0] += d["db"]; db_acc[ri, s, 1] += 1
                py_acc[ri, 0] += d["py"]; py_acc[ri, 1] += d["db"]
                if d["db"] > 0:
                    py_res.append((ri, d["py"], d["db"]))
        for t in (g["home"], g["away"]):
            for k in g["fg"].get(t, []):
                if 15 <= k["d"] <= 77 and k["r"] in ("made", "missed", "blocked"):
                    fg_d.append(k["d"]); fg_m.append(1 if k["r"] == "made" else 0)
            x = g["xp"].get(t, {})
            xp_att += x.get("att", 0); xp_made += x.get("made", 0); two_att += x.get("two_att", 0); two_made += x.get("two_made", 0)
            td_pass += g["team"][t]["td_pass"]; td_rush += g["team"][t]["td_rush"]
            tm_ = g["team"][t]; m_ = (g["hs"] - g["as"]) if t == g["home"] else (g["as"] - g["hs"])
            rush_rows.append((m_, tm_["rush"])); rush_tot += tm_["rush"]; ryds_tot += tm_["ryds"]; cmp_tot += tm_["cmp"]; att_tot += tm_["att"]
            fgm_team.append(sum(1 for k in g["fg"].get(t, []) if k["r"] == "made"))
        totals.append(g["hs"] + g["as"]); margs.append(g["hs"] - g["as"])
        h1 = sum(g["q"]["home"][:2]) + sum(g["q"]["away"][:2]); h1s.append(h1); h2s.append(g["hs"] + g["as"] - h1)
        ties += int(sum(g["q"]["home"][:4]) == sum(g["q"]["away"][:4]))
    lt.games = len(games); lt.drives = int(counts.sum()); lt.season_counts = dict(sorted(season_counts.items()))
    lt._cell_n = counts.sum(axis=-1)  # type: ignore[attr-defined]
    # outcome table: half marginal -> (half, start, bucket) -> (..., state), each level smoothed toward its parent
    # hierarchy: half -> (half, time left) -> (half, time left, score state) -> (..., how the drive started).
    # Late in a half the score state matters far more than how the drive started, so it sits higher.
    for h in range(2):
        marg = counts[h].sum(axis=(0, 1, 2)); marg = marg / max(marg.sum(), 1)
        for b in range(N_BUCKETS):
            cb = counts[h, :, b].sum(axis=(0, 1))
            m1 = (cb + 10 * marg) / (cb.sum() + 10)
            for st in range(N_STATES):
                cbs = counts[h, :, b, st].sum(axis=0)
                m2 = (cbs + 15 * m1) / (cbs.sum() + 15)
                for s in range(3):
                    c = counts[h, s, b, st]
                    lt.outcome[h, s, b, st] = (c + 25 * m2) / (c.sum() + 25)
    for (ri, b), vals in durs.items():
        a = np.array(vals, dtype=float)
        if len(a) >= 5 and a.std() > 0:
            lt.dur_mean[ri, b] = max(a.mean(), 5.0)
            lt.dur_shape[ri, b] = float(min(40.0, max(0.8, (a.mean() / a.std()) ** 2)))
        elif len(a):
            lt.dur_mean[ri, b] = max(a.mean(), 5.0)
    # score-state pace (leading teams drain the clock): observed / expected seconds on drives with time to spare
    st_acc = np.zeros((2, N_STATES, 2))
    for g in games:
        for d in g["drives"]:
            if d["h"] > 2 or d["res"] not in RES_IDX:
                continue
            b = bucket_of(rem_at_start(d))
            if b < 3:
                continue
            st_acc[d["h"] - 1, state_of(d.get("m", 0)), 0] += d["span"]
            st_acc[d["h"] - 1, state_of(d.get("m", 0)), 1] += lt.dur_mean[RES_IDX[d["res"]], b]
    lt.dur_state = np.where(st_acc[..., 1] > 0, (st_acc[..., 0] + 30 * 150) / (st_acc[..., 1] + 30 * 150), 1.0)
    # passing tables
    if db_acc[..., 1].sum() > 0:
        overall = db_acc[..., 0].sum(axis=1) / np.maximum(db_acc[..., 1].sum(axis=1), 1)
        lt.db_tab = (db_acc[..., 0] + 20 * overall[:, None]) / (db_acc[..., 1] + 20)
        lt.ypdb = float(py_acc[:, 0].sum() / max(py_acc[:, 1].sum(), 1))
        lt.ypdb_tab = (py_acc[:, 0] + 50 * lt.ypdb) / (py_acc[:, 1] + 50)
        if py_res:
            arr = np.array(py_res, dtype=float)
            resid = (arr[:, 1] - lt.ypdb_tab[arr[:, 0].astype(int)] * arr[:, 2]) / np.sqrt(arr[:, 2])
            lt.ypdb_sd = float(np.std(resid))
    if len(fg_d) > 200:
        lt.fg_a, lt.fg_b = _fit_logistic(np.array(fg_d), np.array(fg_m))
        hist = np.bincount(np.clip(np.array(fg_d) - 18, 0, 59), minlength=60).astype(float)
        lt.fg_dist_p = (hist + 0.5) / (hist.sum() + 30)
    if xp_att:
        lt.xp_make = xp_made / xp_att
    tds = td_pass + td_rush
    if tds:
        lt.pass_td_share = td_pass / tds
    if len(rush_rows) > 50:
        X = np.array([m for m, _ in rush_rows], dtype=float); Y = np.array([r for _, r in rush_rows], dtype=float)
        if X.var() > 0:
            b = np.polyfit(X, Y, 1); lt.rush_slope, lt.rush_base = float(b[0]), float(b[1]); lt.rush_sd = float(np.std(Y - np.polyval(b, X)))
        lt.ypc = ryds_tot / max(rush_tot, 1); lt.comp_rate = cmp_tot / max(att_tot, 1)
        lt.two_rate = two_att / tds
    if two_att:
        lt.two_make = two_made / two_att
    lt.home_logor, lt.context = _context_effects(games, lt, cfg)
    if totals:
        lt.total_mean = float(np.mean(totals)); lt.total_sd = float(np.std(totals)); lt.margin_sd = float(np.std(margs))
        lt.h1_share = float(np.sum(h1s) / max(np.sum(totals), 1)); lt.tie_rate = ties / len(totals)
        lt.hist_total = np.bincount(np.clip(totals, 0, 100), minlength=101).tolist()
        lt.hist_h1 = np.bincount(np.clip(h1s, 0, 70), minlength=71).tolist()
        lt.hist_h2 = np.bincount(np.clip(h2s, 0, 70), minlength=71).tolist()
    if fgm_team:
        lt.fg_made_per_team = float(np.mean(fgm_team))
    return lt


def drive_expectations(lt: LeagueTable, d: dict) -> tuple[float, float, float, float, float]:
    """League probabilities of a touchdown, a field-goal try and a turnover, the expected seconds and the
    expected dropbacks for this drive's situation."""
    rem = rem_at_start(d)
    b = bucket_of(rem); s = state_of(d.get("m", 0))
    p = lt.outcome[d["h"] - 1, START_IDX[start_cat(d["start"])], b, s]
    e_td = float(p[RES_IDX["TD"]])
    e_fg = float(p[RES_IDX["FG"]] + p[RES_IDX["FGM"]])
    e_to = float(p[RES_IDX["TO"]] + p[RES_IDX["OPPTD"]])
    ri = RES_IDX.get(d["res"], 3)
    e_secs = float(lt.dur_mean[ri, b]) * (float(lt.dur_state[d["h"] - 1, s]) if b >= 3 else 1.0)
    e_db = float(lt.db_tab[ri, s])
    return e_td, e_fg, e_to, e_secs, e_db


def rest_cat(days: int | None) -> str:
    if days is None:
        return "normal"
    return "short" if days <= 5 else ("long" if days >= 9 else "normal")


def game_context_keys(g: dict, side: str) -> list[str]:
    """Context factor names that apply to `side`'s offense in game g."""
    keys = []
    rest = g.get("rest") or {}
    own, opp = rest.get(side), rest.get("away" if side == "home" else "home")
    if own is not None and opp is not None:
        if own - opp >= 3:
            keys.append("rest_adv")
        elif opp - own >= 3:
            keys.append("rest_dis")
    if own is not None and own <= 5 and (opp is None or opp <= 5):
        keys.append("short_week")
    roof = (g.get("roof") or "").lower()
    if roof in ("dome", "closed"):
        keys.append("dome")
    w = g.get("wind")
    if roof not in ("dome", "closed") and w is not None and w >= 15:
        keys.append("wind15")
    t = g.get("temp")
    if roof not in ("dome", "closed") and t is not None and t <= 32:
        keys.append("cold")
    if g.get("div") == 1:
        keys.append("division")
    return keys


def _context_effects(games: list[dict], lt: LeagueTable, cfg: ModelConfig) -> tuple[dict, dict]:
    acc: dict[str, dict[str, list[float]]] = defaultdict(lambda: {"TD": [0.0, 0.0, 0.0], "FG": [0.0, 0.0, 0.0], "TO": [0.0, 0.0, 0.0]})

    def add(key: str, d: dict):
        e_td, e_fg, e_to, _, _ = drive_expectations(lt, d)
        a = acc[key]
        a["TD"][0] += d["res"] == "TD"; a["TD"][1] += e_td; a["TD"][2] += 1
        a["FG"][0] += d["res"] in ("FG", "FGM"); a["FG"][1] += e_fg; a["FG"][2] += 1
        a["TO"][0] += d["res"] in ("TO", "OPPTD"); a["TO"][1] += e_to; a["TO"][2] += 1

    for g in games:
        keys = {"home": game_context_keys(g, "home"), "away": game_context_keys(g, "away")}
        neutral = (g.get("location") or "Home") == "Neutral"
        for d in g["drives"]:
            if d["h"] > 2 or d["res"] not in RES_IDX:
                continue
            side = "home" if d["t"] == g["home"] else "away"
            if side == "home" and not neutral:
                add("home", d)
            elif side == "away" and not neutral:
                add("away", d)
            for k in keys[side]:
                add(k, d)
    out = {}
    for key, a in acc.items():
        out[key] = {m: shrink_logor(a[m][0], a[m][1], a[m][2], cfg.k_context) for m in ("TD", "FG", "TO")}
        out[key]["n"] = int(a["TD"][2])
        out[key]["raw"] = {m: round(a[m][0] / max(a[m][1], 1e-9), 4) for m in ("TD", "FG", "TO")}
    home = out.pop("home", {"TD": 0.0, "FG": 0.0, "TO": 0.0, "n": 0})
    away = out.pop("away", {"TD": 0.0, "FG": 0.0, "TO": 0.0, "n": 0})
    # home advantage as half the home-vs-away gap (the table itself is the average of the two)
    ha = {m: (home[m] - away[m]) / 2 for m in ("TD", "FG", "TO")}
    ha["n"] = home.get("n", 0) + away.get("n", 0)
    ha["raw_home"] = home.get("raw"); ha["raw_away"] = away.get("raw")
    return ha, out


# ------------------------------------------------------------------------------------------------ profiles
@dataclass
class Side:
    n: float = 0.0
    td: float = 0.0
    td_x: float = 0.0
    fg: float = 0.0
    fg_x: float = 0.0
    to: float = 0.0
    to_x: float = 0.0
    secs: float = 0.0
    secs_x: float = 0.0
    pts: float = 0.0
    db: float = 0.0
    db_x: float = 0.0
    py: float = 0.0
    py_x: float = 0.0
    ptd: float = 0.0
    rtd: float = 0.0
    rush_att: float = 0.0       # rushing attempts (weighted)
    rush_x: float = 0.0         # league rushes expected for the game's score margin
    ryds: float = 0.0

    def add_game(self, tm: dict, margin: float, w: float, lt: LeagueTable) -> None:
        self.rush_att += w * tm["rush"]; self.rush_x += w * (lt.rush_base + lt.rush_slope * margin); self.ryds += w * tm["ryds"]

    def add_drive(self, d: dict, e, w: float, lt: LeagueTable) -> None:
        e_td, e_fg, e_to, e_secs, e_db = e
        self.n += w
        self.td += w * (d["res"] == "TD"); self.td_x += w * e_td
        self.fg += w * (d["res"] in ("FG", "FGM")); self.fg_x += w * e_fg
        self.to += w * (d["res"] in ("TO", "OPPTD")); self.to_x += w * e_to
        self.secs += w * d["span"]; self.secs_x += w * e_secs
        self.pts += w * d["pts"]
        if "db" in d:
            self.db += w * d["db"]; self.db_x += w * e_db
            self.py += w * d["py"]; self.py_x += w * d["db"] * float(lt.ypdb_tab[RES_IDX[d["res"]]])
            self.ptd += w * d.get("ptd", 0); self.rtd += w * d.get("rtd", 0)

    def logors(self, cfg: ModelConfig) -> dict[str, float]:
        return {"TD": shrink_logor(self.td, self.td_x, self.n, cfg.k_drive_team),
                "FG": shrink_logor(self.fg, self.fg_x, self.n, cfg.k_drive_fg),
                "TO": shrink_logor(self.to, self.to_x, self.n, cfg.k_drive_team)}

    def pace(self, cfg: ModelConfig) -> float:
        return shrink_ratio(self.secs, self.secs_x, self.n, cfg.k_pace, 0.75, 1.3)

    def rush_mult(self, lt: LeagueTable, cfg: ModelConfig) -> float:
        return shrink_ratio(self.rush_att, self.rush_x, self.n, cfg.k_dropbacks, 0.7, 1.4)

    def ypc_mult(self, lt: LeagueTable, cfg: ModelConfig) -> float:
        return shrink_ratio(self.ryds, self.rush_att * lt.ypc, self.rush_att, cfg.k_qb_rate, 0.7, 1.4)

    def db_mult(self, cfg: ModelConfig) -> float:
        return shrink_ratio(self.db, self.db_x, self.n, cfg.k_dropbacks, 0.7, 1.4)

    def ypdb_mult(self, cfg: ModelConfig) -> float:
        return shrink_ratio(self.py, self.py_x, self.db, cfg.k_qb_rate, 0.6, 1.5)

    def pass_td_logor(self, lt: LeagueTable, cfg: ModelConfig) -> float:
        n = self.ptd + self.rtd
        return shrink_logor(self.ptd, n * lt.pass_td_share, n, cfg.k_td_share * 2)

    def ppd(self) -> float:
        return self.pts / self.n if self.n else 0.0

    def describe(self, cfg: ModelConfig, lt: LeagueTable) -> dict:
        lo = self.logors(cfg)
        return {"drives": round(self.n, 1), "ppd": round(self.ppd(), 3), "td_rate": round(self.td / self.n, 4) if self.n else None,
                "td_x_rate": round(self.td_x / self.n, 4) if self.n else None, "fg_rate": round(self.fg / self.n, 4) if self.n else None,
                "fg_x_rate": round(self.fg_x / self.n, 4) if self.n else None, "to_rate": round(self.to / self.n, 4) if self.n else None,
                "or_td": round(math.exp(lo["TD"]), 3), "or_fg": round(math.exp(lo["FG"]), 3), "or_to": round(math.exp(lo["TO"]), 3),
                "pace": round(self.pace(cfg), 3), "secs_per_drive": round(self.secs / self.n, 1) if self.n else None,
                "db_mult": round(self.db_mult(cfg), 3), "ypdb": round(self.py / self.db, 2) if self.db else None,
                "ypdb_mult": round(self.ypdb_mult(cfg), 3), "pass_td_share": round(self.ptd / (self.ptd + self.rtd), 3) if (self.ptd + self.rtd) else None,
                "pass_td_or": round(math.exp(self.pass_td_logor(lt, cfg)), 3)}


@dataclass
class QBProfile:
    pid: str
    name: str = ""
    w: float = 0.0
    games: int = 0
    db: float = 0.0
    att: float = 0.0
    cmp: float = 0.0
    yds: float = 0.0
    td: float = 0.0
    int_: float = 0.0
    epa: float = 0.0
    off: Side = field(default_factory=Side)     # his team's drives in the games he was the primary passer
    teams: dict = field(default_factory=dict)
    last_date: str = ""
    last_games: list = field(default_factory=list)

    def describe(self, lt: LeagueTable, cfg: ModelConfig) -> dict:
        return {"id": self.pid, "name": self.name, "games": self.games, "dropbacks": round(self.db), "yards": round(self.yds),
                "ypdb": round(self.yds / self.db, 2) if self.db else None, "ypdb_mult": round(self.off.ypdb_mult(cfg), 3),
                "db_mult": round(self.off.db_mult(cfg), 3), "pass_td": round(self.td), "int": round(self.int_),
                "pass_td_or": round(math.exp(self.off.pass_td_logor(lt, cfg)), 3),
                "epa_per_db": round(self.epa / self.db, 3) if self.db else None,
                "yds_per_game": round(self.yds / self.w, 1) if self.w else None, "td_per_game": round(self.td / self.w, 2) if self.w else None,
                "last_games": self.last_games[-6:]}


@dataclass
class PlayerProfile:
    pid: str
    name: str = ""
    team: str = ""
    w: float = 0.0
    games: int = 0
    car: float = 0.0
    tgt: float = 0.0
    rzc: float = 0.0
    rzt: float = 0.0
    rtd: float = 0.0
    rectd: float = 0.0
    ret_td: float = 0.0
    t_car: float = 0.0
    t_tgt: float = 0.0
    t_rzc: float = 0.0
    t_rzt: float = 0.0
    t_ptd: float = 0.0
    t_rtd: float = 0.0
    recyds: float = 0.0
    ryds: float = 0.0
    recs: float = 0.0
    t_pyds: float = 0.0
    t_rush: float = 0.0
    t_cmp: float = 0.0
    games_td: int = 0
    last_date: str = ""
    recent: list = field(default_factory=list)
    snaps: list = field(default_factory=list)          # (date, offensive snap share, recency weight) in his games with snap data

    def snap_trend(self, cfg: ModelConfig) -> float:
        """Recent snap share (last two games) over his recency-weighted average, pulled halfway to 1 and capped:
        a back who went from 40% to 70% of the snaps when the starter got hurt gets a bigger share now."""
        if len(self.snaps) < 3:
            return 1.0
        w = sum(x[2] for x in self.snaps); base = sum(x[1] * x[2] for x in self.snaps) / w if w else 0
        recent = sum(x[1] for x in self.snaps[-2:]) / 2
        if base <= 0.05:
            return 1.0
        r = recent / base
        return float(min(1.8, max(0.55, 1 + cfg.snap_trend_weight * (r - 1))))

    def shares(self, cfg: ModelConfig) -> tuple[float, float]:
        """(share of the team's passing touchdowns caught, share of the team's rushing touchdowns scored),
        each the player's own rate shrunk toward a usage prior (half overall share, half red-zone share)."""
        k = cfg.k_td_share
        tgt_s = self.tgt / self.t_tgt if self.t_tgt > 0 else 0.0
        rzt_s = self.rzt / self.t_rzt if self.t_rzt > 0 else tgt_s
        car_s = self.car / self.t_car if self.t_car > 0 else 0.0
        rzc_s = self.rzc / self.t_rzc if self.t_rzc > 0 else car_s
        prior_rec = 0.5 * tgt_s + 0.5 * rzt_s
        prior_rush = 0.5 * car_s + 0.5 * rzc_s
        rec = (self.rectd + k * prior_rec) / (self.t_ptd + k)
        rush = (self.rtd + k * prior_rush) / (self.t_rtd + k)
        return float(min(rec, 0.9)), float(min(rush, 0.9))

    def usage(self, cfg: ModelConfig) -> dict:
        """Shares behind the yardage props: receiving yards as a share of the team's passing yards, rushes as a
        share of the team's rushes with his own yards per carry, receptions as a share of the team's completions,
        each shrunk toward zero with k_usage weighted games (a new player starts small)."""
        k = cfg.k_usage
        w = self.w
        f = lambda num, den: (num / den) * (w / (w + k)) if den > 0 else 0.0  # noqa: E731
        ypc = (self.ryds + 4.2 * 20) / (self.car + 20) if self.car > 0 else 4.2
        return {"rec_yds_share": f(self.recyds, self.t_pyds), "car_share": f(self.car, self.t_rush), "ypc": ypc,
                "rec_share": f(self.recs, self.t_cmp), "games_w": round(w, 2)}

    def describe(self, cfg: ModelConfig) -> dict:
        rec, rush = self.shares(cfg)
        return {"id": self.pid, "name": self.name, "team": self.team, "games": self.games,
                "tgt_share": round(self.tgt / self.t_tgt, 3) if self.t_tgt else 0.0, "car_share": round(self.car / self.t_car, 3) if self.t_car else 0.0,
                "rz_tgt_share": round(self.rzt / self.t_rzt, 3) if self.t_rzt else 0.0, "rz_car_share": round(self.rzc / self.t_rzc, 3) if self.t_rzc else 0.0,
                "rec_td_share": round(rec, 3), "rush_td_share": round(rush, 3), "td_games": self.games_td,
                "recent": self.recent[-5:]}


@dataclass
class KickerProfile:
    pid: str
    att: float = 0.0
    made: float = 0.0
    made_x: float = 0.0
    xp_att: float = 0.0
    xp_made: float = 0.0
    long_att: float = 0.0
    long_made: float = 0.0
    games: int = 0
    raw_att: int = 0
    raw_made: int = 0
    last_date: str = ""

    def logor(self, cfg: ModelConfig) -> float:
        return shrink_logor(self.made, self.made_x, self.att, cfg.k_kicker)

    def xp_rate(self, lt: LeagueTable, cfg: ModelConfig) -> float:
        k = cfg.k_kicker
        return (self.xp_made + k * lt.xp_make) / (self.xp_att + k)

    def describe(self, cfg: ModelConfig, lt: LeagueTable) -> dict:
        return {"id": self.pid, "att": self.raw_att, "made": self.raw_made, "pct": round(self.raw_made / self.raw_att, 3) if self.raw_att else None,
                "expected_pct": round(self.made_x / self.att, 3) if self.att else None, "or": round(math.exp(self.logor(cfg)), 3),
                "xp_rate": round(self.xp_rate(lt, cfg), 3), "long_50plus": f"{round(self.long_made)}/{round(self.long_att)}", "games": self.games}


@dataclass
class TeamProfile:
    team: str
    off: Side = field(default_factory=Side)
    def_: Side = field(default_factory=Side)
    off_h: list = field(default_factory=lambda: [Side(), Side()])     # by half (the half-shape factor)
    def_h: list = field(default_factory=lambda: [Side(), Side()])
    games: int = 0
    games_cur: int = 0
    wins_cur: int = 0
    losses_cur: int = 0
    ties_cur: int = 0
    pf_cur: int = 0
    pa_cur: int = 0
    kickers: dict = field(default_factory=dict)
    qbs: dict = field(default_factory=dict)
    qbs_cur: dict = field(default_factory=dict)
    last_kicker: str = ""
    last_qb: str = ""
    last_date: str = ""
    recent: list = field(default_factory=list)
    fg_made_cur: list = field(default_factory=list)
    h1_cur: list = field(default_factory=list)
    h2_cur: list = field(default_factory=list)
    epa_off: float = 0.0
    epa_def: float = 0.0
    plays_off: float = 0.0
    plays_def: float = 0.0
    adv_off: dict = field(default_factory=dict)        # current-season research stats, offense
    adv_def: dict = field(default_factory=dict)        # ... and what the defense allowed

    def adv_rates(self, which: str) -> dict:
        a = self.adv_off if which == "off" else self.adv_def
        f = lambda n, d: round(a.get(n, 0) / a[d], 4) if a.get(d) else None  # noqa: E731
        neu = a.get("neu_n", 0); xn = a.get("neu_xn", 0)
        return {"success": f("succ", "plays"), "explosive": f("expl", "plays"), "third_down": f("third_conv", "third"), "red_zone_td": f("rz_td", "rz"),
                "sack_rate": f("sk", "db"), "pace": round(a["pace_s"] / a["pace_n"], 1) if a.get("pace_n") else None,
                "neutral_pass": round(a["neu_pass"] / neu, 4) if neu else None,
                "proe": round(a["neu_pass"] / neu - a["neu_xpass"] / xn, 4) if (neu and xn) else None,
                "epa_pass": f("pass_epa", "passes"), "epa_rush": f("rush_epa", "runs"), "rz_trips_pg": round(a.get("rz", 0) / a["games"], 2) if a.get("games") else None}

    def primary_qb(self) -> str:
        src = self.qbs_cur or self.qbs
        return max(src, key=src.get) if src else ""

    def describe(self, cfg: ModelConfig, lt: LeagueTable) -> dict:
        return {"team": self.team, "games": self.games, "games_current": self.games_cur,
                "record": f"{self.wins_cur}-{self.losses_cur}" + (f"-{self.ties_cur}" if self.ties_cur else ""),
                "pf": self.pf_cur, "pa": self.pa_cur, "offense": self.off.describe(cfg, lt), "defense": self.def_.describe(cfg, lt),
                "epa_off_per_play": round(self.epa_off / self.plays_off, 3) if self.plays_off else None,
                "epa_def_per_play": round(self.epa_def / self.plays_def, 3) if self.plays_def else None,
                "fg_made_avg": round(float(np.mean(self.fg_made_cur)), 2) if self.fg_made_cur else None,
                "h1_pts_avg": round(float(np.mean(self.h1_cur)), 1) if self.h1_cur else None,
                "h2_pts_avg": round(float(np.mean(self.h2_cur)), 1) if self.h2_cur else None,
                "last_qb": self.last_qb, "last_kicker": self.last_kicker, "recent": self.recent[-6:]}


@dataclass
class Profiles:
    league: LeagueTable
    teams: dict
    qbs: dict
    players: dict
    kickers: dict
    season: int
    data_through: str = ""
    new_qb: dict = field(default_factory=dict)

    def team(self, t: str) -> TeamProfile:
        return self.teams.setdefault(t, TeamProfile(team=t))


def primary_qb(g: dict, t: str) -> str | None:
    q = g["qbs"].get(t) or {}
    return max(q, key=lambda k: q[k]["db"]) if q else None


def build_profiles(games: list[dict], season: int, cfg: ModelConfig = CFG, league: LeagueTable | None = None, snaps: dict | None = None) -> Profiles:
    """Profiles from every game in `games` (all of which must precede the games being predicted)."""
    seasons = sorted({g["season"] for g in games})
    league_seasons = [s for s in seasons if s >= season - cfg.league_seasons + 1] or seasons[-cfg.league_seasons:]
    lt = league or build_league([g for g in games if g["season"] in league_seasons], league_seasons, cfg)
    P = Profiles(league=lt, teams={}, qbs={}, players={}, kickers={}, season=season)
    games = sorted(games, key=lambda g: (g["date"], g["game_id"]))
    team_total: dict[str, int] = defaultdict(int)
    for g in games:
        team_total[g["home"]] += 1; team_total[g["away"]] += 1
    team_seen: dict[str, int] = defaultdict(int)
    nq = {"TD": [0.0, 0.0, 0.0], "FG": [0.0, 0.0, 0.0], "TO": [0.0, 0.0, 0.0], "py": [0.0, 0.0]}
    season_team_games: dict[tuple[int, str], int] = defaultdict(int)
    season_team_qbs: dict[tuple[int, str], set] = defaultdict(set)
    for g in games:
        sw = prior_weight(g["season"], season, cfg)
        cur = g["season"] == season
        for t, opp, side in ((g["home"], g["away"], "home"), (g["away"], g["home"], "away")):
            tp = P.team(t)
            team_seen[t] += 1
            back = team_total[t] - team_seen[t]
            rw = 0.5 ** (back / cfg.recency_half_life_games)
            tp.games += 1; tp.last_date = g["date"]
            pf = g["hs"] if side == "home" else g["as"]; pa = g["as"] if side == "home" else g["hs"]
            if cur:
                tp.games_cur += 1; tp.pf_cur += pf; tp.pa_cur += pa
                tp.wins_cur += pf > pa; tp.losses_cur += pf < pa; tp.ties_cur += pf == pa
                tp.fg_made_cur.append(sum(1 for k in g["fg"].get(t, []) if k["r"] == "made"))
                tp.h1_cur.append(sum(g["q"][side][:2])); tp.h2_cur.append(pf - sum(g["q"][side][:2]))
            tp.recent.append({"date": g["date"], "opp": opp, "home": side == "home", "pf": pf, "pa": pa, "week": g["week"], "season": g["season"]})
            tm = g["team"][t]; om = g["team"][opp]
            if cur:
                for src, dst in ((tm, tp.adv_off), (om, tp.adv_def)):
                    for k2, v2 in (src.get("adv") or {}).items():
                        dst[k2] = dst.get(k2, 0) + v2
                    dst["sk"] = dst.get("sk", 0) + src.get("sk", 0); dst["db"] = dst.get("db", 0) + src.get("db", 0)
                    dst["games"] = dst.get("games", 0) + 1
            tp.off.add_game(tm, pf - pa, sw, lt); tp.def_.add_game(om, pa - pf, sw, lt)
            tp.epa_off += sw * tm["epa"]; tp.plays_off += sw * tm["plays"]
            tp.epa_def += sw * om["epa"]; tp.plays_def += sw * om["plays"]
            # quarterback
            qid = primary_qb(g, t)
            key = (g["season"], t)
            is_new = bool(qid) and season_team_games[key] >= 3 and qid not in season_team_qbs[key]
            season_team_games[key] += 1
            qp = None
            if qid:
                q = g["qbs"][t][qid]
                season_team_qbs[key].add(qid)
                qp = P.qbs.setdefault(qid, QBProfile(pid=qid, name=q["name"]))
                qp.name = q["name"]; qp.w += sw; qp.games += 1; qp.db += sw * q["db"]; qp.att += sw * q["att"]; qp.cmp += sw * q["cmp"]
                qp.yds += sw * q["yds"]; qp.td += sw * q["td"]; qp.int_ += sw * q["int"]; qp.epa += sw * q["epa"]
                qp.teams[t] = qp.teams.get(t, 0.0) + sw; qp.last_date = g["date"]
                qp.last_games.append({"date": g["date"], "team": t, "opp": opp, "db": q["db"], "yds": q["yds"], "td": q["td"], "int": q["int"]})
                tp.qbs[qid] = tp.qbs.get(qid, 0.0) + sw * rw
                if cur:
                    tp.qbs_cur[qid] = tp.qbs_cur.get(qid, 0.0) + rw
                tp.last_qb = qid
            # kicker
            kid = g["kicker"].get(t) or ""
            if kid:
                kp = P.kickers.setdefault(kid, KickerProfile(pid=kid))
                kp.games += 1; kp.last_date = g["date"]
                for k in g["fg"].get(t, []):
                    if 15 <= k["d"] <= 77:
                        kp.att += sw; kp.made += sw * (k["r"] == "made"); kp.made_x += sw * float(lt.fg_make(k["d"]))
                        if cur:
                            kp.raw_att += 1; kp.raw_made += k["r"] == "made"
                        if k["d"] >= 50:
                            kp.long_att += sw; kp.long_made += sw * (k["r"] == "made")
                x = g["xp"].get(t, {}); kp.xp_att += sw * x.get("att", 0); kp.xp_made += sw * x.get("made", 0)
                tp.kickers[kid] = tp.kickers.get(kid, 0.0) + sw; tp.last_kicker = kid
            # skill players
            pl = g["players"].get(t, {})
            t_car = sum(s["car"] for s in pl.values()); t_tgt = sum(s["tgt"] for s in pl.values())
            t_rzc = sum(s.get("rzc", 0) for s in pl.values()); t_rzt = sum(s.get("rzt", 0) for s in pl.values())
            for pid, s in pl.items():
                pp = P.players.setdefault(pid, PlayerProfile(pid=pid, name=s["name"]))
                pp.name = s["name"]; pp.team = t; pp.w += rw; pp.games += 1
                pp.car += rw * s["car"]; pp.tgt += rw * s["tgt"]; pp.rzc += rw * s.get("rzc", 0); pp.rzt += rw * s.get("rzt", 0)
                pp.rtd += rw * s["rtd"]; pp.rectd += rw * s["rectd"]; pp.ret_td += rw * s.get("ret_td", 0)
                pp.t_car += rw * t_car; pp.t_tgt += rw * t_tgt; pp.t_rzc += rw * t_rzc; pp.t_rzt += rw * t_rzt
                pp.t_ptd += rw * tm["td_pass"]; pp.t_rtd += rw * tm["td_rush"]
                pp.recyds += rw * s.get("recyds", 0); pp.ryds += rw * s.get("ryds", 0); pp.recs += rw * s.get("rec", 0)
                pp.t_pyds += rw * tm["pyds"]; pp.t_rush += rw * tm["rush"]; pp.t_cmp += rw * tm["cmp"]
                pp.games_td += (s["rtd"] + s["rectd"]) > 0; pp.last_date = g["date"]
                pp.recent.append({"date": g["date"], "team": t, "car": s["car"], "tgt": s["tgt"], "td": s["rtd"] + s["rectd"]})
                sp = (snaps or {}).get(g["game_id"], {}).get(pid)
                if sp is not None:
                    pp.snaps.append((g["date"], sp, rw))
            # drives
            for d in g["drives"]:
                if d["h"] > 2 or d["res"] not in RES_IDX:
                    continue
                e = drive_expectations(lt, d)
                if d["t"] == t:
                    tp.off.add_drive(d, e, sw, lt)
                    tp.off_h[d["h"] - 1].add_drive(d, e, sw, lt)
                    if qp is not None:
                        qp.off.add_drive(d, e, sw, lt)
                    if is_new:
                        nq["TD"][0] += d["res"] == "TD"; nq["TD"][1] += e[0]; nq["TD"][2] += 1
                        nq["FG"][0] += d["res"] in ("FG", "FGM"); nq["FG"][1] += e[1]; nq["FG"][2] += 1
                        nq["TO"][0] += d["res"] in ("TO", "OPPTD"); nq["TO"][1] += e[2]; nq["TO"][2] += 1
                        if "db" in d:
                            nq["py"][0] += d["py"]; nq["py"][1] += d["db"] * float(lt.ypdb_tab[RES_IDX[d["res"]]])
                else:
                    tp.def_.add_drive(d, e, sw, lt)
                    tp.def_h[d["h"] - 1].add_drive(d, e, sw, lt)
    P.new_qb = {m: shrink_logor(*nq[m], cfg.k_context) for m in ("TD", "FG", "TO")}
    P.new_qb["ypdb_mult"] = shrink_ratio(nq["py"][0], nq["py"][1], nq["py"][1] / max(lt.ypdb, 1), cfg.k_qb_rate)
    P.new_qb["n"] = int(nq["TD"][2])
    P.data_through = games[-1]["date"] if games else ""
    return P


__all__ = ["LeagueTable", "TeamProfile", "QBProfile", "PlayerProfile", "KickerProfile", "Profiles", "build_league", "build_profiles",
           "drive_expectations", "start_cat", "bucket_of", "state_of", "rem_at_start", "rest_cat", "game_context_keys", "primary_qb",
           "RES", "RES_IDX", "START_IDX", "START_CATS", "N_BUCKETS", "N_STATES", "SYMMETRIC_CONTEXT", "TEAM_CONTEXT", "logit", "sigmoid"]
