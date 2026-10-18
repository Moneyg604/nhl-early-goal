"""NFL engine checks: data reconciliation, simulation calibration, market arithmetic, grading, freezing."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pytest

from nfl.config import DATA_DIR
from nfl.live import name_key, parse_summary
from nfl.markets import fair_odds, over_under, pmf
from nfl.scorecard import grade
from nfl.site import freeze_started

HAVE_DATA = (DATA_DIR / "games_2025.jsonl").exists() and (DATA_DIR / "games_2024.jsonl").exists()


def test_name_keys_match_espn_and_nflverse():
    pairs = [("J.Smith-Njigba", "Jaxon Smith-Njigba"), ("A.St. Brown", "Amon-Ra St. Brown"), ("C.Stroud", "C.J. Stroud"),
             ("K.Walker", "Kenneth Walker III"), ("D.Metcalf", "DK Metcalf"), ("M.Harrison", "Marvin Harrison Jr."), ("J.Chase", "Ja'Marr Chase")]
    for a, b in pairs:
        assert name_key(a) == name_key(b), (a, b)
    assert name_key("J.Chase") != name_key("J.Cook")


def test_over_under_counts_pushes():
    p = pmf(np.array([40, 41, 41, 42, 44]), 0, 100)
    ov, pu, un = over_under(p, 0, 41)
    assert abs(ov - 0.4) < 1e-9 and abs(pu - 0.4) < 1e-9 and abs(un - 0.2) < 1e-9
    # fair odds with a push: the stake comes back on a push
    assert abs(fair_odds(0.4, 0.4) - 1.5) < 1e-3


def test_parse_summary_box():
    js = {"boxscore": {"players": [{"team": {"abbreviation": "WSH"}, "statistics": [
        {"name": "passing", "keys": ["completions/passingAttempts", "passingYards", "yardsPerPassAttempt", "passingTouchdowns"],
         "athletes": [{"athlete": {"displayName": "Jayden Daniels"}, "stats": ["20/30", "251", "8.4", "2"]}]},
        {"name": "rushing", "keys": ["rushingAttempts", "rushingYards", "yardsPerRushAttempt", "rushingTouchdowns"],
         "athletes": [{"athlete": {"displayName": "Brian Robinson Jr."}, "stats": ["12", "50", "4.2", "1"]}]},
        {"name": "kicking", "keys": ["fieldGoalsMade/fieldGoalAttempts"], "athletes": [{"athlete": {"displayName": "K"}, "stats": ["3/4"]}]}]}]}}
    box = parse_summary(js)
    assert box["qb"][name_key("Jayden Daniels")]["yds"] == 251
    assert box["fg"]["WAS"] == 3
    assert name_key("B.Robinson") in box["td"]


def _game(hs, as_, h1=(10, 7), fg_home=2):
    return {"hs": hs, "as": as_, "q": {"home": [h1[0], 0, hs - h1[0], 0], "away": [h1[1], 0, as_ - h1[1], 0]},
            "fg": {"KC": [{"r": "made"}] * fg_home, "LAC": []}, "qbs": {"KC": {"1": {"name": "P.Mahomes", "yds": 260, "td": 2}}, "LAC": {}},
            "players": {"KC": {"9": {"rtd": 1, "rectd": 0}}, "LAC": {}}}


def test_grading_rules():
    g = _game(24, 21)
    assert grade({"market": "ml", "side": "home"}, g, {}) == "won"
    assert grade({"market": "spread", "side": "home", "line": 3.0}, g, {}) == "push"
    assert grade({"market": "spread", "side": "away", "line": 3.5}, g, {}) == "won"
    assert grade({"market": "total", "side": "over", "line": 44.5}, g, {}) == "won"
    assert grade({"market": "h1", "side": "under", "line": 17.5}, g, {}) == "won"
    assert grade({"market": "h2", "side": "over", "line": 27.5}, g, {}) == "won"
    assert grade({"market": "fg", "team": "KC", "side": "over", "line": 1.5}, g, {}) == "won"
    assert grade({"market": "qb_yds", "team": "KC", "qb": "Patrick Mahomes", "side": "under", "line": 255.5}, g, {}) == "lost"
    assert grade({"market": "qb_td", "team": "KC", "qb": "Patrick Mahomes", "side": "over", "line": 1.5}, g, {}) == "won"
    assert grade({"market": "atd", "team": "KC", "id": "9"}, g, {}) == "won"
    assert grade({"market": "atd", "team": "KC", "id": "77"}, g, {}) is None


def test_freeze_keeps_pregame_numbers():
    old = {"games": [{"game_id": "A", "kickoff_utc": "2026-10-18T17:00Z", "markets": {"x": 1}}, {"game_id": "B", "kickoff_utc": "2026-10-19T00:20Z", "markets": {"x": 1}}],
           "picks": {"ml": [{"game_id": "A", "score": 0.9}, {"game_id": "B", "score": 0.6}]}}
    new = {"games": [{"game_id": "A", "kickoff_utc": "2026-10-18T17:00Z", "markets": {"x": 2}, "actual": {"hs": 20, "as": 17}},
                     {"game_id": "B", "kickoff_utc": "2026-10-19T00:20Z", "markets": {"x": 2}}], "picks": {}}
    now = datetime(2026, 10, 18, 20, 0, tzinfo=timezone.utc)
    out = freeze_started(new, old, now)
    a, b = out["games"]
    assert a["markets"] == {"x": 1} and a["actual"]["hs"] == 20 and a.get("frozen")
    assert b["markets"] == {"x": 2}


@pytest.mark.skipif(not HAVE_DATA, reason="nflverse seasons not ingested")
def test_drive_points_reconcile_with_final_scores():
    bad = 0; n = 0
    with (DATA_DIR / "games_2025.jsonl").open() as fh:
        for line in fh:
            g = json.loads(line)
            hp = sum(d["pts"] if d["t"] == g["home"] else d.get("opts", 0) for d in g["drives"])
            ap = sum(d["pts"] if d["t"] == g["away"] else d.get("opts", 0) for d in g["drives"])
            n += 1; bad += (hp, ap) != (g["hs"], g["as"])
            assert sum(g["q"]["home"]) == g["hs"] and sum(g["q"]["away"]) == g["as"]
    assert n > 250 and bad == 0


@pytest.mark.skipif(not HAVE_DATA, reason="nflverse seasons not ingested")
def test_neutral_simulation_matches_league():
    from nfl.features import build_profiles
    from nfl.ingest import load_games
    from nfl.sim import neutral_side, simulate
    games = load_games([2023, 2024, 2025])
    P = build_profiles(games, 2025)
    lt = P.league
    r = simulate(lt, neutral_side(lt), neutral_side(lt), n=40_000, seed=3)
    tot = r.total
    assert abs(tot.mean() - lt.total_mean) < 1.5
    assert abs(tot.std() - lt.total_sd) < 1.5
    assert abs(r.margin.std() - lt.margin_sd) < 1.0
    assert abs(r.fgm.mean() - lt.fg_made_per_team) < 0.15
    # the cumulative total distribution within 3 points of the league at the common lines
    act = np.array([g["hs"] + g["as"] for g in games])
    for L in (37.5, 41.5, 44.5, 47.5, 51.5):
        assert abs((tot > L).mean() - (act > L).mean()) < 0.04


def test_odds_parsing_best_price_and_consensus():
    from nfl.odds import parse_game_lines, parse_props
    ev = {"id": "e1", "home_team": "Denver Broncos", "away_team": "Seattle Seahawks", "commence_time": "2026-10-16T00:15:00Z", "bookmakers": [
        {"key": "dk", "title": "DraftKings", "markets": [
            {"key": "h2h", "outcomes": [{"name": "Denver Broncos", "price": 2.20}, {"name": "Seattle Seahawks", "price": 1.70}]},
            {"key": "spreads", "outcomes": [{"name": "Denver Broncos", "price": 1.91, "point": 2.5}, {"name": "Seattle Seahawks", "price": 1.91, "point": -2.5}]},
            {"key": "totals", "outcomes": [{"name": "Over", "price": 1.87, "point": 40.5}, {"name": "Under", "price": 1.95, "point": 40.5}]}]},
        {"key": "fd", "title": "FanDuel", "markets": [
            {"key": "h2h", "outcomes": [{"name": "Denver Broncos", "price": 2.30}, {"name": "Seattle Seahawks", "price": 1.66}]},
            {"key": "spreads", "outcomes": [{"name": "Denver Broncos", "price": 1.95, "point": 2.5}, {"name": "Seattle Seahawks", "price": 1.87, "point": -2.5}]}]}]}
    g = parse_game_lines([ev])["SEA@DEN"]
    assert g["ml"]["home"] == 2.30 and g["ml"]["book_home"] == "FanDuel" and g["ml"]["away"] == 1.70
    assert 0.40 < g["ml"]["consensus_home"] < 0.45
    assert g["spread"]["line"] == 2.5 and g["spread"]["home"] == 1.95 and g["total"]["line"] == 40.5
    pe = {"home_team": "Denver Broncos", "away_team": "Seattle Seahawks", "bookmakers": [{"title": "DraftKings", "markets": [
        {"key": "player_pass_yds", "outcomes": [{"name": "Over", "description": "Bo Nix", "price": 1.87, "point": 205.5}, {"name": "Under", "description": "Bo Nix", "price": 1.95, "point": 205.5}]},
        {"key": "player_anytime_td", "outcomes": [{"name": "Yes", "description": "RJ Harvey", "price": 3.4}]},
        {"key": "totals_h1", "outcomes": [{"name": "Over", "price": 1.9, "point": 20.5}, {"name": "Under", "price": 1.9, "point": 20.5}]}]}]}
    pr = parse_props(pe)
    assert pr["qb_yds"][name_key("Bo Nix")]["line"] == 205.5 and pr["qb_yds"][name_key("Bo Nix")]["over"] == 1.87
    assert pr["atd"][name_key("RJ Harvey")]["yes"] == 3.4
    assert pr["h1"]["line"] == 20.5


def test_market_weights_match_moneyline_and_spread():
    from nfl.markets import ml_weights
    from nfl.sim import SimResult
    rng = np.random.default_rng(1)
    n = 50000
    hp = rng.poisson(24, n); ap = rng.poisson(20, n)
    z = np.zeros((n, 2), dtype=int)
    r = SimResult(n=n, pts=np.stack([hp, ap], 1), h1=z, fgm=z, fga=z, ptd=z, rtd=z, yds=z.astype(float), db=z, ot=np.zeros(n, bool), drives=z)
    lines = {"home_ml": -300, "away_ml": 250, "spread": 6.5, "home_spread_odds": -110, "away_spread_odds": -110}
    w, meta = ml_weights(r, lines)
    m = hp - ap
    p_home = (w * (m > 0)).sum() / w.sum() / (1 - (w * (m == 0)).sum() / w.sum())
    assert abs(p_home - meta["market_home"]) < 0.005
    assert abs((w * (m > 6.5)).sum() / w.sum() - 0.5) < 0.005


def test_overtime_rules():
    """2025 regular-season overtime: both teams possess even after a first-drive touchdown, next score wins after
    that, defensive scores end it at once, the clock running out leaves a tie."""
    from nfl.sim import ot_over, RES
    TD, FG, FGM, PUNT, TO, DOWNS, EOH, OPPTD, SAF = (RES.index(k) for k in ("TD", "FG", "FGM", "PUNT", "TO", "DOWNS", "EOH", "OPPTD", "SAF"))
    def over(res, poss, rem, diff):
        return bool(ot_over(np.array([res]), np.array([poss]), np.array([rem]), np.array([diff]))[0])
    assert not over(TD, 1, 400.0, True)          # first-possession touchdown: the other team still gets the ball
    assert not over(FG, 1, 400.0, True)          # first-possession field goal: same
    assert not over(PUNT, 1, 400.0, False)
    assert over(TD, 2, 300.0, True)              # answer with a lead after both possessed: over
    assert over(FG, 2, 300.0, True)
    assert not over(FG, 2, 300.0, False)         # both kicked field goals: level, sudden death continues
    assert not over(TD, 2, 300.0, False)         # both scored touchdowns: level, continue
    assert over(FG, 3, 200.0, True)              # first score after that wins
    assert over(OPPTD, 1, 400.0, True)           # defensive touchdown ends it at once
    assert over(SAF, 1, 400.0, True)             # safety ends it at once
    assert over(EOH, 1, 0.0, False)              # clock runs out: tie
    assert over(PUNT, 2, 0.3, False)
    assert not over(TO, 2, 100.0, False)         # a turnover with the score level keeps going


@pytest.mark.skipif(not HAVE_DATA, reason="nflverse seasons not ingested")
def test_overtime_frequency_and_ties():
    from nfl.features import build_profiles
    from nfl.ingest import load_games
    from nfl.sim import neutral_side, simulate
    games = load_games([2023, 2024, 2025])
    P = build_profiles(games, 2025)
    lt = P.league
    r = simulate(lt, neutral_side(lt), neutral_side(lt), n=40_000, seed=7)
    ot_rate = r.ot.mean()
    tie_rate = (r.pts[:, 0] == r.pts[:, 1]).mean()
    act_ot = np.mean([len(g["q"]["home"]) > 4 for g in games])          # 5.3% of 2023-25 games went to overtime
    assert abs(ot_rate - act_ot) < 0.02, (ot_rate, act_ot)
    assert tie_rate < 0.01, tie_rate                 # ties are rare (1 in 816 real games)
    assert tie_rate < ot_rate
