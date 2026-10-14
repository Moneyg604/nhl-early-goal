"""Direct model for the first-5 / first-10 no-goal markets.

The hazard chain in model.py is a good engine for the joint markets (period
winner, full-game result, spread) but the early window is so short that its
outcome is dominated by noise. Rather than derive the early probability from
full-game strength, this module fits a regularised logistic regression
directly on the early outcome with walk-forward (as-of) features, and reports
its own out-of-sample calibration so no one has to take the ranking on faith.

Features per game (all computed from games strictly before the game date,
prior season decayed by prior_season_weight and shrunk toward the league):
  tempo       first-10 shots on goal, for + against, both teams, league-relative
  egoals      first-10 goals, for + against, both teams, league-relative
  no5share    share of each team's games with no goal in the first 5, both teams
  total_exp   full-game goals for + against per game, both teams, league-relative
  goalie_sv   starters' shrunk save% minus league (average of the two)
  b2b         number of teams on a back-to-back (0, 1, 2)
  rest_min    min days rest across the two teams (capped at 3)
  travel      max travel distance across the two teams, in 1000 km
  tz          max time zones crossed
  home_early  home team first-10 goals-for rate minus away team's (asymmetry)
  lg_drift    league season-to-date no-goal rate minus the prior-season rate

The fitted coefficients are stored with the model version; predict() is used
by the pipeline for the two headline markets, and the hazard chain's first
period is rescaled so the simulation reproduces the same probability.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from .config import CFG, DATA_DIR, ModelConfig, prior_weight
from .ingest import GameRecord

FEATURES = ["tempo", "egoals", "no5share", "no10share", "total_exp", "goalie_sv", "b2b", "rest_min", "travel", "tz", "home_early", "lg_drift"]


def first_goal_minute(g: GameRecord) -> float:
    return min((e.minute for e in g.events if e.type == "goal"), default=99.0)


@dataclass
class Agg:
    """Weighted running aggregates for one team (or one goalie)."""
    games: float = 0.0
    e10_sog: float = 0.0       # for + against
    e10_goals: float = 0.0     # for + against
    e10_gf: float = 0.0
    no5: float = 0.0
    no10: float = 0.0
    goals: float = 0.0         # for + against, regulation
    shots: float = 0.0         # goalie: shots faced
    ga: float = 0.0            # goalie: goals against


class AsOfState:
    """Everything the feature builder knows at a point in time."""

    def __init__(self, cfg: ModelConfig = CFG):
        self.cfg = cfg
        self.team: dict[str, Agg] = defaultdict(Agg)
        self.goalie: dict[int, Agg] = defaultdict(Agg)
        self.lg = Agg()            # league running aggregates (weighted)
        self.lg_prior_no5 = 0.66   # prior-season league rate, fixed
        self.lg_prior_no10 = 0.42
        self.lg_cur_games = 0.0
        self.lg_cur_no5 = 0.0
        self.lg_cur_no10 = 0.0

    def add(self, g: GameRecord, weight: float, current: bool) -> None:
        fg = first_goal_minute(g)
        for t in (g.home, g.away):
            a = self.team[t]
            a.games += weight
            a.no5 += weight * (fg >= 5)
            a.no10 += weight * (fg >= 10)
        per_goalie: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0])
        for e in g.events:
            if e.minute >= 60:
                continue
            if e.type in ("goal", "shot-on-goal"):
                if e.minute < 10:
                    self.team[g.home].e10_sog += weight
                    self.team[g.away].e10_sog += weight
                if e.goalie:
                    per_goalie[e.goalie][0] += 1
                    per_goalie[e.goalie][1] += e.type == "goal"
            if e.type == "goal":
                self.team[g.home].goals += weight
                self.team[g.away].goals += weight
                if e.minute < 10:
                    self.team[g.home].e10_goals += weight
                    self.team[g.away].e10_goals += weight
                    self.team[e.team].e10_gf += weight
        for gid, (s, ga) in per_goalie.items():
            self.goalie[gid].shots += weight * s
            self.goalie[gid].ga += weight * ga
        self.lg.games += weight
        self.lg.no5 += weight * (fg >= 5)
        self.lg.no10 += weight * (fg >= 10)
        if current:
            self.lg_cur_games += 1
            self.lg_cur_no5 += fg >= 5
            self.lg_cur_no10 += fg >= 10

    # league means for shrinkage targets (per team-game)
    def league_means(self) -> dict:
        n = max(self.lg.games, 1.0)
        tg = [a for a in self.team.values() if a.games > 0]
        tot_games = sum(a.games for a in tg) or 1.0
        return {
            "e10_sog": sum(a.e10_sog for a in tg) / tot_games,
            "e10_goals": sum(a.e10_goals for a in tg) / tot_games,
            "e10_gf": sum(a.e10_gf for a in tg) / tot_games,
            "goals": sum(a.goals for a in tg) / tot_games,
            "no5": self.lg.no5 / n,
            "no10": self.lg.no10 / n,
            "sv": 1 - (sum(a.ga for a in self.goalie.values()) / max(1.0, sum(a.shots for a in self.goalie.values()))),
        }

    def features(self, g: GameRecord, starters: dict | None = None) -> dict:
        cfg = self.cfg
        lm = self.league_means()
        k = cfg.early_k_team

        def tshr(a: Agg, attr: str, key: str) -> float:
            return (getattr(a, attr) + k * lm[key]) / (a.games + k)

        h, a_ = self.team[g.home], self.team[g.away]
        tempo = (tshr(h, "e10_sog", "e10_sog") + tshr(a_, "e10_sog", "e10_sog")) / (2 * lm["e10_sog"]) - 1
        egoals = (tshr(h, "e10_goals", "e10_goals") + tshr(a_, "e10_goals", "e10_goals")) / (2 * lm["e10_goals"]) - 1
        no5share = (tshr(h, "no5", "no5") + tshr(a_, "no5", "no5")) / 2 - lm["no5"]
        no10share = (tshr(h, "no10", "no10") + tshr(a_, "no10", "no10")) / 2 - lm["no10"]
        total_exp = (tshr(h, "goals", "goals") + tshr(a_, "goals", "goals")) / (2 * lm["goals"]) - 1
        home_early = (tshr(h, "e10_gf", "e10_gf") - tshr(a_, "e10_gf", "e10_gf")) / lm["e10_gf"]
        st = starters or g.starters or {}
        svs = []
        for side in ("home", "away"):
            gid = st.get(side)
            ga = self.goalie.get(gid) if gid else None
            if ga and ga.shots > 0:
                svs.append((ga.shots - ga.ga + cfg.k_goalie * lm["sv"]) / (ga.shots + cfg.k_goalie))
            else:
                svs.append(lm["sv"])
        goalie_sv = (sum(svs) / 2 - lm["sv"]) * 100  # in save% points
        rh, ra = (g.rest or {}).get("home") or {}, (g.rest or {}).get("away") or {}
        b2b = int(bool(rh.get("b2b"))) + int(bool(ra.get("b2b")))
        rests = [r.get("days_rest") for r in (rh, ra) if r.get("days_rest") is not None]
        rest_min = min(3, min(rests)) if rests else 2
        travel = max((r.get("travel_km") or 0) for r in (rh, ra)) / 1000.0
        tz = max((r.get("tz_shift") or 0) for r in (rh, ra))
        if self.lg_cur_games >= 30:
            lg_drift = (self.lg_cur_no5 + 60 * self.lg_prior_no5) / (self.lg_cur_games + 60) - self.lg_prior_no5
        else:
            lg_drift = 0.0
        return {"tempo": tempo, "egoals": egoals, "no5share": no5share, "no10share": no10share, "total_exp": total_exp,
                "goalie_sv": goalie_sv, "b2b": b2b, "rest_min": rest_min, "travel": travel, "tz": tz,
                "home_early": home_early, "lg_drift": lg_drift}


def walk_forward_rows(prior: list[GameRecord], current: list[GameRecord], cfg: ModelConfig = CFG, projected_starters=None) -> list[dict]:
    """Feature rows for every current-season game using only earlier games."""
    st = AsOfState(cfg)
    cur_season = max(g.season for g in current) if current else 0
    for g in prior:
        st.add(g, prior_weight(g.season, cur_season, cfg), False)
    lm = st.league_means()
    st.lg_prior_no5, st.lg_prior_no10 = lm["no5"], lm["no10"]
    rows = []
    by_date: dict[str, list[GameRecord]] = defaultdict(list)
    for g in current:
        by_date[g.date].append(g)
    for d in sorted(by_date):
        for g in by_date[d]:
            fg = first_goal_minute(g)
            f = st.features(g)
            f.update({"game_id": g.game_id, "date": d, "y5": int(fg >= 5), "y10": int(fg >= 10)})
            rows.append(f)
        for g in by_date[d]:
            st.add(g, 1.0, True)
    return rows


# ------------------------------------------------------------------ fitting

@dataclass
class EarlyModel:
    coef5: dict = field(default_factory=dict)
    coef10: dict = field(default_factory=dict)
    scale: dict = field(default_factory=dict)     # feature standardisation (mean, sd)
    base5: float = 0.66
    base10: float = 0.42
    n_train: int = 0

    def _z(self, f: dict) -> np.ndarray:
        return np.array([(f[k] - self.scale[k][0]) / self.scale[k][1] for k in FEATURES])

    def predict(self, f: dict) -> tuple[float, float]:
        z = self._z(f)
        l5 = self.coef5["b"] + float(np.dot(z, np.array([self.coef5[k] for k in FEATURES])))
        l10 = self.coef10["b"] + float(np.dot(z, np.array([self.coef10[k] for k in FEATURES])))
        return 1 / (1 + math.exp(-l5)), 1 / (1 + math.exp(-l10))

    def contributions(self, f: dict, window: int = 5) -> dict:
        """Per-feature logit contributions (for the dashboard's audit trail)."""
        coef = self.coef5 if window == 5 else self.coef10
        z = self._z(f)
        return {k: round(float(z[i] * coef[k]), 4) for i, k in enumerate(FEATURES)}

    def to_json(self) -> str:
        return json.dumps({"coef5": self.coef5, "coef10": self.coef10, "scale": self.scale, "base5": self.base5, "base10": self.base10, "n_train": self.n_train})

    @staticmethod
    def from_json(s: str) -> "EarlyModel":
        d = json.loads(s)
        return EarlyModel(d["coef5"], d["coef10"], {k: tuple(v) for k, v in d["scale"].items()}, d["base5"], d["base10"], d["n_train"])


def fit_logistic(X: np.ndarray, y: np.ndarray, l2: float) -> np.ndarray:
    """L2-regularised logistic regression by IRLS. Returns [b, w1..wk]."""
    n, k = X.shape
    A = np.hstack([np.ones((n, 1)), X])
    w = np.zeros(k + 1)
    w[0] = math.log(y.mean() / (1 - y.mean()))
    reg = np.full(k + 1, l2)
    reg[0] = 0.0
    for _ in range(50):
        p = 1 / (1 + np.exp(-A @ w))
        grad = A.T @ (p - y) + reg * w
        W = p * (1 - p)
        H = (A * W[:, None]).T @ A + np.diag(reg)
        step = np.linalg.solve(H, grad)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def fit_early_model(rows: list[dict], l2: float | None = None, cfg: ModelConfig = CFG) -> EarlyModel:
    l2 = cfg.early_l2 if l2 is None else l2
    X = np.array([[r[k] for k in FEATURES] for r in rows], dtype=float)
    mu, sd = X.mean(0), X.std(0)
    sd[sd == 0] = 1.0
    Z = (X - mu) / sd
    m = EarlyModel(scale={k: (float(mu[i]), float(sd[i])) for i, k in enumerate(FEATURES)}, n_train=len(rows))
    for window, key in ((5, "coef5"), (10, "coef10")):
        y = np.array([r[f"y{window}"] for r in rows], dtype=float)
        w = fit_logistic(Z, y, l2)
        d = {"b": float(w[0])}
        d.update({k: float(w[i + 1]) for i, k in enumerate(FEATURES)})
        setattr(m, key, d)
        setattr(m, f"base{window}", float(y.mean()))
    return m


def model_path() -> "Path":
    from pathlib import Path

    return DATA_DIR / "early_model.json"


def save_model(m: EarlyModel) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    model_path().write_text(m.to_json())


def load_model() -> EarlyModel | None:
    p = model_path()
    return EarlyModel.from_json(p.read_text()) if p.exists() else None


# --------------------------------------------------------------- evaluation

def logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())


def evaluate(train_rows: list[dict], test_rows: list[dict], l2: float, cfg: ModelConfig = CFG) -> dict:
    """Fit on train rows, score test rows. Baseline = train mean (plus drift feature's own effect)."""
    m = fit_early_model(train_rows, l2, cfg)
    out = {}
    for w in (5, 10):
        y = np.array([r[f"y{w}"] for r in test_rows], dtype=float)
        p = np.array([m.predict(r)[0 if w == 5 else 1] for r in test_rows])
        base = np.full(len(y), float(np.mean([r[f"y{w}"] for r in train_rows])))
        order = np.argsort(-p)
        q = max(1, len(p) // 5)
        out[f"first{w}"] = {
            "logloss_model": round(logloss(p, y), 5), "logloss_base": round(logloss(base, y), 5),
            "brier_model": round(float(((p - y) ** 2).mean()), 5), "brier_base": round(float(((base - y) ** 2).mean()), 5),
            "mean_pred": round(float(p.mean()), 4), "actual": round(float(y.mean()), 4),
            "top_quintile_actual": round(float(y[order[:q]].mean()), 4), "bottom_quintile_actual": round(float(y[order[-q:]].mean()), 4),
            "top_quintile_pred": round(float(p[order[:q]].mean()), 4), "bottom_quintile_pred": round(float(p[order[-q:]].mean()), 4),
            "pred_sd": round(float(p.std()), 4),
        }
    out["coef5"] = {k: round(v, 4) for k, v in m.coef5.items()}
    out["coef10"] = {k: round(v, 4) for k, v in m.coef10.items()}
    return out
