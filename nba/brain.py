"""The NBA bot's judgment: an analyst's checks on every DraftKings bet, the best per category, the combined top five,
and the projection cards for props the feed did not price. Reads the payload only."""
from __future__ import annotations

from datetime import datetime, timezone

CATEGORIES = [("points", "Points", ("pts",), 4), ("rebounds", "Rebounds", ("reb",), 4), ("assists", "Assists", ("ast",), 4), ("threes", "Three-pointers", ("threes",), 3),
              ("pra", "Points + rebounds + assists", ("pra",), 3), ("moneyline", "Moneyline", ("ml",), 3), ("spread", "Spread", ("spread",), 3), ("totals", "Game totals", ("total",), 3)]
COMBINE_LEGS = 5
COMBINE_ODDS = (1.35, 2.20)
BOT_MAX_GAP = 0.15
KEEP_EXTRA = 40


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def _ordinal(n) -> str:
    n = int(n)
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def confidence(b: dict, g: dict, pl: dict | None) -> dict:
    score = 55.0
    n = b.get("books") or 0
    score += min(n, 6) * 4 - 8
    pm, pk = b.get("p_model"), b.get("p_market")
    if pm is not None and pk is not None and b.get("kind") not in ("total",):
        d = abs(pm - pk)
        score += 8 if d < 0.05 else (0 if d < 0.10 else (-10 if d < 0.20 else -18))
    if pl:
        score += 6 if pl.get("games", 0) >= 10 else (0 if pl.get("games", 0) >= 4 else -10)
        if pl.get("q"):
            score -= 12
    if b.get("kind") == "total":
        score -= 6
    score = max(5, min(97, score))
    return {"score": round(score), "label": "high" if score >= 72 else ("medium" if score >= 50 else "low")}


def price_label(b: dict) -> str:
    ev = b.get("ev") or 0
    if not b.get("odds"):
        return "no price"
    return "attractive" if ev >= 0.02 else ("fair" if ev >= -0.03 else "poor")


def analyze(b: dict, g: dict, pl: dict | None, meta: dict) -> dict:
    k = b["kind"]; side = b["side"]
    R = g.get("research") or {}
    tside = "home" if g["home"] == b.get("team") else ("away" if g["away"] == b.get("team") else None)
    opp = "away" if tside == "home" else "home"
    reasons, formula, limits, risks = [], [], [], []
    proj = None; rng = None
    m = g.get("model") or {}
    if k in ("ml", "spread", "total"):
        for s_ in ("away", "home"):
            r = R.get(s_) or {}
            reasons.append(f"{g[s_]} ({r.get('record')}): offensive rating {r.get('ortg')}, defensive rating {r.get('drtg')}, pace {r.get('pace')} (league {meta.get('league', {}).get('ortg')} / {meta.get('league', {}).get('pace')}), {r.get('games')} games this season")
        proj = f"model: {g['home']} {m.get('home_pts')}, {g['away']} {m.get('away_pts')} (margin {g['home']} {m.get('margin'):+}, total {m.get('total')}, pace {m.get('pace')})"
        if k == "ml":
            formula.append(f"P({b['team']} wins) = Φ(expected margin ÷ 12.6) = {b['p_model']*100:.1f}%; DraftKings' price with the vig removed = {(b.get('p_market') or 0)*100:.1f}%")
        elif k == "spread":
            formula.append(f"P(cover) = Φ((expected margin {m.get('margin'):+} + line {b['line']:+g} for {b['team']}) ÷ 12.6) = {b['p_model']*100:.1f}%")
        else:
            formula.append(f"P({side} {b['line']}) = Φ((model total {m.get('total')} − {b['line']}) ÷ 18.5) = {b['p_model']*100:.1f}% (DraftKings' prices on the total are not in ESPN's feed: 1.91 each side assumed)")
        for s_ in ("away", "home"):
            outs = [i for i in (g.get("injuries") or {}).get(g[s_], []) if (i.get("status") or "").lower() in ("out", "doubtful")]
            if outs:
                reasons.append(f"{g[s_]} out / doubtful: " + ", ".join(f"{i['name']} ({i.get('injury') or ''})".replace(" ()", "") for i in outs[:5]))
        limits.append("Ratings are box-score based (points per 100 possessions, pace), adjusted for opponents and shrunk toward the league; no lineup-level model yet")
    else:
        st = ((pl or {}).get("stats") or {}).get(k) or {}
        if pl:
            proj = f"model: {st.get('mean')} {k} on {pl.get('minutes')} minutes (sd {st.get('sd')}); season average {st.get('season_avg') if st.get('season_avg') is not None else 'n/a'}, last season {st.get('prior_avg') if st.get('prior_avg') is not None else 'n/a'}"
            last = pl.get("last") or []
            if last:
                reasons.append(f"Last {len(last)}: " + ", ".join(f"{x.get(k)} in {x.get('min'):.0f} min vs {x.get('opp')}" for x in last[-5:]))
            ro = (R.get(opp) or {}) if opp else {}
            reasons.append(f"Opponent {g[opp] if opp else ''}: defensive rating {ro.get('drtg')}, pace {ro.get('pace')}; game pace projected {m.get('pace')} (league {meta.get('league', {}).get('pace')})")
            if g.get("lines", {}).get("spread") is not None:
                sp = abs(float(g["lines"]["spread"]))
                if sp >= 10:
                    risks.append((60, f"Spread of {sp:g}: a blowout trims starters' fourth-quarter minutes (the model applies 8%)"))
            formula.append(f"Mean = minutes {pl.get('minutes')} × rate per minute × pace and opponent adjustments = {st.get('mean')}; P({side} {b['line']}) = Φ(({st.get('mean')} − {b['line']}) ÷ {st.get('sd')}) = {b['p_model']*100:.1f}%" + (f"; market consensus {b['p_market']*100:.1f}% over {b.get('books')} books" if b.get("p_market") is not None else ""))
            if pl.get("q"):
                risks.append((85, f"{pl['name']} is on the injury report as questionable or day-to-day: confirm he plays"))
            if pl.get("games", 0) < 4:
                risks.append((55, f"Only {pl.get('games')} games this season: last season's rates carry most of the weight"))
        limits.append("Usage shifts from teammates out are not modelled yet: when a starter sits, the players who inherit his minutes are under-projected")
    risks.sort(key=lambda x: -x[0])
    return {"proj": proj, "range": rng, "reasons": reasons[:8], "formula": formula, "limits": limits,
            "risk": risks[0][1] if risks else "No specific risk flagged beyond ordinary game variance", "personnel": [], "stamps": {"model": meta.get("generated_utc"), "odds": (g.get("odds") or {}).get("props_fetched")}}


def judge(b: dict, g: dict, pl: dict | None) -> dict:
    checks = []; score = float(b["p"]); hard = None

    def add(name, ok, txt, w_ok=0.0, w_bad=0.0):
        nonlocal score
        checks.append({"name": name, "ok": ok, "txt": txt})
        if ok is True:
            score += w_ok
        elif ok is False:
            score += w_bad
    pm, pk = b.get("p_model"), b.get("p_market")
    if pm is not None and pk is not None and b["kind"] != "total":
        gap = abs(pm - pk)
        add("Model vs market", gap <= 0.10, f"model {pm*100:.0f}% vs market {pk*100:.0f}% ({gap*100:.0f} points apart)", 0.03, -0.5 * gap)
        if gap > BOT_MAX_GAP:
            hard = "model and market too far apart"
    if pl:
        add("Availability", not pl.get("q"), "questionable / day-to-day" if pl.get("q") else "not on the injury report", 0.0, -0.06)
        if pl.get("q"):
            hard = hard or "questionable"
        add("Sample", pl.get("games", 0) >= 4, f"{pl.get('games')} games this season", 0.02, -0.04)
        last = pl.get("last") or []
        k = b["kind"]
        if len(last) >= 3 and b.get("line") is not None:
            hits = sum(1 for x in last if (x.get(k, 0) > b["line"]) == (b["side"] == "over"))
            rate = hits / len(last)
            add("Recent form vs the line", rate >= 0.6 if rate >= 0.6 or rate <= 0.4 else None, f"{b['side']} {b['line']} hit in {hits} of the last {len(last)}", 0.04, -0.08)
            if rate <= 0.25:
                hard = hard or "recent form points the other way"
    if b["kind"] == "total":
        add("Price", None, "DraftKings' total prices are not in the feed (1.91 assumed)", 0, -0.02)
    if b.get("odds") and (b.get("ev") or 0) < -0.06:
        add("Price", False, f"EV {b['ev']*100:+.1f}% at DraftKings' price", 0, -0.03)
    conf = ((b.get("conf") or {}).get("score") or 50) / 100
    score += 0.10 * (conf - 0.5)
    return {"score": round(score, 4), "checks": checks, "hard_fail": hard, "passed": sum(1 for c in checks if c["ok"] is True), "failed": sum(1 for c in checks if c["ok"] is False)}


def _player(g: dict, b: dict) -> dict | None:
    if not b.get("who"):
        return None
    for s_ in ("home", "away"):
        for x in (g.get("props") or {}).get(s_, []):
            if x.get("id") == b.get("pid") or x.get("name") == b.get("who"):
                return x
    return None


def category_picks(board: list[dict]) -> dict:
    out = {}
    for key, label, kinds, n in CATEGORIES:
        cands = [b for b in board if b["kind"] in kinds and b.get("judge") and not b["judge"]["hard_fail"] and b.get("odds") and b["odds"] >= 1.25]
        cands.sort(key=lambda b: -b["judge"]["score"])
        chosen = []; per_game: dict = {}; per_player: set = set()
        for b in cands:
            pk = (b.get("who") or "", b["kind"])
            if per_game.get(b["game_id"], 0) >= 2 or pk in per_player:
                continue
            chosen.append(b["id"]); per_game[b["game_id"]] = per_game.get(b["game_id"], 0) + 1; per_player.add(pk)
            if len(chosen) >= n:
                break
        out[key] = {"label": label, "n": n, "ids": chosen}
    return out


def combine_top(board: list[dict], cats: dict) -> dict:
    by_id = {b["id"]: b for b in board}
    pool = [by_id[i] for c in cats.values() for i in c["ids"] if i in by_id and by_id[i].get("odds") and COMBINE_ODDS[0] <= by_id[i]["odds"] <= COMBINE_ODDS[1]]
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
    return {"legs": legs, "n": len(legs), "odds": round(odds, 2), "prob": round(prob, 4), "fair_odds": round(1 / prob, 2) if prob > 0 else None,
            "ev": round(prob * odds - 1, 4) if legs else None, "complete": len(legs) == COMBINE_LEGS, "odds_band": list(COMBINE_ODDS), "n_candidates": len(pool)}


def bot_block(payload: dict, extra: list[dict]) -> dict:
    now = _now()
    board = (payload.get("best_bets") or {}).get("ranked") or []
    G = {g["game_id"]: g for g in payload.get("games", [])}
    meta = dict(payload.get("meta") or {}); meta["generated_utc"] = payload.get("generated_utc")
    for b in board + extra:
        g = G.get(b["game_id"])
        if g is None:
            continue
        pl = _player(g, b)
        b["tier"] = "A" if (g.get("research") or {}).get("home", {}).get("games", 0) >= 10 else "B"
        b["conf"] = confidence(b, g, pl)
        b["price"] = price_label(b)
        b["analysis"] = analyze(b, g, pl, meta)
        b["judge"] = judge(b, g, pl)
    cats = category_picks(board)
    combine = combine_top(board, cats)
    extra = sorted((b for b in extra if not b["judge"]["hard_fail"]), key=lambda b: -b["judge"]["score"])[:KEEP_EXTRA]
    return {"v": 1, "generated": now, "extra": extra, "cats": cats, "combine": combine,
            "stamps": {"model": meta.get("generated_utc"), "odds": (payload.get("best_bets") or {}).get("odds_fetched")},
            "rules": {"combine_odds": list(COMBINE_ODDS), "legs": COMBINE_LEGS, "max_gap": BOT_MAX_GAP, "categories": [{"key": k, "label": l, "kinds": list(ks), "n": n} for k, l, ks, n in CATEGORIES]}}


__all__ = ["bot_block", "judge", "analyze", "category_picks", "combine_top", "CATEGORIES"]
