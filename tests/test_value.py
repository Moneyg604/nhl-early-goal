"""Best-bets engine checks: line conversion, the model nudge, expected value, locking and the page's selection ids."""
from __future__ import annotations

import math

import numpy as np

from nfl.scorecard import grade
from nfl.value import (ATD_MAX_ODDS, GOOD_EV, NUDGE_CAP, Dist, _nudge, best_bets, devig, game_bets, normal_dist, picks_from_bets,
                       sel_id)


def _yards(mean: float, sd: float = 60.0) -> Dist:
    v = np.arange(0, 121) * 5.0
    p = np.exp(-0.5 * ((v - mean) / sd) ** 2)
    return Dist(0, list(p), 5.0)


def test_devig_removes_the_margin():
    assert abs(devig(1.91, 1.91) - 0.5) < 1e-12
    q = devig(1.6, 2.4)
    assert abs(q - (1 / 1.6) / (1 / 1.6 + 1 / 2.4)) < 1e-12


def test_same_line_reproduces_the_book_exactly():
    d = _yards(240)
    for q in (0.3, 0.5, 0.62):
        s = d.solve_shift(239.5, q)
        assert abs(d.two_way(239.5, s) - q) < 1e-6


def test_books_on_other_lines_move_onto_draftkings_line():
    d = _yards(240)
    # a book hanging 245.5 at 50/50 says the median is ~245.5, so the over at DraftKings' 240.5 is better than a coin flip
    s = d.solve_shift(245.5, 0.5)
    o, _, u = d.at(240.5, s)
    assert o > 0.52
    assert abs(d.median(s) - 245.5) < 5.1


def test_integer_stats_keep_pushes():
    d = Dist(0, [0.2, 0.3, 0.3, 0.2])             # 0..3 touchdowns
    o, pu, u = d.at(2.0)
    assert abs(o - 0.2) < 1e-12 and abs(pu - 0.3) < 1e-12 and abs(u - 0.5) < 1e-12
    o, pu, u = d.at(1.5, 0.5)                       # half-way shift mixes the two whole shifts
    assert 0 < o < 1 and pu == 0


def test_model_nudge_is_capped_and_fades_on_big_disagreement():
    f, n, _ = _nudge("qb_yds", 0.50, 0.58)
    assert 0 < n <= NUDGE_CAP + 1e-9
    f2, n2, note = _nudge("qb_yds", 0.50, 0.29)    # the Prescott case: 21 points apart -> the market stands
    assert n2 == 0 and f2 == 0.50 and "market trusted" in note
    f3, n3, _ = _nudge("spread", 0.50, 0.70)       # game lines: no nudge at all
    assert n3 == 0 and f3 == 0.50
    f4, n4, _ = _nudge("atd", 0.03, 0.10)          # a long shot cannot be doubled
    assert f4 < 0.04


def _game(dk_line=275.5, other_lines=(278.5, 278.5, 280.5, 273.5), model_mean=230.0):
    books = {"DraftKings": {"line": dk_line, "over": 1.88, "under": 1.90}}
    for i, L in enumerate(other_lines):
        books[f"B{i}"] = {"line": L, "over": 1.88, "under": 1.88}
    d = _yards(model_mean)
    vals = list(d.p)
    return {"game_id": "2026_06_DAL_GB", "home": "GB", "away": "DAL", "kickoff_utc": "2099-01-01T00:20Z",
            "odds": {"props": {"qb_yds": {"d.prescott": {"name": "Dak Prescott", "books": books}}}},
            "markets": {"dist": {}, "ml": {}, "qb": {"away": {"yds_pmf5": [0, vals]}}},
            "qb": {"away": {"name": "Dak Prescott"}, "home": {}}, "props": {}, "anytime": {}}


def test_a_biased_model_no_longer_makes_an_under_look_good():
    bets = game_bets(_game())
    under = next(b for b in bets if b["side"] == "under")
    over = next(b for b in bets if b["side"] == "over")
    # the market sits near 50/50 at DraftKings' 275.5; the model (median 230) says ~78% under, far outside the fade band
    assert abs(under["p_market"] - 0.5) < 0.05 and under["p_model"] > 0.7
    assert under["nudge"] == 0 and under["ev"] < 0 and not under["good"]
    assert over["ev"] < 0 and not over["good"]


def test_a_draftkings_line_far_off_the_market_is_found():
    # every other book hangs 290.5 at 50/50; DraftKings' 275.5 over is then well above 50% -> good bet
    bets = game_bets(_game(dk_line=275.5, other_lines=(290.5, 290.5, 290.5, 290.5), model_mean=285.0))
    over = next(b for b in bets if b["side"] == "over")
    assert over["p_market"] > 0.55 and over["ev"] >= GOOD_EV and over["good"]


def test_ev_arithmetic():
    bets = game_bets(_game())
    b = bets[0]
    assert abs(b["ev"] - (b["p"] * (b["odds"] - 1) - (1 - b["p"] - b["push"]))) < 1e-3
    assert abs(b["breakeven"] - 1 / b["odds"]) < 1e-3


def test_long_shot_touchdowns_are_never_good():
    g = _game()
    g["odds"]["props"] = {"atd": {"a.beck": {"name": "Andrew Beck", "books": {"DraftKings": {"yes": 66.0}, "B1": {"yes": 30.0}, "B2": {"yes": 30.0}, "B3": {"yes": 34.0}}}}}
    b = game_bets(g)[0]
    assert b["odds"] > ATD_MAX_ODDS and b["ev"] > 0 and not b["good"] and b["excluded"] == "long shot"


def test_started_games_lock_their_good_bets():
    g = _game(dk_line=275.5, other_lines=(290.5, 290.5, 290.5, 290.5), model_mean=285.0)
    p = {"games": [g]}
    first = best_bets(p)
    assert first["n_good"] == 1
    g2 = dict(g, kickoff_utc="2000-01-01T00:00Z")   # kicked off
    second = best_bets({"games": [g2]}, prev=first)
    assert second["n_good"] == 0 and len(second["locked"]) == 1 and second["locked"][0]["id"] == first["ranked"][0]["id"]
    picks = picks_from_bets(second, {"games": [g2]})
    assert picks["qb_yds"][0]["qb"] == "Dak Prescott" and picks["qb_yds"][0]["side"] == "over"


def test_spread_picks_grade_with_the_nflverse_convention():
    # DraftKings: GB -1.5 at home. picks_from_bets stores line 1.5 (home favoured), which the scorecard grades
    g = {"game_id": "X", "home": "GB", "away": "DAL"}
    bb = {"ranked": [{"id": "s", "good": True, "kind": "spread", "side": "home", "line": -1.5, "team": "GB", "game_id": "X", "mu": "DAL @ GB",
                      "p": 0.5, "odds": 1.95, "ev": 0.03, "label": "GB -1.5"},
                     {"id": "t", "good": True, "kind": "spread", "side": "away", "line": 1.5, "team": "DAL", "game_id": "X", "mu": "DAL @ GB",
                      "p": 0.5, "odds": 1.95, "ev": 0.03, "label": "DAL +1.5"}]}
    pk = picks_from_bets(bb, {"games": [g]})["spread"]
    rec = {"hs": 24, "as": 23}                      # GB by 1: GB -1.5 loses, DAL +1.5 wins
    res = {x["side"]: grade(x, rec, {}) for x in pk}
    assert res == {"home": "lost", "away": "won"}


def test_selection_ids_match_the_page():
    # the page builds ids with JavaScript's String(number): 53 -> "53", -1.5 -> "-1.5", null -> ""
    assert sel_id("total", "G", "over", 53.0, "") == "total|G|over|53|"
    assert sel_id("spread", "G", "home", -1.5, "GB") == "spread|G|home|-1.5|GB"
    assert sel_id("ml", "G", "home", None, "GB") == "ml|G|home||GB"
    assert sel_id("spread", "G", "away", -0.0, "DAL") == "spread|G|away|0|DAL"


def test_fallback_shape_for_unlisted_players():
    d = normal_dist(55.5, 25.0, 5.0)
    o, _, u = d.at(55.5)
    assert abs(o - 0.5) < 0.06 and math.isclose(o + u, 1.0, abs_tol=1e-9)


def test_weighted_median_is_the_ordinary_median_for_equal_weights():
    from nfl.value import wmedian
    assert wmedian([1, 2, 3, 4], [1, 1, 1, 1]) == 2.5
    assert wmedian([1, 2, 3], [1, 1, 1]) == 2
    assert wmedian([1, 2, 3, 4], [1, 1, 1, 3]) == 3.5      # Pinnacle-style double weight pulls it


def test_players_sharing_a_short_name_never_borrow_each_others_numbers():
    from nfl.odds import parse_props
    ev = {"home_team": "Atlanta Falcons", "away_team": "Chicago Bears", "bookmakers": [
        {"title": t, "markets": [{"key": "player_rush_yds", "outcomes": [
            {"description": "Bijan Robinson", "name": "Over", "point": 79.5, "price": 1.87}, {"description": "Bijan Robinson", "name": "Under", "point": 79.5, "price": 1.87},
            {"description": "Brian Robinson", "name": "Over", "point": 27.5, "price": 1.87}, {"description": "Brian Robinson", "name": "Under", "point": 27.5, "price": 1.87}]}]}
        for t in ("DraftKings", "FanDuel", "BetMGM")]}
    pp = parse_props(ev)["rush_yds"]
    assert set(pp) == {"bijan robinson", "brian robinson"}
    assert {b["line"] for b in pp["bijan robinson"]["books"].values()} == {79.5}


def test_books_far_apart_are_never_good():
    # a stored row mixing two players: DraftKings and one book at 79.5, two books at 27.5
    g = _game(dk_line=79.5, other_lines=(79.5, 27.5, 27.5), model_mean=60.0)
    for b in game_bets(g):
        assert not b["good"] and b["excluded"] == "books disagree"


def test_break_even_counts_pushes():
    d = Dist(-10, [0.0] * 7 + [0.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 0.4, 0.3])   # margins -10..5, 10% on exactly -3
    g = {"game_id": "X", "home": "GB", "away": "DAL", "kickoff_utc": "2099-01-01T00:00Z", "markets": {"dist": {"margin": [-10, list(d.p)]}, "ml": {}},
         "odds": {"spread": {"books": {"DraftKings": {"line": -3.0, "home": 2.0, "away": 1.8}, "B1": {"line": -3.0, "home": 1.9, "away": 1.9},
                                       "B2": {"line": -3.0, "home": 1.9, "away": 1.9}}}}, "qb": {}, "props": {}, "anytime": {}}
    home = next(b for b in game_bets(g) if b["kind"] == "spread" and b["side"] == "home")
    assert home["push"] > 0 and abs(home["breakeven"] - (1 - home["push"]) / home["odds"]) < 1e-3


def test_an_odds_row_never_matches_a_different_first_name_in_the_model():
    g = _game()
    g["qb"]["away"]["name"] = "Brian Robinson"                    # the model only knows Brian
    g["odds"]["props"]["qb_yds"] = {"b.robinson": {"name": "Bijan Robinson", "books": g["odds"]["props"]["qb_yds"]["d.prescott"]["books"]}}
    b = game_bets(g)[0]
    assert b["p_model"] is None and b["who"] == "Bijan Robinson"
