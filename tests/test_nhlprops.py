"""NHL props: data conventions, distributions and the odds parsing."""
import numpy as np
import pandas as pd


def test_blocked_shot_attribution_and_assists():
    """In the sportsdataverse play-by-play the blocked shot's event team is the BLOCKING team and player 2 the blocker;
    goals carry the scorer as player 1 and assists as players 2 and 3."""
    from nhlprops.ingest import convert_season, sdv_file
    if not sdv_file(2027).exists():
        return
    sk, tf = convert_season(2027, verbose=False)
    # every skater block is counted once for the blocking team: skater sum ~ team sum (a few blockers lack on-ice data)
    assert 0.85 < sk.blk.sum() / tf.blk.sum() <= 1.0
    assert abs(sk.g.sum() - tf.gf.sum()) <= 2          # a scorer with no on-ice record is dropped from the skater table
    assert abs(sk.a.sum() / sk.g.sum() - 1.7) < 0.2        # about 1.7 assists per goal
    assert (sk.pts == sk.g + sk.a).all()
    assert tf.pp_opps.mean() > 2 and tf.ppg.mean() < tf.pp_opps.mean()
    assert (tf.ppg <= tf.gf).all()


def test_distributions_price_lines():
    from nhlprops.model import poisson_pmf, nb_pmf, over_under, fair_line
    p = poisson_pmf(1.0, 7)
    o, pu, u = over_under(p, 0.5)
    assert abs(o - (1 - np.exp(-1))) < 1e-3 and pu == 0
    o, pu, u = over_under(p, 1.0)
    assert abs(pu - np.exp(-1)) < 1e-3
    nb = nb_pmf(3.0, 15.0, 14)
    m = sum(k * x for k, x in enumerate(nb))
    assert abs(m - 3.0) < 0.05
    assert fair_line(nb) in (2.5, 3.5)
    assert abs(sum(nb) - 1) < 1e-4


def test_points_are_thinned_team_goals():
    """A skater with a 20% share of a team expected to score 3 goals has Poisson(0.6) points."""
    from nhlprops.features import League, Skater
    from nhlprops.config import CFG
    lg = League()
    S = Skater(pid=1, name="x", team="TOR", games=200, w=200.0, pts=120.0, tgf=600.0, oi=0.33 * 200, recent_oi=0.33)
    r = S.rates(lg, CFG)
    assert abs(r["pts_share"] - 0.2) < 0.02


def test_props_odds_parsing():
    from nhlprops.odds import parse_event, daily_allowance
    ev = {"home_team": "Toronto Maple Leafs", "away_team": "Montreal Canadiens", "bookmakers": [{"title": "DraftKings", "markets": [
        {"key": "player_shots_on_goal", "outcomes": [{"name": "Over", "description": "Auston Matthews", "point": 3.5, "price": 1.8}, {"name": "Under", "description": "Auston Matthews", "point": 3.5, "price": 2.0}]},
        {"key": "team_totals", "outcomes": [{"name": "Over", "description": "Toronto Maple Leafs", "point": 3.5, "price": 1.9}, {"name": "Under", "description": "Toronto Maple Leafs", "point": 3.5, "price": 1.9}]},
        {"key": "player_goal_scorer_anytime", "outcomes": [{"name": "Yes", "description": "Auston Matthews", "price": 2.1}]}]}]}
    d = parse_event(ev)
    assert d["home"] == "TOR" and d["away"] == "MTL"
    assert d["markets"]["sog"]["a matthews"]["books"]["DraftKings"]["line"] == 3.5
    assert d["markets"]["team_total"]["TOR"]["over"] == 1.9
    assert d["markets"]["goal"]["a matthews"]["yes"] == 2.1
    assert daily_allowance(None) == 0 and daily_allowance(450) > 0


def test_lineup_matching_and_fallback():
    from nhlprops.pipeline import lineup_skaters
    lu = {"groups": {"f1": [{"name": "Auston Matthews", "pos": "C"}], "d1": [{"name": "Morgan Rielly", "pos": "D"}], "pp1": [{"name": "Auston Matthews", "pos": "C"}]},
          "injuries": [{"name": "Morgan Rielly", "status": "Out"}]}
    rows, inj = lineup_skaters(lu)
    assert rows[0]["pp"] == "PP1" and rows[1]["pos"] == "D"
    assert "m rielly" in inj
