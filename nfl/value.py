"""Best bets: a fair probability and the expected value for every bet DraftKings lists, ranked best to worst.

Why the market comes first
--------------------------
The walk-forward test (nfl/backtest.py) shows the simulation does not beat the closing moneyline, spread or
total. Its player markets were only ever tested against each player's own recent average, never against a
sportsbook line, which is a much easier bar. In Week 6 of 2026 it pulled every quarterback's volume toward the
league average and toward 2024-25 (Bryce Young projected at 205 yards while averaging 317, Stafford 265 vs 314,
Prescott 235 vs 276), so every high-volume passer came out as an under. The old page then priced those
probabilities against DraftKings and reported the size of the model's error as "expected value".

A bet is only good if it beats its price, so the probability it is judged on has to be at least as sharp as
the book. Here that is the market itself (every book's price with the margin removed), and the model is only
allowed to nudge it.

Method
------
1. Market probability at DraftKings' line. Every book's two-way price is de-vigged (proportional method).
   Books post different lines (Prescott 273.5 to 280.5 this week), so each book is moved onto DraftKings' line:
   the model's distribution for that stat supplies the shape (how spread out it is, where the pushes fall) and
   is shifted until it reproduces that book's no-vig price at that book's line. The consensus is the weighted
   median shift across books (Pinnacle, the sharpest book in the feed, counts double; DraftKings counts like
   any other book, which keeps the estimate conservative).
2. Model probability at DraftKings' line (the simulation, unshifted).
3. Fair probability = market + nudge, nudge = MODEL_WEIGHT x (model - market), capped at +/- NUDGE_CAP and
   faded to nothing when model and market disagree by more than FADE_HI: a large disagreement with several
   books is far more often something the model cannot see (a new play-caller, a quarterback change, an injury)
   than a market mistake. Game lines get no nudge (the backtest shows the model does not beat them).
4. Expected value at DraftKings' price: fair x (odds - 1) - (1 - fair - push).
5. A bet is listed as good at EV >= GOOD_EV with at least MIN_BOOKS books in the consensus. Anytime-touchdown
   prices are one-sided (books post only "Yes"), so their margin is assumed (ATD_MARGIN, labelled on the page)
   and they need GOOD_EV_ATD.

Every number is stored with its inputs (each book's line and price, the shift, the model's figure) so the page
can show the arithmetic.
"""
from __future__ import annotations

import math
import statistics

import numpy as np

BOOK = "DraftKings"
BOOK_WEIGHT = {"Pinnacle": 2.0}      # every other book 1.0
MIN_BOOKS = 3                        # books (DraftKings included) quoting the market for a bet to count as good
GOOD_EV = 0.02                       # +2% at DraftKings' price
GOOD_EV_ATD = 0.05                   # anytime TD: the margin is assumed, so ask for more
ATD_MARGIN = 0.07                    # share of a one-sided "Yes" price that is margin (assumed, not measured)
ATD_MAX_ODDS = 8.0                   # anytime TD longer than +700 is never listed as good: long-shot margins are unknown and large
NUDGE_CAP = 0.04                     # the model can move the market's probability by at most 4 points
FADE_LO, FADE_HI = 0.10, 0.20        # model weight falls linearly from full at 10 points of disagreement to 0 at 20
DISAGREE = 0.25                      # books more than 25 points apart at DraftKings' line: something is wrong with the market data
KEEP_INPUTS = 80                     # bets below the good ones that keep their full inputs on the page (size)
MODEL_WEIGHT = {"ml": 0.0, "spread": 0.0, "total": 0.0, "h1": 0.0, "h2": 0.0,
                "qb_yds": 0.3, "qb_td": 0.3, "rec_yds": 0.3, "rush_yds": 0.3, "recs": 0.3, "atd": 0.3}
LABEL = {"ml": "Moneyline", "spread": "Spread", "total": "Game total", "h1": "1st half total", "h2": "2nd half total",
         "qb_yds": "Passing yards", "qb_td": "Passing TDs", "rec_yds": "Receiving yards", "rush_yds": "Rushing yards",
         "recs": "Receptions", "atd": "Anytime TD"}
UNIT = {"qb_yds": "pass yds", "qb_td": "pass TDs", "rec_yds": "rec yds", "rush_yds": "rush yds", "recs": "receptions"}


# ------------------------------------------------------------------------------------------- distributions
class Dist:
    """A stat's distribution from the simulation, priced at any line and shifted by any amount.

    step 1: integer stats (points, touchdowns, receptions) with pushes on whole-number lines; a fractional shift
    mixes the two neighbouring whole shifts. step > 1: yardage stored in bins, read as uniform within each bin."""

    def __init__(self, off: float, vals: list[float], step: float = 1.0):
        p = np.asarray(vals, dtype=float)
        s = p.sum()
        self.p = p / s if s > 0 else p
        self.step = float(step)
        self.v = (np.arange(len(p)) + off) * self.step
        self.lo, self.hi = float(self.v[0]) if len(p) else 0.0, float(self.v[-1]) if len(p) else 0.0

    def _at(self, line: float) -> tuple[float, float, float]:
        if self.step == 1.0:
            o = float(self.p[self.v > line + 1e-9].sum()); pu = float(self.p[np.abs(self.v - line) <= 1e-9].sum())
            return o, pu, max(0.0, 1.0 - o - pu)
        h = self.step / 2
        frac = np.clip((self.v + h - line) / self.step, 0.0, 1.0)
        o = float((self.p * frac).sum())
        return o, 0.0, 1.0 - o

    def at(self, line: float, shift: float = 0.0) -> tuple[float, float, float]:
        """(over, push, under) for the stat plus `shift` at `line`."""
        if self.step != 1.0:
            return self._at(line - shift)
        k0 = math.floor(shift); f = shift - k0
        a = self._at(line - k0)
        if f < 1e-9:
            return a
        b = self._at(line - k0 - 1)
        return tuple((1 - f) * x + f * y for x, y in zip(a, b))  # type: ignore[return-value]

    def two_way(self, line: float, shift: float = 0.0) -> float:
        o, _, u = self.at(line, shift)
        return o / (o + u) if (o + u) > 0 else 0.5

    def solve_shift(self, line: float, q_over: float) -> float:
        """The shift at which the over has two-way probability q_over at `line` (bisection; monotone in the shift)."""
        span = (self.hi - self.lo) + 4 * self.step + 50
        lo, hi = -span, span
        q_over = min(max(q_over, 1e-4), 1 - 1e-4)
        for _ in range(60):
            mid = (lo + hi) / 2
            if self.two_way(line, mid) < q_over:
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2

    def median(self, shift: float = 0.0) -> float:
        c = np.cumsum(self.p)
        i = int(np.searchsorted(c, 0.5))
        return float(self.v[min(i, len(self.v) - 1)] + shift)


def normal_dist(mean: float, sd: float, step: float = 1.0) -> Dist:
    """Fallback shape for a player the simulation does not list (only its spread matters: it converts lines)."""
    v = np.arange(max(0.0, mean - 5 * sd), mean + 5 * sd + step, step)
    p = np.exp(-0.5 * ((v - mean) / max(sd, 1e-6)) ** 2)
    return Dist(v[0] / step, list(p), step)


# ------------------------------------------------------------------------------------------- prices
def devig(a: float | None, b: float | None) -> float | None:
    """No-vig probability of side a from two decimal prices."""
    if not a or not b or a <= 1 or b <= 1:
        return None
    ia, ib = 1 / a, 1 / b
    return ia / (ia + ib)


def wmedian(xs: list[float], ws: list[float]) -> float:
    """Weighted median; when the cumulative weight lands exactly on half, the midpoint of the two middle values
    (so an even number of equally weighted books gives the ordinary median, not the lower one)."""
    o = sorted(zip(xs, ws)); tot = sum(w for _, w in o); c = 0.0
    for i, (x, w) in enumerate(o):
        c += w
        if abs(c - tot / 2) < 1e-9 and i + 1 < len(o):
            return (x + o[i + 1][0]) / 2
        if c > tot / 2:
            return x
    return o[-1][0]


def _logit(p: float) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return math.log(p / (1 - p))


def _nudge(kind: str, market: float, model: float | None) -> tuple[float, float, str]:
    """(fair, applied nudge in probability points, note). Worked on the log-odds scale so a 3% long shot cannot be
    doubled by a nudge sized for a coin flip: NUDGE_CAP and the fade band are expressed at 50% and scaled."""
    w = MODEL_WEIGHT.get(kind, 0.0)
    if model is None or w == 0:
        return market, 0.0, "market only" if model is None else "game line: market price (the model does not beat it)"
    d = _logit(model) - _logit(market)
    ad = abs(d)
    cap, lo, hi = 4 * NUDGE_CAP, 4 * FADE_LO, 4 * FADE_HI          # slope of the logit at 50% is 4
    if ad >= hi:
        return market, 0.0, f"model {model*100:.0f}% vs market {market*100:.0f}%: too far apart, market trusted"
    fade = 1.0 if ad <= lo else (hi - ad) / (hi - lo)
    n = max(-cap, min(cap, w * fade * d))
    fair = 1 / (1 + math.exp(-(_logit(market) + n)))
    return fair, fair - market, f"model {model*100:.0f}% nudges the market {(fair - market)*100:+.1f} pts"


def _ev(p: float, push: float, odds: float) -> float:
    return p * (odds - 1) - (1 - p - push)


# ------------------------------------------------------------------------------------------- per market
def _two_way_market(kind: str, dist: Dist | None, books: dict, s1: str, s2: str, line_of, *, model_dist: Dist | None = None,
                    flip_line: bool = False) -> dict | None:
    """Consensus for an over/under style market at DraftKings' line.

    books    {title: {"line": L, s1: dec, s2: dec}}; line_of(book) gives the line in the stat's own terms
    dist     shape used to move books onto DraftKings' line (the model's, or a fallback)
    Returns a dict with the market's (over, push, under) at DK's line and the inputs, or None when DK does not quote it."""
    dk = books.get(BOOK)
    if not dk or dk.get(s1) is None or dk.get(s2) is None:
        return None
    L = line_of(dk)
    if L is None:
        return None
    shifts, ws, used = [], [], []
    for title, b in books.items():
        q = devig(b.get(s1), b.get(s2))
        lb = line_of(b)
        if q is None or lb is None:
            continue
        if dist is None:
            if lb != L:
                continue
            shifts.append(q); ws.append(BOOK_WEIGHT.get(title, 1.0))
        else:
            shifts.append(dist.solve_shift(lb, q)); ws.append(BOOK_WEIGHT.get(title, 1.0))
        used.append({"book": title, "line": b.get("line"), s1: b.get(s1), s2: b.get(s2), "nv": round(q, 4)})
    if not shifts:
        return None
    if dist is None:
        q = wmedian(shifts, ws)
        o, pu, u = q, 0.0, 1 - q
        shift = None
        at_dk = list(shifts)
    else:
        shift = wmedian(shifts, ws)
        o, pu, u = dist.at(L, shift)
        at_dk = [dist.two_way(L, sh) for sh in shifts]          # every book's view moved onto DraftKings' line
    res = {"line": dk.get("line"), "L": L, "dk": {s1: dk[s1], s2: dk[s2]}, "market": tuple(round(x, 5) for x in (o, pu, u)),
           "shift": None if shift is None else round(shift, 3), "books": used,
           "n": len(used), "lines": sorted({b["line"] for b in used if b["line"] is not None}),
           "spread_pts": round(max(at_dk) - min(at_dk), 4)}
    if model_dist is not None:
        res["model"] = tuple(round(x, 5) for x in model_dist.at(L, 0.0))
        if shift is not None:
            res["market_median"] = round(model_dist.median(shift), 1)
            res["model_median"] = round(model_dist.median(0.0), 1)
    return res


def _sel(g: dict, kind: str, side: str, label: str, line, odds: float, market: tuple[float, float, float], model: tuple[float, float, float] | None,
         info: dict, who: str | None = None, team: str | None = None, flags: list[str] | None = None, one_sided: bool = False) -> dict:
    o, pu, u = market
    p_mkt = o / (1 - pu) if (1 - pu) > 0 else o          # win chance among bets that are not pushed
    p_mod = None
    if model is not None:
        mo, mpu, mu = model
        p_mod = mo / (1 - mpu) if (1 - mpu) > 0 else mo
    fair2, nudge, note = _nudge(kind, p_mkt, p_mod)
    fair = fair2 * (1 - pu)                               # back to an unconditional win probability
    ev = _ev(fair, pu, odds)
    need = GOOD_EV_ATD if one_sided else GOOD_EV
    n = info.get("n", 0)
    excluded = None
    if one_sided and odds > ATD_MAX_ODDS:
        excluded = "long shot"
        flags = list(flags or []) + [f"long shot (longer than +{round((ATD_MAX_ODDS - 1) * 100)}): the books' margin on these is unknown and large, so it is never listed as good"]
    elif info.get("spread_pts", 0) > DISAGREE:
        excluded = "books disagree"
        flags = list(flags or []) + [f"the books' prices differ by {info['spread_pts']*100:.0f} points at this line: a stale line, a role change or two players with the same name; never listed as good"]
    elif n < MIN_BOOKS:
        excluded = "thin market"
        flags = list(flags or []) + [f"only {n} book{'s' if n != 1 else ''} quote this: too thin to trust the consensus"]
    good = ev >= need and excluded is None
    conf = "high" if (n >= 5 and not one_sided and not (flags or [])) else ("medium" if n >= MIN_BOOKS else "low")
    return {"id": sel_id(kind, g["game_id"], side, line, who or team or ""),
            "game_id": g["game_id"], "mu": f'{g["away"]} @ {g["home"]}', "kick": g.get("kickoff_utc") or "", "kind": kind,
            "market": LABEL[kind], "side": side, "line": line, "who": who, "team": team, "label": label, "odds": round(odds, 3),
            "p": round(fair, 4), "push": round(pu, 4), "p_market": round(p_mkt * (1 - pu), 4),
            "p_model": None if p_mod is None else round(p_mod * (1 - pu), 4), "nudge": round(nudge, 4), "note": note,
            "fair_odds": round((1 - pu) / fair, 3) if fair > 0 else None, "breakeven": round((1 - pu) / odds, 4),
            "ev": round(ev, 4), "good": bool(good), "excluded": excluded, "need": need, "books": n, "confidence": conf, "flags": flags or [],
            "one_sided": one_sided, "inputs": info}


def fmt_line(line) -> str:
    """A line as the page's JavaScript prints it (String(53) is "53", String(-1.5) is "-1.5")."""
    if line is None:
        return ""
    if float(line) == 0:
        return "0"
    return format(float(line), "g")


def sel_id(kind: str, game_id: str, side: str, line, who: str) -> str:
    return "|".join((kind, game_id, side, fmt_line(line), who or ""))


def _book_rows(x: dict | None) -> dict:
    return (x or {}).get("books") or {}


def game_bets(g: dict) -> list[dict]:
    """Every bet DraftKings quotes for one game, both sides, with fair probability and EV."""
    from .live import full_key, name_key

    out: list[dict] = []
    O = g.get("odds") or {}
    if not O:
        return out
    mk = g.get("markets") or {}
    dist = mk.get("dist") or {}
    H, A = g["home"], g["away"]
    qflags = {s: [] for s in ("home", "away")}
    for s in ("home", "away"):
        q = (g.get("qb") or {}).get(s) or {}
        if q.get("change"):
            qflags[s].append(f"{g[s]} quarterback change")
        if q.get("status"):
            qflags[s].append(f"{q.get('name')} {q.get('status')}")

    # moneyline: two-way, no line; a tie voids the bet
    mlb = _book_rows(O.get("ml"))
    dk = mlb.get(BOOK)
    if dk and dk.get("home") and dk.get("away"):
        qs, ws, used = [], [], []
        for title, b in mlb.items():
            q = devig(b.get("home"), b.get("away"))
            if q is not None:
                qs.append(q); ws.append(BOOK_WEIGHT.get(title, 1.0)); used.append({"book": title, "home": b.get("home"), "away": b.get("away"), "nv": round(q, 4)})
        if qs:
            tie = float((mk.get("ml") or {}).get("tie") or 0.0)
            qh = wmedian(qs, ws)
            info = {"books": used, "n": len(used), "dk": {"home": dk["home"], "away": dk["away"]}}
            for side, q in (("home", qh), ("away", 1 - qh)):
                m = mk.get("ml") or {}
                model = None
                if m.get(side) is not None:
                    model = (m[side], tie, 1 - m[side] - tie)
                out.append(_sel(g, "ml", side, f"{g[side]} moneyline", None, dk[side], (q * (1 - tie), tie, (1 - q) * (1 - tie)), model, info, team=g[side]))

    # spread (stat: home margin; the home side wins when margin > -home_line)
    if dist.get("margin"):
        D = Dist(dist["margin"][0], dist["margin"][1])
        r = _two_way_market("spread", D, _book_rows(O.get("spread")), "home", "away", lambda b: None if b.get("line") is None else -b["line"], model_dist=D)
        if r:
            hl = r["line"]
            o, pu, u = r["market"]; mo = r.get("model")
            out.append(_sel(g, "spread", "home", f"{H} {hl:+g}", hl, r["dk"]["home"], (o, pu, u), mo, r, team=H))
            out.append(_sel(g, "spread", "away", f"{A} {-hl:+g}", -hl, r["dk"]["away"], (u, pu, o), None if mo is None else (mo[2], mo[1], mo[0]), r, team=A))

    # totals: game, first half, second half
    for kind, key, rows in (("total", "total", _book_rows(O.get("total"))), ("h1", "h1", _book_rows((O.get("props") or {}).get("h1"))),
                            ("h2", "h2", _book_rows((O.get("props") or {}).get("h2")))):
        if not dist.get(key) or not rows:
            continue
        D = Dist(dist[key][0], dist[key][1])
        r = _two_way_market(kind, D, rows, "over", "under", lambda b: b.get("line"), model_dist=D)
        if r:
            pre = {"total": "", "h1": "1H ", "h2": "2H "}[kind]
            o, pu, u = r["market"]; mo = r.get("model")
            out.append(_sel(g, kind, "over", f"{pre}Over {r['line']:g}", r["line"], r["dk"]["over"], (o, pu, u), mo, r))
            out.append(_sel(g, kind, "under", f"{pre}Under {r['line']:g}", r["line"], r["dk"]["under"], (u, pu, o), None if mo is None else (mo[2], mo[1], mo[0]), r))

    # player markets
    P = O.get("props") or {}
    model_d: dict = {}               # (kind, full name key) -> (Dist, side, display name, flags)
    for s in ("home", "away"):
        q = (g.get("qb") or {}).get(s) or {}
        qm = (mk.get("qb") or {}).get(s) or {}
        if q.get("name") and qm:
            nk = full_key(q["name"])
            if qm.get("yds_pmf5"):
                model_d[("qb_yds", nk)] = (Dist(qm["yds_pmf5"][0], qm["yds_pmf5"][1], 5.0), s, q["name"], list(qflags[s]))
            if qm.get("td_pmf"):
                model_d[("qb_td", nk)] = (Dist(0, qm["td_pmf"], 1.0), s, q["name"], list(qflags[s]))
        for x in (g.get("props") or {}).get(s, []):
            fl = list(qflags[s]) + ([f"{x['name']} questionable"] if x.get("q") else [])
            for kind in ("rec_yds", "rush_yds", "recs"):
                d = x.get(kind)
                if d and d.get("pmf"):
                    model_d[(kind, full_key(x["name"]))] = (Dist(d["pmf"][0], d["pmf"][1], float(d.get("step", 1.0))), s, x["name"], fl)

    def match(table: dict, kind: str, row: dict, key: str):
        """The model's entry for an odds row: by full name, else by short name only when exactly one model
        player has it (two players sharing 'b.robinson' must never borrow each other's numbers)."""
        fk = full_key(row.get("name") or "")
        hit = table.get((kind, fk))
        if hit is not None:
            return hit
        nk = name_key(row.get("name") or key)
        cands = [v for (k2, _), v in table.items() if k2 == kind and name_key(v[2]) == nk]
        if len(cands) != 1:
            return None
        a, b = fk.split(" ")[0] if fk else "", full_key(cands[0][2]).split(" ")[0]
        return None if (len(a) > 2 and len(b) > 2 and a != b) else cands[0]
    for kind in ("qb_yds", "qb_td", "rec_yds", "rush_yds", "recs"):
        for nk, x in (P.get(kind) or {}).items():
            rows = _book_rows(x)
            if BOOK not in rows:
                continue
            md = match(model_d, kind, x, nk)
            if md:
                D, s, name, fl = md
            else:
                # a player the simulation does not list: market only; a generic shape moves books onto DK's line
                dkl = rows[BOOK].get("line")
                if dkl is None:
                    continue
                sd = {"qb_yds": 65.0, "rec_yds": max(12.0, 0.85 * math.sqrt(dkl) * 4), "rush_yds": max(12.0, 0.8 * math.sqrt(dkl) * 4)}.get(kind)
                D = normal_dist(dkl, sd, 5.0 if kind != "qb_td" and kind != "recs" else 1.0) if sd else None
                s, name, fl = None, x.get("name") or nk, ["not in the model's player list"]
            r = _two_way_market(kind, D, rows, "over", "under", lambda b: b.get("line"), model_dist=D if md else None)
            if not r:
                continue
            team = g[s] if s else None
            o, pu, u = r["market"]; mo = r.get("model")
            unit = UNIT[kind]
            out.append(_sel(g, kind, "over", f"{name} over {r['line']:g} {unit}", r["line"], r["dk"]["over"], (o, pu, u), mo, r, who=name, team=team, flags=fl))
            out.append(_sel(g, kind, "under", f"{name} under {r['line']:g} {unit}", r["line"], r["dk"]["under"], (u, pu, o),
                            None if mo is None else (mo[2], mo[1], mo[0]), r, who=name, team=team, flags=fl))

    # anytime touchdown: books post "Yes" only; margin assumed
    atd_model = {}
    for s in ("home", "away"):
        for a in (g.get("anytime") or {}).get(s, []):
            atd_model[("atd", full_key(a["name"]))] = (a["p"], s, a["name"], list(qflags[s]) + ([f"{a['name']} questionable"] if a.get("q") else []))
    for nk, x in (P.get("atd") or {}).items():
        rows = _book_rows(x)
        dk = rows.get(BOOK)
        if not dk or not dk.get("yes") or dk["yes"] <= 1:
            continue
        ps, ws, used = [], [], []
        for title, b in rows.items():
            y, nn = b.get("yes"), b.get("no")
            if not y or y <= 1:
                continue
            q = devig(y, nn) if nn else (1 / y) * (1 - ATD_MARGIN)
            ps.append(q); ws.append(BOOK_WEIGHT.get(title, 1.0)); used.append({"book": title, "yes": y, "no": nn, "nv": round(q, 4)})
        if not ps:
            continue
        q = wmedian(ps, ws)
        m = match(atd_model, "atd", x, nk)
        mp, s, name, fl = (m if m else (None, None, x.get("name") or nk, ["not in the model's player list"]))
        info = {"books": used, "n": len(used), "dk": {"yes": dk["yes"]}, "margin_assumed": ATD_MARGIN,
                "spread_pts": round(max(ps) - min(ps), 4) if max(ps) <= 2 * min(ps) else 1.0}
        out.append(_sel(g, "atd", "yes", f"{name} anytime TD", None, dk["yes"], (q, 0.0, 1 - q), None if mp is None else (mp, 0.0, 1 - mp), info,
                        who=name, team=g[s] if s else None, flags=fl, one_sided=True))
    return out


def _started(g: dict, now: str) -> bool:
    return bool(g.get("actual") or g.get("score")) or bool(g.get("kickoff_utc") and g["kickoff_utc"] <= now)


def best_bets(payload: dict, prev: dict | None = None) -> dict:
    """Every DraftKings bet for the games that have not kicked off, the better side of each market only: the good
    ones first (best expected value first), then everything else in the same order.

    prev: the best_bets block from the previous build of the same week. Good bets for games that have kicked off
    are carried over unchanged ("locked") so the track record grades exactly what the page showed before kickoff."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    started = {g["game_id"] for g in payload.get("games", []) if _started(g, now)}
    allb: list[dict] = []
    for g in payload.get("games", []):
        if g["game_id"] in started:
            continue
        allb.extend(game_bets(g))
    # keep the better side of each market (the other side is always worse: both carry DraftKings' margin)
    best: dict = {}
    for b in allb:
        if b["kind"] in ("ml", "spread"):
            k = (b["kind"], b["game_id"])
        elif b["kind"] == "atd":
            k = (b["kind"], b["game_id"], b["who"])
        else:
            k = (b["kind"], b["game_id"], b["who"] or "", b["line"])
        if k not in best or b["ev"] > best[k]["ev"]:
            best[k] = b
    # ordered by how far each bet clears its own bar (EV minus the EV it needs), so a one-sided anytime-TD price,
    # whose margin is assumed, has to beat a two-sided price by the extra it is asked for
    ranked = sorted(best.values(), key=lambda b: (not b["good"], b["excluded"] is not None, -(b["ev"] - b["need"]), -b["books"]))
    for i, b in enumerate(ranked, 1):
        b["rank"] = i
        if not b["good"] and i > len([x for x in ranked if x["good"]]) + KEEP_INPUTS:
            b.pop("inputs", None)                # the page shows the arithmetic for the good bets and the closest misses
    good = [b for b in ranked if b["good"]]
    locked: dict[str, dict] = {}
    for b in ((prev or {}).get("locked") or []) + [x for x in ((prev or {}).get("ranked") or []) if x.get("good")]:
        if b["game_id"] in started and b["id"] not in locked:
            locked[b["id"]] = {k: v for k, v in b.items() if k != "inputs"}
    lines_at = max(((g.get("odds") or {}).get("fetched") or "" for g in payload.get("games", []) if g["game_id"] not in started), default="") or None
    props_at = min(((g.get("odds") or {}).get("props_fetched") for g in payload.get("games", [])
                    if g["game_id"] not in started and (g.get("odds") or {}).get("props_fetched")), default=None)
    return {"book": BOOK, "generated": now, "odds_fetched": lines_at, "props_fetched_oldest": props_at, "n_priced": len(allb), "n_markets": len(ranked), "n_good": len(good),
            "rules": {"good_ev": GOOD_EV, "good_ev_atd": GOOD_EV_ATD, "min_books": MIN_BOOKS, "nudge_cap": NUDGE_CAP, "fade": [FADE_LO, FADE_HI],
                      "model_weight": MODEL_WEIGHT, "atd_margin": ATD_MARGIN, "atd_max_odds": ATD_MAX_ODDS, "book_weight": BOOK_WEIGHT},
            "ranked": ranked, "locked": sorted(locked.values(), key=lambda b: (b["kick"], -b["ev"])),
            "all": {b["id"]: {k: b[k] for k in ("p", "push", "p_market", "p_model", "ev", "odds", "books", "note", "good", "need", "excluded")} for b in allb}}


def picks_from_bets(bb: dict, payload: dict) -> dict:
    """The good bets, per market, in the shape the rest of the page, the scorecard and the notifier read
    (nflverse spread convention: a positive line means the home team is favoured)."""
    byid = {g["game_id"]: g for g in payload.get("games", [])}
    out: dict[str, list] = {}
    rows = [b for b in (bb.get("locked") or []) + (bb.get("ranked") or []) if b.get("good")]
    seen = set()
    for b in rows:
        if b["id"] in seen:
            continue
        seen.add(b["id"])
        g = byid.get(b["game_id"])
        if g is None:
            continue
        k = b["kind"]
        side_team = None
        if b.get("team"):
            side_team = "home" if g["home"] == b["team"] else "away"
        x = {"game_id": b["game_id"], "mu": b["mu"], "market": k, "side": b["side"], "p": b["p"], "odds": b["odds"], "ev": b["ev"], "score": b["ev"],
             "book": BOOK, "p_market": b.get("p_market"), "p_model": b.get("p_model"), "label": b["label"], "rank": b.get("rank")}
        if k == "ml":
            x.update(team=b["team"])
        elif k == "spread":
            hl = b["line"] if b["side"] == "home" else -b["line"]       # DraftKings' home line (negative: home favoured)
            x.update(line=-hl, team=b["team"])
        elif k in ("total", "h1", "h2"):
            x.update(line=b["line"])
        elif k in ("qb_yds", "qb_td"):
            x.update(line=b["line"], qb=b["who"], team=b.get("team"), side_team=side_team,
                     median=(b.get("inputs") or {}).get("market_median"))
        elif k in ("rec_yds", "rush_yds", "recs"):
            pid = None
            from .live import name_key
            for s in ("home", "away"):
                for p in (g.get("props") or {}).get(s, []):
                    if name_key(p["name"]) == name_key(b["who"] or ""):
                        pid = p["id"]
            x.update(line=b["line"], player=b["who"], id=pid, team=b.get("team"), side_team=side_team,
                     median=(b.get("inputs") or {}).get("market_median"))
        elif k == "atd":
            pid = None
            from .live import name_key
            for s in ("home", "away"):
                for a in (g.get("anytime") or {}).get(s, []):
                    if name_key(a["name"]) == name_key(b["who"] or ""):
                        pid = a["id"]
            x.update(player=b["who"], id=pid, team=b.get("team"), fair=b.get("fair_odds"))
        out.setdefault(k, []).append(x)
    for k in out:
        out[k].sort(key=lambda x: -x["ev"])
    return out


__all__ = ["Dist", "best_bets", "picks_from_bets", "game_bets", "devig", "sel_id", "BOOK", "GOOD_EV", "MIN_BOOKS"]
