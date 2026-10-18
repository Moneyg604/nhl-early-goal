"""The research desk: the overlay a Claude research session writes after reading the week's news.

The simulation and the judgment layer (brain.py) only see structured data: play-by-play, the official injury
report, depth charts, weather, the odds feed. The desk is the layer that reads everything else, the way a
handicapper does: beat-writer reports, practice participation, Friday designations, coaching and scheme changes,
cornerback assignments, kicker and stadium notes, line movement, and writes down what it concluded, with the
inputs and the arithmetic, for every selection it makes and every candidate it declined.

The overlay lives at data/nfl/research/<season>-wNN.json (schema below). The owner's spec, data/nfl/desk_config.json,
says what the desk may pick (markets, DraftKings' posted lines only, the sections and the Best picks list, the plain-
English instructions). This module validates the overlay against the spec and the published payload, merges it
into the week payload (payload["bot"]["desk"], a "desk" block on each matching board bet, and payload["picks"]
["desk"] / ["desk_best"] so the scorecard grades the desk's record on its own lines) and never changes a number the
simulation produced: the desk's probability sits beside the simulation's, labelled as the desk's.

Two ways to validate:
  strict  (tools/validate_desk.py and tools/assemble_desk.py, before a commit): the full spec. Markets switched
          off, alternate lines, unverified prices under "DraftKings' lines only", the probability, grade and
          evidence floors, per-game and total caps, one pick per player per market, section and Best-pick rules,
          and an exact match with the odds feed for odds_source "feed".
  lenient (merge(), every site build): the overlay's structure only. A file that passed the strict check keeps
          showing after kickoff and after DraftKings moves (a move becomes a line alert on the pick, never an
          error), and a selection the current spec no longer allows is set aside in desk.excluded, not shown.

Overlay schema (every key required unless marked optional):
{
  "v": 1, "season": 2026, "week": 6, "generated_utc": "2026-10-17 18:05 UTC", "analyst": "Claude research desk",
  "odds_band": [1.35, 2.20],                       (kept for the file format; the spec's odds_rule decides whether it applies)
  "summary": "a short paragraph on the slate",                         (optional)
  "games": {"<game_id>": {"notes": [...], "weather": "...", "injuries": [...], "sources": [{"name","url","fetched"}]}},
  "selections": [ {
      "id": "<board id from best_bets.ranked, or desk|<kind>|<game_id>|<side>|<line>|<who or team>>",
            (the board's proj|... and alt|... entries are not ids: re-key a projection as desk|...; alternates are off)
      "game_id", "kind", "side", "line" (null for ml), "who" (null for game lines), "team" (null for totals),
      "label", "odds" (DraftKings decimal), "odds_source": "feed" | "draftkings" | "unverified",
      "p": 0.0-1.0 (the desk's probability), "grade": "A" | "B" | "C", "evidence": "measured" | "partial" | "unmeasured",
      "confidence": 0-100,
      "inputs": [...], "arithmetic": [...], "pros": [...], "risks": [...], "verdict": "...",
      "sources": [{"name","url","fetched"}]
  } ],
  "sections": {"<section key from the spec>": [selection ids, strongest first]},   (optional; derived from the spec when absent)
  "best": [selection ids, strongest first],                                       (optional; derived from the spec when absent)
  "wild_cards": [ selections, same fields ],                                      (optional; only when the spec enables them)
  "declined": [ {"id", "label", "why"} ]                                          (optional)
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
# the built-in defaults, used only when the spec file is missing (a broken file is reported, see load_config)
DEFAULT_CONFIG = {"v": 2, "odds_rule": "band", "odds_band": [1.35, 2.2], "lines": "draftkings", "sections": [], "best": {"label": "Best picks", "min": 3, "max": 6},
                  "instructions": [], "wild_cards": {"enabled": True, "odds_band": [2.21, 4.5], "max": 3, "min_p": 0.3},
                  "markets": {k: True for k in ("ml", "spread", "total", "h1", "h2", "qb_yds", "qb_td", "rec_yds", "recs", "rush_yds", "fg", "alts")},
                  "selection": {"min_grade": "C", "min_evidence": "unmeasured", "min_p": 0.52, "max_per_game": 3, "max_selections": 24, "one_player_per_market": True},
                  "variables": {}, "alerts": {"telegram": True, "line_move_points": 1.0, "odds_drop": 0.08, "injury_flags": True}}

NFL_KINDS = ("ml", "spread", "total", "h1", "h2", "qb_yds", "qb_td", "rec_yds", "rush_yds", "recs", "fg", "atd")
NBA_KINDS = ("ml", "spread", "total", "pts", "reb", "ast", "threes", "pra")
KINDS = NFL_KINDS + ("pts", "reb", "ast", "threes", "pra")
GAME_KINDS = ("ml", "spread", "total", "h1", "h2")
QB_KINDS = ("qb_yds", "qb_td")
PLAYER_KINDS = ("rec_yds", "rush_yds", "recs", "atd", "pts", "reb", "ast", "threes", "pra", "fg")
KIND_LABEL = {"ml": "Moneyline", "spread": "Spread", "total": "Game total", "h1": "1st half total", "h2": "2nd half total", "qb_yds": "Passing yards",
              "qb_td": "Passing touchdowns", "rec_yds": "Receiving yards", "rush_yds": "Rushing yards", "recs": "Receptions", "fg": "Kicker field goals",
              "atd": "Anytime touchdown", "pts": "Points", "reb": "Rebounds", "ast": "Assists", "threes": "Threes", "pra": "Points + rebounds + assists"}
KEY_NAME = "kickoff_utc"       # the game's start-time field
SIDES = {"ml": ("home", "away"), "spread": ("home", "away"), "atd": ("yes",)}
GRADES = ("A", "B", "C")
EVIDENCE = ("measured", "partial", "unmeasured")
EV_RANK = {"measured": 2, "partial": 1, "unmeasured": 0}
GRADE_RANK = {"A": 2, "B": 1, "C": 0}
ODDS_SOURCES = ("feed", "draftkings", "unverified")
DEFAULT_BAND = (1.35, 2.20)
LIST_FIELDS = ("inputs", "arithmetic", "pros", "risks")
ID_RE = re.compile(r"^(desk\|)?[a-z_0-9]+\|\d{4}_\d{2}(_\d{2})?_[A-Z]{2,4}_[A-Z]{2,4}\|")


def load_config() -> dict:
    """data/<sport>/desk_config.json merged over the defaults.

    A missing file leaves the defaults. A file that does not parse also leaves the defaults, but the problem is
    recorded in cfg["_error"]: the pre-commit tools refuse to run on it and the page shows it. The file's
    "markets" list is the whole list: a market it leaves out is off (a missing key is never permissive)."""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        text = CONFIG_PATH.read_text()
    except OSError:
        return cfg
    try:
        d = json.loads(text)
    except json.JSONDecodeError as e:
        cfg["_error"] = f"{CONFIG_PATH.name} is not valid JSON ({e.msg}, line {e.lineno}): fix the file; until then the desk runs on built-in defaults"
        return cfg
    if not isinstance(d, dict):
        cfg["_error"] = f"{CONFIG_PATH.name} must be a JSON object"
        return cfg
    for k, v in d.items():
        if k == "markets" and isinstance(v, dict):
            cfg["markets"] = {mk: bool(on) for mk, on in v.items()}
        elif isinstance(cfg.get(k), dict) and not isinstance(v, dict):
            cfg["_error"] = f"{CONFIG_PATH.name}: {k!r} must be an object; the built-in default is used until it is fixed"
        elif k == "sections" and not (isinstance(v, list) and all(isinstance(x, dict) for x in v)):
            cfg["_error"] = f"{CONFIG_PATH.name}: 'sections' must be a list of objects"
        elif isinstance(v, dict) and isinstance(cfg.get(k), dict):
            cfg[k].update(v)
        else:
            cfg[k] = v
    return cfg


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
    if not isinstance(d, dict) or int(d.get("season") or 0) != season or int(d.get("week") or 0) != week:
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


def _num(x) -> float | None:
    try:
        return None if x is None or isinstance(x, bool) else float(x)
    except (TypeError, ValueError):
        return None


def _now_s(now: datetime | None = None) -> str:
    return (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%MZ")


def _start(g: dict) -> str:
    return g.get("kickoff_utc") or g.get("tip_utc") or ""


def started_games(payload: dict | None, now: datetime | None = None) -> set:
    """Game ids that have kicked off: the same test the board uses (nfl/value.py _started)."""
    now_s = _now_s(now)
    out = set()
    for g in (payload or {}).get("games", []) or []:
        k = _start(g)
        if g.get("actual") or g.get("score") or g.get("frozen") or (k and k <= now_s):
            out.add(g.get("game_id"))
    return out


def _sport(d: dict, payload: dict | None) -> str:
    if payload and payload.get("sport") in ("nfl", "nba"):
        return payload["sport"]
    return "nba" if ("date" in d and "week" not in d) else "nfl"


def _board(payload: dict | None) -> dict:
    """Every board row a selection may point at: the bets still to play, the bets locked at kickoff, the bot's extras."""
    p = payload or {}
    bb = p.get("best_bets") or {}
    rows = (bb.get("ranked") or []) + (bb.get("locked") or []) + ((p.get("bot") or {}).get("extra") or [])
    return {b["id"]: b for b in rows if isinstance(b, dict) and "id" in b}


def spec_block(s: dict, cfg: dict) -> str | None:
    """Why the spec does not allow this selection's market, or None when it does."""
    kind = s.get("kind")
    sid = str(s.get("id") or "")
    M = cfg.get("markets") or {}
    if sid.startswith("alt|") or kind == "alts":
        if cfg.get("lines") == "draftkings" or not M.get("alts", False):
            return "alternate lines are off in the spec (DraftKings' posted lines only)"
    if kind == "atd" and not M.get("atd", False):
        return "anytime touchdowns are not a desk market (the page has its own TD board)"
    if M and not M.get(kind, False):
        return f"{KIND_LABEL.get(kind, kind)} is switched off in the spec"
    secs = [x for x in (cfg.get("sections") or []) if isinstance(x, dict)]
    if secs and not any(kind in (x.get("markets") or []) for x in secs):
        return f"{KIND_LABEL.get(kind, kind)} is in none of the spec's sections"
    return None


def _player_key(s: dict) -> str:
    return str(s.get("who") or s.get("team") or s.get("id"))


def validate(d: dict, payload: dict | None = None, strict: bool = True) -> list[str]:
    """Every problem found, as text. An empty list means the overlay is usable.

    strict=True is the pre-commit check (the whole spec, and the feed price as of now); strict=False is the build-time
    check (structure only: a selection that passed before kickoff keeps showing after kickoff and after a line move)."""
    errs: list[str] = []
    if not isinstance(d, dict):
        return ["overlay is not a JSON object"]
    keyed_by_date = "date" in d and "week" not in d
    for k in ("v", "season", "generated_utc", "analyst", "odds_band", "games", "selections") + (("date",) if keyed_by_date else ("week",)):
        if k not in d:
            errs.append(f"missing top-level key {k!r}")
    if errs:
        return errs
    cfg = load_config()
    if strict and cfg.get("_error"):
        errs.append(cfg["_error"])
    sport = _sport(d, payload)
    kinds = NBA_KINDS if sport == "nba" else NFL_KINDS
    band = d.get("odds_band")
    if not (isinstance(band, list) and len(band) == 2 and all(isinstance(x, (int, float)) for x in band) and 1.0 < band[0] < band[1]):
        errs.append("odds_band must be [low, high] decimal odds with 1 < low < high")
    rule = cfg.get("odds_rule") or "band"
    band = list(cfg.get("odds_band") or DEFAULT_BAND) if rule == "band" else [1.01, 1000.0]   # the spec decides, never the overlay
    try:
        datetime.strptime(str(d["generated_utc"]), "%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        errs.append("generated_utc must look like '2026-10-17 18:05 UTC'")
    if not isinstance(d["games"], dict):
        errs.append("games must be an object keyed by game_id")
    if not isinstance(d["selections"], list):
        return errs + ["selections must be a list"]
    games = {g["game_id"]: g for g in (payload or {}).get("games", [])} if payload else {}
    started = started_games(payload) if payload else set()
    board = _board(payload) if payload else {}
    wk = d.get("week") if "week" in d else d.get("date")
    if payload and isinstance(d["games"], dict):
        for gid in d["games"]:
            if gid not in games:
                errs.append(f"games: {gid} is not in {wk}")
    pub = ((payload or {}).get("bot") or {}).get("desk") if payload else None
    pub_ids = None
    if strict and isinstance(pub, dict) and pub.get("ok"):
        pub_ids = {x.get("id") for k in ("selections", "wild_cards", "excluded") for x in pub.get(k) or [] if isinstance(x, dict)}
    wild = d.get("wild_cards") or []
    if not isinstance(wild, list):
        errs.append("wild_cards must be a list")
        wild = []
    wcfg = cfg.get("wild_cards") or {}
    open_wild = [w for w in wild if not (isinstance(w, dict) and w.get("game_id") in started)]
    if strict and open_wild and not wcfg.get("enabled", True):
        errs.append(f"wild_cards: the spec has wild cards switched off; remove the {len(open_wild)} wild card(s) or move them to declined")
    if strict and open_wild and wcfg.get("max") is not None and len(wild) > max(int(wcfg["max"]), len(wild) - len(open_wild)):
        errs.append(f"wild_cards: {len(wild)}, the spec allows at most {wcfg['max']}")
    wband = list(wcfg.get("odds_band") or [2.21, 4.5])
    scfg = cfg.get("selection") or {}
    p_floor = float(scfg.get("min_p") if scfg.get("min_p") is not None else 0.5)
    w_floor = float(wcfg.get("min_p") if wcfg.get("min_p") is not None else 0.2)
    min_ev = EV_RANK.get(scfg.get("min_evidence") or "unmeasured", 0)
    min_gr = GRADE_RANK.get(scfg.get("min_grade") or "C", 0)
    dk_only = cfg.get("lines") == "draftkings"
    seen = set()
    rows = [(s, band, p_floor, "selection") for s in d["selections"]] + [(s, wband, w_floor, "wild card") for s in wild]
    good: list[dict] = []
    for i, (s, sband, floor, what) in enumerate(rows):
        tag = f"{what} {i + 1} ({s.get('label') if isinstance(s, dict) else '?'})"
        if not isinstance(s, dict):
            errs.append(f"{tag}: not an object")
            continue
        missing = [k for k in ("id", "game_id", "kind", "side", "label", "odds", "odds_source", "p", "grade", "evidence", "confidence", "verdict", "sources") + LIST_FIELDS if k not in s]
        if missing:
            errs.append(f"{tag}: missing {', '.join(missing)}")
            continue
        if not isinstance(s["id"], str) or not isinstance(s["kind"], str) or not isinstance(s["side"], str) or not isinstance(s["game_id"], str):
            errs.append(f"{tag}: id, game_id, kind and side must be text")
            continue
        bad_num = [k for k in ("odds", "p", "confidence") if not (isinstance(s[k], (int, float)) and not isinstance(s[k], bool))]
        if s.get("line") is not None and not (isinstance(s["line"], (int, float)) and not isinstance(s["line"], bool)):
            bad_num.append("line")
        if bad_num:
            errs.append(f"{tag}: {', '.join(bad_num)} must be numbers, not text")
            continue
        if s["id"] in seen:
            errs.append(f"{tag}: duplicate id {s['id']}")
        seen.add(s["id"])
        if not ID_RE.match(str(s["id"])):
            errs.append(f"{tag}: id {s['id']!r} is not '<kind>|<game_id>|...' (re-key proj|/alt| board entries as desk|<kind>|<game_id>|<side>|<line>|<who or team>)")
        else:
            parts = str(s["id"]).split("|")
            if parts[0] == "desk":
                parts = parts[1:]
            for pos, name in enumerate(("kind", "game_id", "side")):
                if len(parts) > pos and parts[pos] != str(s.get(name)):
                    errs.append(f"{tag}: the id says {name} {parts[pos]!r} but the selection says {s.get(name)!r}")
            if len(parts) > 3 and _num(parts[3]) is not None and _num(s.get("line")) is not None and abs(_num(parts[3]) - _num(s.get("line"))) > 1e-9:
                errs.append(f"{tag}: the id says line {parts[3]} but the selection says {s.get('line')}")
        if s["kind"] not in kinds:
            errs.append(f"{tag}: kind {s['kind']!r} is not a {sport.upper()} market ({', '.join(kinds)})")
        sides = SIDES.get(s["kind"], ("over", "under"))
        if s["side"] not in sides:
            errs.append(f"{tag}: side {s['side']!r} must be one of {sides} for {s['kind']}")
        line = _num(s.get("line"))
        if s["kind"] in ("ml", "atd"):
            if s.get("line") is not None:
                errs.append(f"{tag}: line must be null for {s['kind']}")
        elif line is None:
            errs.append(f"{tag}: line must be a number")
        if s["kind"] in QB_KINDS + PLAYER_KINDS and not (isinstance(s.get("who"), str) and s["who"].strip()):
            errs.append(f"{tag}: who (the player) is required for {s['kind']}")
        if s["kind"] in ("ml", "spread") + QB_KINDS + PLAYER_KINDS and not (isinstance(s.get("team"), str) and s["team"]):
            errs.append(f"{tag}: team is required for {s['kind']}")
        gid = s["game_id"]
        policy = strict and gid not in started          # a pick whose game has kicked off is history: never re-judged
        odds, p = _num(s["odds"]), _num(s["p"])
        if odds is None or odds <= 1.0:
            errs.append(f"{tag}: odds must be decimal odds above 1.0")
        elif policy and not (sband[0] <= odds <= sband[1]):
            errs.append(f"{tag}: odds {odds} outside the band {sband[0]} to {sband[1]}")
        if s["odds_source"] not in ODDS_SOURCES:
            errs.append(f"{tag}: odds_source must be one of {ODDS_SOURCES}")
        if p is None or not (0.0 < p < 1.0):
            errs.append(f"{tag}: p must be a probability strictly between 0 and 1")
        elif policy and p < floor:
            errs.append(f"{tag}: p {p} is below the spec's floor {floor} for a {what}")
        if s["grade"] not in GRADES:
            errs.append(f"{tag}: grade must be A, B or C")
        if s["evidence"] not in EVIDENCE:
            errs.append(f"{tag}: evidence must be measured, partial or unmeasured")
        if not (isinstance(s["confidence"], (int, float)) and not isinstance(s["confidence"], bool) and 0 <= s["confidence"] <= 100):
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
        if policy:
            why = spec_block(s, cfg)
            if why:
                errs.append(f"{tag}: {why}; move it to declined")
            if dk_only and s["odds_source"] == "unverified":
                errs.append(f"{tag}: the spec takes DraftKings' posted lines only; confirm the line and price on a page showing DraftKings' board (odds_source 'draftkings', URL in sources) or move it to declined")
            if s["evidence"] in EV_RANK and EV_RANK[s["evidence"]] < min_ev:
                errs.append(f"{tag}: evidence {s['evidence']!r} is below the spec's minimum {scfg.get('min_evidence')!r}")
            if s["grade"] in GRADE_RANK and GRADE_RANK[s["grade"]] < min_gr:
                errs.append(f"{tag}: grade {s['grade']} is below the spec's minimum {scfg.get('min_grade')}")
        if payload:
            if gid not in games:
                errs.append(f"{tag}: game_id {gid} is not in {wk}")
            elif s.get("team") and s["team"] not in (games[gid]["home"], games[gid]["away"]):
                errs.append(f"{tag}: team {s['team']} is not in {gid}")
            b = board.get(s["id"])
            if b is not None:
                for k in ("kind", "side"):
                    if b.get(k) != s.get(k):
                        errs.append(f"{tag}: {k} {s.get(k)!r} differs from the board's {b.get(k)!r} for the same id")
                bl = _num(b.get("line"))
                if bl is not None and line is not None and abs(bl - line) > 1e-9:
                    errs.append(f"{tag}: line {line:g} differs from the board's {bl:g} for the same id (use a desk| id for a different line)")
            elif strict and gid not in started and not str(s["id"]).startswith("desk|"):
                errs.append(f"{tag}: id {s['id']} is not on the board; ids that are not on the board must start with 'desk|'")
            # the feed's DraftKings price, checked before the commit; after the commit a move is a line alert, not an error
            if strict and s["odds_source"] == "feed" and gid in games and gid not in started and s["kind"] in kinds:
                now = current_price(s, games[gid])
                if now is None:
                    errs.append(f"{tag}: odds_source is 'feed' but the odds feed has no DraftKings price for this market; use 'draftkings' (a page showing DraftKings' board, URL in sources)")
                else:
                    nl = _num(now.get("line"))
                    if nl is not None and line is not None and abs(nl - line) > 1e-9:
                        errs.append(f"{tag}: odds_source is 'feed' but DraftKings' line in the feed is {nl:g} (selection says {line:g})")
                    if now.get("odds") and odds is not None and abs(float(now["odds"]) - odds) > 0.06:
                        errs.append(f"{tag}: odds_source is 'feed' but DraftKings' price in the feed is {now['odds']} (selection says {odds})")
        if pub_ids is not None and gid in started and s["id"] not in pub_ids:
            errs.append(f"{tag}: its game has kicked off and it was not published before kickoff; remove it")
        if what == "selection" and gid not in started:
            good.append(s)
    if strict:
        per_game: dict[str, int] = {}
        for s in good:
            per_game[s["game_id"]] = per_game.get(s["game_id"], 0) + 1
        cap = scfg.get("max_per_game")
        for gid, n in per_game.items():
            if cap is not None and n > int(cap):
                errs.append(f"{gid}: {n} selections, the spec allows at most {cap} per game")
        for sp in [x for x in (cfg.get("sections") or []) if isinstance(x, dict) and x.get("key")]:
            kinds = set(sp.get("markets") or [])
            rows = [x for x in d["selections"] if isinstance(x, dict) and x.get("kind") in kinds and (x.get("game_id") in started or not spec_block(x, cfg))]
            n, n_started = len(rows), sum(1 for x in rows if x.get("game_id") in started)
            if sp.get("max") is not None and n > max(int(sp["max"]), n_started):
                errs.append(f"{n} {sp.get('label') or sp['key']} selections, the section allows at most {sp['max']}: keep the strongest, move the rest to declined")
        if scfg.get("max_selections") is not None and len(good) > int(scfg["max_selections"]):
            errs.append(f"{len(good)} selections, the spec allows at most {scfg['max_selections']}")
        if scfg.get("one_player_per_market", True):
            seen_pm: dict[tuple, str] = {}
            for s in good:
                key = (s["game_id"], s["kind"], _player_key(s) if s.get("who") else "game")
                if key in seen_pm:
                    errs.append(f"{s['label']}: a second {s['kind']} pick for {key[2] if key[2] != 'game' else 'the same game'} ({seen_pm[key]}); keep one")
                seen_pm[key] = s["label"]
    sel_ids = {x.get("id") for x in d["selections"] + wild if isinstance(x, dict)}
    for i, x in enumerate(d.get("declined") or []):
        if not (isinstance(x, dict) and x.get("label") and x.get("why")):
            errs.append(f"declined {i + 1}: needs label and why")
        elif strict and x.get("id") in sel_ids and x.get("id") not in (None, "none"):
            errs.append(f"{x.get('label')}: listed both as a selection and as declined; keep one")
    errs += _check_lists(d, cfg, strict, started)
    return errs


def _check_lists(d: dict, cfg: dict, strict: bool, started: set | None = None) -> list[str]:
    """The overlay's own sections and Best picks (both optional: the merge derives them from the spec when absent).
    Picks whose game has kicked off keep their places (the honest scorecard): a cap is never broken by them alone."""
    errs: list[str] = []
    st = started or set()
    sels = {s["id"]: s for s in d.get("selections") or [] if isinstance(s, dict) and "id" in s}
    secs = d.get("sections")
    spec = {x["key"]: x for x in cfg.get("sections") or [] if isinstance(x, dict) and x.get("key")}
    in_sec: set = set()
    if secs is not None:
        if not isinstance(secs, dict):
            errs.append("sections must be an object {section key: [selection ids]}")
            secs = {}
        for key, lst in secs.items():
            if not isinstance(lst, list) or any(i not in sels for i in lst):
                errs.append(f"sections.{key}: every entry must be the id of a selection in this overlay")
                continue
            if not strict:
                in_sec.update(lst)
                continue
            sp = spec.get(key)
            if spec and sp is None:
                errs.append(f"sections.{key}: not a section in the spec ({', '.join(spec)})")
                continue
            if sp:
                n_started = sum(1 for i in lst if sels[i].get("game_id") in st)
                if len(lst) > max(int(sp.get("max") or 99), n_started):
                    errs.append(f"sections.{key}: {len(lst)} selections, the spec allows at most {sp.get('max')}")
                kinds = set(sp.get("markets") or [])
                bad = [i for i in lst if kinds and sels[i]["kind"] not in kinds and sels[i].get("game_id") not in st]
                if bad:
                    errs.append(f"sections.{key}: {len(bad)} selection(s) are not {sorted(kinds)} markets")
            twice = [i for i in lst if i in in_sec]
            if twice:
                errs.append(f"sections.{key}: {len(twice)} selection(s) are already in another section")
            in_sec.update(lst)
        if strict and spec:
            # with explicit lists, a pick still to play that is in no list would silently vanish from the app and the record
            for i, x in sels.items():
                if x.get("game_id") not in st and i not in in_sec and not spec_block(x, cfg):
                    home = next((k for k, sp in spec.items() if x.get("kind") in (sp.get("markets") or [])), None)
                    errs.append(f"{x.get('label')}: in no section list; add it to sections.{home} or move it to declined")
    best = d.get("best")
    if best is not None:
        if not isinstance(best, list) or any(i not in sels for i in best):
            errs.append("best must be a list of selection ids from this overlay")
        elif strict:
            bs = cfg.get("best") or {}
            n_started = sum(1 for i in best if sels[i].get("game_id") in st)
            if len(best) > max(int(bs.get("max") or 6), n_started):
                errs.append(f"best: {len(best)} picks, the spec allows at most {bs.get('max')}")
            if len(set(best)) != len(best):
                errs.append("best: an id is listed twice")
            per_game: dict[str, int] = {}
            players: set = set()
            for i in best:
                s = sels[i]
                per_game[s["game_id"]] = per_game.get(s["game_id"], 0) + 1
                pk = _player_key(s) if s.get("who") else f"{s['game_id']}|{s['kind']}"
                if pk and pk in players:
                    errs.append(f"best: {pk if s.get('who') else s['label']} appears twice (one Best pick per player, one per game line)")
                if pk:
                    players.add(pk)
                if s.get("odds_source") == "unverified" and s.get("game_id") not in st:
                    errs.append(f"best: {s['label']} has an unverified price; a Best pick needs DraftKings' confirmed line")
                if secs is not None and i not in in_sec and s.get("game_id") not in st:
                    errs.append(f"best: {s['label']} is in no section; Best picks come from the sections")
            for gid, n in per_game.items():
                if n > 2 and gid not in st:
                    errs.append(f"best: {n} picks from {gid}, the spec allows at most two per game")
    return errs


def notes(d: dict, payload: dict | None = None) -> list[str]:
    """Soft warnings the desk should read (not errors): sections or Best picks short of the spec's minimum, and
    selections the spec sets aside. Printed by tools/validate_desk.py and tools/assemble_desk.py."""
    out: list[str] = []
    if not isinstance(d, dict) or not isinstance(d.get("selections"), list):
        return out
    cfg = load_config()
    sels = [s for s in d["selections"] if isinstance(s, dict) and "id" in s and "kind" in s and _num(s.get("p")) is not None]
    allowed = [s for s in sels if not spec_block(s, cfg)]
    for s in sels:
        why = spec_block(s, cfg)
        if why:
            out.append(f"{s.get('label')}: {why}; it will not be shown")
    view = [dict(s, p=float(s["p"]), confidence=_num(s.get("confidence")) or 0) for s in allowed]
    view.sort(key=lambda x: (-x["p"], -x["confidence"]))
    sections, best = _sections(d, view, cfg)
    for sp in cfg.get("sections") or []:
        if not isinstance(sp, dict) or not sp.get("key"):
            continue
        n = len(sections.get(sp["key"]) or [])
        if n < int(sp.get("min") or 0):
            out.append(f"section {sp.get('label') or sp['key']}: {n} selection(s), the spec asks for at least {sp.get('min')} (name the gap in the summary)")
    bs = cfg.get("best") or {}
    if len(best) < int(bs.get("min") or 0):
        out.append(f"Best picks: {len(best)}, the spec asks for {bs.get('min')} to {bs.get('max')} (fine for a one- or two-game window; say so in the summary)")
    return out


def _player_id(g: dict, side: str | None, who: str | None) -> str | None:
    if not who:
        return None
    from .live import name_key
    key = name_key(who)
    for s_ in ([side] if side else ["home", "away"]):
        for lst in ((g.get("props") or {}).get(s_, []), (g.get("anytime") or {}).get(s_, [])):
            for x in lst or []:
                if isinstance(x, dict) and name_key(x.get("name") or "") == key and x.get("id"):
                    return x["id"]
    return None


def _side_of(s: dict, g: dict) -> str | None:
    if s.get("team"):
        return "home" if g["home"] == s["team"] else ("away" if g["away"] == s["team"] else None)
    return None


def _scorecard_pick(s: dict, g: dict, sport: str = "nfl") -> dict:
    """The selection in the shape the sport's scorecard reads. Spreads: the NFL scorecard (nfl/scorecard.py) reads the
    line in nflverse home-margin terms (minus the home team's points); the NBA scorecard reads the home team's points."""
    k = s["kind"]
    tside = _side_of(s, g)
    pk = {"game_id": s["game_id"], "mu": f'{g["away"]} @ {g["home"]}', "market": k, "side": s["side"], "team": s.get("team"), "side_team": tside,
          "p": float(s["p"]), "odds": float(s["odds"]) if s.get("odds") else None, "label": s.get("label"),
          "ev": round(float(s["p"]) * float(s["odds"]) - 1, 4) if s.get("odds") else None, "desk": True}
    if k == "spread":
        line = float(s["line"])
        if sport == "nba":
            pk["line"] = line if s["side"] == "home" else -line
        else:
            pk["line"] = -line if s["side"] == "home" else line
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


def _enrich(s: dict, g: dict, board: dict) -> dict:
    b = board.get(s["id"])
    tside = _side_of(s, g)
    x = {k: s.get(k) for k in ("id", "game_id", "kind", "side", "line", "who", "team", "label", "odds", "odds_source", "p", "grade", "evidence", "confidence",
                               "inputs", "arithmetic", "pros", "risks", "verdict", "sources")}
    x["p"] = float(x["p"])
    x["odds"] = float(x["odds"])
    x["mu"] = f'{g["away"]} @ {g["home"]}'
    x["kick"] = _start(g)
    x["tside"] = tside
    x["pid"] = _player_id(g, tside, s.get("who"))
    x["fair_odds"] = round(1 / x["p"], 3)
    x["ev"] = round(x["p"] * x["odds"] - 1, 4)
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


def _iso(stamp: str | None) -> str:
    """'2026-10-17 18:05 UTC' or '2026-10-17T18:05Z' -> '2026-10-17T18:05Z' (comparable as text)."""
    s = str(stamp or "")
    m = re.match(r"^(\d{4}-\d\d-\d\d)[ T](\d\d:\d\d)", s)
    return f"{m.group(1)}T{m.group(2)}Z" if m else ""


def _against(s: dict, now: dict | None, cfg: dict, generated: str | None = None) -> dict | None:
    """Did DraftKings move against the selection since the desk priced it? Returns the alert or None.
    A feed snapshot older than the desk's run says nothing about a move since the desk priced it."""
    if not now:
        return None
    fetched, priced = _iso(now.get("fetched")), _iso(generated)
    if fetched and priced and fetched < priced:
        return None
    k, side = s["kind"], s["side"]
    pts = float((cfg.get("alerts") or {}).get("line_move_points") or 1.0)
    drop = float((cfg.get("alerts") or {}).get("odds_drop") or 0.08)
    out = {"line_was": s.get("line"), "line_now": now.get("line"), "odds_was": s.get("odds"), "odds_now": now.get("odds"), "fetched": now.get("fetched")}
    moved = 0.0
    lw, ln = _num(s.get("line")), _num(now.get("line"))
    same_line = lw is None or ln is None or abs(lw - ln) < 1e-9
    if k != "ml" and lw is not None and ln is not None:
        d = ln - lw
        # worse for the bettor: an over whose line rose, an under whose line fell, a spread whose points shrank
        moved = d if side == "over" else -d
    worse_odds = same_line and bool(now.get("odds")) and bool(s.get("odds")) and (float(now["odds"]) - float(s["odds"])) <= -drop
    if moved >= pts or worse_odds:
        out["why"] = (f"line moved {s.get('line')} to {now.get('line')}" if moved >= pts else f"price {float(s['odds']):.2f} to {float(now['odds']):.2f}")
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
            pk = _scorecard_pick(s, g, payload.get("sport") or "nfl"); pk["desk"] = False; pk["cat"] = key
            out.append(pk)
    return out


def _market_picks(games: dict, sport: str = "nfl") -> list[dict]:
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
        pk = _scorecard_pick(s, g, sport); pk["desk"] = False
        out.append(pk)
    return out


def hot_not(payload: dict, desk_sels: list[dict]) -> dict:
    """What's hot and what's not: the biggest DraftKings line moves since the opener (spread, total, moneyline), the
    steam side of each, and where the desk disagrees most with the market."""
    movers = []
    started = started_games(payload)
    for g in payload.get("games", []):
        if g.get("game_id") in started:
            continue                                   # an in-play line is not a move since the opener
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
        if pm is not None and x.get("game_id") not in started:
            edges.append({"id": x["id"], "game_id": x["game_id"], "label": x["label"], "mu": x["mu"], "kick": x["kick"], "desk": x["p"], "market": pm,
                          "gap": round(x["p"] - pm, 4), "odds": x["odds"]})
    edges.sort(key=lambda x: -x["gap"])
    return {"movers": movers[:16], "edges": [e for e in edges if e["gap"] > 0][:8], "fades": sorted((e for e in edges if e["gap"] < 0), key=lambda x: x["gap"])[:4]}


def _rank_key(x: dict) -> tuple:
    """Best-pick order: measured evidence first, then the desk's probability, then its confidence."""
    return (-EV_RANK.get(x.get("evidence"), 0), -float(x["p"]), -float(x.get("confidence") or 0))


def _sections(d: dict, sels: list[dict], cfg: dict, started: set | None = None) -> tuple[dict, list]:
    """{section key: [ids]} and the Best-pick ids: the overlay's own when it has them, else derived from the spec.
    Derived sections: the selections of each section's markets, strongest desk chance first, capped at the section's
    max. Derived Best picks: drawn from the sections (or every selection when the spec has none), measured evidence
    first, then the desk's probability, then confidence; one per player, at most two per game, never an unverified
    price when the spec takes DraftKings' posted lines only."""
    by_id = {x["id"]: x for x in sels}
    spec = [x for x in (cfg.get("sections") or []) if isinstance(x, dict) and x.get("key")]
    st = started or set()
    if isinstance(d.get("sections"), dict):
        sections = {k: [i for i in v if i in by_id] for k, v in d["sections"].items() if isinstance(v, list)}
        if spec:
            fixed = {}
            for sp in spec:
                kinds = set(sp.get("markets") or [])
                rows = [i for i in sections.get(sp["key"], []) if not kinds or by_id[i]["kind"] in kinds]
                old = [i for i in rows if by_id[i]["game_id"] in st]
                new = [i for i in rows if by_id[i]["game_id"] not in st]
                fixed[sp["key"]] = old + new[:max(0, int(sp.get("max") or 6) - len(old))]
            sections = fixed
    else:
        sections = {}
        taken: set = set()
        for sp in spec:
            kinds = set(sp.get("markets") or [])
            rows = [x for x in sels if x["kind"] in kinds and x["id"] not in taken]
            rows.sort(key=lambda x: (-float(x["p"]), -float(x.get("confidence") or 0)))
            keep = rows[:int(sp.get("max") or 6)]
            sections[sp["key"]] = [x["id"] for x in keep]
            taken.update(sections[sp["key"]])
    if isinstance(d.get("best"), list):
        best = [i for i in d["best"] if i in by_id]
    else:
        bs = cfg.get("best") or {}
        in_sec = {i for v in sections.values() for i in v}
        pool = [x for x in sels if (x["id"] in in_sec if spec else True) and x.get("odds_source") != "unverified"]
        pool.sort(key=_rank_key)
        best, per_game, players = [], {}, set()
        for x in pool:
            pk = _player_key(x) if x.get("who") else f"{x['game_id']}|{x['kind']}"
            if per_game.get(x["game_id"], 0) >= 2 or (pk and pk in players):
                continue
            best.append(x["id"]); per_game[x["game_id"]] = per_game.get(x["game_id"], 0) + 1
            if pk:
                players.add(pk)
            if len(best) >= int(bs.get("max") or 6):
                break
    return sections, best


def merge(payload: dict, overlay: dict | None = None, prev: dict | None = None) -> dict | None:
    """Attach the overlay to the payload. Returns the desk block (also stored at payload["bot"]["desk"]) or None.
    Never raises: a file that cannot be read becomes an error block the page and the message show.
    prev: the previous published build of the same week/day; its leaderboard baselines for started games are kept."""
    try:
        return _merge(payload, overlay, prev)
    except Exception as e:  # noqa: BLE001
        block = {"v": 2, "ok": False, "errors": [f"the desk file could not be merged: {type(e).__name__}: {e}"]}
        bot = payload.get("bot") if isinstance(payload.get("bot"), dict) else None
        if bot is not None:
            bot["desk"] = block
            try:
                bot["desk_config"] = load_config()
            except Exception:  # noqa: BLE001
                pass
        for k in ("desk", "desk_wild", "desk_best"):
            (payload.get("picks") or {}).pop(k, None)
        return block


def _why_unusable(f: Path) -> str:
    """Why a research file that exists could not be used (so the page says so instead of 'the desk has not run')."""
    try:
        raw = json.loads(f.read_text())
    except json.JSONDecodeError as e:
        return f"{f.name} is not valid JSON ({e.msg}, line {e.lineno})"
    except OSError as e:
        return f"{f.name} cannot be read ({e})"
    if not isinstance(raw, dict):
        return f"{f.name} is not a JSON object"
    return f"{f.name} says season {raw.get('season')} week {raw.get('week')}, which is not this week"


def _merge(payload: dict, overlay: dict | None, prev: dict | None) -> dict | None:
    cfg = load_config()
    if cfg.get("_error"):
        # a spec that cannot be read never re-opens what the owner closed: use the last spec that was read cleanly
        last = ((prev or {}).get("bot") or {}).get("desk_config") if prev else None
        if isinstance(last, dict) and not last.get("_error") and isinstance(last.get("markets"), dict):
            err = cfg["_error"]
            cfg = json.loads(json.dumps(last))
            cfg["_error"] = err + " (the last spec that could be read is used)"
    sport = payload.get("sport") or ("nba" if payload.get("week") is None and payload.get("date") else "nfl")
    load_err = None
    if overlay is not None:
        d = overlay
    else:
        weekly = payload.get("week") is not None
        f = overlay_path(int(payload.get("season") or 0), int(payload.get("week") or 0)) if weekly else RESEARCH_DIR / f"{payload.get('date')}.json"
        d = load_overlay(int(payload.get("season") or 0), int(payload.get("week") or 0)) if weekly else load_overlay_file(f)
        if d is None and f.exists():
            load_err = _why_unusable(f)
    bot = payload.setdefault("bot", {}) if payload.get("bot") is not None else None
    games = {g["game_id"]: g for g in payload.get("games", [])}
    board = _board(payload)
    started = started_games(payload)
    # leaderboard baselines are built whether or not a desk file exists; started games keep the previous build's entries
    picks = payload.setdefault("picks", {})
    picks["bot"] = _bot_picks(payload, board, games)
    picks["market"] = _market_picks(games, sport)
    if prev and started:
        for key in ("bot", "market"):
            old = [x for x in ((prev.get("picks") or {}).get(key) or []) if x.get("game_id") in started]
            if old:
                picks[key] = old + [x for x in picks[key] if x.get("game_id") not in started]
    if d is None and not load_err:
        if bot is not None:
            bot["desk"] = None
            bot["desk_config"] = cfg
            bot["hot"] = hot_not(payload, [])
        for k in ("desk", "desk_wild", "desk_best"):
            picks.pop(k, None)
        return None
    errs = [load_err] if load_err else validate(d, payload, strict=False)
    if errs:
        if bot is not None:
            bot["desk"] = {"v": 2, "ok": False, "errors": errs[:12], "n_errors": len(errs), "generated": d.get("generated_utc") if isinstance(d, dict) else None,
                           "analyst": d.get("analyst") if isinstance(d, dict) else None}
            bot["desk_config"] = cfg
            bot["hot"] = hot_not(payload, [])
        for k in ("desk", "desk_wild", "desk_best"):
            picks.pop(k, None)
        return bot["desk"] if bot is not None else None
    # what the current spec allows; the rest is set aside (listed, never shown as a pick, never graded as one).
    # A pick's state at kickoff is final (the honest scorecard): for a game that has started, the previous build's
    # decision stands, so a later spec change can neither remove a published pick nor revive a set-aside one.
    pd = ((prev or {}).get("bot") or {}).get("desk") if prev else None
    pd = pd if isinstance(pd, dict) and pd.get("ok") else None          # any published desk (builds older than this code have no "excluded")
    prev_excl = {x.get("id"): x.get("why") for x in (pd or {}).get("excluded") or []}
    prev_shown = {x.get("id") for x in (pd or {}).get("selections") or []} | {x.get("id") for x in (pd or {}).get("wild_cards") or []}
    prev_best = list((pd or {}).get("best") or [])

    def blocked(s: dict) -> str | None:
        if pd is not None and s["game_id"] in started:
            if s["id"] in prev_shown:
                return None                                # published before kickoff: stays shown and graded
            if s["id"] in prev_excl:
                return prev_excl[s["id"]]                  # set aside before kickoff: stays set aside
        why = spec_block(s, cfg)
        if not why and cfg.get("lines") == "draftkings" and s.get("odds_source") == "unverified":
            why = "price never confirmed on DraftKings (the spec takes DraftKings' posted lines only)"
        return why
    excluded, keep = [], []
    for s in d["selections"]:
        why = blocked(s)
        if why:
            excluded.append({"id": s["id"], "game_id": s["game_id"], "label": s.get("label"), "kind": s["kind"], "why": why})
        else:
            keep.append(s)
    wild_on = bool((cfg.get("wild_cards") or {}).get("enabled", True))
    wild_in = []
    for s in d.get("wild_cards") or []:
        wb = list((cfg.get("wild_cards") or {}).get("odds_band") or [2.21, 4.5])
        fresh = not (pd is not None and s["game_id"] in started)
        why = ("wild cards are switched off in the spec" if not wild_on and fresh
               else (f"price outside the wild-card band {wb[0]} to {wb[1]}" if fresh and _num(s.get("odds")) is not None and not (wb[0] <= float(s["odds"]) <= wb[1]) else blocked(s)))
        if why:
            excluded.append({"id": s["id"], "game_id": s["game_id"], "label": s.get("label"), "kind": s["kind"], "why": why, "wild": True})
        else:
            wild_in.append(s)
    sels = [_enrich(s, games[s["game_id"]], board) for s in keep]
    wild = [_enrich(s, games[s["game_id"]], board) for s in wild_in]
    for x in sels + wild:
        x["alert"] = None if x["game_id"] in started else _against(x, x.get("now"), cfg, d.get("generated_utc"))
    sels.sort(key=lambda x: (-x["p"], -x["confidence"]))
    wild.sort(key=lambda x: (-x["p"] * x["odds"], -x["confidence"]))
    sections, best = _sections(d, sels, cfg, started)
    by_sel = {x["id"]: x for x in sels}
    if pd is not None and not isinstance(d.get("best"), list):
        # derived Best picks: started ones keep their places from the previous build; the rest fill what is left
        frozen = [i for i in prev_best if i in by_sel and by_sel[i]["game_id"] in started]
        cap = int((cfg.get("best") or {}).get("max") or 6)
        best = frozen + [i for i in best if i not in frozen and by_sel[i]["game_id"] not in started][:max(0, cap - len(frozen))]
    spec_secs = [x for x in (cfg.get("sections") or []) if isinstance(x, dict) and x.get("key")]
    if spec_secs:
        # only what the spec's lists hold is shown and graded; anything else is set aside with the reason
        listed = {i for v in sections.values() for i in v} | set(best) | {i for i in prev_shown if i in by_sel and by_sel[i]["game_id"] in started}
        explicit = isinstance(d.get("sections"), dict)
        for x in [x for x in sels if x["id"] not in listed]:
            home = next((sp for sp in spec_secs if x["kind"] in (sp.get("markets") or [])), None)
            if home and explicit and len(sections.get(home["key"]) or []) < int(home.get("max") or 6):
                why = f"not in the desk's {home.get('label') or home['key']} list"
            else:
                why = f"beyond the {home.get('label') or home['key']} section's maximum of {home.get('max')}" if home else "in none of the spec's sections"
            excluded.append({"id": x["id"], "game_id": x["game_id"], "label": x["label"], "kind": x["kind"], "why": why})
        sels = [x for x in sels if x["id"] in listed]
        keep = [s for s in keep if s["id"] in listed]
    pk_by = {s["id"]: _scorecard_pick(s, games[s["game_id"]], sport) for s in keep}
    rule = cfg.get("odds_rule") or "band"
    desk = {"v": 2, "ok": True, "generated": d["generated_utc"], "analyst": d["analyst"], "band": list(cfg.get("odds_band") or DEFAULT_BAND), "odds_rule": rule,
            "lines": cfg.get("lines"), "summary": d.get("summary") or "", "games": {gid: v for gid, v in (d.get("games") or {}).items() if gid in games},
            "selections": sels, "wild_cards": wild, "wild_band": list((cfg.get("wild_cards") or {}).get("odds_band") or [2.21, 4.5]),
            "sections": sections, "best": best,
            "spec": {"sections": cfg.get("sections") or [], "best": cfg.get("best") or {}, "instructions": cfg.get("instructions") or [],
                     "derived_sections": not isinstance(d.get("sections"), dict), "derived_best": not isinstance(d.get("best"), list),
                     "derived": not isinstance(d.get("best"), list)},
            "declined": list(d.get("declined") or []), "excluded": excluded, "n": len(sels), "config_error": cfg.get("_error"),
            "alerts": [{"id": x["id"], "game_id": x["game_id"], "label": x["label"], "mu": x["mu"], "kick": x["kick"], **x["alert"]} for x in sels + wild if x.get("alert")]}
    if bot is not None:
        bot["desk"] = desk
        bot["desk_config"] = cfg
        bot["hot"] = hot_not(payload, sels)
    picks["desk"] = sorted(pk_by.values(), key=lambda x: -x["p"])
    picks["desk_wild"] = [_scorecard_pick(s, games[s["game_id"]], sport) for s in wild_in]
    picks["desk_best"] = [dict(pk_by[i], rank=n) for n, i in enumerate(best, 1) if i in pk_by]
    return desk


def write_overlay(d: dict) -> Path:
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    f = overlay_path(int(d["season"]), int(d["week"]))
    f.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    return f


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


__all__ = ["load_overlay", "validate", "notes", "merge", "write_overlay", "overlay_path", "load_config", "hot_not", "current_price", "spec_block",
           "started_games", "RESEARCH_DIR", "DEFAULT_BAND", "KINDS", "NFL_KINDS", "NBA_KINDS"]
