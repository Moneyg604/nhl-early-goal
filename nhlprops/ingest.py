"""Per-game skater and team records from the sportsdataverse play-by-play parquet (one file per season,
refreshed nightly; see earlygoal.ingest_sdv for the download).

Skater-game: shots on goal, goals, assists, points, blocked shots, individual expected goals, power-play
points, and two deployment measures: the share of the game's events he was on the ice for (a time-on-ice
proxy, there are no shift records in the file) and the same share during his team's power plays.

Team-game: shots and shot attempts for and against, blocks, goals for and against (regulation + overtime),
shootout flag, power-play opportunities and goals, times short-handed and goals allowed on them.

    python -m nhlprops ingest [--seasons 2023 2024 2025 2026]       (season = end year)
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd

from .config import DATA_DIR, SDV_DIR

TIME_EVENTS = {"SHOT", "MISSED_SHOT", "BLOCKED_SHOT", "GOAL", "FACEOFF", "HIT", "GIVEAWAY", "TAKEAWAY", "STOP"}
ATTEMPTS = {"SHOT", "MISSED_SHOT", "BLOCKED_SHOT", "GOAL"}


def sdv_file(season_end: int):
    return SDV_DIR / f"play_by_play_lite_{season_end}.parquet"


def skaters_file(season_end: int):
    return DATA_DIR / f"skaters_{season_end}.parquet"


def teams_file(season_end: int):
    return DATA_DIR / f"teams_{season_end}.parquet"


def _pp_for(df: pd.DataFrame) -> pd.Series:
    """True where the event team is on the power play (more skaters than the opponent, opponent at 4 or fewer)."""
    own = np.where(df.event_team_type == "home", df.home_skaters, df.away_skaters)
    opp = np.where(df.event_team_type == "home", df.away_skaters, df.home_skaters)
    return pd.Series((own > opp) & (opp <= 4) & (own >= 4), index=df.index)


def convert_season(season_end: int, verbose: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    t0 = time.time()
    cols = ["event_type", "event_team_abbr", "event_team_type", "description", "period_type", "game_seconds", "home_score", "away_score",
            "event_player_1_id", "event_player_1_name", "event_player_1_type", "event_player_2_id", "event_player_2_name", "event_player_2_type",
            "event_player_3_id", "event_player_3_name", "event_player_3_type", "penalty_severity", "penalty_minutes", "home_skaters", "away_skaters",
            "xg", "game_id", "season_type", "home_abbr", "away_abbr", "game_date", "event_idx", "empty_net"]
    cols += [f"{s}_on_{i}_id" for s in ("home", "away") for i in range(1, 8)]
    df = pd.read_parquet(sdv_file(season_end), columns=cols)
    df = df[(df.season_type == "R") & (df.period_type != "SHOOTOUT")].copy()
    df["game_id"] = df.game_id.astype(np.int64)
    df["pp"] = _pp_for(df)
    games = df.groupby("game_id").agg(home=("home_abbr", "first"), away=("away_abbr", "first"), date=("game_date", "first"),
                                      hs=("home_score", "max"), as_=("away_score", "max")).reset_index()
    # shootout: a game whose play-by-play includes a SHOOTOUT period
    full = pd.read_parquet(sdv_file(season_end), columns=["game_id", "period_type", "home_score", "away_score"])
    so_games = set(full.loc[full.period_type == "SHOOTOUT", "game_id"].astype(np.int64))
    ot_games = set(full.loc[full.period_type == "OVERTIME", "game_id"].astype(np.int64))
    final = full.groupby(full.game_id.astype(np.int64)).agg(hs=("home_score", "max"), as_=("away_score", "max"))
    games = games.set_index("game_id")
    games["so"] = games.index.isin(so_games)
    games["ot"] = games.index.isin(ot_games)
    games["hs_final"] = final.hs.reindex(games.index); games["as_final"] = final.as_.reindex(games.index)
    games = games.reset_index()

    # ---------------- skater events
    ev = df[df.event_type.isin({"SHOT", "GOAL", "BLOCKED_SHOT"})]
    rows = []
    shots = ev[ev.event_type.isin({"SHOT", "GOAL"})]
    s1 = shots.groupby(["game_id", "event_team_abbr", "event_player_1_id"]).agg(
        sog=("event_type", "size"), g=("event_type", lambda s: int((s == "GOAL").sum())), ixg=("xg", "sum"),
        pp_sog=("pp", "sum"), name=("event_player_1_name", "last")).reset_index().rename(columns={"event_team_abbr": "team", "event_player_1_id": "pid"})
    goals = ev[ev.event_type == "GOAL"]
    a_rows = []
    for k in (2, 3):
        a = goals[goals[f"event_player_{k}_type"] == "Assist"][["game_id", "event_team_abbr", f"event_player_{k}_id", f"event_player_{k}_name", "pp"]]
        a.columns = ["game_id", "team", "pid", "name", "pp"]
        a["primary"] = (k == 2)
        a_rows.append(a)
    assists = pd.concat(a_rows)
    s2 = assists.groupby(["game_id", "team", "pid"]).agg(a=("pid", "size"), a1=("primary", "sum"), pp_a=("pp", "sum"), name=("name", "last")).reset_index()
    ppg = goals[goals.pp].groupby(["game_id", "event_team_abbr", "event_player_1_id"]).size().rename("pp_g").reset_index().rename(columns={"event_team_abbr": "team", "event_player_1_id": "pid"})
    # a blocked shot's event team is the BLOCKING team (NHL API convention); player 1 is the shooter from the other side
    blocks = ev[ev.event_type == "BLOCKED_SHOT"].copy()
    blocks["team"] = blocks.event_team_abbr
    s3 = blocks.groupby(["game_id", "team", "event_player_2_id"]).agg(blk=("event_type", "size"), name=("event_player_2_name", "last")).reset_index().rename(columns={"event_player_2_id": "pid"})
    # on-ice shares (time proxy)
    te = df[df.event_type.isin(TIME_EVENTS)]
    n_ev = te.groupby("game_id").size().rename("n_ev")
    pp_rows = {}
    oi_parts = []
    for side in ("home", "away"):
        ids = te[[f"{side}_on_{i}_id" for i in range(1, 8)] + ["game_id", "pp", "event_team_type"]].copy()
        ids["own_pp"] = ids.pp & (ids.event_team_type == side)
        own_pp = ids.own_pp
        long = ids.melt(id_vars=["game_id", "own_pp"], value_vars=[f"{side}_on_{i}_id" for i in range(1, 8)], value_name="pid").dropna(subset=["pid"])
        oi = long.groupby(["game_id", "pid"]).agg(oi_n=("pid", "size"), oi_pp_n=("own_pp", "sum")).reset_index()
        oi["side"] = side
        oi_parts.append(oi)
        # team PP event counts (for the PP on-ice share denominator)
        pp_rows[side] = ids[own_pp].groupby("game_id").size()
    oi = pd.concat(oi_parts)
    oi = oi.merge(games[["game_id", "home", "away"]], on="game_id")
    oi["team"] = np.where(oi.side == "home", oi.home, oi.away)
    oi = oi.merge(n_ev, left_on="game_id", right_index=True)
    pp_den = pd.concat([pp_rows["home"].rename("pp_ev").reset_index().assign(side="home"), pp_rows["away"].rename("pp_ev").reset_index().assign(side="away")])
    oi = oi.merge(pp_den, on=["game_id", "side"], how="left")
    oi["oi"] = oi.oi_n / oi.n_ev
    oi["oi_pp"] = np.where(oi.pp_ev.fillna(0) > 0, oi.oi_pp_n / oi.pp_ev.replace(0, np.nan), np.nan)
    oi = oi[["game_id", "team", "pid", "oi", "oi_pp"]]
    sk = oi.merge(s1, on=["game_id", "team", "pid"], how="outer").merge(s2, on=["game_id", "team", "pid"], how="outer", suffixes=("", "_a")) \
           .merge(ppg, on=["game_id", "team", "pid"], how="outer").merge(s3, on=["game_id", "team", "pid"], how="outer", suffixes=("", "_b"))
    sk["name"] = sk.name.fillna(sk.get("name_a")).fillna(sk.get("name_b"))
    # a skater with no event of his own in a game still needs his name: the last name seen for the id this season
    names = sk.dropna(subset=["name"]).groupby("pid").name.last()
    sk["name"] = sk.name.fillna(sk.pid.map(names))
    for c in ("sog", "g", "ixg", "pp_sog", "a", "a1", "pp_a", "pp_g", "blk"):
        sk[c] = sk[c].fillna(0)
    sk["pts"] = sk.g + sk.a
    sk["pp_pts"] = sk.pp_g + sk.pp_a
    sk = sk.drop(columns=[c for c in ("name_a", "name_b") if c in sk.columns])
    # goalies are on the ice but not skaters: drop ids that appear as a goalie
    goalie_ids = set(pd.read_parquet(sdv_file(season_end), columns=["home_goalie_id", "away_goalie_id"]).stack().dropna().astype(np.int64))
    sk["pid"] = sk.pid.astype(np.int64)
    sk = sk[~sk.pid.isin(goalie_ids) & (sk.oi.fillna(0) > 0.02)]
    sk = sk.merge(games[["game_id", "date", "home", "away"]], on="game_id")
    sk["opp"] = np.where(sk.team == sk.home, sk.away, sk.home)
    sk["is_home"] = sk.team == sk.home
    sk["season"] = season_end
    sk = sk.drop(columns=["home", "away"]).sort_values(["date", "game_id", "team", "pid"]).reset_index(drop=True)

    # ---------------- team-games
    att = df[df.event_type.isin(ATTEMPTS)].copy()
    att["event_team_abbr"] = np.where(att.event_type == "BLOCKED_SHOT", np.where(att.event_team_abbr == att.home_abbr, att.away_abbr, att.home_abbr), att.event_team_abbr)
    tf = att.groupby(["game_id", "event_team_abbr"]).agg(att=("event_type", "size"), sog=("event_type", lambda s: int(s.isin(["SHOT", "GOAL"]).sum())),
                                                         gf=("event_type", lambda s: int((s == "GOAL").sum())), xgf=("xg", "sum"),
                                                         ppg=("pp", lambda s: 0)).reset_index().rename(columns={"event_team_abbr": "team"})
    gpp = goals[goals.pp].groupby(["game_id", "event_team_abbr"]).size().rename("ppg").reset_index().rename(columns={"event_team_abbr": "team"})
    tf = tf.drop(columns=["ppg"]).merge(gpp, on=["game_id", "team"], how="left")
    tf["ppg"] = tf.ppg.fillna(0).astype(int)
    blk_made = blocks.groupby(["game_id", "team"]).size().rename("blk").reset_index()
    tf = tf.merge(blk_made, on=["game_id", "team"], how="left"); tf["blk"] = tf.blk.fillna(0).astype(int)
    # power-play opportunities: a minor or a non-fighting major with no offsetting penalty on the other team at the same second
    pen = df[(df.event_type == "PENALTY") & df.penalty_severity.isin(["Minor", "Major"]) & (df.penalty_minutes > 0)].copy()
    pen = pen[~pen.description.fillna("").str.contains("fighting", case=False)]
    pen["key"] = pen.game_id.astype(str) + ":" + pen.game_seconds.astype(str)
    both = pen.groupby("key").event_team_abbr.nunique()
    offsetting = set(both[both > 1].index)
    pen = pen[~pen.key.isin(offsetting)]
    pen = pen.merge(games[["game_id", "home", "away"]], on="game_id")
    pen["pp_team"] = np.where(pen.event_team_abbr == pen.home, pen.away, pen.home)
    opps = pen.groupby(["game_id", "pp_team"]).size().rename("pp_opps").reset_index().rename(columns={"pp_team": "team"})
    tf = tf.merge(opps, on=["game_id", "team"], how="left"); tf["pp_opps"] = tf.pp_opps.fillna(0).astype(int)
    tf = tf.merge(games[["game_id", "date", "home", "away", "so", "ot", "hs_final", "as_final"]], on="game_id")
    tf["opp"] = np.where(tf.team == tf.home, tf.away, tf.home)
    tf["is_home"] = tf.team == tf.home
    # against: join the opponent's row
    opp_cols = tf[["game_id", "team", "att", "sog", "gf", "xgf", "ppg", "pp_opps", "blk"]].rename(
        columns={"team": "opp", "att": "att_a", "sog": "sog_a", "gf": "ga", "xgf": "xga", "ppg": "ppga", "pp_opps": "pk_opps", "blk": "blk_a"})
    tf = tf.merge(opp_cols, on=["game_id", "opp"], how="left")
    tf["final_for"] = np.where(tf.is_home, tf.hs_final, tf.as_final)         # includes the shootout winner's credited goal
    tf["season"] = season_end
    tf = tf.drop(columns=["home", "away", "hs_final", "as_final"]).sort_values(["date", "game_id", "team"]).reset_index(drop=True)
    if verbose:
        print(f"  {season_end}: {len(games)} games, {len(sk)} skater-games, {len(tf)} team-games in {time.time() - t0:.1f}s", file=sys.stderr)
    return sk, tf


def ingest(seasons: list[int], force: bool = False) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for s in seasons:
        src = sdv_file(s)
        if not src.exists():
            print(f"  {s}: no play-by-play file ({src.name})", file=sys.stderr)
            continue
        dst = skaters_file(s)
        if dst.exists() and not force and dst.stat().st_mtime >= src.stat().st_mtime:
            continue
        sk, tf = convert_season(s)
        sk.to_parquet(dst, index=False)
        tf.to_parquet(teams_file(s), index=False)


def load(seasons: list[int]) -> tuple[pd.DataFrame, pd.DataFrame]:
    sk, tf = [], []
    for s in seasons:
        if skaters_file(s).exists():
            sk.append(pd.read_parquet(skaters_file(s))); tf.append(pd.read_parquet(teams_file(s)))
    if not sk:
        return pd.DataFrame(), pd.DataFrame()
    return pd.concat(sk, ignore_index=True), pd.concat(tf, ignore_index=True)


__all__ = ["convert_season", "ingest", "load", "skaters_file", "teams_file"]
