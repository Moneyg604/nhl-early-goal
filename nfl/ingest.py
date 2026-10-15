"""nflverse play-by-play -> one compact record per game (data/nfl/games_<season>.jsonl).

Each record carries what the model measures: every drive with its result, points, length and half; the
quarter scores; every field-goal and extra-point try with the kicker; per-team play counts, dropbacks,
yards and EPA; per-quarterback passing lines; every skill player's touches, targets and touchdowns; the
closing market lines (spread, total, moneylines) from the nflverse schedule; roof, surface, temperature
and wind. Nothing is derived here that cannot be recomputed from the raw parquet.

    python -m nfl ingest            # current season + the seasons the model uses (downloads once, converts)
    python -m nfl ingest --back 6   # also refresh older seasons
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import ASSETS, DATA_DIR, FIRST_SEASON, RAW_DIR
from .features import annotate_spans

PBP_COLS = [
    "game_id", "home_team", "away_team", "season_type", "season", "week", "game_date", "posteam", "defteam", "qtr",
    "game_seconds_remaining", "half_seconds_remaining", "game_half", "play_type", "yards_gained", "touchdown",
    "pass_touchdown", "rush_touchdown", "return_touchdown", "field_goal_result", "field_goal_attempt", "kick_distance",
    "extra_point_result", "extra_point_attempt", "two_point_conv_result", "two_point_attempt", "total_home_score",
    "total_away_score", "posteam_score", "posteam_score_post", "fixed_drive", "fixed_drive_result",
    "drive_start_transition", "drive_play_count", "drive_start_yard_line", "passer_player_id", "passer_player_name",
    "passing_yards", "complete_pass", "pass_attempt", "sack", "qb_dropback", "rusher_player_id", "rusher_player_name",
    "rushing_yards", "receiver_player_id", "receiver_player_name", "receiving_yards", "td_player_id", "td_player_name",
    "kicker_player_id", "kicker_player_name", "safety", "interception", "fumble_lost", "epa", "qb_kneel", "qb_spike",
    "penalty", "punt_attempt", "kickoff_attempt", "roof", "surface", "temp", "wind", "spread_line", "total_line",
    "result", "total", "desc", "yardline_100", "down",
]

RESULT_CODES = {
    "Touchdown": "TD", "Field goal": "FG", "Missed field goal": "FGM", "Punt": "PUNT", "Turnover": "TO",
    "Turnover on downs": "DOWNS", "End of half": "EOH", "Opp touchdown": "OPPTD", "Safety": "SAF",
}


def season_now(now: datetime | None = None) -> int:
    """The NFL season a date belongs to (the season of the Super Bowl played in February 2027 is 2026)."""
    now = now or datetime.now(timezone.utc)
    return now.year if now.month >= 3 else now.year - 1


def games_file(season: int) -> Path:
    return DATA_DIR / f"games_{season}.jsonl"


def download(url: str, dest: Path, max_age_h: float | None = None, force: bool = False) -> Path | None:
    """Fetch a release asset into data/nfl/raw/ (skipped when a fresh copy exists). Never raises."""
    import requests  # type: ignore

    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        if max_age_h is None or time.time() - dest.stat().st_mtime < max_age_h * 3600:
            return dest
    try:
        r = requests.get(url, timeout=300, headers={"User-Agent": "Mozilla/5.0"}, stream=True)
        if not r.ok:
            print(f"  {url}: HTTP {r.status_code}")
            return dest if dest.exists() else None
        tmp = dest.with_suffix(dest.suffix + ".part")
        with tmp.open("wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        if tmp.stat().st_size < 1000:
            tmp.unlink(missing_ok=True)
            return dest if dest.exists() else None
        tmp.replace(dest)
        return dest
    except Exception as e:  # noqa: BLE001
        print(f"  {url}: {e}")
        return dest if dest.exists() else None


def fetch_schedule(force: bool = False) -> Path | None:
    return download(ASSETS["schedule"], RAW_DIR / "games.csv", max_age_h=3, force=force)


def fetch_reference(season: int, force: bool = False) -> dict[str, Path | None]:
    """Injuries, depth charts, weekly rosters (current season) and the player table."""
    out = {}
    for key in ("injuries", "depth", "rosters"):
        out[key] = download(ASSETS[key].format(season=season), RAW_DIR / f"{key}_{season}.parquet", max_age_h=3, force=force)
    out["players"] = download(ASSETS["players"], RAW_DIR / "players.parquet", max_age_h=72, force=force)
    return out


def _f(x, default=None):
    try:
        if x is None:
            return default
        v = float(x)
        return default if v != v else v
    except (TypeError, ValueError):
        return default


def _i(x, default=0):
    v = _f(x)
    return default if v is None else int(v)


def convert_season(season: int, pbp_path: Path, schedule: "pd.DataFrame | None" = None) -> int:  # type: ignore[name-defined]  # noqa: F821
    """Parquet -> games_<season>.jsonl. Returns the number of games written."""
    import pandas as pd  # type: ignore

    import pyarrow.parquet as pq  # type: ignore

    names = set(pq.ParquetFile(pbp_path).schema.names)
    cols = [c for c in PBP_COLS if c in names]
    df = pd.read_parquet(pbp_path, columns=cols)
    df = df[df["play_type"].notna() | df["fixed_drive_result"].notna()]
    sched = {}
    if schedule is not None:
        for r in schedule[schedule["season"] == season].itertuples(index=False):
            sched[r.game_id] = r
    recs = []
    for gid, g in df.groupby("game_id", sort=True):
        g = g.sort_index()
        home, away = str(g["home_team"].iloc[0]), str(g["away_team"].iloc[0])
        stype = str(g["season_type"].iloc[0])
        rec = {"game_id": str(gid), "season": int(season), "week": _i(g["week"].iloc[0]), "type": stype,
               "date": str(g["game_date"].iloc[0])[:10], "home": home, "away": away}
        # final + quarter scores (total_*_score is the score after the play)
        hs = _i(g["total_home_score"].max()); as_ = _i(g["total_away_score"].max())
        rec["hs"], rec["as"] = hs, as_
        qh, qa = [], []
        ph = pa = 0
        for q in (1, 2, 3, 4, 5):
            sub = g[g["qtr"] == q]
            if len(sub) == 0:
                if q <= 4:
                    qh.append(0); qa.append(0)
                continue
            th, ta = _i(sub["total_home_score"].max()), _i(sub["total_away_score"].max())
            th, ta = max(th, ph), max(ta, pa)
            qh.append(th - ph); qa.append(ta - pa)
            ph, pa = th, ta
        rec["q"] = {"home": qh, "away": qa}
        rec["ot"] = int((g["qtr"] >= 5).any())
        for k in ("roof", "surface"):
            v = g[k].iloc[0] if k in g else None
            rec[k] = None if v is None or (isinstance(v, float) and v != v) else str(v)
        rec["temp"] = _f(g["temp"].iloc[0]) if "temp" in g else None
        rec["wind"] = _f(g["wind"].iloc[0]) if "wind" in g else None
        lines = {"spread": _f(g["spread_line"].iloc[0]), "total": _f(g["total_line"].iloc[0])}
        s = sched.get(str(gid))
        if s is not None:
            lines.update({"home_ml": _f(getattr(s, "home_moneyline", None)), "away_ml": _f(getattr(s, "away_moneyline", None)),
                          "home_spread_odds": _f(getattr(s, "home_spread_odds", None)), "away_spread_odds": _f(getattr(s, "away_spread_odds", None)),
                          "over_odds": _f(getattr(s, "over_odds", None)), "under_odds": _f(getattr(s, "under_odds", None))})
            rec["rest"] = {"home": _i(getattr(s, "home_rest", 7), 7), "away": _i(getattr(s, "away_rest", 7), 7)}
            rec["div"] = _i(getattr(s, "div_game", 0))
            rec["time"] = str(getattr(s, "gametime", "") or "")
            rec["weekday"] = str(getattr(s, "weekday", "") or "")
            rec["stadium"] = str(getattr(s, "stadium", "") or "")
            rec["location"] = str(getattr(s, "location", "Home") or "Home")
            rec["qb"] = {"home": {"id": str(getattr(s, "home_qb_id", "") or ""), "name": str(getattr(s, "home_qb_name", "") or "")},
                         "away": {"id": str(getattr(s, "away_qb_id", "") or ""), "name": str(getattr(s, "away_qb_name", "") or "")}}
        rec["lines"] = lines

        # drives (points from the running home/away totals, so a defensive score inside a drive lands on the right side)
        drives = []
        g = g.assign(_th=g["total_home_score"].ffill().fillna(0), _ta=g["total_away_score"].ffill().fillna(0))
        g["_th_pre"] = g["_th"].shift(1).fillna(0)
        g["_ta_pre"] = g["_ta"].shift(1).fillna(0)
        dg = g[g["fixed_drive"].notna()]
        for dn, d in dg.groupby("fixed_drive", sort=True):
            team = d["posteam"].dropna()
            team = str(team.iloc[0]) if len(team) else None
            if team not in (home, away):
                continue
            res = RESULT_CODES.get(str(d["fixed_drive_result"].iloc[0]), None)
            if res is None:
                continue
            half = str(d["game_half"].iloc[0])
            h = 1 if half == "Half1" else (2 if half == "Half2" else 3)
            th0, ta0 = _i(d["_th_pre"].iloc[0]), _i(d["_ta_pre"].iloc[0])
            th1, ta1 = _i(d["_th"].max()), _i(d["_ta"].max())
            own, opp = (th1 - th0, ta1 - ta0) if team == home else (ta1 - ta0, th1 - th0)
            start_sec = _f(d["game_seconds_remaining"].max(), 0.0) or 0.0
            end_sec = _f(d["game_seconds_remaining"].min(), 0.0) or 0.0
            secs = max(0.0, start_sec - end_sec)
            plays = int(((d["play_type"].isin(["pass", "run", "qb_kneel", "qb_spike"])) & (d["penalty"].fillna(0) == 0)).sum())
            st = d["drive_start_transition"].iloc[0]
            st = "" if st is None or (isinstance(st, float) and st != st) else str(st)
            dbm = (d["qb_dropback"] == 1) & (d["posteam"] == team)
            pam = (d["pass_attempt"] == 1) & (d["posteam"] == team)
            margin0 = (th0 - ta0) if team == home else (ta0 - th0)
            drives.append({"n": int(dn), "t": team, "h": h, "q": _i(d["qtr"].iloc[0]), "res": res, "pts": max(0, own), "opts": max(0, opp),
                           "plays": plays, "secs": round(secs), "start": st, "eos": round(end_sec), "m": margin0,
                           "db": int(dbm.sum()), "py": int(d.loc[pam, "passing_yards"].fillna(0).sum()),
                           "ptd": int(((d["pass_touchdown"] == 1) & (d["posteam"] == team)).sum()),
                           "rtd": int(((d["rush_touchdown"] == 1) & (d["posteam"] == team)).sum())})
        rec["drives"] = drives

        # kicks
        fg = {home: [], away: []}
        for r in g[g["field_goal_attempt"] == 1].itertuples(index=False):
            t = str(r.posteam)
            if t in fg:
                fg[t].append({"d": _i(r.kick_distance), "r": str(r.field_goal_result), "k": str(r.kicker_player_id or ""), "q": _i(r.qtr),
                              "h": 1 if str(r.game_half) == "Half1" else 2, "late": int(_f(r.half_seconds_remaining, 999) <= 60)})
        rec["fg"] = fg
        xp = {}
        for t in (home, away):
            sub = g[(g["extra_point_attempt"] == 1) & (g["posteam"] == t)]
            two = g[(g["two_point_attempt"] == 1) & (g["posteam"] == t)]
            xp[t] = {"att": int(len(sub)), "made": int((sub["extra_point_result"] == "good").sum()),
                     "two_att": int(len(two)), "two_made": int((two["two_point_conv_result"] == "success").sum())}
        rec["xp"] = xp
        kicker = {}
        for t in (home, away):
            ks = g[(g["posteam"] == t) & ((g["field_goal_attempt"] == 1) | (g["extra_point_attempt"] == 1))]["kicker_player_id"].dropna()
            kicker[t] = str(ks.mode().iloc[0]) if len(ks) else ""
        rec["kicker"] = kicker

        # team lines
        team = {}
        for t in (home, away):
            o = g[(g["posteam"] == t)]
            plays = o[o["play_type"].isin(["pass", "run"]) & (o["penalty"].fillna(0) == 0)]
            db = o[o["qb_dropback"] == 1]
            passes = o[o["pass_attempt"] == 1]
            rushes = o[(o["play_type"] == "run") & (o["penalty"].fillna(0) == 0)]
            td_off = o[(o["touchdown"] == 1) & ((o["pass_touchdown"] == 1) | (o["rush_touchdown"] == 1))]
            team[t] = {
                "plays": int(len(plays)), "db": int(len(db)), "att": int((passes["sack"].fillna(0) == 0).sum()), "cmp": int(passes["complete_pass"].fillna(0).sum()),
                "pyds": int(passes["passing_yards"].fillna(0).sum()), "rush": int(len(rushes)), "ryds": int(rushes["rushing_yards"].fillna(0).sum()),
                "epa": round(float(plays["epa"].fillna(0).sum()), 3), "epa_db": round(float(db["epa"].fillna(0).sum()), 3),
                "epa_rush": round(float(rushes["epa"].fillna(0).sum()), 3), "sk": int(o["sack"].fillna(0).sum()),
                "int": int(o["interception"].fillna(0).sum()), "fl": int(o["fumble_lost"].fillna(0).sum()),
                "td_pass": int((td_off["pass_touchdown"] == 1).sum()), "td_rush": int((td_off["rush_touchdown"] == 1).sum()),
                "td_ret": int(((g["return_touchdown"] == 1) & (g["td_player_id"].notna()) & (g["defteam"] != t) & (g["posteam"] != t)).sum()),
                "h1": {"db": int((db["game_half"] == "Half1").sum()), "plays": int((plays["game_half"] == "Half1").sum()),
                       "pyds": int(passes[passes["game_half"] == "Half1"]["passing_yards"].fillna(0).sum())},
            }
        # defensive / return touchdowns credited to the scoring team (td_player on a play where posteam is the other side)
        for t in (home, away):
            other = away if t == home else home
            dtd = g[(g["touchdown"] == 1) & (g["pass_touchdown"] != 1) & (g["rush_touchdown"] != 1) & (g["td_player_id"].notna())]
            # return touchdowns: posteam is the kicking team on kickoffs/punts, the offense on turnovers; score goes to the team of the scorer
            n = 0
            for r in dtd.itertuples(index=False):
                scorer_team = _scorer_team(r, home, away)
                if scorer_team == t:
                    n += 1
            team[t]["td_other"] = n
        rec["team"] = team

        # quarterbacks
        qbs = {home: {}, away: {}}
        for t in (home, away):
            o = g[(g["posteam"] == t) & (g["qb_dropback"] == 1) & g["passer_player_id"].notna()]
            for pid, p in o.groupby("passer_player_id"):
                att = p[p["pass_attempt"] == 1]
                qbs[t][str(pid)] = {"name": str(p["passer_player_name"].iloc[0]), "db": int(len(p)), "att": int((att["sack"].fillna(0) == 0).sum()),
                                   "cmp": int(att["complete_pass"].fillna(0).sum()), "yds": int(att["passing_yards"].fillna(0).sum()),
                                   "td": int(att["pass_touchdown"].fillna(0).sum()), "int": int(att["interception"].fillna(0).sum()),
                                   "sk": int(p["sack"].fillna(0).sum()), "epa": round(float(p["epa"].fillna(0).sum()), 3),
                                   "h1_yds": int(att[att["game_half"] == "Half1"]["passing_yards"].fillna(0).sum()),
                                   "h1_db": int((p["game_half"] == "Half1").sum())}
            # quarterback rushing (anytime touchdown market)
            for pid in list(qbs[t]):
                ru = g[(g["posteam"] == t) & (g["rusher_player_id"] == pid) & (g["play_type"] == "run")]
                qbs[t][pid]["ryds"] = int(ru["rushing_yards"].fillna(0).sum())
                qbs[t][pid]["rtd"] = int(ru["rush_touchdown"].fillna(0).sum())
                qbs[t][pid]["car"] = int(len(ru))
        rec["qbs"] = qbs

        # skill players: touches, targets, touchdowns
        players = {home: {}, away: {}}

        def ent(t, pid, name):
            d = players[t].setdefault(str(pid), {"name": str(name), "car": 0, "tgt": 0, "rec": 0, "rtd": 0, "rectd": 0, "ryds": 0, "recyds": 0, "rzc": 0, "rzt": 0, "ret_td": 0})
            return d

        for t in (home, away):
            o = g[g["posteam"] == t]
            for r in o[(o["play_type"] == "run") & o["rusher_player_id"].notna()].itertuples(index=False):
                e = ent(t, r.rusher_player_id, r.rusher_player_name)
                e["car"] += 1; e["ryds"] += _i(r.rushing_yards); e["rtd"] += _i(r.rush_touchdown)
                if _f(r.yardline_100, 99) <= 20:
                    e["rzc"] += 1
            for r in o[(o["pass_attempt"] == 1) & o["receiver_player_id"].notna()].itertuples(index=False):
                e = ent(t, r.receiver_player_id, r.receiver_player_name)
                e["tgt"] += 1; e["rec"] += _i(r.complete_pass); e["recyds"] += _i(r.receiving_yards); e["rectd"] += _i(r.pass_touchdown)
                if _f(r.yardline_100, 99) <= 20:
                    e["rzt"] += 1
        # return / defensive touchdowns by scorer
        for r in g[(g["touchdown"] == 1) & (g["pass_touchdown"] != 1) & (g["rush_touchdown"] != 1) & g["td_player_id"].notna()].itertuples(index=False):
            t = _scorer_team(r, home, away)
            if t in players:
                ent(t, r.td_player_id, r.td_player_name)["ret_td"] += 1
        rec["players"] = players
        recs.append(rec)

    out = games_file(season)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for r in recs:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")
    return len(recs)


def _scorer_team(r, home: str, away: str) -> str | None:
    """Team credited with a non-offensive touchdown: a return on a kickoff/punt belongs to the receiving team
    (defteam), a turnover return to the defense (defteam); when the play text names the team we trust that."""
    desc = str(getattr(r, "desc", "") or "")
    pos, de = str(getattr(r, "posteam", "")), str(getattr(r, "defteam", ""))
    pt = str(getattr(r, "play_type", ""))
    if pt in ("kickoff", "punt"):
        return de if de in (home, away) else None
    # fumble return by the offense's own player (rare) shows up as a rush/pass td, not here; everything else is the defense
    if "TOUCHDOWN" in desc and de in (home, away):
        return de
    return de if de in (home, away) else (pos if pos in (home, away) else None)


def load_games(seasons: list[int], reg_only: bool = True) -> list[dict]:
    out = []
    for s in seasons:
        f = games_file(s)
        if not f.exists():
            continue
        with f.open() as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if reg_only and r.get("type") != "REG":
                    continue
                annotate_spans(r)
                out.append(r)
    out.sort(key=lambda r: (r["date"], r["game_id"]))
    return out


def load_schedule() -> "pd.DataFrame | None":  # type: ignore[name-defined]  # noqa: F821
    import pandas as pd  # type: ignore

    p = RAW_DIR / "games.csv"
    if not p.exists():
        p = fetch_schedule()
    if p is None or not p.exists():
        return None
    return pd.read_csv(p, low_memory=False)


def ingest(seasons: list[int], current: int, force_current: bool = True) -> dict[int, int]:
    """Download and convert the given seasons (the current season is re-fetched every run)."""
    fetch_schedule()
    sched = load_schedule()
    counts = {}
    for s in seasons:
        p = download(ASSETS["pbp"].format(season=s), RAW_DIR / f"pbp_{s}.parquet", max_age_h=(2 if s == current else None), force=False)
        if p is None:
            counts[s] = sum(1 for _ in games_file(s).open()) if games_file(s).exists() else 0
            continue
        fresh = games_file(s).exists() and games_file(s).stat().st_mtime >= p.stat().st_mtime
        if fresh and not (s == current and force_current):
            counts[s] = sum(1 for _ in games_file(s).open())
            continue
        counts[s] = convert_season(s, p, sched)
        print(f"  {s}: {counts[s]} games")
    return counts


def data_through(seasons: list[int]) -> str:
    games = load_games(seasons, reg_only=False)
    return max((g["date"] for g in games), default="")


def seasons_available() -> list[int]:
    return sorted(int(p.stem.split("_")[1]) for p in DATA_DIR.glob("games_*.jsonl"))


__all__ = ["ingest", "load_games", "load_schedule", "fetch_schedule", "fetch_reference", "season_now", "data_through", "seasons_available", "FIRST_SEASON"]
