"""Feature layer: league, team and goalie profiles built from GameRecords.

Design rules (mirroring the SLATE research rules):
  * every rate is derived from event data, never from a prop card or a book price
  * current-season measured rates carry the most weight; last season is a
    decayed prior; league averages are the shrinkage target
  * every profile reports the sample it was built on so the ranking layer can
    label inputs measured / partial / unmeasured
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .config import CFG, ModelConfig, prior_weight
from .ingest import Event, GameRecord


# ----------------------------------------------------------------- helpers

def shrink_rate(count: float, exposure: float, league_rate: float, k: float) -> float:
    """Empirical-Bayes shrinkage of count/exposure toward league_rate with k pseudo-exposure."""
    return (count + k * league_rate) / (exposure + k) if (exposure + k) > 0 else league_rate


def score_at(events: list[Event], minute: float, home: str) -> tuple[int, int]:
    h = a = 0
    for e in events:
        if e.type == "goal" and e.minute < minute:
            if e.team == home:
                h += 1
            else:
                a += 1
    return h, a


# ------------------------------------------------------------ league profile

@dataclass
class LeagueProfile:
    games: int = 0
    # goals per team per minute, by game segment
    rate_bins: dict = field(default_factory=dict)   # (start,end) -> rate
    rate_en_leader: float = 0.0
    rate_en_trailer: float = 0.0
    rate_last2_regular: float = 0.0
    ot_rate_per_min: float = 0.0
    so_home_win: float = 0.5
    home_mult: float = 1.0
    sog_per_game: float = 0.0            # per team
    sh_pct: float = 0.0
    xg_per_game: float = 0.0             # per team, regulation, from MoneyPuck when loaded (0 = not loaded)
    e10_xg_per_game: float = 0.0
    xg_games: int = 0
    sv_pct: float = 0.0
    early5_sog_per_game: float = 0.0     # per team, first 5 minutes
    early10_sog_per_game: float = 0.0
    early10_goals_per_game: float = 0.0  # per team
    p1_goals_per_game: float = 0.0       # per team
    p_no_goal_5: float = 0.0             # descriptive: share of games with no goal in first 5
    p_no_goal_10: float = 0.0
    early10_pen_per_game: float = 0.0    # per team
    context_mults: dict = field(default_factory=dict)  # measured rest/travel multipliers
    context_samples: dict = field(default_factory=dict)
    norm: dict = field(default_factory=lambda: {"finish": 1.0, "goalie": 1.0, "off_shot": 1.0, "def_shot": 1.0})

    def bin_rate(self, start: float, end: float, cfg: ModelConfig = CFG) -> float:
        key = (float(start), float(end))
        if key in self.rate_bins and self.games >= 100:
            return self.rate_bins[key]
        # fall back to priors
        if end <= 1:
            return cfg.prior_rate_p1_first_min
        if end <= 5:
            return cfg.prior_rate_p1_min_1_to_5
        if end <= 10:
            return cfg.prior_rate_p1_min_5_to_10
        if end <= 20:
            return cfg.prior_rate_p1_min_10_to_20
        if end <= 40:
            return cfg.prior_rate_p2
        return cfg.prior_rate_p3_regular


def _all_bins(cfg: ModelConfig) -> list[tuple[float, float]]:
    edges = list(cfg.p1_bins) + list(cfg.p2_bins[1:]) + list(cfg.p3_bins[1:])
    return [(float(edges[i]), float(edges[i + 1])) for i in range(len(edges) - 1)]


def build_league_profile(games: list[GameRecord], cfg: ModelConfig = CFG, weights: list[float] | None = None, xg: dict | None = None) -> LeagueProfile:
    """League hazards and effects. `weights` lets the current season count more than the prior ones.
    `xg` (game_id -> MoneyPuck record, see xg.py) adds league expected-goal rates when present."""
    lp = LeagueProfile()
    if xg:
        n_x = xs = xe = 0.0
        for g in games:
            r = xg.get(g.game_id)
            if r and g.final:
                n_x += 1
                xs += r["xg"]["home"]["reg"] + r["xg"]["away"]["reg"]
                xe += r["xg"]["home"]["e10"] + r["xg"]["away"]["e10"]
        if n_x >= 50:
            lp.xg_games = int(n_x)
            lp.xg_per_game = xs / (2 * n_x)
            lp.e10_xg_per_game = xe / (2 * n_x)
    pairs = [(g, (weights[i] if weights else 1.0)) for i, g in enumerate(games) if g.final]
    games = [g for g, _ in pairs]
    lp.games = len(games)
    if not games:
        lp.home_mult = cfg.prior_home_mult
        lp.sv_pct = cfg.prior_league_sv
        lp.sh_pct = 1 - cfg.prior_league_sv
        lp.ot_rate_per_min = cfg.prior_ot_goal_rate
        lp.so_home_win = cfg.prior_shootout_home_win
        lp.rate_en_leader = cfg.prior_rate_p3_empty_net_leader
        lp.rate_en_trailer = cfg.prior_rate_p3_empty_net_trailer
        lp.rate_last2_regular = cfg.prior_rate_p3_regular
        return lp

    bins = _all_bins(cfg)
    goal_counts = {b: 0 for b in bins}
    home_goals = away_goals = 0
    sog = goals = 0
    goalie_shots = goalie_goals = 0   # shots that actually faced a goalie (excludes empty-net goals)
    e5_sog = e10_sog = e10_goals = p1_goals = e10_pen = 0
    no5 = no10 = 0
    # last-two-minute empty-net bookkeeping
    en_leader_goals = en_trailer_goals = en_minutes = 0.0
    last2_regular_goals = last2_regular_minutes = 0.0
    ot_goals = ot_minutes = 0.0
    so_games = so_home_wins = 0

    n_w = 0.0
    for g, w in pairs:
        n_w += w
        first_goal = min((e.minute for e in g.events if e.type == "goal"), default=99.0)
        no5 += w * (first_goal >= 5)
        no10 += w * (first_goal >= 10)
        for e in g.events:
            if e.type == "goal":
                goals += w
                if e.team == g.home:
                    home_goals += w
                else:
                    away_goals += w
                if e.minute < 60:
                    for b in bins:
                        if b[0] <= e.minute < b[1]:
                            goal_counts[b] += w
                            break
                if e.minute < 10:
                    e10_goals += w
                if e.minute < 20:
                    p1_goals += w
                if e.minute >= 60:
                    ot_goals += w
            if e.type in ("goal", "shot-on-goal"):
                sog += w
                if e.goalie:
                    goalie_shots += w
                    goalie_goals += w * (e.type == "goal")
                if e.minute < 5:
                    e5_sog += w
                if e.minute < 10:
                    e10_sog += w
            if e.type == "penalty" and e.minute < 10 and e.duration <= 5:
                e10_pen += w
        # empty-net window: last two minutes of regulation, classified by score at 58:00
        h58, a58 = score_at(g.events, 58.0, g.home)
        diff = h58 - a58
        goals_last2 = [e for e in g.events if e.type == "goal" and 58.0 <= e.minute < 60.0]
        if abs(diff) in (1, 2):
            leader = g.home if diff > 0 else g.away
            en_minutes += 2.0
            for e in goals_last2:
                if e.team == leader:
                    en_leader_goals += 1
                else:
                    en_trailer_goals += 1
        else:
            last2_regular_minutes += 4.0  # two teams x two minutes
            last2_regular_goals += len(goals_last2)
        if g.ended_in == "OT":
            ot_end = max((e.minute for e in g.events if e.type == "goal" and e.minute >= 60), default=65.0)
            ot_minutes += max(0.1, ot_end - 60.0)
        elif g.ended_in == "SO":
            ot_minutes += 5.0
            so_games += 1
            so_home_wins += g.home_score > g.away_score

    n = n_w
    for b, c in goal_counts.items():
        length = b[1] - b[0]
        lp.rate_bins[b] = c / (2.0 * n * length)
    # Pool the one-minute bins of the first period into groups so a single
    # season's noise (~100 goals per bin) does not leak into the hazard curve:
    # [0,1) alone (distinctly quiet), [1,3), [3,5), [5,10), then the 2-min bins.
    for group in ((1, 3), (3, 5), (5, 10)):
        members = [b for b in bins if group[0] <= b[0] and b[1] <= group[1]]
        c = sum(goal_counts[b] for b in members)
        tot_len = sum(b[1] - b[0] for b in members)
        pooled = c / (2.0 * n * tot_len) if tot_len else 0.0
        for b in members:
            lp.rate_bins[b] = pooled
    lp.home_mult = (home_goals / away_goals) if away_goals else cfg.prior_home_mult
    lp.sog_per_game = sog / (2.0 * n)
    lp.sh_pct = goals / sog if sog else 1 - cfg.prior_league_sv
    lp.sv_pct = (1 - goalie_goals / goalie_shots) if goalie_shots else cfg.prior_league_sv
    lp.early5_sog_per_game = e5_sog / (2.0 * n)
    lp.early10_sog_per_game = e10_sog / (2.0 * n)
    lp.early10_goals_per_game = e10_goals / (2.0 * n)
    lp.p1_goals_per_game = p1_goals / (2.0 * n)
    lp.early10_pen_per_game = e10_pen / (2.0 * n)
    lp.p_no_goal_5 = no5 / n
    lp.p_no_goal_10 = no10 / n
    lp.rate_en_leader = shrink_rate(en_leader_goals, en_minutes, cfg.prior_rate_p3_empty_net_leader, 60)
    lp.rate_en_trailer = shrink_rate(en_trailer_goals, en_minutes, cfg.prior_rate_p3_empty_net_trailer, 60)
    lp.rate_last2_regular = shrink_rate(last2_regular_goals, last2_regular_minutes, cfg.prior_rate_p3_regular, 60)
    lp.ot_rate_per_min = shrink_rate(ot_goals, ot_minutes, cfg.prior_ot_goal_rate, 100)
    lp.so_home_win = shrink_rate(so_home_wins, so_games, cfg.prior_shootout_home_win, 40)
    lp.context_mults, lp.context_samples = _context_effects(games, cfg)
    return lp


def compute_norms(lp: LeagueProfile, teams: dict, goalies: dict, cfg: ModelConfig = CFG) -> None:
    """Normalisation constants so each factor averages exactly 1 across the league
    (otherwise shrinkage and starter selection bias the totals a few % low)."""
    lp.norm = {"finish": 1.0, "goalie": 1.0, "off_shot": 1.0, "def_shot": 1.0}
    lg_sv = lp.sv_pct or cfg.prior_league_sv
    tw = [(t, t.w_games) for t in teams.values() if t.w_games > 0]
    if tw:
        tot = sum(w for _, w in tw)
        raw = [t.mults(lp, cfg) for t, _ in tw]
        for key in ("finish", "off_shot_full", "def_shot_full"):
            m = sum(r[key] * w for r, (_, w) in zip(raw, tw)) / tot
            lp.norm[{"finish": "finish", "off_shot_full": "off_shot", "def_shot_full": "def_shot"}[key]] = m
    gw = [(g, g.starts_cur + cfg.prior_season_weight * g.starts_prior) for g in goalies.values() if (g.starts_cur + g.starts_prior) > 0 and g.w_shots > 0]
    if gw:
        tot = sum(w for _, w in gw)
        lp.norm["goalie"] = sum(g.goal_mult(lp, cfg) * w for g, w in gw) / tot


def _context_effects(games: list[GameRecord], cfg: ModelConfig) -> tuple[dict, dict]:
    """Measured multipliers for rest / travel conditions, shrunk toward priors.

    Each effect is the ratio of goals (for, or against) per team-game under the
    condition to goals per team-game otherwise, using the first 10 minutes AND
    the full game pooled 50/50 to keep the sample workable.
    """
    conds = {
        "b2b_off": (lambda r: bool(r.get("b2b")), "for", cfg.prior_b2b_off_mult),
        "b2b_def": (lambda r: bool(r.get("b2b")), "against", cfg.prior_b2b_def_mult),
        "long_travel_def": (lambda r: (r.get("travel_km") or 0) > 1500, "against", cfg.prior_long_travel_def_mult),
        "tz_shift_def": (lambda r: (r.get("tz_shift") or 0) >= 2, "against", cfg.prior_tz_shift_def_mult ** 2),
        "three_in_four_def": (lambda r: bool(r.get("three_in_four")), "against", 1.0),
    }
    agg: dict[str, dict[str, float]] = {k: defaultdict(float) for k in conds}
    for g in games:
        gf = {g.home: 0.0, g.away: 0.0}
        for e in g.events:
            if e.type == "goal" and e.minute < 60:
                gf[e.team] += 0.5 + (0.5 if e.minute < 10 else 0.0)  # pooled early + full game
        for side, team, opp in (("home", g.home, g.away), ("away", g.away, g.home)):
            r = (g.rest or {}).get(side) or {}
            if not r:
                continue
            for name, (pred, which, _) in conds.items():
                val = gf[team] if which == "for" else gf[opp]
                key = "c" if pred(r) else "b"
                agg[name][key + "_goals"] += val
                agg[name][key + "_games"] += 1
    mults, samples = {}, {}
    for name, (_, _, prior) in conds.items():
        a = agg[name]
        n_c, n_b = a["c_games"], a["b_games"]
        if n_c >= 5 and n_b >= 50:
            ratio = (a["c_goals"] / n_c) / (a["b_goals"] / n_b)
            mults[name] = (n_c * ratio + cfg.k_context * prior) / (n_c + cfg.k_context)
        else:
            mults[name] = prior
        samples[name] = int(n_c)
    # mutual fatigue: both teams on a back-to-back, or both on their third game in four nights. Measured on
    # the first 10 minutes only (combined goals per game), because that is where the slow start shows up.
    c_goals = c_games = b_goals = b_games = 0.0
    for g in games:
        r = g.rest or {}
        if not r.get("home") or not r.get("away"):
            continue
        early = sum(1 for e in g.events if e.type == "goal" and e.minute < 10)
        if mutual_fatigue(r["home"], r["away"]):
            c_goals += early; c_games += 1
        else:
            b_goals += early; b_games += 1
    n_c = 2 * c_games   # team-games, to keep the shrinkage scale of the other effects
    if c_games >= 5 and b_games >= 50 and b_goals > 0:
        ratio = (c_goals / c_games) / (b_goals / b_games)
        mults["mutual_fatigue_early"] = (n_c * ratio + cfg.k_context * cfg.prior_mutual_fatigue_mult) / (n_c + cfg.k_context)
    else:
        mults["mutual_fatigue_early"] = cfg.prior_mutual_fatigue_mult
    samples["mutual_fatigue_early"] = int(c_games)
    return mults, samples


def mutual_fatigue(rest_home: dict, rest_away: dict) -> bool:
    """Both teams on the second night of a back-to-back, or both on their third game in four nights."""
    rh, ra = rest_home or {}, rest_away or {}
    return bool((rh.get("b2b") and ra.get("b2b")) or (rh.get("three_in_four") and ra.get("three_in_four")))


# -------------------------------------------------------------- team profile

@dataclass
class TeamProfile:
    team: str
    games_cur: int = 0
    games_prior: int = 0
    # weighted counts (current + decayed prior season)
    w_games: float = 0.0
    sog_for: float = 0.0
    sog_against: float = 0.0
    goals_for: float = 0.0
    goals_against: float = 0.0
    e10_sog_for: float = 0.0
    e10_sog_against: float = 0.0
    e10_goals_for: float = 0.0
    e10_goals_against: float = 0.0
    e5_goals_for: float = 0.0
    e5_goals_against: float = 0.0
    # expected goals (MoneyPuck), weighted like the shot counts; xg_games counts the games that had the data
    xg_games: float = 0.0
    xg_for: float = 0.0
    xg_against: float = 0.0
    e10_xg_for: float = 0.0
    e10_xg_against: float = 0.0
    goals_for_xg: float = 0.0            # goals in the games that had xG, for finishing = goals / xG
    p1_goals_for: float = 0.0
    p1_goals_against: float = 0.0
    e10_pen_taken: float = 0.0
    e10_pen_drawn: float = 0.0
    attempts_for: float = 0.0            # unblocked attempts, pace
    attempts_against: float = 0.0
    # current-season descriptive (not weighted)
    cur_no_goal_5: int = 0               # games with no goal by EITHER team in first 5
    cur_no_goal_10: int = 0
    cur_scored_first5: int = 0
    cur_allowed_first5: int = 0
    last_games: list = field(default_factory=list)   # last 10 current-season game summaries

    def add_game(self, g: GameRecord, weight: float, current: bool, xg_rec: dict | None = None) -> None:
        me = self.team
        opp = g.away if g.home == me else g.home
        self.w_games += weight
        if xg_rec:
            side = "home" if g.home == me else "away"
            other = "away" if side == "home" else "home"
            x, xo = xg_rec["xg"][side], xg_rec["xg"][other]
            self.xg_games += weight
            self.xg_for += weight * x["reg"]
            self.xg_against += weight * xo["reg"]
            self.e10_xg_for += weight * x["e10"]
            self.e10_xg_against += weight * xo["e10"]
            self.goals_for_xg += weight * x["goals_reg"]
        if current:
            self.games_cur += 1
        else:
            self.games_prior += 1
        first_goal_any = 99.0
        gf5 = ga5 = 0
        for e in g.events:
            own = e.team == me
            if e.type in ("goal", "shot-on-goal"):
                if own:
                    self.sog_for += weight
                else:
                    self.sog_against += weight
                if e.minute < 10:
                    if own:
                        self.e10_sog_for += weight
                    else:
                        self.e10_sog_against += weight
            if e.type in ("goal", "shot-on-goal", "missed-shot") and e.minute < 60:
                if own:
                    self.attempts_for += weight
                else:
                    self.attempts_against += weight
            if e.type == "goal" and e.minute < 60:
                first_goal_any = min(first_goal_any, e.minute)
                if own:
                    self.goals_for += weight
                else:
                    self.goals_against += weight
                if e.minute < 10:
                    if own:
                        self.e10_goals_for += weight
                    else:
                        self.e10_goals_against += weight
                if e.minute < 5:
                    if own:
                        self.e5_goals_for += weight
                        gf5 += 1
                    else:
                        self.e5_goals_against += weight
                        ga5 += 1
                if e.minute < 20:
                    if own:
                        self.p1_goals_for += weight
                    else:
                        self.p1_goals_against += weight
            if e.type == "penalty" and e.minute < 10 and e.duration <= 5:
                if own:
                    self.e10_pen_taken += weight
                else:
                    self.e10_pen_drawn += weight
        if current:
            self.cur_no_goal_5 += first_goal_any >= 5
            self.cur_no_goal_10 += first_goal_any >= 10
            self.cur_scored_first5 += gf5 > 0
            self.cur_allowed_first5 += ga5 > 0
            self.last_games.append(
                {
                    "date": g.date,
                    "opp": opp,
                    "home": g.home == me,
                    "first_goal_min": None if first_goal_any >= 99 else round(first_goal_any, 2),
                    "gf5": gf5,
                    "ga5": ga5,
                    "score": f"{g.home_score}-{g.away_score}" if g.home == me else f"{g.away_score}-{g.home_score}",
                }
            )
            self.last_games = self.last_games[-10:]

    # ---- shrunk, league-relative multipliers -------------------------------
    def mults(self, lp: LeagueProfile, cfg: ModelConfig = CFG) -> dict:
        wg = self.w_games
        lg_sog = lp.sog_per_game or 30.0
        lg_e10 = lp.early10_sog_per_game or 4.6
        lg_sh = lp.sh_pct or 0.098
        # shot rates (full game and early), shrunk in games
        off_full = shrink_rate(self.sog_for, wg, lg_sog, cfg.k_team_shots) / lg_sog
        def_full = shrink_rate(self.sog_against, wg, lg_sog, cfg.k_team_shots) / lg_sog
        off_early = shrink_rate(self.e10_sog_for, wg, lg_e10, cfg.k_team_shots) / lg_e10
        def_early = shrink_rate(self.e10_sog_against, wg, lg_e10, cfg.k_team_shots) / lg_e10
        w = cfg.early_specific_weight
        # finishing: shooting% shrunk in shots
        finish = shrink_rate(self.goals_for, self.sog_for, lg_sh, cfg.k_team_finish) / lg_sh
        off_e = w * off_early + (1 - w) * off_full
        def_e = w * def_early + (1 - w) * def_full
        if cfg.use_xg and lp.xg_per_game > 0 and self.xg_games >= 10:
            # shot quality: expected goals for and against, shrunk in games like the shot counts; finishing as goals over xG
            a = cfg.xg_weight
            xo_full = shrink_rate(self.xg_for, self.xg_games, lp.xg_per_game, cfg.k_team_shots) / lp.xg_per_game
            xd_full = shrink_rate(self.xg_against, self.xg_games, lp.xg_per_game, cfg.k_team_shots) / lp.xg_per_game
            xo_early = shrink_rate(self.e10_xg_for, self.xg_games, lp.e10_xg_per_game, cfg.k_team_shots) / lp.e10_xg_per_game
            xd_early = shrink_rate(self.e10_xg_against, self.xg_games, lp.e10_xg_per_game, cfg.k_team_shots) / lp.e10_xg_per_game
            fin_xg = (self.goals_for_xg + cfg.k_finish_xg * 1.0) / (self.xg_for + cfg.k_finish_xg) if self.xg_for > 0 else 1.0
            off_full = (1 - a) * off_full + a * xo_full
            def_full = (1 - a) * def_full + a * xd_full
            off_e = (1 - a) * off_e + a * (w * xo_early + (1 - w) * xo_full)
            def_e = (1 - a) * def_e + a * (w * xd_early + (1 - w) * xd_full)
            finish = (1 - a) * finish + a * fin_xg
        return {
            "off_shot_full": off_full,
            "def_shot_full": def_full,
            "off_shot_early": off_e,
            "def_shot_early": def_e,
            "finish": finish,
            "pace": shrink_rate(self.attempts_for + self.attempts_against, wg, 2 * (lp.sog_per_game or 30) * 1.45, cfg.k_team_shots)
            / (2 * (lp.sog_per_game or 30) * 1.45),
        }

    def descriptive(self, lp: LeagueProfile) -> dict:
        wg = self.w_games or 1.0
        n = self.games_cur or 1
        return {
            "games_cur": self.games_cur,
            "games_prior": self.games_prior,
            "xg_games": int(self.xg_games),
            "xg_for_pg": round(self.xg_for / self.xg_games, 3) if self.xg_games else None,
            "xg_against_pg": round(self.xg_against / self.xg_games, 3) if self.xg_games else None,
            "e10_xg_for_pg": round(self.e10_xg_for / self.xg_games, 3) if self.xg_games else None,
            "e10_xg_against_pg": round(self.e10_xg_against / self.xg_games, 3) if self.xg_games else None,
            "goals_per_xg": round(self.goals_for_xg / self.xg_for, 3) if self.xg_for else None,
            "e10_gf_pg": round(self.e10_goals_for / wg, 3),
            "e10_ga_pg": round(self.e10_goals_against / wg, 3),
            "e5_gf_pg": round(self.e5_goals_for / wg, 3),
            "e5_ga_pg": round(self.e5_goals_against / wg, 3),
            "e10_sog_for_pg": round(self.e10_sog_for / wg, 2),
            "e10_sog_against_pg": round(self.e10_sog_against / wg, 2),
            "sog_for_pg": round(self.sog_for / wg, 2),
            "sog_against_pg": round(self.sog_against / wg, 2),
            "gf_pg": round(self.goals_for / wg, 2),
            "ga_pg": round(self.goals_against / wg, 2),
            "sh_pct": round(self.goals_for / self.sog_for, 4) if self.sog_for else None,
            "e10_pen_taken_pg": round(self.e10_pen_taken / wg, 3),
            "e10_pen_drawn_pg": round(self.e10_pen_drawn / wg, 3),
            "cur_no_goal_5_share": round(self.cur_no_goal_5 / n, 3) if self.games_cur else None,
            "cur_no_goal_10_share": round(self.cur_no_goal_10 / n, 3) if self.games_cur else None,
            "cur_scored_first5_share": round(self.cur_scored_first5 / n, 3) if self.games_cur else None,
            "cur_allowed_first5_share": round(self.cur_allowed_first5 / n, 3) if self.games_cur else None,
            "last_games": self.last_games,
        }


# ------------------------------------------------------------ goalie profile

@dataclass
class GoalieProfile:
    goalie_id: int
    name: str = ""
    team: str = ""
    starts_cur: int = 0
    starts_prior: int = 0
    w_shots: float = 0.0
    w_goals: float = 0.0
    e10_shots: float = 0.0
    e10_goals: float = 0.0
    recent: list = field(default_factory=list)   # last 8 starts: (date, shots, goals)
    last_start_date: str = ""
    xg_faced: float = 0.0                        # MoneyPuck expected goals faced (weighted), regulation, no empty net
    goals_on_xg: float = 0.0                     # goals allowed in those shots
    e10_xg_faced: float = 0.0
    e10_goals_on_xg: float = 0.0

    def sv_shrunk(self, lp: LeagueProfile, cfg: ModelConfig = CFG) -> float:
        lg = lp.sv_pct or cfg.prior_league_sv
        saves = self.w_shots - self.w_goals
        return shrink_rate(saves, self.w_shots, lg, cfg.k_goalie)

    def xg_ratio(self, cfg: ModelConfig = CFG) -> float | None:
        """Goals allowed over expected goals faced, shrunk toward 1 (below 1 = better than the shots deserved)."""
        if self.xg_faced <= 0:
            return None
        return (self.goals_on_xg + cfg.k_goalie_xg) / (self.xg_faced + cfg.k_goalie_xg)

    def goal_mult(self, lp: LeagueProfile, cfg: ModelConfig = CFG) -> float:
        """Multiplier on the opponent's scoring rate from facing this goalie: save % based, blended with the xG ratio when present."""
        lg = lp.sv_pct or cfg.prior_league_sv
        m = (1 - self.sv_shrunk(lp, cfg)) / (1 - lg)
        r = self.xg_ratio(cfg) if cfg.use_xg else None
        if r is not None:
            a = cfg.xg_weight
            m = (1 - a) * m + a * r
        return m

    def sv_raw(self) -> float | None:
        return (self.w_shots - self.w_goals) / self.w_shots if self.w_shots else None

    def e10_sv_raw(self) -> float | None:
        return (self.e10_shots - self.e10_goals) / self.e10_shots if self.e10_shots else None

    def recent_sv(self, n: int = 5) -> float | None:
        r = self.recent[-n:]
        s = sum(x[1] for x in r)
        return (s - sum(x[2] for x in r)) / s if s else None


# ---------------------------------------------------------------- builders

def add_games_to_profiles(
    teams: dict[str, TeamProfile], goalies: dict[int, GoalieProfile], games: list[GameRecord], weight: float, is_cur: bool, xg: dict | None = None
) -> None:
    """Incrementally fold games into team and goalie profiles (used by build_profiles and the backtest).
    `xg` maps game_id to a MoneyPuck record (xg.py); games without one simply add no xG."""

    def team(ab: str) -> TeamProfile:
        if ab not in teams:
            teams[ab] = TeamProfile(ab)
        return teams[ab]

    def goalie(gid: int) -> GoalieProfile:
        if gid not in goalies:
            goalies[gid] = GoalieProfile(gid)
        return goalies[gid]

    for g in sorted(games, key=lambda x: (x.date, x.game_id)):
        if not g.final:
            continue
        xg_rec = xg.get(g.game_id) if xg else None
        team(g.home).add_game(g, weight, is_cur, xg_rec)
        team(g.away).add_game(g, weight, is_cur, xg_rec)
        if xg_rec:
            for gk, v in (xg_rec.get("goalies") or {}).items():
                try:
                    gp = goalie(int(gk))
                except ValueError:
                    continue
                gp.xg_faced += weight * v["xg"]
                gp.goals_on_xg += weight * v["goals"]
                gp.e10_xg_faced += weight * v.get("e10_xg", 0.0)
                gp.e10_goals_on_xg += weight * v.get("e10_goals", 0)
        per_goalie: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
        for e in g.events:
            if e.type in ("goal", "shot-on-goal") and e.goalie and e.minute < 60:
                acc = per_goalie[e.goalie]
                acc[0] += 1
                acc[1] += e.type == "goal"
                if e.minute < 10:
                    acc[2] += 1
                    acc[3] += e.type == "goal"
        for gid, (s_, ga, es, ega) in per_goalie.items():
            gp = goalie(gid)
            gp.name = g.goalie_names.get(str(gid), gp.name)
            gp.w_shots += weight * s_
            gp.w_goals += weight * ga
            gp.e10_shots += weight * es
            gp.e10_goals += weight * ega
            side = "home" if g.starters.get("home") == gid else ("away" if g.starters.get("away") == gid else None)
            if side:
                gp.team = g.home if side == "home" else g.away
                if is_cur:
                    gp.starts_cur += 1
                    gp.recent.append((g.date, int(s_), int(ga)))
                    gp.recent = gp.recent[-8:]
                    gp.last_start_date = g.date
                else:
                    gp.starts_prior += 1
            else:
                gp.team = gp.team or (g.home if any(e.goalie == gid and e.team == g.away for e in g.events) else g.away)
        # a goalie who started but faced no shot in a game still counts as a start
        for side, gid in g.starters.items():
            if gid and gid not in per_goalie:
                gp = goalie(gid)
                gp.name = g.goalie_names.get(str(gid), gp.name)
                gp.team = g.home if side == "home" else g.away
                if is_cur:
                    gp.starts_cur += 1
                    gp.last_start_date = g.date
                else:
                    gp.starts_prior += 1


def infer_current_season(current: list[GameRecord], prior: list[GameRecord]) -> int:
    if current:
        return max(g.season for g in current)
    return (max(g.season for g in prior) + 10001) if prior else 0


def build_profiles(
    current: list[GameRecord], prior: list[GameRecord], cfg: ModelConfig = CFG, current_season: int | None = None
) -> tuple[LeagueProfile, dict[str, TeamProfile], dict[int, GoalieProfile]]:
    cur = current_season or infer_current_season(current, prior)
    from .xg import load_xg

    xg = load_xg(sorted({g.season for g in prior + current})) or None   # loaded for the record; used only when cfg.use_xg
    lp = build_league_profile(prior + current, cfg, weights=[1.0] * len(prior) + [cfg.league_current_weight] * len(current), xg=xg)
    teams: dict[str, TeamProfile] = {}
    goalies: dict[int, GoalieProfile] = {}
    by_season: dict[int, list[GameRecord]] = {}
    for g in prior:
        by_season.setdefault(g.season, []).append(g)
    for season in sorted(by_season):  # oldest first so the latest team assignment wins
        add_games_to_profiles(teams, goalies, by_season[season], prior_weight(season, cur, cfg), False, xg)
    add_games_to_profiles(teams, goalies, current, 1.0, True, xg)
    compute_norms(lp, teams, goalies, cfg)
    return lp, teams, goalies
