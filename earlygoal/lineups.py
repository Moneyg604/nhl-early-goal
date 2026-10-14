"""Lines, pairs, special-teams units and injuries from DailyFaceoff's line-combinations pages.

Display only. Nothing here moves a probability: no lineup variable has shown out-of-sample value for the
five-minute window, and the page says so next to the data. It is on the dossier so a reader can see a
missing top-pair defenceman or a game-time decision before betting.

The page embeds its data as Next.js JSON: props.pageProps.combinations.players[] with groupIdentifier
(f1..f4, d1..d3, g, pp1, pp2, pk1, pk2 ...), categoryIdentifier (ev, pp, pk, ...), injuryStatus,
gameTimeDecision, latestNews{details, createdAt} and season / last10 / last5 counting stats; and
props.pageProps.sortedTeams[] with shortName and slug for every team.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .config import DATA_DIR

BASE = "https://www.dailyfaceoff.com/teams/{slug}/line-combinations"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept": "text/html,application/xhtml+xml"}
# fallback slugs, used until a page's sortedTeams list is read
SLUGS = {
    "ANA": "anaheim-ducks", "BOS": "boston-bruins", "BUF": "buffalo-sabres", "CAR": "carolina-hurricanes", "CBJ": "columbus-blue-jackets",
    "CGY": "calgary-flames", "CHI": "chicago-blackhawks", "COL": "colorado-avalanche", "DAL": "dallas-stars", "DET": "detroit-red-wings",
    "EDM": "edmonton-oilers", "FLA": "florida-panthers", "LAK": "los-angeles-kings", "MIN": "minnesota-wild", "MTL": "montreal-canadiens",
    "NJD": "new-jersey-devils", "NSH": "nashville-predators", "NYI": "new-york-islanders", "NYR": "new-york-rangers", "OTT": "ottawa-senators",
    "PHI": "philadelphia-flyers", "PIT": "pittsburgh-penguins", "SEA": "seattle-kraken", "SJS": "san-jose-sharks", "STL": "st-louis-blues",
    "TBL": "tampa-bay-lightning", "TOR": "toronto-maple-leafs", "UTA": "utah-mammoth", "VAN": "vancouver-canucks", "VGK": "vegas-golden-knights",
    "WPG": "winnipeg-jets", "WSH": "washington-capitals",
}
GROUP_LABELS = {"f1": "Line 1", "f2": "Line 2", "f3": "Line 3", "f4": "Line 4", "d1": "Pair 1", "d2": "Pair 2", "d3": "Pair 3",
                "g": "Goalies", "g1": "Goalies", "pp1": "PP1", "pp2": "PP2", "pk1": "PK1", "pk2": "PK2"}


def _num(x) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def parse_lineup_page(html: str) -> dict | None:
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None
    pp = (d.get("props") or {}).get("pageProps") or {}
    comb = pp.get("combinations") or {}
    players = comb.get("players") or []
    if not players:
        return None
    groups: dict[str, list[dict]] = {}
    injuries: list[dict] = []
    for p in players:
        name = p.get("name") or ""
        pos = (p.get("positionIdentifier") or "").upper()
        gid = (p.get("groupIdentifier") or "").lower()
        cat = (p.get("categoryIdentifier") or "").lower()
        news = p.get("latestNews") or {}
        l10, l5 = p.get("last10") or {}, p.get("last5") or {}
        entry = {"name": name, "pos": pos, "group": gid, "category": cat,
                 "shots_last10_pg": round((_num(l10.get("shots")) or 0) / max(1.0, _num(l10.get("gamesPlayed")) or 1), 2) if l10 else None,
                 "toi_last5": round((_num(l5.get("toiMinutes")) or 0) / max(1.0, _num(l5.get("gamesPlayed")) or 1), 1) if l5 else None}
        key = gid
        if cat in ("pp", "pk") and not gid.startswith(cat):
            key = cat + (gid[-1] if gid and gid[-1].isdigit() else "1")
        if gid in ("g", "g1", "g2", "goalies"):
            key = "g"
        groups.setdefault(key, []).append(entry)
        status = str(p.get("injuryStatus") or "None")
        gtd = str(p.get("gameTimeDecision") or "False").lower() == "true"
        if status.lower() not in ("none", "", "null") or gtd:
            injuries.append({"name": name, "pos": pos, "status": status if status.lower() not in ("none", "") else "game-time decision",
                             "game_time_decision": gtd, "news": (news.get("details") or "").strip()[:220], "news_at": news.get("createdAt")})
    teams = {}
    for t in pp.get("sortedTeams") or []:
        if t.get("shortName") and t.get("slug"):
            teams[t["shortName"]] = t["slug"]
    lines = {k: [e["name"] for e in v] for k, v in groups.items() if k in GROUP_LABELS}
    return {
        "team": comb.get("teamAbbreviation"), "updated_at": comb.get("updatedAt"), "source_name": comb.get("sourceName"),
        "lines": lines, "groups": {k: v for k, v in groups.items() if k in GROUP_LABELS}, "injuries": injuries, "teams": teams,
    }


def scrape_lineups(teams: list[str], date: str, cache: bool = True) -> dict[str, dict]:
    """Lineups for `teams`, cached per date under data/cache. Best effort: a team that fails is simply absent."""
    try:
        import requests  # type: ignore
    except Exception:  # pragma: no cover
        return {}
    cache_file = DATA_DIR / "cache" / f"lineups-{date}.json"
    out: dict[str, dict] = {}
    if cache and cache_file.exists():
        try:
            out = json.loads(cache_file.read_text())
        except json.JSONDecodeError:
            out = {}
    slugs = dict(SLUGS)
    for team in teams:
        if team in out:
            continue
        slug = slugs.get(team)
        if not slug:
            continue
        try:
            r = requests.get(BASE.format(slug=slug), timeout=25, headers=UA)
            r.raise_for_status()
            parsed = parse_lineup_page(r.text)
        except Exception:  # noqa: BLE001
            parsed = None
        if parsed:
            slugs.update(parsed.pop("teams", {}) or {})
            parsed["fetched_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            out[team] = parsed
    if cache:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps(out))
    return out


def summarize_for_game(lu: dict | None) -> dict | None:
    """The part of a team's lineup the dossier shows."""
    if not lu:
        return None
    lines = lu.get("lines") or {}
    groups = lu.get("groups") or {}
    top = []
    for k in ("f1", "d1"):
        for e in groups.get(k, []):
            top.append({"name": e["name"], "pos": e["pos"], "group": k, "shots_last10_pg": e.get("shots_last10_pg"), "toi_last5": e.get("toi_last5")})
    return {
        "updated_at": lu.get("updated_at"), "source_name": lu.get("source_name"), "fetched_utc": lu.get("fetched_utc"),
        "lines": {k: lines[k] for k in ("f1", "f2", "f3", "f4", "d1", "d2", "d3", "g", "pp1", "pp2") if k in lines},
        "injuries": lu.get("injuries") or [],
        "top_unit": top,
    }
