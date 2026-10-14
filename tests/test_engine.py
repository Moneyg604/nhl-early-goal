import math

from earlygoal.demo import build_demo
from earlygoal.features import build_league_profile, build_profiles
from earlygoal.ingest import parse_play_by_play
from earlygoal.model import SideInputs, build_game_model
from earlygoal.sim import simulate


def _side(team, home, rest=None):
    return SideInputs(team, home, None, None, "unknown", "none", "", rest or {})


def test_sim_matches_analytic_on_priors():
    lp = build_league_profile([])
    gm = build_game_model({"game_id": 1, "date": "2026-10-13", "start_utc": ""}, _side("NYI", True), _side("VAN", False), lp)
    r = simulate(gm, sims=200_000, seed=11)
    assert abs(r.p_no_goal_5 - r.p_no_goal_5_analytic) < 4 * r.mc_se_5 + 1e-9
    assert abs(r.p_no_goal_10 - r.p_no_goal_10_analytic) < 4 * r.mc_se_10 + 1e-9
    assert 0.55 < r.p_no_goal_5 < 0.80
    assert 0.30 < r.p_no_goal_10 < 0.60
    assert abs(r.fg_home_win + r.fg_away_win - 1) < 1e-9
    assert abs(r.p1_home_win + r.p1_tie + r.p1_away_win - 1) < 1e-9
    assert r.fg_home_cover_m15 < r.fg_home_win < r.fg_home_cover_p15


def test_context_multipliers_move_rates_in_the_right_direction():
    lp = build_league_profile([])
    base = build_game_model({"game_id": 1, "date": "d", "start_utc": ""}, _side("A", True, {"b2b": False, "days_rest": 1}), _side("B", False, {"b2b": False, "days_rest": 1}), lp)
    tired = build_game_model({"game_id": 1, "date": "d", "start_utc": ""}, _side("A", True, {"b2b": False, "days_rest": 1}), _side("B", False, {"b2b": True, "days_rest": 0}), lp)
    # a back-to-back away side allows more, so the no-goal probability falls
    assert tired.p_no_goal_before(5) < base.p_no_goal_before(5)


def test_parse_play_by_play_minimal():
    pbp = {
        "id": 2026020001, "season": 20262027, "gameDate": "2026-10-07", "startTimeUTC": "2026-10-07T23:00:00Z", "gameState": "OFF",
        "homeTeam": {"id": 10, "abbrev": "TOR", "score": 2}, "awayTeam": {"id": 8, "abbrev": "MTL", "score": 1},
        "gameOutcome": {"lastPeriodType": "REG"},
        "rosterSpots": [{"playerId": 1, "positionCode": "G", "firstName": {"default": "Joseph"}, "lastName": {"default": "Woll"}},
                        {"playerId": 2, "positionCode": "G", "firstName": {"default": "Sam"}, "lastName": {"default": "Montembeault"}}],
        "plays": [
            {"typeDescKey": "shot-on-goal", "periodDescriptor": {"number": 1, "periodType": "REG"}, "timeInPeriod": "00:40", "situationCode": "1551", "details": {"eventOwnerTeamId": 8, "goalieInNetId": 1}},
            {"typeDescKey": "goal", "periodDescriptor": {"number": 1, "periodType": "REG"}, "timeInPeriod": "03:30", "situationCode": "1451", "details": {"eventOwnerTeamId": 10, "goalieInNetId": 2}},
            {"typeDescKey": "penalty", "periodDescriptor": {"number": 1, "periodType": "REG"}, "timeInPeriod": "05:00", "situationCode": "1551", "details": {"eventOwnerTeamId": 8, "duration": 2}},
            {"typeDescKey": "goal", "periodDescriptor": {"number": 3, "periodType": "REG"}, "timeInPeriod": "19:10", "situationCode": "0651", "details": {"eventOwnerTeamId": 10, "goalieInNetId": 2}},
            {"typeDescKey": "goal", "periodDescriptor": {"number": 5, "periodType": "SO"}, "timeInPeriod": "00:00", "situationCode": "1010", "details": {"eventOwnerTeamId": 8}},
        ],
    }
    rec = parse_play_by_play(pbp)
    assert rec.final and rec.home == "TOR" and rec.away == "MTL"
    assert rec.starters == {"home": 1, "away": 2}
    assert len(rec.events) == 4  # shootout attempt dropped
    g1 = rec.events[1]
    assert g1.type == "goal" and g1.team == "TOR" and math.isclose(g1.minute, 3.5) and g1.strength == "PP"
    assert math.isclose(rec.events[3].minute, 59.1667, abs_tol=1e-3)
    assert rec.goalie_names["1"] == "Joseph Woll"


def test_profiles_from_demo_are_sane():
    prior, current, slate, league = build_demo(5)
    lp, teams, goalies = build_profiles(current, prior)
    assert lp.games > 1000
    assert 0.55 < lp.p_no_goal_5 < 0.80
    assert 0.88 < lp.sv_pct < 0.92
    assert len(teams) == 32
    # the synthetic league's best offence should carry an above-average offensive multiplier
    best = max(league, key=lambda t: league[t]["off"])
    worst = min(league, key=lambda t: league[t]["off"])
    assert teams[best].mults(lp)["off_shot_full"] > teams[worst].mults(lp)["off_shot_full"]


def test_sdv_conversion_minimal(tmp_path):
    import pandas as pd
    from earlygoal.ingest_sdv import load_sdv

    rows = []
    def ev(et, period, ptype, secs, team, goalie=None, ss="5v5", pim=None, hs=0, as_=0):
        rows.append({"game_id": 2025020001, "season": "20252026", "season_type": "R", "game_date": "2025-10-07", "home_abbr": "FLA", "away_abbr": "CHI",
                     "event_type": et, "period": period, "period_type": ptype, "game_seconds": secs, "event_team_abbr": team,
                     "event_goalie_id": goalie, "event_goalie_name": "G" if goalie else None, "strength_state": ss, "penalty_minutes": pim,
                     "home_skaters": 5, "away_skaters": 5, "home_goalie_in": 1, "away_goalie_in": 1, "home_goalie_id": 1.0, "away_goalie_id": 2.0,
                     "home_goalie": "Sergei Bobrovsky", "away_goalie": "Spencer Knight", "home_score": hs, "away_score": as_})
    ev("FACEOFF", 1, "REGULAR", 0, "FLA")
    ev("SHOT", 1, "REGULAR", 30, "CHI", goalie=1.0)
    ev("GOAL", 1, "REGULAR", 603, "CHI", goalie=1.0, hs=0, as_=1)
    ev("PENALTY", 1, "REGULAR", 700, "FLA", pim=2.0)
    ev("GOAL", 1, "REGULAR", 848, "FLA", goalie=2.0, ss="5v4", hs=1, as_=1)
    ev("SHOT", 5, "SHOOTOUT", 3900, "FLA", goalie=2.0, hs=1, as_=1)
    ev("GOAL", 5, "SHOOTOUT", 3900, "CHI", goalie=1.0, hs=1, as_=1)
    ev("GAME_END", 5, "SHOOTOUT", 3900, None, hs=1, as_=1)
    p = tmp_path / "x.parquet"
    pd.DataFrame(rows).to_parquet(p)
    recs = load_sdv(p)
    assert len(recs) == 1
    r = recs[0]
    assert r.home == "FLA" and r.away == "CHI" and r.ended_in == "SO"
    assert (r.home_score, r.away_score) == (1, 2)          # shootout winner credited with the extra goal
    assert r.starters == {"home": 1, "away": 2}
    assert [e.type for e in r.events] == ["shot-on-goal", "goal", "penalty", "goal"]
    assert r.events[3].strength == "PP" and abs(r.events[3].minute - 848 / 60) < 1e-3
    assert r.goalie_names["1"] == "Sergei Bobrovsky"
