"""Ranking, confidence tiers, picks and the JSON payload the dashboard renders.

Rules carried over from the SLATE workflow:
  * no probability without inputs: every number ships with its labelled inputs
  * book prices never enter the ranking; if odds are supplied they are only
    used AFTER ranking to display fair price / edge
  * fewer high-quality picks beat a padded list: top-3 cards only show games
    whose tier is A or B
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import DATA_DIR, MODEL_VERSION
from .model import GameModel
from .sim import SimResult

TIER_ORDER = {"A": 0, "B": 1, "C": 2}


def load_odds(date: str, path: Path | None = None) -> dict:
    p = path or (DATA_DIR / "odds.json")
    if not p.exists():
        return {}
    with p.open() as f:
        all_odds = json.load(f)
    return all_odds.get(date, {})


def _et(start_utc: str) -> str:
    if not start_utc:
        return ""
    try:
        dt = datetime.fromisoformat(start_utc.replace("Z", "+00:00")).astimezone(ZoneInfo("America/Toronto"))
        return dt.strftime("%-I:%M %p ET")
    except Exception:
        return start_utc


def _pick(home: str, away: str, ph: float, pa: float) -> tuple[str, float]:
    return (home, ph) if ph >= pa else (away, pa)


def game_row(gm: GameModel, r: SimResult, odds: dict) -> dict:
    home, away = gm.home, gm.away
    key = f"{away}@{home}"
    o = odds.get(key, {})

    def with_odds(market: str, p: float, side: str | None = None) -> dict:
        """Attach the book's price when the odds file has one. Two-sided markets store {"home": x, "away": y};
        `side` says which one the pick is."""
        d = {"p": round(p, 4), "fair": round(1 / p, 3) if p > 0 else None}
        v = o.get(market)
        price = None
        if isinstance(v, dict):
            if side and isinstance(v.get(side), (int, float)):
                price = float(v[side])
                bk = (v.get("book") or {}).get(side)
                if bk:
                    d["book_name"] = bk
        elif isinstance(v, (int, float)):
            price = float(v)
        if price and price > 1:
            d["book"] = price
            d["edge"] = round(p * price - 1, 4)
        return d

    m15_pick, m15_p = _pick(home, away, r.fg_home_cover_m15, r.fg_away_cover_m15)
    p15_pick, p15_p = _pick(home, away, r.fg_home_cover_p15, r.fg_away_cover_p15)
    p1m_pick, p1m_p = _pick(home, away, r.p1_home_win, r.p1_away_win)
    p1p_pick, p1p_p = _pick(home, away, r.p1_home_win + r.p1_tie, r.p1_away_win + r.p1_tie)
    fgml_pick, fgml_p = _pick(home, away, r.fg_home_win, r.fg_away_win)

    inputs = gm.inputs
    sides = inputs["sides"]
    return {
        "game_id": gm.game_id,
        "key": key,
        "matchup": f"{away} @ {home}",
        "home": home,
        "away": away,
        "time_et": _et(gm.start_utc),
        "tier": gm.tier,
        "tier_reasons": gm.tier_reasons,
        "markets": {
            "u05_first5": with_odds("u05_first5", r.p_no_goal_5),
            "o05_first5": with_odds("o05_first5", 1 - r.p_no_goal_5),
            "u05_first10": with_odds("u05_first10", r.p_no_goal_10),
            "o05_first10": with_odds("o05_first10", 1 - r.p_no_goal_10),
            "p1_minus05": {"pick": p1m_pick, **with_odds("p1_minus05", p1m_p)},
            "p1_plus05": {"pick": p1p_pick, **with_odds("p1_plus05", p1p_p)},
            "p1_ml": {"pick": p1m_pick, **with_odds("p1_ml", p1m_p), "home": round(r.p1_home_win, 4), "tie": round(r.p1_tie, 4), "away": round(r.p1_away_win, 4)},
            "fg_ml": {"pick": fgml_pick, **with_odds("fg_ml", fgml_p, "home" if fgml_pick == home else "away"), "home": round(r.fg_home_win, 4), "away": round(r.fg_away_win, 4),
                      "home_reg": round(r.fg_home_reg_win, 4), "away_reg": round(r.fg_away_reg_win, 4), "reg_tie": round(r.fg_reg_tie, 4)},
            "fg_spread": {"pick": m15_pick, "line": -1.5, **with_odds("fg_spread_m15", m15_p, "home" if m15_pick == home else "away"), "plus_pick": p15_pick, "plus_p": round(p15_p, 4)},
            "fg_total": {"mean": round(r.fg_mean_home + r.fg_mean_away, 3), "over55": round(r.fg_over_55, 4), "over65": round(r.fg_over_65, 4),
                         **({"book_line": o["fg_total"].get("line"), "book_over": o["fg_total"].get("over"), "book_under": o["fg_total"].get("under")} if isinstance(o.get("fg_total"), dict) else {})},
            "fg_over45": with_odds("fg_over45", r.fg_over_45),
            "home_over15": {"pick": home, **with_odds("home_over15", r.home_over_15)},
            "away_over15": {"pick": away, **with_odds("away_over15", r.away_over_15)},
            "p1_under25": with_odds("p1_under25", r.p1_under_25),
        },
        "analytic": {"u05_first5": round(r.p_no_goal_5_analytic, 4), "u05_first10": round(r.p_no_goal_10_analytic, 4)},
        "uncertainty": inputs.get("uncertainty", {}),
        "mc_se": {"first5": round(r.mc_se_5, 5), "first10": round(r.mc_se_10, 5)},
        "first_goal_hist": [round(x, 4) for x in r.first_goal_minute_hist],
        "p1": {"home": round(r.p1_home_win, 4), "tie": round(r.p1_tie, 4), "away": round(r.p1_away_win, 4), "total_dist": [round(x, 4) for x in r.p1_total_dist], "mean_total": round(r.p1_mean_total, 3)},
        "projected": {"home": round(r.fg_mean_home, 2), "away": round(r.fg_mean_away, 2), "median": list(r.median_score)},
        "goalies": {
            "home": sides["away"]["faces_goalie"],   # the goalie the away side faces = home goalie
            "away": sides["home"]["faces_goalie"],
        },
        "sides": sides,
        "league": inputs["league"],
        "unmeasured": inputs["unmeasured"],
        "sims": r.sims,
    }


def build_payload(rows: list[dict], date: str, lp_summary: dict, meta: dict) -> dict:
    ab = [x for x in rows if x["tier"] in ("A", "B")] or rows

    def top(market: str, n: int = 3, key=lambda m: m["p"]) -> list[dict]:
        pool = sorted(ab, key=lambda x: (-key(x["markets"][market]), TIER_ORDER[x["tier"]]))
        return [{"matchup": x["matchup"], "pick": x["markets"][market].get("pick"), "p": x["markets"][market]["p"], "tier": x["tier"], "game_id": x["game_id"]} for x in pool[:n]]

    ranked_f5 = sorted(rows, key=lambda x: (TIER_ORDER[x["tier"]], -x["markets"]["u05_first5"]["p"]))
    for i, x in enumerate(ranked_f5):
        x["rank_u05_first5"] = i + 1
    ranked_f10 = sorted(rows, key=lambda x: (TIER_ORDER[x["tier"]], -x["markets"]["u05_first10"]["p"]))
    for i, x in enumerate(ranked_f10):
        x["rank_u05_first10"] = i + 1

    potd = ranked_f5[0] if ranked_f5 else None
    return {
        "date": date,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "model_version": MODEL_VERSION,
        "meta": meta,
        "league": lp_summary,
        "pick_of_day": None if potd is None else {
            "matchup": potd["matchup"], "market": "Under 0.5 goals, first 5:00", "p": potd["markets"]["u05_first5"]["p"],
            "fair": potd["markets"]["u05_first5"]["fair"], "tier": potd["tier"], "game_id": potd["game_id"],
            "runner_up": None if len(ranked_f5) < 2 else {"matchup": ranked_f5[1]["matchup"], "p": ranked_f5[1]["markets"]["u05_first5"]["p"], "tier": ranked_f5[1]["tier"]},
        },
        "top": {
            "u05_first5": top("u05_first5"),
            "u05_first10": top("u05_first10"),
            "fg_over45": top("fg_over45"),
            "team_over15": sorted(
                [{"matchup": x["matchup"], "pick": x["markets"][k]["pick"], "p": x["markets"][k]["p"], "tier": x["tier"], "game_id": x["game_id"], "market": k}
                 for x in ab for k in ("home_over15", "away_over15")], key=lambda t: -t["p"])[:3],
            "p1_under25": top("p1_under25"),
            "p1_plus05": top("p1_plus05"),
            "p1_minus05": top("p1_minus05"),
            "p1_ml": top("p1_ml"),
            "fg_ml": top("fg_ml"),
            "fg_spread": top("fg_spread"),
        },
        "games": sorted(rows, key=lambda x: x["game_id"]),
    }


def write_csv(rows: list[dict], path: Path) -> None:
    import csv

    cols = ["rank_u05_first5", "matchup", "time_et", "tier", "u05_first5", "fair_first5", "u05_first10", "fair_first10",
            "p1_minus05_pick", "p1_minus05", "p1_plus05_pick", "p1_plus05", "p1_ml_pick", "p1_ml", "fg_ml_pick", "fg_ml",
            "fg_spread_pick", "fg_spread_m15", "proj_home", "proj_away", "home_goalie", "home_goalie_status", "away_goalie", "away_goalie_status"]
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for x in sorted(rows, key=lambda r: r["rank_u05_first5"]):
            m = x["markets"]
            w.writerow([
                x["rank_u05_first5"], x["matchup"], x["time_et"], x["tier"],
                m["u05_first5"]["p"], m["u05_first5"]["fair"], m["u05_first10"]["p"], m["u05_first10"]["fair"],
                m["p1_minus05"]["pick"], m["p1_minus05"]["p"], m["p1_plus05"]["pick"], m["p1_plus05"]["p"],
                m["p1_ml"]["pick"], m["p1_ml"]["p"], m["fg_ml"]["pick"], m["fg_ml"]["p"],
                m["fg_spread"]["pick"], m["fg_spread"]["p"], x["projected"]["home"], x["projected"]["away"],
                x["goalies"]["home"]["name"], x["goalies"]["home"]["status"], x["goalies"]["away"]["name"], x["goalies"]["away"]["status"],
            ])
