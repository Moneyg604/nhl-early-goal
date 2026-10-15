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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .brand import BRAND_CSS, NAME, brand_html, copy_assets, head_tags
from .config import OUT_DIR, ROOT


def slate_today(now: datetime | None = None) -> str:
    """The slate day: Eastern date, rolling over at 4 am so late West Coast games still belong to the night before."""
    now = now or datetime.now(timezone.utc)
    return (now.astimezone(ZoneInfo("America/Toronto")) - timedelta(hours=4)).strftime("%Y-%m-%d")

SITE_DIR = ROOT / "docs"

HEAD_EXTRA = """<link rel="manifest" href="{base}manifest.webmanifest">
<meta name="theme-color" content="#070b12">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Gill Sports">
<link rel="apple-touch-icon" href="{base}apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="192x192" href="{base}icon-192.png">
<style>
.hmeta .pub{{color:var(--dim)}}
.sport{{display:inline-flex;border:1px solid var(--line2);border-radius:999px;overflow:hidden;margin-left:10px;vertical-align:middle}}
.sport a{{font-family:var(--body);font-size:11.5px;font-weight:700;letter-spacing:.06em;padding:4px 10px;color:var(--muted);text-decoration:none}}
.sport a.on{{background:var(--ice);color:#06121e}}
@media (max-width:480px){{.brand .bt{{display:none}}.sport{{margin-left:0}}}}
.hmeta .install{{display:none;color:var(--ice);cursor:default}}
@media (max-width:640px){{.hmeta .pub,.hmeta .lbl2{{display:none}}}}
</style>
"""

# Goes into the app header's <span id="dayslot"> slot: a slate switcher, the publish time, the install hint.
DAYSLOT = """<span class="lbl2">Slate</span><select id="daysel" aria-label="slate date">{options}</select><span class="pub">published {published}</span><span class="install" id="installhint" title="Share, then Add to Home Screen">installable</span>"""

SITE_SCRIPT = """<script>
(function(){{
  var s=document.getElementById('daysel'); if(s) s.onchange=function(){{ location.href=this.value; }};
  // relabel the slate switcher relative to the viewer's own day (Eastern, rolling over at 4 am)
  try {{
    var t=new Date(Date.now()-4*3600*1000).toLocaleDateString('en-CA',{{timeZone:'America/Toronto'}});
    var tm=new Date(Date.now()+20*3600*1000).toLocaleDateString('en-CA',{{timeZone:'America/Toronto'}});
    var ys=new Date(Date.now()-28*3600*1000).toLocaleDateString('en-CA',{{timeZone:'America/Toronto'}});
    if(s) Array.prototype.forEach.call(s.options, function(o){{ var d=o.getAttribute('data-date'); if(!d) return;
      var l=o.getAttribute('data-label'), p=d===t?'Today':(d===tm?'Tomorrow':'');
      o.textContent = p ? p+' · '+l.replace(/^\\S+\\s/,'') : l; }});
  }} catch(e) {{}}
  var ua=navigator.userAgent||''; var standalone=window.matchMedia('(display-mode: standalone)').matches||window.navigator.standalone;
  if(!standalone && /iPhone|iPad|Android/.test(ua)){{ var h=document.getElementById('installhint'); if(h) h.style.display='inline'; }}
  if('serviceWorker' in navigator){{ navigator.serviceWorker.register('{base}sw.js').catch(function(){{}}); }}
}})();
</script>
"""

MANIFEST = {
    "name": "Gill Sports",
    "short_name": "Gill Sports",
    "description": "NHL and NFL research desk: simulated probabilities, research, live scores and picks",
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

SW = """// Gill Sports service worker: network first, fall back to the last copy when offline.
const CACHE = 'gs-v1';
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


LEGACY_BAR = """<nav class="sitebar" style="display:flex;flex-wrap:wrap;align-items:center;gap:8px 14px;margin:0 0 12px;padding:8px 12px;border:1px solid var(--line);border-radius:12px;background:var(--panel);font-size:12px;color:var(--muted)"><span>Slate</span><select id="daysel" aria-label="slate date" style="background:#0a1220;border:1px solid var(--line);color:var(--text);border-radius:8px;padding:6px 8px;font-size:13px">{options}</select><span style="margin-left:auto">published {published}</span></nav>
"""


def _inject(html: str, options_html: str, published: str, base: str) -> str:
    """Add the install hooks to <head>, the slate switcher to the app header and the service-worker
    registration before </body>. Pages rendered by the previous template (kept under docs/days/)
    get the switcher as a bar above their old header instead."""
    title = "<title>Early Goal Desk</title>"
    if title not in html or "</body>" not in html:
        raise RuntimeError("dashboard template changed: <title> or </body> not found")
    new_title = f"<title>{NAME} · NHL</title>"
    html = html.replace(title, new_title + "\n" + HEAD_EXTRA.format(base=base)
                        + head_tags(base, f"{NAME} · NHL", "NHL slate: first-5 and first-10 minute unders, period and full-game markets, simulated 100,000 times per game"), 1)
    # brand colours last in <head>, so they override the page's own stylesheet (older pages included)
    html = html.replace("</head>", "<style>" + BRAND_CSS + "</style>\n</head>", 1)
    brand = '<div class="brand">Early <span>Goal</span> Desk</div>'
    if brand in html:
        html = html.replace(brand, brand_html(base, "nhl", f"{base}nfl/"), 1)
    if '<span id="dayslot"></span>' in html:
        html = html.replace('<span id="dayslot"></span>', DAYSLOT.format(options=options_html, published=published), 1)
    elif '<div class="wrap">\n<header>' in html:
        html = html.replace('<div class="wrap">\n<header>', '<div class="wrap">\n' + LEGACY_BAR.format(options=options_html, published=published) + "<header>", 1)
    else:
        raise RuntimeError("dashboard template changed: no slot for the day switcher")
    return html.replace("</body>", SITE_SCRIPT.format(base=base) + "</body>", 1)


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
        # machine-readable companions: the CSV summary and the full payload
        for ext, src in (("csv", out_dir / f"summary-{m.group(1)}.csv"), ("json", out_dir / f"results-{m.group(1)}.json")):
            if src.exists():
                shutil.copy(src, days_dir / f"{m.group(1)}.{ext}")
    raws = sorted(days_dir.glob("*.raw.html"), reverse=True)[:keep_days]
    for stale in sorted(days_dir.glob("*.raw.html"), reverse=True)[keep_days:]:
        stale.unlink(missing_ok=True)
        for ext in (".html", ".csv", ".json"):
            (days_dir / stale.name.replace(".raw.html", ext)).unlink(missing_ok=True)
    local_days = [p.name.replace(".raw.html", "") for p in raws]
    days = sorted(set(local_days) | set(prior_days or []), reverse=True)[:keep_days]
    if not raws:
        raise SystemExit("nothing to publish: run `python -m earlygoal run` first")
    published = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    def nice(d: str) -> str:
        try:
            return datetime.strptime(d, "%Y-%m-%d").strftime("%a %b %d").replace(" 0", " ")
        except ValueError:
            return d

    today = slate_today()

    def label(d: str) -> str:
        k = (datetime.strptime(d, "%Y-%m-%d") - datetime.strptime(today, "%Y-%m-%d")).days
        return ("Today · " if k == 0 else ("Tomorrow · " if k == 1 else "")) + (nice(d).split(" ", 1)[1] if k in (0, 1) else nice(d))

    def options(selected: str, base: str) -> str:
        return "".join(
            f'<option value="{base}days/{d}.html" data-date="{d}" data-label="{nice(d)}" {"selected" if d == selected else ""}>{label(d)}</option>'
            for d in days
        )

    # the front page is today's slate; before the first build of a day it is the most recent one
    past_or_today = [d for d in local_days if d <= today]
    index_day = today if today in local_days else (past_or_today[0] if past_or_today else local_days[-1])

    for raw in raws:
        d = raw.name.replace(".raw.html", "")
        html = raw.read_text(encoding="utf-8")
        (days_dir / f"{d}.html").write_text(_inject(html, options(d, "../"), published, "../"), encoding="utf-8")
    latest = (days_dir / f"{index_day}.raw.html").read_text(encoding="utf-8")
    (site_dir / "index.html").write_text(_inject(latest, options(index_day, "./"), published, "./"), encoding="utf-8")
    (site_dir / "days.json").write_text(json.dumps({"days": days, "latest": index_day, "today": today, "published": published}, indent=1))
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
    copy_assets(site_dir)
    for size, name in ((192, "icon-192.png"), (512, "icon-512.png"), (180, "apple-touch-icon.png")):
        if not (site_dir / name).exists():
            _icon(size, site_dir / name)
    return site_dir
