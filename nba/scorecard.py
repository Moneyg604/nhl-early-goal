"""Grade every published day's picks against the box scores (data/nba games, after the morning ingest).
Writes docs/nba/scorecard.json: per line (desk, wild cards, bot, market) won / lost / push / units, a leaderboard,
by day and overall."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from .config import SITE_DIR
from .ingest import load_games

MARKETS = {"ml": "Moneyline", "spread": "Spread", "total": "Total", "pts": "Points", "reb": "Rebounds", "ast": "Assists", "threes": "Threes", "pra": "PRA",
           "desk": "Research desk", "desk_best": "Desk best picks", "desk_wild": "Desk wild cards", "bot": "Bot's picks", "market": "DraftKings favourites"}
LEADERS = ("desk_best", "desk", "desk_wild", "bot", "market")


def _name_key(n: str) -> str:
    from nfl.live import name_key
    return name_key(n or "")


def _player(g: dict, pick: dict) -> dict | None:
    teams = [pick["team"]] if pick.get("team") else [g["home"], g["away"]]
    for t in teams:
        for p in (g.get("players") or {}).get(t, []):
            if (pick.get("id") and p.get("id") == pick["id"]) or (pick.get("player") and _name_key(p.get("name")) == _name_key(pick["player"])):
                return p
    return None


def grade(pick: dict, g: dict) -> str | None:
    hs, as_ = g["hs"], g["as"]
    m = pick["market"]
    if m == "ml":
        return "push" if hs == as_ else ("won" if (hs > as_) == (pick["side"] == "home") else "lost")
    if m == "spread":
        diff = (hs - as_) + pick["line"] if pick["side"] == "home" else (as_ - hs) - pick["line"]    # line: the home team's points
        if diff == 0:
            return "push"
        return "won" if diff > 0 else "lost"
    if m == "total":
        t = hs + as_
        if t == pick["line"]:
            return "push"
        return "won" if (t > pick["line"]) == (pick["side"] == "over") else "lost"
    if m in ("pts", "reb", "ast", "threes", "pra"):
        p = _player(g, pick)
        if p is None or p.get("dnp"):
            return None
        v = {"pts": p["pts"], "reb": p["reb"], "ast": p["ast"], "threes": p["tpm"], "pra": p["pts"] + p["reb"] + p["ast"]}[m]
        if v == pick["line"]:
            return "push"
        return "won" if (v > pick["line"]) == (pick["side"] == "over") else "lost"
    return None


def build_scorecard(site_dir=None) -> dict:
    site_dir = site_dir or SITE_DIR
    ddir = site_dir / "days"
    payloads = []
    for f in sorted(ddir.glob("*.json")) if ddir.exists() else []:
        try:
            payloads.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            continue
    seasons = sorted({p["season"] for p in payloads})
    games = {}
    for g in load_games(seasons) if seasons else []:
        games[f'{(g.get("date_local") or g["date"][:10]).replace("-", "_")}_{g["away"]}_{g["home"]}'] = g
        games[g["id"]] = g
    tally: dict = defaultdict(lambda: {"won": 0, "lost": 0, "push": 0, "units": 0.0, "staked": 0})
    days: dict = {}
    items = []
    for p in payloads:
        dt: dict = defaultdict(lambda: {"won": 0, "lost": 0, "push": 0})
        gmap = {g["game_id"]: g for g in p["games"]}
        for key, lst in (p.get("picks") or {}).items():
            for pk in lst:
                gp = gmap.get(pk["game_id"]) or {}
                g = games.get(pk["game_id"]) or (games.get(gp.get("espn_id")) if gp.get("espn_id") else None)
                if g is None:
                    continue
                r = grade(pk, g)
                if r is None:
                    continue
                dt[key][r] += 1; tally[key][r] += 1
                u = None
                if pk.get("odds"):
                    u = (pk["odds"] - 1) if r == "won" else (-1.0 if r == "lost" else 0.0)
                    tally[key]["units"] += u; tally[key]["staked"] += 1
                items.append({"day": p["date"], "line": key, "market": pk["market"], "mu": pk.get("mu"), "label": pk.get("label"), "p": pk.get("p"), "odds": pk.get("odds"),
                              "result": r, "units": None if u is None else round(u, 3)})
        days[p["date"]] = dict(dt)
    summary = {k: {**v, "units": round(v["units"], 3), "n": v["won"] + v["lost"], "rate": round(v["won"] / (v["won"] + v["lost"]), 4) if (v["won"] + v["lost"]) else None,
                   "roi": round(v["units"] / v["staked"], 4) if v["staked"] else None, "label": MARKETS.get(k, k)} for k, v in tally.items()}
    board = sorted([{"key": k, **summary[k]} for k in LEADERS if k in summary], key=lambda r: -(r["units"] or 0))
    out = {"updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "summary": summary, "leaderboard": board, "days": days, "items": items[-400:],
           "note": "One unit per pick at the DraftKings price shown before tip-off."}
    site_dir.mkdir(parents=True, exist_ok=True)
    (site_dir / "scorecard.json").write_text(json.dumps(out, separators=(",", ":")))
    return out


__all__ = ["build_scorecard", "grade", "MARKETS"]
