"""Send the NFL week (or the next kickoff window) to Telegram / Discord, same channels as the NHL bot.

    python tools/notify_nfl.py --reason weekly    # the bot's picks by category, the 68%+ props, the bot's top six (Wednesdays)
    python tools/notify_nfl.py --reason t75       # the games kicking off in the next two hours, with inactives
    python tools/notify_nfl.py --reason daily     # sends only on Wednesday mornings (weekly preview)
    python tools/notify_nfl.py --reason test --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import _h, send_discord, send_telegram  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from earlygoal.brand import site_url  # noqa: E402

SITE = site_url() + "nfl/"
VKEY = {"ml": "moneyline", "spread": "spread", "total": "total", "h1": "h1_total", "h2": "h2_total", "fg": "fg_over1.5", "qb_yds": "qb_yards",
        "qb_td": "qb_td_over1.5", "atd": "anytime_td", "rec_yds": "rec_yds", "rush_yds": "rush_yds", "recs": "recs"}
LABEL = {"ml": "Moneyline", "spread": "Spread", "total": "Total", "h1": "1st half", "h2": "2nd half", "fg": "Team FGs", "qb_yds": "QB pass yds",
         "qb_td": "QB pass TDs", "atd": "Anytime TD", "rec_yds": "Receiving yds", "rush_yds": "Rushing yds", "recs": "Receptions"}


def current_payload() -> dict | None:
    wj = ROOT / "docs" / "nfl" / "weeks.json"
    if not wj.exists():
        return None
    cur = json.loads(wj.read_text()).get("current")
    f = ROOT / "docs" / "nfl" / "weeks" / f"{cur}.json"
    return json.loads(f.read_text()) if f.exists() else None


def ko(g) -> datetime | None:
    try:
        return datetime.strptime(g["kickoff_utc"], "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def et(d: datetime) -> str:
    return d.astimezone(ZoneInfo("America/New_York")).strftime("%a %-I:%M %p ET")


def verdict_icon(p: dict, key: str) -> str:
    v = (((p.get("validation") or {}).get("pooled") or {}).get(VKEY[key]) or {}).get("verdict")
    return {"beats baseline": "✅", "marginal": "〰️", "no edge": "⚠️"}.get(v, "❔")


def pick_line(k: str, x: dict, p: dict) -> str:
    byid = {g["game_id"]: g for g in p["games"]}
    g = byid.get(x["game_id"], {})
    if k == "ml":
        return f"{x['team']} ML {x['p']*100:.0f}% (fair {1/x['p']:.2f})"
    if k == "spread":
        team = g.get("home") if x["side"] == "home" else g.get("away")
        line = -x["line"] if x["side"] == "home" else x["line"]
        return f"{team} {line:+g} (model {x['edge_pts']:+.1f} pts vs line)"
    if k in ("total", "h1", "h2"):
        return f"{x['mu']} {x['side']} {x['line']} ({x['p']*100:.0f}%)"
    if k == "fg":
        return f"{x['team']} {x['side']} 1.5 FGs ({x['p']*100:.0f}%)"
    if k == "qb_yds":
        return f"{x['qb']} {x['side']} {x['line']} yds ({x['p']*100:.0f}%, median {x['median']:.0f})"
    if k == "qb_td":
        return f"{x['qb']} {x['side']} 1.5 TD ({x['p']*100:.0f}%)"
    if k == "atd":
        return f"{x['player']} ({x['team']}) {x['p']*100:.0f}%"
    if k in ("rec_yds", "rush_yds", "recs"):
        return f"{x['player']} {x['side']} {x['line']} ({x['p']*100:.0f}%, median {x['median']:.0f})"
    return ""


def _am(d: float) -> str:
    return f"+{round((d - 1) * 100)}" if d >= 2 else f"-{round(100 / (d - 1))}"


PROP_KINDS = ("qb_yds", "qb_td", "rec_yds", "rush_yds", "recs")
PROP_MIN_P = 0.68              # a player prop makes the message at this win chance or better, with positive EV at DraftKings
CAT_ICON = {"passing": "🎯", "receiving": "🙌", "rushing": "🏃", "totals": "🔢", "moneyline": "💰", "spread": "➕", "fieldgoals": "🦵"}


def _bet_line(b: dict, B, T, with_mu: bool = True) -> str:
    """'Geno Smith under 1.5 pass TDs (NYJ @ NE)  67% @ 1.43  EV -3.9%' in the NHL message's shape."""
    mu = f" ({b['mu']})" if with_mu else ""
    odds = f" @ {b['odds']:.2f}" if b.get("odds") else " (fair " + (f"{b['fair_odds']:.2f}" if b.get("fair_odds") else "–") + ", no DK price in feed)"
    ev = f"  EV {b['ev']*100:+.1f}%" if b.get("ev") is not None else ""
    sim = f" · sim {b['p_model']*100:.0f}%" if b.get("p_model") is not None and b.get("p_market") is not None else ""
    pct = f"{b['p']*100:.0f}%"
    return f"{T(b['label'] + mu)}  {B(pct)}{T(odds + ev + sim)}"


SRC_NOTE = {"feed": "", "draftkings": " (DK checked)", "unverified": " ⚠ price not verified on DraftKings"}


def _desk_line(i, x: dict, B, T) -> str:
    """'1. Jonathan Taylor under 89.5 rush yds (TEN @ IND)  60% @ 1.89 (DK checked) · B · measured'"""
    head = f"{i}. " if isinstance(i, int) else "• "
    pct = f"{x['p']*100:.0f}%"
    return head + T(f"{x['label']} ({x['mu']})") + "  " + B(pct) + T(f" @ {x['odds']:.2f}{SRC_NOTE.get(x.get('odds_source') or '', '')} · {x['grade']} · {x.get('evidence', '')}")


def desk_lines(desk: dict, B, T, live, windowed: bool = False) -> list[str]:
    """The research desk in the spec's order: the Best picks, then each section, then the alerts. Prices are shown,
    never used to choose, when the spec's odds_rule is 'ignore'."""
    out: list[str] = []
    if not desk:
        return out
    if not desk.get("ok"):
        errs = desk.get("errors") or []
        out.append("⚠️ " + B("Research desk file rejected") + T(f": {len(errs)} problem(s), first: {errs[0] if errs else 'unknown'}. The next desk run fixes it."))
        out.append("")
        return out
    by = {x["id"]: x for x in desk.get("selections") or []}
    spec = desk.get("spec") or {}
    rule = desk.get("odds_rule") or "band"
    up = [x for x in desk.get("selections") or [] if live(x)]
    how = "picked on evidence; DraftKings price shown, never the reason" if rule == "ignore" else f"DraftKings prices {(desk.get('band') or [1.35, 2.2])[0]:.2f} to {(desk.get('band') or [1.35, 2.2])[1]:.2f}"
    out.append("⭐ " + B(f"Research desk · {len(up)} pick{'s' if len(up) != 1 else ''} to play") + T(f"  desk win chance · {how}"))
    if desk.get("summary"):
        s = str(desk["summary"]).strip()
        out.append(T(s if len(s) <= 400 else s[:397] + "…"))
    out.append("")
    best = [by[i] for i in desk.get("best") or [] if i in by and live(by[i])]
    if best:
        out.append("🏆 " + B(f"{(spec.get('best') or {}).get('label') or 'Best picks'} · {len(best)}") + T("  strongest evidence of winning"))
        for n, x in enumerate(best, 1):
            out.append(_desk_line(n, x, B, T))
        out.append("")
    shown = {x["id"] for x in best}
    for sp in spec.get("sections") or []:
        rows = [by[i] for i in (desk.get("sections") or {}).get(sp.get("key"), []) if i in by and live(by[i]) and i not in shown]
        if not rows:
            continue
        out.append("📋 " + B(sp.get("label") or sp.get("key")))
        for x in rows:
            out.append(_desk_line(None, x, B, T))
        out.append("")
    if not spec.get("sections"):
        rest = [x for x in up if x["id"] not in shown]
        for n, x in enumerate(rest[:12], 1):
            out.append(_desk_line(n, x, B, T))
        if len(rest) > 12:
            out.append(T(f"…and {len(rest) - 12} more in the app"))
        if rest:
            out.append("")
    if not up:
        out.append(T("No desk pick in these games." if windowed else "No desk pick left to play."))
        out.append("")
    wild = [x for x in desk.get("wild_cards") or [] if live(x)]
    if wild:
        wb = desk.get("wild_band") or [2.21, 4.5]
        out.append("🃏 " + B(f"Wild cards · {len(wild)}") + T(f"  longer prices {wb[0]:.2f} to {wb[1]:.2f}, smaller stakes"))
        for x in wild:
            out.append(_desk_line(None, x, B, T))
        out.append("")
    alerts = [a for a in desk.get("alerts") or [] if live(a)]
    if alerts:
        out.append("🚨 " + B("DraftKings moved against a desk pick") + T("  re-check before betting"))
        for a in alerts:
            out.append("• " + T(f"{a['label']} ({a['mu']}): {a['why']} (DraftKings, {a.get('fetched') or ''})"))
        out.append("")
    out.append(T(f"Desk run {desk.get('generated', '')}. Open a pick in the app for the inputs, the arithmetic and the risks."))
    out.append("")
    return out


def bot_lines(p: dict, B, T, game_ids: set | None = None) -> list[str]:
    """The bot's picks by category, the player props at 68%+ with positive EV, and the bot's top six."""
    bb = p.get("best_bets") or {}
    bot = p.get("bot") or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    board = {b["id"]: b for b in (bb.get("ranked") or []) + (bot.get("extra") or [])}

    def live(b):
        return bool(b) and (not b.get("kick") or b["kick"] > now) and (game_ids is None or b.get("game_id") in game_ids)

    out: list[str] = []
    # the research desk first, in the spec's order (shown even before the odds feed has a board)
    out.extend(desk_lines(bot.get("desk") or {}, B, T, live, windowed=game_ids is not None))
    if not bb:
        return out
    if not bot:
        out.append("🤖 " + B("Bot's picks") + T(": not built yet for this week (next site run)"))
        return out
    hot = bot.get("hot") or {}
    movers = [m for m in hot.get("movers") or [] if (not m.get("kick") or m["kick"] > now) and (game_ids is None or m.get("game_id") in game_ids)][:6]
    if movers:
        out.append("🔥 " + B("What's hot / what's not") + T("  DraftKings line moves since the opener"))
        for m in movers:
            out.append("• " + T(f"{m['label']} · hot {m['hot']}, cold {m['cold']}"))
        out.append("")
    cats = bot.get("cats") or {}
    out.append("🤖 " + B("Bot's picks") + T("  the site's model, separate from the desk and its spec · win chance @ DraftKings price · EV · simulation"))
    any_cat = False
    for c in (bot.get("rules") or {}).get("categories") or [{"key": k, "label": v.get("label")} for k, v in cats.items()]:
        key = c["key"]; cat = cats.get(key) or {}
        rows = [board.get(i) for i in cat.get("ids") or []]
        rows = [b for b in rows if live(b)]
        if not rows:
            continue
        any_cat = True
        out.append("")
        out.append(f"{CAT_ICON.get(key, '•')} " + B(c.get("label") or key))
        for b in rows:
            out.append("• " + _bet_line(b, B, T))
    if not any_cat:
        out.append(T("Nothing passes the bot's checks for the games still to play."))
    # player props the bot would call strong: 68%+ to win, positive EV, a real DraftKings price, nothing flagged
    props = [b for b in board.values() if live(b) and b["kind"] in PROP_KINDS and b.get("odds") and b["p"] >= PROP_MIN_P
             and (b.get("ev") or 0) > 0 and not b.get("excluded") and not any("questionable" in f or "not the listed starter" in f for f in (b.get("flags") or []))]
    props.sort(key=lambda b: (-b["p"], -(b.get("ev") or 0)))
    out.append("")
    if props:
        out.append("🎟️ " + B(f"Player props {round(PROP_MIN_P*100)}%+ with positive EV at DraftKings"))
        for b in props[:12]:
            out.append("• " + _bet_line(b, B, T))
        if len(props) > 12:
            out.append(T(f"…and {len(props) - 12} more on the page"))
    else:
        out.append("🎟️ " + B("Player props") + T(f": no DraftKings prop at {round(PROP_MIN_P*100)}%+ with positive EV right now"))
    # the bot's top six across every market (no anytime touchdowns), one per game, real DraftKings prices
    C = bot.get("combine") or {}
    legs = [l for l in (C.get("legs") or []) if live(l)]
    out.append("")
    if legs:
        band = C.get("odds_band") or [1.35, 2.2]
        out.append("🏆 " + B(f"Bot's top {len(legs)} · all markets, no anytime TD") + T(f"  one per game, DK {band[0]:.2f} to {band[1]:.2f}"))
        for i, l in enumerate(legs, 1):
            out.append(f"{i}. " + _bet_line(l, B, T))
        if len(legs) == len(C.get("legs") or []) and C.get("odds"):
            out.append(T(f"All {len(legs)} together: {C['odds']:.2f} ({C['prob']*100:.1f}% to hit, fair {C.get('fair_odds') or 0:.2f})"))
    else:
        out.append("🏆 " + B("Bot's top 6") + T(": fewer than six legs qualify for the games still to play"))
    return out


def build(p: dict, reason: str, html: bool, window: list[dict] | None = None) -> str:
    B = (lambda t: f"<b>{_h(t)}</b>") if html else (lambda t: str(t))
    T = _h if html else (lambda t: str(t))
    gs = sorted(p["games"], key=lambda g: g.get("kickoff_utc") or "")
    kos = [k for k in (ko(g) for g in gs) if k]
    span = f"{kos[0].astimezone(ZoneInfo('America/New_York')):%a %b %-d} to {kos[-1].astimezone(ZoneInfo('America/New_York')):%a %b %-d}" if kos else ""
    head = {"weekly": "🗓️ Week preview", "daily": "🗓️ Week preview", "t75": "⏰ Kickoff soon", "update": "🔄 Update", "research": "⭐ Research desk", "test": "🧪 Test message"}.get(reason, "🔄 Update")
    out = [f"🏈 {B('Gill Sports · NFL week ' + str(p['week']))} · {T(head)}", T(f"{span} · {len(gs)} games")]
    if reason == "t75" and window:
        out.append("")
        for g in window:
            mk = g["markets"]; L = g.get("lines") or {}
            fav = "home" if mk["ml"]["home"] >= mk["ml"]["away"] else "away"
            s = L.get("spread")
            sp = "no line" if s is None else (f"{g['home']} -{s:g}" if s > 0 else (f"{g['away']} -{-s:g}" if s < 0 else "pick'em"))
            line = [f"{B(g['away'] + ' @ ' + g['home'])} · {T(et(ko(g)))}",
                    T(f"  {g[fav]} wins {mk['ml'][fav]*100:.0f}% · {sp} · total {L.get('total')}")]
            for side in ("away", "home"):
                q = g["qb"][side]
                if q.get("change"):
                    line.append(T(f"  QB change: {q.get('name','?')} starts for {g[side]}"))
            outs = [i for s in ("away", "home") for i in (g.get("injuries") or {}).get(s, []) if i.get("status") in ("Out", "Doubtful") and i.get("pos") in ("QB", "RB", "WR", "TE", "K")]
            if outs:
                line.append(T("  Out: " + ", ".join(f"{i['name']} {i['pos']}" for i in outs[:6])))
            out.append("\n".join(line))
            out.append("")
        out.extend(bot_lines(p, B, T, game_ids={g["game_id"] for g in window}))
    else:
        out.append("")
        out.extend(bot_lines(p, B, T))
        changes = [f"{g['qb'][s]['name']} ({g[s]})" for g in gs for s in ("home", "away") if g["qb"][s].get("change")]
        if changes:
            out.append("")
            out.append("🧢 " + T("QB changes: " + ", ".join(changes)))
        wx = [f"{g['away']}@{g['home']} {g['weather']['wind']:.0f} mph" for g in gs if g.get("weather") and (g["weather"].get("wind") or 0) >= 15]
        if wx:
            out.append("🌬️ " + T("Windy: " + ", ".join(wx)))
    out.append("")
    out.append("🔗 " + (f'<a href="{SITE}">Open Gill Sports · NFL</a>' if html else SITE))
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reason", default="daily")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.dry_run and not (os.environ.get("DISCORD_WEBHOOK_URL") or os.environ.get("TELEGRAM_BOT_TOKEN")):
        print("no notification channel configured")
        return
    if a.reason == "quiet":
        print("quiet rebuild: no message")
        return
    p = current_payload()
    if not p:
        print("no NFL payload")
        return
    now = datetime.now(timezone.utc)
    window = None
    if a.reason == "t75":
        window = [g for g in p["games"] if ko(g) and timedelta(minutes=-10) <= ko(g) - now <= timedelta(hours=2, minutes=30) and not g.get("actual")]
        if not window:
            print("no game in the next window; not sending")
            return
    if a.reason == "daily" and now.astimezone(ZoneInfo("America/New_York")).weekday() != 2:
        print("daily build: the week preview goes out on Wednesdays; not sending")
        return
    text = build(p, a.reason, False, window)
    if a.dry_run:
        print(text)
        print("\n--- telegram html ---\n" + build(p, a.reason, True, window))
        return
    for part in chunks(build(p, a.reason, True, window)):
        send_telegram(part)
    for part in chunks(text, 1900):
        send_discord(part)


def chunks(text: str, limit: int = 3800) -> list[str]:
    """Telegram caps a message at 4096 characters (Discord at 2000): split on blank lines."""
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if cur and len(cur) + len(block) + 2 > limit:
            parts.append(cur); cur = block
        else:
            cur = (cur + "\n\n" + block) if cur else block
    if cur:
        parts.append(cur)
    return parts


if __name__ == "__main__":
    main()
