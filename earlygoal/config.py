"""Central configuration for the early-goal engine.

Everything tunable lives here so the model can be audited in one place.
Values marked PRIOR are fallback assumptions used only when the cached data
cannot estimate the quantity; the ingestion step overrides them with measured
values whenever enough games are available.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
OUT_DIR = ROOT / "out"
OVERRIDES_FILE = DATA_DIR / "overrides.json"

NHL_API = "https://api-web.nhle.com/v1"
NHL_STATS_API = "https://api.nhle.com/stats/rest/en"

MODEL_VERSION = "0.5.0"


@dataclass
class ModelConfig:
    # Seasons used to build profiles (most recent first). Current season is
    # always included automatically; prior seasons are added with a decay.
    n_prior_seasons: int = 2                 # seasons before the current one that feed the profiles
    prior_season_weights: tuple[float, ...] = (0.55, 0.25)   # one season back, two seasons back; game-for-game vs current
    prior_season_weight: float = 0.55        # weight for a prior game whose distance is not in the table
    league_current_weight: float = 3.0       # current-season games count this much in the league hazard curve

    # Shrinkage (pseudo-games) toward league average. Larger = more conservative.
    # Early-season (October) runs sit almost entirely on these priors; that is
    # intended. Current-season signal grows with games played.
    # Backtested on 2,624 real games (2024-25 and 2025-26 walk-forward): these
    # values gave the best out-of-sample log loss; looser shrinkage only added noise.
    k_team_shots: float = 60.0               # shot-rate profiles, in team-games
    k_team_finish: float = 2000.0            # team shooting%, in shots (talent spread is tiny)
    k_goalie: float = 3000.0                 # goalie save%, in shots faced
    k_context: float = 150.0                 # rest / travel / home effects, in team-games
    early_specific_weight: float = 0.25      # weight of first-10-minute profile vs full-game profile

    # Direct early-window model (early_model.py)
    early_k_team: float = 25.0               # pseudo-games of shrinkage for the as-of team aggregates
    early_l2: float = 30.0                   # L2 penalty on standardised coefficients

    # Time windows (minutes into period 1) we care about
    windows: tuple[int, ...] = (5, 10)

    # Base hazard bins for the simulation, in minutes from game start.
    # First-period bins are fine-grained so 5:00 and 10:00 land on bin edges.
    p1_bins: tuple[float, ...] = (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18, 20)
    p2_bins: tuple[float, ...] = (20, 25, 30, 35, 40)
    p3_bins: tuple[float, ...] = (40, 45, 50, 55, 58, 60)   # last 2 min = empty-net window

    # PRIORS: league-average goals per TEAM per minute by segment of the game.
    # Derived from recent NHL seasons (~3.05 goals per team-game, first period
    # lightest, 3rd period heaviest because of empty-net goals). Replaced by
    # measured values after ingestion.
    prior_rate_p1_first_min: float = 0.030
    prior_rate_p1_min_1_to_5: float = 0.042
    prior_rate_p1_min_5_to_10: float = 0.047
    prior_rate_p1_min_10_to_20: float = 0.050
    prior_rate_p2: float = 0.0535
    prior_rate_p3_regular: float = 0.052
    prior_rate_p3_empty_net_leader: float = 0.22    # leading team, net empty
    prior_rate_p3_empty_net_trailer: float = 0.085  # trailing team, extra attacker

    prior_home_mult: float = 1.04            # home team scores ~4% more
    prior_b2b_off_mult: float = 0.97         # back-to-back: scores slightly less
    prior_b2b_def_mult: float = 1.05         # ...and allows slightly more
    prior_long_travel_def_mult: float = 1.02 # > 1500 km since last game
    prior_tz_shift_def_mult: float = 1.015   # per time zone crossed, capped at 2
    prior_rest_edge_mult: float = 1.015      # per extra rest day vs opponent, capped at 2
    use_xg: bool = False                     # shot quality (MoneyPuck expected goals) blended into shot rates, finishing and goalie quality; the walk-forward prune turns it on when it helps
    xg_weight: float = 0.5                   # share of the xG-based estimate in that blend
    k_finish_xg: float = 120.0               # finishing as goals over xG, shrunk in xG units (about 40 games)
    k_goalie_xg: float = 150.0               # goalie as goals allowed over xG faced, shrunk in xG units (about 60 starts)
    use_context: bool = True                 # rest / travel multipliers (back-to-back, travel, time zones, 3-in-4, rest edge) on the full game
    use_context_early: bool = False          # ...also on the first 10 minutes (walk-forward says they add noise there)
    use_mutual_fatigue: bool = True          # both teams on a back-to-back (or both 3-in-4): measured early-window multiplier
    prior_mutual_fatigue_mult: float = 1.0   # prior for that multiplier (1.0 = no effect until the data says so)

    prior_league_sv: float = 0.902           # league save%
    prior_ot_goal_rate: float = 0.145        # per minute, combined, 3v3 OT
    prior_shootout_home_win: float = 0.50

    # Monte Carlo
    sims: int = 100_000
    seed: int | None = None

    # Confidence tiers
    tier_a_min_games: int = 20               # current-season team games for tier A
    tier_b_min_games: int = 8


# Switches the monthly revalidation may flip (data/factors.json, written by `backtest --prune`): a factor that
# stops improving the walk-forward backtest is turned off there without changing the code.
PRUNABLE = ("use_context_early", "use_mutual_fatigue", "use_xg")


def _load_factor_switches() -> dict:
    import json

    f = DATA_DIR / "factors.json"
    if not f.exists():
        return {}
    try:
        d = json.loads(f.read_text())
        return {k: bool(v) for k, v in (d.get("switches") or {}).items() if k in PRUNABLE}
    except Exception:  # noqa: BLE001
        return {}


CFG = ModelConfig(**_load_factor_switches())


def prior_seasons_for(current_season: int, cfg: ModelConfig = CFG) -> list[int]:
    """Seasons that feed the profiles for `current_season` (20262027 -> [20252026, 20242025])."""
    return [current_season - 10001 * k for k in range(1, cfg.n_prior_seasons + 1)]


def prior_weight(season: int, current_season: int, cfg: ModelConfig = CFG) -> float:
    """Game weight for a prior season by its distance from the current one."""
    d = (current_season - season) // 10001
    if 1 <= d <= len(cfg.prior_season_weights):
        return cfg.prior_season_weights[d - 1]
    return cfg.prior_season_weight
