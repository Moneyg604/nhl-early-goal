"""From profiles to one simulated game: the inputs for each side, the market anchor, and the final run.

    inputs = game_inputs(P, row, avail)        # every multiplier, with where it came from
    res    = run_game(P, row, avail)           # pure model sim, market-anchored sim, markets

The model alone (team, quarterback, kicker and context effects on the league drive table) gives an
expected margin and total. When the book's spread and total are known, the final simulation is anchored
to a blend of book and model: target = book + w * (model - book), with w measured walk-forward
(`backtest`, data/nfl/factors.json). The derived markets (halves, field goals, passing, touchdown scorers)
then come out of one simulation that agrees with the game line the market already prices well, while the
team-specific parts (who scores how, how fast, which half) come from the profiles.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field

import numpy as np

from .config import CFG, DATA_DIR, ModelConfig
from .features import RES, RES_IDX, Profiles, game_context_keys, logit, sigmoid
from .sim import SideInputs, SimResult, simulate

TD, FG, FGM, PUNT, TO, DOWNS, EOH, OPPTD, SAF = (RES_IDX[r] for r in RES)


def load_blend() -> dict:
    f = DATA_DIR / "factors.json"
    try:
        d = json.loads(f.read_text())
        return d.get("blend") or {}
    except Exception:  # noqa: BLE001
        return {}


def load_key_numbers() -> dict:
    f = DATA_DIR / "factors.json"
    try:
        d = json.loads(f.read_text())
        return {int(k): float(v) for k, v in (d.get("key_numbers") or {}).items()}
    except Exception:  # noqa: BLE001
        return {}


def _vec(td: float, fg: float, to: float) -> np.ndarray:
    v = np.zeros(len(RES))
    v[TD] = td; v[FG] = fg; v[FGM] = fg; v[TO] = to; v[OPPTD] = to
    return v


@dataclass
class SideBuild:
    team: str
    qb_id: str = ""
    qb_name: str = ""
    qb_status: str = ""
    kicker: str = ""
    parts: dict = field(default_factory=dict)        # name -> (TD, FG, TO) log odds ratios
    inputs: SideInputs | None = None
    notes: list = field(default_factory=list)


def side_inputs(P: Profiles, row: dict, side: str, cfg: ModelConfig = CFG) -> SideBuild:
    """Inputs for `side`'s offense: its offense, the opponent's defense, home field, context, quarterback,
    kicker. Every piece is kept by name so the page can show the arithmetic."""
    lt = P.league
    t = row["home"] if side == "home" else row["away"]
    o = row["away"] if side == "home" else row["home"]
    tp, op = P.team(t), P.team(o)
    sb = SideBuild(team=t)
    off_lo = tp.off.logors(cfg)
    def_lo = op.def_.logors(cfg)
    sb.parts["offense"] = (off_lo["TD"], off_lo["FG"], off_lo["TO"])
    sb.parts["opp_defense"] = (def_lo["TD"], def_lo["FG"], def_lo["TO"])
    neutral = (row.get("location") or "Home") == "Neutral"
    if cfg.use_home and not neutral:
        sgn = 1.0 if side == "home" else -1.0
        sb.parts["home_field"] = tuple(sgn * lt.home_logor[m] for m in ("TD", "FG", "TO"))
    keys = game_context_keys(row, side)
    for k in keys:
        if k in ("rest_adv", "rest_dis", "short_week") and not cfg.use_rest:
            continue
        if k == "dome" and not cfg.use_roof:
            continue
        if k in ("wind15", "cold") and not cfg.use_wind:
            continue
        if k == "division" and not cfg.use_division:
            continue
        c = lt.context.get(k)
        if c:
            sb.parts[k] = (c["TD"], c["FG"], c["TO"])
    # quarterback
    qb = (row.get("qb") or {}).get(side) or {}
    qid = qb.get("id") or tp.primary_qb()
    sb.qb_id = qid; sb.qb_name = qb.get("name") or (P.qbs[qid].name if qid in P.qbs else "")
    sb.qb_status = qb.get("status", "")
    primary = tp.primary_qb()
    qp = P.qbs.get(qid)
    new_starter = bool(qid) and primary and qid != primary and (tp.qbs_cur.get(qid, 0) < 2.5)
    if cfg.use_qb_blend and new_starter:
        nq = P.new_qb
        sb.parts["qb_change"] = (nq.get("TD", 0.0), nq.get("FG", 0.0), nq.get("TO", 0.0))
        sb.notes.append(f"{sb.qb_name or qid} starts in place of {P.qbs[primary].name if primary in P.qbs else primary}")
    # half shape
    shifts = np.zeros((2, len(RES)))
    base = sum(np.array(v) for v in sb.parts.values()) if sb.parts else np.zeros(3)
    for h in range(2):
        v = _vec(*base)
        if cfg.use_half_shape:
            oh = tp.off_h[h].logors(cfg); dh = op.def_h[h].logors(cfg)
            # half-specific deviation from the team's overall, shrunk again (halves have half the drives)
            for m, j in (("TD", TD), ("FG", FG)):
                dev = 0.5 * ((oh[m] - off_lo[m]) + (dh[m] - def_lo[m]))
                v[j] += dev
                if m == "FG":
                    v[FGM] += dev
        shifts[h] = v
    # kicker
    kid = row.get("kicker", {}).get(side) if isinstance(row.get("kicker"), dict) else None
    kid = kid or tp.last_kicker
    kp = P.kickers.get(kid)
    sb.kicker = kid or ""
    make_shift = kp.logor(cfg) if kp else 0.0
    xp = kp.xp_rate(lt, cfg) if kp else lt.xp_make
    # passing
    db_mult = tp.off.db_mult(cfg) * op.def_.db_mult(cfg)
    if qp is not None and qp.off.db >= 120:
        ym = qp.off.ypdb_mult(cfg)
        ptd_lo = qp.off.pass_td_logor(lt, cfg)
    else:
        ym = tp.off.ypdb_mult(cfg) * (P.new_qb.get("ypdb_mult", 1.0) if new_starter else 1.0)
        ptd_lo = tp.off.pass_td_logor(lt, cfg)
    ym *= op.def_.ypdb_mult(cfg)
    p_pass = sigmoid(logit(lt.pass_td_share) + ptd_lo + op.def_.pass_td_logor(lt, cfg))
    pace = tp.off.pace(cfg) * op.def_.pace(cfg)
    sb.inputs = SideInputs(shift=shifts, pace=pace, make_shift=make_shift, xp=xp, db_mult=db_mult, ypdb_mult=ym, p_pass_td=p_pass)
    return sb


def anchor(P: Profiles, home: SideInputs, away: SideInputs, target_home: float, target_away: float, n: int = 20_000,
           iters: int = 5, seed: int = 7, fg_frac: float = 1.0) -> tuple[SideInputs, SideInputs, dict]:
    """Shift both offenses' scoring odds (touchdowns and field-goal tries alike) until the simulated mean
    points match the targets. Common random numbers keep the iteration smooth."""
    lt = P.league
    a_h = a_a = 0.0
    hist = []
    for _ in range(iters):
        h2 = _with_shift(home, a_h, fg_frac); a2 = _with_shift(away, a_a, fg_frac)
        r = simulate(lt, h2, a2, n=n, seed=seed)
        mh, ma = float(r.pts[:, 0].mean()), float(r.pts[:, 1].mean())
        hist.append((round(a_h, 4), round(a_a, 4), round(mh, 2), round(ma, 2)))
        if abs(mh - target_home) < 0.15 and abs(ma - target_away) < 0.15:
            break
        # elasticity of points to a scoring-odds shift is about 0.8 (measured on the league table)
        el = 0.8 if fg_frac >= 0.99 else 0.55 + 0.25 * fg_frac       # points respond less when only touchdowns move
        a_h += math.log(max(target_home, 3.0) / max(mh, 3.0)) / el
        a_a += math.log(max(target_away, 3.0) / max(ma, 3.0)) / el
        a_h = float(np.clip(a_h, -1.5, 1.5)); a_a = float(np.clip(a_a, -1.5, 1.5))
    return _with_shift(home, a_h, fg_frac), _with_shift(away, a_a, fg_frac), {"shift_home": round(a_h, 4), "shift_away": round(a_a, 4), "fg_frac": fg_frac, "iterations": hist}


def _with_shift(si: SideInputs, a: float, fg_frac: float = 1.0) -> SideInputs:
    sh = np.array(np.broadcast_to(np.asarray(si.shift, dtype=float), (2, len(RES))))
    sh[:, TD] += a; sh[:, FG] += a * fg_frac; sh[:, FGM] += a * fg_frac
    return SideInputs(shift=sh, pace=si.pace, make_shift=si.make_shift, xp=si.xp, db_mult=si.db_mult, ypdb_mult=si.ypdb_mult, p_pass_td=si.p_pass_td)


@dataclass
class GameRun:
    row: dict
    home: SideBuild
    away: SideBuild
    model_margin: float
    model_total: float
    model_home_win: float
    target_margin: float | None
    target_total: float | None
    anchor: dict | None
    sim: SimResult
    pure: SimResult | None = None


def market_targets(row: dict, model_margin: float, model_total: float, blend: dict | None = None) -> tuple[float | None, float | None]:
    lines = row.get("lines") or {}
    s, t = lines.get("spread"), lines.get("total")
    if s is None or t is None or (isinstance(s, float) and math.isnan(s)) or (isinstance(t, float) and math.isnan(t)):
        return None, None
    blend = load_blend() if blend is None else blend
    wm, wt = float(blend.get("margin", 0.0)), float(blend.get("total", 0.0))
    return s + wm * (model_margin - s), t + wt * (model_total - t)


def run_game(P: Profiles, row: dict, cfg: ModelConfig = CFG, n: int | None = None, n_pure: int = 30_000, seed: int | None = 11,
             blend: dict | None = None, anchor_to_market: bool = True, keep_pure: bool = False, anchor_n: int = 20_000) -> GameRun:
    n = n or cfg.sims
    hb = side_inputs(P, row, "home", cfg)
    ab = side_inputs(P, row, "away", cfg)
    pure = simulate(P.league, hb.inputs, ab.inputs, n=n_pure, seed=seed)
    mm, mt = float(pure.margin.mean()), float(pure.total.mean())
    mw = float((pure.margin > 0).mean() + 0.5 * (pure.margin == 0).mean())
    tm, tt = market_targets(row, mm, mt, blend) if anchor_to_market else (None, None)
    anc = None
    hi, ai = hb.inputs, ab.inputs
    if tm is not None:
        hi, ai, anc = anchor(P, hb.inputs, ab.inputs, (tt + tm) / 2, (tt - tm) / 2, n=anchor_n, seed=(seed or 0) + 1, fg_frac=cfg.anchor_fg_frac)
    final = simulate(P.league, hi, ai, n=n, seed=(seed or 0) + 2) if (tm is not None or n != n_pure) else pure
    return GameRun(row=row, home=hb, away=ab, model_margin=mm, model_total=mt, model_home_win=mw, target_margin=tm, target_total=tt,
                   anchor=anc, sim=final, pure=pure if keep_pure else None)


__all__ = ["side_inputs", "anchor", "run_game", "GameRun", "SideBuild", "market_targets", "load_blend", "load_key_numbers"]
