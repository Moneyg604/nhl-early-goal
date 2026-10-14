"""Glue: slate + profiles -> models -> simulations -> ranked payload."""
from __future__ import annotations

from .config import CFG, ModelConfig
from .features import GoalieProfile, LeagueProfile, TeamProfile
from .goalies import resolve_starter
from .model import SideInputs, build_game_model
from .rank import build_payload, game_row, load_odds
from .research import build_index, game_research, slate_research
from .sim import simulate


def league_summary(lp: LeagueProfile, n_cur_games: int, n_prior_games: int) -> dict:
    return {
        "games_in_profile": lp.games,
        "current_season_games": n_cur_games,
        "prior_season_games": n_prior_games,
        "p_no_goal_5_observed": round(lp.p_no_goal_5, 4) if lp.games else None,
        "p_no_goal_10_observed": round(lp.p_no_goal_10, 4) if lp.games else None,
        "goals_per_team_game_first10": round(lp.early10_goals_per_game, 3) if lp.games else None,
        "p1_goals_per_team_game": round(lp.p1_goals_per_game, 3) if lp.games else None,
        "home_mult": round(lp.home_mult, 4),
        "league_sv": round(lp.sv_pct, 4) if lp.games else None,
        "context_effects": {k: round(v, 4) for k, v in (lp.context_mults or {}).items()},
        "context_samples": lp.context_samples,
    }


def run_slate(
    slate: list[dict],
    lp: LeagueProfile,
    teams: dict[str, TeamProfile],
    goalies: dict[int, GoalieProfile],
    date: str,
    overrides: dict | None = None,
    dfo: dict | None = None,
    sims: int = CFG.sims,
    seed: int | None = None,
    cfg: ModelConfig = CFG,
    meta: dict | None = None,
    odds: dict | None = None,
    records: list | None = None,
    lineups: dict | None = None,
) -> tuple[dict, list]:
    """`records` (all seasons on disk) enables the research dossier on every game."""
    overrides = overrides or {}
    dfo = dfo or {}
    odds = odds if odds is not None else load_odds(date)
    ix = build_index(records) if records else None
    season = int(date[:4]) * 10000 + int(date[:4]) + 1 if int(date[5:7]) >= 9 else (int(date[:4]) - 1) * 10000 + int(date[:4])
    rows, models = [], []
    for i, g in enumerate(slate):
        sides = {}
        for key in ("home", "away"):
            team = g[key]
            rest = (g.get("rest") or {}).get(key) or {}
            st = resolve_starter(team, date, goalies, overrides, dfo, rest)
            sides[key] = SideInputs(
                team=team,
                is_home=key == "home",
                profile=teams.get(team),
                goalie=st["goalie"],
                goalie_status=st["status"],
                goalie_source=st["source"],
                goalie_note=st["note"],
                rest=rest,
            )
        gm = build_game_model(g, sides["home"], sides["away"], lp, cfg)
        r = simulate(gm, sims=sims, seed=None if seed is None else seed + i)
        row = game_row(gm, r, odds)
        if ix is not None:
            row["research"] = game_research(ix, {"date": date, "home": g["home"], "away": g["away"]}, sides, season, lp.context_mults or {})
            if lineups:
                from .lineups import summarize_for_game

                row["research"]["lineups"] = {k: summarize_for_game(lineups.get(g[k])) for k in ("home", "away")}
        rows.append(row)
        models.append((gm, r))
    payload = build_payload(rows, date, league_summary(lp, meta.get("current_season_games", 0) if meta else 0, meta.get("prior_season_games", 0) if meta else 0), meta or {})
    if ix is not None:
        payload["research"] = slate_research(ix, lp.context_mults or {}, lp.context_samples or {}, meta or {}, xg_games=lp.xg_games)
    return payload, models
