"""The research desk: the overlay a Claude research session writes after reading the week's news.

The simulation and the judgment layer (brain.py) only see structured data: play-by-play, the official injury
report, depth charts, weather, the odds feed. The desk is the layer that reads everything else, the way a
handicapper does: beat-writer reports, practice participation, Friday designations, coaching and scheme changes,
cornerback assignments, kicker and stadium notes, line movement, and writes down what it concluded, with the
inputs and the arithmetic, for every selection it makes and every candidate it declined.

The overlay lives at data/nfl/research/<season>-wNN.json (schema below). This module validates it, merges it
into the week payload (payload["bot"]["desk"], a "desk" block on each matching board bet, and payload["picks"]
["desk"] so the scorecard grades the desk's record on its own line) and never changes a number the simulation
produced: the desk's probability sits beside the simulation's, labelled as the desk's.

Overlay schema (every key required unless marked optional):
{
  "v": 1, "season": 2026, "week": 6, "generated_utc": "2026-10-17 18:05 UTC", "analyst": "Claude research desk",
  "odds_band": [1.35, 2.20],
  "summary": "a short paragraph on the slate",                         (optional)
  "games": {"<game_id>": {"notes": [...], "weather": "...", "injuries": [...], "sources": [{"name","url","fetched"}]}},
  "selections": [ {
      "id": "<board id, or desk|<kind>|<game_id>|<side>|<line>|<who or team>>",
      "game_id", "kind", "side", "line" (null for ml/atd), "who" (null for game lines), "team" (null for totals),
      "label", "odds" (DraftKings decimal), "odds_source": "feed" | "draftkings" | "unverified",
      "p": 0.0-1.0 (the desk's probability), "grade": "A" | "B" | "C", "evidence": "measured" | "partial" | "unmeasured",
      "confidence": 0-100,
      "inputs": [...], "arithmetic": [...], "pros": [...], "risks": [...], "verdict": "...",
      "sources": [{"name","url","fetched"}]
  } ],
  "declined": [ {"id", "label", "why"} ]                                (optional)
}
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

RESEARCH_DIR = DATA_DIR / "research"
CONFIG_PATH = DATA_DIR / "desk_config.json"
# markets the desk knows; a sport module may extend KINDS / PLAYER_KINDS / QB_KINDS before using the desk
GAME_KINDS = ("ml", "spread", "total", "h1", "h2")
QB_KINDS = ("qb_yds", "qb_td")
PLAYER_KINDS = ("rec_yds", "rush_yds", "recs", "atd", "pts", "reb", "ast", "threes", "pra", "fg")
KEY_NAME = "kickoff_utc"       # the game's start-time field
DEFAULT_CONFIG = {"v": 1, "odds_band": [1.35, 2.2], "wild_cards": {"enabled": True, "odds_band": [2.21, 4.5], "max": 3, "min_p": 0.3},
                  "markets": {k: True for k in ("ml", "spread", "total", "h1", "h2", "qb_yds", "qb_td", "rec_yds", "recs", "rush_yds", "fg", "alts")},
                  "selection": {"min_grade": "C", "min_evidence": "unmeasured", "min_p": 0.52, "max_per_game": 3, "max_selections": 24, "one_player_per_market": True},
                  "variables": {}, "alerts": {"telegram": True, "line_move_points": 1.0, "odds_drop": 0.08, "injury_flags": True}}


def load_config() -> dict:
    """data/nfl/desk_config.json merged over the defaults (a missing or broken file leaves the defaults)."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        d = json.loads(CONFIG_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return cfg
    for k, v in d.items():
        if isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg
KINDS = ("ml", "spread", "total", "h1", "h2", "qb_yds", "qb_td", "rec_yds", "rush_yds", "recs", "fg", "atd", "pts", "reb", "ast", "threes", "pra")
SIDES = {"ml": ("home", "away"), "spread": ("home", "away"), "atd": ("yes",)}
GRADES = ("A", "B", "C")
EVIDENCE = ("measured", "partial", "unmeasured")
ODDS_SOURCES = ("feed", "draftkings", "unverified")
DEFAULT_BAND = (1.35, 2.20)
LIST_FIELDS = ("inputs", "arithmetic", "pros", "risks")
ID_RE = re.compile(r"^(desk\|)?[a-z_0-9]+\|\d{4}_\d{2}(_\d{2})?_[A-Z]{2,4}_[A-Z]{2,4}\|")


def overlay_path(season: int, week: int) -> Path:
    return RESEARCH_DIR / f"{season}-w{week:02d}.json"


def load_overlay(season: int, week: int) -> dict | None:
    f = overlay_path(season, week)
    if not f.exists():
        return None
    try:
        d = json.loads(f.read_text())
    except json.JSONDecodeError:
        return None
    if int(d.get("season") or 0) != season or int(d.get("week") or 0) != week:
        return None
    return d


def load_overlay_file(f: Path) -> dict | None:
    """An overlay at an explicit path (the NBA desk is keyed by date, not week)."""
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text())
    except json.JSONDecodeError:
        return None


def _is_list_of_str(x) -> bool:
    return isinstance(x, list) and all(isinstance(s, str) and s.strip() for s in x)


def validate(d: dict, payload: dict | None = None) -> list[str]:
    """Every problem found, as text. An empty list means the overlay is usable."""
    errs: list[str] = []
    if not isinstance(d, dict):
        return ["overlay is not a JSON object"]
    keyed_by_date = "date" in d and "week" not in d
    for k in ("v", "season", "generated_utc", "analyst", "odds_band", "games", "selections") + (("date",) if keyed_by_date else ("week",)):
        if k not in d:
            errs.append(f"missing top-level key {k!r}")
    if errs:
        return errs
    band = d.get("odds_band")
    if not (isinstance(band, list) and len(band) == 2 and all(isinstance(x, (int, float)) for x in band) and 1.0 < band[0] < band[1]):
        errs.append("odds_band must be [low, high] decimal odds with 1 < low < high")
        band = list(DEFAULT_BAND)
    try:
        datetime.strptime(d["generated_utc"], "%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        errs.append("generated_utc must look like '2026-10-17 18:05 UTC'")
    if not isinstance(d["games"], dict):
        errs.append("games must be an object keyed by game_id")
    games = {g["game_id"]: g for g in (payload or {}).get("games", [])} if payload else {}
    board = {b["id"]: b for b in ((payload or {}).get("best_bets") or {}).get("ranked", []) + (((payload or {}).get("bot") or {}).get("extra") or [])} if payload else {}
    if payload:
        wk = d.get("week") if "week" in d else d.get("date")
        for gid in d["games"]:
            if gid not in games:
                errs.append(f"games: {gid} is not in {wk}")
    if not isinstance(d["selections"], list):
        return errs + ["selections must be a list"]
    wild = d.get("wild_cards") or []
    if not isinstance(wild, list):
        errs.append("wild_cards must be a list"); wild = []
    wband = list((d.get("wild_band") or (load_config().get("wild_cards") or {}).get("odds_band") or [2.21, 4.5]))
    seen = set()
    rows = [(s, band, 0.5, "selection") for s in d["selections"]] + [(s, wband, 0.2, "wild card") for s in wild]
    for i, (s, band, p_floor, what) in enumerate(rows):
        tag = f"{what} {i + 1} ({s.get('label') if isinstance(s, dict) else '?'})"
        if not isinstance(s, dict):
            errs.append(f"{tag}: not an object"); continue
        missing = [k for k in ("id", "game_id", "kind", "side", "label", "odds", "odds_source", "p", "grade", "evidence", "confidence", "verdict", "sources") + LIST_FIELDS if k not in s]
        if missing:
            errs.append(f"{tag}: missing {', '.join(missing)}")
            continue
        if s["id"] in seen:
            errs.append(f"{tag}: duplicate id {s['id']}")
        seen.add(s["id"])
        if not ID_RE.match(str(s["id"])):
            errs.append(f"{tag}: id {s['id']!r} is not '<kind>|<game_id>|...' ")
        if s["kind"] not in KINDS:
            errs.append(f"{tag}: kind {s['kind']!r} not one of {KINDS}")
        sides = SIDES.get(s["kind"], ("over", "under"))
        if s["side"] not in sides:
            errs.append(f"{tag}: side {s['side']!r} must be one of {sides} for {s['kind']}")
        if s["kind"] in ("ml", "atd"):
            if s.get("line") is not None:
                errs.append(f"{tag}: line must be null for {s['kind']}")
        elif not isinstance(s.get("line"), (int, float)):
            errs.append(f"{tag}: line must be a number")
        if s["kind"] in QB_KINDS + PLAYER_KINDS and not (isinstance(s.get("who"), str) and s["who"].strip()):
            errs.append(f"{tag}: who (the player) is required for {s['kind']}")
        if s["kind"] in ("ml", "spread") + QB_KINDS + PLAYER_KINDS and not (isinstance(s.get("team"), str) and s["team"]):
            errs.append(f"{tag}: team is required for {s['kind']}")
        if not (isinstance(s["odds"], (int, float)) and s["odds"] > 1.0):
            errs.append(f"{tag}: odds must be decimal odds above 1.0")
        elif not (band[0] <= s["odds"] <= band[1]):
            errs.append(f"{tag}: odds {s['odds']} outside the band {band[0]} to {band[1]}")
        if isinstance(s["p"], (int, float)) and s["p"] < p_floor:
            errs.append(f"{tag}: p {s['p']} is below the floor {p_floor} for a {what}")
        if s["odds_source"] not in ODDS_SOURCES:
            errs.append(f"{tag}: odds_source must be one of {ODDS_SOURCES}")
        if not (isinstance(s["p"], (int, float)) and 0.0 < s["p"] < 1.0):
            errs.append(f"{tag}: p must be a probability strictly between 0 and 1")
        if s["grade"] not in GRADES:
            errs.append(f"{tag}: grade must be A, B or C")
        if s["evidence"] not in EVIDENCE:
            errs.append(f"{tag}: evidence must be measured, partial or unmeasured")
        if not (isinstance(s["confidence"], (int, float)) and 0 <= s["confidence"] <= 100):
            errs.append(f"{tag}: confidence must be 0 to 100")
        if not (isinstance(s["verdict"], str) and s["verdict"].strip()):
            errs.append(f"{tag}: verdict must be a sentence")
        for k in LIST_FIELDS:
            if not _is_list_of_str(s[k]) or not s[k]:
                errs.append(f"{tag}: {k} must be a non-empty list of strings")
        if not isinstance(s["sources"], list) or not s["sources"] or not all(isinstance(x, dict) and x.get("name") and x.get("fetched") for x in s["sources"]):
            errs.append(f"{tag}: sources must list at least one {{name, url, fetched}}")
        if s["evidence"] == "unmeasured" and s["grade"] == "A":
            errs.append(f"{tag}: an unmeasured selection cannot be grade A")
        if payload:
            if s["game_id"] not in games:
                errs.append(f"{tag}: game_id {s['game_id']} is not in {d.get('week') if 'week' in d else d.get('date')}")
            elif s.get("team") and s["team"] not in (games[s["game_id"]]["home"], games[s["game_id"]]["away"]):
                errs.append(f"{tag}: team {s['team']} is not in {s['game_id']}")
            b = board.get(s["id"])
            if b is not None:
                for k in ("kind", "side"):
                    if b.get(k) != s.get(k):
                        errs.append(f"{tag}: {k} {s.get(k)!r} differs from the board's {b.get(k)!r} for the same id")
                if b.get("line") is not None and s.get("line") is not None and abs(float(b["line"]) - float(s["line"])) > 1e-9:
                    errs.append(f"{tag}: line {s['line']} differs from the board's {b['line']} for the same id (use a desk| id for a different line)")
            elif not str(s["id"]).startswith("desk|"):
                errs.append(f"{tag}: id {s['id']} is not on the board; ids that are not on the board must start with 'desk|'")
            if s.get("odds_source") == "feed" and s["game_id"] in games and s["kind"] in KINDS:
                now = current_price(s, games[s["game_id"]])
                if now is None:
                    errs.append(f"{tag}: odds_source is 'feed' but the odds feed has no DraftKings price for this market; use 'draftkings' or 'unverified'")
                else:
                    if now.get("line") is not None and s.get("line") is not None and abs(float(now["line"]) - float(s["line"])) > 1e-9:
                        errs.append(f"{tag}: odds_source is 'feed' but DraftKings' line in the feed is {now['line']} (selection says {s['line']})")
                    if now.get("odds") and isinstance(s.get("odds"), (int, float)) and abs(float(now["odds"]) - float(s["odds"])) > 0.06:
                        errs.append(f"{tag}: odds_source is 'feed' but DraftKings' price in the feed is {now['odds']} (selection says {s['odds']})")
    for i, x in enumerate(d.get("declined") or []):
        if not (isinstance(x, dict) and x.get("label") and x.get("why")):
            errs.append(f"declined {i + 1}: needs label and why")
    return errs


def _player_id(g: dict, side: str | None, who: str | None) -> str | None:
    if not who:
        return None
    from .live import name_key
    key = name_key(who)
    for s_ in ([side] if side else ["home", "away"]):
        for lst in ((g.get("props") or {}).get(s_, []), (g.get("anytime") or {}).get(s_, [])):
            for x in lst:
                if name_key(x.get("name") or "") == key and x.get("id"):
                    return x["id"]
    return None


def _side_of(s: dict, g: dict) -> str | None:
    if s.get("team"):
        return "home" if g["home"] == s["team"] else ("away" if g["away"] == s["team"] else None)
    return None


def _scorecard_pick(s: dict, g: dict) -> dict:
    """The selection in the shape nfl.scorecard.grade reads (spread line in nflverse home-margin terms)."""
    k = s["kind"]
    tside = _side_of(s, g)
    pk = {"game_id": s["game_id"], "mu": f'{g["away"]} @ {g["home"]}', "market": k, "side": s["side"], "team": s.get("team"), "side_team": tside,
          "p": s["p"], "odds": s.get("odds"), "label": s.get("label"), "ev": round(s["p"] * s["odds"] - 1, 4) if s.get("odds") else None, "desk": True}
    if k == "spread":
        pk["line"] = -float(s["line"]) if s["side"] == "home" else float(s["line"])
    elif k not in ("ml", "atd"):
        pk["line"] = float(s["line"])
    if k in QB_KINDS:
        pk["qb"] = s.get("who")
    elif k in PLAYER_KINDS and k != "fg":
        pk["player"] = s.get("who")
        pid = _player_id(g, tside, s.get("who"))
        if pid:
            pk["id"] = pid
    return pk


def _start(g: dict) -> str:
    return g.get("kickoff_utc") or g.get("tip_utc") or ""


def _enrich(s: dict, g: dict, board: dict) -> dict:
    b = board.get(s["id"])
    tside = _side_of(s, g)
    x = {k: s.get(k) for k in ("id", "game_id", "kind", "side", "line", "who", "team", "label", "odds", "odds_source", "p", "grade", "evidence", "confidence",
                               "inputs", "arithmetic", "pros", "risks", "verdict", "sources")}
    x["mu"] = f'{g["away"]} @ {g["home"]}'
    x["kick"] = _start(g)
    x["tside"] = tside
    x["pid"] = _player_id(g, tside, s.get("who"))
    x["fair_odds"] = round(1 / s["p"], 3)
    x["ev"] = round(s["p"] * s["odds"] - 1, 4)
    if b is not None:
        x["board"] = {k: b.get(k) for k in ("p", "p_model", "p_market", "ev", "fair_odds", "odds", "conf", "price", "flags")}
        x["board"]["judge"] = (b.get("judge") or {}).get("score")
        b["desk"] = {k: x[k] for k in ("p", "grade", "evidence", "confidence", "verdict", "pros", "risks", "inputs", "arithmetic", "sources", "odds", "odds_source")}
    x["now"] = current_price(s, g)
    return x


def current_price(s: dict, g: dict) -> dict | None:
    """DraftKings' line and price for the selection's market as of the latest odds pull in the payload
    (game lines, halves, QB props); None when the feed has no such market."""
    O = g.get("odds") or {}
    k, side = s["kind"], s["side"]
    dk = None
    if k == "ml":
        dk = ((O.get("ml") or {}).get("books") or {}).get("DraftKings")
        if dk and dk.get(side):
            return {"line": None, "odds": dk[side], "fetched": O.get("fetched")}
        return None
    if k in ("spread", "total"):
        dk = ((O.get(k) or {}).get("books") or {}).get("DraftKings")
        if not dk or dk.get("line") is None:
            return None
        line = dk["line"] if k == "total" else (dk["line"] if side == "home" else -dk["line"])
        return {"line": line, "odds": dk.get(side), "fetched": O.get("fetched")}
    P = O.get("props") or {}
    if k in P and isinstance(P[k], dict):
        rows = P[k]
        if k in ("h1", "h2"):
            r = rows if "books" in rows else None
        else:
            from .live import name_key
            r = next((v for v in rows.values() if isinstance(v, dict) and name_key(v.get("name") or "") == name_key(s.get("who") or "")), None)
        dk = ((r or {}).get("books") or {}).get("DraftKings")
        if dk and dk.get("line") is not None:
            return {"line": dk["line"], "odds": dk.get(side), "fetched": O.get("props_fetched")}
    return None


def _against(s: dict, now: dict | None, cfg: dict) -> dict | None:
    """Did DraftKings move against the selection since the desk priced it? Returns the alert or None."""
    if not now:
        return None
    k, side = s["kind"], s["side"]
    pts = float((cfg.get("alerts") or {}).get("line_move_points") or 1.0)
    drop = float((cfg.get("alerts") or {}).get("odds_drop") or 0.08)
    out = {"line_was": s.get("line"), "line_now": now.get("line"), "odds_was": s.get("odds"), "odds_now": now.get("odds"), "fetched": now.get("fetched")}
    moved = 0.0
    if k != "ml" and now.get("line") is not None and s.get("line") is not None:
        d = float(now["line"]) - float(s["line"])
        # worse for the bettor: an over whose line rose, an under whose line fell, a spread whose points shrank
        moved = d if side in ("over",) else (-d if side == "under" else -d)
        if k == "spread":
            moved = -d                      # team-relative points: fewer points is worse for either side
    worse_odds = (now.get("odds") or 0) and s.get("odds") and (now["odds"] - s["odds"]) <= -drop
    if moved >= pts or worse_odds:
        out["why"] = (f"line moved {s.get('line')} to {now.get('line')}" if moved >= pts else f"price {s.get('odds'):.2f} to {now['odds']:.2f}")
        out["severity"] = "line" if moved >= pts else "price"
        return out
    return None


def _bot_picks(payload: dict, board: dict, games: dict) -> list[dict]:
    """The bot's category picks in scorecard form (the leaderboard's 'bot' line)."""
    cats = (payload.get("bot") or {}).get("cats") or {}
    out = []
    for key, c in cats.items():
        for i in c.get("ids") or []:
            b = board.get(i)
            if not b or not b.get("odds") or b["kind"] == "fg":
                continue
            g = games.get(b["game_id"])
            if not g:
                continue
            s = {"game_id": b["game_id"], "kind": b["kind"], "side": b["side"], "line": b.get("line"), "who": b.get("who"), "team": b.get("team"),
                 "label": b["label"], "odds": b["odds"], "p": b["p"]}
            pk = _scorecard_pick(s, g); pk["desk"] = False; pk["cat"] = key
            out.append(pk)
    return out


def _market_picks(games: dict) -> list[dict]:
    """The DraftKings favourite on the moneyline in every game (the leaderboard's 'market' baseline)."""
    out = []
    for g in games.values():
        dk = (((g.get("odds") or {}).get("ml") or {}).get("books") or {}).get("DraftKings")
        if not dk or not dk.get("home") or not dk.get("away"):
            continue
        side = "home" if dk["home"] <= dk["away"] else "away"
        odds = dk[side]
        p = round((1 / odds) / (1 / dk["home"] + 1 / dk["away"]), 4)
        s = {"game_id": g["game_id"], "kind": "ml", "side": side, "line": None, "who": None, "team": g[side], "label": f"{g[side]} moneyline (favourite)", "odds": odds, "p": p}
        pk = _scorecard_pick(s, g); pk["desk"] = False
        out.append(pk)
    return out


def hot_not(payload: dict, desk_sels: list[dict]) -> dict:
    """What's hot and what's not: the biggest DraftKings line moves since the opener (spread, total, moneyline), the
    steam side of each, and where the desk disagrees most with the market."""
    movers = []
    for g in payload.get("games", []):
        O = g.get("odds") or {}
        op = O.get("opening") or {}
        mu = f'{g["away"]} @ {g["home"]}'
        kick = _start(g)
        for k in ("spread", "total"):
            a = ((op.get(k) or {}).get("books") or {}).get("DraftKings") or (op.get(k) or {})
            b = ((O.get(k) or {}).get("books") or {}).get("DraftKings") or (O.get(k) or {})
            if a.get("line") is None or b.get("line") is None:
                continue
            d = float(b["line"]) - float(a["line"])
            if abs(d) < 0.5:
                continue
            if k == "spread":
                hot = g["away"] if d > 0 else g["home"]                   # book line is the home team's points: more points = market moved to the away side
                label = f"{mu} spread {g['home']} {a['line']:+g} → {b['line']:+g}"
            else:
                hot = "Over" if d > 0 else "Under"
                label = f"{mu} total {a['line']:g} → {b['line']:g}"
            movers.append({"game_id": g["game_id"], "mu": mu, "kick": kick, "kind": k, "move": round(d, 1), "size": abs(d), "hot": hot,
                           "cold": (g["away"] if hot == g["home"] else g["home"]) if k == "spread" else ("Under" if hot == "Over" else "Over"),
                           "label": label, "opened": O.get("opening_at") or "", "now": O.get("fetched") or ""})
        a = (op.get("ml") or {}); b = (O.get("ml") or {})
        if a.get("consensus_home") is not None and b.get("consensus_home") is not None:
            d = float(b["consensus_home"]) - float(a["consensus_home"])
            if abs(d) >= 0.03:
                hot = g["home"] if d > 0 else g["away"]
                movers.append({"game_id": g["game_id"], "mu": mu, "kick": kick, "kind": "ml", "move": round(d * 100, 1), "size": abs(d) * 100 / 4,
                               "hot": hot, "cold": g["away"] if hot == g["home"] else g["home"],
                               "label": f"{mu} moneyline {g['home']} {a['consensus_home']*100:.0f}% → {b['consensus_home']*100:.0f}%", "now": O.get("fetched") or ""})
    movers.sort(key=lambda x: -x["size"])
    edges = []
    for x in desk_sels:
        pm = (x.get("board") or {}).get("p_market")
        if pm is not None:
            edges.append({"id": x["id"], "label": x["label"], "mu": x["mu"], "kick": x["kick"], "desk": x["p"], "market": pm, "gap": round(x["p"] - pm, 4), "odds": x["odds"]})
    edges.sort(key=lambda x: -x["gap"])
    return {"movers": movers[:16], "edges": edges[:8], "fades": sorted(edges, key=lambda x: x["gap"])[:4]}


def merge(payload: dict, overlay: dict | None = None) -> dict | None:
    """Attach the overlay to the payload. Returns the desk block (also stored at payload["bot"]["desk"]) or None."""
    cfg = load_config()
    if overlay is not None:
        d = overlay
    elif payload.get("week") is not None:
        d = load_overlay(int(payload.get("season") or 0), int(payload.get("week") or 0))
    else:
        d = load_overlay_file(RESEARCH_DIR / f"{payload.get('date')}.json")
    bot = payload.setdefault("bot", {}) if payload.get("bot") is not None else None
    games = {g["game_id"]: g for g in payload.get("games", [])}
    board = {b["id"]: b for b in (payload.get("best_bets") or {}).get("ranked", []) + ((payload.get("bot") or {}).get("extra") or [])}
    # leaderboard baselines are built whether or not a desk file exists
    payload.setdefault("picks", {})["bot"] = _bot_picks(payload, board, games)
    payload["picks"]["market"] = _market_picks(games)
    if d is None:
        if bot is not None:
            bot["desk"] = None
            bot["desk_config"] = cfg
            bot["hot"] = hot_not(payload, [])
        return None
    errs = validate(d, payload)
    if errs:
        if bot is not None:
            bot["desk"] = {"v": 1, "ok": False, "errors": errs[:12], "generated": d.get("generated_utc"), "analyst": d.get("analyst")}
            bot["desk_config"] = cfg
            bot["hot"] = hot_not(payload, [])
        payload["picks"].pop("desk", None); payload["picks"].pop("desk_wild", None)
        return bot["desk"] if bot is not None else None
    band = list(d.get("odds_band") or DEFAULT_BAND)
    sels = [_enrich(s, games[s["game_id"]], board) for s in d["selections"]]
    wild = [_enrich(s, games[s["game_id"]], board) for s in (d.get("wild_cards") or [])]
    for x in sels + wild:
        x["alert"] = _against(x, x.get("now"), cfg)
    picks = [_scorecard_pick(s, games[s["game_id"]]) for s in d["selections"]]
    wpicks = [_scorecard_pick(s, games[s["game_id"]]) for s in (d.get("wild_cards") or [])]
    sels.sort(key=lambda x: (-x["p"], -x["confidence"]))
    wild.sort(key=lambda x: (-x["p"] * x["odds"], -x["confidence"]))
    picks.sort(key=lambda x: -x["p"])
    desk = {"v": 1, "ok": True, "generated": d["generated_utc"], "analyst": d["analyst"], "band": band, "summary": d.get("summary") or "",
            "games": {gid: v for gid, v in (d.get("games") or {}).items() if gid in games},
            "selections": sels, "wild_cards": wild, "wild_band": list((cfg.get("wild_cards") or {}).get("odds_band") or [2.21, 4.5]),
            "declined": list(d.get("declined") or []), "n": len(sels),
            "alerts": [{"id": x["id"], "label": x["label"], "mu": x["mu"], "kick": x["kick"], **x["alert"]} for x in sels + wild if x.get("alert")]}
    if bot is not None:
        bot["desk"] = desk
        bot["desk_config"] = cfg
        bot["hot"] = hot_not(payload, sels)
    payload["picks"]["desk"] = picks
    payload["picks"]["desk_wild"] = wpicks
    return desk


def write_overlay(d: dict) -> Path:
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    f = overlay_path(int(d["season"]), int(d["week"]))
    f.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    return f


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


__all__ = ["load_overlay", "validate", "merge", "write_overlay", "overlay_path", "load_config", "hot_not", "current_price", "RESEARCH_DIR", "DEFAULT_BAND", "KINDS"]
