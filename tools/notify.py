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


def telegram_chat_id(tok: str) -> str | None:
    """The chat to post to: TELEGRAM_CHAT_ID when set, else the most recent private chat that messaged the bot
    (Telegram keeps those updates for about a day, so this is for first contact, not for every run)."""
    import requests  # type: ignore

    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if chat:
        return chat
    try:
        r = requests.get(f"https://api.telegram.org/bot{tok}/getUpdates", timeout=20)
        for u in reversed(r.json().get("result", [])):
            m = u.get("message") or u.get("edited_message") or {}
            c = m.get("chat") or {}
            if c.get("id"):
                return str(c["id"])
    except Exception as e:  # noqa: BLE001
        print("telegram getUpdates failed:", e)
    return None


def remember_chat_id(chat: str) -> bool:
    """Keep the discovered chat id as a repository variable (visible to collaborators only) so later runs need no getUpdates."""
    import subprocess

    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if not repo or not os.environ.get("GH_TOKEN"):
        return False
    r = subprocess.run(["gh", "variable", "set", "TELEGRAM_CHAT_ID", "--repo", repo, "--body", chat], capture_output=True, text=True)
    print("gh variable set:", "ok" if r.returncode == 0 else r.stderr.strip()[:200])
    return r.returncode == 0


def send_telegram(text: str) -> bool:
    import requests  # type: ignore

    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok:
        return False
    chat = telegram_chat_id(tok)
    if not chat:
        print("telegram: no chat id yet; message the bot once, then run the setup workflow")
        return False
    discovered = not os.environ.get("TELEGRAM_CHAT_ID")
    if discovered:
        saved = remember_chat_id(chat)
        text += f"\n\n(Telegram chat {chat} {'saved; alerts will arrive here from now on' if saved else 'found; add it as the TELEGRAM_CHAT_ID secret so alerts keep working'})"
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text, "disable_web_page_preview": True}, timeout=20)
    print("telegram:", r.status_code)
    return r.ok


def send_github_issue(text: str, date: str, reason: str) -> bool:
    """No-secret channel: one GitHub issue per slate day, a comment per build, with an @mention of the
    repository owner so GitHub's own email / mobile notifications carry the message."""
    import subprocess

    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if not repo or not os.environ.get("GH_TOKEN"):
        return False
    owner = repo.split("/")[0]
    title = f"Slate {date}"
    body = f"@{owner}\n\n```\n{text}\n```"
    q = subprocess.run(["gh", "issue", "list", "--repo", repo, "--state", "open", "--label", "slate", "--search", f'"{title}" in:title', "--json", "number,title"],
                       capture_output=True, text=True)
    num = None
    try:
        for it in json.loads(q.stdout or "[]"):
            if it.get("title") == title:
                num = it["number"]
                break
    except json.JSONDecodeError:
        pass
    if num is None:
        subprocess.run(["gh", "label", "create", "slate", "--repo", repo, "--color", "0e8a16", "--description", "daily slate notifications", "--force"], capture_output=True, text=True)
        r = subprocess.run(["gh", "issue", "create", "--repo", repo, "--title", title, "--label", "slate", "--body", body], capture_output=True, text=True)
        print("github issue:", "created" if r.returncode == 0 else r.stderr.strip()[:200])
        ok = r.returncode == 0
    else:
        r = subprocess.run(["gh", "issue", "comment", str(num), "--repo", repo, "--body", body], capture_output=True, text=True)
        print("github issue:", f"comment on #{num}" if r.returncode == 0 else r.stderr.strip()[:200])
        ok = r.returncode == 0
    # close slate issues older than two days so the list stays short
    old = subprocess.run(["gh", "issue", "list", "--repo", repo, "--state", "open", "--label", "slate", "--json", "number,title"], capture_output=True, text=True)
    try:
        for it in json.loads(old.stdout or "[]"):
            d = it.get("title", "").replace("Slate ", "")
            if d and (datetime.fromisoformat(date) - datetime.fromisoformat(d)).days >= 2:
                subprocess.run(["gh", "issue", "close", str(it["number"]), "--repo", repo], capture_output=True, text=True)
    except (json.JSONDecodeError, ValueError):
        pass
    return ok


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
    ap.add_argument("--reason", default="update", help="t120 | morning | update | test (always sends)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    use_issue = os.environ.get("NOTIFY_GITHUB_ISSUE", "").lower() in ("1", "true", "yes")
    if not a.dry_run and not (os.environ.get("DISCORD_WEBHOOK_URL") or os.environ.get("TELEGRAM_BOT_TOKEN") or use_issue):
        print("no notification channel configured (set DISCORD_WEBHOOK_URL, TELEGRAM_BOT_TOKEN, or NOTIFY_GITHUB_ISSUE=1)")
        return
    date = a.date or slate_today()
    p = load_payload(date)
    if not p:
        print(f"no payload for {date}")
        return
    ch = p.get("changes") or {}
    notable = ch.get("first_build") or any(x.get("kind") in ("goalie", "status", "slate") for x in (ch.get("items") or []))
    if a.reason == "test":
        notable = True
    if a.reason == "update" and not notable:
        print("update without goalie or slate changes; not sending")
        return
    text = build_message(p, a.reason)
    if a.dry_run:
        print(text)
        return
    ok = send_telegram(text) | send_discord(text)
    if use_issue:
        ok = send_github_issue(text, date, a.reason) | ok
    if not ok:
        sys.exit(0)


if __name__ == "__main__":
    main()
