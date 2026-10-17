"""The research-desk overlay: validation, merge into the payload, scorecard picks."""
from __future__ import annotations

import copy

from nfl.desk import merge, validate

SRC = [{"name": "test", "url": "https://example.com", "fetched": "2026-10-17T17:00Z"}]


def _payload():
    g1 = {"game_id": "2026_06_NYJ_NE", "home": "NE", "away": "NYJ", "kickoff_utc": "2026-10-18T17:00Z",
          "props": {"away": [], "home": []}, "anytime": {"away": [{"name": "Breece Hall", "id": "00-1"}], "home": []},
          "odds": {"fetched": "2026-10-15T04:00Z", "props_fetched": "2026-10-15T04:00Z",
                   "ml": {"books": {"DraftKings": {"home": 1.3, "away": 3.6}}},
                   "props": {"qb_td": {"g.smith": {"name": "Geno Smith", "line": 1.5, "books": {"DraftKings": {"line": 1.5, "over": 2.5, "under": 1.43}}}}}}}
    g2 = {"game_id": "2026_06_BAL_CLE", "home": "CLE", "away": "BAL", "kickoff_utc": "2026-10-18T17:00Z",
          "props": {"away": [{"name": "Derrick Henry", "id": "00-2"}], "home": []}, "anytime": {"away": [], "home": []},
          "odds": {"fetched": "2026-10-15T04:00Z", "ml": {"books": {"DraftKings": {"home": 3.1, "away": 1.39}}},
                   "spread": {"books": {"DraftKings": {"line": 5.5, "home": 1.87, "away": 1.95}}},
                   "opening": {"spread": {"books": {"DraftKings": {"line": 4.5}}}, "ml": {"consensus_home": 0.33}}}}
    board = [{"id": "qb_td|2026_06_NYJ_NE|under|1.5|Geno Smith", "game_id": "2026_06_NYJ_NE", "kind": "qb_td", "side": "under", "line": 1.5,
              "who": "Geno Smith", "team": "NYJ", "label": "Geno Smith under 1.5 pass TDs", "odds": 1.43, "p": 0.67, "p_model": 0.68, "p_market": 0.66,
              "ev": -0.04, "fair_odds": 1.49, "judge": {"score": 0.7}},
             {"id": "spread|2026_06_BAL_CLE|home|5.5|CLE", "game_id": "2026_06_BAL_CLE", "kind": "spread", "side": "home", "line": 5.5, "team": "CLE",
              "label": "CLE +5.5", "odds": 1.87, "p": 0.53, "p_model": 0.5, "p_market": 0.53, "ev": -0.01, "fair_odds": 1.89, "judge": {"score": 0.6}}]
    return {"season": 2026, "week": 6, "games": [g1, g2], "best_bets": {"ranked": board}, "bot": {"extra": []}, "picks": {}}


def _sel(**kw):
    base = {"id": "qb_td|2026_06_NYJ_NE|under|1.5|Geno Smith", "game_id": "2026_06_NYJ_NE", "kind": "qb_td", "side": "under", "line": 1.5,
            "who": "Geno Smith", "team": "NYJ", "label": "Geno Smith under 1.5 pass TDs", "odds": 1.43, "odds_source": "feed", "p": 0.64, "grade": "B",
            "evidence": "measured", "confidence": 70, "inputs": ["i"], "arithmetic": ["a"], "pros": ["p"], "risks": ["r"], "verdict": "v", "sources": SRC}
    base.update(kw)
    return base


def _overlay(*sels):
    return {"v": 1, "season": 2026, "week": 6, "generated_utc": "2026-10-17 17:30 UTC", "analyst": "desk", "odds_band": [1.35, 2.2],
            "games": {"2026_06_NYJ_NE": {"notes": ["n"], "sources": SRC}}, "selections": list(sels)}


def test_valid_overlay_merges_and_ranks():
    p = _payload()
    ov = _overlay(_sel(), _sel(id="spread|2026_06_BAL_CLE|home|5.5|CLE", game_id="2026_06_BAL_CLE", kind="spread", side="home", line=5.5, who=None, team="CLE",
                         label="CLE +5.5", odds=1.87, p=0.56, grade="C", evidence="partial", confidence=55),
                 _sel(id="desk|rush_yds|2026_06_BAL_CLE|over|74.5|Derrick Henry", game_id="2026_06_BAL_CLE", kind="rush_yds", side="over", line=74.5,
                      who="Derrick Henry", team="BAL", label="Derrick Henry over 74.5 rush yds", odds=1.87, odds_source="draftkings", p=0.7))
    assert validate(ov, p) == []
    desk = merge(p, ov)
    assert desk["ok"] and desk["n"] == 3
    assert [x["label"] for x in desk["selections"]][0] == "Derrick Henry over 74.5 rush yds"      # highest desk chance first
    henry = desk["selections"][0]
    assert henry["pid"] == "00-2" and henry["tside"] == "away" and "board" not in henry
    geno = next(x for x in desk["selections"] if x["who"] == "Geno Smith")
    assert geno["board"]["p"] == 0.67 and geno["board"]["judge"] == 0.7
    # the board bet now carries the desk's view for its card
    b = p["best_bets"]["ranked"][0]
    assert b["desk"]["p"] == 0.64 and b["desk"]["grade"] == "B"
    # scorecard picks: spread line in home-margin terms, player ids for props
    picks = {x["label"]: x for x in p["picks"]["desk"]}
    assert picks["CLE +5.5"]["line"] == -5.5 and picks["CLE +5.5"]["market"] == "spread"
    assert picks["Derrick Henry over 74.5 rush yds"]["id"] == "00-2" and picks["Derrick Henry over 74.5 rush yds"]["player"] == "Derrick Henry"
    assert picks["Geno Smith under 1.5 pass TDs"]["qb"] == "Geno Smith"


def test_rejects_bad_selections():
    p = _payload()
    assert any("outside the band" in e for e in validate(_overlay(_sel(odds=2.5)), p))
    assert any("cannot be grade A" in e for e in validate(_overlay(_sel(grade="A", evidence="unmeasured")), p))
    assert any("not on the board" in e for e in validate(_overlay(_sel(id="qb_td|2026_06_NYJ_NE|under|2.5|Geno Smith", line=2.5)), p))
    assert any("differs from the board" in e for e in validate(_overlay(_sel(line=2.5)), p))
    assert any("missing" in e for e in validate(_overlay({k: v for k, v in _sel().items() if k != "risks"}), p))
    assert any("not in week" in e for e in validate(_overlay(_sel(game_id="2026_06_XX_YY")), p))
    assert any("sources" in e for e in validate(_overlay(_sel(sources=[])), p))
    assert any("duplicate" in e for e in validate(_overlay(_sel(), _sel()), p))


def test_invalid_overlay_is_reported_not_merged():
    p = _payload()
    desk = merge(p, _overlay(_sel(odds=9.0)))
    assert desk["ok"] is False and desk["errors"]
    assert "desk" not in p["picks"]
    assert "desk" not in p["best_bets"]["ranked"][0]


def test_missing_overlay_leaves_payload_alone(tmp_path, monkeypatch):
    import nfl.desk as D
    monkeypatch.setattr(D, "RESEARCH_DIR", tmp_path)
    p = _payload()
    q = copy.deepcopy(p)
    assert merge(p, None) is None and p["bot"]["desk"] is None
    assert "desk" not in p["picks"] and p["picks"]["market"][0]["team"] == "NE"     # leaderboard baselines still built


def test_feed_source_must_match_the_feed_and_alerts_fire():
    p = _payload()
    bad = validate(_overlay(_sel(odds=1.6)), p)
    assert any("DraftKings' price in the feed is 1.43" in e for e in bad)
    ov = _overlay(_sel(), _sel(id="spread|2026_06_BAL_CLE|home|5.5|CLE", game_id="2026_06_BAL_CLE", kind="spread", side="home", line=5.5, who=None, team="CLE",
                             label="CLE +5.5", odds=1.87, p=0.56, grade="C", evidence="partial", confidence=55))
    assert validate(ov, p) == []
    desk = merge(p, ov)
    cle = next(x for x in desk["selections"] if x["label"] == "CLE +5.5")
    assert cle["now"] == {"line": 5.5, "odds": 1.87, "fetched": "2026-10-15T04:00Z"} and cle["alert"] is None
    # the opener was CLE +4.5, now +5.5: the market moved toward BAL, so BAL is hot and CLE is cold
    hot = p["bot"]["hot"]
    assert hot["movers"][0]["hot"] == "BAL" and hot["movers"][0]["cold"] == "CLE" and hot["movers"][0]["move"] == 1.0
    # a price drop of 0.08 or more is an alert
    ov2 = _overlay(_sel(id="desk|ml|2026_06_BAL_CLE|away||BAL", game_id="2026_06_BAL_CLE", kind="ml", side="away", line=None, who=None, team="BAL",
                        label="BAL moneyline", odds=1.5, odds_source="draftkings", p=0.72))
    desk2 = merge(_payload(), ov2)
    assert desk2["alerts"] and desk2["alerts"][0]["severity"] == "price"
