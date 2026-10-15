"""Walk-forward validation, week by week.

For every regular-season week of each test season the profiles are rebuilt from games played before that
week only (earlier seasons plus earlier weeks), then every game of the week is simulated:

  * the model alone, against the closing spread, total and moneyline (does it know anything the market
    does not?), and the blend weight w = how much of the model's disagreement with the closing line to keep;
  * the market-anchored simulation, for the derived markets, each against a simple baseline:
      1H / 2H totals        vs the league rate at a line set at the market total times the league half share
      team field goals made vs the league rate (over 0.5 / 1.5 / 2.5)
      QB passing yards      vs a line at the quarterback's recent average (a coin flip)
      QB passing touchdowns vs a Poisson at the quarterback's recent rate
      anytime touchdown     vs each player's own recent touchdown rate
    scored by log loss (lower is better) and calibration by decile;
  * the key-number correction: how often each final margin happens versus how often the simulation says.

    python -m nfl backtest --seasons 2023 2024 2025 [--sims 30000] [--workers 4]

Results: data/nfl/backtest_latest.json (summary, shown on the page) and data/nfl/factors.json (blend
weights, key-number weights, factor switches).
"""
from __future__ import annotations

import json
import zlib
import math
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from .config import CFG, DATA_DIR, ModelConfig
from .features import build_profiles, primary_qb
from .ingest import load_games
from .markets import devig2, game_markets, anytime_td, over_under, pmf
from .model import run_game
from .players import candidates
from .props import player_props, prob_over

_GAMES: list[dict] = []
_SNAPS: dict = {}


def _init(seasons: list[int]):
    global _GAMES, _SNAPS
    from .ingest import load_snaps
    _GAMES = load_games(seasons)
    _SNAPS = load_snaps(seasons)


def ll(p: float, y: int) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))


def _row_for(g: dict) -> dict:
    row = {k: g.get(k) for k in ("home", "away", "season", "week", "date", "roof", "temp", "wind", "rest", "div", "location", "lines", "time")}
    qb = {}
    for side, t in (("home", g["home"]), ("away", g["away"])):
        sid = ((g.get("qb") or {}).get(side) or {}).get("id") or ""
        qid = sid if sid in (g["qbs"].get(t) or {}) else (primary_qb(g, t) or sid)
        qb[side] = {"id": qid, "name": ((g["qbs"].get(t) or {}).get(qid) or {}).get("name", "")}
    row["qb"] = qb
    row["kicker"] = {"home": g["kicker"].get(g["home"], ""), "away": g["kicker"].get(g["away"], "")}
    return row


def run_week(args) -> dict:
    season, week, sims, cfg_over = args
    over = dict(cfg_over or {})
    n_pure = int(over.pop("_sims_pure", sims)); anchor_n = int(over.pop("_anchor_n", 20_000))
    cfg = ModelConfig(**{**CFG.__dict__, **over})
    train = [g for g in _GAMES if (season - 3 <= g["season"] < season) or (g["season"] == season and g["week"] < week)]
    test = [g for g in _GAMES if g["season"] == season and g["week"] == week]
    if not test or not train:
        return {"rows": []}
    P = build_profiles(train, season, cfg, snaps=_SNAPS)
    lt = P.league
    h1_share = lt.h1_share
    rows = []
    # each player's game log before this week (for the trailing-average lines)
    g_hist_players: dict[str, list] = {}
    for gg in train:
        for t in (gg["home"], gg["away"]):
            for pid, st in gg["players"].get(t, {}).items():
                g_hist_players.setdefault(pid, []).append(st)
    for g in test:
        row = _row_for(g)
        try:
            run = run_game(P, row, cfg, n=sims, n_pure=n_pure, seed=zlib.crc32(g["game_id"].encode()) % 100000, blend={"margin": 0.0, "total": 0.0},
                           keep_pure=True, anchor_n=anchor_n)
        except Exception as e:  # noqa: BLE001
            rows.append({"game_id": g["game_id"], "error": str(e)})
            continue
        r = run.sim; pure = run.pure
        L = g["lines"] or {}
        margin = g["hs"] - g["as"]; total = g["hs"] + g["as"]
        h1 = sum(g["q"]["home"][:2]) + sum(g["q"]["away"][:2]); h2 = total - h1
        out = {"game_id": g["game_id"], "season": season, "week": week, "home": g["home"], "away": g["away"], "margin": margin, "total": total,
               "h1": h1, "h2": h2, "spread": L.get("spread"), "total_line": L.get("total"),
               "model_margin": round(run.model_margin, 2), "model_total": round(run.model_total, 2)}
        # --- the model alone vs the closing line
        pm = pure.margin; pt = pure.total
        out["model_home_win"] = round(float((pm > 0).mean() / max(1e-9, 1 - (pm == 0).mean())), 4)
        ph, pa = devig2(L.get("home_ml"), L.get("away_ml"))
        out["mkt_home_win"] = round(ph, 4) if ph is not None else None
        if L.get("spread") is not None:
            s = L["spread"]
            cov = float((pm > s).mean()); push = float((pm == s).mean())
            out["model_cover"] = round(cov / max(1e-9, 1 - push), 4)
            out["home_covered"] = None if margin == s else int(margin > s)
            out["home_spread_odds"] = L.get("home_spread_odds"); out["away_spread_odds"] = L.get("away_spread_odds")
        if L.get("total") is not None:
            t = L["total"]
            ov = float((pt > t).mean()); push = float((pt == t).mean())
            out["model_over"] = round(ov / max(1e-9, 1 - push), 4)
            out["went_over"] = None if total == t else int(total > t)
            out["over_odds"] = L.get("over_odds"); out["under_odds"] = L.get("under_odds")
        # --- anchored derived markets
        mk = game_markets(r, L)
        out["anch_margin_pmf"] = mk["dist"]["margin"]
        if L.get("total") is not None:
            l1 = math.floor(L["total"] * h1_share) + 0.5
            l2 = math.floor(L["total"] * (1 - h1_share)) + 0.5
            out["h1_line"] = l1; out["h2_line"] = l2
            out["p_h1_over"] = round(float((r.h1.sum(axis=1) > l1).mean()), 4)
            out["p_h2_over"] = round(float((r.h2.sum(axis=1) > l2).mean()), 4)
        fg = {}
        for i, side in enumerate(("home", "away")):
            t = g[side]
            made = sum(1 for k in g["fg"].get(t, []) if k["r"] == "made")
            fg[side] = {"made": made, "p": [mk["fg"][side]["over0.5"], mk["fg"][side]["over1.5"], mk["fg"][side]["over2.5"]]}
        out["fg"] = fg
        # quarterbacks
        qbo = {}
        for i, side in enumerate(("home", "away")):
            t = g[side]; qid = row["qb"][side]["id"]
            q = (g["qbs"].get(t) or {}).get(qid)
            if not q or q["db"] < 15:
                continue
            qp = P.qbs.get(qid)
            last = (qp.last_games[-10:] if qp else [])
            n_l = len(last)
            avg_y = (sum(x["yds"] for x in last) + 3 * 215.0) / (n_l + 3)
            avg_td = (sum(x["td"] for x in last) + 4 * 1.35) / (n_l + 4)
            line = math.floor(avg_y) + 0.5
            y = r.yds[:, i]; tdn = r.ptd[:, i]
            qbo[side] = {"yds": q["yds"], "td": q["td"], "line": line, "p_over": round(float((y > line).mean()), 4), "median": round(float(np.median(y)), 1),
                         "trail": round(avg_y, 1), "p_td05": round(float((tdn >= 1).mean()), 4), "p_td15": round(float((tdn >= 2).mean()), 4),
                         "p_td25": round(float((tdn >= 3).mean()), 4), "base_td05": round(1 - math.exp(-avg_td), 4),
                         "base_td15": round(1 - math.exp(-avg_td) * (1 + avg_td), 4), "base_td25": round(1 - math.exp(-avg_td) * (1 + avg_td + avg_td ** 2 / 2), 4),
                         "starts_prior": n_l}
        out["qb"] = qbo
        # anytime touchdown
        atd = []
        for i, side in enumerate(("home", "away")):
            t = g[side]
            played = {pid for pid, s in g["players"].get(t, {}).items() if s["car"] + s["tgt"] > 0}
            cands = candidates(P, t, played=played, cfg=cfg)
            res = anytime_td(r, i, cands)
            scored = {pid for pid, s in g["players"].get(t, {}).items() if s["rtd"] + s["rectd"] > 0}
            for c in res:
                pp = P.players.get(c["id"])
                rate = ((pp.rtd + pp.rectd) / pp.w) if pp and pp.w > 0 else 0.0
                wgt = pp.w if pp else 0.0
                base_rate = (rate * wgt + 0.25 * 3) / (wgt + 3)
                atd.append({"p": c["p"], "base": round(1 - math.exp(-base_rate), 4), "y": int(c["id"] in scored)})
            team_tds = g["team"][t]["td_pass"] + g["team"][t]["td_rush"]
            covered = sum(g["players"][t][pid]["rtd"] + g["players"][t][pid]["rectd"] for pid in {c["id"] for c in cands} if pid in g["players"][t])
            out.setdefault("td_cover", []).append((covered, team_tds))
        out["atd"] = atd
        # yardage props at a line set at the player's recent average (coin-flip baseline), players with a real role only
        yp = []
        for i, side in enumerate(("home", "away")):
            t = g[side]
            played = {pid for pid, s in g["players"].get(t, {}).items() if s["car"] + s["tgt"] > 0}
            cands = candidates(P, t, played=played, cfg=cfg)
            for x in player_props(P, row, side, r, cands, cfg=cfg):
                pp = P.players.get(x["id"]); act = g["players"][t].get(x["id"])
                if pp is None or act is None or len(pp.recent) < 4:
                    continue
                hist = [h for h in g_hist_players.get(x["id"], [])][-8:]
                for key, akey, floor in (("rec_yds", "recyds", 20), ("rush_yds", "ryds", 20), ("recs", "rec", 2)):
                    d = x.get(key)
                    if not d or len(hist) < 4:
                        continue
                    avg = sum(h[akey] for h in hist) / len(hist)
                    if avg < floor:
                        continue
                    line = (math.floor(avg) + 0.5)
                    po, pu, un = prob_over(d, line)
                    yp.append({"k": key, "p_over": round(po / max(1e-9, 1 - pu), 4), "y": int(act[akey] > line), "push": int(act[akey] == line), "median": d["q"][2], "avg": round(avg, 1), "act": act[akey]})
        out["yprops"] = yp
        rows.append(out)
    return {"rows": rows}


def _calib(ps: list[float], ys: list[int], bins: int = 10) -> list[dict]:
    if not ps:
        return []
    a = np.array(ps); y = np.array(ys)
    qs = np.quantile(a, np.linspace(0, 1, bins + 1))
    out = []
    for i in range(bins):
        m = (a >= qs[i]) & ((a < qs[i + 1]) if i < bins - 1 else (a <= qs[i + 1]))
        if m.sum():
            out.append({"p": round(float(a[m].mean()), 4), "hit": round(float(y[m].mean()), 4), "n": int(m.sum())})
    return out


def _cmp(name: str, model: list[float], base: list[float], ys: list[int], note: str) -> dict:
    if not ys:
        return {"market": name, "n": 0}
    lm = float(np.mean([ll(p, y) for p, y in zip(model, ys)]))
    lb = float(np.mean([ll(p, y) for p, y in zip(base, ys)]))
    # paired standard error of the difference
    d = np.array([ll(p, y) - ll(b, y) for p, b, y in zip(model, base, ys)])
    se = float(d.std(ddof=1) / math.sqrt(len(d))) if len(d) > 1 else float("nan")
    gain = lb - lm
    verdict = "beats baseline" if gain > 2 * se else ("marginal" if gain > 0 else "no edge")
    bm = float(np.mean([(p - y) ** 2 for p, y in zip(model, ys)])); bb = float(np.mean([(b - y) ** 2 for b, y in zip(base, ys)]))
    acc = float(np.mean([(p >= 0.5) == (y == 1) for p, y in zip(model, ys)]))
    return {"market": name, "n": len(ys), "ll_model": round(lm, 5), "ll_base": round(lb, 5), "gain": round(gain, 5), "se": round(se, 5),
            "brier_model": round(bm, 5), "brier_base": round(bb, 5), "accuracy": round(acc, 4),
            "verdict": verdict, "hit_rate": round(float(np.mean(ys)), 4), "mean_p": round(float(np.mean(model)), 4),
            "calibration": _calib(model, ys), "baseline": note}


def _bet_record(ps: list[float], ys: list, odds_a: list, odds_b: list, threshold: float) -> dict:
    """Bet the model's side when its probability clears `threshold` (either side) at the listed odds (-110 when missing)."""
    from .markets import american_to_decimal
    n = w = l = 0
    pnl = 0.0
    for p, y, oa, ob in zip(ps, ys, odds_a, odds_b):
        if y is None:
            continue
        if p >= threshold:
            dec = american_to_decimal(oa) or 1.909
            n += 1; w += y == 1; l += y == 0
            pnl += (dec - 1) if y == 1 else -1
        elif p <= 1 - threshold:
            dec = american_to_decimal(ob) or 1.909
            n += 1; w += y == 0; l += y == 1
            pnl += (dec - 1) if y == 0 else -1
    return {"threshold": threshold, "bets": n, "won": w, "lost": l, "win_rate": round(w / n, 4) if n else None, "roi": round(pnl / n, 4) if n else None}


def summarize(rows: list[dict]) -> dict:
    rows = [r for r in rows if "error" not in r]
    S: dict = {"games": len(rows)}
    # --- game lines: model vs market
    ml = [(r["model_home_win"], r["mkt_home_win"], int(r["margin"] > 0)) for r in rows if r.get("mkt_home_win") is not None and r["margin"] != 0]
    if ml:
        S["moneyline"] = _cmp("Moneyline (model alone vs de-vigged closing line)", [a for a, _, _ in ml], [b for _, b, _ in ml], [y for _, _, y in ml],
                              "the closing moneyline, vig removed")
    sp = [r for r in rows if r.get("home_covered") is not None and r.get("model_cover") is not None]
    if sp:
        S["spread"] = _cmp("Spread (model alone vs 50/50 at the closing spread)", [r["model_cover"] for r in sp], [0.5] * len(sp), [r["home_covered"] for r in sp],
                           "a coin flip at the closing spread")
        S["spread"]["bets"] = [_bet_record([r["model_cover"] for r in sp], [r["home_covered"] for r in sp], [r.get("home_spread_odds") for r in sp],
                                           [r.get("away_spread_odds") for r in sp], th) for th in (0.53, 0.55, 0.58, 0.6)]
    to = [r for r in rows if r.get("went_over") is not None and r.get("model_over") is not None]
    if to:
        S["total"] = _cmp("Total (model alone vs 50/50 at the closing total)", [r["model_over"] for r in to], [0.5] * len(to), [r["went_over"] for r in to],
                          "a coin flip at the closing total")
        S["total"]["bets"] = [_bet_record([r["model_over"] for r in to], [r["went_over"] for r in to], [r.get("over_odds") for r in to],
                                          [r.get("under_odds") for r in to], th) for th in (0.53, 0.55, 0.58, 0.6)]
    # blend weights: actual - line = w (model - line) + noise
    for key, act, line, mod in (("margin", "margin", "spread", "model_margin"), ("total", "total", "total_line", "model_total")):
        xs = np.array([r[mod] - r[line] for r in rows if r.get(line) is not None])
        ys = np.array([r[act] - r[line] for r in rows if r.get(line) is not None])
        if len(xs) > 30 and xs.var() > 0:
            w = float((xs * ys).sum() / (xs * xs).sum())
            resid = ys - w * xs
            se = float(math.sqrt(resid.var() / (xs * xs).sum()))
            S.setdefault("blend", {})[key] = {"w": round(w, 4), "se": round(se, 4), "n": int(len(xs)),
                                              "mae_line": round(float(np.abs(ys).mean()), 3), "mae_model": round(float(np.abs(ys - xs).mean()), 3)}
    # --- derived markets
    h1 = [r for r in rows if "p_h1_over" in r]
    if h1:
        base1 = float(np.mean([r["h1"] > r["h1_line"] for r in h1]))
        base2 = float(np.mean([r["h2"] > r["h2_line"] for r in h1]))
        S["h1_total"] = _cmp("1st half total (line = market total x league 1H share)", [r["p_h1_over"] for r in h1], [base1] * len(h1),
                             [int(r["h1"] > r["h1_line"]) for r in h1], "the hit rate of that line over the same games (hindsight constant)")
        S["h2_total"] = _cmp("2nd half total incl. OT (line = market total x league 2H share)", [r["p_h2_over"] for r in h1], [base2] * len(h1),
                             [int(r["h2"] > r["h2_line"]) for r in h1], "the hit rate of that line over the same games (hindsight constant)")
    fgp = {0: [], 1: [], 2: []}; fgy = {0: [], 1: [], 2: []}
    for r in rows:
        for side in ("home", "away"):
            f = r["fg"][side]
            for j in range(3):
                fgp[j].append(f["p"][j]); fgy[j].append(int(f["made"] > j))
    for j, nm in ((0, "0.5"), (1, "1.5"), (2, "2.5")):
        if fgy[j]:
            base = float(np.mean(fgy[j]))
            S[f"fg_over{nm}"] = _cmp(f"Team field goals made over {nm}", fgp[j], [base] * len(fgy[j]), fgy[j], "the league hit rate over the same games (hindsight constant)")
    qp, qy, qmed, qtrail, qact = [], [], [], [], []
    td = {k: ([], [], []) for k in ("05", "15", "25")}
    for r in rows:
        for side, q in (r.get("qb") or {}).items():
            if q["yds"] == q["line"]:
                continue
            qp.append(q["p_over"]); qy.append(int(q["yds"] > q["line"]))
            qmed.append(q["median"]); qtrail.append(q["trail"]); qact.append(q["yds"])
            for k, thr in (("05", 0), ("15", 1), ("25", 2)):
                td[k][0].append(q[f"p_td{k}"]); td[k][1].append(q[f"base_td{k}"]); td[k][2].append(int(q["td"] > thr))
    if qy:
        S["qb_yards"] = _cmp("QB passing yards (line = his recent average)", qp, [0.5] * len(qy), qy, "a coin flip at the quarterback's recent average")
        S["qb_yards"]["mae_model_median"] = round(float(np.mean(np.abs(np.array(qact) - np.array(qmed)))), 2)
        S["qb_yards"]["mae_recent_avg"] = round(float(np.mean(np.abs(np.array(qact) - np.array(qtrail)))), 2)
    for k, nm in (("05", "0.5"), ("15", "1.5"), ("25", "2.5")):
        if td[k][2]:
            S[f"qb_td_over{nm}"] = _cmp(f"QB passing touchdowns over {nm}", td[k][0], td[k][1], td[k][2], "a Poisson at the quarterback's recent touchdown rate")
    for key, nm in (("rec_yds", "Receiving yards"), ("rush_yds", "Rushing yards"), ("recs", "Receptions")):
        ps = [x["p_over"] for r in rows for x in r.get("yprops", []) if x["k"] == key and not x["push"]]
        ys = [x["y"] for r in rows for x in r.get("yprops", []) if x["k"] == key and not x["push"]]
        if ys:
            S[key] = _cmp(f"{nm} (line = the player's recent average)", ps, [0.5] * len(ys), ys, "a coin flip at the player's recent average")
            S[key]["mae_model_median"] = round(float(np.mean([abs(x["act"] - x["median"]) for r in rows for x in r.get("yprops", []) if x["k"] == key])), 2)
            S[key]["mae_recent_avg"] = round(float(np.mean([abs(x["act"] - x["avg"]) for r in rows for x in r.get("yprops", []) if x["k"] == key])), 2)
    ap, ab, ay = [], [], []
    for r in rows:
        for a in r.get("atd", []):
            ap.append(a["p"]); ab.append(a["base"]); ay.append(a["y"])
    if ay:
        S["anytime_td"] = _cmp("Anytime touchdown scorer", ap, ab, ay, "each player's own recent touchdown rate")
    cov = [c for r in rows for c in r.get("td_cover", [])]
    if cov:
        S["td_coverage"] = round(sum(a for a, _ in cov) / max(1, sum(b for _, b in cov)), 4)
    # --- key numbers: actual |margin| frequency vs the anchored simulation's
    acc = np.zeros(41); act = np.zeros(41)
    for r in rows:
        off, vals = r["anch_margin_pmf"]
        for i, p in enumerate(vals):
            m = abs(off + i)
            if m <= 40:
                acc[m] += p
        if abs(r["margin"]) <= 40:
            act[abs(r["margin"])] += 1
    n = len(rows)
    if n:
        S["key_numbers"] = {str(k): {"actual": round(act[k] / n, 4), "sim": round(acc[k] / n, 4)} for k in range(0, 22)}
    return S


def key_weights(S: dict, k_pseudo: float = 20.0) -> dict:
    """Weights for |margin| = 0..21: (actual + k * sim) / ((1 + k/n) * sim) style shrinkage toward 1."""
    kn = S.get("key_numbers") or {}
    n = S.get("games", 0)
    out = {}
    for k, v in kn.items():
        a, s = v["actual"] * n, v["sim"] * n
        if s <= 0:
            continue
        w = (a + k_pseudo) / (s + k_pseudo)
        out[k] = round(float(w), 4)
    return out


def key_number_check(rows: list[dict], k: float = 20.0) -> dict:
    """Walk-forward test of the key-number correction: weights from earlier test seasons applied to the last one,
    scored by the log loss of cover / push / miss at the closing spread. Returns the weights and whether they helped."""
    rows = [r for r in rows if "error" not in r and r.get("anch_margin_pmf")]
    seasons = sorted({r["season"] for r in rows})
    if len(seasons) < 2:
        return {"use": False, "reason": "needs two seasons"}

    def weights(rs):
        acc = np.zeros(41); act = np.zeros(41)
        for r in rs:
            off, vals = r["anch_margin_pmf"]
            for i, p in enumerate(vals):
                if abs(off + i) <= 40:
                    acc[abs(off + i)] += p
            if abs(r["margin"]) <= 40:
                act[abs(r["margin"])] += 1
        return {m: float((act[m] + k) / (acc[m] + k)) for m in range(22)}

    def score(rs, w):
        ll = []
        for r in rs:
            if r.get("spread") is None:
                continue
            off, vals = r["anch_margin_pmf"]
            v = np.arange(off, off + len(vals)); p = np.array(vals, dtype=float)
            if w:
                p = p * np.array([w.get(abs(int(x)), 1.0) for x in v]); p /= p.sum()
            s, y = r["spread"], r["margin"]
            pr = p[v > s].sum() if y > s else (p[v == s].sum() if y == s else p[v < s].sum())
            ll.append(-math.log(max(float(pr), 1e-4)))
        return float(np.mean(ll)) if ll else float("nan")

    test = seasons[-1]
    train = [r for r in rows if r["season"] < test]; te = [r for r in rows if r["season"] == test]
    w = weights(train)
    a, b = score(te, None), score(te, w)
    return {"use": b < a - 1e-4, "ll_without": round(a, 5), "ll_with": round(b, 5), "test_season": test,
            "weights": {str(m): round(v, 4) for m, v in weights(rows).items()}}


def backtest(seasons: list[int], sims: int = 20_000, workers: int = 2, cfg_over: dict | None = None, weeks: list[int] | None = None) -> dict:
    t0 = time.time()
    all_seasons = sorted({s - k for s in seasons for k in range(0, 4)})
    tasks = [(s, w, sims, cfg_over) for s in seasons for w in (weeks or range(1, 19))]
    rows: list[dict] = []
    with ProcessPoolExecutor(max_workers=workers, initializer=_init, initargs=(all_seasons,)) as ex:
        for res in ex.map(run_week, tasks):
            rows.extend(res["rows"])
    by_season = {}
    for s in seasons:
        by_season[str(s)] = summarize([r for r in rows if r.get("season") == s])
    pooled = summarize(rows)
    return {"seasons": seasons, "sims": sims, "minutes": round((time.time() - t0) / 60, 1), "pooled": pooled, "by_season": by_season,
            "cfg": cfg_over or {}, "rows": rows}


def resummarize(path=None) -> dict:
    """Recompute the summaries from the saved per-game rows (no new simulations)."""
    rows = [json.loads(l) for l in (DATA_DIR / "backtest_rows.jsonl").open()]
    old = json.loads((path or DATA_DIR / "backtest_latest.json").read_text())
    seasons = old.get("seasons") or sorted({r["season"] for r in rows if "season" in r})
    res = {**{k: v for k, v in old.items() if k not in ("pooled", "by_season")}, "pooled": summarize(rows),
           "by_season": {str(s): summarize([r for r in rows if r.get("season") == s]) for s in seasons}, "rows": rows}
    return res


def save(result: dict, path=None) -> None:
    path = path or DATA_DIR / "backtest_latest.json"
    slim = {k: v for k, v in result.items() if k != "rows"}
    slim["generated_utc"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    path.write_text(json.dumps(slim, indent=1))
    rows_path = DATA_DIR / "backtest_rows.jsonl"
    with rows_path.open("w") as fh:
        for r in result["rows"]:
            fh.write(json.dumps(r, separators=(",", ":")) + "\n")


__all__ = ["backtest", "summarize", "save", "key_weights", "run_week"]
