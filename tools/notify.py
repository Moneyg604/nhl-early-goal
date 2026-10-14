"""Send the slate summary to Telegram and/or Discord after a build, when a channel is configured.

Environment (GitHub secrets):
    TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID    a bot created with @BotFather and the chat it should post to
    DISCORD_WEBHOOK_URL                      a channel webhook (channel settings > integrations > webhooks)

    python tools/notify.py --reason t120     # always sends
    python tools/notify.py --reason update   # sends only when the build changed goalies or the slate
    python tools/notify.py --dry-run         # prints the message instead
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
SITE = "https://moneyg604.github.io/nhl-early-goal/"


def slate_today() -> str:
    return (datetime.now(timezone.utc).astimezone(ZoneInfo("America/Toronto")) - timedelta(hours=4)).strftime("%Y-%m-%d")


def load_payload(date: str) -> dict | None:
    for p in (ROOT / "docs" / "days" / f"{date}.json", ROOT / "out" / f"results-{date}.json"):
        if p.exists():
            return json.loads(p.read_text())
    page = ROOT / "docs" / "days" / f"{date}.raw.html"
    if page.exists():
        m = re.search(r'<script id="payload" type="application/json">(.*?)</script>', page.read_text(encoding="utf-8"), re.S)
        if m:
            return json.loads(m.group(1).replace("<\\/", "</"))
    return None


def pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def build_message(p: dict, reason: str) -> str:
    games = p["games"]
    qs = [q for g in games for q in (g["goalies"]["home"], g["goalies"]["away"])]
    conf = sum(1 for q in qs if q.get("status") == "confirmed")
    when = {"t120": "two hours before the first puck drop", "morning": "morning build", "update": "update"}.get(reason, reason)
    lines = [f"Early Goal Desk, {p['date']} ({when})", f"{len(games)} games, goalies confirmed {conf}/{len(qs)}, built {p.get('generated_utc', '')}", ""]

    def best(key, label, pick=None, sides=None):
        cands = []
        for g in games:
            if sides:
                for k, t in ((sides[0], g["home"]), (sides[1], g["away"])):
                    cands.append((g["markets"][k]["p"], g, t))
            elif key in g["markets"]:
                cands.append((g["markets"][key]["p"], g, g["markets"][key].get("pick") if pick else None))
        if not cands:
            return
        cands.sort(key=lambda x: -x[0])
        top = cands[:3]
        lines.append(label + ": " + "; ".join(f"{g['matchup']}{' ' + t if t else ''} {pct(pp)}" for pp, g, t in top))

    best("u05_first5", "Under 0.5 first 5")
    best("fg_over45", "Over 4.5")
    best(None, "Team over 1.5", sides=("home_over15", "away_over15"))
    best("p1_under25", "1P under 2.5")
    best("fg_ml", "FG moneyline", pick=True)
    best("p1_plus05", "1P +0.5", pick=True)
    ch = p.get("changes") or {}
    items = [x for x in (ch.get("items") or []) if x.get("kind") in ("goalie", "status", "slate", "tier")]
    if items:
        lines += ["", f"Changed since {ch.get('since', 'the last build')}:"] + [f"- {x['game']}: {x['text']}" for x in items[:10]]
    ahead = [g for g in games if g["tier"] == "C"]
    if ahead:
        lines.append(f"Tier C (something unmeasured): {', '.join(g['matchup'] for g in ahead)}")
    lines += ["", SITE]
    return "\n".join(lines)


def send_telegram(text: str) -> bool:
    import requests  # type: ignore

    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not tok or not chat:
        return False
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=20)
    print("telegram:", r.status_code)
    return r.ok


def send_discord(text: str) -> bool:
    import requests  # type: ignore

    url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not url:
        return False
    r = requests.post(url, json={"content": text[:1990]}, timeout=20)
    print("discord:", r.status_code)
    return r.ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--reason", default="update", help="t120 | morning | update")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not a.dry_run and not (os.environ.get("DISCORD_WEBHOOK_URL") or (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))):
        print("no notification channel configured (set DISCORD_WEBHOOK_URL or TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID)")
        return
    date = a.date or slate_today()
    p = load_payload(date)
    if not p:
        print(f"no payload for {date}")
        return
    ch = p.get("changes") or {}
    notable = ch.get("first_build") or any(x.get("kind") in ("goalie", "status", "slate") for x in (ch.get("items") or []))
    if a.reason == "update" and not notable:
        print("update without goalie or slate changes; not sending")
        return
    text = build_message(p, a.reason)
    if a.dry_run:
        print(text)
        return
    ok = send_telegram(text) | send_discord(text)
    if not ok:
        sys.exit(0)


if __name__ == "__main__":
    main()
