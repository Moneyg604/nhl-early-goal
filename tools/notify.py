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


STATUS_ICON = {"confirmed": "✅", "expected": "🟡", "likely": "🟡", "projected": "⏳", "unconfirmed": "⏳", "unknown": "❔"}


def _h(x) -> str:
    return str(x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_message(p: dict, reason: str, html: bool = False) -> str:
    """The slate as a phone message. `html=True` renders Telegram's HTML flavour (bold, monospace); otherwise plain text."""
    B = (lambda t: f"<b>{_h(t)}</b>") if html else (lambda t: str(t))
    T = _h if html else (lambda t: str(t))
    games = p["games"]
    qs = [q for g in games for q in (g["goalies"]["home"], g["goalies"]["away"])]
    conf = sum(1 for q in qs if q.get("status") == "confirmed")
    try:
        y, m, d = p["date"].split("-")
        nice = datetime(int(y), int(m), int(d)).strftime("%a %b %-d")
    except Exception:  # noqa: BLE001
        nice = p["date"]
    head_icon, head_txt = {"t120": ("⏰", "Two hours to puck drop"), "morning": ("☀️", "Morning slate"), "update": ("🔄", "Update"), "test": ("🧪", "Test message")}.get(reason, ("🔄", reason))
    lines = [f"🏒 {B('Early Goal Desk')} · {T(nice)}", f"{head_icon} {T(head_txt)} · {len(games)} games · goalies {conf}/{len(qs)} confirmed", ""]

    def rng(g):
        u = (g.get("uncertainty") or {}).get("first5")
        return f" · range {u['lo']*100:.0f}–{u['hi']*100:.0f}" if u else ""

    top5 = sorted(games, key=lambda g: -g["markets"]["u05_first5"]["p"])[:3]
    lines.append(f"🔒 {B('Under 0.5 · first 5 minutes')}")
    for i, g in enumerate(top5, 1):
        mk = g["markets"]["u05_first5"]
        lines.append(f"{i}. {T(g['matchup'])}  {B(pct(mk['p']))}  fair {mk['fair']:.2f}{rng(g) if i == 1 else ''}")
    lines.append("")

    def best(key, sides=None):
        cands = []
        for g in games:
            if sides:
                for k, t in ((sides[0], g["home"]), (sides[1], g["away"])):
                    cands.append((g["markets"][k]["p"], g, t))
            elif key in g["markets"]:
                cands.append((g["markets"][key]["p"], g, g["markets"][key].get("pick")))
        return max(cands, key=lambda x: x[0]) if cands else None

    board = [("⬆️", "Over 4.5", best("fg_over45")), ("🥅", "Team over 1.5", best(None, sides=("home_over15", "away_over15"))),
             ("1️⃣", "1P under 2.5", best("p1_under25")), ("💰", "FG moneyline", best("fg_ml")), ("➕", "1P +0.5", best("p1_plus05"))]
    lines.append(f"🎯 {B('Best of the board')}")
    for icon, label, b in board:
        if not b:
            continue
        pp, g, t = b
        lines.append(f"{icon} {T(label)}: {T(g['matchup'])}{' ' + B(t) if t else ''}  {B(pct(pp))}")
    lines.append("")

    lines.append(f"🧤 {B('Starters')}")
    for g in games:
        a, h = g["goalies"]["away"], g["goalies"]["home"]
        la = (a.get("name") or "unknown").split()[-1]
        lh = (h.get("name") or "unknown").split()[-1]
        lines.append(f"{T(g['matchup'])}  {T(la)} {STATUS_ICON.get(a.get('status'), '❔')} / {T(lh)} {STATUS_ICON.get(h.get('status'), '❔')}  {T(g.get('time_et', ''))}")
    tired = [g["matchup"] for g in games if ((g.get("research") or {}).get("schedule") or {}).get("mutual_fatigue")]
    if tired:
        lines += ["", f"😴 {B('Both teams tired')} (slow-start factor on): {T(', '.join(tired))}"]
    ch = p.get("changes") or {}
    items = [x for x in (ch.get("items") or []) if x.get("kind") in ("goalie", "status", "slate", "tier")]
    if items:
        lines += ["", f"🔁 {B('Since ' + str(ch.get('since', 'the last build')))}"] + [f"• {T(x['game'])}: {T(x['text'])}" for x in items[:10]]
    lines += ["", f"🔗 {T(SITE)}" if not html else f'🔗 <a href="{SITE}">Open the desk</a>']
    return "\n".join(lines)


def telegram_chat_id(tok: str) -> str | None:
    """The chat to post to: TELEGRAM_CHAT_ID when set, else the most recent private chat that messaged the bot
    (Telegram keeps those updates for about a day, so this is for first contact, not for every run)."""
    import requests  # type: ignore

    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if chat:
        return chat
    if CHAT_FILE.exists():
        chat = _unseal(tok, CHAT_FILE.read_text())
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


CHAT_FILE = ROOT / "data" / "telegram_chat.enc"


def _pad(tok: str) -> bytes:
    import hashlib

    return hashlib.sha256(("egd-chat:" + tok).encode()).digest()


def _seal(tok: str, chat: str) -> str:
    """The chat id sealed with the bot token (XOR against a token-derived pad plus an HMAC tag). The
    repository is public, so the id is never stored in the clear; only the holder of the token can read it."""
    import base64, hashlib, hmac

    raw = chat.encode()
    pad = _pad(tok)
    ct = bytes(b ^ pad[i % len(pad)] for i, b in enumerate(raw))
    tag = hmac.new(pad, ct, hashlib.sha256).digest()[:8]
    return base64.b64encode(tag + ct).decode()


def _unseal(tok: str, blob: str) -> str | None:
    import base64, hashlib, hmac

    try:
        data = base64.b64decode(blob.strip())
        tag, ct = data[:8], data[8:]
        pad = _pad(tok)
        if not hmac.compare_digest(tag, hmac.new(pad, ct, hashlib.sha256).digest()[:8]):
            return None
        return bytes(b ^ pad[i % len(pad)] for i, b in enumerate(ct)).decode()
    except Exception:  # noqa: BLE001
        return None


def remember_chat_id(chat: str, tok: str) -> bool:
    """Keep the discovered chat id for later runs: sealed with the token into data/telegram_chat.enc (committed by
    the workflow), and as a repository variable when the token has that permission."""
    import subprocess

    ok = False
    try:
        CHAT_FILE.parent.mkdir(parents=True, exist_ok=True)
        CHAT_FILE.write_text(_seal(tok, chat) + "\n")
        print("chat id sealed into", CHAT_FILE.name)
        ok = True
    except Exception as e:  # noqa: BLE001
        print("could not write the sealed chat id:", e)
    repo = os.environ.get("GH_REPO") or os.environ.get("GITHUB_REPOSITORY")
    if repo and os.environ.get("GH_TOKEN"):
        r = subprocess.run(["gh", "variable", "set", "TELEGRAM_CHAT_ID", "--repo", repo, "--body", chat], capture_output=True, text=True)
        print("gh variable set:", "ok" if r.returncode == 0 else "not permitted (fine, the sealed file is enough)")
        ok = ok or r.returncode == 0
    return ok


def send_telegram(text: str) -> bool:
    import requests  # type: ignore

    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok:
        return False
    chat = telegram_chat_id(tok)
    if not chat:
        print("telegram: no chat id yet; message the bot once, then run the setup workflow")
        return False
    discovered = not os.environ.get("TELEGRAM_CHAT_ID") and not (CHAT_FILE.exists() and _unseal(tok, CHAT_FILE.read_text()) == chat)
    if discovered:
        saved = remember_chat_id(chat, tok)
        text += f"\n\n({'Chat saved; alerts will arrive here from now on.' if saved else 'Chat found but not saved; message the bot again tomorrow.'})"
    r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=20)
    print("telegram:", r.status_code)
    if not r.ok:
        # fall back to plain text if the HTML was rejected for any reason
        r = requests.post(f"https://api.telegram.org/bot{tok}/sendMessage", json={"chat_id": chat, "text": re.sub(r"<[^>]+>", "", text), "disable_web_page_preview": True}, timeout=20)
        print("telegram (plain):", r.status_code)
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
        print("\n--- telegram html ---\n" + build_message(p, a.reason, html=True))
        return
    ok = send_telegram(build_message(p, a.reason, html=True)) | send_discord(text)
    if use_issue:
        ok = send_github_issue(text, date, a.reason) | ok
    if not ok:
        sys.exit(0)


if __name__ == "__main__":
    main()
