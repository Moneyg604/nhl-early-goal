"""The phone app's feed: the current week (NFL) or day (NBA) trimmed to the fields docs/app/index.html reads.

The full payload is 1 to 3 MB (every game's research, props, inputs and the simulation's samples); the app needs the
desk, the spec, the line moves, the board rows and the games' kickoff times and results, about a fifth of it. The
field paths are the payload's own, so the app reads the trimmed feed and the full payload the same way (it falls
back to the full payload when the feed is missing or older than the index).

    docs/nfl/app.json   written by nfl/site.py with "app": {"file": "app.json", "current": ..., "published": ...} in weeks.json
    docs/nba/app.json   written by nba/site.py, same entry in days.json
"""
from __future__ import annotations

import json
from pathlib import Path

GAME_KEYS = ("game_id", "season", "week", "date", "home", "away", "kickoff_utc", "tip_utc", "weekday", "stadium", "roof", "surface", "espn", "lines",
             "weather", "temp", "wind", "actual", "score", "frozen", "tier", "state", "status", "completed")
BET_KEYS = ("id", "game_id", "mu", "kick", "kind", "market", "side", "line", "who", "team", "pid", "label", "odds", "p", "push", "p_market", "p_model",
            "fair_odds", "breakeven", "ev", "good", "excluded", "books", "flags", "price", "group", "priced_at", "rank")
BOT_KEYS = ("generated", "week_label", "stamps", "desk", "desk_config", "hot")


def _bet(b: dict) -> dict:
    r = {k: b[k] for k in BET_KEYS if k in b}
    if isinstance(b.get("conf"), dict):
        r["conf"] = {"score": b["conf"].get("score"), "label": b["conf"].get("label")}
    if isinstance(b.get("desk"), dict):
        r["desk"] = {"p": b["desk"].get("p"), "grade": b["desk"].get("grade")}
    return r


def build(payload: dict) -> dict:
    """The trimmed copy (the payload itself is not changed)."""
    bb = payload.get("best_bets") or {}
    bot = payload.get("bot") or {}
    return {"app": {"v": 1}, **{k: payload[k] for k in ("sport", "season", "week", "date", "generated_utc") if k in payload},
            "games": [{k: g[k] for k in GAME_KEYS if k in g} for g in payload.get("games", [])],
            "best_bets": {**{k: bb[k] for k in ("book", "generated", "odds_fetched", "props_fetched_oldest", "n_priced") if k in bb},
                          "ranked": [_bet(b) for b in bb.get("ranked") or [] if isinstance(b, dict)]},
            "bot": {k: bot[k] for k in BOT_KEYS if k in bot}}


def write(site_dir: Path, payload: dict, current: str, published: str) -> dict | None:
    """Write <site_dir>/app.json; returns the index entry, or None when it could not be written (the app then reads
    the full payload, so a failure here never breaks the site)."""
    try:
        (site_dir / "app.json").write_text(json.dumps(build(payload), separators=(",", ":"), ensure_ascii=False))
        return {"file": "app.json", "current": current, "published": published}
    except Exception as e:  # noqa: BLE001
        print(f"app feed skipped: {e}")
        return None


__all__ = ["build", "write"]
