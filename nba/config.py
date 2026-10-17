"""Configuration for the NBA engine. Everything tunable is here so the model can be audited in one place."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data" / "nba"
CACHE_DIR = DATA_DIR / "cache"
OUT_DIR = ROOT / "out" / "nba"
SITE_DIR = ROOT / "docs" / "nba"

MODEL_VERSION = "0.1.0"

# ESPN's public site API: schedule and scores by date, box scores, injuries and DraftKings game lines per game
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard"
ESPN_SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary"

# season = the year the season ends (2026-27 is season 2027), like ESPN's season.year
SEASON_START = {2026: "2025-10-21", 2027: "2026-10-20"}
SEASON_END = {2026: "2026-04-12", 2027: "2027-04-11"}

TEAMS = ("ATL", "BOS", "BKN", "CHA", "CHI", "CLE", "DAL", "DEN", "DET", "GS", "HOU", "IND", "LAC", "LAL", "MEM", "MIA", "MIL", "MIN", "NO", "NY",
         "OKC", "ORL", "PHI", "PHX", "POR", "SAC", "SA", "TOR", "UTAH", "WSH")
# The Odds API spells teams by full name; ESPN abbreviations are the site's keys
ODDS_TEAMS = {"Atlanta Hawks": "ATL", "Boston Celtics": "BOS", "Brooklyn Nets": "BKN", "Charlotte Hornets": "CHA", "Chicago Bulls": "CHI",
              "Cleveland Cavaliers": "CLE", "Dallas Mavericks": "DAL", "Denver Nuggets": "DEN", "Detroit Pistons": "DET", "Golden State Warriors": "GS",
              "Houston Rockets": "HOU", "Indiana Pacers": "IND", "Los Angeles Clippers": "LAC", "LA Clippers": "LAC", "Los Angeles Lakers": "LAL",
              "Memphis Grizzlies": "MEM", "Miami Heat": "MIA", "Milwaukee Bucks": "MIL", "Minnesota Timberwolves": "MIN", "New Orleans Pelicans": "NO",
              "New York Knicks": "NY", "Oklahoma City Thunder": "OKC", "Orlando Magic": "ORL", "Philadelphia 76ers": "PHI", "Phoenix Suns": "PHX",
              "Portland Trail Blazers": "POR", "Sacramento Kings": "SAC", "San Antonio Spurs": "SA", "Toronto Raptors": "TOR", "Utah Jazz": "UTAH",
              "Washington Wizards": "WSH"}


@dataclass
class ModelConfig:
    # --- team ratings: points per 100 possessions scored and allowed, pace per 48, recency-weighted and shrunk
    half_life_games: float = 15.0          # exponential weighting of a team's games this season
    prior_season_weight: float = 0.35      # a game last season counts this much of a current-season game
    k_team_games: float = 12.0             # pseudo-games toward the league average (ratings)
    home_court: float = 2.3                # points added to the home team's expected margin
    margin_sd: float = 12.6                # NBA final margin standard deviation around the expected margin
    total_sd: float = 18.5                 # final total standard deviation around the expected total

    # --- players
    player_half_life: float = 8.0          # exponential weighting of a player's games (minutes and per-minute rates)
    k_player_minutes: float = 3.0          # pseudo-games toward his season average for minutes
    k_player_rate: float = 6.0             # pseudo-games toward his prior for per-minute rates
    min_games_listed: int = 3              # games played this season (or 8 last season) before a projection is listed
    blowout_minutes: float = 0.92          # starters' minutes multiplier when the spread is 10 or more
    min_minutes_listed: float = 18.0       # projected minutes before a prop projection is listed
    # per-stat standard deviations relative to the mean (used when the player's own variance has too few games)
    sd_ratio: dict | None = None

    # --- market blend for props (the market is the anchor; the model moves it by at most this much)
    nudge_cap: float = 0.05
    model_weight: float = 0.35

    def __post_init__(self):
        if self.sd_ratio is None:
            self.sd_ratio = {"pts": 0.36, "reb": 0.42, "ast": 0.48, "threes": 0.70, "pra": 0.30}


CFG = ModelConfig()
