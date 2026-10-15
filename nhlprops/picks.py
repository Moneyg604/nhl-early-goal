"""Server-side shortlist of props for the Telegram message: the same rule as the page's S / A grades
(validated market, an established skater, positive EV at the book's own line and price)."""
from __future__ import annotations

from .model import over_under

LABEL = {"sog": "shots", "pts": "points", "ast": "assists", "blk": "blocks", "goal": "anytime goal", "team_total": "team total"}
VKEY = {"sog": "sog", "pts": "pts", "ast": "ast", "goal": "goal", "blk": "blk", "team_total": "team_total"}


def _validated(payload: dict) -> set:
    V = (payload.get("validation") or {}).get("pooled") or {}
    return {k for k, vk in VKEY.items() if (V.get(vk) or {}).get("verdict") == "beats baseline"}


def best_bets(payload: dict, book: str = "DraftKings", min_ev: float = 0.05, limit: int = 6) -> list[dict]:
    ok = _validated(payload)
    out = []
    for g in payload.get("games", []):
        mu = f"{g['away']} @ {g['home']}"
        for side in ("away", "home"):
            S = g["sides"][side]
            tt = (S.get("book_team_total") or {}).get("books", {}).get(book)
            if tt and "team_total" in ok and tt.get("line") is not None:
                for sd in ("over", "under"):
                    o, pu, u = over_under(S["markets"]["team_total"], tt["line"])
                    p = (o if sd == "over" else u) / max(1e-9, 1 - pu)
                    odds = (tt.get("prices") or {}).get(sd)
                    if odds and odds > 1 and p * odds - 1 >= min_ev:
                        out.append({"text": f"{S['team']} team total {sd} {tt['line']}", "mu": mu, "p": p, "odds": odds, "ev": p * odds - 1})
            for s in S.get("skaters", []):
                if not s.get("pmf") or s.get("games", 0) < 15:
                    continue
                for k in ("sog", "pts", "ast", "blk", "goal"):
                    if k not in ok:
                        continue
                    b = ((s.get("book") or {}).get(k) or {}).get("books", {}).get(book)
                    if not b:
                        continue
                    sides = ("yes",) if k == "goal" else ("over", "under")
                    for sd in sides:
                        odds = (b.get("prices") or {}).get(sd)
                        if not odds or odds <= 1:
                            continue
                        line = 0.5 if k == "goal" else b.get("line")
                        if line is None:
                            continue
                        o, pu, u = over_under(s["pmf"][k], line)
                        p = (o if sd in ("over", "yes") else u) / max(1e-9, 1 - pu)
                        if k == "goal" and 1 / odds < 0.5 * p:
                            continue                     # long shot the market strongly disagrees with: never a top pick
                        ev = p * odds - 1
                        if ev >= min_ev and p >= 0.3:
                            txt = f"{s['name']} anytime goal" if k == "goal" else f"{s['name']} {LABEL[k]} {sd} {line}"
                            out.append({"text": txt, "mu": mu, "p": p, "odds": odds, "ev": ev})
    out.sort(key=lambda x: -x["ev"])
    return out[:limit]


__all__ = ["best_bets"]
