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
KINDS = ("ml", "spread", "total", "h1", "h2", "qb_yds", "qb_td", "rec_yds", "rush_yds", "recs", "fg", "atd")
SIDES = {"ml": ("home", "away"), "spread": ("home", "away"), "atd": ("yes",)}
GRADES = ("A", "B", "C")
EVIDENCE = ("measured", "partial", "unmeasured")
ODDS_SOURCES = ("feed", "draftkings", "unverified")
DEFAULT_BAND = (1.35, 2.20)
LIST_FIELDS = ("inputs", "arithmetic", "pros", "risks")
ID_RE = re.compile(r"^(desk\|)?[a-z_0-9]+\|\d{4}_\d{2}_[A-Z]{2,3}_[A-Z]{2,3}\|")


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


def _is_list_of_str(x) -> bool:
    return isinstance(x, list) and all(isinstance(s, str) and s.strip() for s in x)


def validate(d: dict, payload: dict | None = None) -> list[str]:
    """Every problem found, as text. An empty list means the overlay is usable."""
    errs: list[str] = []
    if not isinstance(d, dict):
        return ["overlay is not a JSON object"]
    for k in ("v", "season", "week", "generated_utc", "analyst", "odds_band", "games", "selections"):
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
        for gid in d["games"]:
            if gid not in games:
                errs.append(f"games: {gid} is not in week {d['week']}")
    if not isinstance(d["selections"], list):
        return errs + ["selections must be a list"]
    seen = set()
    for i, s in enumerate(d["selections"]):
        tag = f"selection {i + 1} ({s.get('label') if isinstance(s, dict) else '?'})"
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
        if s["kind"] in ("qb_yds", "qb_td", "rec_yds", "rush_yds", "recs", "fg", "atd") and not (isinstance(s.get("who"), str) and s["who"].strip()):
            errs.append(f"{tag}: who (the player) is required for {s['kind']}")
        if s["kind"] in ("ml", "spread", "qb_yds", "qb_td", "rec_yds", "rush_yds", "recs", "fg", "atd") and not (isinstance(s.get("team"), str) and s["team"]):
            errs.append(f"{tag}: team is required for {s['kind']}")
        if not (isinstance(s["odds"], (int, float)) and s["odds"] > 1.0):
            errs.append(f"{tag}: odds must be decimal odds above 1.0")
        elif not (band[0] <= s["odds"] <= band[1]):
            errs.append(f"{tag}: odds {s['odds']} outside the band {band[0]} to {band[1]}")
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
                errs.append(f"{tag}: game_id {s['game_id']} is not in week {d['week']}")
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
    if k in ("qb_yds", "qb_td"):
        pk["qb"] = s.get("who")
    elif k in ("rec_yds", "rush_yds", "recs", "atd"):
        pk["player"] = s.get("who")
        pid = _player_id(g, tside, s.get("who"))
        if pid:
            pk["id"] = pid
    return pk


def merge(payload: dict, overlay: dict | None = None) -> dict | None:
    """Attach the overlay to the payload. Returns the desk block (also stored at payload["bot"]["desk"]) or None."""
    season, week = int(payload.get("season") or 0), int(payload.get("week") or 0)
    d = overlay if overlay is not None else load_overlay(season, week)
    bot = payload.setdefault("bot", {}) if payload.get("bot") is not None else None
    if d is None:
        if bot is not None:
            bot["desk"] = None
        return None
    errs = validate(d, payload)
    if errs:
        if bot is not None:
            bot["desk"] = {"v": 1, "ok": False, "errors": errs[:12], "generated": d.get("generated_utc"), "analyst": d.get("analyst")}
        payload.setdefault("picks", {}).pop("desk", None)
        return bot["desk"] if bot is not None else None
    games = {g["game_id"]: g for g in payload.get("games", [])}
    board = {b["id"]: b for b in (payload.get("best_bets") or {}).get("ranked", []) + ((payload.get("bot") or {}).get("extra") or [])}
    band = list(d.get("odds_band") or DEFAULT_BAND)
    sels = []
    picks = []
    for s in d["selections"]:
        g = games[s["game_id"]]
        b = board.get(s["id"])
        tside = _side_of(s, g)
        x = {k: s.get(k) for k in ("id", "game_id", "kind", "side", "line", "who", "team", "label", "odds", "odds_source", "p", "grade", "evidence", "confidence",
                                   "inputs", "arithmetic", "pros", "risks", "verdict", "sources")}
        x["mu"] = f'{g["away"]} @ {g["home"]}'
        x["kick"] = g.get("kickoff_utc") or ""
        x["tside"] = tside
        x["pid"] = _player_id(g, tside, s.get("who"))
        x["fair_odds"] = round(1 / s["p"], 3)
        x["ev"] = round(s["p"] * s["odds"] - 1, 4)
        if b is not None:
            x["board"] = {k: b.get(k) for k in ("p", "p_model", "p_market", "ev", "fair_odds", "odds", "conf", "price", "flags")}
            x["board"]["judge"] = (b.get("judge") or {}).get("score")
            b["desk"] = {k: x[k] for k in ("p", "grade", "evidence", "confidence", "verdict", "pros", "risks", "inputs", "arithmetic", "sources", "odds", "odds_source")}
        sels.append(x)
        picks.append(_scorecard_pick(s, g))
    sels.sort(key=lambda x: (-x["p"], -x["confidence"]))
    picks.sort(key=lambda x: -x["p"])
    desk = {"v": 1, "ok": True, "generated": d["generated_utc"], "analyst": d["analyst"], "band": band, "summary": d.get("summary") or "",
            "games": {gid: v for gid, v in (d.get("games") or {}).items() if gid in games},
            "selections": sels, "declined": list(d.get("declined") or []), "n": len(sels)}
    if bot is not None:
        bot["desk"] = desk
    payload.setdefault("picks", {})["desk"] = picks
    return desk


def write_overlay(d: dict) -> Path:
    RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
    f = overlay_path(int(d["season"]), int(d["week"]))
    f.write_text(json.dumps(d, indent=1, ensure_ascii=False))
    return f


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


__all__ = ["load_overlay", "validate", "merge", "write_overlay", "overlay_path", "RESEARCH_DIR", "DEFAULT_BAND", "KINDS"]
