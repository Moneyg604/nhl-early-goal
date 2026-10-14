"""Static site + installable web app (PWA) built from the daily dashboards.

`python -m earlygoal publish` turns out/dashboard-<date>.html into

    docs/index.html            latest slate, with a day switcher and install hooks
    docs/days/<date>.html      every slate kept so far
    docs/days.json             list of days, newest first
    docs/manifest.webmanifest  home-screen install (name, icon, standalone display)
    docs/sw.js                 service worker: network first, last copy offline
    docs/icon-192.png, icon-512.png, apple-touch-icon.png

Serve docs/ from GitHub Pages (or any static host) and open it on a phone;
"Add to Home Screen" gives an app icon that opens full screen and refreshes
itself whenever the scheduled job publishes a new slate.
"""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from .config import OUT_DIR, ROOT

SITE_DIR = ROOT / "docs"

HEAD_EXTRA = """<link rel="manifest" href="{base}manifest.webmanifest">
<meta name="theme-color" content="#070c14">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Early Goal">
<link rel="apple-touch-icon" href="{base}apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="192x192" href="{base}icon-192.png">
<style>
.sitebar{{display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:0 0 12px;padding:8px 12px;border:1px solid var(--line);border-radius:12px;background:var(--panel);font-size:12px;color:var(--muted)}}
.sitebar select{{background:#0a1220;border:1px solid var(--line);color:var(--text);border-radius:8px;padding:6px 8px;font-size:13px}}
.sitebar .upd{{margin-left:auto}}
.sitebar .install{{display:none;color:var(--ice)}}
</style>
"""

SITEBAR = """<nav class="sitebar"><span>Slate</span><select id="daysel" aria-label="slate date">{options}</select><span class="install" id="installhint">Add to Home Screen for the app view</span><span class="upd">published {published}</span></nav>
<script>
(function(){{
  var s=document.getElementById('daysel'); if(s) s.onchange=function(){{ location.href=this.value; }};
  var ua=navigator.userAgent||''; var standalone=window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone;
  if(!standalone && /iPhone|iPad|Android/.test(ua)){{ var h=document.getElementById('installhint'); if(h) h.style.display='inline'; }}
  if('serviceWorker' in navigator){{ navigator.serviceWorker.register('{base}sw.js').catch(function(){{}}); }}
}})();
</script>
"""

MANIFEST = {
    "name": "Early Goal Desk",
    "short_name": "Early Goal",
    "description": "NHL first-5 and first-10 minute under 0.5, 1P and FG markets, simulated daily",
    "start_url": "./",
    "scope": "./",
    "display": "standalone",
    "background_color": "#070c14",
    "theme_color": "#070c14",
    "icons": [
        {"src": "icon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any"},
        {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
    ],
}

SW = """// Early Goal Desk service worker: network first, fall back to the last copy when offline.
const CACHE = 'egd-v2';
self.addEventListener('install', e => { self.skipWaiting(); });
self.addEventListener('activate', e => { e.waitUntil(self.clients.claim()); });
self.addEventListener('fetch', e => {
  const req = e.request;
  if (req.method !== 'GET') return;
  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;          // never touch the scoreboard or relays
  if (url.pathname.endsWith('.json')) return;                // live.json and scorecard.json are network-only
  e.respondWith(
    fetch(req).then(res => {
      const copy = res.clone();
      caches.open(CACHE).then(c => c.put(req, copy)).catch(() => {});
      return res;
    }).catch(() => caches.match(req).then(r => r || (req.mode === 'navigate' ? caches.match('./index.html') : undefined)))
  );
});
"""


def _icon(size: int, path: Path) -> None:
    """Dark rounded tile with a goal-light glyph; drawn with PIL so no asset ships with the repo."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = size // 5
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=(7, 12, 20, 255))
    # ice-blue ring (the goal light) and a green puck-dot
    cx, cy = size / 2, size / 2
    rr = size * 0.30
    w = max(3, size // 22)
    d.ellipse((cx - rr, cy - rr, cx + rr, cy + rr), outline=(111, 211, 255, 255), width=w)
    pr = size * 0.11
    d.ellipse((cx - pr, cy - pr, cx + pr, cy + pr), fill=(61, 220, 132, 255))
    # tick marks at 5 and 10 o'clock positions (the two windows)
    import math

    for ang in (-60, -120):
        a = math.radians(ang)
        x1, y1 = cx + math.cos(a) * rr * 1.18, cy + math.sin(a) * rr * 1.18
        x2, y2 = cx + math.cos(a) * rr * 1.42, cy + math.sin(a) * rr * 1.42
        d.line((x1, y1, x2, y2), fill=(111, 211, 255, 255), width=w)
    img.save(path)


def _inject(html: str, options_html: str, published: str, base: str) -> str:
    html = html.replace("<title>Early Goal Desk</title>", "<title>Early Goal Desk</title>\n" + HEAD_EXTRA.format(base=base), 1)
    bar = SITEBAR.format(options=options_html, published=published, base=base)
    return html.replace('<div class="wrap">\n<header>', '<div class="wrap">\n' + bar + "<header>", 1)


def build_site(out_dir: Path = OUT_DIR, site_dir: Path = SITE_DIR, keep_days: int = 30, prior_days: list[str] | None = None, artifact: bool = False) -> Path:
    """Build the site. `prior_days` lists dates already published elsewhere (their pages are kept by the
    host, so they appear in the selector without being rebuilt). `artifact` also writes index.artifact.html,
    the index without a document skeleton, for hosts that wrap the page themselves."""
    site_dir.mkdir(parents=True, exist_ok=True)
    days_dir = site_dir / "days"
    days_dir.mkdir(exist_ok=True)
    # carry over previously published days, add new ones from out/
    for f in sorted(out_dir.glob("dashboard-*.html")):
        m = re.match(r"dashboard-(\d{4}-\d{2}-\d{2})\.html$", f.name)
        if not m:
            continue  # demo files are not published
        shutil.copy(f, days_dir / f"{m.group(1)}.raw.html")
    raws = sorted(days_dir.glob("*.raw.html"), reverse=True)[:keep_days]
    for stale in sorted(days_dir.glob("*.raw.html"), reverse=True)[keep_days:]:
        stale.unlink(missing_ok=True)
        (days_dir / stale.name.replace(".raw.html", ".html")).unlink(missing_ok=True)
    local_days = [p.name.replace(".raw.html", "") for p in raws]
    days = sorted(set(local_days) | set(prior_days or []), reverse=True)[:keep_days]
    if not raws:
        raise SystemExit("nothing to publish: run `python -m earlygoal run` first")
    published = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def options(selected: str, base: str) -> str:
        return "".join(
            f'<option value="{base}days/{d}.html" {"selected" if d == selected else ""}>{d}{" (latest)" if i == 0 else ""}</option>'
            for i, d in enumerate(days)
        )

    for raw in raws:
        d = raw.name.replace(".raw.html", "")
        html = raw.read_text(encoding="utf-8")
        (days_dir / f"{d}.html").write_text(_inject(html, options(d, "../"), published, "../"), encoding="utf-8")
    latest = raws[0].read_text(encoding="utf-8")
    (site_dir / "index.html").write_text(_inject(latest, options(local_days[0], "./"), published, "./"), encoding="utf-8")
    (site_dir / "days.json").write_text(json.dumps({"days": days, "latest": local_days[0], "published": published}, indent=1))
    if artifact:
        idx = (site_dir / "index.html").read_text(encoding="utf-8")
        start, end = idx.index("<title>"), idx.rindex("</body>")
        (site_dir / "index.artifact.html").write_text(idx[start:end], encoding="utf-8")
    (site_dir / "manifest.webmanifest").write_text(json.dumps(MANIFEST, indent=1))
    sc = ROOT / "data" / "scorecard.json"
    if sc.exists():
        shutil.copy(sc, site_dir / "scorecard.json")
    (site_dir / "sw.js").write_text(SW)
    (site_dir / ".nojekyll").write_text("")
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")):
        if not (site_dir / name).exists():
            _icon(size, site_dir / name)
    return site_dir
