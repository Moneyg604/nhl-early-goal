"""Shot quality: expected goals from MoneyPuck's shot-level data, joined to the play-by-play records.

MoneyPuck publishes every unblocked shot with an expected-goal value (xGoal), the game clock, the
shooting team and the goalie. This module turns a season file into one compact record per game:

    {"game_id": 2025020001, "home": "FLA", "away": "CHI",
     "xg": {"home": {"e5": 0.21, "e10": 0.48, "reg": 2.9, "goals_reg": 3}, "away": {...}},
     "goalies": {"8475683": {"xg": 2.1, "goals": 2, "shots": 27, "e10_xg": 0.4, "e10_goals": 0}}}

Those feed the team and goalie profiles (`features.py`) as an alternative to shot counts and raw save %
when `ModelConfig.use_xg` is on: shot-quality rates for and against, finishing as goals over xG, and
goalie quality as goals allowed over xG faced. Whether that helps is decided by the walk-forward test
in CI (`backtest --prune`), not assumed here.

The data is only reachable from the GitHub runner (the files live on moneypuck.com); locally the module
works from whatever season files are already under data/xg/.
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from .config import DATA_DIR

XG_DIR = DATA_DIR / "xg"
URLS = ("https://peter-tanner.com/moneypuck/downloads/shots_{y}.zip", "https://moneypuck.com/moneypuck/playerData/shots/shots_{y}.zip")
COLS = ["game_id", "season", "period", "time", "event", "teamCode", "isHomeTeam", "homeTeamCode", "awayTeamCode", "xGoal", "goal",
        "goalieIdForShot", "shotOnEmptyNet", "isPlayoffGame", "shotRush", "shotRebound"]


def season_year(season: int) -> int:
    """20252026 -> 2025 (MoneyPuck names files by the season's first year)."""
    return season // 10000


def xg_file(season: int) -> Path:
    return XG_DIR / f"xg_{season}.jsonl"


def download_shots(season: int, force: bool = False) -> Path | None:
    """Fetch the season zip into data/xg/ (kept so a finished season is never fetched twice)."""
    import requests  # type: ignore

    XG_DIR.mkdir(parents=True, exist_ok=True)
    y = season_year(season)
    p = XG_DIR / f"shots_{y}.zip"
    if p.exists() and not force:
        return p
    for u in URLS:
        try:
            r = requests.get(u.format(y=y), timeout=300, headers={"User-Agent": "Mozilla/5.0"})
            if r.ok and len(r.content) > 10_000:
                p.write_bytes(r.content)
                return p
        except Exception:  # noqa: BLE001
            continue
    return None


def convert(zip_path: Path, season: int, out: Path | None = None) -> int:
    """Season zip -> per-game xG records (regular season only). Returns the number of games written."""
    import pandas as pd  # type: ignore

    z = zipfile.ZipFile(zip_path)
    name = [n for n in z.namelist() if n.endswith(".csv")][0]
    with z.open(name) as f:
        df = pd.read_csv(io.TextIOWrapper(f, encoding="utf-8"), usecols=lambda c: c in COLS, low_memory=False)
    df = df[(df["isPlayoffGame"].fillna(0).astype(int) == 0)]
    y = season_year(season)
    df["nhl_id"] = (str(y) + "0" + df["game_id"].astype(int).astype(str).str.zfill(5)).astype(int)
    df["t"] = df["time"].astype(float)
    df["xg"] = df["xGoal"].astype(float).fillna(0.0)
    df["g"] = df["goal"].fillna(0).astype(int)
    df["en"] = df["shotOnEmptyNet"].fillna(0).astype(int)
    df["home"] = df["isHomeTeam"].fillna(0).astype(int) == 1
    recs = []
    for gid, gdf in df.groupby("nhl_id"):
        home, away = str(gdf["homeTeamCode"].iloc[0]), str(gdf["awayTeamCode"].iloc[0])
        xg = {}
        for side, mask in (("home", gdf["home"]), ("away", ~gdf["home"])):
            s = gdf[mask & (gdf["en"] == 0)]
            reg = s[s["t"] < 3600]
            xg[side] = {"e5": round(float(s[s["t"] < 300]["xg"].sum()), 4), "e10": round(float(s[s["t"] < 600]["xg"].sum()), 4),
                        "reg": round(float(reg["xg"].sum()), 4), "goals_reg": int(reg["g"].sum()), "goals_e10": int(s[s["t"] < 600]["g"].sum()),
                        "attempts_e10": int((s["t"] < 600).sum()), "rush_e10": int(((s["t"] < 600) & (s["shotRush"].fillna(0).astype(int) == 1)).sum())}
        goalies = {}
        g_ok = gdf[(gdf["en"] == 0) & gdf["goalieIdForShot"].notna()]
        for gk, sdf in g_ok.groupby("goalieIdForShot"):
            reg = sdf[sdf["t"] < 3600]
            goalies[str(int(gk))] = {"xg": round(float(reg["xg"].sum()), 4), "goals": int(reg["g"].sum()), "shots": int(len(reg)),
                                     "e10_xg": round(float(sdf[sdf["t"] < 600]["xg"].sum()), 4), "e10_goals": int(sdf[sdf["t"] < 600]["g"].sum())}
        recs.append({"game_id": int(gid), "home": home, "away": away, "xg": xg, "goalies": goalies})
    out = out or xg_file(season)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as fh:
        for r in recs:
            fh.write(json.dumps(r) + "\n")
    return len(recs)


def ensure_season(season: int, is_current: bool = False) -> int:
    """Download + convert when missing (or when the current season's file is older than a day). Never raises."""
    import time

    f = xg_file(season)
    try:
        if f.exists() and (not is_current or time.time() - f.stat().st_mtime < 20 * 3600):
            return sum(1 for _ in f.open())
        z = download_shots(season, force=is_current)
        if z is None:
            return sum(1 for _ in f.open()) if f.exists() else 0
        return convert(z, season)
    except Exception:  # noqa: BLE001
        return sum(1 for _ in f.open()) if f.exists() else 0


def load_xg(seasons: list[int]) -> dict[int, dict]:
    """game_id -> xG record for every season file on disk."""
    out: dict[int, dict] = {}
    for s in seasons:
        f = xg_file(s)
        if not f.exists():
            continue
        with f.open() as fh:
            for line in fh:
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                out[int(r["game_id"])] = r
    return out
