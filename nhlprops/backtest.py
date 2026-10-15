"""Walk-forward validation of the props, day by day.

Profiles are rebuilt every `rebuild_days` from records strictly before the day; each game of the day is
priced for the skaters who dressed in their team's previous game (the pregame candidate set, exactly what
the live page uses), and a candidate who did not play is a void bet, not a loss.

Each market is scored by log loss against a baseline that needs no model:
    shots on goal       over / under a line at his trailing average   vs a negative binomial at that average
    blocked shots       same
    points / assists / anytime goal (over 0.5)                          vs a Poisson at his trailing rate
    team total          over / under at the team's trailing average   vs a Poisson at that average
    power-play goals    over 0.5 / 1.5                                 vs a Poisson at the team's trailing rate
plus calibration by decile. "Beats baseline" = gain more than two standard errors above zero.

    python -m nhlprops backtest [--seasons 2024 2025 2026]     (season = end year)
"""
from __future__ import annotations

import json
import math
import time
from datetime import date, timedelta

import numpy as np
import pandas as pd

from .config import CFG, DATA_DIR, ModelConfig
from .features import build
from .ingest import load
from .model import team_inputs, skater_markets, team_markets, over_under, nb_pmf, poisson_pmf, KMAX

TRAIL_PLAYER = 10          # games in a player's trailing average (sets the line, as the books do)
TRAIL_BASE = 25            # games in the baseline rate, shrunk toward the league skater rate with K_BASE pseudo-games
K_BASE = 3.0
TRAIL_TEAM = 20


def ll(p: float, y: int) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _line_at(avg: float) -> float:
    return math.floor(avg) + 0.5


def run(seasons: list[int], cfg: ModelConfig = CFG, rebuild_days: int = 7, verbose: bool = True) -> dict:
    t0 = time.time()
    all_seasons = list(range(min(seasons) - 2, max(seasons) + 1))
    sk, tf = load(all_seasons)
    sk = sk.sort_values("date"); tf = tf.sort_values("date")
    test_t = tf[tf.season.isin(seasons)]
    days = sorted(test_t.date.unique())
    rows: list[dict] = []
    P = None; built_for = None
    sk_by_game = {k: g for k, g in sk.groupby("game_id")}
    # player and team histories for trailing averages (ordered by date; sliced with searchsorted)
    sk_by_pid = {int(k): (g.date.values.astype(str), g) for k, g in sk.groupby("pid")}
    tf_by_team = {k: (g.date.values.astype(str), g) for k, g in tf.groupby("team")}
    sk_by_team = {k: (g.date.values.astype(str), g) for k, g in sk.groupby("team")}

    def before(store, key, d, n):
        if key not in store:
            return None
        dates, g = store[key]
        i = int(np.searchsorted(dates, d, side="left"))
        return g.iloc[max(0, i - n):i]

    def dressed(team, d):
        g = before(sk_by_team, team, d, 60)
        if g is None or g.empty:
            return set()
        last_date = g.date.values[-1]
        return set(g[g.date == last_date].pid.astype(int))
    for d in days:
        if P is None or (date.fromisoformat(d) - date.fromisoformat(built_for)).days >= rebuild_days:
            P = build(sk, tf, d, cfg); built_for = d
        day_games = test_t[test_t.date == d]
        for gid, g in day_games.groupby("game_id"):
            if len(g) != 2:
                continue
            home = g[g.is_home].iloc[0]; away = g[~g.is_home].iloc[0]
            played = sk_by_game.get(gid)
            if played is None:
                continue
            for side, opp in ((home, away), (away, home)):
                team = side.team
                ti = team_inputs(P, team, opp.team, bool(side.is_home), cfg)
                tm = team_markets(P, ti)
                # team trailing averages (pregame)
                hist = before(tf_by_team, team, d, TRAIL_TEAM)
                row = {"game_id": int(gid), "date": d, "season": int(side.season), "team": team, "opp": opp.team, "home": bool(side.is_home)}
                if hist is not None and len(hist) >= 8:
                    avg_g = (float(hist.final_for.sum()) + 5 * P.league.team_gf) / (len(hist) + 5)
                    avg_ppg = (float(hist.ppg.sum()) + 5 * P.league.pp_opps * P.league.pp_conv) / (len(hist) + 5)
                    L = _line_at(avg_g)
                    po, pu, _ = over_under(tm["team_total"], L)
                    bo, bu, _ = over_under(poisson_pmf(avg_g, KMAX["team_total"]), L)
                    row["team_total"] = {"line": L, "p": po / max(1e-9, 1 - pu), "base": bo / max(1e-9, 1 - bu), "y": int(side.final_for > L), "push": int(side.final_for == L),
                                         "act": int(side.final_for), "lam": tm["lam_goals"], "avg": round(avg_g, 2)}
                    for nm, thr in (("ppg05", 0.5), ("ppg15", 1.5)):
                        row[nm] = {"p": over_under(tm["ppg"], thr)[0], "base": over_under(poisson_pmf(avg_ppg, KMAX["ppg"]), thr)[0], "y": int(side.ppg > thr), "lam": tm["lam_ppg"]}
                # skaters: dressed last game, settled only if he played
                cands = dressed(team, d)
                pl = played[played.team == team].set_index("pid")
                srows = []
                for pid in cands:
                    S = P.skaters.get(int(pid))
                    if S is None or pid not in pl.index:
                        continue
                    act = pl.loc[pid]
                    pb = before(sk_by_pid, int(pid), d, TRAIL_BASE)
                    if pb is None or len(pb) < 5:
                        continue
                    ph = pb.tail(TRAIL_PLAYER)
                    lg = P.league
                    base_rate = lambda col, lr: (float(pb[col].sum()) + K_BASE * lr) / (len(pb) + K_BASE)  # noqa: E731
                    m = skater_markets(P, S, ti, ti["lam_goals"], cfg)
                    sr = {"pid": int(pid), "name": S.name}
                    for key, akey in (("sog", "sog"), ("blk", "blk")):
                        avg = float(ph[akey].mean())
                        if avg < 0.6:
                            continue
                        L = _line_at(avg)
                        size = lg.nb_size_sog if key == "sog" else lg.nb_size_blk
                        po, pu, _ = over_under(m["pmf"][key], L)
                        bo, bu, _ = over_under(nb_pmf(base_rate(akey, lg.sog if key == "sog" else lg.blk), size, KMAX[key]), L)
                        sr[key] = {"line": L, "p": po / max(1e-9, 1 - pu), "base": bo / max(1e-9, 1 - bu), "y": int(act[akey] > L), "act": int(act[akey]), "mean": m["mean"][key], "avg": round(avg, 2)}
                    for key, akey in (("pts", "pts"), ("ast", "a"), ("goal", "g")):
                        avg = float(ph[akey].mean())
                        po = over_under(m["pmf"][key], 0.5)[0]
                        lr = {"pts": (1 + lg.ast_per_goal) / 18 * lg.team_gf, "a": lg.ast_per_goal / 18 * lg.team_gf, "g": lg.team_gf / 18}[akey]
                        bo = 1 - math.exp(-base_rate(akey, lr))
                        sr[key] = {"p": po, "base": bo, "y": int(act[akey] > 0.5), "act": int(act[akey]), "mean": m["mean"][key], "avg": round(avg, 2)}
                    srows.append(sr)
                row["skaters"] = srows
                rows.append(row)
        if verbose and days.index(d) % 30 == 0:
            print(f"  {d}: {len(rows)} team-games in {time.time() - t0:.0f}s", flush=True)
    out = {"seasons": seasons, "minutes": round((time.time() - t0) / 60, 1), "cfg": cfg.__dict__, "pooled": summarize(rows),
           "by_season": {str(s): summarize([r for r in rows if r["season"] == s]) for s in seasons}, "rows": rows,
           "generated_utc": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())}
    return out


def _calib(ps, ys, bins=10):
    if not ps:
        return []
    ps = np.array(ps); ys = np.array(ys)
    o = np.argsort(ps); ps, ys = ps[o], ys[o]
    out = []
    for chunk in np.array_split(np.arange(len(ps)), bins):
        if len(chunk):
            out.append({"n": int(len(chunk)), "pred": round(float(ps[chunk].mean()), 4), "actual": round(float(ys[chunk].mean()), 4)})
    return out


def _cmp(name: str, model, base, ys, note: str) -> dict:
    n = len(ys)
    if n == 0:
        return {"name": name, "n": 0}
    lm = np.array([ll(p, y) for p, y in zip(model, ys)]); lb = np.array([ll(p, y) for p, y in zip(base, ys)])
    d = lb - lm
    se = float(d.std(ddof=1) / math.sqrt(n)) if n > 1 else 0.0
    gain = float(d.mean())
    bm = float(np.mean((np.array(model) - np.array(ys)) ** 2)); bb = float(np.mean((np.array(base) - np.array(ys)) ** 2))
    acc = float(np.mean([(p > 0.5) == bool(y) for p, y in zip(model, ys)]))
    verdict = "beats baseline" if gain > 2 * se and gain > 0 else ("marginal" if gain > 0 else "no edge")
    return {"name": name, "n": n, "ll_model": round(float(lm.mean()), 5), "ll_base": round(float(lb.mean()), 5), "brier_model": round(bm, 5), "brier_base": round(bb, 5),
            "gain": round(gain, 5), "se": round(se, 5), "accuracy": round(acc, 4), "verdict": verdict, "baseline": note, "calibration": _calib(model, ys)}


def summarize(rows: list[dict]) -> dict:
    S: dict = {}
    def collect(getter):
        ps, bs, ys = [], [], []
        for r in rows:
            for x in getter(r):
                if x is None or x.get("push"):
                    continue
                ps.append(x["p"]); bs.append(x["base"]); ys.append(x["y"])
        return ps, bs, ys
    for key, nm, note in (("sog", "Shots on goal (line = his trailing average)", "a negative binomial at his 25-game average (shrunk toward the league)"),
                          ("blk", "Blocked shots (line = his trailing average)", "a negative binomial at his 25-game average (shrunk toward the league)"),
                          ("pts", "Points over 0.5", "a Poisson at his 25-game rate (shrunk toward the league)"), ("ast", "Assists over 0.5", "a Poisson at his 25-game rate (shrunk toward the league)"),
                          ("goal", "Anytime goal", "a Poisson at his 25-game rate (shrunk toward the league)")):
        ps, bs, ys = collect(lambda r, k=key: [s.get(k) for s in r.get("skaters", [])])
        if ys:
            S[key] = _cmp(nm, ps, bs, ys, note)
            if key in ("sog", "blk"):
                acts = [s[key]["act"] for r in rows for s in r.get("skaters", []) if s.get(key)]
                means = [s[key]["mean"] for r in rows for s in r.get("skaters", []) if s.get(key)]
                avgs = [s[key]["avg"] for r in rows for s in r.get("skaters", []) if s.get(key)]
                S[key]["mae_model"] = round(float(np.mean(np.abs(np.array(acts) - np.array(means)))), 3)
                S[key]["mae_recent_avg"] = round(float(np.mean(np.abs(np.array(acts) - np.array(avgs)))), 3)
    for key, nm, note in (("team_total", "Team total (line = trailing average)", "a Poisson at the team's 20-game average (shrunk toward the league)"),
                          ("ppg05", "Power-play goals over 0.5", "a Poisson at the team's 20-game rate (shrunk toward the league)"), ("ppg15", "Power-play goals over 1.5", "a Poisson at the team's 20-game rate (shrunk toward the league)")):
        ps, bs, ys = collect(lambda r, k=key: [r.get(k)])
        if ys:
            S[key] = _cmp(nm, ps, bs, ys, note)
    S["team_games"] = len(rows)
    S["skater_games"] = sum(len(r.get("skaters", [])) for r in rows)
    return S


def save(result: dict, path=None) -> None:
    path = path or DATA_DIR / "backtest_latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    slim = {k: v for k, v in result.items() if k != "rows"}
    path.write_text(json.dumps(slim, indent=1))
    (DATA_DIR / "backtest_rows.jsonl").write_text("\n".join(json.dumps(r) for r in result["rows"]))


__all__ = ["run", "summarize", "save"]
