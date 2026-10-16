"""The bot's judgment: checks, category lists, the combined top six, the TD board and the payload block."""
from __future__ import annotations

import sys
from pathlib import Path

from nfl.brain import COMBINE_ODDS, bot_block, category_picks, combine_top, judge
from nfl.value import best_bets

from test_value import _game


def _payload(**kw) -> dict:
    g = _game(**kw)
    g["qb"]["away"]["profile"] = {"last_games": [{"date": "2026-09-10", "yds": 300, "td": 2, "db": 40, "opp": "X"},
                                                 {"date": "2026-09-17", "yds": 310, "td": 3, "db": 41, "opp": "Y"},
                                                 {"date": "2026-09-24", "yds": 295, "td": 2, "db": 39, "opp": "Z"}]}
    g["tier"] = "A"
    p = {"season": 2026, "week": 6, "generated_utc": "2026-10-16T12:00Z", "meta": {"league": {}, "sources": []}, "games": [g]}
    p["best_bets"] = best_bets(p)
    return p


def test_judge_fails_a_bet_this_seasons_form_points_against():
    p = _payload(dk_line=275.5, other_lines=(290.5, 290.5, 290.5, 290.5), model_mean=285.0)
    g = p["games"][0]
    over = next(b for b in p["best_bets"]["ranked"] if b["side"] == "over")
    under = dict(over, side="under", label="Dak Prescott under 275.5 pass yds", id="u", p=1 - over["p"], p_model=1 - over["p_model"], p_market=1 - over["p_market"])
    meta = {"league": {}, "sources": [], "generated_utc": "2026-10-16T12:00Z"}
    jo = judge(over, g, meta, 2026)
    ju = judge(under, g, meta, 2026)
    form_o = next(c for c in jo["checks"] if c["name"] == "Season form vs the line")
    assert form_o["ok"] is True and jo["hard_fail"] is None
    assert ju["hard_fail"] == "this season's form points the other way"
    assert jo["score"] > ju["score"]


def test_bot_block_builds_categories_and_the_top_six_without_anytime_td():
    p = _payload(dk_line=275.5, other_lines=(290.5, 290.5, 290.5, 290.5), model_mean=285.0)
    bot = bot_block(p)
    p["bot"] = bot
    assert set(bot["cats"]) == {"passing", "receiving", "rushing", "totals", "moneyline", "spread", "fieldgoals"}
    assert bot["cats"]["passing"]["ids"], "the good passing bet should be the passing pick"
    legs = bot["combine"]["legs"]
    assert all(l["kind"] != "atd" for l in legs)
    assert all(COMBINE_ODDS[0] <= l["odds"] <= COMBINE_ODDS[1] for l in legs)
    assert len({l["game_id"] for l in legs}) == len(legs)          # one per game
    ranked = p["best_bets"]["ranked"]
    assert all("conf" in b and "price" in b and "analysis" in b and "judge" in b for b in ranked)
    assert bot["tds"] == []


def test_combine_skips_prices_outside_the_band():
    board = [{"id": "a", "game_id": "G1", "kind": "ml", "odds": 1.30, "p": 0.78, "judge": {"score": 0.9, "passed": 3, "failed": 0, "checks": [], "hard_fail": None}, "label": "A"},
             {"id": "b", "game_id": "G1", "kind": "spread", "odds": 1.90, "p": 0.55, "judge": {"score": 0.6, "passed": 2, "failed": 1, "checks": [], "hard_fail": None}, "label": "B"},
             {"id": "c", "game_id": "G2", "kind": "total", "odds": 1.85, "p": 0.56, "judge": {"score": 0.62, "passed": 2, "failed": 0, "checks": [], "hard_fail": None}, "label": "C"}]
    cats = {"moneyline": {"label": "", "n": 4, "ids": ["a"]}, "spread": {"label": "", "n": 4, "ids": ["b"]}, "totals": {"label": "", "n": 4, "ids": ["c"]}}
    C = combine_top(board, cats)
    assert [l["id"] for l in C["legs"]] == ["c", "b"]               # 1.30 is below the band; one leg per game
    assert C["n"] == 2 and not C["complete"]


def test_notifier_lists_the_bots_picks_and_the_top_six():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import notify_nfl as N
    p = _payload(dk_line=275.5, other_lines=(290.5, 290.5, 290.5, 290.5), model_mean=285.0)
    p["bot"] = bot_block(p)
    txt = N.build(p, "weekly", False)
    assert "Bot's picks" in txt and "Passing yards and TD passes" in txt and "Dak Prescott over 275.5" in txt
    assert "Bot's top" in txt and "Player props" in txt
    assert "anytime" not in txt.lower().replace("no anytime td", "")
