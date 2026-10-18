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


# header, theme and navigation shared by every page (the desk app at docs/app/ uses the same values)
#
# One design system: navy ink, slate panels, gold for what is chosen or active, violet for links and secondary marks,
# Bricolage Grotesque for display type and IBM Plex Sans for text. The sport pages were drawn in an older palette;
# retheme() maps that palette onto this one, and BRAND_CSS (loaded last on every page) restyles the shared parts.
# One navigation: the same bar on every page (Desk, NFL, NBA, NHL, Props), at the bottom on a phone and as a rail on
# the left on a wide screen; each page's own sections sit under the header as one row of chips.
PALETTE = {
    "#070b12": "#0F1529", "#070c14": "#0F1529", "#0e141f": "#1A2340", "#131b29": "#212C4F", "#1d2838": "#29345A", "#27344a": "#36426C",
    "#0a1017": "#0B1022", "#0b111a": "#0B1022", "#0a1220": "#0B1022", "#e8eef7": "#EEF1F8", "#93a3ba": "#AEB8D0", "#5e6f88": "#7F8AAA",
    "#5ec8ff": "#B49BFF", "#3ddc84": "#39D98A", "#06121e": "#0F1529",
    "#162236": "#212C4F", "#bcd3f0": "#C9D0E4", "#1f6f8f": "#4A3F86",
    "rgba(94,200,255,": "rgba(180,155,255,", "rgba(120,200,255,": "rgba(180,155,255,", "rgba(61,220,132,": "rgba(57,217,138,", "rgba(7,11,18,": "rgba(15,21,41,",
    "family=Barlow+Condensed:wght@600;700;800&": "family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700;12..96,800&",
}


BRAND_START, BRAND_END = "/*gs-brand*/", "/*gs-brand-end*/"
_FONT_PX = re.compile(r"font-size:\s*(\d+(?:\.\d+)?)px")
_WIDE_CAPS = re.compile(r"letter-spacing:\s*\.(?:06|08|1|12|14)em")


def type_size(px: float) -> float:
    """The shared type scale: nothing under 12px; text up to 15px a step larger; headings and big numbers as drawn."""
    if px >= 15.5:
        return px
    if px < 10.5:
        return 12.0
    if px < 11.5:
        return 12.5
    return px + 1.5


def _retype(css: str) -> str:
    css = _FONT_PX.sub(lambda m: f"font-size:{type_size(float(m.group(1))):g}px", css)
    return _WIDE_CAPS.sub("letter-spacing:.03em", css)


def retheme(html: str) -> str:
    """A page drawn in the older style, in the shared one: the palette and display font, and the shared type scale
    (font sizes and the letter spacing of small capitals). The shared BRAND_CSS block is left exactly as written.
    No data is touched: only colour values and CSS font-size / letter-spacing declarations change."""
    for old, new in PALETTE.items():
        html = html.replace(old, new)
        if old.startswith("#"):
            html = html.replace(old.upper(), new)
    out, i = [], 0
    while True:
        a = html.find(BRAND_START, i)
        if a < 0:
            out.append(_retype(html[i:]))
            break
        b = html.find(BRAND_END, a)
        b = len(html) if b < 0 else b + len(BRAND_END)
        out.append(_retype(html[i:a]))
        out.append(html[a:b])
        i = b
    return "".join(out)


BRAND_CSS = """/*gs-brand*/
:root{--bg:#0F1529;--panel:#1A2340;--panel2:#212C4F;--line:rgba(190,205,240,.12);--line2:rgba(190,205,240,.22);--text:#EEF1F8;--muted:#B4BDD4;--dim:#8E99B9;
  --ice:#B49BFF;--gold:#E6B84F;--gold2:#F5D27A;--green:#39D98A;--amber:#F3B63A;--red:#FF6B6B;
  --display:'Bricolage Grotesque',system-ui,sans-serif;--body:'IBM Plex Sans',system-ui,-apple-system,sans-serif;--gnav:66px}
html{background:var(--bg)}
body{background:transparent !important;line-height:1.55;text-rendering:optimizeLegibility}
td,th,.num{font-variant-numeric:tabular-nums}
p,li{line-height:1.6}
body{padding-bottom:calc(var(--gnav) + env(safe-area-inset-bottom,0px) + 24px) !important}
body:before{content:'';position:fixed;inset:0;z-index:-1;pointer-events:none;background:radial-gradient(900px 520px at 0% -8%,rgba(180,155,255,.11),transparent 62%),radial-gradient(760px 460px at 105% -4%,rgba(230,184,79,.09),transparent 58%),var(--bg)}
a{color:var(--ice)}
/* header */
.app{background:rgba(15,21,41,.84);-webkit-backdrop-filter:saturate(1.4) blur(16px);backdrop-filter:saturate(1.4) blur(16px);border-bottom:1px solid var(--line)}
.app .row{padding:12px 0 8px;gap:12px}
.brand{display:flex;align-items:center;gap:11px;min-width:0;font-family:var(--body);font-size:15px;font-weight:400;letter-spacing:0;text-transform:none;line-height:1;white-space:nowrap}
.brand .home{display:flex;flex:0 0 auto}
.brand .logo{width:40px;height:40px;border-radius:12px;object-fit:cover;box-shadow:0 0 0 1px rgba(230,184,79,.35),0 6px 18px rgba(120,80,255,.22);flex:0 0 auto}
.brand .bt{display:block !important;font-family:var(--display);font-weight:800;font-size:21px;letter-spacing:-.01em;line-height:1;text-transform:none;background:none;-webkit-background-clip:border-box;background-clip:border-box;color:var(--text)}
.brand .bt b{color:var(--gold);font-weight:800;background:none}
.brand .bt small{display:block;font-family:var(--body);font-weight:500;font-size:13px;color:var(--gold2);opacity:.9;margin-top:4px;letter-spacing:0}
@media (max-width:420px){.brand .logo{width:36px;height:36px}.brand .bt{font-size:19px}}
.app .row{flex-wrap:nowrap}
.brand{flex:0 0 auto}
.hmeta{gap:8px;font-size:13px;color:var(--dim);min-width:0;flex:0 1 auto;justify-content:flex-end}
.hmeta select{background:var(--panel);border:1px solid var(--line2);color:var(--text);border-radius:999px;padding:7px 12px;font-size:14px;font-weight:600;min-height:38px;max-width:190px;min-width:0;text-overflow:ellipsis}
.hmeta .lbl2{color:var(--dim)}
.hmeta .install{display:none !important}
@media (max-width:640px){.hmeta .pub,.hmeta .lbl2{display:none}}
@media (max-width:420px){.hmeta select{max-width:136px;padding:7px 10px;font-size:13.5px}}
/* each page's own sections: one row of chips */
.tabs{gap:8px;margin:0 -16px;padding:2px 16px 10px;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tabs button{flex:0 0 auto;min-width:0;background:var(--panel);border:1px solid var(--line);color:var(--muted);border-radius:999px;padding:9px 15px;font-size:14px;font-weight:600;min-height:40px}
.tabs button.on{background:rgba(230,184,79,.12);border-color:rgba(230,184,79,.55);color:var(--gold2)}
@media (max-width:480px){.tabs button{padding:9px 14px;font-size:14px}}
/* what is selected is gold everywhere (chips, toolbars, settings); selected rows keep the violet tint */
.chips button.on,.toolbar button.on,.dset .chips2 label.on{background:rgba(230,184,79,.12) !important;border-color:rgba(230,184,79,.55) !important;color:var(--gold2) !important}
.chips button,.toolbar button,.bbbar select,.toolbar select{border-radius:999px}
select,input[type=search],input[type=text],input[type=number]{border-radius:10px}
.hmeta select,.bbbar select,.toolbar select{border-radius:999px}
/* primary actions are gold */
.bbl .combine,.combine{background:var(--gold) !important;color:#1b1402 !important;border-radius:12px}
/* type and surfaces */
h1,h2,h3{font-family:var(--display);letter-spacing:-.015em;text-transform:none}
h2{font-weight:700;font-size:21px}
h2 small{text-transform:none;letter-spacing:0}
.lead{color:var(--muted)}
/* wide tables scroll sideways inside their card instead of squeezing their columns together */
.tblwrap table.sk{width:max(100%,540px)}
/* in tables wider than a phone, the first column stays pinned while the numbers scroll under it */
.tblwrap table.sk tr>:first-child,.panel .tbl table:not(.kv) tr>:first-child{position:sticky;left:0;z-index:1;background:var(--panel);box-shadow:8px 0 8px -8px rgba(0,0,0,.7)}
.ptable table tr>:first-child{position:sticky;left:0;z-index:1;background:var(--bg);box-shadow:8px 0 8px -8px rgba(0,0,0,.7)}
@media (min-width:761px){.panel .tbl table tr>:first-child,.ptable table tr>:first-child,.tblwrap table.sk tr>:first-child{box-shadow:none}}
/* scanner rows: the book's name is shortened, and any label too long for its column is cut cleanly */
.srow .num .k{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
/* tab rows that scroll sideways fade at the right edge, so it is clear there is more */
@media (max-width:760px){.tabs{-webkit-mask-image:linear-gradient(90deg,#000 calc(100% - 28px),transparent);mask-image:linear-gradient(90deg,#000 calc(100% - 28px),transparent);padding-right:36px}}
/* label and value tables stack on a phone: the label on its own line, the value full width under it */
@media (max-width:560px){
  .panel table.kv,.panel table.kv tbody,.panel table.kv tr,.panel table.kv td{display:block;width:auto !important}
  .panel table.kv tr{border-top:1px solid var(--line);padding:10px 0}
  .panel table.kv tr:first-child{border-top:0;padding-top:2px}
  .panel table.kv td{border:0 !important;padding:0 !important}
  .panel table.kv td:first-child{white-space:normal;font-size:12.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--dim);margin-bottom:4px}
}
/* the desk's "looked at and declined" list: candidate and reason side by side, stacked on a phone */
table.decl{width:100%;min-width:0 !important;border-collapse:collapse;font-size:14.5px;margin:4px 0 14px}
table.decl th{text-align:left;font-size:12.5px;font-weight:700;letter-spacing:.04em;text-transform:uppercase;color:var(--dim);padding:6px 10px;border-bottom:1px solid var(--line)}
table.decl td{text-align:left;vertical-align:top;padding:10px;border-top:1px solid var(--line);white-space:normal;line-height:1.5}
table.decl td:first-child{width:36%;font-weight:600;color:var(--text)}
table.decl td:last-child{color:var(--muted)}
@media (max-width:560px){
  table.decl thead{display:none}
  table.decl,table.decl tbody,table.decl tr,table.decl td{display:block;width:auto !important}
  table.decl tr{border-top:1px solid var(--line);padding:10px 2px}
  table.decl tr:first-child{border-top:0}
  table.decl td{border:0;padding:0}
  table.decl td:first-child{margin-bottom:3px}
}
/* counts inside filter buttons stay readable */
button small{font-size:max(12px,.85em)}
/* a "why" note that opens on tap */
details.banner>summary{cursor:pointer;list-style:none}
details.banner>summary::-webkit-details-marker{display:none}
details.banner>summary .more{margin-left:6px;font-weight:600;text-decoration:underline;text-underline-offset:3px;opacity:.85;white-space:nowrap}
details.banner[open]>summary .more{display:none}
details.banner>p{margin:8px 0 0}
/* subtitles under a number wrap instead of being cut off with an ellipsis */
.nc .hd .when{white-space:normal;min-width:0;text-align:right}
.board .s,.board .mu,.mb .s,.mb .k,.srow .sel .t,.srow .num .t,.srow .n-bt .k,.atd li .nm,.bb .ti .t,.bb .three .s,.gcard .lines .s{white-space:normal !important;overflow:visible !important;text-overflow:clip !important}
.srow .n-bt .k{flex:0 0 auto}
/* the big percentages in two-column market boxes fit beside their labels on a phone */
@media (max-width:480px){.mb .row .p{font-size:17px}.mb .row{gap:4px}}
/* the refresh button sits above the navigation bar (pages whose header has no room for it) */
#fab{bottom:calc(var(--gnav) + 16px + env(safe-area-inset-bottom,0px)) !important;border-color:rgba(230,184,79,.55) !important;color:var(--gold2) !important}
/* on every page with the shared header it sits in the header row instead, beside the date, so it never covers numbers */
#fab.hfab{position:static !important;order:9;flex:0 0 auto;width:38px;height:38px;min-height:38px;padding:0;line-height:36px;font-size:17px;box-shadow:none;background:var(--panel);border:1px solid var(--line2) !important;color:var(--muted) !important}
#fab.hfab:hover,#fab.hfab:focus-visible{color:var(--gold2) !important;border-color:rgba(230,184,79,.55) !important}
@media (max-width:380px){.hmeta{gap:6px}.hmeta select{max-width:128px;padding:7px 8px;font-size:13px}}
/* one navigation for the whole app */
.gnav{position:fixed;left:0;right:0;bottom:0;z-index:40;height:calc(var(--gnav) + env(safe-area-inset-bottom,0px));padding-bottom:env(safe-area-inset-bottom,0px);background:rgba(13,18,36,.9);-webkit-backdrop-filter:saturate(1.4) blur(16px);backdrop-filter:saturate(1.4) blur(16px);border-top:1px solid var(--line);display:flex;margin:0}
.gnav a{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;color:var(--dim);font-family:var(--body);font-size:12px;font-weight:600;letter-spacing:0;text-transform:none;text-decoration:none;min-width:0}
.gnav a .ic{width:52px;height:30px;border-radius:999px;display:flex;align-items:center;justify-content:center;transition:background .25s}
.gnav svg{width:22px;height:22px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
.gnav a[aria-current=page]{color:var(--gold2)}
.gnav a[aria-current=page] .ic{background:rgba(230,184,79,.12)}
.gnav a:focus-visible{outline:2px solid var(--gold);outline-offset:-4px;border-radius:12px}
@media (min-width:860px) and (min-height:520px){
  body{padding-left:92px !important;padding-bottom:28px !important}
  .detwrap{max-width:calc(min(100vw - 92px,1240px) - 48px) !important}
  .gnav{top:0;bottom:0;right:auto;width:84px;height:auto;flex-direction:column;justify-content:flex-start;padding-top:calc(env(safe-area-inset-top,0px) + 92px);border-top:0;border-right:1px solid var(--line)}
  .gnav a{flex:0 0 auto;padding:12px 0}
  #fab:not(.hfab){bottom:24px !important}
}
/*gs-brand-end*/
"""

ICONS = {
    "desk": '<path d="M3 8a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v1.5a2.5 2.5 0 0 0 0 5V16a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-1.5a2.5 2.5 0 0 0 0-5z"/><path d="M14 6v12" stroke-dasharray="2 2"/>',
    "nfl": '<path d="M4.5 19.5c-1.4-4.6 1-10.3 5.3-13.1C13 4.3 17 4 19.5 4.5c1.4 4.6-1 10.3-5.3 13.1-3.2 2.1-7.2 2.4-9.7 1.9z"/><path d="M9 15l6-6M10.5 10.5l1.5 1.5M12 9l1.5 1.5M9 12l1.5 1.5"/>',
    "nba": '<circle cx="12" cy="12" r="8.5"/><path d="M3.5 12h17M12 3.5v17M6 6c2.5 2.2 2.5 9.8 0 12M18 6c-2.5 2.2-2.5 9.8 0 12"/>',
    "nhl": '<ellipse cx="12" cy="9" rx="7" ry="3"/><path d="M5 9v5c0 1.7 3.1 3 7 3s7-1.3 7-3V9"/>',
    "props": '<circle cx="12" cy="8" r="3.5"/><path d="M5 20c.8-3.6 3.6-5.5 7-5.5s6.2 1.9 7 5.5"/>',
}
SECTION_LABEL = {"desk": "Desk", "nfl": "NFL", "nba": "NBA", "nhl": "NHL", "props": "Props"}
SECTION_TITLE = {"nhl": "NHL", "props": "NHL props", "nfl": "NFL", "nba": "NBA", "desk": "Research desk"}


def gnav_html(hrefs: dict, current: str) -> str:
    """The navigation bar every page shares: Desk, NFL, NBA, NHL, Props (the current one highlighted)."""
    out = []
    for key in ("desk", "nfl", "nba", "nhl", "props"):
        cur = ' aria-current="page"' if key == current else ""
        out.append(f'<a href="{hrefs[key]}"{cur}><span class="ic"><svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[key]}</svg></span>{SECTION_LABEL[key]}</a>')
    return '<nav class="gnav" aria-label="Gill Sports sections">' + "".join(out) + "</nav>"


def section_hrefs(root: str, sport: str, other_href: str, props_href: str | None = None, nfl_href: str | None = None, nba_href: str | None = None) -> dict:
    """Links to every section from a page whose path to the site root is `root` (\"./\", \"../\" or \"../../\")."""
    return {"desk": root + "app/",
            "nfl": root + "nfl/" if sport == "nfl" else (nfl_href or (other_href if sport == "nhl" else root + "nfl/")),
            "nba": root + "nba/" if sport == "nba" else (nba_href or root + "nba/"),
            "nhl": root if sport == "nhl" else other_href,
            "props": root + "props/"}


def brand_html(root: str, sport: str, other_href: str, props_href: str | None = None, nfl_href: str | None = None, nba_href: str | None = None) -> str:
    """The header brand (mark, wordmark, the section's name) and the shared navigation bar. `sport` is the current
    section ("nhl", "props", "nfl" or "nba"); every link is built from `root` (this page's path to the site root),
    so it works from a section's front page (root "../") and from its archive pages (root "../../") alike."""
    return (f'<div class="brand"><a class="home" href="{root}app/" aria-label="{NAME} desk"><img class="logo" src="{root}brand-mark.png?v={ASSET_VERSION}" alt="" width="40" height="40"></a>'
            f'<span class="bt">Gill <b>Sports</b><small>{SECTION_TITLE.get(sport, sport.upper())}</small></span></div>')


_FAB = re.compile(r'<button id="fab"(?![^>]*\bhfab\b)([^>]*)>(.*?)</button>[ \t]*\n?', re.S)


def _fab_to_header(html: str) -> str:
    """Move the floating refresh button into the header row, beside the date picker. Its handlers find it by id, so
    they keep working; a page without the shared header keeps the floating button."""
    m, j = _FAB.search(html), html.find('<div class="hmeta">')
    if not m or j == -1:
        return html
    btn = f'<button id="fab" class="hfab"{m.group(1)}>{m.group(2)}</button>'
    html = html[:m.start()] + html[m.end():]
    j = html.find('<div class="hmeta">')
    k = html.find("</div>", j)
    return html[:k] + btn + html[k:]


def finish_page(html: str, root: str, sport: str, other_href: str, props_href: str | None = None, nfl_href: str | None = None, nba_href: str | None = None) -> str:
    """Every page's last step: the shared palette, and the shared navigation bar just before </body> (outside the
    blurred header, which would otherwise trap a fixed bar inside it)."""
    html = retheme(html)
    html = _fab_to_header(html)
    if 'class="gnav"' not in html and "</body>" in html:
        nav = gnav_html(section_hrefs(root, sport, other_href, props_href, nfl_href, nba_href), sport)
        i = html.rindex("</body>")
        html = html[:i] + nav + "\n" + html[i:]
    return html


__all__ = ["NAME", "SHORT", "site_url", "copy_assets", "head_tags", "brand_html", "gnav_html", "section_hrefs", "retheme", "finish_page", "BRAND_CSS", "PALETTE", "repository"]
