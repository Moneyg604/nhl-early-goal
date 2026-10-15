"""Site name, address and brand assets, shared by the NHL and NFL sections and the alert bots.

The public address follows the GitHub repository automatically: a repository named <owner>.github.io (or an
organisation site such as gill-sports.github.io) is served at the root, any other repository at
https://<owner>.github.io/<repository>/. CI passes GITHUB_REPOSITORY; locally the git remote is read.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

NAME = "Gill Sports"
SHORT = "Gill Sports"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "brand"
SITE_FILES = ("icon-192.png", "icon-512.png", "apple-touch-icon.png", "favicon.png", "brand-mark.png", "og.jpg")
ASSET_VERSION = "2"          # bump when the brand files change (cache-busting query on the header mark)


def repository() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY") or os.environ.get("GH_REPO") or ""
    if repo:
        return repo
    try:
        url = subprocess.run(["git", "-C", str(ROOT), "remote", "get-url", "origin"], capture_output=True, text=True).stdout.strip()
        m = re.search(r"github\.com[/:]([^/]+/[^/.]+(?:\.github\.io)?)", url)
        return m.group(1) if m else ""
    except Exception:  # noqa: BLE001
        return ""


def site_url() -> str:
    """https://gill-sports.github.io/ for an organisation site, else https://owner.github.io/repo/."""
    override = os.environ.get("SITE_URL")
    if override:
        return override.rstrip("/") + "/"
    repo = repository()
    if "/" not in repo:
        return "https://moneyg604.github.io/nhl-early-goal/"
    owner, name = repo.split("/", 1)
    if name.lower().endswith(".github.io"):
        return f"https://{name.lower()}/"
    return f"https://{owner.lower()}.github.io/{name}/"


def copy_assets(site_dir: Path) -> None:
    """Icons, header mark and link-preview image into the published site root."""
    site_dir.mkdir(parents=True, exist_ok=True)
    for f in SITE_FILES:
        src = ASSETS / f
        if src.exists():
            shutil.copy(src, site_dir / f)


def head_tags(root: str, title: str, description: str) -> str:
    """Favicons, home-screen icons and the link preview (Telegram, iMessage, ChatGPT) for a page."""
    url = site_url()
    return (f'<link rel="icon" type="image/png" href="{root}favicon.png">'
            f'<meta property="og:site_name" content="{NAME}"><meta property="og:title" content="{title}">'
            f'<meta property="og:description" content="{description}"><meta property="og:image" content="{url}og.jpg">'
            f'<meta property="og:type" content="website"><meta name="twitter:card" content="summary_large_image">')


# header: the crown mark, the wordmark, and the sport switch; colours tuned to the logo (violet accent, gold word)
BRAND_CSS = """
:root{--ice:#b49bff}
.brand{display:flex;align-items:center;gap:10px}
.brand .logo{width:40px;height:40px;border-radius:10px;object-fit:cover;box-shadow:0 0 0 1px rgba(180,155,255,.35),0 4px 14px rgba(120,80,255,.25)}
.brand .bt{font-family:var(--display);font-weight:800;letter-spacing:.05em;text-transform:uppercase;background:linear-gradient(180deg,#ffe08a,#e2a93b 60%,#b9842a);-webkit-background-clip:text;background-clip:text;color:transparent}
.brand .bt span{background:linear-gradient(180deg,#e9e2ff,#b49bff);-webkit-background-clip:text;background-clip:text;color:transparent}
.sport a.on{color:#120a24 !important}
@media (max-width:480px){.brand .logo{width:34px;height:34px}}
"""


def brand_html(root: str, sport: str, other_href: str) -> str:
    nhl = '<a class="on" href="#">NHL</a>' if sport == "nhl" else f'<a href="{other_href}">NHL</a>'
    nfl = '<a class="on" href="#">NFL</a>' if sport == "nfl" else f'<a href="{other_href}">NFL</a>'
    return (f'<div class="brand"><img class="logo" src="{root}brand-mark.png?v={ASSET_VERSION}" alt="{NAME}" width="40" height="40">'
            f'<span class="bt">Gill <span>Sports</span></span><nav class="sport" aria-label="sport">{nhl}{nfl}</nav></div>')


__all__ = ["NAME", "SHORT", "site_url", "copy_assets", "head_tags", "brand_html", "BRAND_CSS", "repository"]
