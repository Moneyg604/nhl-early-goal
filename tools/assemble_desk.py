"""Assemble per-game research fragments into one research-desk overlay, then validate it (strict, as validate_desk.py).

    python tools/assemble_desk.py --season 2026 --week 6 --frags <dir> [--keep data/nfl/research/2026-w06.json] [--summary "..."] [--best id,id,...] [--sections file.json]
    python tools/assemble_desk.py --sport nba --date 2026-10-20 --frags <dir> [--keep data/nba/research/2026-10-20.json] [--summary "..."] [--best id,id,...]

A fragment is one JSON file per game in <dir> (any name ending .json; several per game are fine):
    {"game_id": "2026_06_TEN_IND",
     "notes": {"notes": ["..."], "weather": "...", "injuries": ["..."], "sources": [{"name", "url", "fetched"}]},
     "selections": [ ...selection objects (see the schema in nfl/desk.py)... ],
     "wild_cards": [ ...only when the spec enables wild cards... ],
     "declined": [{"id", "label", "why"}]}
("notes" may also be a plain list of strings.)

--keep carries over, unchanged, everything for games that have already kicked off: their selections, wild cards,
game notes, their places in the sections and in the Best picks. Fragments for games that have kicked off are
skipped. The sections are then filled from the new selections up to each section's max, and the Best picks from
--best (the desk's own choice, strongest first) or, without it, by the spec's rule (measured evidence first, then
the desk's probability, then confidence; one per player, at most two per game, never an unverified price).
--sections takes a JSON file (or a JSON string) {"<section key>": [ids]} for the new selections, when the desk
wants to choose the section lists itself.

The result is written to data/nfl/research/<season>-wNN.json (or data/nba/research/<date>.json) only when it passes
the strict check; otherwise every problem is printed, the draft is written to <dir>/_assembled_invalid.json, and the
exit status is 1.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from nfl.desk import DEFAULT_BAND, EV_RANK, _board, _player_key, current_price, spec_block, started_games  # noqa: E402


def _rank(x: dict) -> tuple:
    return (-EV_RANK.get(x.get("evidence"), 0), -float(x["p"]), -float(x.get("confidence") or 0))


def _lists(out: dict, old: dict | None, started: set, cfg: dict, sections_in: dict | None, best_in: list | None, pub: dict | None = None) -> tuple[dict, list]:
    """Sections and Best picks: started picks keep the places the published page gave them; the rest is filled."""
    from nfl.desk import _sections
    sels = [s for s in out["selections"] if not spec_block(s, cfg)]
    by = {s["id"]: s for s in sels}
    spec = [x for x in (cfg.get("sections") or []) if isinstance(x, dict) and x.get("key")]
    # the previous overlay's lists, as the page showed them (derived when the old file had none)
    old_secs, old_best = {}, []
    if isinstance(pub, dict) and pub.get("ok"):
        old_secs, old_best = dict(pub.get("sections") or {}), list(pub.get("best") or [])      # what the page showed
    elif old:
        old_sels = [dict(s, p=float(s["p"])) for s in old.get("selections") or []
                    if isinstance(s, dict) and "id" in s and "kind" in s and isinstance(s.get("p"), (int, float)) and not spec_block(s, cfg)]
        old_sels.sort(key=lambda x: (-x["p"], -float(x.get("confidence") or 0)))
        old_secs, old_best = _sections(old, old_sels, cfg)
    sections: dict[str, list] = {}
    taken: set = set()
    for sp in spec:
        key, cap = sp["key"], int(sp.get("max") or 6)
        kinds = set(sp.get("markets") or [])
        frozen = [i for i in old_secs.get(key, []) if i in by and by[i]["game_id"] in started]
        if sections_in is not None and key in sections_in:
            new = [i for i in sections_in.get(key, []) if i in by and by[i]["game_id"] not in started]
        else:
            rows = [s for s in sels if s["kind"] in kinds and s["game_id"] not in started and s["id"] not in taken]
            rows.sort(key=lambda x: (-float(x["p"]), -float(x.get("confidence") or 0)))
            new = [s["id"] for s in rows]
        sections[key] = (frozen + [i for i in new if i not in frozen])[:max(cap, len(frozen))]
        taken.update(sections[key])
    if not spec:
        sections = {}
    in_sec = {i for v in sections.values() for i in v}
    bcfg = cfg.get("best") or {}
    cap = int(bcfg.get("max") or 6)
    best = [i for i in old_best if i in by and by[i]["game_id"] in started]
    per_game: dict[str, int] = {}
    players: set = set()
    for i in best:
        per_game[by[i]["game_id"]] = per_game.get(by[i]["game_id"], 0) + 1
        if by[i].get("who"):
            players.add(_player_key(by[i]))
    if best_in is not None:
        cand = [by[i] for i in best_in if i in by and by[i]["game_id"] not in started]
    else:
        cand = [s for s in sels if s["game_id"] not in started and (s["id"] in in_sec if spec else True)
                and s.get("odds_source") != "unverified"]
        cand.sort(key=_rank)
    for s in cand:
        if len(best) >= cap:
            break
        pk = _player_key(s) if s.get("who") else None
        pk = pk or f"{s['game_id']}|{s['kind']}"
        if best_in is None and (per_game.get(s["game_id"], 0) >= 2 or pk in players):
            continue
        best.append(s["id"])
        per_game[s["game_id"]] = per_game.get(s["game_id"], 0) + 1
        players.add(pk)
    return sections, best


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sport", default="nfl", choices=("nfl", "nba"))
    ap.add_argument("--season", type=int)
    ap.add_argument("--week", type=int)
    ap.add_argument("--date", help="NBA: the ET date of the slate")
    ap.add_argument("--frags", required=True)
    ap.add_argument("--keep", help="existing overlay whose started-game selections (and their places in the lists) are kept")
    ap.add_argument("--summary", default="")
    ap.add_argument("--analyst", default="Claude research desk")
    ap.add_argument("--best", help="comma-separated selection ids for the Best picks, strongest first (default: the spec's rule)")
    ap.add_argument("--sections", help="JSON file or JSON string {section key: [ids]} for the new selections (default: filled by desk chance)")
    ap.add_argument("--payload", help="payload JSON (default: docs/nfl/weeks/<season>-wNN.json, or docs/nba/days/<date>.json)")
    a = ap.parse_args(argv)
    now = datetime.now(timezone.utc)
    if a.sport == "nba":
        from nba.desk import load_config, notes, overlay_path, validate
        from nba.ingest import season_now
        if not a.date:
            print("--date is required for the NBA desk"); return 2
        pf = ROOT / "docs" / "nba" / "days" / f"{a.date}.json"
        season = a.season or season_now(datetime.strptime(a.date, "%Y-%m-%d").date())
        out = {"v": 1, "season": season, "date": a.date, "generated_utc": now.strftime("%Y-%m-%d %H:%M UTC"), "analyst": a.analyst,
               "odds_band": list(DEFAULT_BAND), "summary": a.summary, "games": {}, "selections": [], "wild_cards": [], "declined": []}
        out_path = overlay_path(a.date)
    else:
        from nfl.desk import load_config, notes, overlay_path, validate
        if a.season is None or a.week is None:
            print("--season and --week are required for the NFL desk"); return 2
        pf = ROOT / "docs" / "nfl" / "weeks" / f"{a.season}-w{a.week:02d}.json"
        out = {"v": 1, "season": a.season, "week": a.week, "generated_utc": now.strftime("%Y-%m-%d %H:%M UTC"), "analyst": a.analyst,
               "odds_band": list(DEFAULT_BAND), "summary": a.summary, "games": {}, "selections": [], "wild_cards": [], "declined": []}
        out_path = overlay_path(a.season, a.week)
    cfg = load_config()
    if cfg.get("_error"):
        print(f"the spec cannot be read: {cfg['_error']}. Stop and tell the owner; do not run on defaults.")
        return 1
    out["odds_band"] = list(cfg.get("odds_band") or DEFAULT_BAND)
    if a.payload:
        pf = Path(a.payload)
    payload = json.loads(pf.read_text()) if pf.exists() else None
    if payload is None:
        print(f"note: no payload at {pf}; the board and feed checks are skipped")
    games = {g["game_id"]: g for g in (payload or {}).get("games", [])}
    started = started_games(payload) if payload else set()
    kept = 0
    old = None
    if a.keep and not Path(a.keep).exists():
        print(f"note: --keep {a.keep} does not exist yet (first run of the week): nothing to keep")
    if a.keep and Path(a.keep).exists() and payload is None:
        print("--keep needs the published payload to know which games have kicked off; pass --payload or pull the repository"); return 1
    if a.keep and Path(a.keep).exists():
        try:
            old = json.loads(Path(a.keep).read_text())
        except json.JSONDecodeError as e:
            print(f"cannot read --keep {a.keep}: {e}"); return 1
        for key in ("selections", "wild_cards"):
            for s in old.get(key) or []:
                if isinstance(s, dict) and s.get("game_id") in started:
                    out[key].append(s); kept += 1
        for gid, v in (old.get("games") or {}).items():
            if gid in started:
                out["games"][gid] = v
        for x in old.get("declined") or []:
            if isinstance(x, dict) and x.get("game_id") in started:
                out["declined"].append(x)
        if not a.summary:
            out["summary"] = old.get("summary") or ""
    seen = {s["id"] for s in out["selections"] + out["wild_cards"]}
    n_frag = 0
    frag_games: set = set()
    for f in sorted(Path(a.frags).glob("*.json")):
        if f.name.startswith("_"):
            continue
        try:
            d = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            print(f"skip {f.name}: {e}"); continue
        if not isinstance(d, dict):
            print(f"skip {f.name}: not a JSON object"); continue
        gid = d.get("game_id") or f.stem
        if games and gid not in games:
            print(f"skip {f.name}: {gid} is not on this slate"); continue
        if gid in started:
            print(f"skip {f.name}: {gid} has kicked off (its picks stay as they were)"); continue
        n_frag += 1
        frag_games.add(gid)
        nt = d.get("notes") or {}
        if isinstance(nt, list):
            nt = {"notes": nt}
        if isinstance(nt, dict) and any(nt.get(k) for k in ("notes", "weather", "injuries")):
            g = out["games"].setdefault(gid, {"notes": [], "weather": "", "injuries": [], "sources": []})
            g["notes"] += [x for x in nt.get("notes") or [] if isinstance(x, str)]
            g["weather"] = g["weather"] or nt.get("weather") or ""
            g["injuries"] += [x for x in nt.get("injuries") or [] if isinstance(x, str)]
            g["sources"] += [x for x in nt.get("sources") or [] if isinstance(x, dict)]
        for key in ("selections", "wild_cards"):
            for s in d.get(key) or []:
                if not isinstance(s, dict):
                    print(f"skip a non-object entry in {f.name}"); continue
                if s.get("id") in seen:
                    print(f"duplicate selection id {s.get('id')} in {f.name}; skipped"); continue
                s.setdefault("game_id", gid)
                if s.get("game_id") != gid:
                    print(f"skip {s.get('label')} in {f.name}: it names game {s.get('game_id')}, the fragment is for {gid}"); continue
                out[key].append(s); seen.add(s.get("id"))
        for x in d.get("declined") or []:
            if isinstance(x, dict) and x.get("label") and x.get("why"):
                out["declined"].append({"id": x.get("id") or "none", "label": x["label"], "why": x["why"], "game_id": gid})
    # the previous run's picks for games still to play: a game this run covered (a fragment) is replaced by its fragment,
    # and an earlier pick it did not re-list is recorded in declined; a game this run did not cover keeps its earlier
    # picks, except those the current spec no longer allows or whose DraftKings feed price has moved (to declined)
    if old:
        covered = frag_games | {s.get("game_id") for s in out["selections"] + out["wild_cards"]}
        declined_ids = {x.get("id") for x in out["declined"]}
        board_ids = set(_board(payload)) if payload else set()
        carried = 0

        def decline(x: dict, why: str) -> None:
            if x.get("id") not in declined_ids:
                out["declined"].append({"id": x.get("id") or "none", "label": x.get("label") or "?", "why": why, "game_id": x.get("game_id")})
                declined_ids.add(x.get("id"))
                print(f"note: {x.get('label')} moved to declined ({why})")
        for key in ("selections", "wild_cards"):
            for x in old.get(key) or []:
                if not isinstance(x, dict) or x.get("game_id") in started or x.get("id") in seen:
                    continue
                if x.get("game_id") in covered:
                    decline(x, "dropped by this run (not re-listed in the game's fragment)")
                    continue
                if x.get("id") in declined_ids:
                    continue
                why = spec_block(x, cfg)
                if not why and cfg.get("lines") == "draftkings" and x.get("odds_source") == "unverified":
                    why = "price never confirmed on DraftKings"
                if not why and key == "wild_cards" and not (cfg.get("wild_cards") or {}).get("enabled", True):
                    why = "wild cards are switched off in the spec"
                if not why and payload and not str(x.get("id") or "").startswith("desk|") and x.get("id") not in board_ids:
                    why = "its DraftKings line has moved off the board since the earlier run; re-research it"
                if not why and x.get("odds_source") == "feed" and x.get("game_id") in games:
                    try:
                        now_p = current_price(x, games[x["game_id"]])
                    except Exception:  # noqa: BLE001
                        now_p = None
                    if now_p is None:
                        why = "no longer in the odds feed"
                    elif (now_p.get("line") is not None and x.get("line") is not None and abs(float(now_p["line"]) - float(x["line"])) > 1e-9) \
                            or (now_p.get("odds") and x.get("odds") and abs(float(now_p["odds"]) - float(x["odds"])) > 0.06):
                        why = f"DraftKings moved since the earlier run (now {now_p.get('line')} at {now_p.get('odds')}); re-research it"
                if why:
                    decline(x, f"set aside on re-check: {why}")
                    continue
                out[key].append(x); seen.add(x.get("id")); carried += 1
        for gid, v in (old.get("games") or {}).items():
            if gid not in started and gid not in covered:
                out["games"][gid] = v
        for x in old.get("declined") or []:
            if isinstance(x, dict) and x.get("game_id") not in started and x.get("game_id") not in covered \
                    and (x.get("id") in (None, "none") or (x.get("id") not in declined_ids and x.get("id") not in seen)) and x.get("label") and x.get("why"):
                out["declined"].append(x)
                declined_ids.add(x.get("id"))
        if carried:
            print(f"note: {carried} pick(s) from the previous run kept for games this run did not re-research")
    if not out["wild_cards"]:
        out.pop("wild_cards")
    out["selections"].sort(key=lambda s: (-float(s.get("p") or 0), -float(s.get("confidence") or 0)))
    # sections and Best picks (started picks keep their places; the rest by the desk's choice or the spec's rule)
    sec_in = None
    if a.sections:
        try:
            src = Path(a.sections)
            sec_in = json.loads(src.read_text() if src.exists() else a.sections)
            if not isinstance(sec_in, dict):
                raise ValueError("must be an object {section key: [ids]}")
        except (OSError, ValueError) as e:
            print(f"--sections: {e}"); return 1
    best_in = None
    if a.best:
        best_in = [i.strip() for i in a.best.split(",") if i.strip()]
        ids = {s.get("id") for s in out["selections"]}
        unknown = [i for i in best_in if i not in ids]
        if unknown:
            print(f"--best: {len(unknown)} id(s) are not selections in this overlay: {', '.join(unknown)}"); return 1
    valid_sels = [s for s in out["selections"] if isinstance(s.get("p"), (int, float)) and "id" in s and "kind" in s and "game_id" in s]
    pub = ((payload or {}).get("bot") or {}).get("desk")
    sections, best = _lists({**out, "selections": valid_sels}, old, started, cfg, sec_in, best_in, pub)
    if sections or (cfg.get("sections") or []):
        out["sections"] = sections
    out["best"] = best
    errs = validate(out, payload)
    if errs:
        print(f"{len(errs)} problem(s) in the assembled overlay:")
        for e in errs:
            print(" -", e)
        bad = Path(a.frags) / "_assembled_invalid.json"
        bad.write_text(json.dumps(out, indent=1, ensure_ascii=False))
        print(f"nothing was written to {out_path}; the draft is at {bad}")
        return 1
    f = out_path
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(f"wrote {f}: {len(out['selections'])} selections and {len(out.get('wild_cards') or [])} wild cards ({kept} kept from games that kicked off), "
          f"{len(out['declined'])} declined, {n_frag} fragments, {len(out['games'])} games with notes")
    for n in notes(out, payload):
        print("note:", n)
    lab = {x["id"]: x for x in out["selections"]}
    print(f"\n{(cfg.get('best') or {}).get('label') or 'Best picks'} ({len(best)}):")
    for i, sid in enumerate(best, 1):
        s = lab[sid]
        print(f"{i:2d}. {s['label']:<46} {float(s['odds']):.2f} {s['odds_source']:<11} desk {float(s['p'])*100:.0f}%  {s['grade']} {s['evidence']}")
    for sp in cfg.get("sections") or []:
        ids = sections.get(sp.get("key")) or []
        print(f"\n{sp.get('label') or sp.get('key')} ({len(ids)} of {sp.get('min', 0)} to {sp.get('max', '?')}):")
        for i, sid in enumerate(ids, 1):
            s = lab[sid]
            print(f"{i:2d}. {s['label']:<46} {float(s['odds']):.2f} desk {float(s['p'])*100:.0f}%  {s['grade']} {s['evidence']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
