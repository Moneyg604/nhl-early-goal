"""Game model: piecewise-constant goal hazards for both teams, fully auditable.

For each time bin b of the game, each team's goal rate per minute is

    lambda_team(b) = base(b)                     league goals / team / minute in that bin
                   * home_or_away                sqrt(home multiplier) either way
                   * off_shot(team, b)           team's shot-rate for, league-relative (early or full-game profile)
                   * def_shot(opponent, b)       opponent's shot-rate against, league-relative
                   * finish(team)                team shooting% vs league (heavily shrunk)
                   * goalie(opponent starter)    (1 - sv%) / (1 - league sv%), shrunk
                   * context                     rest / back-to-back / travel / time-zone / rest-edge

Everything is multiplicative so the dashboard can show the chain of factors
and the exact arithmetic that produced the early-goal probability:

    P(no goal in first 5) = exp( - sum_b (lambda_home(b) + lambda_away(b)) * len(b) ),  b within [0, 5)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .config import CFG, ModelConfig
from .features import GoalieProfile, LeagueProfile, TeamProfile


@dataclass
class SideInputs:
    team: str
    is_home: bool
    profile: TeamProfile | None
    goalie: GoalieProfile | None
    goalie_status: str
    goalie_source: str
    goalie_note: str
    rest: dict
    mults: dict = field(default_factory=dict)
    labels: dict = field(default_factory=dict)


@dataclass
class GameModel:
    game_id: int
    date: str
    start_utc: str
    home: str
    away: str
    bins: list                       # [(start, end)] regulation, last bin is the empty-net window
    lam_home: np.ndarray             # goals/min per bin for home team
    lam_away: np.ndarray
    en_leader_home: float            # per-minute rate for home if home leads by 1-2 with net empty
    en_leader_away: float
    en_trailer_home: float
    en_trailer_away: float
    ot_rate_home: float              # per-minute 3v3 OT
    ot_rate_away: float
    so_home_win: float
    inputs: dict                     # audit trail
    tier: str
    tier_reasons: list

    # ---- analytic quantities (exact for a piecewise-constant Poisson process)
    def p_no_goal_before(self, minute: float) -> float:
        total = 0.0
        for (s, e), lh, la in zip(self.bins, self.lam_home, self.lam_away):
            if s >= minute:
                break
            length = min(e, minute) - s
            total += (lh + la) * length
        return math.exp(-total)

    def expected_goals(self, upto: float = 60.0) -> tuple[float, float]:
        h = a = 0.0
        for (s, e), lh, la in zip(self.bins, self.lam_home, self.lam_away):
            if s >= upto:
                break
            length = min(e, upto) - s
            h += lh * length
            a += la * length
        return h, a


def _label_team(p: TeamProfile | None, cfg: ModelConfig) -> tuple[str, str]:
    if p is None or (p.games_cur == 0 and p.games_prior == 0):
        return "unmeasured", "no game data for team"
    if p.games_cur >= cfg.tier_a_min_games:
        return "measured", f"{p.games_cur} games this season + {p.games_prior} last season"
    if p.games_cur > 0 or p.games_prior > 0:
        return "partial", f"only {p.games_cur} games this season; leaning on {p.games_prior} games from last season"
    return "unmeasured", "no data"


def _label_goalie(g: GoalieProfile | None, status: str) -> tuple[str, str]:
    if g is None:
        return "unmeasured", "starter unknown; league-average goalie used"
    shots = g.w_shots
    if status == "confirmed" and shots >= 400:
        return "measured", f"confirmed starter, {int(shots)} weighted shots of data"
    if status == "confirmed":
        return "partial", f"confirmed starter but thin sample ({int(shots)} shots); shrunk toward league"
    if status in ("expected", "projected", "unconfirmed"):
        return "partial", f"starter {status} ({int(shots)} shots of data); re-check before the puck drops"
    return "unmeasured", "no starter information"


def context_multipliers(side: SideInputs, opp: SideInputs, lp: LeagueProfile, cfg: ModelConfig) -> dict:
    """Multipliers applied to THIS side's scoring rate because of rest/travel context."""
    cm = lp.context_mults or {}
    m: dict[str, float] = {}
    r, ro = side.rest or {}, opp.rest or {}
    if r.get("b2b"):
        m["own back-to-back"] = cm.get("b2b_off", cfg.prior_b2b_off_mult)
    if ro.get("b2b"):
        m["opponent back-to-back"] = cm.get("b2b_def", cfg.prior_b2b_def_mult)
    if (ro.get("travel_km") or 0) > 1500:
        m[f"opponent travelled {int(ro.get('travel_km'))} km"] = cm.get("long_travel_def", cfg.prior_long_travel_def_mult)
    if (ro.get("tz_shift") or 0) >= 2:
        m[f"opponent crossed {ro.get('tz_shift')} time zones"] = cm.get("tz_shift_def", cfg.prior_tz_shift_def_mult ** 2)
    if ro.get("three_in_four"):
        m["opponent 3 games in 4 nights"] = cm.get("three_in_four_def", 1.0)
    dr, dro = r.get("days_rest"), ro.get("days_rest")
    if dr is not None and dro is not None and dr - dro >= 2:
        edge = min(2, dr - dro)
        m[f"rest edge +{dr - dro} days"] = cfg.prior_rest_edge_mult ** edge
    return m


def early_context_multipliers(side: SideInputs, opp: SideInputs, lp: LeagueProfile, cfg: ModelConfig) -> dict:
    """Multipliers that apply to the first 10 minutes only (slow starts), measured from the data."""
    from .features import mutual_fatigue

    m: dict[str, float] = {}
    if cfg.use_mutual_fatigue and mutual_fatigue(side.rest or {}, opp.rest or {}):
        m["both teams on a back-to-back / 3-in-4 (first 10 min)"] = (lp.context_mults or {}).get("mutual_fatigue_early", cfg.prior_mutual_fatigue_mult)
    return m


def build_game_model(
    game: dict,
    home: SideInputs,
    away: SideInputs,
    lp: LeagueProfile,
    cfg: ModelConfig = CFG,
) -> GameModel:
    edges = list(cfg.p1_bins) + list(cfg.p2_bins[1:]) + list(cfg.p3_bins[1:])
    bins = [(float(edges[i]), float(edges[i + 1])) for i in range(len(edges) - 1)]
    base = np.array([lp.bin_rate(s, e, cfg) for s, e in bins])
    # the final bin is the empty-net window; its base is the *regular* rate,
    # the empty-net dynamics are injected by the simulator from the score state
    base[-1] = lp.rate_last2_regular if lp.games >= 100 else cfg.prior_rate_p3_regular
    lg_sv = lp.sv_pct or cfg.prior_league_sv
    home_mult = lp.home_mult if lp.games >= 100 else cfg.prior_home_mult
    hm = math.sqrt(home_mult)

    sides = {"home": home, "away": away}
    for key, side in sides.items():
        opp = away if key == "home" else home
        tm = side.profile.mults(lp, cfg) if side.profile else {
            "off_shot_full": 1.0, "def_shot_full": 1.0, "off_shot_early": 1.0, "def_shot_early": 1.0, "finish": 1.0, "pace": 1.0}
        om = opp.profile.mults(lp, cfg) if opp.profile else {
            "off_shot_full": 1.0, "def_shot_full": 1.0, "off_shot_early": 1.0, "def_shot_early": 1.0, "finish": 1.0, "pace": 1.0}
        g_opp = opp.goalie
        sv = g_opp.sv_shrunk(lp, cfg) if (g_opp is not None and g_opp.w_shots > 0) else lg_sv
        goalie_mult = (1 - sv) / (1 - lg_sv) / (lp.norm.get("goalie", 1.0) or 1.0)
        ctx = context_multipliers(side, opp, lp, cfg)
        ctx_total = float(np.prod(list(ctx.values()))) if ctx else 1.0
        ectx = early_context_multipliers(side, opp, lp, cfg)
        ectx_total = float(np.prod(list(ectx.values()))) if ectx else 1.0
        nrm = lp.norm or {}
        side.mults = {
            "home_ice": hm if side.is_home else 1 / hm,
            "off_shot_early": tm["off_shot_early"] / (nrm.get("off_shot", 1.0) or 1.0),
            "off_shot_full": tm["off_shot_full"] / (nrm.get("off_shot", 1.0) or 1.0),
            "opp_def_shot_early": om["def_shot_early"] / (nrm.get("def_shot", 1.0) or 1.0),
            "opp_def_shot_full": om["def_shot_full"] / (nrm.get("def_shot", 1.0) or 1.0),
            "finish": tm["finish"] / (nrm.get("finish", 1.0) or 1.0),
            "opp_goalie": goalie_mult,
            "opp_goalie_sv_shrunk": sv,
            "context": ctx,
            "context_total": ctx_total,
            "early_context": ectx,
            "early_context_total": ectx_total,
        }
        tl, tnote = _label_team(side.profile, cfg)
        gl, gnote = _label_goalie(g_opp, opp.goalie_status)
        side.labels = {
            "team_profile": {"label": tl, "note": tnote},
            "opp_goalie": {"label": gl, "note": gnote},
            "rest_travel": {"label": "measured" if side.rest else "unmeasured", "note": "from team schedule" if side.rest else "schedule context missing"},
        }

    def lam_for(side: SideInputs) -> np.ndarray:
        m = side.mults
        out = np.zeros(len(bins))
        for i, (s, e) in enumerate(bins):
            early = e <= 20
            off = m["off_shot_early"] if early else m["off_shot_full"]
            dfn = m["opp_def_shot_early"] if early else m["opp_def_shot_full"]
            out[i] = base[i] * m["home_ice"] * off * dfn * m["finish"] * m["opp_goalie"] * m["context_total"]
            if e <= 10:
                out[i] *= m["early_context_total"]
        return out

    lam_home, lam_away = lam_for(home), lam_for(away)

    # empty-net window rates (last 2 minutes), scaled mildly by offensive strength
    en_l, en_t = lp.rate_en_leader, lp.rate_en_trailer
    en_leader_home = en_l * math.sqrt(home.mults["off_shot_full"])
    en_leader_away = en_l * math.sqrt(away.mults["off_shot_full"])
    en_trailer_home = en_t * math.sqrt(home.mults["off_shot_full"])
    en_trailer_away = en_t * math.sqrt(away.mults["off_shot_full"])

    # OT: league 3v3 rate split by full-game scoring strength
    eh, ea = lam_home[:-1].mean(), lam_away[:-1].mean()
    share_h = eh / (eh + ea) if (eh + ea) > 0 else 0.5
    ot_rate = lp.ot_rate_per_min or cfg.prior_ot_goal_rate
    ot_rate_home, ot_rate_away = ot_rate * share_h, ot_rate * (1 - share_h)

    # tier
    reasons = []
    tier = "A"
    for side in (home, away):
        if side.labels["team_profile"]["label"] != "measured":
            tier = "B" if tier == "A" else tier
            reasons.append(f"{side.team} profile {side.labels['team_profile']['label']}: {side.labels['team_profile']['note']}")
        gs = (away if side.is_home else home).goalie_status
        if gs not in ("confirmed",):
            tier = "B" if tier == "A" else tier
            reasons.append(f"{(away if side.is_home else home).team} goalie {gs}")
        if side.labels["opp_goalie"]["label"] == "unmeasured" or side.labels["team_profile"]["label"] == "unmeasured":
            tier = "C"
    if not reasons:
        reasons.append("both profiles measured, both goalies confirmed")

    inputs = {
        "league": {
            "games_in_profile": lp.games,
            "home_mult": round(home_mult, 4),
            "league_sv": round(lg_sv, 4),
            "p_no_goal_5_league_observed": round(lp.p_no_goal_5, 4) if lp.games else None,
            "p_no_goal_10_league_observed": round(lp.p_no_goal_10, 4) if lp.games else None,
            "base_rates_first_10": {f"{int(s)}-{int(e)}": round(float(b), 5) for (s, e), b in zip(bins[:10], base[:10])},
            "context_effects": {k: round(v, 4) for k, v in (lp.context_mults or {}).items()},
            "context_samples": lp.context_samples,
        },
        "sides": {},
        "unmeasured": [
            "line matchups / deployment (not published pre-game)",
            "officials' early-penalty tendency (hook present, not fetched)",
            "injuries and scratches unless entered in overrides.json",
            "in-game events after puck drop",
        ],
    }
    for key, side in sides.items():
        opp = away if key == "home" else home
        prof = side.profile.descriptive(lp) if side.profile else {}
        g = opp.goalie
        inputs["sides"][key] = {
            "team": side.team,
            "profile": prof,
            "rest": side.rest,
            "mults": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in side.mults.items() if k not in ("context", "early_context")},
            "context_detail": {k: round(v, 4) for k, v in side.mults["context"].items()},
            "early_context_detail": {k: round(v, 4) for k, v in side.mults.get("early_context", {}).items()},
            "faces_goalie": {
                "name": g.name if g else None,
                "id": g.goalie_id if g else None,
                "status": opp.goalie_status,
                "source": opp.goalie_source,
                "note": opp.goalie_note,
                "sv_raw": round(g.sv_raw(), 4) if (g and g.sv_raw() is not None) else None,
                "sv_shrunk": round(side.mults["opp_goalie_sv_shrunk"], 4),
                "sv_last5": round(g.recent_sv(5), 4) if (g and g.recent_sv(5) is not None) else None,
                "e10_sv_raw": round(g.e10_sv_raw(), 4) if (g and g.e10_sv_raw() is not None) else None,
                "starts_cur": g.starts_cur if g else None,
                "shots_weighted": int(g.w_shots) if g else 0,
            },
            "labels": side.labels,
            "lambda_first_10_per_min": [round(float(x), 5) for x in (lam_home if key == "home" else lam_away)[:10]],
        }

    return GameModel(
        game_id=game["game_id"],
        date=game["date"],
        start_utc=game.get("start_utc", ""),
        home=home.team,
        away=away.team,
        bins=bins,
        lam_home=lam_home,
        lam_away=lam_away,
        en_leader_home=en_leader_home,
        en_leader_away=en_leader_away,
        en_trailer_home=en_trailer_home,
        en_trailer_away=en_trailer_away,
        ot_rate_home=ot_rate_home,
        ot_rate_away=ot_rate_away,
        so_home_win=lp.so_home_win if lp.games else cfg.prior_shootout_home_win,
        inputs=inputs,
        tier=tier,
        tier_reasons=reasons,
    )
