"""The NBA research desk: the same overlay machinery as the NFL desk (nfl/desk.py), keyed by date instead of week.

    data/nba/research/<date>.json      the overlay a Claude research session writes
    data/nba/desk_config.json          the owner's settings for the desk

Overlay keys: "season", "date" (YYYY-MM-DD, no "week"), and otherwise the NFL schema; kinds are ml, spread, total,
pts, reb, ast, threes, pra; selection ids match the board's ("pts|2026_10_20_BOS_DET|over|27.5|Jayson Tatum").
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import nfl.desk as D

from .config import DATA_DIR

RESEARCH_DIR = DATA_DIR / "research"
CONFIG_PATH = DATA_DIR / "desk_config.json"


@contextmanager
def _nba():
    old = (D.RESEARCH_DIR, D.CONFIG_PATH)
    D.RESEARCH_DIR, D.CONFIG_PATH = RESEARCH_DIR, CONFIG_PATH
    try:
        yield
    finally:
        D.RESEARCH_DIR, D.CONFIG_PATH = old


def overlay_path(date: str) -> Path:
    return RESEARCH_DIR / f"{date}.json"


def load_config() -> dict:
    with _nba():
        return D.load_config()


def validate(d: dict, payload: dict | None = None) -> list[str]:
    with _nba():
        return D.validate(d, payload)


def merge(payload: dict, overlay: dict | None = None):
    with _nba():
        return D.merge(payload, overlay)


def write_overlay(d: dict) -> Path:
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    import json
    f = overlay_path(d["date"])
    f.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    return f


__all__ = ["overlay_path", "load_config", "validate", "merge", "write_overlay", "RESEARCH_DIR", "CONFIG_PATH"]
