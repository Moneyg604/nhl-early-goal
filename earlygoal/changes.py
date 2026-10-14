"""What changed between two builds of the same slate: goalies, probabilities, tiers, games."""
from __future__ import annotations

import json
from pathlib import Path

from .config import OUT_DIR, ROOT

WATCH = [
    ("u05_first5", "under 0.5 first 5"), ("u05_first10", "under 0.5 first 10"), ("fg_ml", "FG moneyline"),
    ("fg_over45", "over 4.5"), ("home_over15", "home over 1.5"), ("away_over15", "away over 1.5"), ("p1_under25", "1P under 2.5"),
]


def previous_payload(date: str) -> dict | None:
    """The last build of this date the reader could have seen: the published page first, then out/."""
    from .scorecard import payload_from_page

    page = ROOT / "docs" / "days" / f"{date}.raw.html"
    if page.exists():
        try:
            return payload_from_page(page)
        except Exception:  # noqa: BLE001
            pass
    res = OUT_DIR / f"results-{date}.json"
    if res.exists():
        try:
            return json.loads(res.read_text())
        except Exception:  # noqa: BLE001
            pass
    return None


def diff_payloads(prev: dict | None, cur: dict, move_threshold: float = 0.01) -> dict:
    if not prev or not prev.get("games"):
        return {"since": None, "items": [], "first_build": True}
    items: list[dict] = []
    prev_games = {g["game_id"]: g for g in prev["games"]}
    cur_ids = {g["game_id"] for g in cur["games"]}
    for g in cur["games"]:
        pg = prev_games.get(g["game_id"])
        if pg is None:
            items.append({"game_id": g["game_id"], "game": g["matchup"], "kind": "slate", "text": "added to the slate"})
            continue
        for side in ("home", "away"):
            a, b = pg["goalies"][side], g["goalies"][side]
            if (a.get("name") or "") != (b.get("name") or ""):
                items.append({"game_id": g["game_id"], "game": g["matchup"], "kind": "goalie",
                              "text": f"{g[side]} goalie now {b.get('name') or 'unknown'} ({b.get('status')}), was {a.get('name') or 'unknown'} ({a.get('status')})"})
            elif (a.get("status") or "") != (b.get("status") or ""):
                items.append({"game_id": g["game_id"], "game": g["matchup"], "kind": "status",
                              "text": f"{g[side]} {b.get('name') or 'goalie'} now {b.get('status')}, was {a.get('status')}"})
        if pg.get("tier") != g.get("tier"):
            items.append({"game_id": g["game_id"], "game": g["matchup"], "kind": "tier", "text": f"tier {pg.get('tier')} to {g.get('tier')}"})
        for key, label in WATCH:
            if key not in g["markets"] or key not in pg["markets"]:
                continue
            a, b = pg["markets"][key]["p"], g["markets"][key]["p"]
            if abs(b - a) >= move_threshold:
                pick = g["markets"][key].get("pick")
                items.append({"game_id": g["game_id"], "game": g["matchup"], "kind": "move",
                              "text": f"{label}{' ' + pick if pick and key == 'fg_ml' else ''} {a*100:.1f}% to {b*100:.1f}%", "delta": round(b - a, 4), "market": key})
    for gid, pg in prev_games.items():
        if gid not in cur_ids:
            items.append({"game_id": gid, "game": pg["matchup"], "kind": "slate", "text": "no longer on the slate"})
    return {"since": prev.get("generated_utc"), "items": items, "first_build": False,
            "data_through_before": (prev.get("meta") or {}).get("data_through"), "data_through_after": (cur.get("meta") or {}).get("data_through")}
