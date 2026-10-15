"""Settings for the NHL props model. Every number here was either measured from the data or tested in the
walk-forward backtest (data/nhlprops/factors.json lists the tests)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "nhlprops"
SDV_DIR = ROOT / "data" / "sdv"
OUT_DIR = ROOT / "out" / "nhlprops"
MODEL_VERSION = "nhlprops-1.0"

# the standard lines DraftKings posts; the page prices any line from the stored distributions
STANDARD_LINES = {
    "sog": [1.5, 2.5, 3.5, 4.5, 5.5],
    "pts": [0.5, 1.5, 2.5],
    "ast": [0.5, 1.5],
    "goal": [0.5],
    "blk": [0.5, 1.5, 2.5, 3.5],
    "team_total": [1.5, 2.5, 3.5, 4.5],
    "ppg": [0.5, 1.5],
}


@dataclass(frozen=True)
class ModelConfig:
    # ---- player rates: exponentially weighted by games back (half-life in games) and shrunk toward the league skater prior
    half_life_games: float = 60.0          # a game 60 games ago counts half as much as the last one (20 and 35 tested worse, 100 no better)
    prior_season_weight: float = 0.5       # a game last season counts this much (on top of the half-life)
    k_sog: float = 3.0                     # pseudo-games of league-prior shots on goal
    k_pts: float = 5.0                     # pseudo-games of league-prior points share
    k_ast: float = 10.0
    k_goal: float = 5.0 
    k_blk: float = 3.0
    k_oi: float = 4.0                      # pseudo-games for the on-ice share (deployment)
    # ---- team multipliers (log ratios vs league, shrunk with k pseudo-games)
    k_team: float = 25.0
    k_pp: float = 30.0
    # ---- dispersion: shots and blocks are more spread than Poisson; negative-binomial size parameters (measured)
    nb_size_sog: float = 15.0          # measured within-player: var / mean 1.09 for shots (size 18.7), 1.07 for blocks (13.7); a little wider for estimation error
    nb_size_blk: float = 11.0
    # ---- deployment: how much a change in the player's recent on-ice share moves his rates (0 = ignore, 1 = fully)
    deploy_weight: float = 0.5
    # ---- scoring input: how the team's expected goals today scale the player's points (1 = proportional)
    goals_elasticity: float = 1.0
    # ---- candidates: a skater must have dressed within this many of the team's games to be listed
    recent_games: int = 3
    sims: int = 50_000


CFG = ModelConfig()

PRUNABLE = ["deploy_weight", "goals_elasticity", "prior_season_weight"]

__all__ = ["CFG", "ModelConfig", "DATA_DIR", "SDV_DIR", "OUT_DIR", "MODEL_VERSION", "STANDARD_LINES", "PRUNABLE"]
