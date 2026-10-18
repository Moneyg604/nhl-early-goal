"""The research-desk overlay: validation (strict before a commit, lenient at build time), the merge into the payload,
the owner's spec (markets, DraftKings' lines only, sections, Best picks), the scorecard picks, assemble_desk."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

from nfl.desk import merge, notes, validate

ROOT = Path(__file__).resolve().parents[1]
LIVE_SPEC = ROOT / "data" / "nfl" / "desk_config.json"
KICK = "2099-10-18T17:00Z"            # far in the future: these games never count as started
PAST = "2020-10-18T17:00Z"


@pytest.fixture(autouse=True)
def _defaults(monkeypatch, tmp_path):
    """Tests run on the module's default spec (band rule, every market on) unless they load the live spec."""
    import nfl.desk as D
    monkeypatch.setattr(D, "CONFIG_PATH", tmp_path / "none.json")
    monkeypatch.setattr(D, "RESEARCH_DIR", tmp_path / "research")


@pytest.fixture()
def live_spec(monkeypatch):
    """The owner's live spec (data/nfl/desk_config.json): sections, Best picks, no pass TDs, DraftKings' lines only."""
    import nfl.desk as D
    monkeypatch.setattr(D, "CONFIG_PATH", LIVE_SPEC)
    return json.loads(LIVE_SPEC.read_text())


SRC = [{"name": "test", "url": "https://example.com", "fetched": "2026-10-17T17:00Z"}]


def _payload(fetched="2026-10-15T04:00Z", kick=KICK):
    g1 = {"game_id": "2026_06_NYJ_NE", "home": "NE", "away": "NYJ", "kickoff_utc": kick,
          "props": {"away": [{"name": "Garrett Wilson", "id": "00-3"}], "home": []}, "anytime": {"away": [{"name": "Breece Hall", "id": "00-1"}], "home": []},
          "odds": {"fetched": fetched, "props_fetched": fetched,
                   "ml": {"books": {"DraftKings": {"home": 1.3, "away": 3.6}}},
                   "props": {"qb_td": {"g.smith": {"name": "Geno Smith", "line": 1.5, "books": {"DraftKings": {"line": 1.5, "over": 2.5, "under": 1.43}}}},
                             "qb_yds": {"g.smith": {"name": "Geno Smith", "line": 219.5, "books": {"DraftKings": {"line": 219.5, "over": 1.87, "under": 1.93}}}}}}}
    g2 = {"game_id": "2026_06_BAL_CLE", "home": "CLE", "away": "BAL", "kickoff_utc": kick,
          "props": {"away": [{"name": "Derrick Henry", "id": "00-2"}], "home": []}, "anytime": {"away": [], "home": []},
          "odds": {"fetched": fetched, "ml": {"books": {"DraftKings": {"home": 3.1, "away": 1.39}}},
                   "spread": {"books": {"DraftKings": {"line": 5.5, "home": 1.87, "away": 1.95}}},
                   "total": {"books": {"DraftKings": {"line": 41.5, "over": 1.91, "under": 1.91}}},
                   "opening": {"spread": {"books": {"DraftKings": {"line": 4.5}}}, "ml": {"consensus_home": 0.33}}}}
    board = [{"id": "qb_td|2026_06_NYJ_NE|under|1.5|Geno Smith", "game_id": "2026_06_NYJ_NE", "kind": "qb_td", "side": "under", "line": 1.5,
              "who": "Geno Smith", "team": "NYJ", "label": "Geno Smith under 1.5 pass TDs", "odds": 1.43, "p": 0.67, "p_model": 0.68, "p_market": 0.66,
              "ev": -0.04, "fair_odds": 1.49, "judge": {"score": 0.7}},
             {"id": "qb_yds|2026_06_NYJ_NE|over|219.5|Geno Smith", "game_id": "2026_06_NYJ_NE", "kind": "qb_yds", "side": "over", "line": 219.5,
              "who": "Geno Smith", "team": "NYJ", "label": "Geno Smith over 219.5 pass yds", "odds": 1.87, "p": 0.55, "p_model": 0.57, "p_market": 0.52,
              "ev": 0.02, "fair_odds": 1.82, "judge": {"score": 0.6}},
             {"id": "spread|2026_06_BAL_CLE|home|5.5|CLE", "game_id": "2026_06_BAL_CLE", "kind": "spread", "side": "home", "line": 5.5, "team": "CLE",
              "label": "CLE +5.5", "odds": 1.87, "p": 0.53, "p_model": 0.5, "p_market": 0.53, "ev": -0.01, "fair_odds": 1.89, "judge": {"score": 0.6}}]
    return {"sport": "nfl", "season": 2026, "week": 6, "games": [g1, g2], "best_bets": {"ranked": board, "locked": []}, "bot": {"extra": []}, "picks": {}}


def _sel(**kw):
    base = {"id": "qb_td|2026_06_NYJ_NE|under|1.5|Geno Smith", "game_id": "2026_06_NYJ_NE", "kind": "qb_td", "side": "under", "line": 1.5,
            "who": "Geno Smith", "team": "NYJ", "label": "Geno Smith under 1.5 pass TDs", "odds": 1.43, "odds_source": "feed", "p": 0.64, "grade": "B",
            "evidence": "measured", "confidence": 70, "inputs": ["i"], "arithmetic": ["a"], "pros": ["p"], "risks": ["r"], "verdict": "v", "sources": SRC}
    base.update(kw)
    return base


def _qbyds(**kw):
    return _sel(**{"id": "qb_yds|2026_06_NYJ_NE|over|219.5|Geno Smith", "kind": "qb_yds", "side": "over", "line": 219.5, "label": "Geno Smith over 219.5 pass yds",
                   "odds": 1.87, "p": 0.6, **kw})


def _henry(**kw):
    return _sel(**{"id": "desk|rush_yds|2026_06_BAL_CLE|over|74.5|Derrick Henry", "game_id": "2026_06_BAL_CLE", "kind": "rush_yds", "side": "over", "line": 74.5,
                   "who": "Derrick Henry", "team": "BAL", "label": "Derrick Henry over 74.5 rush yds", "odds": 1.87, "odds_source": "draftkings", "p": 0.7, **kw})


def _cle(**kw):
    return _sel(**{"id": "spread|2026_06_BAL_CLE|home|5.5|CLE", "game_id": "2026_06_BAL_CLE", "kind": "spread", "side": "home", "line": 5.5, "who": None, "team": "CLE",
                   "label": "CLE +5.5", "odds": 1.87, "p": 0.56, "grade": "C", "evidence": "partial", "confidence": 55, **kw})


def _overlay(*sels, **kw):
    d = {"v": 1, "season": 2026, "week": 6, "generated_utc": "2026-10-17 17:30 UTC", "analyst": "desk", "odds_band": [1.35, 2.2],
         "games": {"2026_06_NYJ_NE": {"notes": ["n"], "sources": SRC}}, "selections": list(sels)}
    d.update(kw)
    return d


def test_valid_overlay_merges_and_ranks():
    p = _payload()
    ov = _overlay(_sel(), _cle(), _henry())
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
    # Best picks, in order, are graded on their own line
    assert [x["label"] for x in p["picks"]["desk_best"]] == [next(s["label"] for s in desk["selections"] if s["id"] == i) for i in desk["best"]]
    assert p["picks"]["desk_best"][0]["rank"] == 1


def test_rejects_bad_selections():
    p = _payload()
    assert any("outside the band" in e for e in validate(_overlay(_sel(odds=2.5)), p))
    assert any("cannot be grade A" in e for e in validate(_overlay(_sel(grade="A", evidence="unmeasured")), p))
    assert any("not on the board" in e for e in validate(_overlay(_sel(id="qb_td|2026_06_NYJ_NE|under|2.5|Geno Smith", line=2.5)), p))
    assert any("differs from the board" in e for e in validate(_overlay(_sel(line=2.5)), p))
    assert any("missing" in e for e in validate(_overlay({k: v for k, v in _sel().items() if k != "risks"}), p))
    assert any("is not in 6" in e for e in validate(_overlay(_sel(game_id="2026_06_XX_YY")), p))
    assert any("sources" in e for e in validate(_overlay(_sel(sources=[])), p))
    assert any("duplicate" in e for e in validate(_overlay(_sel(), _sel()), p))
    # the id must say what the selection says
    assert any("the id says side" in e for e in validate(_overlay(_henry(side="under")), p))


def test_structural_error_is_reported_not_merged():
    p = _payload()
    desk = merge(p, _overlay(_sel(p=1.5)))
    assert desk["ok"] is False and desk["errors"]
    assert "desk" not in p["picks"] and "desk_best" not in p["picks"]
    assert "desk" not in p["best_bets"]["ranked"][0]
    # a broken file never crashes the build
    desk = merge(_payload(), _overlay(_sel(), games=None))
    assert desk["ok"] is False


def test_missing_overlay_leaves_payload_alone():
    p = _payload()
    assert merge(p, None) is None and p["bot"]["desk"] is None
    assert "desk" not in p["picks"] and p["picks"]["market"][0]["team"] == "NE"     # leaderboard baselines still built


def test_unreadable_research_file_is_reported(tmp_path, monkeypatch):
    import nfl.desk as D
    D.RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    (D.RESEARCH_DIR / "2026-w06.json").write_text("{ not json")
    p = _payload()
    desk = merge(p)
    assert desk["ok"] is False and "not valid JSON" in desk["errors"][0]


def test_feed_is_checked_before_the_commit_and_moves_become_alerts_after():
    p = _payload()
    # before the commit: a 'feed' price must match the feed
    assert any("DraftKings' price in the feed is 1.43" in e for e in validate(_overlay(_sel(odds=1.6)), p))
    ov = _overlay(_sel(), _cle())
    assert validate(ov, p) == []
    desk = merge(p, ov)
    cle = next(x for x in desk["selections"] if x["label"] == "CLE +5.5")
    assert cle["now"] == {"line": 5.5, "odds": 1.87, "fetched": "2026-10-15T04:00Z"} and cle["alert"] is None
    # the opener was CLE +4.5, now +5.5: the market moved toward BAL, so BAL is hot and CLE is cold
    hot = p["bot"]["hot"]
    assert hot["movers"][0]["hot"] == "BAL" and hot["movers"][0]["cold"] == "CLE" and hot["movers"][0]["move"] == 1.0
    # after the commit, a newer feed with a worse price is an alert on the pick, never an error
    ov2 = _overlay(_sel(id="desk|ml|2026_06_BAL_CLE|away||BAL", game_id="2026_06_BAL_CLE", kind="ml", side="away", line=None, who=None, team="BAL",
                        label="BAL moneyline", odds=1.5, odds_source="draftkings", p=0.72))
    desk2 = merge(_payload(fetched="2026-10-18T12:00Z"), ov2)
    assert desk2["ok"] and desk2["alerts"] and desk2["alerts"][0]["severity"] == "price" and desk2["alerts"][0]["game_id"] == "2026_06_BAL_CLE"
    # a feed older than the desk's run says nothing about a move since the desk priced it
    assert merge(_payload(fetched="2026-10-15T04:00Z"), ov2)["alerts"] == []
    # a 'feed' pick whose DraftKings line moved after the commit keeps showing, with a line alert
    moved = _payload(fetched="2026-10-18T12:00Z")
    moved["games"][1]["odds"]["spread"]["books"]["DraftKings"] = {"line": 6.5, "home": 1.87, "away": 1.95}
    bal = _sel(id="desk|spread|2026_06_BAL_CLE|away|-5.5|BAL", game_id="2026_06_BAL_CLE", kind="spread", side="away", line=-5.5, who=None, team="BAL",
               label="BAL -5.5", odds=1.95, p=0.55)
    assert validate(_overlay(bal), moved)                         # strict: the feed now says -6.5
    desk3 = merge(moved, _overlay(bal))
    assert desk3["ok"] and desk3["alerts"][0]["severity"] == "line"


def test_started_game_keeps_its_desk_picks():
    """After kickoff the board drops a game's bets; a board-id pick must keep showing and keep being graded."""
    p = _payload(kick=PAST)
    p["best_bets"]["ranked"] = []                                   # the board no longer lists started games
    ov = _overlay(_sel(), _cle())
    assert validate(ov, p) == []                                    # no 'not on the board', no feed check after kickoff
    desk = merge(p, ov)
    assert desk["ok"] and desk["n"] == 2 and len(p["picks"]["desk"]) == 2
    assert all(x["alert"] is None for x in desk["selections"])


def test_live_spec_sets_aside_markets_it_switched_off(live_spec):
    p = _payload()
    td = _sel()                                                     # an under 1.5 passing TDs: the spec switched the market off
    errs = validate(_overlay(td, _qbyds(), _henry()), p)
    assert any("Passing touchdowns is switched off" in e for e in errs)
    desk = merge(p, _overlay(td, _qbyds(), _henry()))
    assert desk["ok"]                                                # the page never goes blank over it
    assert td["id"] not in {x["id"] for x in desk["selections"]}
    assert [x["id"] for x in desk["excluded"]] == [td["id"]]
    assert td["id"] not in {x.get("qb") and x["label"] for x in p["picks"]["desk"]}
    assert all(x["market"] != "qb_td" for x in p["picks"]["desk"])
    assert desk["odds_rule"] == "ignore"


def test_live_spec_prices_are_not_a_filter_but_draftkings_lines_are(live_spec):
    p = _payload()
    # odds_rule 'ignore': a short price is fine when the evidence supports it
    short = _henry(odds=1.22, p=0.78)
    assert validate(_overlay(short), p) == []
    # lines 'draftkings': an unverified price is not a pick
    assert any("DraftKings' posted lines only" in e for e in validate(_overlay(_henry(odds_source="unverified")), p))
    # and in a file already committed it can show, but never as a Best pick
    desk = merge(p, _overlay(_henry(odds_source="unverified"), _qbyds()))
    assert _henry()["id"] not in desk["best"] and desk["best"] == [_qbyds()["id"]]


def test_live_spec_sections_and_best_picks(live_spec):
    p = _payload()
    ov = _overlay(_qbyds(), _henry(), _cle())
    assert validate(ov, p) == []
    desk = merge(p, ov)
    assert desk["sections"]["qb"] == [_qbyds()["id"]] and desk["sections"]["rushing"] == [_henry()["id"]] and desk["sections"]["game"] == [_cle()["id"]]
    assert desk["sections"]["receiving"] == []
    # Best picks: measured evidence first, then the desk's chance; at most two per game (BAL @ CLE gives two)
    assert desk["best"] == [_henry()["id"], _qbyds()["id"], _cle()["id"]]
    assert any("receiving" in n.lower() for n in notes(ov, p))       # a section short of its minimum is a note, not an error
    # an explicit Best list must follow the spec: one per player, at most two per game, drawn from the sections
    two_geno = _overlay(_qbyds(), _henry(), _cle(), best=[_qbyds()["id"], _qbyds()["id"]])
    assert any("listed twice" in e for e in validate(two_geno, p))
    three = _overlay(_henry(), _cle(), _sel(id="desk|total|2026_06_BAL_CLE|under|41.5|", game_id="2026_06_BAL_CLE", kind="total", side="under", line=41.5,
                                             who=None, team=None, label="Under 41.5", odds=1.91, odds_source="draftkings", p=0.58),
                     best=[_henry()["id"], _cle()["id"], "desk|total|2026_06_BAL_CLE|under|41.5|"])
    errs = validate(three, p)
    assert any("at most two per game" in e for e in errs)
    assert any("a second total pick" in e or "section allows" in e or "at most 3 per game" in e or "two per game" in e for e in errs)


def test_live_spec_wild_cards_off(live_spec):
    p = _payload()
    w = _henry(id="desk|rush_yds|2026_06_BAL_CLE|over|99.5|Derrick Henry", line=99.5, odds=2.6, p=0.4, label="Derrick Henry over 99.5 rush yds")
    ov = _overlay(_qbyds(), wild_cards=[w])
    assert any("wild cards switched off" in e for e in validate(ov, p))
    desk = merge(p, ov)
    assert desk["ok"] and desk["wild_cards"] == [] and p["picks"]["desk_wild"] == []


def test_broken_spec_is_reported(tmp_path, monkeypatch):
    import nfl.desk as D
    bad = tmp_path / "desk_config.json"
    bad.write_text('{"odds_rule": "ignore",')
    monkeypatch.setattr(D, "CONFIG_PATH", bad)
    cfg = D.load_config()
    assert "not valid JSON" in cfg["_error"]
    assert any("not valid JSON" in e for e in validate(_overlay(_qbyds()), _payload()))


def test_spec_markets_list_is_the_whole_list(tmp_path, monkeypatch):
    import nfl.desk as D
    f = tmp_path / "desk_config.json"
    f.write_text(json.dumps({"markets": {"qb_yds": True}}))
    monkeypatch.setattr(D, "CONFIG_PATH", f)
    cfg = D.load_config()
    assert cfg["markets"] == {"qb_yds": True}
    assert D.spec_block({"kind": "rush_yds", "id": "x"}, cfg)                 # a market the file leaves out is off


def test_nba_spread_picks_are_graded_on_the_right_side(tmp_path, monkeypatch):
    import nba.desk as N
    from nba.scorecard import grade
    monkeypatch.setattr(N, "CONFIG_PATH", tmp_path / "none.json")
    monkeypatch.setattr(N, "RESEARCH_DIR", tmp_path)
    g = {"game_id": "2026_10_20_DET_BOS", "home": "BOS", "away": "DET", "tip_utc": KICK, "props": {}, "odds": {}}
    p = {"sport": "nba", "date": "2026-10-20", "season": 2027, "games": [g], "best_bets": {"ranked": []}, "bot": {}, "picks": {}}
    bos = _sel(id="desk|spread|2026_10_20_DET_BOS|home|-4.5|BOS", game_id="2026_10_20_DET_BOS", kind="spread", side="home", line=-4.5, who=None, team="BOS",
               label="BOS -4.5", odds=1.91, odds_source="draftkings", p=0.6)
    det = _sel(id="desk|spread|2026_10_20_DET_BOS|away|4.5|DET", game_id="2026_10_20_DET_BOS", kind="spread", side="away", line=4.5, who=None, team="DET",
               label="DET +4.5", odds=1.91, odds_source="draftkings", p=0.55)
    ov = {"v": 1, "season": 2027, "date": "2026-10-20", "generated_utc": "2026-10-20 18:00 UTC", "analyst": "desk", "odds_band": [1.35, 2.2], "games": {},
          "selections": [bos, det]}
    desk = N.merge(p, ov)
    assert desk["ok"], desk
    picks = {x["label"]: x for x in p["picks"]["desk"]}
    final = {"hs": 102, "as": 100}                                         # BOS by 2: BOS -4.5 loses, DET +4.5 wins
    assert grade(picks["BOS -4.5"], final) == "lost"
    assert grade(picks["DET +4.5"], final) == "won"


def _run_assemble(argv):
    sys.path.insert(0, str(ROOT / "tools"))
    import importlib
    import assemble_desk as A
    importlib.reload(A)
    return A.main(argv)


def test_assemble_keeps_started_games_and_their_best_places(tmp_path, monkeypatch, capsys):
    import nfl.desk as D
    monkeypatch.setattr(D, "RESEARCH_DIR", tmp_path / "research")
    p = _payload()
    p["games"][1]["kickoff_utc"] = PAST                              # BAL @ CLE has kicked off
    pf = tmp_path / "payload.json"
    pf.write_text(json.dumps(p))
    old = _overlay(_henry(), _qbyds(), best=[_henry()["id"]])
    keep = tmp_path / "old.json"
    keep.write_text(json.dumps(old))
    frags = tmp_path / "frags"
    frags.mkdir()
    # a fragment for the started game is ignored; one for the game still to play is used (notes as a plain list)
    (frags / "2026_06_BAL_CLE.json").write_text(json.dumps({"game_id": "2026_06_BAL_CLE", "selections": [_cle()]}))
    (frags / "2026_06_NYJ_NE.json").write_text(json.dumps({"game_id": "2026_06_NYJ_NE", "notes": ["Wilson is a full go"],
                                                           "selections": [_qbyds(p=0.62)], "declined": [{"label": "x", "why": "y"}]}))
    rc = _run_assemble(["--season", "2026", "--week", "6", "--frags", str(frags), "--keep", str(keep), "--payload", str(pf), "--summary", "s"])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "has kicked off" in out
    d = json.loads((tmp_path / "research" / "2026-w06.json").read_text())
    ids = [s["id"] for s in d["selections"]]
    assert _henry()["id"] in ids and _cle()["id"] not in ids          # the started pick stays exactly as it was
    assert d["best"][0] == _henry()["id"]                             # and keeps its Best-pick place
    assert d["games"]["2026_06_NYJ_NE"]["notes"] == ["Wilson is a full go"]


def test_assemble_refuses_an_invalid_result(tmp_path, monkeypatch, capsys, live_spec):
    import nfl.desk as D
    monkeypatch.setattr(D, "RESEARCH_DIR", tmp_path / "research")
    pf = tmp_path / "payload.json"
    pf.write_text(json.dumps(_payload()))
    frags = tmp_path / "frags"
    frags.mkdir()
    (frags / "a.json").write_text(json.dumps({"game_id": "2026_06_NYJ_NE", "selections": [_sel()]}))     # a pass-TD pick: off in the spec
    rc = _run_assemble(["--season", "2026", "--week", "6", "--frags", str(frags), "--payload", str(pf)])
    out = capsys.readouterr().out
    assert rc == 1 and "switched off" in out
    assert not (tmp_path / "research" / "2026-w06.json").exists() and (frags / "_assembled_invalid.json").exists()


def test_live_overlay_still_merges_under_the_live_spec(live_spec):
    """The committed week-6 file was written before the spec changed: it must keep showing, with the banned picks set aside."""
    ov = json.loads((ROOT / "data" / "nfl" / "research" / "2026-w06.json").read_text())
    pf = ROOT / "docs" / "nfl" / "weeks" / "2026-w06.json"
    if not pf.exists():
        pytest.skip("no published week-6 payload")
    p = copy.deepcopy(json.loads(pf.read_text()))
    desk = merge(p, ov)
    assert desk["ok"], desk.get("errors")
    assert all(x["kind"] != "qb_td" for x in desk["selections"])
    if any(s.get("kind") == "qb_td" for s in ov.get("selections") or []):
        assert {x["kind"] for x in desk["excluded"]} >= {"qb_td"}       # the file as first written carried TD-pass picks; later desk runs may have moved them to declined already
    assert 3 <= len(desk["best"]) <= 6
    by = {x["id"]: x for x in desk["selections"]}
    assert all(by[i]["odds_source"] != "unverified" for i in desk["best"])


def test_assemble_declines_carried_picks_the_spec_no_longer_allows(tmp_path, monkeypatch, capsys, live_spec):
    """Tonight's case: the week file holds a pass-TD pick for a game this run does not cover (Monday night)."""
    import nfl.desk as D
    monkeypatch.setattr(D, "RESEARCH_DIR", tmp_path / "research")
    pf = tmp_path / "payload.json"
    pf.write_text(json.dumps(_payload()))
    keep = tmp_path / "old.json"
    keep.write_text(json.dumps(_overlay(_sel(), _henry())))        # NYJ @ NE pass-TD pick (now off) + BAL @ CLE rush pick
    frags = tmp_path / "frags"
    frags.mkdir()
    (frags / "b.json").write_text(json.dumps({"game_id": "2026_06_BAL_CLE", "selections": [_henry(p=0.71)]}))
    rc = _run_assemble(["--season", "2026", "--week", "6", "--frags", str(frags), "--keep", str(keep), "--payload", str(pf)])
    out = capsys.readouterr().out
    assert rc == 0, out
    d = json.loads((tmp_path / "research" / "2026-w06.json").read_text())
    assert [s["id"] for s in d["selections"]] == [_henry()["id"]]
    assert any(x["id"] == _sel()["id"] and "switched off" in x["why"] for x in d["declined"])


def test_assemble_a_fragment_replaces_its_games_earlier_picks(tmp_path, monkeypatch, capsys):
    import nfl.desk as D
    monkeypatch.setattr(D, "RESEARCH_DIR", tmp_path / "research")
    pf = tmp_path / "payload.json"
    pf.write_text(json.dumps(_payload()))
    keep = tmp_path / "old.json"
    keep.write_text(json.dumps(_overlay(_qbyds(), _henry())))
    frags = tmp_path / "frags"
    frags.mkdir()
    # a final-news fragment for BAL @ CLE that drops Henry (no notes text, no picks) and nothing for NYJ @ NE
    (frags / "b.json").write_text(json.dumps({"game_id": "2026_06_BAL_CLE", "notes": {"sources": SRC}, "selections": [],
                                              "declined": [{"id": _henry()["id"], "label": "Derrick Henry over 74.5 rush yds", "why": "ruled out Sunday"}]}))
    rc = _run_assemble(["--season", "2026", "--week", "6", "--frags", str(frags), "--keep", str(keep), "--payload", str(pf)])
    out = capsys.readouterr().out
    assert rc == 0, out
    d = json.loads((tmp_path / "research" / "2026-w06.json").read_text())
    ids = [s["id"] for s in d["selections"]]
    assert _henry()["id"] not in ids and _qbyds()["id"] in ids          # dropped stays dropped; the uncovered game keeps its pick
    assert _henry()["id"] not in d["best"]


def test_a_spec_change_never_rewrites_the_graded_record(live_spec, tmp_path, monkeypatch):
    """A pick shown at kickoff stays shown and graded after the owner switches its market off; one set aside stays set aside."""
    import nfl.desk as D
    p = _payload()
    ov = _overlay(_qbyds(), _henry(), _sel())                       # the pass-TD pick is set aside by the live spec
    first = merge(p, ov)
    assert [x["id"] for x in first["excluded"]] == [_sel()["id"]]
    prev = copy.deepcopy(p)
    # the games kick off; then the owner switches rushing yards off and passing TDs on (without a section, so still blocked)
    spec = json.loads(LIVE_SPEC.read_text())
    spec["markets"]["rush_yds"] = False
    f = tmp_path / "spec.json"
    f.write_text(json.dumps(spec))
    monkeypatch.setattr(D, "CONFIG_PATH", f)
    later = _payload(kick=PAST)
    desk = merge(later, ov, prev)
    shown = {x["id"] for x in desk["selections"]}
    assert _henry()["id"] in shown and _qbyds()["id"] in shown        # still shown, still graded
    assert _sel()["id"] not in shown                                   # still set aside
    assert {x["label"] for x in later["picks"]["desk_best"]} == {x["label"] for x in prev["picks"]["desk_best"]}


def test_strict_check_lists_explicit_sections_and_started_caps(live_spec):
    p = _payload()
    # explicit lists that leave a pick still to play out of every list
    ov = _overlay(_qbyds(), _henry(), sections={"qb": [_qbyds()["id"]]})
    assert any("in no section list" in e for e in validate(ov, p))
    # an unverified price is never a Best pick, whatever the spec
    assert any("unverified price" in e for e in validate(_overlay(_henry(odds_source="unverified"), best=[_henry()["id"]]), p))


def test_assemble_declines_a_carried_pick_whose_board_line_moved(tmp_path, monkeypatch, capsys):
    import nfl.desk as D
    monkeypatch.setattr(D, "RESEARCH_DIR", tmp_path / "research")
    p = _payload()
    p["best_bets"]["ranked"] = [b for b in p["best_bets"]["ranked"] if not b["id"].startswith("qb_yds")]   # the 219.5 line is gone
    pf = tmp_path / "payload.json"
    pf.write_text(json.dumps(p))
    keep = tmp_path / "old.json"
    keep.write_text(json.dumps(_overlay(_qbyds(odds_source="draftkings"), _henry())))
    frags = tmp_path / "frags"
    frags.mkdir()
    (frags / "b.json").write_text(json.dumps({"game_id": "2026_06_BAL_CLE", "selections": [_henry()]}))
    rc = _run_assemble(["--season", "2026", "--week", "6", "--frags", str(frags), "--keep", str(keep), "--payload", str(pf)])
    out = capsys.readouterr().out
    assert rc == 0, out
    d = json.loads((tmp_path / "research" / "2026-w06.json").read_text())
    assert _qbyds()["id"] not in [s["id"] for s in d["selections"]]
    assert any(x["id"] == _qbyds()["id"] and "moved off the board" in x["why"] for x in d["declined"])


def test_first_build_on_this_code_keeps_what_the_old_code_published(live_spec):
    """Week 6 was published by the older code (no desk.excluded): its started picks keep their published state."""
    p = _payload()
    prev = copy.deepcopy(p)
    prev["bot"]["desk"] = {"ok": True, "selections": [{"id": _sel()["id"]}, {"id": _qbyds()["id"]}], "best": [_sel()["id"]]}   # old format
    later = _payload(kick=PAST)
    desk = merge(later, _overlay(_sel(), _qbyds()), prev)
    shown = {x["id"] for x in desk["selections"]}
    assert _sel()["id"] in shown and _qbyds()["id"] in shown          # the published pass-TD pick is not re-judged after kickoff
    assert desk["best"][0] == _sel()["id"]
