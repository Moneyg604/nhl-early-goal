"""Send tonight's NBA slate to Telegram / Discord, same channels as the NHL and NFL bots.

    python tools/notify_nba.py --reason daily      # the morning preview (lines, the bot's picks)
    python tools/notify_nba.py --reason props      # the pre-tip message (desk, props, the bot's top five)
    python tools/notify_nba.py --reason research   # after a desk run
    python tools/notify_nba.py --reason test --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
from notify import _h, send_discord, send_telegram  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from earlygoal.brand import site_url  # noqa: E402

SITE = site_url() + "nba/"
CAT_ICON = {"points": "🎯", "rebounds": "🙌", "assists": "🤝", "threes": "🏹", "pra": "📊", "moneyline": "💰", "spread": "➕", "totals": "🔢"}
PROP_MIN_P = 0.62


def current_payload() -> dict | None:
    dj = ROOT / "docs" / "nba" / "days.json"
    if not dj.exists():
        return None
    cur = json.loads(dj.read_text()).get("current")
    f = ROOT / "docs" / "nba" / "days" / f"{cur}.json"
    return json.loads(f.read_text()) if f.exists() else None


def et(iso: str) -> str:
    try:
        return datetime.strptime(iso, "%Y-%m-%dT%H:%MZ").replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/New_York")).strftime("%-I:%M %p ET")
    except Exception:  # noqa: BLE001
        return ""


def _bet_line(b: dict, B, T, with_mu: bool = True) -> str:
    mu = f" ({b['mu']})" if with_mu else ""
    odds = f" @ {b['odds']:.2f}" if b.get("odds") else " (model line, no DK price)"
    ev = f"  EV {b['ev']*100:+.1f}%" if b.get("ev") is not None else ""
    return f"{T(b['label'] + mu)}  {B(f'{b['p']*100:.0f}%')}{T(odds + ev)}"


def build(p: dict, reason: str, html: bool) -> str:
    B = (lambda t: f"<b>{_h(t)}</b>") if html else (lambda t: str(t))
    T = _h if html else (lambda t: str(t))
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    gs = sorted(p["games"], key=lambda g: g.get("tip_utc") or "")
    head = {"daily": "🗓️ Tonight's slate", "props": "⏰ Pre-tip", "research": "⭐ Research desk", "update": "🔄 Update", "test": "🧪 Test message"}.get(reason, "🔄 Update")
    out = [f"🏀 {B('Gill Sports · NBA ' + p['date'])} · {T(head)}", T(f"{len(gs)} games")]
    bot = p.get("bot") or {}
    board = {b["id"]: b for b in (p.get("best_bets") or {}).get("ranked", []) + (bot.get("extra") or [])}

    def live(b):
        return bool(b) and (not b.get("kick") or b["kick"] > now)
    out.append("")
    for g in gs:
        L = g.get("lines") or {}; m = g.get("model") or {}
        if g.get("tip_utc") and g["tip_utc"] <= now:
            continue
        sp = f"{g['home']} {L['spread']:+g}" if L.get("spread") is not None else "no line"
        out.append(T(f"• {g['away']} @ {g['home']} {et(g.get('tip_utc') or '')} · {sp} · total {L.get('total', '–')} · model {g['home']} {m.get('home_win', 0)*100:.0f}%, margin {m.get('margin', 0):+}, total {m.get('total')}"))
    desk = bot.get("desk") or {}
    if desk.get("ok"):
        rows = [x for x in desk.get("selections") or [] if live(x)]
        out.append("")
        if rows:
            band = desk.get("band") or [1.35, 2.2]
            out.append("⭐ " + B(f"Research desk · {len(rows)} selection{'s' if len(rows) != 1 else ''}") + T(f"  desk win chance @ DK {band[0]:.2f} to {band[1]:.2f} · grade"))
            for i, x in enumerate(rows[:12], 1):
                src = {"feed": "", "draftkings": " (DK checked)", "unverified": " (price unverified)"}.get(x.get("odds_source") or "", "")
                out.append(f"{i}. " + T(f"{x['label']} ({x['mu']})") + "  " + B(f"{x['p']*100:.0f}%") + T(f" @ {x['odds']:.2f}{src} · {x['grade']} · {x.get('evidence', '')}"))
        wild = [x for x in desk.get("wild_cards") or [] if live(x)]
        if wild:
            out.append("🃏 " + B(f"Wild cards · {len(wild)}"))
            for x in wild:
                out.append("• " + T(f"{x['label']} ({x['mu']})") + "  " + B(f"{x['p']*100:.0f}%") + T(f" @ {x['odds']:.2f} · {x['grade']}"))
        alerts = [a for a in desk.get("alerts") or [] if not a.get("kick") or a["kick"] > now]
        if alerts:
            out.append("🚨 " + B("Line moved against a desk pick"))
            for a in alerts:
                out.append("• " + T(f"{a['label']} ({a['mu']}): {a['why']}"))
    cats = bot.get("cats") or {}
    out.append("")
    out.append("🤖 " + B("Bot's picks") + T("  win chance @ DraftKings price · EV"))
    any_cat = False
    for c in (bot.get("rules") or {}).get("categories") or []:
        cat = cats.get(c["key"]) or {}
        rows = [board.get(i) for i in cat.get("ids") or []]
        rows = [b for b in rows if live(b)]
        if not rows:
            continue
        any_cat = True
        out.append(f"{CAT_ICON.get(c['key'], '•')} " + B(c.get("label") or c["key"]))
        for b in rows:
            out.append("• " + _bet_line(b, B, T))
    if not any_cat:
        out.append(T("Nothing passes the bot's checks for the games still to play (props are priced before the first tip)."))
    props = [b for b in board.values() if live(b) and b["kind"] in ("pts", "reb", "ast", "threes", "pra") and b.get("odds") and b["p"] >= PROP_MIN_P and (b.get("ev") or 0) > 0]
    props.sort(key=lambda b: (-b["p"], -(b.get("ev") or 0)))
    if props:
        out.append("")
        out.append("🎟️ " + B(f"Player props {round(PROP_MIN_P*100)}%+ with positive EV at DraftKings"))
        for b in props[:10]:
            out.append("• " + _bet_line(b, B, T))
    C = bot.get("combine") or {}
    legs = [l for l in (C.get("legs") or []) if live(l)]
    if legs:
        out.append("")
        band = C.get("odds_band") or [1.35, 2.2]
        out.append("🏆 " + B(f"Bot's top {len(legs)}") + T(f"  one per game, DK {band[0]:.2f} to {band[1]:.2f}"))
        for i, l in enumerate(legs, 1):
            out.append(f"{i}. " + _bet_line(l, B, T))
    out.append("")
    out.append("🔗 " + (f'<a href="{SITE}">Open Gill Sports · NBA</a>' if html else SITE))
    return "\n".join(out)


def chunks(text: str, limit: int = 3800) -> list[str]:
    parts, cur = [], ""
    for block in text.split("\n\n"):
        if cur and len(cur) + len(block) + 2 > limit:
            parts.append(cur); cur = block
        else:
            cur = (cur + "\n\n" + block) if cur else block
    if cur:
        parts.append(cur)
    return parts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reason", default="daily")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.dry_run and not (os.environ.get("DISCORD_WEBHOOK_URL") or os.environ.get("TELEGRAM_BOT_TOKEN")):
        print("no notification channel configured"); return
    if a.reason == "quiet":
        print("quiet rebuild: no message"); return
    p = current_payload()
    if not p or not p.get("games"):
        print("no NBA games to report"); return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    if all((g.get("tip_utc") or "") <= now for g in p["games"]):
        print("every game has tipped off; not sending"); return
    text = build(p, a.reason, False)
    if a.dry_run:
        print(text); print("\n--- telegram html ---\n" + build(p, a.reason, True)); return
    for part in chunks(build(p, a.reason, True)):
        send_telegram(part)
    for part in chunks(text, 1900):
        send_discord(part)


if __name__ == "__main__":
    main()
