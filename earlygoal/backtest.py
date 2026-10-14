"""Walk-forward backtest of the first-5 / first-10 no-goal probabilities.

For every date in the evaluation window the model only knows games strictly
before that date (prior season + current season to date). Team and goalie
profiles are updated incrementally after each slate; the league hazard curve
is refreshed every `league_refresh_days`. Starting goalies default to the
actual starters from the game record (the model with correct goalie info);
--projected-goalies uses the usage heuristic instead.

Reported: Brier score and log loss vs a constant league-rate baseline,
calibration by probability bucket, the hit rate of the model's top-1 / top-3
picks per slate vs the slate average, and break-even hit rates by price.
"""
from __future__ import annotations

import math
from collections import defaultdict

from .config import CFG, ModelConfig, prior_weight
from .features import GoalieProfile, TeamProfile, add_games_to_profiles, build_league_profile, compute_norms, infer_current_season
from .goalies import resolve_starter
from .ingest import GameRecord
from .model import SideInputs, build_game_model


def _outcomes(g: GameRecord) -> tuple[int, int]:
    first = min((e.minute for e in g.events if e.type == "goal"), default=99.0)
    return int(first >= 5), int(first >= 10)


def run_backtest(
    prior: list[GameRecord],
    current: list[GameRecord],
    start: str | None = None,
    end: str | None = None,
    projected_goalies: bool = False,
    cfg: ModelConfig = CFG,
    verbose: bool = True,
    league_refresh_days: int = 14,
    with_sim: bool = False,
    sim_paths: int = 20000,
) -> dict:
    cur = sorted([g for g in current if g.final], key=lambda x: (x.date, x.game_id))
    if not cur:
        raise SystemExit("backtest needs current-season games on disk; run ingest first")
    dates = sorted({g.date for g in cur})
    eval_dates = [d for d in dates if (not start or d >= start) and (not end or d <= end)]
    teams: dict[str, TeamProfile] = {}
    goalies: dict[int, GoalieProfile] = {}
    by_season: dict[int, list[GameRecord]] = {}
    for g in prior:
        by_season.setdefault(g.season, []).append(g)
    cur_season = infer_current_season(cur, prior)
    for season in sorted(by_season):
        add_games_to_profiles(teams, goalies, by_season[season], prior_weight(season, cur_season, cfg), False)
    seen: list[GameRecord] = []
    lp = build_league_profile(prior, cfg)
    compute_norms(lp, teams, goalies, cfg)
    last_refresh = -10**9
    rows = []
    for i, d in enumerate(dates):
        slate = [g for g in cur if g.date == d]
        if d in eval_dates:
            if i - last_refresh >= league_refresh_days:
                lp = build_league_profile(prior + seen, cfg, weights=[1.0] * len(prior) + [cfg.league_current_weight] * len(seen))
                compute_norms(lp, teams, goalies, cfg)
                last_refresh = i
            base5, base10 = lp.p_no_goal_5, lp.p_no_goal_10
            for g in slate:
                sides = {}
                for key in ("home", "away"):
                    team = g.home if key == "home" else g.away
                    rest = (g.rest or {}).get(key) or {}
                    if projected_goalies:
                        st = resolve_starter(team, d, goalies, {}, {}, rest)
                        gp, status = st["goalie"], st["status"]
                    else:
                        gid = g.starters.get(key)
                        gp = goalies.get(gid) if gid else None
                        status = "confirmed" if gp else "unknown"
                    sides[key] = SideInputs(team, key == "home", teams.get(team), gp, status, "backtest", "", rest)
                gm = build_game_model({"game_id": g.game_id, "date": d, "start_utc": g.start_utc}, sides["home"], sides["away"], lp, cfg)
                y5, y10 = _outcomes(g)
                eh, ea = gm.expected_goals()
                gh1 = sum(1 for e in g.events if e.type == "goal" and e.team == g.home and e.minute < 20)
                ga1 = sum(1 for e in g.events if e.type == "goal" and e.team == g.away and e.minute < 20)
                row = {"gh1": gh1, "ga1": ga1, "date": d, "game": f"{g.away}@{g.home}", "p5": gm.p_no_goal_before(5), "p10": gm.p_no_goal_before(10),
                       "y5": y5, "y10": y10, "b5": base5, "b10": base10, "tier": gm.tier,
                       "xg_h": eh, "xg_a": ea, "gh": g.home_score, "ga": g.away_score, "ended": g.ended_in}
                if with_sim:
                    from .sim import simulate
                    r = simulate(gm, sims=sim_paths, seed=g.game_id % 100000)
                    row.update({"fg_home": r.fg_home_win, "p1_home": r.p1_home_win, "p1_tie": r.p1_tie, "p1_away": r.p1_away_win,
                                "home_m15": r.fg_home_cover_m15, "away_m15": r.fg_away_cover_m15, "over55": r.fg_over_55})
                rows.append(row)
            if verbose and len(rows) % 200 < len(slate):
                print(f"  backtest through {d}: {len(rows)} games")
        add_games_to_profiles(teams, goalies, slate, 1.0, True)
        seen += slate
    s = summarize(rows)
    s["rows"] = rows
    return s


def _brier(ps, ys):
    return sum((p - y) ** 2 for p, y in zip(ps, ys)) / len(ps)


def _logloss(ps, ys):
    eps = 1e-6
    return -sum(y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps)) for p, y in zip(ps, ys)) / len(ps)


def summarize(rows: list[dict]) -> dict:
    out = {"n": len(rows)}
    if not rows:
        return out
    for w in ("5", "10"):
        ps = [r["p" + w] for r in rows]
        ys = [r["y" + w] for r in rows]
        bs = [r["b" + w] for r in rows]
        buckets = defaultdict(lambda: [0, 0.0, 0.0])
        for p, y in zip(ps, ys):
            k = min(19, int(p * 20))
            buckets[k][0] += 1
            buckets[k][1] += p
            buckets[k][2] += y
        cal = {f"{k/20:.2f}-{(k+1)/20:.2f}": {"n": v[0], "pred": round(v[1] / v[0], 3), "actual": round(v[2] / v[0], 3)} for k, v in sorted(buckets.items())}
        by_date = defaultdict(list)
        for r in rows:
            by_date[r["date"]].append(r)
        top1 = top3 = n1 = n3 = 0
        bottom1 = 0
        for d, rs in by_date.items():
            rs = sorted(rs, key=lambda r: -r["p" + w])
            top1 += rs[0]["y" + w]
            bottom1 += rs[-1]["y" + w]
            n1 += 1
            for r in rs[:3]:
                top3 += r["y" + w]
                n3 += 1
        # decile lift: actual rate in the top 20% of model probabilities vs bottom 20%
        order = sorted(range(len(ps)), key=lambda i: -ps[i])
        k5 = max(1, len(ps) // 5)
        top_q = sum(ys[i] for i in order[:k5]) / k5
        bot_q = sum(ys[i] for i in order[-k5:]) / k5
        out["first" + w] = {
            "brier_model": round(_brier(ps, ys), 5),
            "brier_baseline": round(_brier(bs, ys), 5),
            "logloss_model": round(_logloss(ps, ys), 5),
            "logloss_baseline": round(_logloss(bs, ys), 5),
            "actual_rate": round(sum(ys) / len(ys), 4),
            "mean_pred": round(sum(ps) / len(ps), 4),
            "top1_hit_rate": round(top1 / n1, 4) if n1 else None,
            "bottom1_hit_rate": round(bottom1 / n1, 4) if n1 else None,
            "top3_hit_rate": round(top3 / n3, 4) if n3 else None,
            "top_quintile_actual": round(top_q, 4),
            "bottom_quintile_actual": round(bot_q, 4),
            "slates": n1,
            "calibration": cal,
        }
    # joint markets, when the simulation ran
    if rows and "fg_home" in rows[0]:
        import numpy as np

        def score(name, p, y, const):
            p = np.clip(np.array(p, dtype=float), 1e-6, 1 - 1e-6)
            y = np.array(y, dtype=float)
            c = np.full(len(y), const)
            order = np.argsort(-p)
            q = max(1, len(p) // 5)
            return {
                "logloss_model": round(float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean()), 5),
                "logloss_constant": round(float(-(y * np.log(c) + (1 - y) * np.log(1 - c)).mean()), 5),
                "brier_model": round(float(((p - y) ** 2).mean()), 5),
                "brier_constant": round(float(((c - y) ** 2).mean()), 5),
                "mean_pred": round(float(p.mean()), 4), "actual": round(float(y.mean()), 4),
                "top_quintile_pred": round(float(p[order[:q]].mean()), 4), "top_quintile_actual": round(float(y[order[:q]].mean()), 4),
                "bottom_quintile_pred": round(float(p[order[-q:]].mean()), 4), "bottom_quintile_actual": round(float(y[order[-q:]].mean()), 4),
                "n": int(len(y)),
            }

        yh = [1.0 if r["gh"] > r["ga"] else 0.0 for r in rows]
        out["fg_ml_home"] = score("fg_ml_home", [r["fg_home"] for r in rows], yh, sum(yh) / len(yh))
        y15 = [1.0 if (r["gh"] - r["ga"]) >= 2 else 0.0 for r in rows]
        out["fg_home_minus15"] = score("fg_home_minus15", [r["home_m15"] for r in rows], y15, sum(y15) / len(y15))
        ya15 = [1.0 if (r["ga"] - r["gh"]) >= 2 else 0.0 for r in rows]
        out["fg_away_minus15"] = score("fg_away_minus15", [r["away_m15"] for r in rows], ya15, sum(ya15) / len(ya15))
        yo = [1.0 if (r["gh"] + r["ga"]) > 5.5 else 0.0 for r in rows]
        out["fg_over55"] = score("fg_over55", [r["over55"] for r in rows], yo, sum(yo) / len(yo))
        y1h = [1.0 if r["gh1"] > r["ga1"] else 0.0 for r in rows]
        out["p1_home_win"] = score("p1_home_win", [r["p1_home"] for r in rows], y1h, sum(y1h) / len(y1h))
        y1a = [1.0 if r["ga1"] > r["gh1"] else 0.0 for r in rows]
        out["p1_away_win"] = score("p1_away_win", [r["p1_away"] for r in rows], y1a, sum(y1a) / len(y1a))
        y1t = [1.0 if r["ga1"] == r["gh1"] else 0.0 for r in rows]
        out["p1_tie"] = score("p1_tie", [r["p1_tie"] for r in rows], y1t, sum(y1t) / len(y1t))
    # full-game sanity: expected vs actual goals
    xg = sum(r["xg_h"] + r["xg_a"] for r in rows) / len(rows)
    ag = sum(min(r["gh"], 99) + r["ga"] - (1 if r["ended"] in ("OT", "SO") else 0) for r in rows) / len(rows)
    out["full_game"] = {"mean_expected_regulation_goals": round(xg, 3), "mean_actual_regulation_goals": round(ag, 3)}
    out["break_even"] = {f"price {p:.2f}": round(1 / p, 4) for p in (1.20, 1.25, 1.30, 1.35, 1.40, 1.50, 1.80, 2.00)}
    return out


def print_report(s: dict) -> None:
    print(f"\nBacktest over {s['n']} games")
    for w in ("5", "10"):
        k = "first" + w
        if k not in s:
            continue
        r = s[k]
        print(f"\nUnder 0.5 goals, first {w}:00")
        print(f"  actual no-goal rate {r['actual_rate']:.3f}   mean model prob {r['mean_pred']:.3f}")
        print(f"  Brier   model {r['brier_model']:.5f}   baseline {r['brier_baseline']:.5f}   ({'better' if r['brier_model'] < r['brier_baseline'] else 'NOT better'} than league constant)")
        print(f"  LogLoss model {r['logloss_model']:.5f}   baseline {r['logloss_baseline']:.5f}")
        print(f"  top-1 pick per slate hit {r['top1_hit_rate']:.3f}   top-3 {r['top3_hit_rate']:.3f}   bottom-1 {r['bottom1_hit_rate']:.3f}   over {r['slates']} slates")
        print(f"  top quintile actual {r['top_quintile_actual']:.3f}   bottom quintile actual {r['bottom_quintile_actual']:.3f}")
        print("  calibration (bucket: n, predicted, actual)")
        for b, v in r["calibration"].items():
            print(f"    {b}: n={v['n']:4d}  pred={v['pred']:.3f}  actual={v['actual']:.3f}")
    for k in ("fg_ml_home", "fg_home_minus15", "fg_away_minus15", "fg_over55", "p1_home_win", "p1_away_win", "p1_tie"):
        if k in s:
            r = s[k]
            print(f"{k:>16}: log loss model {r['logloss_model']:.5f} vs constant {r['logloss_constant']:.5f} ({'better' if r['logloss_model'] < r['logloss_constant'] else 'NOT better'})  mean {r['mean_pred']:.3f} actual {r['actual']:.3f}  top-quintile pred {r['top_quintile_pred']:.3f} actual {r['top_quintile_actual']:.3f}  bottom {r['bottom_quintile_pred']:.3f} / {r['bottom_quintile_actual']:.3f}")
    fg = s.get("full_game", {})
    if fg:
        print(f"\nFull game: mean expected regulation goals {fg['mean_expected_regulation_goals']:.3f} vs actual {fg['mean_actual_regulation_goals']:.3f}")
    print("\nBreak-even hit rate by price:", ", ".join(f"{k} -> {v:.3f}" for k, v in s["break_even"].items()))
