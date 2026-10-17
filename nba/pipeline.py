"""Build one day's NBA payload: the slate, DraftKings lines, the model's projections, every priced market with its
win chance, the bot's category picks and the research desk.

    payload = build_day("2026-10-20")
"""
from __future__ import annotations

import json
import math
import time
from datetime import datetime, timezone

from .config import CFG, DATA_DIR, MODEL_VERSION, OUT_DIR
from .espn import parse_game, parse_pregame, scoreboard, summary
from .ingest import load_games, season_now
from .model import STATS, Ratings
from .odds import for_game, load as load_odds

KIND_LABEL = {"ml": "Moneyline", "spread": "Spread", "total": "Game total", "pts": "Points", "reb": "Rebounds", "ast": "Assists", "threes": "Three-pointers made",
              "pra": "Points + rebounds + assists"}
UNIT = {"pts": "pts", "reb": "reb", "ast": "ast", "threes": "threes", "pra": "PRA"}
MARGIN_ASSUMED = 0.045       # a one-sided DraftKings price gets this margin removed


def _r(x, n=3):
    return None if x is None else round(float(x), n)


def _nv(a: float | None, b: float | None) -> float | None:
    if a and b and a > 1 and b > 1:
        return (1 / a) / ((1 / a) + (1 / b))
    return None


def _dec_from_prob(p: float) -> float:
    return round(1 / p, 3) if p > 0 else None


def day_games(date: str) -> list[dict]:
    """The day's games with ESPN's header, DraftKings lines, injuries and (for finished games) the box score."""
    out = []
    for ev in scoreboard(date):
        if not ev.get("home") or not ev.get("away"):
            continue
        sm = summary(ev["id"], cache=bool(ev.get("completed")))
        pre = parse_pregame(sm) if sm else {"lines": {}, "injuries": {}}
        g = {"game_id": f'{date.replace("-", "_")}_{ev["away"]}_{ev["home"]}', "espn_id": ev["id"], "date": date, "home": ev["home"], "away": ev["away"],
             "tip_utc": (ev.get("date") or "")[:16] + "Z" if ev.get("date") else None, "state": ev.get("state"), "status": ev.get("status"), "completed": ev.get("completed"),
             "venue": ev.get("venue"), "neutral": ev.get("neutral"), "lines": pre.get("lines") or {}, "injuries": pre.get("injuries") or {}}
        if ev.get("completed") and sm:
            fin = parse_game(sm)
            if fin:
                g["actual"] = {"hs": fin["hs"], "as": fin["as"], "players": {t: {p["id"]: {"name": p["name"], "min": p["min"], "pts": p["pts"], "reb": p["reb"], "ast": p["ast"], "threes": p["tpm"], "pra": p["pts"] + p["reb"] + p["ast"]}
                                                                          for p in rows if not p.get("dnp")} for t, rows in fin["players"].items()}}
        elif ev.get("hs") is not None and ev.get("state") == "in":
            g["live"] = {"hs": ev["hs"], "as": ev["as"], "status": ev.get("status")}
        out.append(g)
    out.sort(key=lambda g: g.get("tip_utc") or "")
    return out


def _out_ids(g: dict, team: str) -> set:
    return {i["id"] for i in (g.get("injuries") or {}).get(team, []) if (i.get("status") or "").lower() in ("out", "doubtful")}


def _questionable(g: dict, team: str) -> set:
    return {i["id"] for i in (g.get("injuries") or {}).get(team, []) if (i.get("status") or "").lower() in ("questionable", "day-to-day", "game time decision")}


def _sel(g, kind, side, label, line, odds, p_market, p_model, who=None, team=None, pid=None, books=None, note="", push=0.0, odds_source="draftkings", inputs=None):
    """One board row in the shape the page, the desk and the scorecard read (ids match the NFL convention)."""
    cfg = CFG
    if p_market is not None and p_model is not None:
        gap = p_model - p_market
        nudge = max(-cfg.nudge_cap, min(cfg.nudge_cap, cfg.model_weight * gap))
        p = p_market + nudge
    elif p_market is not None:
        p, nudge = p_market, 0.0
    else:
        p, nudge = p_model, 0.0
    p = max(0.01, min(0.99, p))
    ev = round(p * odds - 1, 4) if odds else None
    need = 0.02
    good = bool(odds) and ev is not None and ev >= need and (books or 0) >= 2
    row = {"id": f"{kind}|{g['game_id']}|{side}|{'' if line is None else f'{line:g}'}|{who or team or ''}", "game_id": g["game_id"], "mu": f'{g["away"]} @ {g["home"]}',
           "kick": g.get("tip_utc") or "", "kind": kind, "market": KIND_LABEL[kind], "side": side, "line": line, "who": who, "team": team, "pid": pid, "label": label,
           "odds": odds, "p": round(p, 4), "push": round(push, 4), "p_market": _r(p_market, 4), "p_model": _r(p_model, 4), "nudge": round(nudge, 4), "note": note,
           "fair_odds": _dec_from_prob(p), "breakeven": round(1 / odds, 4) if odds else None, "ev": ev, "good": good, "excluded": None if odds else "no DraftKings price",
           "need": need, "books": books or 0, "odds_source": odds_source if odds else None, "group": {"ml": "winners", "spread": "spreads", "total": "totals"}.get(kind, "props"),
           "inputs": inputs or {}}
    return row


def build_day(date: str, cfg=CFG, with_odds: bool = True) -> dict:
    t0 = time.time()
    season = season_now(datetime.strptime(date, "%Y-%m-%d").date())
    games_hist = load_games([season - 1, season])
    R = Ratings(games_hist, season, cfg, through=date)
    odds = load_odds() if with_odds else {}
    games = day_games(date)
    board: list[dict] = []
    extra: list[dict] = []
    for g in games:
        pj = R.project_game(g["home"], g["away"], neutral=bool(g.get("neutral")))
        L = g.get("lines") or {}
        g["model"] = pj
        mk = {"home_win": pj["home_win"], "margin": pj["margin"], "total": pj["total"], "pace": pj["pace"]}
        # moneyline
        nv_home = _nv(L.get("home_ml"), L.get("away_ml"))
        for side in ("home", "away"):
            odds_ = L.get(f"{side}_ml")
            pmk = None if nv_home is None else (nv_home if side == "home" else 1 - nv_home)
            pmd = pj["home_win"] if side == "home" else 1 - pj["home_win"]
            if odds_:
                board.append(_sel(g, "ml", side, f"{g[side]} moneyline", None, odds_, pmk, pmd, team=g[side], books=1 if pmk is not None else 0,
                                  note="game line: DraftKings' price with the vig removed; the model's win chance beside it", odds_source="espn-draftkings"))
        # spread (ESPN/DraftKings: the home team's points)
        if L.get("spread") is not None:
            hl = float(L["spread"])
            nv = _nv(L.get("spread_home_odds") or 1.91, L.get("spread_away_odds") or 1.91)
            pm_home = R.p_cover(pj["margin"], hl)
            board.append(_sel(g, "spread", "home", f"{g['home']} {hl:+g}", hl, L.get("spread_home_odds") or 1.91, nv, pm_home, team=g["home"], books=1,
                              note="DraftKings' spread; the model's cover chance from its expected margin", odds_source="espn-draftkings"))
            board.append(_sel(g, "spread", "away", f"{g['away']} {-hl:+g}", -hl, L.get("spread_away_odds") or 1.91, None if nv is None else 1 - nv, 1 - pm_home, team=g["away"], books=1,
                              note="DraftKings' spread; the model's cover chance from its expected margin", odds_source="espn-draftkings"))
            mk["spread"] = {"line": hl, "home_cover": round(pm_home, 4)}
        if L.get("total") is not None:
            tl = float(L["total"])
            po = R.p_over(pj["total"], tl)
            board.append(_sel(g, "total", "over", f"Over {tl:g}", tl, 1.91, 0.5, po, books=1, note="DraftKings' total (prices assumed 1.91 each side; ESPN lists the number only)", odds_source="espn-draftkings"))
            board.append(_sel(g, "total", "under", f"Under {tl:g}", tl, 1.91, 0.5, 1 - po, books=1, note="DraftKings' total (prices assumed 1.91 each side; ESPN lists the number only)", odds_source="espn-draftkings"))
            mk["total_line"] = tl; mk["over"] = round(po, 4)
        g["markets"] = mk
        # players: projections for both rosters, DraftKings props where the feed priced them
        og = for_game(odds, g["home"], g["away"], g.get("tip_utc")) or {}
        props_feed = og.get("props") or {}
        g["odds"] = {"fetched": og.get("props_fetched"), "props_fetched": og.get("props_fetched"), "props": {k: v for k, v in props_feed.items() if k in STATS},
                     "ml": {"books": {"DraftKings": {"home": L.get("home_ml"), "away": L.get("away_ml")}}} if L.get("home_ml") else {},
                     "spread": {"books": {"DraftKings": {"line": L.get("spread"), "home": L.get("spread_home_odds") or 1.91, "away": L.get("spread_away_odds") or 1.91}}} if L.get("spread") is not None else {},
                     "total": {"books": {"DraftKings": {"line": L.get("total"), "over": 1.91, "under": 1.91}}} if L.get("total") is not None else {}}
        g["props"] = {"home": [], "away": []}
        g["anytime"] = {"home": [], "away": []}
        spread_abs = abs(float(L["spread"])) if L.get("spread") is not None else abs(pj["margin"])
        for side in ("home", "away"):
            team = g[side]; opp = g["away" if side == "home" else "home"]
            outs = _out_ids(g, team); q = _questionable(g, team)
            for pid, prof in R.players.items():
                if prof.get("team") != team or pid in outs:
                    continue
                pp = R.project_player(pid, opp, pj["pace"], spread_abs)
                if not pp:
                    continue
                pp["q"] = pid in q
                pp["usage"] = {"minutes": pp["minutes"]}
                for s in STATS:
                    st = pp["stats"][s]
                    row = (props_feed.get(s) or {}).get(_nk(pp["name"]))
                    fair_line = math.floor(st["mean"]) + 0.5
                    st["fair_line"] = fair_line
                    po, pu = R.p_over_stat(st["mean"], st["sd"], fair_line)
                    st["p_over_fair"] = round(po, 4)
                    if row and row.get("line") is not None:
                        line = float(row["line"])
                        dk = (row.get("books") or {}).get("DraftKings") or {}
                        o_p, pu_p = R.p_over_stat(st["mean"], st["sd"], line)
                        cons = row.get("consensus_over")
                        # the consensus over-probability belongs to the consensus line; moved onto DraftKings' line with the model's shape
                        cons_line = row["line"]
                        if cons is not None and dk.get("line") is not None and abs(float(dk["line"]) - float(cons_line)) > 1e-9:
                            shift = (float(dk["line"]) - float(cons_line))
                            cons = max(0.02, min(0.98, cons - shift * (0.3989 / st["sd"])))
                            line = float(dk["line"])
                        if dk.get("line") is not None:
                            line = float(dk["line"])
                            o_p, pu_p = R.p_over_stat(st["mean"], st["sd"], line)
                        over_odds, under_odds = dk.get("over"), dk.get("under")
                        books = row.get("n") or 0
                        two_m = o_p / (1 - pu_p) if (1 - pu_p) > 0 else o_p
                        inputs = {"market_line": row["line"], "model_mean": st["mean"], "model_sd": st["sd"], "books": [{"book": b, **v} for b, v in (row.get("books") or {}).items()]}
                        if over_odds:
                            board.append(_sel(g, s, "over", f"{pp['name']} over {line:g} {UNIT[s]}", line, over_odds, cons, two_m, who=pp["name"], team=team, pid=pid, books=books,
                                              note=f"market {cons*100:.0f}% over at DraftKings' line" if cons is not None else "DraftKings only", push=pu_p, inputs=inputs))
                        if under_odds:
                            board.append(_sel(g, s, "under", f"{pp['name']} under {line:g} {UNIT[s]}", line, under_odds, None if cons is None else 1 - cons - pu_p, 1 - two_m, who=pp["name"], team=team, pid=pid,
                                              books=books, note=f"market {(1-cons)*100:.0f}% under at DraftKings' line" if cons is not None else "DraftKings only", push=pu_p, inputs=inputs))
                        st["dk"] = {"line": line, "over": over_odds, "under": under_odds, "consensus_over": cons, "n": books}
                    else:
                        # no DraftKings price in the feed: a projection card at the model's fair line (compare DraftKings' line by hand)
                        sd_ = "over" if st["mean"] > fair_line else "under"
                        extra.append(_sel(g, s, sd_, f"{pp['name']} {sd_} {fair_line:g} {UNIT[s]} (model line)", fair_line, None, None, po if sd_ == "over" else 1 - po,
                                          who=pp["name"], team=team, pid=pid, books=0, note="model projection: DraftKings' line not in tonight's feed", push=pu))
                g["props"][side].append({"id": pid, "name": pp["name"], "pos": pp["pos"], "q": pp["q"], "minutes": pp["minutes"], "games": pp["games"], "stats": pp["stats"], "last": pp["last"], "usage": pp["usage"]})
            g["props"][side].sort(key=lambda x: -x["minutes"])
        g["research"] = {"home": pj["ratings"]["home"], "away": pj["ratings"]["away"]}
    board = [b for b in board if b.get("odds")]
    board.sort(key=lambda b: (-b["p"], -(b["ev"] or -9)))
    for i, b in enumerate(board, 1):
        b["rank"] = i
    from .brain import bot_block
    payload = {"sport": "nba", "date": date, "season": season, "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
               "meta": {"model_version": MODEL_VERSION, "league": {"ortg": round(R.league.ortg, 1), "pace": round(R.league.pace, 1)}, "games_fit": len(games_hist),
                        "seconds": round(time.time() - t0, 1), "odds_updated": odds.get("updated_utc"), "credits_remaining": odds.get("credits_remaining")},
               "games": games, "best_bets": {"book": "DraftKings", "ranked": board, "n_priced": len(board), "n_good": sum(1 for b in board if b["good"]),
                                             "odds_fetched": odds.get("updated_utc")}, "picks": {}}
    payload["bot"] = bot_block(payload, extra)
    from .desk import merge as merge_desk
    merge_desk(payload)
    payload["picks"].update(scorecard_picks(payload))
    return payload


def _nk(n: str) -> str:
    from nfl.live import full_key
    return full_key(n or "")


def scorecard_picks(payload: dict) -> dict:
    """The bot's category picks in the scorecard's shape (the research desk's own picks are added by the desk merge)."""
    out: dict = {}
    bot = payload.get("bot") or {}
    board = {b["id"]: b for b in (payload.get("best_bets") or {}).get("ranked", [])}
    games = {g["game_id"]: g for g in payload["games"]}
    rows = []
    for key, c in (bot.get("cats") or {}).items():
        for i in c.get("ids") or []:
            b = board.get(i)
            if not b:
                continue
            g = games[b["game_id"]]
            tside = "home" if g["home"] == b.get("team") else ("away" if g["away"] == b.get("team") else None)
            pk = {"game_id": b["game_id"], "mu": b["mu"], "market": b["kind"], "side": b["side"], "team": b.get("team"), "side_team": tside, "p": b["p"], "odds": b["odds"],
                  "label": b["label"], "ev": b["ev"], "cat": key}
            if b["kind"] == "spread":
                pk["line"] = float(b["line"]) if b["side"] == "home" else -float(b["line"])        # the home team's points
            elif b["kind"] != "ml":
                pk["line"] = b.get("line")
            if b.get("who"):
                pk["player"] = b["who"]; pk["id"] = b.get("pid")
            rows.append(pk)
    out["bot"] = rows
    return out


def save_payload(payload: dict, out_dir=None) -> str:
    out_dir = out_dir or OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"day-{payload['date']}.json").write_text(json.dumps(payload, separators=(",", ":")))
    return payload["date"]


__all__ = ["build_day", "save_payload", "day_games"]
