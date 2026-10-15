"""Touchdown-scorer candidates for a game: who is available and what share of the team's touchdowns each
one is expected to score."""
from __future__ import annotations

from .config import CFG, ModelConfig
from .features import Profiles

SKILL = {"QB", "RB", "FB", "WR", "TE"}
COVERAGE = 0.97          # share of a team's offensive touchdowns scored by its listed candidates (measured in the backtest)


def candidates(P: Profiles, team: str, *, played: set[str] | None = None, available: set[str] | None = None,
               out: set[str] | None = None, positions: dict[str, str] | None = None, recent_games: int = 4,
               cfg: ModelConfig = CFG) -> list[dict]:
    """Players with a measured role for `team`.

    played     -- (backtest) the players who touched the ball in the game; everyone else is skipped
    available  -- (live) the active roster for the week; players not on it are skipped
    out        -- (live) players ruled out or doubtful on the injury report
    positions  -- player id -> position, for the label on the page
    """
    tp = P.teams.get(team)
    if tp is None:
        return []
    recent_dates = {g["date"] for g in tp.recent[-recent_games:]}
    rows = []
    for pid, pp in P.players.items():
        if pp.team != team or pp.games == 0:
            continue
        if played is not None and pid not in played:
            continue
        if played is None:
            if available is not None and pid not in available:
                continue
            if out and pid in out:
                continue
            if not any(r["date"] in recent_dates for r in pp.recent[-recent_games:]) and (available is None or pid not in available):
                continue
            if available is None and not any(r["date"] in recent_dates for r in pp.recent[-recent_games:]):
                continue
        if played is None:
            # live: a real recent role (touches or targets in the last three games, or a third of the snaps last game)
            last3 = pp.recent[-3:]
            usage = sum(r["car"] + r["tgt"] for r in last3)
            snap_last = pp.snaps[-1][1] if pp.snaps else 0.0
            if usage < 3 and snap_last < 0.33:
                continue
        rec, rush = pp.shares(cfg)
        trend = pp.snap_trend(cfg) if cfg.use_snap_trend else 1.0
        rec, rush = rec * trend, rush * trend
        if rec + rush < 0.01:
            continue
        rows.append({"id": pid, "name": pp.name, "pos": (positions or {}).get(pid, ""), "rec_share": rec, "rush_share": rush,
                     "games": pp.games, "tgt_share": round(pp.tgt / pp.t_tgt, 3) if pp.t_tgt else 0.0,
                     "car_share": round(pp.car / pp.t_car, 3) if pp.t_car else 0.0,
                     "rz_share": round((pp.rzt + pp.rzc) / (pp.t_rzt + pp.t_rzc), 3) if (pp.t_rzt + pp.t_rzc) else 0.0,
                     "td_games": pp.games_td, "recent": pp.recent[-5:], "snap_recent": [x[1] for x in pp.snaps[-3:]], "snap_trend": round(trend, 3)})
    # the listed players together score COVERAGE of the team's touchdowns: rescale each kind of share
    for key in ("rec_share", "rush_share"):
        s = sum(r[key] for r in rows)
        if s > 0:
            f = COVERAGE / s
            for r in rows:
                r[key] = min(0.85, r[key] * f)
    return rows


__all__ = ["candidates", "SKILL", "COVERAGE"]
