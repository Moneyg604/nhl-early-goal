"""The bot's judgment: the checks an analyst runs on every DraftKings bet, the best bets per category, the
combined top six, the anytime-touchdown board, alternate lines, kicker props and projected props, and a
bet-specific analysis (projection, reasons, risk, personnel, formulas, limits, source timestamps) for the page.

Everything reads the week payload only (the simulation's own inputs and outputs plus the best-bets block from
value.py): where an input is missing, the card says so under "limits". value.py decides the win chance and the
price; this module decides which of those bets a careful analyst would take and why.
"""
from __future__ import annotations

from datetime import datetime, timezone

from .live import full_key, name_key
from .value import (ATD_MAX_ODDS, GOOD_EV, GOOD_EV_ATD, LABEL, MIN_BOOKS, NUDGE_CAP, Dist, _nudge, _started)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def same_player(a: str, b: str) -> bool:
    if not a or not b:
        return False
    fa, fb = full_key(a), full_key(b)
    if fa == fb:
        return True
    if name_key(a) != name_key(b):
        return False
    x, y = fa.split(" ")[0], fb.split(" ")[0]
    return len(x) <= 2 or len(y) <= 2 or x == y




SLIM = ("id", "game_id", "mu", "kick", "kind", "market", "side", "line", "who", "team", "label", "odds", "p", "push", "p_market", "p_model",
        "nudge", "note", "fair_odds", "breakeven", "ev", "good", "excluded", "need", "books", "confidence", "flags", "one_sided", "priced_at",
        "group", "conf", "price", "analysis", "tier", "base", "judge", "inputs")


def slim(b: dict, keep_inputs: bool) -> dict:
    x = {k: b.get(k) for k in SLIM if k != "inputs"}
    if keep_inputs and b.get("inputs"):
        I = b["inputs"]
        x["inputs"] = {k: I.get(k) for k in ("books", "lines", "market_median", "model_median", "margin_assumed") if I.get(k) is not None}
    return x




PROP_KINDS = {"qb_yds", "qb_td", "rec_yds", "rush_yds", "recs", "atd", "h1", "h2"}
GROUP = {"ml": "winners", "spread": "spreads", "total": "totals", "h1": "totals", "h2": "totals",
         "qb_yds": "props", "qb_td": "props", "rec_yds": "props", "rush_yds": "props", "recs": "props", "atd": "props"}
OUT_STATUS = ("Out", "Doubtful")


def _ordinal(n) -> str:
    n = int(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _injury_rows(g: dict, side: str, positions: tuple) -> list[str]:
    out = []
    for i in (g.get("injuries") or {}).get(side, []):
        if i.get("pos") in positions and (i.get("status") in OUT_STATUS or "Did Not" in (i.get("practice") or "")):
            st = i.get("status") or ("DNP" if "Did Not" in (i.get("practice") or "") else "")
            out.append(f"{i['name']} {i['pos']} {st}, {i.get('injury') or ''}".strip(", "))
    return out




def confidence(b: dict, g: dict) -> dict:
    """Evidence confidence 0-100: how many books price it, how far the model and market disagree, the data behind
    the game (tier), injury and quarterback flags, and the age of the price."""
    score = 55.0
    n = b.get("books") or 0
    score += min(n, 7) * 4 - 12                          # 3 books: 0, 7 books: +16
    pm, pk = b.get("p_model"), b.get("p_market")
    if pm is not None and pk is not None:
        d = abs(pm - pk)
        score += 8 if d < 0.05 else (0 if d < 0.10 else (-10 if d < 0.20 else -18))
    else:
        score -= 6                                       # market only: the model has nothing to add
    tier = g.get("tier") or "C"
    score += {"A": 6, "B": 0, "C": -10}.get(tier, 0)
    if b.get("flags"):
        score -= 8 * min(len(b["flags"]), 2)
    if b.get("one_sided"):
        score -= 8
    if b.get("excluded"):
        score -= 15
    score = max(5, min(97, score))
    label = "high" if score >= 72 else ("medium" if score >= 50 else "low")
    return {"score": round(score), "label": label}


def price_label(b: dict) -> str:
    ev = b.get("ev") or 0
    need = b.get("need") or 0.02
    if b.get("excluded"):
        return "unreliable"
    if ev >= need:
        return "attractive"
    if ev >= -0.03:
        return "fair"
    return "poor"


def _et(iso: str) -> datetime:
    from zoneinfo import ZoneInfo
    return datetime.strptime(iso, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/New_York"))


def week_label(p: dict) -> str:
    ks = sorted(g["kickoff_utc"] for g in p.get("games", []) if g.get("kickoff_utc"))
    if not ks:
        return f"Week {p.get('week')}"
    a, b = _et(ks[0]), _et(ks[-1])
    span = f"{a:%b} {a.day} to {b.day}" if a.month == b.month else f"{a:%b} {a.day} to {b:%b} {b.day}"
    return f"Week {p.get('week')} · {span}"




POS_OL = ("T", "G", "C", "OL", "OT", "OG")
POS_DEF = ("DE", "DT", "NT", "DL", "EDGE", "OLB", "ILB", "LB", "MLB", "CB", "S", "FS", "SS", "DB")


def _rank_txt(r) -> str:
    return _ordinal(r) if r else "unranked"


def _dnp(i: dict) -> bool:
    return i.get("status") in OUT_STATUS or "Did Not" in (i.get("practice") or "")


def _inj(g: dict, side: str, positions: tuple, *, only_dnp: bool = True) -> list[dict]:
    rows = []
    for i in (g.get("injuries") or {}).get(side, []):
        if i.get("pos") in positions and (not only_dnp or _dnp(i)):
            rows.append(i)
    return rows


def _inj_txt(rows: list[dict], n: int = 4) -> str:
    return "; ".join(f"{i['name']} ({i['pos']}) {i.get('status') or ('DNP Thu' if 'Did Not' in (i.get('practice') or '') else (i.get('practice') or '').split(' ')[0])}, {i.get('injury') or ''}".strip(", ")
                     for i in rows[:n])


def _q(dist, lo_scale=1.0):
    """25th / 50th / 75th percentile of a [offset, probs] distribution."""
    import numpy as _np
    off, vals = dist
    p = _np.asarray(vals, float); p = p / p.sum()
    c = _np.cumsum(p)
    v = (_np.arange(len(p)) + off) * lo_scale
    return [float(v[min(int(_np.searchsorted(c, q)), len(v) - 1)]) for q in (0.25, 0.5, 0.75)]


def _side_of(b: dict, g: dict) -> str | None:
    if b.get("team"):
        return "home" if g["home"] == b["team"] else "away"
    if b.get("who"):
        for s_ in ("home", "away"):
            for x in list((g.get("props") or {}).get(s_, [])) + list((g.get("anytime") or {}).get(s_, [])):
                if same_player(x.get("name") or "", b["who"]):
                    return s_
            q = (g.get("qb") or {}).get(s_) or {}
            if q.get("name") and same_player(q["name"], b["who"]):
                return s_
    return None


def _weather(g: dict) -> tuple[list[str], dict]:
    wx = g.get("weather") or {}
    roof = g.get("roof") or "unknown"
    where = f"{g.get('stadium') or 'stadium'} ({g['home']} home), {roof}" + (f", {g.get('surface')}" if g.get("surface") else "")
    flags = {"windy": False, "cold": False, "rain": False}
    if roof in ("dome", "closed"):
        return [f"{where}: no weather effect"], flags
    if not wx:
        return [f"{where}: forecast not available"], flags
    flags["windy"] = (wx.get("wind") or 0) >= 15
    flags["cold"] = wx.get("temp") is not None and wx["temp"] <= 32
    flags["rain"] = (wx.get("precip_prob") or 0) >= 50
    txt = f"{where}: {wx.get('temp', 0):.0f}°F, wind {wx.get('wind', 0):.0f} mph" + (f" gusting {wx['gust']:.0f}" if wx.get("gust") else "") + (f", rain {wx['precip_prob']:.0f}%" if wx.get("precip_prob") is not None else "")
    if flags["windy"]:
        txt += ". Wind over 15 mph: the simulation applies the measured wind effect (fewer touchdowns and field goals, more turnovers)"
    return [txt], flags


def _personnel(g: dict, side: str | None, who: str | None = None) -> list[str]:
    out = []
    for s_ in ([side] if side else ["away", "home"]):
        q = (g.get("qb") or {}).get(s_) or {}
        if q.get("name"):
            src = q.get("source") or ""
            conf = "confirmed" if "agree" in src else "projected"
            out.append(f"{g[s_]} QB {q['name']} ({conf}{', ' + src if src and 'agree' not in src else ''})" + (f", listed {q['status']}" if q.get("status") else "") + (" · new starter this season" if q.get("change") else ""))
    if who:
        for s_ in ("home", "away"):
            for i in (g.get("injuries") or {}).get(s_, []):
                if same_player(i.get("name") or "", who):
                    out.append(f"{who}: injury report {i.get('status') or (i.get('practice') or '')}, {i.get('injury') or ''}".strip(", "))
    return out


def _stamps(b: dict, g: dict, meta: dict) -> dict:
    src = {s.get("name", ""): s for s in (meta.get("sources") or [])}
    inj = next((v for k, v in src.items() if k.startswith("Official injury")), {})
    snaps = next((v for k, v in src.items() if k.startswith("Snap")), {})
    pbp = next((v for k, v in src.items() if k.startswith("Play-by-play")), {})
    return {"odds": b.get("priced_at"), "injuries": inj.get("fetched"), "usage": snaps.get("fetched") or pbp.get("fetched"),
            "data_through": meta.get("data_through"), "weather": meta.get("generated_utc"), "model": meta.get("generated_utc")}


def analyze(b: dict, g: dict, meta: dict) -> dict:
    """Projection, reasons, risk, personnel, formulas and limits for one bet, from the payload only."""
    k = b["kind"]
    side = _side_of(b, g)
    opp = None if side is None else ("away" if side == "home" else "home")
    R = g.get("research") or {}
    rs, ro = (R.get(side) or {}) if side else {}, (R.get(opp) or {}) if opp else {}
    mk = g.get("markets") or {}
    L = g.get("lines") or {}
    lg = (meta.get("league") or {})
    wx_lines, wxf = _weather(g)
    reasons: list[str] = []; formula: list[str] = []; limits: list[str] = []; risks: list[tuple[int, str]] = []
    proj = None; rng = None
    # risks shared by every market
    if b.get("flags"):
        for f_ in b["flags"]:
            risks.append((90, f_))
    pm, pk = b.get("p_model"), b.get("p_market")
    if pm is not None and pk is not None and abs(pm - pk) >= 0.10:
        risks.append((70, f"The simulation ({pm*100:.0f}%) and the market ({pk*100:.0f}%) disagree by {abs(pm-pk)*100:.0f} points; the market is trusted and the gap is a warning that the model is missing something"))
    if (b.get("books") or 0) < 4:
        risks.append((50, f"Only {b.get('books')} books price this market"))
    spread = L.get("spread")
    big = spread is not None and abs(spread) >= 9.5

    if k in ("ml", "spread"):
        for s_ in ("away", "home"):
            r = R.get(s_) or {}
            if not r:
                continue
            a = r.get("adv") or {}; ro_, rd_ = a.get("rank_off") or {}, a.get("rank_def") or {}
            off, dfn = r.get("offense") or {}, r.get("defense") or {}
            reasons.append(f"{g[s_]} ({r.get('record')}): offense scores a touchdown on {off.get('td_rate', 0)*100:.0f}% of drives vs {off.get('td_x_rate', 0)*100:.0f}% expected from the same situations (strength ×{off.get('or_td', 1):.2f}); defense allows {dfn.get('td_rate', 0)*100:.0f}% vs {dfn.get('td_x_rate', 0)*100:.0f}% (×{dfn.get('or_td', 1):.2f}); EPA/play offense {r.get('epa_off_per_play', 0):+.3f}, defense {r.get('epa_def_per_play', 0):+.3f}; pass offense {_rank_txt(ro_.get('epa_pass'))}, pass defense {_rank_txt(rd_.get('epa_pass'))}, run defense {_rank_txt(rd_.get('epa_rush'))}")
        for s_ in ("away", "home"):
            ol = _inj(g, s_, POS_OL); de = _inj(g, s_, POS_DEF)
            if ol:
                reasons.append(f"{g[s_]} offensive line: {_inj_txt(ol)}")
            if de:
                reasons.append(f"{g[s_]} defense: {_inj_txt(de)}")
        hp, ap = mk.get("home_pts"), mk.get("away_pts")
        if mk.get("dist", {}).get("margin"):
            q25, q50, q75 = _q(mk["dist"]["margin"])
            rng = f"home margin 25th to 75th percentile: {q25:+.0f} to {q75:+.0f}"
        if hp is not None:
            proj = f"projected score {g['home']} {hp:.1f}, {g['away']} {ap:.1f}"
        m = g.get("model") or {}
        if k == "ml":
            formula.append(f"P(win) from 100,000 simulated games: {g['home']} wins {mk['ml']['home']*100:.1f}%, {g['away']} {mk['ml']['away']*100:.1f}%, tie {mk['ml'].get('tie', 0)*100:.1f}% (simulated outcomes reweighted to the market's moneyline and spread; model alone had {g['home']} at {m.get('home_win', 0)*100:.0f}%)")
        else:
            formula.append(f"P(cover) = share of simulated games with {g[side]} margin + {b['line']:+g} > 0 = {_pm(b)} (simulation mean margin {g['home']} {m.get('margin', 0):+.1f}; market line {g['home']} {-(spread or 0):+g})")
        formula.append("Each simulated drive draws its result from the league table for its situation (half, field position, time, score), shifted by both teams' measured strengths; points, pace and passing follow drive by drive")
        rest = g.get("rest") or {}
        if rest.get("home") and rest.get("away") and abs(rest["home"] - rest["away"]) >= 3:
            adv = g["home"] if rest["home"] > rest["away"] else g["away"]
            reasons.append(f"Rest: {g['home']} {rest['home']} days, {g['away']} {rest['away']} days; the measured rest-advantage effect is applied for {adv}")
        reasons.extend(wx_lines)
        if wxf["windy"]:
            risks.append((40, "Wind over 15 mph widens the range of outcomes"))
        limits.append("Coaching tendencies and travel are not inputs: the walk-forward test found no measurable effect, so none is applied")
    elif k in ("total", "h1", "h2"):
        poss = None
        secs = [((R.get(s_) or {}).get("offense") or {}).get("secs_per_drive") for s_ in ("home", "away")]
        if all(secs):
            poss = 3600 / (secs[0] + secs[1])
            formula.append(f"Possessions per team ≈ 3600 s ÷ ({secs[0]:.0f} s + {secs[1]:.0f} s per drive) = {poss:.1f} (regulation; pace multipliers {((R.get('home') or {}).get('offense') or {}).get('pace', 1):.2f} / {((R.get('away') or {}).get('offense') or {}).get('pace', 1):.2f})")
        parts = []
        ldrives = (lg.get("drives") or 0) / max(lg.get("games") or 1, 1) / 2        # league drives per team per game
        lppd = (lg.get("total_mean") or 0) / 2 / ldrives if ldrives else None
        for s_ in ("home", "away"):
            r = R.get(s_) or {}; o_ = (R.get("away" if s_ == "home" else "home") or {})
            off, dfn = r.get("offense") or {}, o_.get("defense") or {}
            if off.get("ppd") is not None and dfn.get("ppd") is not None and lppd:
                parts.append((s_, off["ppd"], dfn["ppd"], off["ppd"] * dfn["ppd"] / lppd))
        if parts and poss:
            est = sum(poss * p_[3] for p_ in parts)
            formula.append(f"Points ≈ possessions × offense points per drive × (opponent defense points allowed per drive ÷ league {lppd:.2f}): " + " + ".join(f"{g[s_]} {poss:.1f} × {o:.2f} × ({d:.2f} ÷ {lppd:.2f}) = {poss*a:.1f}" for s_, o, d, a in parts) + f" = {est:.1f} (a first-order check; the simulation's figure above is situation by situation)")
        m = g.get("model") or {}
        share = lg.get("h1_share", 0.5)
        if k == "total":
            proj = f"simulation total {mk.get('total_mean', m.get('total', 0)):.1f} (model alone {m.get('total', 0):.1f}, market {L.get('total')})"
            if mk.get("dist", {}).get("total"):
                q25, q50, q75 = _q(mk["dist"]["total"]); rng = f"25th to 75th percentile: {q25:.0f} to {q75:.0f} points"
        else:
            key = "h1" if k == "h1" else "h2"
            proj = f"simulation {'first' if k == 'h1' else 'second'} half {mk.get(key + '_mean', 0):.1f} points (league {'first' if k == 'h1' else 'second'}-half share {share*100 if k == 'h1' else (1-share)*100:.0f}% of {L.get('total')})"
            if mk.get("dist", {}).get(key):
                q25, q50, q75 = _q(mk["dist"][key]); rng = f"25th to 75th percentile: {q25:.0f} to {q75:.0f} points"
        formula.append(f"P({b['side']} {b['line']}) = share of simulated games {'above' if b['side'] == 'over' else 'below'} {b['line']} = {_pm(b)}")
        for s_ in ("away", "home"):
            r = R.get(s_) or {}; a = (r.get("adv") or {}); ro_, rd_ = a.get("rank_off") or {}, a.get("rank_def") or {}
            ao, ad = a.get("off") or {}, a.get("def") or {}
            if ao:
                reasons.append(f"{g[s_]} offense: explosive plays {ao.get('explosive', 0)*100:.1f}% ({_rank_txt(ro_.get('explosive'))}), red-zone TD {ao.get('red_zone_td', 0)*100:.0f}% ({_rank_txt(ro_.get('red_zone_td'))}), {ao.get('rz_trips_pg', 0):.1f} red-zone trips per game, success rate {ao.get('success', 0)*100:.0f}%; defense allows explosive {ad.get('explosive', 0)*100:.1f}% ({_rank_txt(rd_.get('explosive'))}), red-zone TD {ad.get('red_zone_td', 0)*100:.0f}% ({_rank_txt(rd_.get('red_zone_td'))}); O/U {r.get('ou')}")
        for s_ in ("away", "home"):
            rows = _inj(g, s_, ("QB", "RB", "WR", "TE") + POS_OL)
            if rows:
                reasons.append(f"{g[s_]} offense injuries: {_inj_txt(rows)}")
        reasons.extend(wx_lines)
        if wxf["windy"]:
            risks.append((60, "Wind over 15 mph: fewer points on average and a wider range"))
    elif k in ("qb_yds", "qb_td"):
        q = ((g.get("qb") or {}).get(side) or {}) if side else {}
        prof = q.get("profile") or {}
        qm = (mk.get("qb") or {}).get(side) or {}
        inp = (g.get("inputs") or {}).get(side) or {}
        off, dfn = rs.get("offense") or {}, ro.get("defense") or {}
        if qm:
            proj = f"simulation: {qm.get('db_mean', 0):.1f} dropbacks, {qm.get('yds_mean', 0):.0f} passing yards, {qm.get('td_mean', 0):.2f} TD passes"
            qs = qm.get("yds_q") or []
            if len(qs) >= 5:
                mm = (b.get("inputs") or {}).get("market_median")
                rng = f"passing yards 25th to 75th percentile: {qs[2]:.0f} to {qs[4]:.0f}" + (f"; market median {mm}" if mm is not None and k == "qb_yds" else "")
        if lg.get("ypdb") and inp:
            formula.append(f"Yards per dropback = league {lg['ypdb']:.2f} × QB {prof.get('ypdb_mult', 1):.3f} ({q.get('name')}: {prof.get('ypdb', 0)} on {prof.get('dropbacks', 0)} dropbacks, shrunk toward the league) × {g[opp] if opp else 'opponent'} defense {dfn.get('ypdb_mult', 1):.3f} (allows {dfn.get('ypdb', 0)} per dropback) = {lg['ypdb']*prof.get('ypdb_mult', 1)*dfn.get('ypdb_mult', 1):.2f}")
            formula.append(f"Dropbacks per drive = league rate × {g[side]} offense {off.get('db_mult', 1):.3f} × {g[opp] if opp else 'opponent'} defense {dfn.get('db_mult', 1):.3f} (combined {inp.get('db_mult', 1):.3f}), more when trailing; drives from pace {inp.get('pace', 1):.2f}. Passing yards = Σ over drives of dropbacks × yards per dropback (by drive result)")
            formula.append(f"P({b['side']} {b['line']}) = share of simulated games {'above' if b['side'] == 'over' else 'below'} {b['line']} = {_pm(b)}")
        last = (prof.get("last_games") or [])[-5:]
        if last:
            reasons.append(f"{q.get('name')} last {len(last)}: " + ", ".join(f"{x['db']} db / {x['yds']} yds / {x['td']} TD vs {x['opp']}" for x in last))
        a_off, a_def = (rs.get("adv") or {}), (ro.get("adv") or {})
        ao, ad = a_off.get("off") or {}, a_def.get("def") or {}
        ro_, rd_ = a_off.get("rank_off") or {}, a_def.get("rank_def") or {}
        if ao:
            reasons.append(f"Volume: {g[side]} throw on {ao.get('neutral_pass', 0)*100:.0f}% of neutral downs (pass rate over expected {ao.get('proe', 0)*100:+.0f}%), {ao.get('pace', 0):.0f} s per play; market spread {g['home']} {-(spread or 0):+g} ({'likely trailing, more attempts' if (side == 'home') == ((spread or 0) < 0) and abs(spread or 0) >= 3 else ('likely leading, fewer late attempts' if abs(spread or 0) >= 3 else 'close game expected')})")
        if ao and ad:
            reasons.append(f"Pressure vs protection: {g[side]} sack rate allowed {ao.get('sack_rate', 0)*100:.1f}% ({_rank_txt(ro_.get('sack_rate'))}), {g[opp]} sack rate {ad.get('sack_rate', 0)*100:.1f}% ({_rank_txt(rd_.get('sack_rate'))}); coverage: {g[opp]} pass defense EPA {ad.get('epa_pass', 0):+.3f} ({_rank_txt(rd_.get('epa_pass'))}), explosive allowed {ad.get('explosive', 0)*100:.1f}%")
        rows = _inj(g, side, ("WR", "TE")) if side else []
        ol = _inj(g, side, POS_OL) if side else []
        if rows:
            reasons.append(f"Receivers: {_inj_txt(rows)}")
        if ol:
            reasons.append(f"Offensive line: {_inj_txt(ol)}")
        de = _inj(g, opp, ("CB", "S", "FS", "SS", "DB", "DE", "EDGE", "OLB")) if opp else []
        if de:
            reasons.append(f"{g[opp]} pass defense missing / DNP: {_inj_txt(de)}")
        reasons.extend(wx_lines)
        if wxf["windy"]:
            risks.append((65, "Wind over 15 mph lowers passing volume and efficiency"))
        if big:
            risks.append((45, "Spread of 10+: a blowout changes the second-half passing script either way"))
        if q.get("change"):
            risks.append((80, "New starter: his profile rests on few dropbacks, so the team's rates stand in"))
        limits.append("Routes run and coverage matchups by receiver are not in the data; coverage is measured at the team level (EPA per pass, yards per dropback)")
    elif k in ("rec_yds", "recs", "rush_yds", "atd"):
        pl = next((x for x in (g.get("props") or {}).get(side or "", []) if same_player(x.get("name") or "", b["who"])), None)
        at = next((x for x in (g.get("anytime") or {}).get(side or "", []) if same_player(x.get("name") or "", b["who"])), None)
        u = (pl or {}).get("usage") or {}
        qm = (mk.get("qb") or {}).get(side) or {}
        dfn = ro.get("defense") or {}
        a_def = (ro.get("adv") or {}); ad, rd_ = a_def.get("def") or {}, a_def.get("rank_def") or {}
        if not pl and not at:
            limits.append("No independent player projection: this player is not in the simulation's usage data (too few touches this season), so the win chance is market-derived only")
        if at:
            reasons.append(f"Usage: {at.get('tgt_share', 0)*100:.0f}% of team targets, {at.get('car_share', 0)*100:.0f}% of carries, {at.get('rz_share', 0)*100:.0f}% of red-zone touches; snaps last 3 games {' / '.join(str(round(v*100)) + '%' for v in at.get('snaps') or []) or 'n/a'} (trend ×{at.get('snap_trend', 1):.2f}); scored in {at.get('td_games')} of {at.get('games')} games")
            rec = at.get("recent") or []
            if rec:
                reasons.append("Recent: " + ", ".join(f"{x['car']} car / {x['tgt']} tgt / {x['td']} TD" for x in rec[-4:]))
        # target / carry competition
        others = [x for x in (g.get("anytime") or {}).get(side or "", []) if not same_player(x.get("name") or "", b["who"])]
        if k in ("rec_yds", "recs"):
            comp = sorted(others, key=lambda x: -x.get("tgt_share", 0))[:3]
            if comp:
                reasons.append("Target competition: " + ", ".join(f"{x['name']} {x.get('tgt_share', 0)*100:.0f}%" for x in comp))
            d = (pl or {}).get(k) or {}
            if u and qm and d:
                proj = f"simulation: {d.get('mean', 0):.1f} {'receptions' if k == 'recs' else 'receiving yards'}"
                qs = d.get("q") or []
                if len(qs) >= 4:
                    mm = (b.get("inputs") or {}).get("market_median")
                    rng = f"25th to 75th percentile: {qs[1]:.0f} to {qs[3]:.0f}" + (f"; market median {mm}" if mm is not None else "")
                if k == "rec_yds":
                    formula.append(f"Receiving yards = {u.get('rec_yds_share', 0)*100:.1f}% share of team passing yards × simulated team passing yards (mean {qm.get('yds_mean', 0):.0f}) = {u.get('rec_yds_share', 0)*qm.get('yds_mean', 0):.1f} before game-to-game noise (sd = k × √expected, measured from 2024-25 player games)")
                else:
                    formula.append(f"Receptions = {u.get('rec_share', 0)*100:.1f}% share of team completions × simulated completions (dropbacks {qm.get('db_mean', 0):.1f} × (1 − sack rate 6.5%) × league completion rate) = {u.get('rec_share', 0)*qm.get('db_mean', 0)*0.935*lg.get('comp_rate', 0.65):.1f}")
                formula.append(f"Share = his weighted average over {u.get('games_w', 0):.1f} recent games (half-life 6 games), shrunk toward the team's distribution; P({b['side']} {b['line']}) = {_pm(b)} of simulated games")
            reasons.append(f"Coverage: {g[opp] if opp else 'opponent'} pass defense EPA {ad.get('epa_pass', 0):+.3f} ({_rank_txt(rd_.get('epa_pass'))}), allows {dfn.get('ypdb', 0)} yards per dropback (×{dfn.get('ypdb_mult', 1):.3f} on the league), explosive plays allowed {ad.get('explosive', 0)*100:.1f}%")
            limits.append("Routes run, alignment (slot / wide) and the covering cornerback are not in the data; coverage is measured at the team level")
        elif k == "rush_yds":
            d = (pl or {}).get("rush_yds") or {}
            comp = sorted(others, key=lambda x: -x.get("car_share", 0))[:3]
            if comp:
                reasons.append("Carry competition: " + ", ".join(f"{x['name']} {x.get('car_share', 0)*100:.0f}%" + (" (QB)" if x.get("pos", "").startswith("QB") else "") for x in comp))
            if u and d:
                proj = f"simulation: {d.get('mean', 0):.1f} rushing yards (≈ {d.get('mean', 0)/max(u.get('ypc', 4.0), 0.1):.1f} carries at {u.get('ypc', 0):.2f} per carry)"
                qs = d.get("q") or []
                if len(qs) >= 4:
                    mm = (b.get("inputs") or {}).get("market_median")
                    rng = f"25th to 75th percentile: {qs[1]:.0f} to {qs[3]:.0f}" + (f"; market median {mm}" if mm is not None else "")
                formula.append(f"Rushing yards = {u.get('car_share', 0)*100:.0f}% carry share × team rushes (league base × {g[side]} run rate × {g[opp] if opp else 'opponent'} run defense, plus more carries per point of lead) × {u.get('ypc', 0):.2f} yards per carry (his own, × team and opponent run multipliers)")
                formula.append(f"P({b['side']} {b['line']}) = {_pm(b)} of simulated games; leading teams run more, so the spread ({g['home']} {-(spread or 0):+g}) shapes the carry count")
            reasons.append(f"Front: {g[opp] if opp else 'opponent'} run defense EPA {ad.get('epa_rush', 0):+.3f} ({_rank_txt(rd_.get('epa_rush'))}), success rate allowed {ad.get('success', 0)*100:.0f}%")
            ol = _inj(g, side, POS_OL) if side else []
            if ol:
                reasons.append(f"Offensive line: {_inj_txt(ol)}")
            dl = _inj(g, opp, ("DE", "DT", "NT", "DL", "LB", "ILB", "MLB", "OLB", "EDGE")) if opp else []
            if dl:
                reasons.append(f"{g[opp]} front missing / DNP: {_inj_txt(dl)}")
        else:  # anytime TD
            if at:
                proj = f"simulation: scores in {at['p']*100:.1f}% of games (fair {at.get('fair', 0):.2f})"
                formula.append(f"P(score) = 1 − E[(1 − {at.get('rec_share', 0):.3f} receiving TD share)^(team passing TDs) × (1 − {at.get('rush_share', 0):.3f} rushing TD share)^(team rushing TDs)] over the simulated games; shares = half his overall usage, half his red-zone usage, rescaled across the active players, × snap trend")
            reasons.append(f"Red zone: {g[side] if side else 'team'} {((rs.get('adv') or {}).get('off') or {}).get('rz_trips_pg', 0):.1f} trips per game, TD rate {((rs.get('adv') or {}).get('off') or {}).get('red_zone_td', 0)*100:.0f}%; {g[opp] if opp else 'opponent'} allows red-zone TD {ad.get('red_zone_td', 0)*100:.0f}% ({_rank_txt(rd_.get('red_zone_td'))})")
            limits.append("Books post only a Yes price on anytime touchdowns: a 7% margin is assumed to remove it")
        # workload shifts from teammates out
        mates = [i for i in _inj(g, side, ("QB", "RB", "WR", "TE")) if not same_player(i.get("name") or "", b["who"])] if side else []
        if mates:
            names = {gb_full(i["name"]): i for i in mates}
            shifted = [x for x in others if gb_full(x["name"]) in names and (x.get("tgt_share", 0) >= 0.08 or x.get("car_share", 0) >= 0.15)]
            if shifted:
                reasons.append("Workload shift: " + "; ".join(f"{x['name']} ({x.get('tgt_share', 0)*100:.0f}% targets, {x.get('car_share', 0)*100:.0f}% carries) {names[gb_full(x['name'])].get('status') or 'DNP'}" for x in shifted) + ". The simulation rescales shares across the players expected to be active; it does not model who inherits a specific role")
            else:
                reasons.append(f"{g[side]} teammates on the report: {_inj_txt(mates, 3)}")
        if pl and pl.get("q") or (at and at.get("q")):
            risks.append((85, f"{b['who']} is questionable: a late scratch voids the bet at DraftKings"))
        if big:
            risks.append((45, f"Spread of 10+: {'a blowout cuts late passing' if k in ('rec_yds', 'recs') else 'the game script moves the carry count'}"))
        if wxf["windy"] and k in ("rec_yds", "recs"):
            risks.append((55, "Wind over 15 mph lowers passing volume"))
        q = ((g.get("qb") or {}).get(side) or {}) if side else {}
        if q.get("change"):
            risks.append((60, f"New quarterback ({q.get('name')}): target distribution may differ from the season's"))
        reasons.extend(wx_lines)
    # projected personnel, timestamps, biggest risk
    pers = _personnel(g, side, b.get("who"))
    st = _stamps(b, g, meta)
    if st.get("odds") and st.get("injuries"):
        try:
            if _ts_iso(st["injuries"]) > _ts_iso(st["odds"]) + 3600:
                risks.append((30, "The injury report is newer than this price: DraftKings may have moved it since"))
        except Exception:  # noqa: BLE001
            pass
    risks.sort(key=lambda x: -x[0])
    risk = risks[0][1] if risks else "No specific risk flagged beyond ordinary game variance"
    return {"proj": proj, "range": rng, "reasons": reasons[:8], "formula": formula, "limits": limits, "risk": risk, "personnel": pers, "stamps": st}


def _pm(b: dict) -> str:
    return "not simulated" if b.get("p_model") is None else f"{b['p_model']*100:.1f}%"


def gb_full(n: str) -> str:
    return full_key(n)


def _ts_iso(s: str) -> float:
    s = (s or "").replace(" UTC", "Z").replace(" ", "T")
    if len(s) == 17:
        s = s[:16] + ":00Z"
    return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()


def kicker_props(g: dict, meta: dict) -> list[dict]:
    """Team field goals made (the kicker's FG prop) from the simulation: no DraftKings price in the feed, so these
    carry the fair odds and must be checked against DraftKings' kicker market by hand."""
    out = []
    mk = g.get("markets") or {}
    lg = meta.get("league") or {}
    for side in ("home", "away"):
        f = (mk.get("fg") or {}).get(side) or {}
        kp = ((g.get("kicker") or {}).get(side) or {})
        prof = kp.get("profile") or {}
        if not f or not kp.get("name"):
            continue
        r = (g.get("research") or {}).get(side) or {}
        o_ = (g.get("research") or {}).get("away" if side == "home" else "home") or {}
        off, dfn = r.get("offense") or {}, o_.get("defense") or {}
        inp = (g.get("inputs") or {}).get(side) or {}
        pmf = f.get("pmf") or []
        for line in (0.5, 1.5, 2.5):
            po = sum(pmf[i] for i in range(len(pmf)) if i > line)
            for sd, p in (("over", po), ("under", 1 - po)):
                if p < 0.5:
                    continue
                lab = f"{kp['name']} {sd} {line} field goals made"
                out.append({"id": f"fg|{g['game_id']}|{sd}|{line:g}|{kp['name']}", "game_id": g["game_id"], "mu": f'{g["away"]} @ {g["home"]}', "kick": g.get("kickoff_utc") or "",
                            "kind": "fg", "market": "Kicker field goals", "side": sd, "line": line, "who": kp["name"], "team": g[side], "label": lab,
                            "odds": None, "p": round(p, 4), "push": 0.0, "p_market": None, "p_model": round(p, 4), "nudge": 0.0,
                            "note": "simulation only: DraftKings' kicker market is not in the odds feed", "fair_odds": round(1 / p, 3) if p > 0 else None,
                            "breakeven": None, "ev": None, "good": False, "excluded": "no DraftKings price", "need": 0.02, "books": 0, "confidence": "low",
                            "flags": [], "one_sided": False, "priced_at": None, "group": "kickers", "tier": g.get("tier"),
                            "conf": {"score": 45 if prof.get("att", 0) >= 10 else 35, "label": "low"}, "price": "no price",
                            "analysis": {"proj": f"simulation: {f.get('mean', 0):.2f} field goals made (P(1+) {f.get('over0.5', 0)*100:.0f}%, P(2+) {f.get('over1.5', 0)*100:.0f}%, P(3+) {f.get('over2.5', 0)*100:.0f}%)",
                                         "range": None,
                                         "reasons": [f"{g[side]} offense reaches a field-goal try on {off.get('fg_rate', 0)*100:.1f}% of drives vs {off.get('fg_x_rate', 0)*100:.1f}% expected (×{off.get('or_fg', 1):.2f}); {g['away' if side == 'home' else 'home']} defense allows tries on {dfn.get('fg_rate', 0)*100:.1f}% vs {dfn.get('fg_x_rate', 0)*100:.1f}% (×{dfn.get('or_fg', 1):.2f}); red-zone TD rate {((r.get('adv') or {}).get('off') or {}).get('red_zone_td', 0)*100:.0f}% (stalled drives become tries)",
                                                     f"{kp['name']}: {prof.get('made', 0):.0f} of {prof.get('att', 0):.0f} ({prof.get('pct', 0)*100:.0f}%) vs {prof.get('expected_pct', 0)*100:.0f}% expected for his distances (×{prof.get('or', 1):.2f} on makes), 50+ yards {prof.get('long_50plus', 'n/a')}, over {prof.get('games', 0)} games",
                                                     f"Make-rate shift applied in the simulation (kicker + weather): {inp.get('make_shift', 0):+.3f} on the logit; league make rate {lg.get('fg_make_avg', 0)*100:.0f}%, league {lg.get('fg_made_per_team', 0):.2f} made per team per game"]
                                                    + _weather(g)[0],
                                         "formula": [f"Tries per game = drives × try rate (league table by situation × {off.get('or_fg', 1):.2f} offense × {dfn.get('or_fg', 1):.2f} defense); makes = tries × make probability (league curve for the distance, shifted {inp.get('make_shift', 0):+.3f} for the kicker and weather)",
                                                     f"P({sd} {line}) = share of simulated games with {'more' if sd == 'over' else 'fewer'} than {line} makes = {p*100:.1f}% → fair odds {1/p:.2f}"],
                                         "limits": ["DraftKings' kicker field-goal market is not pulled by the odds feed (it costs an extra credit per game): compare the fair odds with DraftKings' price yourself; the simulation shares every drive with the game's other markets, so a low-scoring script lowers both points and field-goal tries"]
                                                   + ([f"Small sample: {prof.get('att', 0):.0f} attempts"] if prof.get("att", 0) < 10 else []),
                                         "risk": "Weather or a blowout can remove field-goal tries; a missed extra point does not count",
                                         "personnel": _personnel(g, side), "stamps": {"model": meta.get("generated_utc"), "injuries": None, "odds": None}}})
    return out


BOT_MIN_EDGE = 0.03          # simulation's own EV at DraftKings' price
BOT_MAX_GAP = 0.15           # simulation vs market disagreement allowed (probability points)
BOT_ODDS = (1.20, 4.00)
ALT_STEPS = {"qb_yds": (-30, -20, -10, 10, 20, 30), "rec_yds": (-20, -10, 10, 20), "rush_yds": (-20, -10, 10, 20),
             "recs": (-2, -1, 1, 2), "spread": (-7, -3.5, 3.5, 7), "total": (-7, -3.5, 3.5, 7), "h1": (-3.5, 3.5)}


def _dist_for(b: dict, g: dict):
    """The simulation's distribution behind a bet (same source value.game_bets used)."""
    mk = g.get("markets") or {}
    k = b["kind"]
    if k in ("spread",):
        d = (mk.get("dist") or {}).get("margin"); return Dist(d[0], d[1]) if d else None
    if k in ("total", "h1", "h2"):
        d = (mk.get("dist") or {}).get(k if k != "total" else "total"); return Dist(d[0], d[1]) if d else None
    side = _side_of(b, g)
    if k == "qb_yds" and side:
        q = (mk.get("qb") or {}).get(side) or {}
        return Dist(q["yds_pmf5"][0], q["yds_pmf5"][1], 5.0) if q.get("yds_pmf5") else None
    if k in ("rec_yds", "rush_yds", "recs") and side:
        for x in (g.get("props") or {}).get(side, []):
            if same_player(x.get("name") or "", b.get("who") or "") and x.get(k, {}).get("pmf"):
                d = x[k]; return Dist(d["pmf"][0], d["pmf"][1], float(d.get("step", 1.0)))
    return None


def model_ev(b: dict) -> float | None:
    pm = b.get("p_model")
    if pm is None or not b.get("odds"):
        return None
    return pm * (b["odds"] - 1) - (1 - pm - (b.get("push") or 0))


def bot_reason(b: dict, g: dict) -> str:
    pm, pk = b.get("p_model"), b.get("p_market")
    A = b.get("analysis") or {}
    lead = (A.get("reasons") or [""])[0]
    gap = f"simulation {pm*100:.0f}% vs market {pk*100:.0f}%" if pm is not None and pk is not None else ""
    return (gap + ("; " if gap and lead else "") + lead)[:260] + (f" · {b['check']}" if b.get("check") else "")


def research_check(b: dict, g: dict) -> tuple[bool | None, str]:
    """Does the player's own recent production point the same way as the simulation? None = no data to check."""
    k = b["kind"]
    side = _side_of(b, g)
    if k in ("qb_yds", "qb_td") and side:
        q = (g.get("qb") or {}).get(side) or {}
        last = ((q.get("profile") or {}).get("last_games") or [])[-5:]
        if len(last) < 3 or b.get("line") is None:
            return None, "fewer than 3 recent starts to check"
        avg = sum(x["yds" if k == "qb_yds" else "td"] for x in last) / len(last)
        agree = (avg > b["line"]) == (b["side"] == "over")
        return agree, f"recent {len(last)}-game average {avg:.1f} vs line {b['line']} {'agrees' if agree else 'disagrees'}"
    if k == "atd" and side:
        at = next((x for x in (g.get("anytime") or {}).get(side, []) if same_player(x.get("name") or "", b.get("who") or "")), None)
        if at and at.get("games"):
            rate = at["td_games"] / at["games"]
            agree = rate >= (b.get("p_market") or 0) * 0.8
            return agree, f"scored in {at['td_games']} of {at['games']} games ({rate*100:.0f}%) vs market {(b.get('p_market') or 0)*100:.0f}% {'agrees' if agree else 'disagrees'}"
    return None, ""


def bot_picks(board: list[dict], G: dict) -> list[dict]:
    """Bets the simulation itself rates as value at DraftKings' price, ranked by its own edge."""
    out = []
    for b in board:
        if b.get("excluded") or b.get("odds") is None or b.get("p_model") is None:
            continue
        if not (BOT_ODDS[0] <= b["odds"] <= BOT_ODDS[1]) or (b.get("books") or 0) < 3:
            continue
        if any("questionable" in f or "not the listed starter" in f for f in (b.get("flags") or [])):
            continue
        gap = abs(b["p_model"] - (b.get("p_market") or b["p_model"]))
        if gap > BOT_MAX_GAP:
            continue
        mev = model_ev(b)
        if mev is None or mev < BOT_MIN_EDGE:
            continue
        agree, chk = research_check(b, G[b["game_id"]])
        if agree is False:
            continue
        b["check"] = chk
        out.append({"check": chk, "id": b["id"], "label": b["label"], "mu": b["mu"], "kick": b["kick"], "kind": b["kind"], "group": b["group"], "odds": b["odds"],
                    "p": b["p"], "p_model": b["p_model"], "p_market": b.get("p_market"), "model_ev": round(mev, 4), "ev": b["ev"], "price": b["price"],
                    "conf": b.get("conf"), "why": bot_reason(b, G[b["game_id"]]), "game_id": b["game_id"]})
    out.sort(key=lambda x: -x["model_ev"])
    return out


def model_leans(G: dict, board: list[dict]) -> list[dict]:
    """Game-line leans from the simulation ALONE (before it is anchored to the market): where it prefers the
    underdog or the other side of the total, say so, with the market's number beside it."""
    out = []
    by_game: dict = {}
    for b in board:
        if b["kind"] in ("ml", "spread", "total"):
            by_game.setdefault(b["game_id"], {}).setdefault(b["kind"], []).append(b)
    for gid, g in G.items():
        m = g.get("model") or {}
        L = g.get("lines") or {}
        mk = g.get("markets") or {}
        hw = m.get("home_win")
        mh = g.get("market_home_win")
        if hw is not None and mh is not None:
            pick = "home" if hw > mh else "away"
            p_pure = hw if pick == "home" else 1 - hw
            fav = "home" if mh >= 0.5 else "away"
            ml = next((x for x in by_game.get(gid, {}).get("ml", []) if x["side"] == pick), None)
            if ml and ml.get("odds"):
                ev = p_pure * (ml["odds"] - 1) - (1 - p_pure)
                out.append({"game_id": gid, "mu": f'{g["away"]} @ {g["home"]}', "kick": g.get("kickoff_utc") or "", "kind": "ml", "side": pick, "team": g[pick],
                            "label": f"{g[pick]} moneyline" + (" (underdog)" if pick != fav else ""), "odds": ml["odds"], "p_pure": round(p_pure, 4), "p_market": round(mh if pick == "home" else 1 - mh, 4),
                            "p": ml["p"], "ev_pure": round(ev, 4), "ev": ml["ev"], "underdog": pick != fav, "id": ml["id"],
                            "why": f"Simulation alone: {g[pick]} wins {p_pure*100:.0f}% (market {(mh if pick == 'home' else 1-mh)*100:.0f}%); projected score {g['home']} {mk.get('home_pts', 0):.1f}, {g['away']} {mk.get('away_pts', 0):.1f}; model margin {g['home']} {m.get('margin', 0):+.1f} vs line {g['home']} {-(L.get('spread') or 0):+g}"})
        if m.get("margin") is not None and L.get("spread") is not None:
            diff = m["margin"] - L["spread"]
            side = "home" if diff > 0 else "away"
            sp = next((x for x in by_game.get(gid, {}).get("spread", []) if x["side"] == side), None)
            if sp and abs(diff) >= 2.0:
                out.append({"game_id": gid, "mu": f'{g["away"]} @ {g["home"]}', "kick": g.get("kickoff_utc") or "", "kind": "spread", "side": side, "team": g[side],
                            "label": sp["label"], "odds": sp["odds"], "p_pure": None, "p_market": sp.get("p_market"), "p": sp["p"], "ev_pure": None, "ev": sp["ev"], "underdog": (side == "home") == ((L["spread"] or 0) < 0), "id": sp["id"],
                            "why": f"Simulation alone has {g['home']} by {m['margin']:+.1f}, {abs(diff):.1f} points {'better' if diff > 0 else 'worse'} for {g['home']} than the line {g['home']} {-(L['spread']):+g}"})
        if m.get("total") is not None and L.get("total") is not None:
            diff = m["total"] - L["total"]
            side = "over" if diff > 0 else "under"
            to = next((x for x in by_game.get(gid, {}).get("total", []) if x["side"] == side), None)
            if to and abs(diff) >= 3.0:
                out.append({"game_id": gid, "mu": f'{g["away"]} @ {g["home"]}', "kick": g.get("kickoff_utc") or "", "kind": "total", "side": side, "team": None,
                            "label": to["label"], "odds": to["odds"], "p_pure": None, "p_market": to.get("p_market"), "p": to["p"], "ev_pure": None, "ev": to["ev"], "underdog": False, "id": to["id"],
                            "why": f"Simulation alone totals {m['total']:.1f}, {abs(diff):.1f} points {'above' if diff > 0 else 'below'} the market's {L['total']}"})
    out = [x for x in out if x["p_pure"] is None or abs(x["p_pure"] - x["p_market"]) <= BOT_MAX_GAP]
    out.sort(key=lambda x: -(x["ev_pure"] if x["ev_pure"] is not None else x["ev"]))
    return out




def alt_lines(board: list[dict], G: dict) -> list[dict]:
    """Alternate lines the simulation can price: the model's probability at the alternate line, the market's view
    moved to that line (the consensus shift), and the blended chance with fair odds. DraftKings' alt prices are not
    in the feed, so each card says to check them."""
    out = []
    seen = set()
    for b in board:
        k = b["kind"]
        if k not in ALT_STEPS or b.get("p_model") is None or b.get("line") is None:
            continue
        key = (k, b["game_id"], b.get("who") or "")
        if key in seen:
            continue
        seen.add(key)
        g = G[b["game_id"]]
        D = _dist_for(b, g)
        shift = (b.get("inputs") or {}).get("shift")
        if D is None or shift is None:
            continue
        base = b["line"] if k != "spread" or b["side"] == "home" else -b["line"]   # stat terms: home margin
        for step in ALT_STEPS[k]:
            L2 = base + step
            if k in ("recs",) and L2 < 0.5:
                continue
            if k in ("qb_yds", "rec_yds", "rush_yds") and L2 < 5:
                continue
            o_m, pu_m, u_m = D.at(L2, 0.0)
            o_k, pu_k, u_k = D.at(L2, shift)
            for side in ("over", "under"):
                pm = o_m if side == "over" else u_m
                pk = o_k if side == "over" else u_k
                pu = pu_m
                two_m = pm / (1 - pu) if (1 - pu) > 0 else pm
                two_k = pk / (1 - pu_k) if (1 - pu_k) > 0 else pk
                fair2, nudge, note = _nudge(k, two_k, two_m)
                p = fair2 * (1 - pu_k)
                if p < 0.30 or p > 0.80:
                    continue
                if k == "spread":
                    hl = -L2
                    sd = "home" if side == "over" else "away"
                    team = g[sd]
                    label = f"{team} {(hl if sd == 'home' else -hl):+g} (alt)"
                    line = hl if sd == "home" else -hl
                else:
                    sd = side
                    unit = {"total": "", "h1": "1H ", "qb_yds": " pass yds", "rec_yds": " rec yds", "rush_yds": " rush yds", "recs": " receptions"}[k]
                    label = (f"{b['who']} {sd} {L2:g}{unit} (alt)" if b.get("who") else f"{'1H ' if k == 'h1' else ''}{sd.capitalize()} {L2:g} (alt)")
                    line = L2
                out.append({"id": f"alt|{k}|{b['game_id']}|{sd}|{L2:g}|{b.get('who') or ''}", "game_id": b["game_id"], "mu": b["mu"], "kick": b["kick"], "kind": k,
                            "market": b["market"] + " (alternate line)", "side": sd, "line": line, "who": b.get("who"), "team": b.get("team") if k != "spread" else team, "label": label,
                            "odds": None, "p": round(p, 4), "push": round(pu_k, 4), "p_market": round(pk, 4), "p_model": round(pm, 4), "nudge": round(nudge, 4), "note": note,
                            "fair_odds": round((1 - pu_k) / p, 3) if p > 0 else None, "breakeven": None, "ev": None, "good": False, "excluded": "no DraftKings price",
                            "need": 0.02, "books": b.get("books"), "confidence": "low", "flags": list(b.get("flags") or []), "one_sided": False, "priced_at": b.get("priced_at"),
                            "group": "alts", "tier": b.get("tier"), "conf": {"score": max(20, (b.get("conf") or {}).get("score", 50) - 20), "label": "low"}, "price": "no price",
                            "base": {"label": b["label"], "line": b["line"], "odds": b["odds"], "p": b["p"]},
                            "analysis": {"proj": (b.get("analysis") or {}).get("proj"), "range": (b.get("analysis") or {}).get("range"),
                                         "reasons": [f"Alternate line {step:+g} from DraftKings' main line ({b['label']} at {b['odds']}); the market's view is the consensus shift ({shift:+.1f}) applied to the simulation's distribution at this line"] + ((b.get("analysis") or {}).get("reasons") or [])[:3],
                                         "formula": [f"P({sd} {L2:g}) = share of the simulated distribution {'above' if side == 'over' else 'below'} {L2:g}: simulation {pm*100:.1f}%, market-shifted {pk*100:.1f}%, blended {p*100:.1f}% → fair odds {(1-pu_k)/p:.2f}"],
                                         "limits": ["DraftKings' alternate-line price is not in the odds feed: bet it only if DraftKings pays more than the fair odds shown"] + ((b.get("analysis") or {}).get("limits") or []),
                                         "risk": (b.get("analysis") or {}).get("risk"), "personnel": (b.get("analysis") or {}).get("personnel") or [], "stamps": (b.get("analysis") or {}).get("stamps") or {}}})
    out.sort(key=lambda x: -x["p"])
    return out


CATEGORIES = [
    ("passing", "Passing yards and TD passes", ("qb_yds", "qb_td"), 4),
    ("receiving", "Receiving yards and receptions", ("rec_yds", "recs"), 4),
    ("rushing", "Rushing yards", ("rush_yds",), 4),
    ("totals", "Game and half totals", ("total", "h1", "h2"), 4),
    ("moneyline", "Moneyline", ("ml",), 4),
    ("spread", "Spread", ("spread",), 4),
    ("fieldgoals", "Kicker field goals", ("fg",), 2),
]
COMBINE_LEGS = 6
COMBINE_ODDS = (1.40, 2.30)
SEASON_CUTOFF = "-08-01"


def _season_games(prof: dict, season: int) -> list[dict]:
    return [x for x in (prof.get("last_games") or []) if x.get("date", "") >= f"{season}{SEASON_CUTOFF}"]


def judge(b: dict, g: dict, meta: dict, season: int) -> dict:
    """Score the bet the way an analyst would, and record every check.
    Returns {"score", "checks": [{"name", "ok": True/False/None, "txt"}], "hard_fail": str|None}."""
    k = b["kind"]; side = b.get("side")
    checks: list[dict] = []
    score = float(b["p"])
    hard = None
    over_type = side in ("over", "home", "away", "yes")       # for props "over"; for ML/spread handled separately
    sd = _side_of(b, g)
    opp = None if sd is None else ("away" if sd == "home" else "home")
    R = g.get("research") or {}
    rs, ro = (R.get(sd) or {}) if sd else {}, (R.get(opp) or {}) if opp else {}
    rd_ = ((ro.get("adv") or {}).get("rank_def") or {})
    L = g.get("lines") or {}
    spread = L.get("spread")
    wx = g.get("weather") or {}
    outdoors = (g.get("roof") or "") in ("outdoors", "open")
    windy = outdoors and (wx.get("wind") or 0) >= 15
    lg = meta.get("league") or {}

    def add(name, ok, txt, w_ok=0.0, w_bad=0.0):
        nonlocal score
        checks.append({"name": name, "ok": ok, "txt": txt})
        if ok is True:
            score += w_ok
        elif ok is False:
            score += w_bad

    # ---- hard checks
    if b.get("excluded") and b.get("excluded") != "no DraftKings price":
        hard = b["excluded"]
    for f_ in (b.get("flags") or []):
        if "questionable" in f_ or "not the listed starter" in f_:
            hard = f_
    if (b.get("conf") or {}).get("label") == "low" and k != "fg" and b.get("excluded") != "no DraftKings price":
        hard = hard or "low evidence confidence"
    pm, pk = b.get("p_model"), b.get("p_market")
    if pm is not None and pk is not None:
        gap = abs(pm - pk)
        add("Simulation vs market", gap <= 0.10, f"simulation {pm*100:.0f}% vs market {pk*100:.0f}% ({gap*100:.0f} points apart)", 0.03, -0.5 * gap)
        if gap > BOT_MAX_GAP:
            hard = hard or "simulation and market too far apart"
    elif k != "fg":
        if pm is None:
            add("Simulation vs market", None, "no independent projection for this player: market only", 0, -0.03)
        else:
            add("Simulation vs market", None, "no DraftKings price in the feed: simulation only, compare DraftKings' line by hand", 0, -0.03)
    mev = model_ev(b)
    if mev is not None:
        add("Simulation's edge at the price", mev >= 0.03, f"simulation's own EV at DraftKings' price {mev*100:+.1f}%", 0.5 * max(mev, 0), 0.0)
    # ---- market-specific checks
    if k in ("qb_yds", "qb_td"):
        q = ((g.get("qb") or {}).get(sd) or {}) if sd else {}
        prof = q.get("profile") or {}
        sg = _season_games(prof, season)
        stat = "yds" if k == "qb_yds" else "td"
        if len(sg) >= 3 and b.get("line") is not None:
            hits = sum(1 for x in sg if (x[stat] > b["line"]) == (side == "over"))
            rate = hits / len(sg)
            avg = sum(x[stat] for x in sg) / len(sg)
            add("Season form vs the line", rate >= 0.6 if rate >= 0.6 or rate <= 0.4 else None,
                f"{side} {b['line']} hit in {hits} of {len(sg)} starts this season (average {avg:.1f})", 0.05, -0.10)
            if rate <= 0.34:
                hard = hard or "this season's form points the other way"
        else:
            add("Season form vs the line", None, f"only {len(sg)} starts this season", 0, 0)
        r = rd_.get("epa_pass")
        if r:
            good = (r >= 20) if side == "over" else (r <= 12)
            bad = (r <= 12) if side == "over" else (r >= 20)
            add("Matchup", True if good else (False if bad else None), f"{g[opp]} pass defense ranks {_ordinal(r)} by EPA", 0.03, -0.03)
        if spread is not None and sd:
            fav = (sd == "home") == (spread > 0)
            trailing = not fav and abs(spread) >= 3
            leading = fav and abs(spread) >= 3
            if k == "qb_yds":
                ok = (trailing if side == "over" else leading) if (trailing or leading) else None
                add("Game script", ok, f"{g[sd]} {'underdog' if not fav else 'favourite'} by {abs(spread):g}: {'more' if trailing else ('fewer' if leading else 'normal')} late passing expected", 0.03, -0.03)
        if windy:
            add("Weather", side == "under", f"wind {wx['wind']:.0f} mph at kickoff", 0.03, -0.05)
        else:
            add("Weather", None, "no wind effect", 0, 0)
        rows = _inj(g, sd, ("WR", "TE")) if sd else []
        if rows:
            add("Receivers available", side == "under", f"out / DNP: {_inj_txt(rows, 3)}", 0.02, -0.04)
        else:
            add("Receivers available", True, "no receiver on the report as out or DNP", 0.0, 0)
        if q.get("change"):
            add("Quarterback", False, "new starter this season: thin sample", 0, -0.05)
        else:
            add("Quarterback", True, f"{q.get('name')} confirmed starter", 0, 0)
    elif k in ("rec_yds", "recs", "rush_yds"):
        at = next((x for x in (g.get("anytime") or {}).get(sd or "", []) if same_player(x.get("name") or "", b.get("who") or "")), None)
        pl = next((x for x in (g.get("props") or {}).get(sd or "", []) if same_player(x.get("name") or "", b.get("who") or "")), None)
        u = (pl or {}).get("usage") or {}
        rec = [x for x in ((at or {}).get("recent") or []) if x.get("date", "") >= f"{season}{SEASON_CUTOFF}"][-4:]
        if rec and b.get("line") is not None:
            if k == "rush_yds":
                avg_c = sum(x["car"] for x in rec) / len(rec)
                est = avg_c * (u.get("ypc") or 4.0)
                add("Recent usage vs the line", (est > b["line"]) == (side == "over") if abs(est - b["line"]) > 3 else None,
                    f"{avg_c:.1f} carries per game over the last {len(rec)} × {u.get('ypc', 0):.2f} yds per carry ≈ {est:.0f} yds vs line {b['line']}", 0.05, -0.08)
            else:
                avg_t = sum(x["tgt"] for x in rec) / len(rec)
                ypt = (lg.get("ypdb") or 6.2) / (1 - 0.065)
                est = avg_t * ypt if k == "rec_yds" else avg_t * 0.65
                unit = "yds" if k == "rec_yds" else "catches"
                add("Recent usage vs the line", (est > b["line"]) == (side == "over") if abs(est - b["line"]) > (3 if k == "rec_yds" else 0.5) else None,
                    f"{avg_t:.1f} targets per game over the last {len(rec)} ≈ {est:.0f} {unit} ({'league yards per target' if k == 'rec_yds' else 'league catch rate'}) vs line {b['line']}", 0.05, -0.08)
            if at and at.get("snap_trend") is not None:
                tr = at["snap_trend"]
                add("Snap trend", tr >= 1.0 if side == "over" else tr <= 1.0, f"snap share trend ×{tr:.2f} (last three games vs the season)", 0.02, -0.02)
        else:
            add("Recent usage vs the line", None, "no current-season touches recorded", 0, -0.04)
        r = rd_.get("epa_rush" if k == "rush_yds" else "epa_pass")
        if r:
            good = (r >= 20) if side == "over" else (r <= 12)
            bad = (r <= 12) if side == "over" else (r >= 20)
            add("Matchup", True if good else (False if bad else None), f"{g[opp]} {'run' if k == 'rush_yds' else 'pass'} defense ranks {_ordinal(r)} by EPA", 0.03, -0.03)
        if spread is not None and sd:
            fav = (sd == "home") == (spread > 0)
            big = abs(spread) >= 3
            if k == "rush_yds":
                ok = (fav if side == "over" else not fav) if big else None
                add("Game script", ok, f"{g[sd]} {'favourite' if fav else 'underdog'} by {abs(spread):g}: {'more' if fav else 'fewer'} carries with a lead", 0.03, -0.03)
            else:
                ok = ((not fav) if side == "over" else fav) if big else None
                add("Game script", ok, f"{g[sd]} {'underdog' if not fav else 'favourite'} by {abs(spread):g}: {'more' if not fav else 'fewer'} late passes expected", 0.02, -0.02)
        mates = [i for i in _inj(g, sd, ("RB", "WR", "TE")) if not same_player(i.get("name") or "", b.get("who") or "")] if sd else []
        big_mates = []
        for i in mates:
            o = next((x for x in (g.get("anytime") or {}).get(sd, []) if same_player(x.get("name") or "", i.get("name") or "")), None)
            if o and ((k == "rush_yds" and o.get("car_share", 0) >= 0.15) or (k != "rush_yds" and o.get("tgt_share", 0) >= 0.10)):
                big_mates.append(f"{o['name']} ({(o.get('car_share') if k == 'rush_yds' else o.get('tgt_share'))*100:.0f}%)")
        if big_mates:
            add("Teammates out", side == "over", "workload could shift from " + ", ".join(big_mates), 0.03, -0.03)
        else:
            add("Teammates out", None, "no major usage teammate out or DNP", 0, 0)
        if windy and k != "rush_yds":
            add("Weather", side == "under", f"wind {wx['wind']:.0f} mph at kickoff", 0.02, -0.04)
        q = ((g.get("qb") or {}).get(sd) or {}) if sd else {}
        if q.get("change") and k != "rush_yds":
            add("Quarterback", False, f"new starter ({q.get('name')}): target distribution uncertain", 0, -0.04)
    elif k in ("ml", "spread"):
        m = g.get("model") or {}
        team_side = "home" if g["home"] == b.get("team") else "away"
        if k == "ml" and m.get("home_win") is not None and g.get("market_home_win") is not None:
            pure = m["home_win"] if team_side == "home" else 1 - m["home_win"]
            mkt = g["market_home_win"] if team_side == "home" else 1 - g["market_home_win"]
            add("Simulation alone agrees", pure >= mkt - 0.02, f"simulation alone {pure*100:.0f}% vs market {mkt*100:.0f}% for {b['team']}", 0.03, -0.04)
        if k == "spread" and m.get("margin") is not None and spread is not None:
            diff = (m["margin"] - spread) * (1 if team_side == "home" else -1)
            add("Simulation alone agrees", diff > 0, f"simulation margin {g['home']} {m['margin']:+.1f} vs line {g['home']} {-spread:+g}: {abs(diff):.1f} points {'for' if diff > 0 else 'against'} {b['team']}", 0.03, -0.04)
        q = (g.get("qb") or {}).get(team_side) or {}
        qo = (g.get("qb") or {}).get("away" if team_side == "home" else "home") or {}
        add("Quarterbacks", not q.get("change"), f"{b['team']} {q.get('name')}{' (new starter)' if q.get('change') else ''}; opponent {qo.get('name')}{' (new starter)' if qo.get('change') else ''}", 0.0, -0.05)
        ol = _inj(g, team_side, POS_OL); de = _inj(g, team_side, POS_DEF)
        add("Injuries", not (len(ol) + len(de) >= 3), f"{b['team']}: {len(ol)} offensive linemen and {len(de)} defenders out / DNP", 0.0, -0.03)
        rest = g.get("rest") or {}
        if rest.get("home") and rest.get("away"):
            adv = rest[team_side] - rest["away" if team_side == "home" else "home"]
            add("Rest", adv >= 3 if abs(adv) >= 3 else None, f"{b['team']} {rest[team_side]} days vs {rest['away' if team_side == 'home' else 'home']}", 0.02, -0.02)
        r_team = R.get(team_side) or {}
        add("Form", None, f"{b['team']} {r_team.get('record')}, ATS {r_team.get('ats')}, EPA/play offense {r_team.get('epa_off_per_play', 0):+.3f}, defense {r_team.get('epa_def_per_play', 0):+.3f}", 0, 0)
    elif k in ("total", "h1", "h2"):
        m = g.get("model") or {}
        if m.get("total") is not None and L.get("total") is not None:
            diff = m["total"] - L["total"]
            agrees = (diff > 0) == (side == "over")
            add("Simulation alone agrees", agrees if abs(diff) >= 1.5 else None, f"simulation alone {m['total']:.1f} vs market {L['total']}", 0.03, -0.03)
        if windy:
            add("Weather", side == "under", f"wind {wx['wind']:.0f} mph at kickoff", 0.04, -0.06)
        else:
            add("Weather", None, "no weather effect" if not outdoors else f"{wx.get('wind', 0):.0f} mph wind, no effect", 0, 0)
        ex = []
        for s_ in ("home", "away"):
            rr = ((R.get(s_) or {}).get("adv") or {})
            ro_ = rr.get("rank_off") or {}
            if ro_.get("explosive"):
                ex.append(ro_["explosive"])
        if ex:
            avg = sum(ex) / len(ex)
            add("Explosive offenses", avg <= 12 if side == "over" else avg >= 20, f"average explosive-play rank of the two offenses {avg:.0f}", 0.02, -0.02)
        chg = [g[s_] for s_ in ("home", "away") if ((g.get("qb") or {}).get(s_) or {}).get("change")]
        add("Quarterbacks", not chg, "new starter: " + ", ".join(chg) if chg else "both starters established", 0, -0.04)
    elif k == "fg":
        prof = (((g.get("kicker") or {}).get(sd) or {}).get("profile") or {}) if sd else {}
        add("Kicker sample", prof.get("att", 0) >= 10, f"{prof.get('made', 0):.0f} of {prof.get('att', 0):.0f} this season and last", 0.02, -0.05)
        if windy:
            add("Weather", side == "under", f"wind {wx['wind']:.0f} mph at kickoff", 0.03, -0.05)
    # ---- price freshness
    if b.get("priced_at"):
        try:
            age_h = (datetime.now(timezone.utc).timestamp() - _ts_iso(b["priced_at"])) / 3600
            add("Price freshness", age_h <= 12, f"DraftKings price {age_h:.0f} h old", 0.0, -0.03)
        except Exception:  # noqa: BLE001
            pass
    conf = ((b.get("conf") or {}).get("score") or 50) / 100
    score += 0.10 * (conf - 0.5)
    return {"score": round(score, 4), "checks": checks, "hard_fail": hard,
            "passed": sum(1 for c in checks if c["ok"] is True), "failed": sum(1 for c in checks if c["ok"] is False)}


def category_picks(board: list[dict], G: dict, meta: dict, season: int) -> dict:
    """The best N bets per category by judgment score, one per player/market, at most two per game per
    category, no hard failures, no anytime-touchdown markets."""
    out = {}
    for key, label, kinds, n in CATEGORIES:
        cands = [b for b in board if b["kind"] in kinds and b.get("group") != "alts" and b.get("judge") and not b["judge"]["hard_fail"]
                 and not (b.get("excluded") == "no DraftKings price" and key not in ("receiving", "rushing", "fieldgoals"))]
        if key in ("receiving", "rushing") and any(b.get("odds") for b in cands):
            cands = [b for b in cands if b.get("odds")]          # real DraftKings prices first when the feed has them
        if key == "moneyline":
            cands = [b for b in cands if b.get("odds") and b["odds"] >= 1.25]
        cands.sort(key=lambda b: -b["judge"]["score"])
        chosen = []; per_game: dict = {}
        for b in cands:
            if per_game.get(b["game_id"], 0) >= 2:
                continue
            chosen.append(b["id"]); per_game[b["game_id"]] = per_game.get(b["game_id"], 0) + 1
            if len(chosen) >= n:
                break
        out[key] = {"label": label, "n": n, "ids": chosen}
    return out


def combine_top(board: list[dict], cats: dict) -> dict:
    """The bot's top six from the category lists: real DraftKings prices between 1.40 and 2.30, one per game,
    ranked by judgment score."""
    by_id = {b["id"]: b for b in board}
    pool = []
    for key, c in cats.items():
        if key == "fieldgoals":
            continue
        for i in c["ids"]:
            b = by_id.get(i)
            if b and b.get("odds") and COMBINE_ODDS[0] <= b["odds"] <= COMBINE_ODDS[1]:
                pool.append(b)
    pool.sort(key=lambda b: -b["judge"]["score"])
    legs = []; used = set()
    for b in pool:
        if b["game_id"] in used:
            continue
        legs.append({**{k: b.get(k) for k in ("id", "game_id", "label", "mu", "kick", "odds", "p", "p_model", "p_market", "ev", "price", "kind", "fair_odds", "group")},
                     "basis": f"judgment score {b['judge']['score']:.2f}: {b['judge']['passed']} checks passed, {b['judge']['failed']} failed",
                     "why": "; ".join(c["txt"] for c in b["judge"]["checks"] if c["ok"] is True)[:220]})
        used.add(b["game_id"])
        if len(legs) >= COMBINE_LEGS:
            break
    prob = 1.0; odds = 1.0
    for l in legs:
        prob *= l["p"]; odds *= l["odds"]
    return {"legs": legs, "n": len(legs), "odds": round(odds, 2), "odds_is_estimate": False, "prob": round(prob, 4),
            "fair_odds": round(1 / prob, 2) if prob > 0 else None, "ev": round(prob * odds - 1, 4) if legs else None, "complete": len(legs) == COMBINE_LEGS,
            "min_p": 0, "odds_band": list(COMBINE_ODDS), "n_candidates": len(pool)}


def td_board(board: list[dict], G: dict) -> list[dict]:
    """Every anytime-touchdown price DraftKings posts, every team, with the blended and simulation chances."""
    out = []
    for b in board:
        if b["kind"] != "atd" or not b.get("odds"):
            continue
        g = G[b["game_id"]]
        sd = _side_of(b, g)
        at = next((x for x in (g.get("anytime") or {}).get(sd or "", []) if same_player(x.get("name") or "", b.get("who") or "")), None)
        out.append({"id": b["id"], "game_id": b["game_id"], "mu": b["mu"], "kick": b["kick"], "who": b["who"], "team": b.get("team") or (g[sd] if sd else ""),
                    "pos": (at or {}).get("pos") or "", "odds": b["odds"], "p": b["p"], "p_model": b.get("p_model"), "p_market": b.get("p_market"), "ev": b["ev"], "price": b["price"],
                    "rz": (at or {}).get("rz_share"), "td_games": (at or {}).get("td_games"), "games": (at or {}).get("games"), "flags": b.get("flags") or []})
    out.sort(key=lambda x: (x["kick"], x["mu"], -x["p"]))
    return out


def projected_props(G: dict, meta: dict, season: int, kinds=("rec_yds", "recs", "rush_yds")) -> list[dict]:
    """Receiving / rushing props the odds feed did not price: a card per player at the simulation's fair line,
    with the side the recent usage points to, so the viewer can compare DraftKings' line by hand."""
    out = []
    lg = meta.get("league") or {}
    for gid, g in G.items():
        for sd in ("home", "away"):
            opp = "away" if sd == "home" else "home"
            for x in (g.get("props") or {}).get(sd, []):
                at = next((a for a in (g.get("anytime") or {}).get(sd, []) if same_player(a.get("name") or "", x["name"])), None)
                rec = [r for r in ((at or {}).get("recent") or []) if r.get("date", "") >= f"{season}{SEASON_CUTOFF}"][-4:]
                u = x.get("usage") or {}
                for k in kinds:
                    d = x.get(k)
                    if not d or d.get("fair_line") is None or d["q"][2] < (2.5 if k == "recs" else 25):
                        continue
                    line = d["fair_line"]
                    if rec:
                        if k == "rush_yds":
                            est = sum(r["car"] for r in rec) / len(rec) * (u.get("ypc") or 4.0)
                        elif k == "rec_yds":
                            est = sum(r["tgt"] for r in rec) / len(rec) * (lg.get("ypdb") or 6.2) / (1 - 0.065)
                        else:
                            est = sum(r["tgt"] for r in rec) / len(rec) * 0.65
                        side = "over" if est > line else "under"
                    else:
                        side = "over"
                    D = Dist(d["pmf"][0], d["pmf"][1], float(d.get("step", 1.0)))
                    o, pu, un = D.at(line, 0.0)
                    p = o if side == "over" else un
                    unit = {"rec_yds": " rec yds", "rush_yds": " rush yds", "recs": " receptions"}[k]
                    b = {"id": f"proj|{k}|{gid}|{side}|{line:g}|{x['name']}", "game_id": gid, "mu": f'{g["away"]} @ {g["home"]}', "kick": g.get("kickoff_utc") or "",
                         "kind": k, "market": LABEL[k] + " (projection, no DraftKings line in the feed)", "side": side, "line": line, "who": x["name"], "team": g[sd],
                         "label": f"{x['name']} {side} {line:g}{unit} (sim line)", "odds": None, "p": round(p, 4), "push": round(pu, 4), "p_market": None, "p_model": round(p, 4),
                         "nudge": 0.0, "note": "simulation only: the odds feed pulled no DraftKings price for this market", "fair_odds": round((1 - pu) / p, 3) if p > 0 else None,
                         "breakeven": None, "ev": None, "good": False, "excluded": "no DraftKings price", "need": 0.02, "books": 0, "confidence": "low",
                         "flags": (["questionable"] if x.get("q") else []), "one_sided": False, "priced_at": None, "group": "props", "tier": g.get("tier"),
                         "conf": {"score": 45, "label": "low"}, "price": "no price"}
                    b["analysis"] = analyze(b, g, meta)
                    b["analysis"]["limits"] = ["DraftKings' line for this market is not in the odds feed this week (the site pulls three prop markets per game on the free plan). Compare DraftKings' line with the projection: lean over if DraftKings' line sits well below it, under if well above."] + (b["analysis"].get("limits") or [])
                    out.append(b)
    return out


# ---------------------------------------------------------------------------- the payload block
MAX_ALTS = 60
KEEP_EXTRA = 24         # kicker and projected-prop cards kept beyond the category picks
KEEP_ANALYSIS = 12          # anytime-touchdown bets beyond the good ones carry no analysis (the TD board is a table)


def annotate(b: dict, g: dict, meta: dict) -> None:
    """Price age, group, evidence confidence, price label, data tier, flags and the analysis on one bet from value.py."""
    O = g.get("odds") or {}
    b["priced_at"] = O.get("props_fetched") if b["kind"] in PROP_KINDS else O.get("fetched")
    if b["kind"] in ("qb_yds", "qb_td") and b.get("who"):
        starters = [(g.get("qb") or {}).get(s_, {}).get("name") or "" for s_ in ("home", "away")]
        if not any(same_player(n, b["who"]) for n in starters):
            b["flags"] = list(b.get("flags") or []) + [f"{b['who']} is not the listed starter ({' / '.join(n for n in starters if n)}): the bet voids if he does not play"]
            b["excluded"] = b.get("excluded") or "not the listed starter"
            b["good"] = False
    if b.get("p_model") is None and b.get("who"):
        b["flags"] = [x for x in (b.get("flags") or []) if "not in the model" not in x] + ["market-derived: no independent player projection"]
    b["group"] = GROUP.get(b["kind"], "props")
    b["tier"] = g.get("tier")
    b["conf"] = confidence(b, g)
    b["price"] = price_label(b)


def bot_block(payload: dict) -> dict:
    """payload["bot"]: the bot's picks, leans, category lists, combined top six, anytime-TD board, and the extra
    cards (kicker props, projected props, alternate lines) the Best bets tab shows beside value.py's ranked bets.
    Also annotates every ranked bet in place (conf, price, analysis, judge)."""
    now = _now()
    bb = payload.get("best_bets") or {}
    board = bb.get("ranked") or []
    G = {g["game_id"]: g for g in payload.get("games", [])}
    meta = dict(payload.get("meta") or {}); meta["generated_utc"] = payload.get("generated_utc")
    season = int(payload.get("season") or 0)
    n_atd = 0
    for b in board:
        g = G.get(b["game_id"])
        if g is None:
            continue
        annotate(b, g, meta)
        if b["kind"] == "atd":
            n_atd += 1
            if b.get("good") or n_atd <= KEEP_ANALYSIS:
                b["analysis"] = analyze(b, g, meta)
            continue
        b["analysis"] = analyze(b, g, meta)
        b["judge"] = judge(b, g, meta, season)
    picks = bot_picks(board, G)
    leans = model_leans(G, board)
    alts = alt_lines(board, G)[:MAX_ALTS]
    up = {gid: g for gid, g in G.items() if not _started(g, now)}
    extra: list[dict] = []
    for g in up.values():
        extra.extend(kicker_props(g, meta))
    have = {b["kind"] for b in board if b.get("odds")}
    missing = tuple(k for k in ("rec_yds", "recs", "rush_yds") if k not in have)
    if missing:
        extra.extend(projected_props(up, meta, season, missing))
    for b in extra:
        b["judge"] = judge(b, G[b["game_id"]], meta, season)
    full = board + extra
    cats = category_picks(full, G, meta, season)
    combine = combine_top(full, cats)
    tds = td_board(board, G)
    # the page carries the category picks plus the strongest of the rest (size: the week file is embedded in the page)
    keep = {i for c in cats.values() for i in c["ids"]}
    for grp, n in (("kickers", KEEP_EXTRA), ("props", KEEP_EXTRA)):
        rows = sorted((b for b in extra if b["group"] == grp and not b["judge"]["hard_fail"]), key=lambda b: -b["judge"]["score"])
        keep.update(b["id"] for b in rows[:n])
    extra = [b for b in extra if b["id"] in keep]
    for b in alts:
        A = b.get("analysis") or {}
        b["analysis"] = {"proj": A.get("proj"), "range": A.get("range"), "reasons": (A.get("reasons") or [])[:2], "formula": A.get("formula") or [],
                         "limits": (A.get("limits") or [])[:1], "risk": A.get("risk"), "personnel": [], "stamps": A.get("stamps") or {}}
    src = {x.get("name", ""): x for x in (meta.get("sources") or [])}
    stamps = {"model": meta.get("generated_utc"), "weather": meta.get("generated_utc"),
              "injuries": next((v.get("fetched") for k, v in src.items() if k.startswith("Official injury")), None),
              "usage": next((v.get("fetched") for k, v in src.items() if k.startswith("Snap")), None),
              "data_through": meta.get("data_through")}
    return {"v": 1, "generated": now, "week_label": week_label(payload), "lines_at": bb.get("odds_fetched"), "props_at": bb.get("props_fetched_oldest"),
            "stamps": stamps, "extra": [slim(b, False) for b in extra + alts], "picks": picks[:40], "leans": leans[:20],
            "cats": cats, "combine": combine, "tds": tds,
            "rules": {"min_edge": BOT_MIN_EDGE, "max_gap": BOT_MAX_GAP, "odds": list(BOT_ODDS), "combine_odds": list(COMBINE_ODDS), "legs": COMBINE_LEGS,
                      "categories": [{"key": k, "label": l, "kinds": list(ks), "n": n} for k, l, ks, n in CATEGORIES],
                      "good_ev": GOOD_EV, "good_ev_atd": GOOD_EV_ATD, "min_books": MIN_BOOKS, "nudge_cap": NUDGE_CAP, "atd_max_odds": ATD_MAX_ODDS}}


__all__ = ["bot_block", "annotate", "judge", "category_picks", "combine_top", "td_board", "analyze"]
