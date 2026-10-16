"""Send the NFL week (or the next kickoff window) to Telegram / Discord, same channels as the NHL bot.

    python tools/notify_nfl.py --reason weekly    # the week's leans (sent on Wednesdays, or when the week changes)
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


def best_lines(p: dict, B, T, game_ids: set | None = None, n: int = 10) -> list[str]:
    """The good DraftKings bets, best expected value first (nfl/value.py)."""
    bb = p.get("best_bets") or {}
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    good = [b for b in (bb.get("ranked") or []) if b.get("good") and (not b.get("kick") or b["kick"] > now)
            and (game_ids is None or b["game_id"] in game_ids)]
    if not bb:
        return []
    if not good:
        return ["🎯 " + B("Best bets at DraftKings") + T(": none clears the bar right now (EV +2% or better on the market's fair odds).")]
    out = ["🎯 " + B(f"Best bets at DraftKings ({len(good)})") + T("  EV at DK's price · market win chance")]
    for i, b in enumerate(good[:n], 1):
        out.append(T(f"{i}. {b['label']} ({b['mu']}) {_am(b['odds'])} · EV {b['ev']*100:+.1f}% · {b['p']*100:.0f}%"))
    if len(good) > n:
        out.append(T(f"…and {len(good) - n} more on the page"))
    return out


def build(p: dict, reason: str, html: bool, window: list[dict] | None = None) -> str:
    B = (lambda t: f"<b>{_h(t)}</b>") if html else (lambda t: str(t))
    T = _h if html else (lambda t: str(t))
    gs = sorted(p["games"], key=lambda g: g.get("kickoff_utc") or "")
    kos = [k for k in (ko(g) for g in gs) if k]
    span = f"{kos[0].astimezone(ZoneInfo('America/New_York')):%a %b %-d} to {kos[-1].astimezone(ZoneInfo('America/New_York')):%a %b %-d}" if kos else ""
    head = {"weekly": "🗓️ Week preview", "daily": "🗓️ Week preview", "t75": "⏰ Kickoff soon", "update": "🔄 Update", "test": "🧪 Test message"}.get(reason, "🔄 Update")
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
        out.extend(best_lines(p, B, T, game_ids={g["game_id"] for g in window}, n=8))
    else:
        out.append("")
        out.extend(best_lines(p, B, T))
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
