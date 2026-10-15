"""nhlprops: NHL player and game props (shots on goal, points, assists, goals, blocked shots, team totals,
power-play goals) built from the sportsdataverse play-by-play releases and validated walk-forward."""
from .config import CFG, DATA_DIR, MODEL_VERSION

__all__ = ["CFG", "DATA_DIR", "MODEL_VERSION"]
