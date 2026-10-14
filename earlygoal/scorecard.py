"""Track record: score published predictions against what actually happened.

Each published day's page embeds the full prediction payload. Once the games
are final (they appear in the season records the next morning), every market
on every game is scored and folded into a running scorecard that the
dashboard shows as "Track record". Nothing is dropped or re-estimated: the
probabilities scored are exactly the ones that were on the page at the time.

Markets scored per game:
  u05_first5 / u05_first10   hit if no goal in the window (probability scored by Brier)
  p1_minus05 / p1_plus05     the pick shown on the page
  p1_ml                      the pick (win = period won; tie = loss for the -0.5 side)
  fg_ml                      the pick, including OT/SO
  fg_spread                  the pick at -1.5
  fg_total                   over 5.5 vs the page's probability
Also the Top-3 cards: hit rate of the three picks shown per category.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

from .ingest import GameRecord

MARKETS = ["u05_first5", "u05_first10", "p1_minus05", "p1_plus05", "p1_ml", "fg_ml", "fg_spread", "fg_over55"]
TOP_KEYS = ["u05_first5", "u05_first10", "p1_plus05", "p1_minus05", "p1_ml", "fg_ml", "fg_spread"]


def payload_from_page(path: Path) -> dict | None:
    html = path.read_text(encoding="utf-8")
    m = re.search(r'<script id="payload" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return None
    return json.loads(m.group(1).replace("<\\/", "</"))


def first_period_score(g: GameRecord) -> tuple[int, int]:
    h = sum(1 for e in g.events if e.type == "goal" and e.team == g.home and e.minute < 20)
    a = sum(1 for e in g.events if e.type == "goal" and e.team == g.away and e.minute < 20)
    return h, a


def score_game(row: dict, g: GameRecord) -> dict:
    first = min((e.minute for e in g.events if e.type == "goal"), default=99.0)
    h1, a1 = first_period_score(g)
    hs, as_ = g.home_score, g.away_score
    m = row["markets"]
    home, away = row["home"], row["away"]

    def side_won_period(team: str) -> bool:
        return (h1 > a1) if team == home else (a1 > h1)

    def side_won_game(team: str) -> bool:
        return (hs > as_) if team == home else (as_ > hs)

    def side_covered_m15(team: str) -> bool:
        return (hs - as_ >= 2) if team == home else (as_ - hs >= 2)

    out = {
        "game_id": row["game_id"], "matchup": row["matchup"], "tier": row["tier"],
        "final": f"{away} {as_} @ {home} {hs}{' (' + g.ended_in + ')' if g.ended_in in ('OT', 'SO') else ''}",
        "first_goal_min": None if first >= 99 else round(first, 2),
        "p1_score": f"{a1}-{h1}",
        "home": home, "away": away, "home_score": hs, "away_score": as_, "ended_in": g.ended_in, "p1_home": h1, "p1_away": a1,
        "markets": {
            "u05_first5": {"p": m["u05_first5"]["p"], "hit": int(first >= 5)},
            "u05_first10": {"p": m["u05_first10"]["p"], "hit": int(first >= 10)},
            "p1_minus05": {"pick": m["p1_minus05"]["pick"], "p": m["p1_minus05"]["p"], "hit": int(side_won_period(m["p1_minus05"]["pick"]))},
            "p1_plus05": {"pick": m["p1_plus05"]["pick"], "p": m["p1_plus05"]["p"], "hit": int(side_won_period(m["p1_plus05"]["pick"]) or h1 == a1)},
            "p1_ml": {"pick": m["p1_ml"]["pick"], "p": m["p1_ml"]["p"], "hit": int(side_won_period(m["p1_ml"]["pick"]))},
            "fg_ml": {"pick": m["fg_ml"]["pick"], "p": m["fg_ml"]["p"], "hit": int(side_won_game(m["fg_ml"]["pick"]))},
            "fg_spread": {"pick": m["fg_spread"]["pick"], "p": m["fg_spread"]["p"], "hit": int(side_covered_m15(m["fg_spread"]["pick"]))},
            "fg_over55": {"p": m["fg_total"]["over55"], "hit": int(hs + as_ > 5.5)},
        },
    }
    return out


def update_scorecard(scorecard: dict | None, payloads: list[dict], records: dict[int, GameRecord]) -> dict:
    """Fold newly final games into the scorecard. Days whose games are not all final stay pending."""
    sc = scorecard or {"days": {}, "pending": []}
    sc.setdefault("days", {})
    for p in payloads:
        date = p["date"]
        day = sc["days"].setdefault(date, {"games": {}, "top": {}})
        for row in p["games"]:
            gid = str(row["game_id"])
            if gid in day["games"]:
                continue
            g = records.get(row["game_id"])
            if g is None or not g.final:
                continue
            day["games"][gid] = score_game(row, g)
        # top-3 cards as shown on the page
        for key in TOP_KEYS:
            picks = (p.get("top") or {}).get(key) or []
            scored = []
            for pk in picks:
                sg = day["games"].get(str(pk["game_id"]))
                if sg is None:
                    continue
                mk = sg["markets"][key]
                scored.append({"matchup": pk["matchup"], "pick": pk.get("pick"), "p": pk["p"], "hit": mk["hit"]})
            if scored:
                day["top"][key] = scored
        day["n_published"] = len(p["games"])
    sc["pending"] = sorted(d for d, day in sc["days"].items() if len(day["games"]) < day.get("n_published", 0))
    sc["summary"] = summarize(sc)
    return sc


def summarize(sc: dict) -> dict:
    agg = {k: {"n": 0, "hits": 0, "p_sum": 0.0, "brier": 0.0} for k in MARKETS}
    top = {k: {"n": 0, "hits": 0, "p_sum": 0.0} for k in TOP_KEYS}
    potd = {"n": 0, "hits": 0, "p_sum": 0.0}
    for date in sorted(sc["days"]):
        day = sc["days"][date]
        for sg in day["games"].values():
            for k, v in sg["markets"].items():
                a = agg[k]
                a["n"] += 1
                a["hits"] += v["hit"]
                a["p_sum"] += v["p"]
                a["brier"] += (v["p"] - v["hit"]) ** 2
        for k, picks in day.get("top", {}).items():
            for i, pk in enumerate(picks):
                top[k]["n"] += 1
                top[k]["hits"] += pk["hit"]
                top[k]["p_sum"] += pk["p"]
                if k == "u05_first5" and i == 0:
                    potd["n"] += 1
                    potd["hits"] += pk["hit"]
                    potd["p_sum"] += pk["p"]
    out = {"markets": {}, "top3": {}, "pick_of_day": {}}
    for k, a in agg.items():
        if a["n"]:
            out["markets"][k] = {"n": a["n"], "hit_rate": round(a["hits"] / a["n"], 4), "mean_pred": round(a["p_sum"] / a["n"], 4), "brier": round(a["brier"] / a["n"], 4)}
    for k, a in top.items():
        if a["n"]:
            out["top3"][k] = {"n": a["n"], "hit_rate": round(a["hits"] / a["n"], 4), "mean_pred": round(a["p_sum"] / a["n"], 4)}
    if potd["n"]:
        out["pick_of_day"] = {"n": potd["n"], "hit_rate": round(potd["hits"] / potd["n"], 4), "mean_pred": round(potd["p_sum"] / potd["n"], 4)}
    out["days_scored"] = sum(1 for d in sc["days"].values() if d["games"])
    out["games_scored"] = sum(len(d["games"]) for d in sc["days"].values())
    return out
