"""Profiles from the skater-game and team-game records (nhlprops.ingest), built from games before a date.

League: per-game rates and the dispersion of shots and blocks around a player's own mean.
Team:   multipliers vs the league for shots and attempts for / against, blocks per opponent attempt, goals for /
        against, power plays drawn / taken and conversion / kill, each a shrunk log ratio (k_team pseudo-games),
        weighted by recency (half-life in games) with last season discounted.
Skater: recency-weighted rates per game (shots, blocks) and shares per team goal (goals, assists, points), each
        shrunk toward the league skater prior at his ice-time level; deployment = recent on-ice share vs his window.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .config import CFG, ModelConfig


def _w_recency(n_back: np.ndarray, half_life: float) -> np.ndarray:
    return np.power(0.5, n_back / half_life)


@dataclass
class League:
    sog: float = 1.55          # shots on goal per skater-game
    blk: float = 0.85
    team_sog: float = 28.0
    team_att: float = 58.0
    team_gf: float = 3.05      # goals per team-game, regulation + overtime
    team_blk_per_att: float = 0.27
    pp_opps: float = 2.8
    pp_conv: float = 0.21
    oi: float = 0.27           # mean on-ice share per skater-game
    ast_per_goal: float = 1.7
    home_sog: float = 1.0      # home / away ratio
    home_gf: float = 1.0
    home_pp: float = 1.0
    nb_size_sog: float = 12.0
    nb_size_blk: float = 8.0
    n_games: int = 0


@dataclass
class Team:
    team: str
    n: float = 0.0
    sog_for: float = 1.0
    sog_against: float = 1.0
    att_for: float = 1.0
    att_against: float = 1.0
    blk_rate: float = 1.0      # blocks per opponent attempt vs league
    gf: float = 1.0
    ga: float = 1.0
    pp_draw: float = 1.0       # power plays drawn per game vs league
    pp_take: float = 1.0       # times short-handed per game vs league
    pp_conv: float = 1.0       # conversion vs league
    pk: float = 1.0            # goals allowed per kill vs league (1 = average, lower is better)
    recent: list = field(default_factory=list)    # last game dates and skater sets


@dataclass
class Skater:
    pid: int
    name: str
    team: str
    games: int = 0
    w: float = 0.0
    sog: float = 0.0           # weighted sums
    g: float = 0.0
    a: float = 0.0
    pts: float = 0.0
    blk: float = 0.0
    pp_pts: float = 0.0
    oi: float = 0.0
    oi_pp: float = 0.0
    tgf: float = 0.0           # team goals in his games (weighted)
    tatt_a: float = 0.0        # opponent attempts in his games (weighted)
    recent_oi: float = 0.0     # on-ice share over the last five games
    recent_oi_pp: float = 0.0
    last_date: str = ""
    last5: list = field(default_factory=list)
    pos_hint: str = ""         # "D" when his block rate looks like a defenceman's (display only)

    def rates(self, lg: League, cfg: ModelConfig) -> dict:
        oi = (self.oi + cfg.k_oi * lg.oi) / (self.w + cfg.k_oi) if self.w + cfg.k_oi > 0 else lg.oi
        oi_ratio = oi / lg.oi
        pr_sog, pr_blk = lg.sog * oi_ratio, lg.blk * oi_ratio
        share_prior = (1 + lg.ast_per_goal) / 18.0 * oi_ratio          # points per team goal for an average skater at his ice time
        g_prior = 1 / 18.0 * oi_ratio
        a_prior = lg.ast_per_goal / 18.0 * oi_ratio
        sog = (self.sog + cfg.k_sog * pr_sog) / (self.w + cfg.k_sog)
        blk = (self.blk + cfg.k_blk * pr_blk) / (self.w + cfg.k_blk)
        tg = self.tgf
        pts = (self.pts + cfg.k_pts * share_prior * lg.team_gf) / (tg + cfg.k_pts * lg.team_gf)
        ast = (self.a + cfg.k_ast * a_prior * lg.team_gf) / (tg + cfg.k_ast * lg.team_gf)
        goal = (self.g + cfg.k_goal * g_prior * lg.team_gf) / (tg + cfg.k_goal * lg.team_gf)
        # deployment: a skater promoted (or demoted) recently
        dep = 1.0
        if self.recent_oi > 0 and oi > 0 and cfg.deploy_weight > 0:
            dep = (self.recent_oi / oi) ** cfg.deploy_weight
            dep = min(1.6, max(0.6, dep))
        return {"sog": sog * dep, "blk": blk * dep, "pts_share": pts * dep, "ast_share": ast * dep, "goal_share": goal * dep,
                "oi": oi, "deploy": dep, "pp_share": (self.oi_pp / self.w) if self.w > 0 else 0.0}


@dataclass
class Profiles:
    league: League
    teams: dict
    skaters: dict
    as_of: str


def _logor(num: float, den: float, k: float) -> float:
    """Shrunk log ratio of an observed rate (num/den) to its expectation, den in games."""
    if den <= 0 or num <= 0:
        return 0.0
    return math.log(num / den) * den / (den + k)


def build(sk: pd.DataFrame, tf: pd.DataFrame, as_of: str, cfg: ModelConfig = CFG) -> Profiles:
    """Profiles from every record dated strictly before `as_of` (YYYY-MM-DD)."""
    tf = tf[tf.date < as_of]
    sk = sk[sk.date < as_of]
    if tf.empty:
        return Profiles(League(), {}, {}, as_of)
    seasons = sorted(tf.season.unique())
    cur = seasons[-1]
    # ---------------- league (last two seasons, equal weight)
    recent_t = tf[tf.season >= cur - 1]
    recent_s = sk[sk.season >= cur - 1]
    lg = League()
    lg.n_games = int(recent_t.game_id.nunique())
    lg.team_sog = float(recent_t.sog.mean()); lg.team_att = float(recent_t.att.mean()); lg.team_gf = float(recent_t.gf.mean())
    lg.team_blk_per_att = float(recent_t.blk.sum() / max(1, recent_t.att_a.sum()))
    lg.pp_opps = float(recent_t.pp_opps.mean()); lg.pp_conv = float(recent_t.ppg.sum() / max(1, recent_t.pp_opps.sum()))
    lg.sog = float(recent_s.sog.mean()); lg.blk = float(recent_s.blk.mean()); lg.oi = float(recent_s.oi.mean())
    lg.ast_per_goal = float(recent_s.a.sum() / max(1, recent_s.g.sum()))
    h, a = recent_t[recent_t.is_home], recent_t[~recent_t.is_home]
    lg.home_sog = float(h.sog.mean() / max(1e-9, a.sog.mean())); lg.home_gf = float(h.gf.mean() / max(1e-9, a.gf.mean()))
    lg.home_pp = float(h.pp_opps.mean() / max(1e-9, a.pp_opps.mean()))
    lg.nb_size_sog, lg.nb_size_blk = cfg.nb_size_sog, cfg.nb_size_blk
    # ---------------- teams
    teams: dict = {}
    tf = tf.sort_values("date")
    for t, g in tf.groupby("team"):
        g = g.sort_values("date")
        n_back = np.arange(len(g))[::-1].astype(float)
        w = _w_recency(n_back, cfg.half_life_games * 1.5) * np.where(g.season.values < cur, cfg.prior_season_weight, 1.0)
        W = float(w.sum())
        if W <= 0:
            continue
        m = lambda col: float((g[col].values * w).sum())  # noqa: E731
        hw = float((w * np.where(g.is_home.values, 1.0, 0.0)).sum()) / W     # share of home games, to remove the home effect from the team rate
        sog_adj = lg.team_sog * (hw * lg.home_sog + (1 - hw)) / ((lg.home_sog + 1) / 2)
        gf_adj = lg.team_gf * (hw * lg.home_gf + (1 - hw)) / ((lg.home_gf + 1) / 2)
        k = cfg.k_team
        T = Team(team=t, n=W)
        T.sog_for = math.exp(_logor(m("sog"), W * sog_adj, k)); T.sog_against = math.exp(_logor(m("sog_a"), W * lg.team_sog, k))
        T.att_for = math.exp(_logor(m("att"), W * lg.team_att, k)); T.att_against = math.exp(_logor(m("att_a"), W * lg.team_att, k))
        T.blk_rate = math.exp(_logor(m("blk"), m("att_a") * lg.team_blk_per_att, k))
        T.gf = math.exp(_logor(m("gf"), W * gf_adj, k)); T.ga = math.exp(_logor(m("ga"), W * lg.team_gf, k))
        T.pp_draw = math.exp(_logor(m("pp_opps"), W * lg.pp_opps, cfg.k_pp)); T.pp_take = math.exp(_logor(m("pk_opps"), W * lg.pp_opps, cfg.k_pp))
        T.pp_conv = math.exp(_logor(m("ppg"), m("pp_opps") * lg.pp_conv, cfg.k_pp)); T.pk = math.exp(_logor(m("ppga"), m("pk_opps") * lg.pp_conv, cfg.k_pp))
        T.recent = list(g.date.values[-5:])
        teams[t] = T
    # ---------------- skaters (current team = team of his last game)
    skaters: dict = {}
    sk = sk.sort_values(["pid", "date"])
    tg_by_game = tf.set_index(["game_id", "team"]).gf.to_dict()
    atta_by_game = tf.set_index(["game_id", "team"]).att_a.to_dict()
    sk = sk.assign(tgf=[tg_by_game.get((gid, t), 0) for gid, t in zip(sk.game_id, sk.team)],
                   tatt_a=[atta_by_game.get((gid, t), 0) for gid, t in zip(sk.game_id, sk.team)])
    for pid, g in sk.groupby("pid", sort=False):
        n = len(g)
        n_back = np.arange(n)[::-1].astype(float)
        w = _w_recency(n_back, cfg.half_life_games) * np.where(g.season.values < cur, cfg.prior_season_weight, 1.0)
        names = g.name.dropna()
        S = Skater(pid=int(pid), name=str(names.values[-1]) if len(names) else f"#{int(pid)}", team=str(g.team.values[-1]), games=n, w=float(w.sum()))
        for col in ("sog", "g", "a", "pts", "blk", "pp_pts", "oi", "tgf", "tatt_a"):
            setattr(S, col, float((g[col].values * w).sum()))
        oi_pp = g.oi_pp.fillna(0).values
        S.oi_pp = float((oi_pp * w).sum())
        last5 = g.tail(5)
        S.recent_oi = float(last5.oi.mean()); S.recent_oi_pp = float(last5.oi_pp.fillna(0).mean())
        S.last_date = str(g.date.values[-1])
        S.last5 = [{"date": str(d), "sog": int(s), "pts": int(p), "a": int(a_), "g": int(g_), "blk": int(b), "oi": round(float(o), 2)}
                   for d, s, p, a_, g_, b, o in zip(last5.date, last5.sog, last5.pts, last5.a, last5.g, last5.blk, last5.oi)]
        blk_pg = S.blk / S.w if S.w else 0.0
        # fallback only (the roster endpoint replaces it): defencemen play more and block more
        S.pos_hint = "D" if (S.oi / S.w if S.w else 0) > 0.34 and blk_pg > 0.8 and (S.sog / S.w if S.w else 0) < 2.3 else "F"
        skaters[int(pid)] = S
    return Profiles(lg, teams, skaters, as_of)


def dressed_last(sk: pd.DataFrame, team: str, before: str, games: int = 1) -> tuple[set, dict]:
    """Skaters who dressed in the team's last `games` games before `before`: the pregame candidate set."""
    g = sk[(sk.team == team) & (sk.date < before)]
    if g.empty:
        return set(), {}
    dates = sorted(g.date.unique())[-games:]
    last = g[g.date.isin(dates)]
    return set(last.pid.astype(int)), dict(zip(last.pid.astype(int), last.name))


__all__ = ["League", "Team", "Skater", "Profiles", "build", "dressed_last"]
