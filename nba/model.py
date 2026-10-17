"""The NBA model: team ratings from box scores, game projections, and player prop projections.

Teams. From every stored game, possessions = FGA − OREB + TOV + 0.44 × FTA per team; offensive rating = points per
100 possessions, defensive rating = points allowed per 100, pace = possessions per 48 minutes. A team's rating is
the exponentially weighted (half-life 15 games) average of its game ratings, each adjusted for the opponent, shrunk
toward the league with k pseudo-games; last season counts a third of this season per game.

Games. Expected pace = league pace × (pace_h / league) × (pace_a / league); expected points for a team = pace ×
(its ORtg × opponent DRtg / league ORtg) / 100; margin adds home court. Final margin ~ N(margin, 12.6), total ~
N(total, 18.5): P(cover), P(over), P(win) from those.

Players. Minutes: exponentially weighted average of games played (half-life 8), shrunk toward the season average,
trimmed when the spread says blowout. Rates per minute (points, rebounds, assists, threes) weighted the same way
and shrunk toward the player's prior-season rate (or his position's league rate). Opponent: points scale by the
opponent's DRtg vs league and by the game's expected pace vs league; rebounds and assists by pace. Mean = minutes ×
rate × adjustments; sd from the player's own game-to-game spread (at least 8 games) or a per-stat ratio of the mean.
P(over L) = Φ((mean − L) / sd) with a continuity correction for whole-number lines.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

from .config import CFG, ModelConfig

STATS = ("pts", "reb", "ast", "threes", "pra")


def _poss(t: dict) -> float:
    return t["fga"] - t["oreb"] + t["tov"] + 0.44 * t["fta"]


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


@dataclass
class TeamRating:
    team: str
    ortg: float
    drtg: float
    pace: float
    games: int
    games_cur: int
    record: str = ""
    last5: list = field(default_factory=list)


@dataclass
class League:
    ortg: float = 114.0
    pace: float = 99.0
    minutes_sd: float = 4.5


class Ratings:
    def __init__(self, games: list[dict], season: int, cfg: ModelConfig = CFG, through: str | None = None):
        self.cfg = cfg
        self.season = season
        self.league = League()
        self.teams: dict[str, TeamRating] = {}
        self.players: dict[str, dict] = {}            # player id -> profile
        self.player_team: dict[str, str] = {}
        self.names: dict[str, str] = {}
        rows = [g for g in games if g.get("completed") and g.get("team") and (through is None or (g.get("date") or "") < through)]
        rows.sort(key=lambda g: g.get("date") or "")
        self._fit(rows)

    # ------------------------------------------------------------------ teams
    def _fit(self, games: list[dict]) -> None:
        cfg = self.cfg
        raw = []                                   # (date, team, opp, ortg, drtg, pace, season, home, margin)
        for g in games:
            th, ta = g["team"].get(g["home"]), g["team"].get(g["away"])
            if not th or not ta or g.get("hs") is None or g.get("as") is None:
                continue
            ph, pa = _poss(th), _poss(ta)
            poss = (ph + pa) / 2
            if poss < 60:
                continue
            mins = 48.0 + 5.0 * max(0, len(g["q"]["home"]) - 4) if g.get("q") else 48.0
            pace = poss * 48 / mins
            raw.append((g["date"], g["home"], g["away"], 100 * g["hs"] / poss, 100 * g["as"] / poss, pace, g.get("season"), True, g["hs"] - g["as"], g["hs"], g["as"]))
            raw.append((g["date"], g["away"], g["home"], 100 * g["as"] / poss, 100 * g["hs"] / poss, pace, g.get("season"), False, g["as"] - g["hs"], g["as"], g["hs"]))
        if not raw:
            return
        cur = [r for r in raw if r[6] == self.season] or raw
        self.league.ortg = sum(r[3] for r in cur) / len(cur) if len(cur) >= 60 else sum(r[3] for r in raw) / len(raw)
        self.league.pace = sum(r[5] for r in cur) / len(cur) if len(cur) >= 60 else sum(r[5] for r in raw) / len(raw)
        by_team: dict[str, list] = defaultdict(list)
        for r in raw:
            by_team[r[1]].append(r)
        # first pass: unadjusted ratings; second pass: adjust each game for the opponent's unadjusted strength
        def weights(rows):
            n = len(rows); out = []
            cur_rows = sum(1 for r in rows if r[6] == self.season)
            idx = 0
            for i, r in enumerate(rows):
                if r[6] == self.season:
                    back = cur_rows - 1 - idx; idx += 1
                    out.append(0.5 ** (back / cfg.half_life_games))
                else:
                    out.append(cfg.prior_season_weight * 0.5 ** (cur_rows / cfg.half_life_games))
            return out
        unadj = {}
        for t, rows in by_team.items():
            w = weights(rows); W = sum(w) or 1
            o = sum(wi * r[3] for wi, r in zip(w, rows)) / W; d = sum(wi * r[4] for wi, r in zip(w, rows)) / W
            unadj[t] = (o, d)
        L = self.league.ortg
        for t, rows in by_team.items():
            w = weights(rows); W = sum(w) or 1
            o = sum(wi * (r[3] * L / unadj.get(r[2], (L, L))[1]) for wi, r in zip(w, rows)) / W
            d = sum(wi * (r[4] * L / unadj.get(r[2], (L, L))[0]) for wi, r in zip(w, rows)) / W
            p = sum(wi * r[5] for wi, r in zip(w, rows)) / W
            k = cfg.k_team_games
            o = (o * W + L * k) / (W + k); d = (d * W + L * k) / (W + k); p = (p * W + self.league.pace * k) / (W + k)
            cur_rows = [r for r in rows if r[6] == self.season]
            wins = sum(1 for r in cur_rows if r[8] > 0)
            self.teams[t] = TeamRating(t, o, d, p, len(rows), len(cur_rows), f"{wins}-{len(cur_rows) - wins}",
                                       [{"date": r[0], "opp": r[2], "home": r[7], "pts": r[9], "opp_pts": r[10]} for r in cur_rows[-5:]])
        self._fit_players(games)

    # ------------------------------------------------------------------ players
    def _fit_players(self, games: list[dict]) -> None:
        cfg = self.cfg
        logs: dict[str, list] = defaultdict(list)
        for g in games:
            for team, rows in (g.get("players") or {}).items():
                for p in rows:
                    if not p.get("id") or p.get("dnp"):
                        continue
                    logs[p["id"]].append({"date": g["date"], "season": g.get("season"), "team": team, "opp": g["away"] if team == g["home"] else g["home"],
                                          "home": team == g["home"], "min": p["min"], "pts": p["pts"], "reb": p["reb"], "ast": p["ast"], "threes": p["tpm"],
                                          "pra": p["pts"] + p["reb"] + p["ast"], "starter": p.get("starter", False), "pos": p.get("pos") or ""})
                    self.names[p["id"]] = p["name"]
        # positional league rates per minute (prior for thin samples)
        pos_rate: dict[str, dict] = defaultdict(lambda: defaultdict(float)); pos_min: dict[str, float] = defaultdict(float)
        for pid, rows in logs.items():
            for r in rows:
                if r["season"] != self.season and len(rows) > 1:
                    pass
                pos = (r["pos"] or "F")[0]
                pos_min[pos] += r["min"]
                for s in STATS:
                    pos_rate[pos][s] += r[s]
        self.pos_rate = {pos: {s: (pos_rate[pos][s] / pos_min[pos] if pos_min[pos] else 0.0) for s in STATS} for pos in pos_rate}
        for pid, rows in logs.items():
            rows.sort(key=lambda r: r["date"])
            cur = [r for r in rows if r["season"] == self.season]
            prior = [r for r in rows if r["season"] != self.season]
            team = rows[-1]["team"]
            self.player_team[pid] = team
            # minutes: weighted recent games this season, shrunk to this season's average; prior season as fallback
            def wavg(rs, key, hl):
                if not rs:
                    return None, 0.0
                ws = [0.5 ** ((len(rs) - 1 - i) / hl) for i in range(len(rs))]
                return sum(w * r[key] for w, r in zip(ws, rs)) / sum(ws), sum(ws)
            m_rec, w_rec = wavg(cur, "min", cfg.player_half_life)
            m_avg = sum(r["min"] for r in cur) / len(cur) if cur else None
            m_prior = sum(r["min"] for r in prior[-30:]) / len(prior[-30:]) if prior else None
            if m_rec is not None:
                base = m_avg if m_avg is not None else m_rec
                minutes = (m_rec * w_rec + base * cfg.k_player_minutes) / (w_rec + cfg.k_player_minutes)
                if m_prior is not None and len(cur) < 5:
                    minutes = (minutes * len(cur) + m_prior * (5 - len(cur)) * 0.6) / (len(cur) + (5 - len(cur)) * 0.6)
            else:
                minutes = m_prior
            rates = {}
            sds = {}
            pos = (rows[-1]["pos"] or "F")[0]
            for s in STATS:
                tot_cur = sum(r[s] for r in cur); min_cur = sum(r["min"] for r in cur)
                tot_pri = sum(r[s] for r in prior); min_pri = sum(r["min"] for r in prior)
                prior_rate = (tot_pri / min_pri) if min_pri >= 200 else self.pos_rate.get(pos, {}).get(s, 0.0)
                # recency-weighted per-minute rate this season
                if cur and min_cur > 0:
                    ws = [0.5 ** ((len(cur) - 1 - i) / cfg.player_half_life) for i in range(len(cur))]
                    rate_rec = sum(w * r[s] for w, r in zip(ws, cur)) / max(1e-9, sum(w * r["min"] for w, r in zip(ws, cur)))
                    n_eff = sum(ws)
                else:
                    rate_rec, n_eff = prior_rate, 0.0
                rate = (rate_rec * n_eff + prior_rate * cfg.k_player_rate) / (n_eff + cfg.k_player_rate)
                rates[s] = rate
                sample = (cur + prior[-20:])[-25:]
                if len(sample) >= 8:
                    mu = sum(r[s] for r in sample) / len(sample)
                    var = sum((r[s] - mu) ** 2 for r in sample) / (len(sample) - 1)
                    sds[s] = math.sqrt(max(var, 0.25))
                else:
                    sds[s] = None
            self.players[pid] = {"id": pid, "name": self.names.get(pid), "team": team, "pos": rows[-1]["pos"], "games_cur": len(cur), "games_prior": len(prior),
                                 "minutes": minutes, "min_avg": m_avg, "rates": rates, "sd": sds, "starter_rate": (sum(1 for r in cur if r["starter"]) / len(cur)) if cur else None,
                                 "last": [{k: r[k] for k in ("date", "opp", "min", "pts", "reb", "ast", "threes", "pra", "starter")} for r in cur[-10:]],
                                 "season_avg": {s: (sum(r[s] for r in cur) / len(cur) if cur else None) for s in STATS},
                                 "prior_avg": {s: (sum(r[s] for r in prior) / len(prior) if prior else None) for s in STATS}}

    # ------------------------------------------------------------------ games
    def project_game(self, home: str, away: str, neutral: bool = False) -> dict:
        cfg = self.cfg; L = self.league
        th = self.teams.get(home) or TeamRating(home, L.ortg, L.ortg, L.pace, 0, 0)
        ta = self.teams.get(away) or TeamRating(away, L.ortg, L.ortg, L.pace, 0, 0)
        pace = L.pace * (th.pace / L.pace) * (ta.pace / L.pace)
        hp = pace * (th.ortg * ta.drtg / L.ortg) / 100 + (0 if neutral else cfg.home_court / 2)
        ap = pace * (ta.ortg * th.drtg / L.ortg) / 100 - (0 if neutral else cfg.home_court / 2)
        margin = hp - ap; total = hp + ap
        return {"home_pts": round(hp, 1), "away_pts": round(ap, 1), "margin": round(margin, 1), "total": round(total, 1), "pace": round(pace, 1),
                "home_win": round(_phi(margin / cfg.margin_sd), 4), "ratings": {"home": {"ortg": round(th.ortg, 1), "drtg": round(th.drtg, 1), "pace": round(th.pace, 1), "games": th.games_cur, "record": th.record},
                                                                               "away": {"ortg": round(ta.ortg, 1), "drtg": round(ta.drtg, 1), "pace": round(ta.pace, 1), "games": ta.games_cur, "record": ta.record}}}

    def p_cover(self, margin: float, home_line: float) -> float:
        """P(home margin + home_line > 0), home_line = the home team's points (negative when favoured)."""
        return _phi((margin + home_line) / self.cfg.margin_sd)

    def p_over(self, total: float, line: float) -> float:
        return 1 - _phi((line - total) / self.cfg.total_sd)

    # ------------------------------------------------------------------ props
    def project_player(self, pid: str, opp: str, pace: float, spread_abs: float, out_ids: set | None = None) -> dict | None:
        cfg = self.cfg; L = self.league
        p = self.players.get(pid)
        if not p or p.get("minutes") is None:
            return None
        enough = p["games_cur"] >= cfg.min_games_listed or (p["games_cur"] == 0 and p["games_prior"] >= 8) or p["games_cur"] >= 1 and p["games_prior"] >= 8
        if not enough:
            return None
        minutes = p["minutes"]
        if spread_abs >= 10 and (p.get("starter_rate") or 0) >= 0.5:
            minutes *= cfg.blowout_minutes
        if minutes < cfg.min_minutes_listed:
            return None
        to = self.teams.get(opp)
        d_adj = (to.drtg / L.ortg) if to else 1.0           # points allowed vs league
        pace_adj = pace / L.pace
        out = {"id": pid, "name": p["name"], "team": p["team"], "pos": p["pos"], "minutes": round(minutes, 1), "games": p["games_cur"], "stats": {}}
        for s in STATS:
            adj = pace_adj * (d_adj if s in ("pts", "pra") else 1.0) * (1.0 if s != "threes" else min(1.15, max(0.85, d_adj)))
            mean = minutes * p["rates"][s] * adj
            sd = p["sd"].get(s) or max(0.9, cfg.sd_ratio[s] * mean)
            out["stats"][s] = {"mean": round(mean, 2), "sd": round(sd, 2), "season_avg": p["season_avg"].get(s), "prior_avg": p["prior_avg"].get(s)}
        out["last"] = p["last"][-5:]
        return out

    @staticmethod
    def p_over_stat(mean: float, sd: float, line: float) -> tuple[float, float]:
        """(P(over), P(push)) for a line; whole-number lines push on the exact value (continuity-corrected)."""
        if sd <= 0:
            return (1.0 if mean > line else 0.0), 0.0
        if abs(line - round(line)) < 1e-9:
            over = 1 - _phi((line + 0.5 - mean) / sd)
            under = _phi((line - 0.5 - mean) / sd)
            return over, max(0.0, 1 - over - under)
        return 1 - _phi((line - mean) / sd), 0.0


__all__ = ["Ratings", "STATS"]
