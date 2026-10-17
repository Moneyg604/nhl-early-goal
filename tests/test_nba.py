"""The NBA engine end to end on synthetic data: ESPN parsing, ratings, projections, the board, the page."""
from __future__ import annotations

import json
import random

import pytest

import nba.pipeline as PL
from nba.espn import parse_game, parse_pregame
from nba.model import Ratings

TEAMS = ["BOS", "DET", "NY", "PHI", "OKC", "SA"]


def _summary(eid, home, away, hs, as_, completed=True, rosters=None, lines=True, injuries=None):
    rnd = random.Random(eid)

    def comps():
        return [{"homeAway": "home", "team": {"abbreviation": home}, "score": str(hs), "linescores": [{"displayValue": str(hs // 4)}] * 4, "winner": hs > as_},
                {"homeAway": "away", "team": {"abbreviation": away}, "score": str(as_), "linescores": [{"displayValue": str(as_ // 4)}] * 4, "winner": as_ > hs}]
    keys = ["minutes", "points", "fieldGoalsMade-fieldGoalsAttempted", "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "freeThrowsMade-freeThrowsAttempted",
            "rebounds", "assists", "turnovers", "steals", "blocks", "offensiveRebounds", "defensiveRebounds", "fouls", "plusMinus"]
    players = []
    for team in (away, home):
        ath = []
        for i, (pid, name, pos, mins) in enumerate((rosters or {}).get(team, [])):
            m = max(0, rnd.gauss(mins, 3)); pts = max(0, int(m * rnd.gauss(0.6, 0.12)))
            ath.append({"athlete": {"id": pid, "displayName": name, "position": {"abbreviation": pos}}, "starter": i < 5, "didNotPlay": False,
                        "stats": [f"{int(m)}:{int((m % 1) * 60):02d}", str(pts), f"{pts // 2}-{pts}", f"{rnd.randint(0, 4)}-7", "2-3", str(rnd.randint(1, 10)), str(rnd.randint(0, 8)), "1", "1", "0", "1", "4", "2", "+3"]})
        players.append({"team": {"abbreviation": team}, "statistics": [{"keys": keys, "athletes": ath}]})
    teams = [{"team": {"abbreviation": t}, "homeAway": "away" if t == away else "home",
              "statistics": [{"name": "fieldGoalsMade-fieldGoalsAttempted", "displayValue": "40-88"}, {"name": "threePointFieldGoalsMade-threePointFieldGoalsAttempted", "displayValue": "12-35"},
                             {"name": "freeThrowsMade-freeThrowsAttempted", "displayValue": "18-22"}, {"name": "totalRebounds", "displayValue": "44"}, {"name": "offensiveRebounds", "displayValue": "10"},
                             {"name": "defensiveRebounds", "displayValue": "34"}, {"name": "assists", "displayValue": "25"}, {"name": "turnovers", "displayValue": "13"}]} for t in (away, home)]
    d = {"header": {"id": eid, "season": {"year": 2027, "type": 2}, "competitions": [{"id": eid, "date": "2026-10-20T23:30Z", "competitors": comps(), "status": {"type": {"completed": completed, "state": "post" if completed else "pre"}}}]},
         "boxscore": {"players": players, "teams": teams}, "injuries": [{"team": {"abbreviation": t}, "injuries": injuries.get(t, [])} for t in (home, away)] if injuries else []}
    if lines:
        d["pickcenter"] = [{"provider": {"name": "DraftKings"}, "details": f"{home} -4.5", "overUnder": 224.5, "spread": -4.5, "homeTeamOdds": {"moneyLine": -190, "spreadOdds": -110}, "awayTeamOdds": {"moneyLine": 160, "spreadOdds": -110}}]
    return d


def _rosters():
    return {t: [(f"{t}{i}", f"Player {t}{i}", "G" if i < 2 else "F", 34 - i * 2) for i in range(10)] for t in TEAMS}


def test_parse_game_and_pregame():
    r = _rosters()
    g = parse_game(_summary("1", "BOS", "DET", 112, 104, rosters=r))
    assert g["home"] == "BOS" and g["hs"] == 112 and g["players"]["DET"][0]["name"] == "Player DET0" and g["players"]["BOS"][0]["min"] > 0
    assert g["lines"]["spread"] == -4.5 and g["lines"]["total"] == 224.5 and abs(g["lines"]["home_ml"] - 1.526) < 0.01 and abs(g["lines"]["away_ml"] - 2.6) < 0.01
    pre = parse_pregame(_summary("2", "BOS", "DET", 0, 0, completed=False, rosters=r, injuries={"BOS": [{"status": "Out", "athlete": {"id": "BOS0", "displayName": "Player BOS0"}, "details": {"type": "Knee"}}]}))
    assert pre["injuries"]["BOS"][0]["status"] == "Out" and pre["injuries"]["BOS"][0]["injury"] == "Knee"


def _games(n_prior=60, n_cur=8):
    rnd = random.Random(3)
    r = _rosters()
    out = []
    k = 0
    for season, n in ((2026, n_prior), (2027, n_cur)):
        for i in range(n):
            h, a = rnd.sample(TEAMS, 2)
            g = parse_game(_summary(f"{season}{i}", h, a, rnd.randint(95, 130), rnd.randint(95, 130), rosters=r))
            g["date"] = (f"2025-11-{(i % 28) + 1:02d}T00:00Z" if season == 2026 else f"2026-10-{(i % 10) + 1:02d}T00:00Z")
            g["season"] = season
            out.append(g); k += 1
    return out


def test_pipeline_builds_a_day(monkeypatch, tmp_path):
    games = _games()
    r = _rosters()
    monkeypatch.setattr(PL, "load_games", lambda seasons: games)
    monkeypatch.setattr(PL, "scoreboard", lambda date: [{"id": "901", "date": "2026-10-20T23:30Z", "home": "BOS", "away": "DET", "state": "pre", "completed": False, "status": "7:30 PM", "venue": "TD Garden"},
                                                       {"id": "902", "date": "2026-10-21T01:30Z", "home": "OKC", "away": "SA", "state": "pre", "completed": False, "status": "9:30 PM"}])
    monkeypatch.setattr(PL, "summary", lambda eid, cache=True: _summary(eid, "BOS" if eid == "901" else "OKC", "DET" if eid == "901" else "SA", 0, 0, completed=False, rosters=r,
                                                                        injuries={"BOS": [{"status": "Out", "athlete": {"id": "BOS1", "displayName": "Player BOS1"}, "details": {"type": "Ankle"}}]}))
    monkeypatch.setattr(PL, "load_odds", lambda: {"updated_utc": "2026-10-20T20:00Z", "credits_remaining": 400, "games": {"DET@BOS": {"home": "BOS", "away": "DET", "props_fetched": "2026-10-20T20:00Z",
                        "props": {"pts": {"player bos0": {"name": "Player BOS0", "line": 19.5, "n": 3, "consensus_over": 0.52, "books": {"DraftKings": {"line": 19.5, "over": 1.87, "under": 1.95}, "FanDuel": {"line": 19.5, "over": 1.9, "under": 1.9}}}}}}}})
    import nba.desk as ND
    monkeypatch.setattr(ND, "RESEARCH_DIR", tmp_path)
    p = PL.build_day("2026-10-20")
    assert len(p["games"]) == 2
    g = p["games"][0]
    assert g["lines"]["spread"] == -4.5 and g["model"]["home_win"] > 0 and g["markets"]["spread"]["line"] == -4.5
    ids = [b["id"] for b in p["best_bets"]["ranked"]]
    assert "ml|2026_10_20_DET_BOS|home||BOS" in ids and "spread|2026_10_20_DET_BOS|away|4.5|DET" in ids and "total|2026_10_20_DET_BOS|over|224.5|" in ids
    props = [b for b in p["best_bets"]["ranked"] if b["kind"] == "pts"]
    assert props and props[0]["who"] == "Player BOS0" and props[0]["pid"] == "BOS0" and props[0]["books"] == 3
    # the injured starter is not projected
    names = [x["name"] for x in g["props"]["home"]]
    assert "Player BOS1" not in names and "Player BOS0" in names
    assert p["bot"]["cats"]["points"]["ids"] and p["picks"]["bot"]
    assert p["bot"]["desk"] is None and p["bot"]["desk_config"]["odds_band"] == [1.35, 2.2]
    # the page renders and its script parses
    from nba.report import render
    html = render(p)
    assert "Research desk" in html and p["games"][0]["home"] in html
    import subprocess, tempfile, os
    i = html.rindex("<script>"); j = html.rindex("</script>")
    f = tmp_path / "main.js"; f.write_text(html[i + 8:j])
    node = subprocess.run(["node", "--check", str(f)], capture_output=True, text=True)
    if node.returncode != 0 and "No such file" not in node.stderr:
        pytest.fail(node.stderr[:800])


def test_scorecard_grades_nba_picks():
    from nba.scorecard import grade
    g = {"hs": 110, "as": 100, "home": "BOS", "away": "DET", "players": {"BOS": [{"id": "BOS0", "name": "Player BOS0", "pts": 25, "reb": 5, "ast": 7, "tpm": 3, "dnp": False}]}}
    assert grade({"market": "ml", "side": "home"}, g) == "won"
    assert grade({"market": "spread", "side": "home", "line": -12.5}, g) == "lost"
    assert grade({"market": "spread", "side": "away", "line": -12.5}, g) == "won"
    assert grade({"market": "total", "side": "under", "line": 210.5}, g) == "won"
    assert grade({"market": "pts", "side": "over", "line": 24.5, "team": "BOS", "id": "BOS0"}, g) == "won"
    assert grade({"market": "pra", "side": "under", "line": 36.5, "team": "BOS", "player": "Player BOS0"}, g) == "lost"
    assert grade({"market": "ast", "side": "over", "line": 7, "team": "BOS", "id": "BOS0"}, g) == "push"
