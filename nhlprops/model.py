"""Distributions for the props of one game.

Team goals:   Poisson at the expected goals (from the full game model when the slate runs live; from the
              team profiles in the backtest), shootout winner credited one goal as the books settle it.
Power-play goals: opportunities ~ Poisson (team's draw rate x opponent's take rate x home effect), each
              converted at the team's rate x the opponent's kill, so goals ~ Poisson(opportunities x conversion).
Points / assists / goals: each team goal gives the skater a point with his share, so his count is a thinned
              Poisson: Poisson(expected team goals x share). Anytime goal = 1 - exp(-expected goals x goal share).
Shots on goal: negative binomial around his rate x opponent shots-allowed x home effect (dispersion measured).
Blocked shots: negative binomial around his rate x opponent attempt volume x home effect.
"""
from __future__ import annotations

import math

import numpy as np

from .config import CFG, ModelConfig, STANDARD_LINES
from .features import Profiles, Skater, Team

KMAX = {"sog": 14, "blk": 10, "pts": 7, "ast": 6, "goal": 5, "team_total": 11, "ppg": 6}


def poisson_pmf(lam: float, kmax: int) -> list[float]:
    lam = max(lam, 1e-9)
    p = np.array([math.exp(k * math.log(lam) - lam - math.lgamma(k + 1)) for k in range(kmax + 1)])
    p[-1] += max(0.0, 1 - p.sum())
    return [round(float(x), 5) for x in p]


def nb_pmf(mean: float, size: float, kmax: int) -> list[float]:
    """Negative binomial with the given mean and size (variance = mean + mean^2 / size)."""
    mean = max(mean, 1e-6)
    p = size / (size + mean)
    q = np.array([math.exp(math.lgamma(k + size) - math.lgamma(size) - math.lgamma(k + 1) + size * math.log(p) + k * math.log1p(-p)) for k in range(kmax + 1)])
    q[-1] += max(0.0, 1 - q.sum())
    return [round(float(x), 5) for x in q]


def over_under(pmf: list[float], line: float) -> tuple[float, float, float]:
    v = np.arange(len(pmf)); p = np.array(pmf)
    return float(p[v > line].sum()), float(p[v == line].sum()), float(p[v < line].sum())


def fair_line(pmf: list[float]) -> float:
    """The half-point line nearest to even."""
    c = np.cumsum(pmf)
    med = int(np.searchsorted(c, 0.5))
    cands = [med - 0.5, med + 0.5]
    return min(cands, key=lambda L: abs(over_under(pmf, L)[0] - 0.5))


def team_inputs(P: Profiles, team: str, opp: str, is_home: bool, cfg: ModelConfig = CFG) -> dict:
    lg = P.league
    T = P.teams.get(team) or Team(team=team)
    O = P.teams.get(opp) or Team(team=opp)
    home_sog = math.sqrt(lg.home_sog) if is_home else 1 / math.sqrt(lg.home_sog)
    home_gf = math.sqrt(lg.home_gf) if is_home else 1 / math.sqrt(lg.home_gf)
    home_pp = math.sqrt(lg.home_pp) if is_home else 1 / math.sqrt(lg.home_pp)
    lam_goals = lg.team_gf * T.gf * O.ga * home_gf
    exp_sog = lg.team_sog * T.sog_for * O.sog_against * home_sog
    exp_att_opp = lg.team_att * O.att_for * T.att_against / home_sog
    lam_opps = lg.pp_opps * T.pp_draw * O.pp_take * home_pp
    p_conv = min(0.6, lg.pp_conv * T.pp_conv * O.pk)
    return {"lam_goals": lam_goals, "exp_sog": exp_sog, "exp_att_opp": exp_att_opp, "lam_opps": lam_opps, "p_conv": p_conv,
            "lam_ppg": lam_opps * p_conv, "sog_mult": O.sog_against * home_sog, "att_mult": O.att_for / home_sog,
            "parts": {"team_gf": round(T.gf, 3), "opp_ga": round(O.ga, 3), "home_gf": round(home_gf, 3), "team_sog": round(T.sog_for, 3),
                      "opp_sog_allowed": round(O.sog_against, 3), "opp_attempts": round(O.att_for, 3), "pp_draw": round(T.pp_draw, 3),
                      "opp_pp_take": round(O.pp_take, 3), "pp_conv": round(T.pp_conv, 3), "opp_pk": round(O.pk, 3)}}


def skater_markets(P: Profiles, S: Skater, ti: dict, lam_goals: float, cfg: ModelConfig = CFG) -> dict:
    """Distributions for one skater given the team inputs and the expected team goals (regulation + overtime)."""
    lg = P.league
    r = S.rates(lg, cfg)
    sog_mean = r["sog"] * ti["sog_mult"]
    blk_mean = r["blk"] * ti["att_mult"]
    lam = lam_goals ** cfg.goals_elasticity * lg.team_gf ** (1 - cfg.goals_elasticity)
    out = {
        "sog": nb_pmf(sog_mean, lg.nb_size_sog, KMAX["sog"]),
        "blk": nb_pmf(blk_mean, lg.nb_size_blk, KMAX["blk"]),
        "pts": poisson_pmf(lam * r["pts_share"], KMAX["pts"]),
        "ast": poisson_pmf(lam * r["ast_share"], KMAX["ast"]),
        "goal": poisson_pmf(lam * r["goal_share"], KMAX["goal"]),
    }
    means = {"sog": round(sog_mean, 2), "blk": round(blk_mean, 2), "pts": round(lam * r["pts_share"], 3), "ast": round(lam * r["ast_share"], 3),
             "goal": round(lam * r["goal_share"], 3)}
    return {"pmf": out, "mean": means, "rates": {k: round(v, 4) for k, v in r.items()}, "fair": {k: fair_line(v) for k, v in out.items()}}


def team_markets(P: Profiles, ti: dict, goals_pmf: list[float] | None = None) -> dict:
    tt = goals_pmf if goals_pmf is not None else poisson_pmf(ti["lam_goals"], KMAX["team_total"])
    ppg = poisson_pmf(ti["lam_ppg"], KMAX["ppg"])
    return {"team_total": tt, "ppg": ppg, "lam_goals": round(ti["lam_goals"], 3), "lam_opps": round(ti["lam_opps"], 3), "p_conv": round(ti["p_conv"], 4),
            "lam_ppg": round(ti["lam_ppg"], 3), "exp_sog": round(ti["exp_sog"], 1), "fair_total": fair_line(tt), "parts": ti["parts"]}


__all__ = ["team_inputs", "skater_markets", "team_markets", "over_under", "fair_line", "poisson_pmf", "nb_pmf", "KMAX", "STANDARD_LINES"]
