"""The week being published: schedule rows, starting quarterbacks, kickers, injuries, active rosters, weather.

Sources (all nflverse release files, refreshed every run, plus Open-Meteo for weather):
  schedule       games, kickoff, closing / current spread, total, moneylines and their prices, rest days,
                 roof, projected starting quarterbacks (filled in by nflverse during game week)
  injuries       the official practice and game-status report (Out / Doubtful / Questionable)
  depth charts   the latest team depth charts (starting QB and kicker when the schedule has none)
  weekly rosters active roster and positions (who can appear in the touchdown list)
"""
from __future__ import annotations

import math
from collections import Counter
from datetime import datetime, timedelta, timezone

from .config import RAW_DIR
from .venues import HOME_STADIUM, forecast, kickoff_utc


def _nan(x):
    return x is None or (isinstance(x, float) and math.isnan(x))


def _f(x):
    try:
        v = float(x)
        return None if math.isnan(v) else v
    except (TypeError, ValueError):
        return None


def _espn_id(x) -> str | None:
    try:
        return None if _nan(x) else str(int(float(x)))
    except (TypeError, ValueError):
        return None


def pick_week(sched, season: int, now: datetime | None = None) -> int | None:
    """The week to publish: the earliest regular-season week with a game not yet played (it stays up until
    Monday night's game is final, so the results of the week remain on the page)."""
    now = now or datetime.now(timezone.utc)
    s = sched[(sched["season"] == season) & (sched["game_type"] == "REG")]
    unplayed = s[s["home_score"].isna()]
    if len(unplayed) == 0:
        return None
    wk = int(unplayed["week"].min())
    # after the last game of a week (Tuesday morning UTC) move on even if a score is late to arrive
    return wk


def roof_for(row, sched) -> str:
    r = row.get("roof")
    if isinstance(r, str) and r:
        return r
    sid = row.get("stadium_id")
    past = sched[(sched["stadium_id"] == sid) & sched["roof"].notna()]["roof"]
    if len(past):
        return Counter(past.tolist()).most_common(1)[0][0]
    return "outdoors"


def load_reference(season: int):
    import pandas as pd  # type: ignore

    ref = {}
    for key in ("injuries", "depth", "rosters"):
        p = RAW_DIR / f"{key}_{season}.parquet"
        ref[key] = pd.read_parquet(p) if p.exists() else None
    p = RAW_DIR / "players.parquet"
    ref["players"] = pd.read_parquet(p, columns=["gsis_id", "display_name", "position", "latest_team", "status"]) if p.exists() else None
    return ref


def injuries_for(ref, season: int, week: int) -> dict[str, list[dict]]:
    inj = ref.get("injuries")
    out: dict[str, list[dict]] = {}
    if inj is None:
        return out
    w = inj[(inj["season"] == season) & (inj["week"] == week)]
    for r in w.itertuples(index=False):
        st = None if _nan(r.report_status) else str(r.report_status)
        pr = None if _nan(r.practice_status) else str(r.practice_status)
        injury = None if _nan(r.report_primary_injury) else str(r.report_primary_injury)
        if injury is None and not _nan(r.practice_primary_injury):
            injury = str(r.practice_primary_injury)
        out.setdefault(str(r.team), []).append({"id": str(r.gsis_id), "name": str(r.full_name), "pos": str(r.position), "status": st,
                                                "practice": pr, "injury": injury})
    return out


def depth_starters(ref) -> dict[str, dict]:
    """Latest depth chart: QB and K order per team, and every skill player's position and rank."""
    dc = ref.get("depth")
    out: dict[str, dict] = {}
    if dc is None or len(dc) == 0:
        return out
    last_dt = dc.groupby("team")["dt"].transform("max")
    cur = dc[dc["dt"] == last_dt]
    for t, g in cur.groupby("team"):
        d = {"QB": [], "K": [], "pos": {}, "dt": str(g["dt"].iloc[0])}
        for r in g.sort_values("pos_rank").itertuples(index=False):
            pos = str(r.pos_abb)
            gid = "" if _nan(r.gsis_id) else str(r.gsis_id)
            if pos in ("QB", "K") and gid and gid not in d[pos]:
                d[pos].append(gid)
            if pos in ("QB", "RB", "FB", "WR", "TE") and gid:
                d["pos"].setdefault(gid, f"{pos}{int(r.pos_rank)}")
        out[str(t)] = d
    return out


def active_rosters(ref) -> tuple[dict[str, set], dict[str, str], dict[str, str]]:
    """Players on each team's active roster in the latest roster week; positions; names."""
    ro = ref.get("rosters")
    act: dict[str, set] = {}
    pos: dict[str, str] = {}
    names: dict[str, str] = {}
    if ro is None or len(ro) == 0:
        return act, pos, names
    # each team's own latest roster week (early in a game week only the Thursday teams have the new week)
    last = ro[ro["week"] == ro.groupby("team")["week"].transform("max")]
    for r in last.itertuples(index=False):
        gid = "" if _nan(r.gsis_id) else str(r.gsis_id)
        if not gid:
            continue
        pos[gid] = str(r.position); names[gid] = str(r.full_name)
        if str(r.status) == "ACT":
            act.setdefault(str(r.team), set()).add(gid)
    return act, pos, names


def week_rows(sched, season: int, week: int, P, ref, with_weather: bool = True) -> list[dict]:
    """Schedule rows for the week, enriched with everything the model and the page need."""
    s = sched[(sched["season"] == season) & (sched["week"] == week) & (sched["game_type"] == "REG")].sort_values(["gameday", "gametime", "game_id"])
    inj = injuries_for(ref, season, week)
    depth = depth_starters(ref)
    act, pos, names = active_rosters(ref)
    rows = []
    for r in s.to_dict("records"):
        home, away = str(r["home_team"]), str(r["away_team"])
        ko = kickoff_utc(str(r["gameday"]), str(r["gametime"]))
        roof = roof_for(r, sched)
        row = {"game_id": str(r["game_id"]), "season": season, "week": week, "home": home, "away": away, "date": str(r["gameday"]),
               "time": str(r["gametime"]), "weekday": str(r["weekday"]), "kickoff_utc": ko.strftime("%Y-%m-%dT%H:%MZ") if ko else None,
               "stadium": str(r.get("stadium") or ""), "stadium_id": str(r.get("stadium_id") or HOME_STADIUM.get(home, "")),
               "location": str(r.get("location") or "Home"), "roof": roof, "surface": None if _nan(r.get("surface")) else str(r.get("surface")),
               "div": int(_f(r.get("div_game")) or 0), "rest": {"home": int(_f(r.get("home_rest")) or 7), "away": int(_f(r.get("away_rest")) or 7)},
               "lines": {"spread": _f(r.get("spread_line")), "total": _f(r.get("total_line")), "home_ml": _f(r.get("home_moneyline")),
                         "away_ml": _f(r.get("away_moneyline")), "home_spread_odds": _f(r.get("home_spread_odds")),
                         "away_spread_odds": _f(r.get("away_spread_odds")), "over_odds": _f(r.get("over_odds")), "under_odds": _f(r.get("under_odds"))},
               "score": None if _nan(r.get("home_score")) else {"home": int(r["home_score"]), "away": int(r["away_score"])},
               "espn": _espn_id(r.get("espn")),
               "coach": {"home": str(r.get("home_coach") or ""), "away": str(r.get("away_coach") or "")},
               "referee": None if _nan(r.get("referee")) else str(r.get("referee"))}
        # weather: observed values for played games, the forecast for upcoming outdoor games
        row["temp"] = _f(r.get("temp")); row["wind"] = _f(r.get("wind"))
        row["weather"] = None
        if roof in ("outdoors", "open") and row["score"] is None and with_weather:
            wx = forecast(row["stadium_id"], home, ko)
            if wx:
                row["weather"] = wx
                row["temp"] = wx.get("temp"); row["wind"] = wx.get("wind")
        # quarterbacks and kickers
        row["qb"] = {}; row["kicker"] = {}
        row["injuries"] = {"home": inj.get(home, []), "away": inj.get(away, [])}
        for side, t in (("home", home), ("away", away)):
            out_ids = {i["id"] for i in inj.get(t, []) if i["status"] in ("Out", "Doubtful")}
            q_ids = {i["id"]: i["status"] for i in inj.get(t, []) if i["status"]}
            # three sources, majority vote after dropping anyone ruled out: the nflverse schedule's projected starter
            # (it can lag: in 2026 it kept listing a backup for weeks), the quarterback who started the team's last
            # game (play-by-play), and the depth chart's QB1 (it can keep an injured starter on top). Ties go to the
            # last actual starter.
            S = None if _nan(r.get(f"{side}_qb_id")) else str(r.get(f"{side}_qb_id"))
            tp = P.teams.get(t)
            Lq = tp.last_qb if tp is not None else None
            dq = [q for q in (depth.get(t, {}).get("QB") or []) if q not in out_ids]
            D = dq[0] if dq else None
            votes: dict[str, int] = {}
            for c in (S, Lq, D):
                if c and c not in out_ids:
                    votes[c] = votes.get(c, 0) + 1
            nm = lambda q: names.get(q) or (P.qbs[q].name if q in P.qbs else (str(r.get(f"{side}_qb_name")) if q == S else q))  # noqa: E731
            if votes:
                top = max(votes.values())
                pick = next(c for c in (Lq, S, D) if c and votes.get(c) == top)
            else:
                pick = S or Lq or D or ""
            sid, sname = pick, (nm(pick) if pick else "")
            agree = votes.get(pick, 0)
            parts = []
            if S: parts.append(f"schedule {nm(S)}")
            if Lq: parts.append(f"last start {nm(Lq)}")
            if D: parts.append(f"depth chart {nm(D)}")
            src = ("all sources agree" if agree == 3 else f"{agree} of 3 sources") + (" (" + ", ".join(parts) + ")" if agree < 3 else "")
            row.setdefault("qb_uncertain", {})[side] = agree < 2
            row["qb"][side] = {"id": sid or "", "name": sname or "", "source": src, "status": q_ids.get(sid or "", "") or ""}
            dk = [k for k in (depth.get(t, {}).get("K") or []) if k not in out_ids]
            kid = dk[0] if dk else (tp.last_kicker if tp else "")
            row["kicker"][side] = kid
            row.setdefault("kicker_names", {})[side] = names.get(kid, "")
        row["active"] = {"home": sorted(act.get(home, set())), "away": sorted(act.get(away, set()))}
        row["names"] = {pid: names.get(pid, "") for pid in set(act.get(home, set())) | set(act.get(away, set())) if names.get(pid)}
        row["positions"] = {pid: depth.get(home, {}).get("pos", {}).get(pid) or depth.get(away, {}).get("pos", {}).get(pid) or pos.get(pid, "")
                            for pid in set(act.get(home, set())) | set(act.get(away, set()))}
        row["out"] = {"home": sorted({i["id"] for i in inj.get(home, []) if i["status"] in ("Out", "Doubtful")}),
                      "away": sorted({i["id"] for i in inj.get(away, []) if i["status"] in ("Out", "Doubtful")})}
        row["questionable"] = {"home": sorted({i["id"] for i in inj.get(home, []) if i["status"] == "Questionable"}),
                               "away": sorted({i["id"] for i in inj.get(away, []) if i["status"] == "Questionable"})}
        rows.append(row)
    return rows


__all__ = ["pick_week", "week_rows", "load_reference", "injuries_for", "depth_starters", "active_rosters", "roof_for"]
