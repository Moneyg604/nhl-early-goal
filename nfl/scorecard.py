"""Grade every published week's leans against what happened (data/nfl games records, after the play-by-play
lands). Writes docs/nfl/scorecard.json: per market won / lost / push, by week and overall, plus the items."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

from .config import SITE_DIR
from .ingest import load_games
from .live import name_key

MARKETS = {"ml": "Moneyline", "spread": "Spread", "total": "Total", "h1": "1st half total", "h2": "2nd half total",
           "fg": "Team field goals 1.5", "qb_yds": "QB passing yards", "qb_td": "QB passing TDs 1.5", "atd": "Anytime TD", "rec_yds": "Receiving yards", "rush_yds": "Rushing yards", "recs": "Receptions",
           "desk": "Research desk", "desk_best": "Desk best picks", "desk_wild": "Desk wild cards", "bot": "Bot's picks", "market": "DraftKings favourites"}
LEADERS = ("desk_best", "desk", "desk_wild", "bot", "market")


def _player(g: dict, pick: dict) -> dict | None:
    """The player's line in the game record: by id, else by name on his team, else by name on either team."""
    teams = [pick["team"]] if pick.get("team") else [g["home"], g["away"]]
    for t in teams:
        s_ = (g["players"].get(t) or {}).get(pick.get("id")) if pick.get("id") else None
        if s_ is not None:
            return s_
    target = name_key(pick.get("player") or "")
    for t in teams:
        for s_ in (g["players"].get(t) or {}).values():
            if target and name_key(s_.get("name", "")) == target:
                return s_
    return None


def grade(pick: dict, g: dict, game: dict) -> str | None:
    """'won' / 'lost' / 'push' / None (not gradeable yet). g: games record; game: payload game."""
    hs, as_ = g["hs"], g["as"]
    m = pick["market"]
    if m == "ml":
        if hs == as_:
            return "push"
        won = (hs > as_) == (pick["side"] == "home")
        return "won" if won else "lost"
    if m == "spread":
        diff = (hs - as_) - pick["line"]
        if diff == 0:
            return "push"
        return "won" if (diff > 0) == (pick["side"] == "home") else "lost"
    if m == "total":
        t = hs + as_
        if t == pick["line"]:
            return "push"
        return "won" if (t > pick["line"]) == (pick["side"] == "over") else "lost"
    if m in ("h1", "h2"):
        h1 = sum(g["q"]["home"][:2]) + sum(g["q"]["away"][:2])
        v = h1 if m == "h1" else hs + as_ - h1
        if v == pick["line"]:
            return "push"
        return "won" if (v > pick["line"]) == (pick["side"] == "over") else "lost"
    if m == "fg":
        t = pick["team"]
        made = sum(1 for k in g["fg"].get(t, []) if k["r"] == "made")
        return "won" if (made > pick["line"]) == (pick["side"] == "over") else "lost"
    if m in ("qb_yds", "qb_td"):
        target = name_key(pick["qb"])
        teams = [pick["team"]] if pick.get("team") else [g["home"], g["away"]]
        row = next((v for t in teams for v in (g["qbs"].get(t) or {}).values() if name_key(v["name"]) == target), None)
        if row is None:
            return None            # did not play: void
        v = row["yds"] if m == "qb_yds" else row["td"]
        if v == pick["line"]:
            return "push"
        return "won" if (v > pick["line"]) == (pick["side"] == "over") else "lost"
    if m in ("rec_yds", "rush_yds", "recs"):
        s_ = _player(g, pick)
        if s_ is None:
            return None
        v = {"rec_yds": s_.get("recyds", 0), "rush_yds": s_.get("ryds", 0), "recs": s_.get("rec", 0)}[m]
        if v == pick["line"]:
            return "push"
        return "won" if (v > pick["line"]) == (pick["side"] == "over") else "lost"
    if m == "atd":
        s = _player(g, pick)
        if s is None:
            return None            # no touch: treat as not played (void at most books only if inactive)
        return "won" if s["rtd"] + s["rectd"] > 0 else "lost"
    return None


def build_scorecard(site_dir=None) -> dict:
    site_dir = site_dir or SITE_DIR
    wdir = site_dir / "weeks"
    payloads = []
    for f in sorted(x for x in wdir.glob("*.json") if not x.name.endswith(".sims.json")):
        try:
            payloads.append(json.loads(f.read_text()))
        except json.JSONDecodeError:
            continue
    seasons = sorted({p["season"] for p in payloads})
    games = {g["game_id"]: g for g in load_games(seasons)} if seasons else {}
    tally: dict[str, dict[str, float]] = defaultdict(lambda: {"won": 0, "lost": 0, "push": 0, "units": 0.0, "staked": 0})
    weeks: dict[str, dict] = {}
    items = []
    for p in payloads:
        name = f"{p['season']}-w{p['week']:02d}"
        wt: dict[str, dict[str, int]] = defaultdict(lambda: {"won": 0, "lost": 0, "push": 0})
        byid = {g["game_id"]: g for g in p["games"]}
        for key, lst in (p.get("picks") or {}).items():
            for pk in lst:
                g = games.get(pk["game_id"])
                if g is None:
                    continue
                r = grade(pk, g, byid.get(pk["game_id"], {}))
                if r is None:
                    continue
                wt[key][r] += 1; tally[key][r] += 1
                odds = pk.get("odds")
                u = None
                if odds:
                    u = (odds - 1) if r == "won" else (-1.0 if r == "lost" else 0.0)
                    tally[key]["units"] += u; tally[key]["staked"] += 1
                items.append({"week": name, "market": key, "mu": pk.get("mu"), "side": pk.get("side"), "line": pk.get("line"),
                              "who": pk.get("qb") or pk.get("player") or pk.get("team"), "p": pk.get("p"), "result": r,
                              "label": pk.get("label"), "odds": odds, "ev": pk.get("ev"), "units": None if u is None else round(u, 3)})
        weeks[name] = dict(wt)
    summary = {k: {**v, "units": round(v["units"], 3), "n": v["won"] + v["lost"], "rate": round(v["won"] / (v["won"] + v["lost"]), 4) if (v["won"] + v["lost"]) else None,
                   "roi": round(v["units"] / v["staked"], 4) if v["staked"] else None, "label": MARKETS.get(k, k)} for k, v in tally.items()}
    tot = {"won": sum(v["won"] for v in tally.values()), "lost": sum(v["lost"] for v in tally.values()), "push": sum(v["push"] for v in tally.values()),
           "units": round(sum(v["units"] for v in tally.values()), 3), "staked": sum(v["staked"] for v in tally.values())}
    tot["roi"] = round(tot["units"] / tot["staked"], 4) if tot["staked"] else None
    leans = [k for k in tally if k not in LEADERS]
    lt = {"won": sum(tally[k]["won"] for k in leans), "lost": sum(tally[k]["lost"] for k in leans), "push": sum(tally[k]["push"] for k in leans),
          "units": round(sum(tally[k]["units"] for k in leans), 3), "staked": sum(tally[k]["staked"] for k in leans)}
    lt["roi"] = round(lt["units"] / lt["staked"], 4) if lt["staked"] else None
    lt["rate"] = round(lt["won"] / (lt["won"] + lt["lost"]), 4) if (lt["won"] + lt["lost"]) else None
    board = [{"key": k, "label": MARKETS.get(k, k), **summary[k]} for k in LEADERS if k in summary] + [{"key": "leans", "label": "Model leans (all markets)", **lt, "n": lt["won"] + lt["lost"]}]
    board.sort(key=lambda r: -(r["units"] or 0))
    out = {"updated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "summary": summary, "total": tot, "weeks": weeks, "leaderboard": board,
           "items": items[-400:], "note": "Best bets at DraftKings' price, one unit each, graded at the price shown before kickoff."}
    (site_dir / "scorecard.json").write_text(json.dumps(out, separators=(",", ":")))
    return out


__all__ = ["build_scorecard", "grade", "MARKETS"]
