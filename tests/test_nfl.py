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
