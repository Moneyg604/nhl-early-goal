"""Build one week's payload: research every game, simulate it, price every market, pick the leans.

    payload = build_week(season, week)       # dict, rendered by report.py and published by site.py
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone

import numpy as np

from .config import CFG, DATA_DIR, MODEL_VERSION, ModelConfig
from .features import Profiles, build_profiles, game_context_keys
from .ingest import load_games, load_schedule
from .markets import american_to_decimal, anytime_td, devig2, game_markets
from .model import load_blend, load_key_numbers, run_game
from .players import candidates
from .week import load_reference, week_rows


def _r(x, n=3):
    return None if x is None else round(float(x), n)


def head_to_head(games: list[dict], a: str, b: str, k: int = 5) -> list[dict]:
    out = []
    for g in reversed(games):
        if {g["home"], g["away"]} == {a, b}:
            out.append({"date": g["date"], "home": g["home"], "away": g["away"], "hs": g["hs"], "as": g["as"],
                        "h1": sum(g["q"]["home"][:2]) + sum(g["q"]["away"][:2]),
                        "fg": {g["home"]: sum(1 for x in g["fg"].get(g["home"], []) if x["r"] == "made"),
                               g["away"]: sum(1 for x in g["fg"].get(g["away"], []) if x["r"] == "made")},
                        "spread": (g.get("lines") or {}).get("spread"), "total": (g.get("lines") or {}).get("total")})
            if len(out) >= k:
                break
    return out


def team_dossier(P: Profiles, t: str, games: list[dict], cfg: ModelConfig) -> dict:
    tp = P.teams.get(t)
    if tp is None:
        return {"team": t}
    d = tp.describe(cfg, P.league)
    cur = [g for g in games if g["season"] == P.season and t in (g["home"], g["away"])]
    ats = [0, 0, 0]; ou = [0, 0, 0]
    for g in cur:
        L = g.get("lines") or {}
        s = L.get("spread"); tot = L.get("total")
        if s is not None:
            m = (g["hs"] - g["as"]) if g["home"] == t else (g["as"] - g["hs"])
            line = s if g["home"] == t else -s
            ats[0 if m > line else (2 if m == line else 1)] += 1
        if tot is not None:
            T = g["hs"] + g["as"]
            ou[0 if T > tot else (2 if T == tot else 1)] += 1
    d["ats"] = f"{ats[0]}-{ats[1]}" + (f"-{ats[2]}" if ats[2] else "")
    d["ou"] = f"{ou[0]}-{ou[1]}" + (f"-{ou[2]}" if ou[2] else "")
    return d


def tier_for(P: Profiles, row: dict, run) -> tuple[str, list[str]]:
    why = []
    gh, ga = P.teams.get(row["home"]), P.teams.get(row["away"])
    n_min = min(gh.games_cur if gh else 0, ga.games_cur if ga else 0)
    if n_min < CFG.tier_a_min_games:
        why.append(f"only {n_min} games this season for one team (profiles lean on last season)")
    for side, sb in (("home", run.home), ("away", run.away)):
        if (row.get("qb_uncertain") or {}).get(side):
            why.append(f"{sb.team}: starting quarterback uncertain (sources disagree)")
        if "qb_change" in sb.parts:
            why.append(f"{sb.team}: quarterback change ({sb.qb_name})")
        if not sb.qb_id or sb.qb_id not in P.qbs:
            why.append(f"{sb.team}: starting quarterback has no NFL passing record in the data")
    if (row.get("lines") or {}).get("spread") is None:
        why.append("no market line yet (model alone)")
    if not why:
        return "A", why
    if any("no NFL passing record" in w or "no market line" in w or "uncertain" in w for w in why):
        return "C", why
    return "B", why


def build_week(season: int, week: int, cfg: ModelConfig = CFG, sims: int | None = None, with_weather: bool = True,
               games: list[dict] | None = None) -> dict:
    t0 = time.time()
    sched = load_schedule()
    games = games if games is not None else load_games([season - 3, season - 2, season - 1, season])
    # profiles from everything played before this week (the current week's finished games stay out, so the
    # numbers on the page are the pre-game numbers even after Sunday)
    train = [g for g in games if g["season"] < season or (g["season"] == season and g["week"] < week)]
    P = build_profiles(train, season, cfg)
    ref = load_reference(season)
    rows = week_rows(sched, season, week, P, ref, with_weather=with_weather)
    blend = load_blend(); keyw = load_key_numbers()
    from .odds import for_game, load as load_odds
    odds = load_odds()
    played = {g["game_id"]: g for g in games if g["season"] == season and g["week"] == week}
    out_games = []
    samples: dict[str, str] = {}
    for row in rows:
        run = run_game(P, row, cfg, n=sims or cfg.sims, blend=blend)
        mk = game_markets(run.sim, row["lines"], keyw)
        g = {k: row[k] for k in ("game_id", "season", "week", "home", "away", "date", "time", "weekday", "kickoff_utc", "stadium", "location",
                                 "roof", "surface", "div", "rest", "lines", "score", "espn", "weather", "temp", "wind", "coach", "referee")}
        g["markets"] = mk
        g["odds"] = for_game(odds, row["home"], row["away"], row.get("kickoff_utc"))
        samples[row["game_id"]] = sample_blob(run.sim, row["lines"])
        g["model"] = {"margin": _r(run.model_margin, 2), "total": _r(run.model_total, 2), "home_win": _r(run.model_home_win, 4),
                      "target_margin": _r(run.target_margin, 2), "target_total": _r(run.target_total, 2), "anchor": run.anchor,
                      "blend": blend}
        ph, pa = devig2(row["lines"].get("home_ml"), row["lines"].get("away_ml"))
        g["market_home_win"] = _r(ph, 4)
        # inputs, with the arithmetic
        g["inputs"] = {}
        for side, sb in (("home", run.home), ("away", run.away)):
            si = sb.inputs
            g["inputs"][side] = {"team": sb.team, "parts": {k: [round(x, 4) for x in v] for k, v in sb.parts.items()},
                                 "total": [round(float(sum(v[i] for v in sb.parts.values())), 4) for i in range(3)],
                                 "pace": _r(si.pace, 3), "make_shift": _r(si.make_shift, 3), "xp": _r(si.xp, 3), "db_mult": _r(si.db_mult, 3),
                                 "ypdb_mult": _r(si.ypdb_mult, 3), "p_pass_td": _r(si.p_pass_td, 3), "notes": sb.notes,
                                 "context": game_context_keys(row, side)}
        # quarterbacks, kickers
        g["qb"] = {}
        g["kicker"] = {}
        for side, sb in (("home", run.home), ("away", run.away)):
            q = row["qb"][side]
            qp = P.qbs.get(sb.qb_id)
            g["qb"][side] = {**q, "profile": qp.describe(P.league, cfg) if qp else None, "change": "qb_change" in sb.parts}
            kp = P.kickers.get(sb.kicker)
            g["kicker"][side] = {"id": sb.kicker, "name": (row.get("kicker_names") or {}).get(side, ""), "profile": kp.describe(cfg, P.league) if kp else None}
        # anytime touchdown
        g["anytime"] = {}
        for i, side in enumerate(("home", "away")):
            t = row[side]
            active = set(row["active"][side]) or None
            cands = candidates(P, t, available=active, out=set(row["out"][side]), positions=row["positions"], cfg=cfg)
            res = anytime_td(run.sim, i, cands)
            qn = set(row["questionable"][side])
            g["anytime"][side] = [{"id": c["id"], "name": (row.get("names") or {}).get(c["id"]) or c["name"], "short": c["name"], "pos": c["pos"], "p": c["p"], "fair": c["fair"], "q": c["id"] in qn,
                                   "rec_share": round(c["rec_share"], 3), "rush_share": round(c["rush_share"], 3), "tgt_share": c["tgt_share"],
                                   "car_share": c["car_share"], "rz_share": c["rz_share"], "games": c["games"], "td_games": c["td_games"],
                                   "recent": c["recent"]} for c in res if c["p"] >= 0.04][:14]
        g["injuries"] = row["injuries"]
        g["research"] = {"home": team_dossier(P, row["home"], train, cfg), "away": team_dossier(P, row["away"], train, cfg),
                         "h2h": head_to_head(train, row["home"], row["away"])}
        tier, why = tier_for(P, row, run)
        g["tier"] = tier; g["tier_why"] = why
        # results (finished games): actuals for grading the derived markets
        pg = played.get(row["game_id"])
        if pg is not None:
            g["actual"] = actuals(pg)
        elif row["score"]:
            g["actual"] = {"hs": row["score"]["home"], "as": row["score"]["away"]}
        out_games.append(g)
    payload = {
        "sport": "nfl", "season": season, "week": week,
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "meta": {"model_version": MODEL_VERSION, "sims": sims or cfg.sims, "data_through": P.data_through, "league": P.league.describe(),
                 "new_qb": P.new_qb, "switches": {k: getattr(cfg, k) for k in ("use_home", "use_rest", "use_roof", "use_wind", "use_qb_blend", "use_half_shape", "use_division")},
                 "blend": blend, "key_numbers": keyw, "tested": _tested(), "seconds": round(time.time() - t0, 1),
                 "cfg": {"prior_season_weights": list(cfg.prior_season_weights), "k_drive_team": cfg.k_drive_team, "k_drive_fg": cfg.k_drive_fg,
                         "k_kicker": cfg.k_kicker, "anchor_fg_frac": cfg.anchor_fg_frac, "league_seasons": cfg.league_seasons}},
        "games": out_games,
    }
    payload["picks"] = picks(payload)
    payload["validation"] = _validation()
    payload["_samples"] = {"fields": SAMPLE_FIELDS, "bytes": 17, "n": SAMPLE_N, "games": samples}
    return payload


SAMPLE_N = 3000
SAMPLE_FIELDS = "hp ap h1h h1a fgh fga tdh tda rth rta ot | yh ya | w"


def sample_blob(sim, lines: dict, n: int = SAMPLE_N, seed: int = 5) -> str:
    """A random subset of the simulated games, packed for the page's same-game parlay pricing:
    11 unsigned bytes (points home/away, first-half points home/away, field goals made home/away, touchdown
    passes home/away, rushing touchdowns home/away, overtime), two signed 16-bit passing-yard totals, and the
    16-bit market weight x 10000 (see markets.ml_weights). 17 bytes per game, base64."""
    import base64

    from .markets import ml_weights
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(sim.pts), size=min(n, len(sim.pts)), replace=False)
    w, _ = ml_weights(sim, lines)
    w = np.ones(len(sim.pts)) if w is None else w
    u8 = np.stack([sim.pts[idx, 0], sim.pts[idx, 1], sim.h1[idx, 0], sim.h1[idx, 1], sim.fgm[idx, 0], sim.fgm[idx, 1], sim.ptd[idx, 0], sim.ptd[idx, 1],
                   sim.rtd[idx, 0], sim.rtd[idx, 1], sim.ot[idx].astype(int)], axis=1).clip(0, 255).astype(np.uint8)
    i16 = np.stack([sim.yds[idx, 0], sim.yds[idx, 1]], axis=1).round().clip(-32000, 32000).astype("<i2")
    u16 = (w[idx] * 10000).round().clip(0, 65535).astype("<u2").reshape(-1, 1)
    rows = np.concatenate([u8.view(np.uint8), i16.view(np.uint8).reshape(len(idx), 4), u16.view(np.uint8).reshape(len(idx), 2)], axis=1)
    return base64.b64encode(rows.astype(np.uint8).tobytes()).decode()


def actuals(g: dict) -> dict:
    h1h, h1a = sum(g["q"]["home"][:2]), sum(g["q"]["away"][:2])
    qb = {}
    for side in ("home", "away"):
        t = g[side]
        q = g["qbs"].get(t) or {}
        if q:
            pid = max(q, key=lambda k: q[k]["db"])
            qb[side] = {"id": pid, "name": q[pid]["name"], "yds": q[pid]["yds"], "td": q[pid]["td"]}
    scorers = sorted({pid for t in (g["home"], g["away"]) for pid, s in g["players"].get(t, {}).items() if s["rtd"] + s["rectd"] > 0})
    return {"hs": g["hs"], "as": g["as"], "h1": [h1h, h1a], "ot": g.get("ot", 0),
            "fg": {"home": sum(1 for k in g["fg"].get(g["home"], []) if k["r"] == "made"), "away": sum(1 for k in g["fg"].get(g["away"], []) if k["r"] == "made")},
            "qb": qb, "scorers": scorers}


def _tested() -> list:
    try:
        return json.loads((DATA_DIR / "factors.json").read_text()).get("tested") or []
    except Exception:  # noqa: BLE001
        return []


def _validation() -> dict | None:
    f = DATA_DIR / "backtest_latest.json"
    if not f.exists():
        return None
    try:
        d = json.loads(f.read_text())
    except json.JSONDecodeError:
        return None
    slim = {"seasons": d.get("seasons"), "generated_utc": d.get("generated_utc"), "sims": d.get("sims"), "pooled": {}, "by_season": {}}
    for k, v in (d.get("pooled") or {}).items():
        slim["pooled"][k] = v
    for s, S in (d.get("by_season") or {}).items():
        slim["by_season"][s] = {k: ({kk: vv for kk, vv in v.items() if kk not in ("calibration",)} if isinstance(v, dict) else v)
                                for k, v in S.items() if k != "key_numbers"}
    return slim


def _verdict(key: str) -> str | None:
    v = _validation()
    if not v:
        return None
    m = (v.get("pooled") or {}).get(key)
    return m.get("verdict") if isinstance(m, dict) else None


def picks(payload: dict) -> dict:
    """Deterministic leans per market (the page grades them after the games)."""
    G = payload["games"]
    lt = payload["meta"]["league"]
    h1s = lt.get("h1_share", 0.5)
    out: dict[str, list] = {}

    def add(key, items, n=3):
        out[key] = sorted(items, key=lambda x: -x["score"])[:n]

    ml, sp, to, h1, h2, fg, qy, qt, atd = [], [], [], [], [], [], [], [], []
    for g in G:
        mk = g["markets"]; L = g["lines"] or {}
        mu = f'{g["away"]} @ {g["home"]}'
        side = "home" if mk["ml"]["home"] >= mk["ml"]["away"] else "away"
        p = mk["ml"][side]
        odds = american_to_decimal(L.get(f"{side}_ml"))
        ml.append({"game_id": g["game_id"], "mu": mu, "market": "ml", "side": side, "team": g[side], "p": p, "odds": odds,
                   "ev": round(p * odds - 1, 4) if odds else None, "score": p})
        if L.get("spread") is not None and g["model"]["margin"] is not None:
            # lean from the model alone (the anchored price equals the market by design)
            diff = g["model"]["margin"] - L["spread"]
            sp.append({"game_id": g["game_id"], "mu": mu, "market": "spread", "side": "home" if diff > 0 else "away", "line": L["spread"],
                       "model_margin": g["model"]["margin"], "edge_pts": round(diff, 2), "p": mk["spread"]["home_cover"] if diff > 0 else mk["spread"]["away_cover"],
                       "score": abs(diff)})
        if L.get("total") is not None and g["model"]["total"] is not None:
            diff = g["model"]["total"] - L["total"]
            to.append({"game_id": g["game_id"], "mu": mu, "market": "total", "side": "over" if diff > 0 else "under", "line": L["total"],
                       "model_total": g["model"]["total"], "edge_pts": round(diff, 2), "p": mk["total"]["over"] if diff > 0 else mk["total"]["under"],
                       "score": abs(diff)})
            for key, arr, share, lst in (("h1", "h1", h1s, h1), ("h2", "h2", 1 - h1s, h2)):
                line = math.floor(L["total"] * share) + 0.5
                off, vals = mk["dist"][arr]
                v = np.arange(off, off + len(vals)); pv = np.array(vals)
                po = float(pv[v > line].sum())
                s2 = "over" if po >= 0.5 else "under"
                lst.append({"game_id": g["game_id"], "mu": mu, "market": key, "side": s2, "line": line, "p": round(po if s2 == "over" else 1 - po, 4), "score": abs(po - 0.5)})
        for side in ("home", "away"):
            f = mk["fg"][side]
            po = f["over1.5"]
            fg.append({"game_id": g["game_id"], "mu": mu, "market": "fg", "team": g[side], "side_team": side, "side": "over" if po >= 0.5 else "under",
                       "line": 1.5, "p": round(po if po >= 0.5 else 1 - po, 4), "score": abs(po - 0.5)})
            q = (g.get("qb") or {}).get(side) or {}
            prof = q.get("profile") or {}
            qm = mk["qb"][side]
            last = prof.get("last_games") or []
            if last and q.get("name"):
                avg = (sum(x["yds"] for x in last) + 3 * 215) / (len(last) + 3)
                line = math.floor(avg) + 0.5
                off, vals = qm["yds_pmf5"]
                v = (np.arange(off, off + len(vals)) * 5.0); pv = np.array(vals)
                po = float(pv[v > line].sum())
                qy.append({"game_id": g["game_id"], "mu": mu, "market": "qb_yds", "team": g[side], "side_team": side, "qb": q["name"], "line": line,
                           "median": qm["yds_q"][3], "side": "over" if po >= 0.5 else "under", "p": round(max(po, 1 - po), 4), "score": abs(po - 0.5)})
                po2 = qm["td_over1.5"]
                qt.append({"game_id": g["game_id"], "mu": mu, "market": "qb_td", "team": g[side], "side_team": side, "qb": q["name"], "line": 1.5,
                           "side": "over" if po2 >= 0.5 else "under", "p": round(max(po2, 1 - po2), 4), "score": abs(po2 - 0.5)})
            for a in (g.get("anytime") or {}).get(side, [])[:6]:
                atd.append({"game_id": g["game_id"], "mu": mu, "market": "atd", "team": g[side], "player": a["name"], "id": a["id"], "p": a["p"],
                            "fair": a["fair"], "score": a["p"]})
    add("ml", ml); add("spread", sp); add("total", to); add("h1", h1); add("h2", h2); add("fg", fg); add("qb_yds", qy); add("qb_td", qt); add("atd", atd, 6)
    return out


def save_payload(payload: dict, out_dir=None) -> str:
    from .config import OUT_DIR
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    name = f"{payload['season']}-w{payload['week']:02d}"
    samples = payload.pop("_samples", None)
    (out_dir / f"week-{name}.json").write_text(json.dumps(payload, separators=(",", ":")))
    if samples:
        (out_dir / f"week-{name}.sims.json").write_text(json.dumps(samples, separators=(",", ":")))
    return name


__all__ = ["build_week", "save_payload", "picks", "actuals"]
