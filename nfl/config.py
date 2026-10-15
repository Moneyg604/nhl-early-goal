"""Configuration for the NFL engine. Everything tunable is here so the model can be audited in one place.

Values marked PRIOR are fallbacks used only until the data measures the quantity; every one of them is
replaced by a measured value once the seasons are ingested.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "nfl"
RAW_DIR = DATA_DIR / "raw"
CACHE_DIR = DATA_DIR / "cache"
OUT_DIR = ROOT / "out" / "nfl"
SITE_DIR = ROOT / "docs" / "nfl"

MODEL_VERSION = "0.1.0"

# nflverse release assets (GitHub; reachable from the build runner and from most networks)
NFLVERSE = "https://github.com/nflverse/nflverse-data/releases/download"
ASSETS = {
    "pbp": NFLVERSE + "/pbp/play_by_play_{season}.parquet",
    "schedule": NFLVERSE + "/schedules/games.csv",
    "injuries": NFLVERSE + "/injuries/injuries_{season}.parquet",
    "depth": NFLVERSE + "/depth_charts/depth_charts_{season}.parquet",
    "rosters": NFLVERSE + "/weekly_rosters/roster_weekly_{season}.parquet",
    "players": NFLVERSE + "/players/players.parquet",
    "snaps": NFLVERSE + "/snap_counts/snap_counts_{season}.parquet",
}

# Live scoreboard (public ESPN endpoint, CORS-enabled; used by the page and by the live-scores job)
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"

# Seasons: nflverse play-by-play goes back to 1999; the kickoff rules and scoring environment changed
# enough that only recent seasons feed the model.
FIRST_SEASON = 2019


@dataclass
class ModelConfig:
    # --- data windows -------------------------------------------------------------------
    n_prior_seasons: int = 2                      # seasons before the current one that feed the profiles
    prior_season_weights: tuple[float, ...] = (0.35, 0.15)  # one season back, two back; per game vs the current season (walk-forward: beat 0.6 / 0.3)
    league_seasons: int = 3                       # seasons behind the league-average drive outcome table

    # --- shrinkage (pseudo-drives / pseudo-games) toward the league --------------------------
    k_drive_team: float = 300.0                   # offense / defense touchdown and turnover odds ratios, in drives (about 27 games; walk-forward: beat 120)
    anchor_fg_frac: float = 0.3                   # share of the market-anchor scoring shift applied to field-goal tries (walk-forward: 0.3 beat 1.0 and 0.0)
    k_drive_fg: float = 600.0                     # field-goal-try odds ratios (kept separate: the walk-forward test decides how hard to shrink them)
    k_pace: float = 80.0                          # seconds per drive, in drives
    k_kicker: float = 150.0                        # field-goal make odds ratio, in attempts
    k_qb_rate: float = 250.0                      # yards / touchdowns per dropback, in dropbacks (about 7 games)
    k_dropbacks: float = 100.0                    # dropbacks per drive, in drives
    k_td_share: float = 12.0                      # player share of team touchdowns, in team touchdowns
    k_usage: float = 1.5                          # player yardage / reception shares, in weighted games
    k_context: float = 400.0                      # home / rest / roof / wind effects, in drives
    recency_half_life_games: float = 6.0          # exponential weighting of a player's own games (walk-forward: 6 beat 12 for anytime TD)
    use_snap_trend: bool = True                   # scale touchdown shares by the recent change in snap share (walk-forward: kept)
    snap_trend_weight: float = 0.5

    # --- game structure ----------------------------------------------------------------------
    half_seconds: int = 1800
    sims: int = 100_000
    seed: int | None = None
    max_drives_per_half: int = 20

    # --- PRIORS (replaced by measured values) ----------------------------------------------
    prior_home_odds: float = 1.06                 # home team scoring odds (TD or FG) per drive
    prior_xp_make: float = 0.955
    prior_two_point_rate: float = 0.06            # share of touchdowns followed by a two-point try
    prior_two_point_make: float = 0.48
    prior_ot_rate_tie: float = 0.02               # regular-season overtime that ends tied

    # --- factor switches (data/nfl/factors.json may flip the prunable ones) ----------------
    use_home: bool = True
    use_rest: bool = True                         # short week / long rest odds ratios
    use_roof: bool = True                         # dome / outdoors scoring environment
    use_wind: bool = True                         # wind on outdoor passing and kicking
    use_qb_blend: bool = True                     # offense profile follows the starting quarterback
    use_half_shape: bool = True                   # separate first- and second-half outcome tables
    use_division: bool = False                    # division games: measured, off by default

    # --- confidence tiers ------------------------------------------------------------------
    tier_a_min_games: int = 4                     # current-season games for tier A (both teams); by then they outweigh last season
    tier_b_min_games: int = 2


PRUNABLE = ("use_rest", "use_roof", "use_wind", "use_qb_blend", "use_half_shape", "use_division", "use_snap_trend")


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


def prior_seasons_for(season: int, cfg: ModelConfig = CFG) -> list[int]:
    return [season - k for k in range(1, cfg.n_prior_seasons + 1)]


def prior_weight(season: int, current: int, cfg: ModelConfig = CFG) -> float:
    d = current - season
    if d <= 0:
        return 1.0
    if d <= len(cfg.prior_season_weights):
        return cfg.prior_season_weights[d - 1]
    return cfg.prior_season_weights[-1] * 0.5
