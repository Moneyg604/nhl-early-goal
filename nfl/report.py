"""NFL week page: one self-contained HTML file in the same design system as the NHL slate.

Tabs: Week (every game with all nine markets, live scores), Research (dossiers and measured factors),
Picks (leans per market and a slip builder), Results (graded leans, track record), About (method and the
walk-forward validation). The page prices any line from the stored distributions, so the price check
works for the exact line and odds the book shows.
"""
from __future__ import annotations

import json

from earlygoal.brand import BRAND_CSS, brand_html
from earlygoal.report import TEMPLATE as _NHL

BASE_CSS = _NHL[_NHL.index("<style>") + len("<style>"):_NHL.index("</style>")]

NFL_CSS = r"""
.hmeta .pub{color:var(--dim)}
@media (max-width:640px){.hmeta .pub,.hmeta .lbl2{display:none}}
@media (max-width:480px){.brand .bt{display:none}.sport{margin-left:0}}
.mb .k .qtag{vertical-align:1px}
.sport{display:inline-flex;border:1px solid var(--line2);border-radius:999px;overflow:hidden;margin-left:10px;vertical-align:middle}
.sport a{font-family:var(--body);font-size:11.5px;font-weight:700;letter-spacing:.06em;padding:4px 10px;color:var(--muted);text-decoration:none}
.sport a.on{background:var(--ice);color:#06121e}
.ncards{display:grid;grid-template-columns:repeat(auto-fill,minmax(520px,1fr));gap:12px}
@media (max-width:600px){.ncards{grid-template-columns:1fr}}
.nc{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:12px 14px;min-width:0}
.nc .hd{display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
.nc .hd .mu{font-family:var(--display);font-size:24px;font-weight:700;letter-spacing:.02em}
.nc .hd .when{font-size:12px;color:var(--muted);white-space:nowrap}
.nc .gl{display:flex;flex-wrap:wrap;gap:3px 12px;margin:4px 0 8px;font-size:12px;color:var(--muted)}
.nc .gl b{color:var(--text);font-weight:600}
.nc h5{margin:10px 0 5px;font-size:10.5px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);font-weight:700}
.g3{display:grid;grid-template-columns:repeat(3,1fr);gap:6px}
.g2{display:grid;grid-template-columns:1fr 1fr;gap:6px}
@media (max-width:420px){.g3{grid-template-columns:1fr 1fr}.g3>div:last-child{grid-column:span 2}}
@media (max-width:520px){.g2{grid-template-columns:1fr}}
.mb{background:#0a1017;border:1px solid var(--line);border-radius:12px;padding:8px 10px;min-width:0;position:relative}
.mb .k{display:block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin-bottom:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mb .row{display:flex;justify-content:space-between;align-items:baseline;gap:6px;font-size:13px;white-space:nowrap}
.mb .row .p{font-family:var(--display);font-size:19px;font-weight:700}
.mb .s{display:block;font-size:11px;color:var(--muted);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.mb .res{position:static;margin-left:4px;font-size:10px;line-height:15px;padding:0 4px}
.mb.o-hit{background:rgba(61,220,132,.08);border-color:rgba(61,220,132,.35)}.mb.o-miss{background:rgba(255,107,107,.08);border-color:rgba(255,107,107,.35)}.mb.o-tie{background:rgba(243,182,58,.08);border-color:rgba(243,182,58,.35)}
.atd{display:grid;grid-template-columns:1fr 1fr;gap:6px}
@media (max-width:480px){.atd{grid-template-columns:1fr}}
.atd ol{list-style:none;margin:0;padding:0;background:#0a1017;border:1px solid var(--line);border-radius:12px}
.atd li{display:flex;justify-content:space-between;gap:6px;padding:5px 9px;border-top:1px solid var(--line);font-size:12.5px;white-space:nowrap}
.atd li:first-child{border-top:0;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.atd li .nm{overflow:hidden;text-overflow:ellipsis}.atd li .pp{font-weight:700}.atd li .pos{color:var(--dim);font-size:11px;margin-left:4px}
.atd li.hit{background:rgba(61,220,132,.08)}
.qtag{display:inline-block;font-size:9.5px;font-weight:800;border-radius:4px;padding:0 4px;margin-left:4px;background:rgba(243,182,58,.14);color:var(--amber)}
.pc{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;align-items:end}
.pc label{display:flex;flex-direction:column;gap:4px;font-size:11.5px;color:var(--muted)}
.pc select,.pc input{background:#0a1017;border:1px solid var(--line2);color:var(--text);border-radius:8px;padding:7px 9px;font-size:14px;font-family:inherit;min-width:0;width:100%}
.pcout{margin-top:10px;display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px}
.pcout div{background:rgba(7,11,18,.5);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.pcout .k{display:block;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}.pcout .v{font-family:var(--display);font-size:22px;font-weight:700}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chips button{background:var(--panel);border:1px solid var(--line2);color:var(--muted);border-radius:999px;padding:6px 12px;font-size:12.5px;font-family:inherit;cursor:pointer}
.chips button.on{border-color:var(--ice);color:var(--ice)}
.cmp td:nth-child(2),.cmp td:nth-child(3){text-align:right}
.verd{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.06em;border-radius:5px;padding:1px 6px;text-transform:uppercase;white-space:nowrap}
.verd.beats{color:var(--green);background:rgba(61,220,132,.12)}.verd.marginal{color:var(--amber);background:rgba(243,182,58,.12)}.verd.none{color:var(--red);background:rgba(255,107,107,.12)}
.leg2{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 0;border-top:1px dashed var(--line);font-size:13.5px;cursor:pointer}
.leg2:first-child{border-top:0}
.leg2.on{color:var(--ice)}
.leg2 .p{font-family:var(--display);font-size:20px;font-weight:700;color:var(--green)}
.mini{font-size:11.5px;color:var(--dim)}
.scanbar{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;align-items:end}
.scanbar label{display:flex;flex-direction:column;gap:4px;font-size:11.5px;color:var(--muted)}
.scanbar select,.scanbar input{background:#0a1017;border:1px solid var(--line2);color:var(--text);border-radius:8px;padding:7px 9px;font-size:13.5px;font-family:inherit;min-width:0;width:100%}
.scanbar .chips{grid-column:1/-1}
.scan{display:flex;flex-direction:column;border:1px solid var(--line);border-radius:12px;overflow:hidden}
.srow{display:grid;grid-template-columns:34px minmax(0,2.6fr) repeat(4,minmax(0,.8fr)) minmax(0,1.2fr);gap:8px;align-items:center;padding:8px 10px;border-top:1px solid var(--line);cursor:pointer;font-size:13px}
.srow:first-child{border-top:0}.srow:hover{background:rgba(94,200,255,.04)}.srow.on{background:rgba(94,200,255,.08);box-shadow:inset 3px 0 0 var(--ice)}
.srow .sel{min-width:0}.srow .sel b{font-weight:600}.srow .sel .t{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.srow .num{display:flex;flex-direction:column;min-width:0;font-variant-numeric:tabular-nums;white-space:nowrap}
.srow .num .k{font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}.srow .num .t{overflow:hidden;text-overflow:ellipsis}
@media (max-width:760px){.srow{grid-template-columns:28px repeat(4,minmax(0,1fr));row-gap:6px;column-gap:6px}.srow .gr{grid-row:1}.srow .sel{grid-column:2/-1;grid-row:1}
 .srow .n-win{grid-column:2;grid-row:2}.srow .n-fair{grid-column:3;grid-row:2}.srow .n-book{grid-column:4;grid-row:2}.srow .n-ev{grid-column:5;grid-row:2}.srow .n-bt{grid-column:2/-1;grid-row:3;flex-direction:row;gap:6px;align-items:baseline}}
.gr{display:inline-flex;align-items:center;justify-content:center;width:26px;height:26px;border-radius:7px;font-family:var(--display);font-weight:800;font-size:16px}
.gr.sm{width:18px;height:18px;font-size:12px;border-radius:5px;vertical-align:middle}
.gr.gS{background:rgba(94,200,255,.18);color:var(--ice);border:1px solid var(--ice)}.gr.gA{background:rgba(61,220,132,.15);color:var(--green)}.gr.gB{background:rgba(61,220,132,.07);color:#9fe7c0}
.gr.gC{background:rgba(243,182,58,.12);color:var(--amber)}.gr.gD{background:rgba(255,107,107,.1);color:var(--red)}
.gradehelp summary{cursor:pointer;font-size:13px}.gradehelp p{font-size:13px}
.bbhead{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline;margin:2px 0 10px;font-size:12.5px;color:var(--muted)}
.bbhead b{color:var(--text)}
.bbbar{display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:center;margin-bottom:10px}
.bbbar .chips{grid-column:1/-1}
.bbbar select{min-width:0;width:100%;background:#0a1017;border:1px solid var(--line2);color:var(--text);border-radius:8px;padding:6px 9px;font-size:13px;font-family:inherit}
.bbl{display:flex;flex-direction:column;gap:8px}
.bb{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:10px 12px;min-width:0}
.bb.good{border-color:rgba(61,220,132,.45);background:linear-gradient(180deg,rgba(61,220,132,.06),var(--panel) 60%)}
.bb.insl{box-shadow:inset 3px 0 0 var(--ice)}
.bb .top{display:flex;gap:10px;align-items:flex-start}
.bb .rk{flex:0 0 auto;width:30px;height:30px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-family:var(--display);font-weight:800;font-size:17px;background:var(--panel2);color:var(--muted)}
.bb.good .rk{background:rgba(61,220,132,.16);color:var(--green)}
.bb .ti{flex:1 1 auto;min-width:0}
.bb .ti b{display:block;font-size:15px;font-weight:600;line-height:1.25}
.bb .ti .t{display:block;font-size:11.5px;color:var(--dim);margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bb .evb{flex:0 0 auto;text-align:right;font-family:var(--display);font-weight:800;font-size:22px;line-height:1}
.bb .evb .k{display:block;font-family:var(--body);font-size:9.5px;font-weight:700;letter-spacing:.08em;color:var(--dim);margin-top:3px}
.bb .nums{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px;margin-top:8px}
.bb .nums div{background:#0a1017;border:1px solid var(--line);border-radius:9px;padding:5px 8px;min-width:0}
.bb .nums .k{display:block;font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.bb .nums .v{font-family:var(--display);font-size:18px;font-weight:700;white-space:nowrap}
.bb .nums .v .t{font-family:var(--body);font-size:11px;font-weight:500;color:var(--muted);margin-left:3px}
@media (max-width:420px){.bb .nums{grid-template-columns:repeat(2,minmax(0,1fr))}}
.bb .why{margin-top:7px;font-size:12px;color:var(--muted);line-height:1.45}
.bb .why b{color:var(--text);font-weight:600}
.bb details{margin-top:6px;flex:1 1 auto;min-width:0}.bb summary{cursor:pointer;font-size:12px;color:var(--ice)}
.bb .bt{overflow-x:auto;max-width:100%}
body[data-tab="best"] #banner{display:none}
.bb .three{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:8px}
.bb .three div{background:#0a1017;border:1px solid var(--line);border-radius:9px;padding:6px 9px;min-width:0}
.bb .three .k{display:block;font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.bb .three .v{display:block;font-family:var(--display);font-size:19px;font-weight:700;white-space:nowrap;font-variant-numeric:tabular-nums}
.bb .three .v.mid{color:var(--amber)}.bb .three .v.pos,.bb .evb.pos,.bb .v.pos,td.pos{color:var(--green)}.bb .three .v.neg,.bb .evb.neg,.bb .v.neg,td.neg{color:var(--red)}
.bb .three .s{display:block;font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
@media (max-width:480px){.bb .three{grid-template-columns:1fr}.bb .three .s{white-space:normal}}
.bb .chk{display:flex;flex-wrap:wrap;gap:4px;margin-top:8px}
.bb .chk .c{font-size:10.5px;border-radius:6px;padding:2px 7px;background:var(--panel2);color:var(--muted);white-space:nowrap}
.bb .chk .c.ok{color:var(--green);background:rgba(61,220,132,.1)}.bb .chk .c.bad{color:var(--red);background:rgba(255,107,107,.1)}
.bb .chkl{margin-top:6px;font-size:12px}.bb .chkl ul{margin:4px 0 0;padding-left:16px;display:flex;flex-direction:column;gap:3px}.bb .chkl li.ok{color:var(--green)}.bb .chkl li.bad{color:var(--red)}.bb .chkl li.na{color:var(--muted)}.bb .chkl li b{color:var(--text)}
.bb .warn{margin-top:5px;font-size:12px;color:var(--amber)}
.bb .brow{display:flex;align-items:flex-start;gap:8px;margin-top:8px}
.bb details.books{margin-top:0}
.bb details.books>summary{display:inline-block;background:var(--panel2);border:1px solid var(--line2);border-radius:999px;padding:5px 11px;font-size:12.5px;list-style:none;color:var(--ice)}
.bb details.books>summary::-webkit-details-marker{display:none}
.bb details.books>summary::before{content:'▸ ';color:var(--ice)}
.bb details.books[open]>summary::before{content:'▾ '}
.bb details.books[open]>summary{border-color:var(--ice)}
.bb .rs{margin:8px 0 0;padding-left:18px;font-size:12.5px;color:var(--muted);display:flex;flex-direction:column;gap:3px}.bb .rs li::marker{color:var(--ice)}
.bb .proj{margin-top:8px;font-size:12.5px;color:var(--text)}.bb .proj span{color:var(--muted)}
.bb .risk{margin-top:7px;font-size:12.5px;color:#ffd37a}.bb .risk b{color:#ffe3a3}
.bb .pers{margin-top:5px;font-size:12px;color:var(--muted)}.bb .pers b{color:var(--text)}
.bb .fm{margin-top:8px}.bb .fm p{margin:4px 0;font-size:12px;color:var(--muted);font-variant-numeric:tabular-nums}
.bb .lim{margin-top:6px;font-size:12px;color:var(--amber)}
.bb .stamps{margin-top:6px;font-size:11.5px;color:var(--dim)}
.bb.parlay{border-color:var(--ice)}
.bb td.lbl{white-space:normal;min-width:160px;text-align:left}.bb.parlay td.lbl{min-width:200px}
.bbl .combine{background:var(--ice);color:#06121e;border:0;border-radius:10px;padding:10px 16px;font-size:14px;font-weight:700;font-family:inherit;cursor:pointer}
.bbl h2{margin:14px 0 0}
.bbl .note{margin:6px 0;font-size:12px;color:var(--dim);max-width:72ch}
.bbl .empty{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin:0}
.bbl .bt{overflow-x:auto;max-width:100%}
.bbl table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px;font-variant-numeric:tabular-nums}
.bbl th,.bbl td{padding:4px 6px;border-top:1px solid var(--line);text-align:right;white-space:nowrap}
.bbl th{color:var(--dim);font-weight:600;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase}
.bbl th:first-child,.bbl td:first-child,.bbl td.lbl,.bbl th.lbl{text-align:left}
.bb .brow .addb{white-space:nowrap;flex:0 0 auto}
.bbl tr.dk td{color:var(--ice);font-weight:600}
.bbl .tdb th:nth-child(2),.bbl .tdb td:nth-child(2){text-align:left}
.bbl .tdb tr.g td{background:var(--panel2);color:var(--text);font-weight:600;text-align:left}
.bbl .cf.medium{color:var(--amber);background:rgba(243,182,58,.12)}
#best .stale{margin:0 0 10px;border:1px solid rgba(243,182,58,.5);background:rgba(243,182,58,.08);color:#ffd37a;border-radius:12px;padding:10px 14px;font-size:13px;max-width:72ch}
#best .stale b{color:#ffe3a3}
#best>.note{margin:-4px 0 10px;font-size:12px;color:var(--dim);max-width:none}
.bbbar{grid-template-columns:1fr 1fr 1fr}
@media (max-width:600px){.bbbar{grid-template-columns:1fr 1fr}}
.bbhow{font-size:12.5px;color:var(--muted);margin:0 0 10px}.bbhow summary{cursor:pointer;color:var(--ice)}.bbhow p{margin:6px 0;max-width:72ch}
@media (max-width:480px){.tabs button{flex:0 0 auto;padding:8px 9px}}
.bb table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}.bb th,.bb td{padding:3px 6px;border-top:1px solid var(--line);text-align:right;white-space:nowrap}
.bb th:first-child,.bb td:first-child{text-align:left}.bb tr.dk td{color:var(--ice);font-weight:600}
.cf{display:inline-block;font-size:9.5px;font-weight:800;letter-spacing:.06em;border-radius:5px;padding:1px 6px;text-transform:uppercase;vertical-align:1px}
.cf.high{color:var(--green);background:rgba(61,220,132,.12)}.cf.medium{color:var(--amber);background:rgba(243,182,58,.12)}.cf.low{color:var(--red);background:rgba(255,107,107,.12)}
.bb.desk{border-color:rgba(243,182,58,.55)}.bb.desk .rk{background:rgba(243,182,58,.16);color:#ffd37a}
.bb .gr{display:inline-block;font-family:var(--display);font-weight:800;font-size:13px;border-radius:6px;padding:1px 7px;margin-left:6px;vertical-align:1px}
.bb .gr.A{color:var(--green);background:rgba(61,220,132,.14)}.bb .gr.B{color:var(--amber);background:rgba(243,182,58,.14)}.bb .gr.C{color:var(--muted);background:var(--panel2)}
.bb .res{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.06em;border-radius:5px;padding:1px 6px;text-transform:uppercase;margin-left:6px;vertical-align:1px}
.bb .res.hit{color:var(--green);background:rgba(61,220,132,.14)}.bb .res.miss{color:var(--red);background:rgba(255,107,107,.14)}.bb .res.tie,.bb .res.void{color:var(--amber);background:rgba(243,182,58,.14)}.bb .res.live{color:var(--ice);background:rgba(120,200,255,.12)}
.bb .deskr{margin-top:8px;border:1px solid rgba(243,182,58,.35);background:rgba(243,182,58,.05);border-radius:10px;padding:8px 10px}
.bb .deskr h4{margin:0 0 4px;font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#ffd37a}
.bb .deskr p{margin:4px 0;font-size:12.5px;color:var(--text)}.bb .deskr ul{margin:4px 0 0;padding-left:18px;font-size:12.5px;color:var(--muted);display:flex;flex-direction:column;gap:3px}
.bb .deskr .ar li{font-variant-numeric:tabular-nums}.bb .deskr .pr li::marker{color:var(--green)}.bb .deskr .ri li::marker{color:var(--red)}
.bb .deskr .src{margin-top:6px;font-size:11.5px;color:var(--dim)}.bb .deskr .src a{color:var(--ice)}
.bbl .deskhead{background:var(--panel);border:1px solid rgba(243,182,58,.4);border-radius:14px;padding:12px 14px;margin:0 0 10px}
.bbl .deskhead h2{margin:0 0 4px;font-size:16px}.bbl .deskhead p{margin:4px 0;font-size:12.5px;color:var(--muted);max-width:none}
.bbl .deskhead .st{font-size:11.5px;color:var(--dim)}
.bbl .gnotes summary{cursor:pointer;color:var(--ice);font-size:12.5px}.bbl .gnotes ul{margin:4px 0 8px;padding-left:18px;font-size:12px;color:var(--muted)}
.bbsep{margin:14px 0 6px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--dim);font-weight:700}
.bb .addb{margin-left:auto;background:var(--panel2);border:1px solid var(--line2);color:var(--ice);border-radius:8px;padding:3px 9px;font-size:11.5px;font-family:inherit;cursor:pointer}
.slip .lg{display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);border-radius:8px;padding:3px 8px}.slip .lg a{font-size:11px;color:var(--dim)}
"""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Gill Sports · NFL</title>
<meta name="description" content="NFL week __WEEK__: moneyline, spread, totals, half totals, team field goals, quarterback passing and anytime touchdown probabilities from a drive-level simulation">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>__CSS__</style>
</head>
<body>
<button id="fab" title="Refresh live scores" aria-label="Refresh live scores">↻</button>
<div class="app"><div class="wrap">
  <div class="row">
    __BRAND__
    <div class="hmeta"><span id="dayslot"></span></div>
  </div>
  <nav class="tabs" id="tabs">
    <button data-tab="best" class="on">Best bets</button>
    <button data-tab="week">Week</button>
    <button data-tab="scanner">Scanner</button>
    <button data-tab="research">Research</button>
    <button data-tab="results">Results</button>
    <button data-tab="about">About</button>
  </nav>
</div></div>

<div class="wrap">
<div id="banner"></div>
__STATIC__

<section class="tab on" id="tab-best">
  <p class="lead" style="margin-bottom:4px">Every DraftKings market for this week's games, ranked by how likely the bet is to win. Each card shows three things: the win chance, how solid the evidence is, and whether DraftKings' price is attractive, fair or poor. The bot's picks come first: the bets a careful analyst would take, by category, with a button that combines them into the top six.</p>
  <details class="bbhow"><summary>How the bets are ranked</summary>
   <p><b>Win chance.</b> Starts from the whole market: every book's price with its margin removed, moved onto DraftKings' line, with Pinnacle counting double. The simulation (100,000 drive-by-drive games per matchup, built from matchups, pace, quarterbacks, usage, injuries, rest and weather) then moves that chance by up to 4 points on player props and half totals, less when the two disagree by more than 10 points and not at all past 20. Game lines (moneyline, spread, total) take the market's chance unchanged, because in the walk-forward test the simulation did not beat the closing line.</p>
   <p><b>Evidence confidence</b> rates the quality of the inputs, not the chance of winning: it counts the books pricing the market, how closely the simulation and the market agree, how much current-season data stands behind both teams, and flags (a quarterback change, a questionable player, a one-sided price, a player with no independent projection).</p>
   <p><b>Bot's picks</b> runs an analyst's checks on every bet and keeps the best per category: this season's form against the line, the opponent's rank for that stat, the game script the spread implies, receivers or blockers out, workload shifts from teammates out, wind, the quarterback situation, the price's age, and how far the simulation sits from the market. A failed hard check (form pointing the other way, a questionable player, a non-starter, a 15-point model/market gap) removes the bet; soft checks move its score. "Combine into the top 6" takes the six highest-scoring legs across the lists, one per game, at real DraftKings prices between 1.35 and 2.20; anytime touchdowns are never in the lists (they have their own board).</p>
   <p><b>Price.</b> Attractive: DraftKings pays at least 2% more than the win chance justifies (5% for anytime touchdowns, whose margin has to be assumed). Fair: within 3% of fair. Poor: worse than that. Unreliable: too few books, a long shot past +700, or books more than 25 points apart. Kicker field goals and alternate lines come from the simulation only (DraftKings' prices for them are not in the feed), so those cards show fair odds to compare by hand. Attractively priced bets lock at kickoff and are graded in the Results tab.</p></details>
  <div id="best"></div>
</section>

<section class="tab" id="tab-week">
  <div class="status" id="status"></div>
  <div class="livebar" id="livebar"></div>
  <div class="board" id="board"></div>
  <div class="panel" id="pricecheck"></div>
  <div class="toolbar" id="toolbar"></div>
  <div class="ncards" id="cards"></div>
</section>

<section class="tab" id="tab-research">
  <p class="lead">What was measured before the numbers were produced: each team's drive results against what the league scores from the same situations, pace, passing, kicking, the quarterback, the injury report and the context of the game. Sample sizes are shown; every multiplier is shrunk toward the league in proportion to how little data stands behind it.</p>
  <div class="panel" id="sources"></div>
  <div class="panel" id="factors"></div>
  <h2>Game dossiers</h2>
  <div id="dossiers"></div>
</section>

<section class="tab" id="tab-scanner">
  <p class="lead">Every selection the model prices, in every market, nothing hidden. The "win" column is the simulation's own number; the EV column judges the price on the market's fair chance (all books, no vig) wherever DraftKings lists the bet. The likeliest bet is not the best bet: start from the Best bets tab.</p>
  <details class="panel gradehelp"><summary><b>How the grades work</b></summary>
   <p>Grades are expected value at the book's price, judged on the market's fair chance. The bar is +2% (+5% for anytime touchdowns, whose one-sided prices need an assumed margin): <b>S</b> clears it by 3 points or more, <b>A</b> clears it, <b>B</b> positive but under the bar, or a long shot or thin market that is never listed, <b>C</b> 0 to -4%, <b>D</b> worse than -4%. A selection with no market consensus (the book does not list it, or too few books do) is judged on the model alone and never graded above C: in the walk-forward test the model did not beat the closing lines, and in 2026 it under-projected high-volume quarterbacks by about 20 yards. No price means value unknown (C).</p>
   <p>The "backtest" column shows how often selections the model rated at about the same probability actually won over 2023 to 2025, against each player's recent average (not a sportsbook line).</p></details>
  <div class="panel" id="slip"></div>
  <div class="panel" id="scanner"></div>
  <h2>Best bet per market <small>the good DraftKings bets, graded in the track record</small></h2>
  <div class="groups" id="picks"></div>
</section>

<section class="tab" id="tab-results">
  <div class="panel" id="tracker"></div>
  <div class="panel" id="wkresults"></div>
  <div class="panel" id="track"></div>
  <div class="panel"><h3>All weeks</h3><div class="daylist" id="weeklist"></div></div>
</section>

<section class="tab" id="tab-about">
  <div class="panel" id="validation"></div>
  <div class="panel" id="method"></div>
  <footer id="foot"></footer>
</section>
</div>

<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
(function(){ const s=document.getElementById('static'); if(s) s.remove(); })();
const P = JSON.parse(document.getElementById('payload').textContent);
const M = P.meta || {}; const V = P.validation || null;
const BASE = window.NFL_BASE || './';
const pct = (x,d=1) => x==null ? '–' : (x*100).toFixed(d)+'%';
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const amer = a => a==null ? '' : (a>0?'+':'')+Math.round(a);
const dec2am = d => d==null ? '' : (d>=2 ? '+'+Math.round((d-1)*100) : '-'+Math.round(100/(d-1)));
const fair = p => p>0 ? (1/p) : null;
const fmtOdds = d => d==null ? '–' : `${d.toFixed(2)} <span class="t">${dec2am(d)}</span>`;
const parseOdds = s => { s=String(s||'').trim(); if(!s) return null; const v=parseFloat(s); if(isNaN(v)) return null;
  if (/^[+-]/.test(s) || Math.abs(v)>=100) return v>0 ? 1+v/100 : 1+100/(-v); return v>1 ? v : null; };
const tierTag = t => `<span class="tier ${t}" title="${t==='A'?'established starters, enough games this season, market line known':(t==='B'?'a quarterback change or thin current-season data':'starter without NFL passing data, or no market line')}">${t}</span>`;
const byId = {}; P.games.forEach(g=>byId[g.game_id]=g);
const kickoff = g => g.kickoff_utc ? new Date(g.kickoff_utc.replace('Z',':00Z')) : null;
const whenTxt = g => { const k=kickoff(g); if(!k) return esc(g.date); return k.toLocaleString('en-US',{weekday:'short',hour:'numeric',minute:'2-digit'}); };
const slotOf = g => { const k=kickoff(g); if(!k) return 'other'; const et=new Date(k.toLocaleString('en-US',{timeZone:'America/New_York'})); const d=et.getDay(), h=et.getHours()+et.getMinutes()/60;
  if(d===4) return 'thu'; if(d===1) return 'mon'; if(d===0 && h<12) return 'intl'; if(d===0 && h<15) return 'early'; if(d===0 && h<19) return 'late'; if(d===0) return 'night'; return 'other'; };
const SLOTS = {all:'All', thu:'Thursday', intl:'Morning', early:'Sunday 1 pm', late:'Sunday 4 pm', night:'Sunday night', mon:'Monday', other:'Other'};

// ------------------------------------------------------------- distributions
function pOver(dist, line, scale){ // dist = [offset, values]; returns {over, push, under}
  if(!dist || !dist[1]) return null; const off=dist[0], vals=dist[1]; scale = scale||1; let o=0,p=0,u=0;
  for(let i=0;i<vals.length;i++){ const v=(off+i)*scale; if(v>line) o+=vals[i]; else if(v===line) p+=vals[i]; else u+=vals[i]; }
  const s=o+p+u||1; return {over:o/s, push:p/s, under:u/s}; }
function marginP(g, homeLine){ // home covers the spread when margin > line (line = expected home margin; book home spread = -line)
  const r = pOver(g.markets.dist.margin, homeLine); return r ? {home:r.over, push:r.push, away:r.under} : null; }
function fgP(g, side, line){ const pm=g.markets.fg[side].pmf; return pOver([0,pm], line); }
function qbYdsP(g, side, line){ return pOver(g.markets.qb[side].yds_pmf5, line, 5); }
function qbTdP(g, side, line){ return pOver([0,g.markets.qb[side].td_pmf], line); }
const refLine = (g, key) => { const T=(g.lines||{}).total; const sh=(M.league||{}).h1_share||0.5; if(T==null) return g.markets[key+'_fair_line'];
  return Math.floor(T*(key==='h1'?sh:1-sh))+0.5; };

// ------------------------------------------------------------- live scores (ESPN; CI snapshot as fallback)
const ESPN = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard';
const ESPN_SUM = id => 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event='+id;
const MAPAB = {WSH:'WAS', LAR:'LA', JAC:'JAX'};
const SUFFIX = new Set(['jr','sr','ii','iii','iv','v']);
function nameKey(n){ n=String(n||'').trim(); if(!n) return ''; let first, rest;
  if (/^[A-Za-z]{1,2}\.[A-Za-z'-]{2,}/.test(n)) { const i=n.indexOf('.'); first=n.slice(0,i); rest=n.slice(i+1); } else { const i=n.indexOf(' '); first=i<0?n:n.slice(0,i); rest=i<0?'':n.slice(i+1); }
  const toks = rest.replace(/\./g,' ').trim().split(/\s+/).filter(t=>t && !SUFFIX.has(t.toLowerCase().replace(',','')));
  return (first.slice(0,1)+'.'+toks.join('')).toLowerCase(); }
function fullKey(n){ const toks=String(n||'').toLowerCase().replace(/,/g,' ').replace(/'/g,'').split(/[\s.]+/).filter(t=>t && !SUFFIX.has(t)); const out=[];
  for(const t of toks){ if(t.length===1 && out.length===1 && out[0].length<=2 && /^[a-z]+$/.test(out[0])) out[0]+=t; else out.push(t); } return out.join(' '); }
// an odds row for a player: by full name first (two players can share a short key, e.g. Bijan and Brian Robinson), and never one whose first name conflicts
function propRow(T, who){ T=T||{}; const fk=fullKey(who); const r=T[fk]||T[nameKey(who)]; if(!r) return null;
  const a=fk.split(' ')[0]||'', b=fullKey(r.name||'').split(' ')[0]||''; return (a.length>2 && b.length>2 && a!==b) ? null : r; }
let LIVE = {}; const BOX = {}; const boxAt = {};
function parseEvent(ev){ const c=(ev.competitions||[{}])[0]; const st=c.status||ev.status||{}; const ty=st.type||{};
  const o={espn:String(ev.id), state:ty.state, detail:ty.shortDetail||ty.detail, period:st.period, clock:st.displayClock, completed:!!ty.completed};
  for(const t of (c.competitors||[])){ const ab=MAPAB[(t.team||{}).abbreviation]||(t.team||{}).abbreviation; o[t.homeAway]=ab; o[t.homeAway+'_score']=+(t.score||0); o[t.homeAway+'_line']=(t.linescores||[]).map(x=>+(x.value||0)); }
  return o; }
function parseSummary(js){ const box={qb:{}, fg:{}, td:[]};
  for(const tp of ((js.boxscore||{}).players||[])){ let ab=(tp.team||{}).abbreviation||''; ab=MAPAB[ab]||ab;
    for(const grp of (tp.statistics||[])){ const keys=grp.keys||[];
      for(const a of (grp.athletes||[])){ const nm=(a.athlete||{}).displayName||''; const st={}; (a.stats||[]).forEach((v,i)=>st[keys[i]]=v);
        if(grp.name==='passing') box.qb[nameKey(nm)]={name:nm, team:ab, yds:+(st.passingYards||0), td:+(st.passingTouchdowns||0)};
        else if(grp.name==='rushing' && +(st.rushingTouchdowns||0)>0) box.td.push(nameKey(nm));
        else if(grp.name==='receiving' && +(st.receivingTouchdowns||0)>0) box.td.push(nameKey(nm));
        else if(grp.name==='kicking'){ const f=String(st['fieldGoalsMade/fieldGoalAttempts']||'0/0').split('/')[0]; box.fg[ab]=(box.fg[ab]||0)+(+f||0); } } } }
  return box; }
function gameKey(h,a){ return h+'@'+a; }
const GKEY = {}; P.games.forEach(g=>GKEY[gameKey(g.home,g.away)] = g.game_id);
function ingestLive(events){ for(const e of events){ const gid=GKEY[gameKey(e.home,e.away)]; if(gid) LIVE[gid]=Object.assign(LIVE[gid]||{}, e); } }
function fetchJSON(u, ms){ const c=new AbortController(); const t=setTimeout(()=>c.abort(), ms||7000); return fetch(u,{cache:'no-store',signal:c.signal}).then(r=>{clearTimeout(t); if(!r.ok) throw r.status; return r.json();}); }
async function refreshLive(){
  let got=false;
  try { const js = await fetchJSON(ESPN); const wk=(js.week||{}).number, yr=(js.season||{}).year;
    if (!wk || (wk===P.week && yr===P.season)) { ingestLive((js.events||[]).map(parseEvent)); got=true; } } catch(e){}
  if(!got){ try { const js = await fetchJSON(BASE+'live.json'); if(js && js.games && js.week===P.week) { ingestLive(Object.values(js.games)); for(const g of Object.values(js.games)){ const gid=GKEY[gameKey(g.home,g.away)]; if(gid && g.box) BOX[gid]=g.box; } } } catch(e){} }
  // box scores for games in progress or just finished (props tracking)
  const jobs=[]; const now=Date.now();
  for(const [gid,L] of Object.entries(LIVE)){ if(!(L.state==='in' || L.state==='post')) continue; if(byId[gid] && byId[gid].actual && byId[gid].actual.qb) continue;
    if(boxAt[gid] && now-boxAt[gid] < (L.state==='in'?60000:600000)) continue; boxAt[gid]=now;
    jobs.push(fetchJSON(ESPN_SUM(L.espn)).then(js=>{ BOX[gid]=parseSummary(js); }).catch(()=>{})); }
  await Promise.all(jobs);
  render(); }

// ------------------------------------------------------------- outcomes
function finalOf(g){ const A=g.actual; if(A && A.hs!=null) return {final:true, hs:A.hs, as:A.as, h1: A.h1 ? A.h1[0]+A.h1[1] : null};
  const L=LIVE[g.game_id]; if(!L) return null;
  const h1 = (L.home_line||[]).length>=2 && (L.period>=3 || L.state==='post') ? (L.home_line[0]+L.home_line[1]+L.away_line[0]+L.away_line[1]) : null;
  return {final:L.state==='post', live:L.state==='in', hs:L.home_score, as:L.away_score, h1, period:L.period}; }
function outc(g){ // per market: hit / miss / push / pending
  const F=finalOf(g); if(!F || (!F.final && !F.live)) return null; const o={}; const L=g.lines||{};
  const m=F.hs-F.as, tot=F.hs+F.as;
  o.ml_home = F.final ? (m>0?'hit':(m===0?'tie':'miss')) : 'pending'; o.ml_away = F.final ? (m<0?'hit':(m===0?'tie':'miss')) : 'pending';
  if(L.spread!=null){ const d=m-L.spread; o.sp_home = F.final ? (d>0?'hit':(d===0?'tie':'miss')) : 'pending'; o.sp_away = F.final ? (d<0?'hit':(d===0?'tie':'miss')) : 'pending'; }
  if(L.total!=null){ o.over = tot>L.total ? 'hit' : (F.final ? (tot===L.total?'tie':'miss') : 'pending'); o.under = tot>L.total ? 'miss' : (F.final ? (tot===L.total?'tie':'hit') : 'pending'); }
  o.h1 = F.h1; o.h2 = (F.final && F.h1!=null) ? tot-F.h1 : null; o.total=tot; o.final=F.final;
  const A=g.actual||{}; const B=BOX[g.game_id];
  o.fg = A.fg ? A.fg : (B ? {home:B.fg[g.home]||0, away:B.fg[g.away]||0} : null);
  o.qb = {}; for(const side of ['home','away']){ const q=g.qb[side]; if(A.qb && A.qb[side] && nameKey(A.qb[side].name)===nameKey(q.name)) o.qb[side]=A.qb[side]; else if(B && B.qb[nameKey(q.name)]) o.qb[side]=B.qb[nameKey(q.name)]; }
  o.scorers = new Set(); if(A.scorers) A.scorers.forEach(id=>o.scorers.add('id:'+id)); if(B) B.td.forEach(k=>o.scorers.add('k:'+k));
  o.propsFinal = !!(A.qb) || (B && F.final);
  return o; }
function ouRes(v, line, side, final){ if(v==null) return null; if(v>line) return side==='over'?'hit':'miss'; if(!final) return 'pending'; if(v===line) return 'tie'; return side==='over'?'miss':'hit'; }
const RESTXT = {hit:'✓', miss:'✗', tie:'push', pending:'…'};
const markTxt = r => r ? `<span class="res ${r==='tie'?'tie':r}" title="${r}">${RESTXT[r]}</span>` : '';
const boxCls = r => r==='hit'?'o-hit':(r==='miss'?'o-miss':(r==='tie'?'o-tie':''));
function scored(o, a){ if(!o) return null; if(o.scorers.has('id:'+a.id) || o.scorers.has('k:'+nameKey(a.name))) return 'hit'; return o.propsFinal ? 'miss' : 'pending'; }

// ------------------------------------------------------------- header, status, tabs
const verdictOf = key => { const m = V && V.pooled && V.pooled[key]; return m && m.verdict ? m.verdict : null; };
const VK = {ml:'moneyline', spread:'spread', total:'total', h1:'h1_total', h2:'h2_total', fg:'fg_over1.5', qb_yds:'qb_yards', qb_td:'qb_td_over1.5', atd:'anytime_td', rec_yds:'rec_yds', rush_yds:'rush_yds', recs:'recs'};
const verdTag = key => { const v=verdictOf(VK[key]||key); if(!v) return '<span class="verd marginal">not yet validated</span>'; return `<span class="verd ${v==='beats baseline'?'beats':(v==='marginal'?'marginal':'none')}">${esc(v)}</span>`; };
document.getElementById('status').innerHTML = [
  `<b>${P.season} · week ${P.week}</b>`, `<b>${P.games.length}</b> games`,
  `data through <b>${esc(M.data_through||'n/a')}</b>`, `updated <b>${esc(P.generated_utc)}</b>`, `${(M.sims||0).toLocaleString()} sims per game`].map(x=>`<span>${x}</span>`).join('');
(function(){ const b=[]; if(V && V.pooled){ const gl=['moneyline','spread','total'].map(k=>V.pooled[k]).filter(Boolean);
    const none = gl.every(x=>x.verdict!=='beats baseline');
    if(none) b.push(`<div class="banner"><b>Bets are judged on the market, not the model.</b> In the walk-forward test the model alone did not beat the closing lines, and in 2026 it under-projected high-volume quarterbacks by about 20 yards. So every bet's win chance comes from all the books' prices (margin removed) at DraftKings' line, and the model may nudge player props by at most 4 points. The game cards still show the simulation for research.</div>`); }
  else b.push(`<div class="banner"><b>Validation pending.</b> The walk-forward backtest has not been published yet; treat every number as unvalidated.</div>`);
  document.getElementById('banner').innerHTML = b.join(''); })();
const tabs=document.getElementById('tabs');
document.body.dataset.tab='best';
function showTab(name, push){ document.body.dataset.tab=name; document.querySelectorAll('section.tab').forEach(s=>s.classList.toggle('on', s.id==='tab-'+name));
  tabs.querySelectorAll('button').forEach(b=>b.classList.toggle('on', b.dataset.tab===name)); try{localStorage.setItem('egd_nfl_tab',name);}catch(e){}
  if(push && history.replaceState) history.replaceState(null,'','#'+name); window.scrollTo({top:0}); }
tabs.querySelectorAll('button').forEach(b=>b.onclick=()=>showTab(b.dataset.tab,true));
function tabFromHash(){ let h=(location.hash||'').replace('#',''); if(h==='picks') h='scanner'; if(['best','week','scanner','research','results','about'].includes(h)) showTab(h,false); }
tabFromHash(); window.addEventListener('hashchange', tabFromHash);

// ------------------------------------------------------------- week tab
let SLOT = 'all';
function liveChip(g){ const L=LIVE[g.game_id]; const A=g.actual;
  if(A && A.hs!=null) return `<span class="lv final">FINAL ${g.away} ${A.as} · ${g.home} ${A.hs}${A.ot?' (OT)':''}</span>`;
  if(!L) return ''; if(L.state==='post') return `<span class="lv final">FINAL ${g.away} ${L.away_score} · ${g.home} ${L.home_score}</span>`;
  if(L.state==='in') return `<span class="lv live">LIVE ${esc(L.detail||'')} · ${g.away} ${L.away_score} · ${g.home} ${L.home_score}</span>`; return ''; }
function wx(g){ if(g.roof==='dome'||g.roof==='closed') return g.roof==='dome'?'dome':'roof closed';
  const w=g.weather; if(w) return `${Math.round(w.temp)}°F · wind ${Math.round(w.wind)} mph${w.precip_prob!=null?' · rain '+Math.round(w.precip_prob)+'%':''}`;
  if(g.temp!=null||g.wind!=null) return `${g.temp!=null?Math.round(g.temp)+'°F':''}${g.wind!=null?' · wind '+Math.round(g.wind)+' mph':''}`;
  return g.roof==='outdoors'?'outdoors · forecast pending':esc(g.roof||''); }
function mlBox(g,o){ const m=g.markets.ml, L=g.lines||{}; const fav = m.home>=m.away ? 'home':'away';
  const row = side => { const p=m[side]; const bp=bookPrice(g,'ml',side,null,null); const odds=bp?bp.odds:null;
    const ev = odds ? p*(odds-1) - (1-p-m.tie) : null; const r=o?o['ml_'+side]:null;
    return `<div class="row"><span>${g[side]} ${markTxt(r)}</span><span class="p ${side===fav?'hi':''}">${pct(p)}</span></div><span class="s">fair ${fmtOdds((1-m.tie)/p)}${odds?` · best ${odds.toFixed(2)}${ev!=null?` <span class="edge ${ev>=0?'pos':'neg'}">${ev>=0?'+':''}${(ev*100).toFixed(1)}%</span>`:''}`:''}</span>`; };
  return `<div class="mb"><span class="k">Moneyline</span>${row('away')}${row('home')}</div>`; }
function spBox(g,o){ const L=g.lines||{}; if(L.spread==null) return `<div class="mb"><span class="k">Spread</span><span class="s">no line yet · model ${g.home} by ${g.model.margin}</span></div>`;
  const P2 = marginP(g, L.spread); const hs = -L.spread; const r1=o?o.sp_away:null, r2=o?o.sp_home:null;
  const lean = g.model.margin - L.spread;
  return `<div class="mb"><span class="k">Spread</span>
    <div class="row"><span>${g.away} ${(L.spread>0?'+':'')+L.spread} ${markTxt(r1)}</span><span class="p">${pct(P2.away)}</span></div>
    <div class="row"><span>${g.home} ${(hs>0?'+':'')+hs} ${markTxt(r2)}</span><span class="p">${pct(P2.home)}</span></div>
    <span class="s" title="the model alone, before anchoring to the market">model alone: ${g.model.margin>=0?g.home:g.away} by ${Math.abs(g.model.margin).toFixed(1)}${P2.push>0.005?' · push '+pct(P2.push):''}</span></div>`; }
function totBox(g,o){ const L=g.lines||{}; if(L.total==null) return `<div class="mb"><span class="k">Total</span><span class="s">no line yet · model ${g.model.total}</span></div>`;
  const t=pOver(g.markets.dist.total, L.total); const r1=o?o.over:null, r2=o?o.under:null;
  return `<div class="mb"><span class="k">Total ${L.total}</span>
    <div class="row"><span>Over ${markTxt(r1)}</span><span class="p">${pct(t.over)}</span></div>
    <div class="row"><span>Under ${markTxt(r2)}</span><span class="p">${pct(t.under)}</span></div>
    <span class="s">model alone: ${g.model.total.toFixed(1)}${o?` · now ${o.total}`:''}</span></div>`; }
function halfBox(g,o,key){ const line=refLine(g,key); const t=pOver(g.markets.dist[key], line); const fl=g.markets[key+'_fair_line'];
  const v = o ? (key==='h1'?o.h1:o.h2) : null; const done = key==='h1' ? (o && o.h1!=null) : (o && o.final);
  const ro = v!=null ? ouRes(v, line, 'over', done) : null, ru = v!=null ? ouRes(v, line, 'under', done) : null;
  return `<div class="mb"><span class="k">${key==='h1'?'1st':'2nd'} half ${line}</span>
    <div class="row"><span>Over ${markTxt(ro)}</span><span class="p">${pct(t.over)}</span></div><div class="row"><span>Under ${markTxt(ru)}</span><span class="p">${pct(t.under)}</span></div>
    <span class="s">fair line ${fl} · mean ${g.markets[key+'_mean']}${v!=null?' · '+v+' pts':''}</span></div>`; }
function fgBox(g,o){ const f=g.markets.fg; const rr = side => { if(!o||!o.fg) return ''; const v=o.fg[side]; return markTxt(ouRes(v,1.5,f[side]['over1.5']>=0.5?'over':'under', o.final)) + `<span class="t"> ${v}</span>`; };
  return `<div class="mb"><span class="k">Team FGs made o1.5</span>
    <div class="row"><span>${g.away} ${rr('away')}</span><span class="p">${pct(f.away['over1.5'])}</span></div>
    <div class="row"><span>${g.home} ${rr('home')}</span><span class="p">${pct(f.home['over1.5'])}</span></div>
    <span class="s">mean ${f.away.mean.toFixed(2)} / ${f.home.mean.toFixed(2)} · o0.5 ${pct(f.away['over0.5'],0)} / ${pct(f.home['over0.5'],0)}</span></div>`; }
function qbBox(g,o,side){ const q=g.qb[side]||{}, m=g.markets.qb[side]; const prof=q.profile||{}; const now=o&&o.qb?o.qb[side]:null;
  const fl=m.yds_fair_line; const ry = now ? markTxt(ouRes(now.yds, fl, 'over', o.final)) : '';
  return `<div class="mb"><span class="k">${esc(g[side])} QB · ${esc(q.name||'?')}${q.status?`<span class="qtag">${esc(q.status)}</span>`:''}${q.change?'<span class="qtag">change</span>':''}</span>
    <div class="row"><span>Pass yds ${fl} ${ry}</span><span class="p">${Math.round(m.yds_q[3])}</span></div>
    <span class="s">middle 50%: ${Math.round(m.yds_q[2])}–${Math.round(m.yds_q[4])}${prof.yds_per_game?` · season-weighted avg ${prof.yds_per_game}`:''}${now?` · <b>${now.yds} yds, ${now.td} TD</b>`:''}</span>
    <div class="row" style="margin-top:6px"><span>TD passes ${now?markTxt(ouRes(now.td, 1.5, 'over', o.final)):''}</span><span>o0.5 <b>${pct(m['td_over0.5'],0)}</b> · o1.5 <b>${pct(m['td_over1.5'],0)}</b> · o2.5 <b>${pct(m['td_over2.5'],0)}</b></span></div>
    <span class="s">mean ${m.td_mean.toFixed(2)} TD passes · ${m.db_mean} dropbacks</span></div>`; }
function atdList(g,o,side){ const a=(g.anytime||{})[side]||[];
  return `<ol><li><span>${esc(g[side])} anytime TD</span><span>prob · fair</span></li>${a.slice(0,7).map(x=>{ const r=scored(o,x);
    return `<li class="${r==='hit'?'hit':''}"><span class="nm">${esc(x.name)}<span class="pos">${esc(x.pos||'')}</span>${x.q?'<span class="qtag">Q</span>':''}${r==='hit'?' ✓':''}</span><span><span class="pp">${pct(x.p,0)}</span> <span class="t">${x.fair?x.fair.toFixed(2):''}</span></span></li>`; }).join('')}</ol>`; }
function propList(g,o,side){ const a=((g.props||{})[side]||[]); const Pp=(g.odds||{}).props||{};
  const line = (x,key) => { const my=myLine(g,key,x.name); const bq=propRow(Pp[key], x.name); return (my&&my.line!=null)?my.line:((bq&&bq.line!=null)?bq.line:x[key].fair_line); };
  const st = (o && byId[g.game_id].actual && byId[g.game_id].actual.stats) ? byId[g.game_id].actual.stats : null;
  return `<ol><li><span>${esc(g[side])} props</span><span>line · over</span></li>${a.filter(x=>['rec_yds','rush_yds','recs'].some(k=>x[k]&&x[k].q[2]>=(k==='recs'?2.5:20))).slice(0,7).map(x=>{ const parts=[];
    for(const [key,lab,ak] of [['rec_yds','rec','recyds'],['rush_yds','rush','ryds'],['recs','rec#','rec']]){ const d=x[key]; if(!d) continue; const ln=line(x,key); const r=propP(d,ln); const act=st&&st[x.id]?st[x.id][ak]:null; parts.push(`${lab} ${ln}: <span class="pp">${pct(r.over,0)}</span>${act!=null?` <span class="t">(${act})</span>`:''}`); }
    return `<li><span class="nm">${esc(x.name)}<span class="pos">${esc(x.pos||'')}</span>${x.q?'<span class="qtag">Q</span>':''}</span><span class="t" style="white-space:normal;text-align:right">${parts.join(' · ')}</span></li>`; }).join('')}</ol>`; }
function card(g){ const o=outc(g); const r=g.research||{};
  const rest = `rest ${g.away} ${g.rest.away}d · ${g.home} ${g.rest.home}d`;
  return `<article class="nc" id="g-${g.game_id}">
  <div class="hd"><div><span class="mu">${g.away} @ ${g.home}</span> ${tierTag(g.tier)}</div><div class="when">${whenTxt(g)} ${liveChip(g)}</div></div>
  <div class="gl"><span>${esc(g.stadium)}${g.location==='Neutral'?' (neutral)':''}</span><span>${wx(g)}</span><span>${rest}</span>${g.div?'<span>division</span>':''}
   <span>${esc((r.away||{}).record||'')} vs ${esc((r.home||{}).record||'')}</span></div>
  <h5>Game lines</h5><div class="g3">${mlBox(g,o)}${spBox(g,o)}${totBox(g,o)}</div>
  <h5>Halves and kicking</h5><div class="g3">${halfBox(g,o,'h1')}${halfBox(g,o,'h2')}${fgBox(g,o)}</div>
  <h5>Quarterbacks</h5><div class="g2">${qbBox(g,o,'away')}${qbBox(g,o,'home')}</div>
  <h5>Anytime touchdown</h5><div class="atd">${atdList(g,o,'away')}${atdList(g,o,'home')}</div>
  <h5>Receiving and rushing</h5><div class="atd">${propList(g,o,'away')}${propList(g,o,'home')}</div>
  ${g.tier_why && g.tier_why.length ? `<p class="mini" style="margin:8px 0 0">${g.tier_why.map(esc).join(' · ')}</p>`:''}
  <div class="more" style="margin-top:8px"><button class="rbtn" style="margin:0" onclick="showTab('research',true);setTimeout(()=>{const d=document.getElementById('d-${g.game_id}'); if(d){d.open=true; d.scrollIntoView({behavior:'smooth'});}},50)">Research and inputs</button></div>
  </article>`; }
function renderToolbar(){ const slots=['all',...new Set(P.games.map(slotOf))];
  document.getElementById('toolbar').innerHTML = `<div class="chips">${slots.map(s=>`<button data-s="${s}" class="${s===SLOT?'on':''}">${SLOTS[s]||s}</button>`).join('')}</div>`;
  document.querySelectorAll('#toolbar button').forEach(b=>b.onclick=()=>{ SLOT=b.dataset.s; renderToolbar(); renderCards(); }); }
function renderCards(){ const gs=P.games.filter(g=>SLOT==='all'||slotOf(g)===SLOT).sort((a,b)=>(a.kickoff_utc||'').localeCompare(b.kickoff_utc||''));
  document.getElementById('cards').innerHTML = gs.map(card).join(''); }
function renderLivebar(){ const live=P.games.filter(g=>(LIVE[g.game_id]||{}).state==='in'); const el=document.getElementById('livebar');
  if(!live.length){ el.style.display='none'; return; } el.style.display='block';
  el.innerHTML = `<div class="lhd"><span class="pulse"></span><b>${live.length} live</b> ${live.map(g=>{const L=LIVE[g.game_id]; return `<span>${g.away} ${L.away_score} · ${g.home} ${L.home_score} <span class="t">${esc(L.detail||'')}</span></span>`;}).join(' · ')}<button class="rbtn" onclick="refreshLive()">refresh</button></div>`; }
const PK_LABEL = {desk:'Research desk', ml:'Moneyline', spread:'Spread', total:'Total', h1:'1st half total', h2:'2nd half total', fg:'Team FGs 1.5', qb_yds:'QB pass yards', qb_td:'QB pass TDs 1.5', atd:'Anytime TD', rec_yds:'Receiving yards', rush_yds:'Rushing yards', recs:'Receptions'};
function pickText(k, x){ if(k==='ml') return `${x.team} ML`; if(k==='spread'){ const hl=-x.line; return x.side==='home'?`${byId[x.game_id].home} ${hl>0?'+':''}${hl}`:`${byId[x.game_id].away} ${x.line>0?'+':''}${x.line}`; }
  if(k==='total'||k==='h1'||k==='h2') return `${x.side==='over'?'Over':'Under'} ${x.line}`; if(k==='fg') return `${x.team} ${x.side} ${x.line} FGs`;
  if(k==='qb_yds') return `${x.qb} ${x.side} ${x.line} yds`; if(k==='qb_td') return `${x.qb} ${x.side} ${x.line} TDs`; if(k==='atd') return `${x.player} (${x.team})`;
  if(k==='rec_yds') return `${x.player} ${x.side} ${x.line} rec yds`; if(k==='rush_yds') return `${x.player} ${x.side} ${x.line} rush yds`; if(k==='recs') return `${x.player} ${x.side} ${x.line} rec`; return ''; }
function renderBoard(){ const keys=['ml','spread','total','h1','h2','qb_yds','qb_td','rec_yds','rush_yds','recs','atd'];
  document.getElementById('board').innerHTML = keys.filter(k=>(P.picks[k]||[]).length).map(k=>{ const x=P.picks[k][0];
    return `<a href="#best" onclick="showTab('best',true);return false;"><span class="k">${PK_LABEL[k]}</span><span class="mu">${esc(x.label||pickText(k,x))}</span><span class="v">${evTxt(x.ev)}</span><span class="s">${esc(x.mu)} · DraftKings ${x.odds!=null?dec2am(x.odds):''}</span></a>`; }).join(''); }

// ------------------------------------------------------------- price check
const PC_MARKETS = [['ml_home','Moneyline: home'],['ml_away','Moneyline: away'],['sp_home','Spread: home'],['sp_away','Spread: away'],['over','Total: over'],['under','Total: under'],
  ['h1_over','1st half: over'],['h1_under','1st half: under'],['h2_over','2nd half: over'],['h2_under','2nd half: under'],['fg_home_over','Home FGs: over'],['fg_home_under','Home FGs: under'],
  ['fg_away_over','Away FGs: over'],['fg_away_under','Away FGs: under'],['qy_home_over','Home QB yards: over'],['qy_home_under','Home QB yards: under'],['qy_away_over','Away QB yards: over'],['qy_away_under','Away QB yards: under'],
  ['qt_home_over','Home QB TDs: over'],['qt_home_under','Home QB TDs: under'],['qt_away_over','Away QB TDs: over'],['qt_away_under','Away QB TDs: under'],['atd','Anytime TD'],
  ['rec_yds_over','Receiving yards: over'],['rec_yds_under','Receiving yards: under'],['rush_yds_over','Rushing yards: over'],['rush_yds_under','Rushing yards: under'],['recs_over','Receptions: over'],['recs_under','Receptions: under']];
const PLAYER_MK = mk => mk==='atd' || mk.startsWith('rec_yds') || mk.startsWith('rush_yds') || mk.startsWith('recs');
const propKind = mk => mk.startsWith('rec_yds') ? 'rec_yds' : (mk.startsWith('rush_yds') ? 'rush_yds' : (mk.startsWith('recs') ? 'recs' : null));
function myDefault(g, mk){ const side=mk.split('_')[1]; const q=(g.qb||{})[side]||{};
  if(mk.startsWith('qy')) return myLine(g,'qb_yds',q.name); if(mk.startsWith('qt')) return myLine(g,'qb_td',q.name); if(mk.startsWith('h1')) return myLine(g,'h1',null); if(mk.startsWith('h2')) return myLine(g,'h2',null); return null; }
function defaultLine(g, mk){ const L=g.lines||{}; const my=myDefault(g, mk); if(my && my.line!=null) return my.line;
  if(mk.startsWith('sp')) return mk==='sp_home' ? -(L.spread||0) : (L.spread||0); if(mk==='over'||mk==='under') return L.total||g.markets.total_fair_line;
  if(mk.startsWith('h1')) return refLine(g,'h1'); if(mk.startsWith('h2')) return refLine(g,'h2'); if(mk.startsWith('fg')) return 1.5;
  if(mk.startsWith('qy')) return g.markets.qb[mk.split('_')[1]].yds_fair_line; if(mk.startsWith('qt')) return 1.5; return ''; }
function pcProb(g, mk, line, player){
  if(mk==='ml_home'||mk==='ml_away'){ const m=g.markets.ml; const p=mk==='ml_home'?m.home:m.away; return {p, push:m.tie}; }
  if(mk==='sp_home'||mk==='sp_away'){ const homeLine = mk==='sp_home' ? -line : line; const r=marginP(g, homeLine); return {p: mk==='sp_home'?r.home:r.away, push:r.push}; }
  const ou = (r, over) => ({p: over?r.over:r.under, push:r.push});
  if(mk==='over'||mk==='under') return ou(pOver(g.markets.dist.total,line), mk==='over');
  if(mk.startsWith('h1')) return ou(pOver(g.markets.dist.h1,line), mk.endsWith('over')); if(mk.startsWith('h2')) return ou(pOver(g.markets.dist.h2,line), mk.endsWith('over'));
  const side = mk.split('_')[1];
  if(mk.startsWith('fg')) return ou(fgP(g,side,line), mk.endsWith('over')); if(mk.startsWith('qy')) return ou(qbYdsP(g,side,line), mk.endsWith('over'));
  if(mk.startsWith('qt')) return ou(qbTdP(g,side,line), mk.endsWith('over'));
  if(mk==='atd'){ const a=[...(g.anytime.home||[]),...(g.anytime.away||[])].find(x=>x.id===player); return a?{p:a.p,push:0}:null; }
  const pk=propKind(mk); if(pk){ const x=[...((g.props||{}).home||[]),...((g.props||{}).away||[])].find(z=>z.id===player); if(!x||!x[pk]) return null; return ou(propP(x[pk], line), mk.endsWith('over')); } return null; }
function renderPC(){ const el=document.getElementById('pricecheck'); const gs=[...P.games].sort((a,b)=>(a.kickoff_utc||'').localeCompare(b.kickoff_utc||''));
  let st={}; try{ st=JSON.parse(localStorage.getItem('egd_nfl_pc')||'{}'); }catch(e){}
  el.innerHTML = `<h3>Price check <span class="mini" style="text-transform:none;letter-spacing:0">${MYBOOK?`${esc(MYBOOK)}'s line and odds fill in when it posts the market; `:''}any line works, pushes included</span></h3>
  <div class="pc"><label>Game<select id="pc-g">${gs.map(g=>`<option value="${g.game_id}">${g.away} @ ${g.home}</option>`).join('')}</select></label>
  <label>Market<select id="pc-m">${PC_MARKETS.map(([k,l])=>`<option value="${k}">${l}</option>`).join('')}</select></label>
  <label id="pc-pl" style="display:none">Player<select id="pc-p"></select></label>
  <label id="pc-ll">Line<input id="pc-l" inputmode="decimal"></label>
  <label>Book odds<input id="pc-o" placeholder="1.91 or -110" inputmode="text"></label></div><div class="pcout" id="pc-out"></div>`;
  const G=document.getElementById('pc-g'), Mk=document.getElementById('pc-m'), Ln=document.getElementById('pc-l'), Od=document.getElementById('pc-o'), Pl=document.getElementById('pc-p');
  if(st.g && byId[st.g]) G.value=st.g; if(st.m) Mk.value=st.m;
  const syncPlayers = () => { const g=byId[G.value]; const pk=propKind(Mk.value); let a;
    if(pk) a=[...((g.props||{}).away||[]).filter(x=>x[pk]).map(x=>[x,g.away]),...((g.props||{}).home||[]).filter(x=>x[pk]).map(x=>[x,g.home])];
    else a=[...(g.anytime.away||[]).map(x=>[x,g.away]),...(g.anytime.home||[]).map(x=>[x,g.home])];
    const prev=Pl.value; Pl.innerHTML = a.map(([x,t])=>`<option value="${x.id}">${esc(x.name)} (${t})</option>`).join(''); if([...Pl.options].some(o=>o.value===prev)) Pl.value=prev; };
  const propLine = () => { const g=byId[G.value]; const pk=propKind(Mk.value); if(!pk) return null; const x=[...((g.props||{}).home||[]),...((g.props||{}).away||[])].find(z=>z.id===Pl.value); if(!x||!x[pk]) return null;
    const my=myLine(g,pk,x.name); return my&&my.line!=null ? my : {line:x[pk].fair_line}; };
  const syncLine = (keep) => { const g=byId[G.value]; const pm = PLAYER_MK(Mk.value); const atd = Mk.value==='atd'; document.getElementById('pc-pl').style.display = pm?'':'none'; document.getElementById('pc-ll').style.display = atd||Mk.value.startsWith('ml')?'none':'';
    if(pm) syncPlayers();
    if(!keep){ const pl=propLine(); if(pl){ Ln.value=pl.line; Od.value = pl[Mk.value.endsWith('over')?'over':'under'] ? pl[Mk.value.endsWith('over')?'over':'under'].toFixed(2) : ''; }
      else { Ln.value = defaultLine(g, Mk.value); const my=myDefault(g, Mk.value); const o = my ? (Mk.value.endsWith('over') ? my.over : my.under) : null; Od.value = o ? o.toFixed(2) : ''; } } };
  const calc = () => { const g=byId[G.value]; const line=parseFloat(Ln.value); const r=pcProb(g, Mk.value, isNaN(line)?0:line, Pl.value); const out=document.getElementById('pc-out');
    try{ localStorage.setItem('egd_nfl_pc', JSON.stringify({g:G.value, m:Mk.value})); }catch(e){}
    if(!r){ out.innerHTML=''; return; } const d=parseOdds(Od.value); const pw=r.p, push=r.push||0; const fo = pw>0 ? (1-push)/pw : null;
    const ev = d ? pw*(d-1) - (1-pw-push) : null; const kelly = d && ev>0 ? ev/(d-1) : null;
    out.innerHTML = `<div><span class="k">Win</span><span class="v">${pct(pw)}</span></div>${push>0.001?`<div><span class="k">Push</span><span class="v">${pct(push)}</span></div>`:''}
      <div><span class="k">Fair odds</span><span class="v">${fo?fo.toFixed(2):'–'}</span><span class="t">${fo?dec2am(fo):''}</span></div>
      ${d?`<div><span class="k">EV per $10</span><span class="v ${ev>=0?'hi':''}" style="color:${ev>=0?'var(--green)':'var(--red)'}">${ev>=0?'+':''}$${(ev*10).toFixed(2)}</span></div><div><span class="k">Kelly</span><span class="v">${kelly?(kelly*100).toFixed(1)+'%':'no bet'}</span></div>`:''}`; };
  G.onchange=()=>{ syncLine(false); calc(); }; Mk.onchange=()=>{ syncLine(false); calc(); }; Ln.oninput=calc; Od.oninput=calc; Pl.onchange=()=>{ const pl=propLine(); if(pl){ Ln.value=pl.line; const o=pl[Mk.value.endsWith('over')?'over':'under']; Od.value=o?o.toFixed(2):''; } calc(); }; syncLine(false); calc(); }

// ------------------------------------------------------------- research
// mode: 'good' (higher is better for the team), 'bad' (higher is worse), 'n' (no colour)
function orCell(x, mode){ if(x==null) return '–'; const v=(x-1)*100; mode=mode||'good'; const up = mode==='bad' ? 'var(--red)' : 'var(--green)', dn = mode==='bad' ? 'var(--green)' : 'var(--red)';
  const col = mode==='n' ? 'var(--text)' : (v>=3?up:(v<=-3?dn:'var(--text)')); return `<span style="color:${col}">${v>=0?'+':''}${v.toFixed(0)}%</span>`; }
const spreadTxt = (home, away, s) => s==null ? '' : (s>0 ? `${home} -${s}` : (s<0 ? `${away} -${-s}` : "pick'em"));
function teamRows(a, h){ const rows = [['Record', a.record, h.record], ['Points for / against', `${a.pf}–${a.pa}`, `${h.pf}–${h.pa}`], ['ATS / over-under', `${a.ats} · ${a.ou}`, `${h.ats} · ${h.ou}`],
  ['Offense: TDs vs expected', orCell(a.offense&&a.offense.or_td), orCell(h.offense&&h.offense.or_td)], ['Offense: FG tries vs expected', orCell(a.offense&&a.offense.or_fg,'n'), orCell(h.offense&&h.offense.or_fg,'n')],
  ['Offense: turnovers vs expected', orCell(a.offense&&a.offense.or_to,'bad'), orCell(h.offense&&h.offense.or_to,'bad')], ['Defense: TDs allowed vs expected', orCell(a.defense&&a.defense.or_td,'bad'), orCell(h.defense&&h.defense.or_td,'bad')],
  ['Defense: FG tries allowed', orCell(a.defense&&a.defense.or_fg,'n'), orCell(h.defense&&h.defense.or_fg,'n')], ['Defense: takeaways vs expected', orCell(a.defense&&a.defense.or_to), orCell(h.defense&&h.defense.or_to)],
  ['Seconds per drive (pace)', a.offense&&a.offense.secs_per_drive, h.offense&&h.offense.secs_per_drive], ['EPA per play, offense', a.epa_off_per_play, h.epa_off_per_play], ['EPA per play allowed', a.epa_def_per_play, h.epa_def_per_play],
  ['Points per drive (weighted)', a.offense&&a.offense.ppd, h.offense&&h.offense.ppd], ['1H / 2H points per game', `${a.h1_pts_avg??'–'} / ${a.h2_pts_avg??'–'}`, `${h.h1_pts_avg??'–'} / ${h.h2_pts_avg??'–'}`],
  ['Field goals made per game', a.fg_made_avg, h.fg_made_avg], ['Drives in the profile', a.offense&&a.offense.drives, h.offense&&h.offense.drives]];
  const A=(a.adv||{}), Hh=(h.adv||{});
  const pr = (x, adv, side, k, fmt) => { const v=((adv||{})[side]||{})[k]; if(v==null) return '–'; const r=((adv||{})['rank_'+side]||{})[k];
    return `${fmt==='s'?v.toFixed(1)+'s':(fmt==='e'?(v>=0?'+':'')+v.toFixed(2):pct(v,1))}${r?` <span class="t">${r}${r===1?'st':(r===2?'nd':(r===3?'rd':'th'))}</span>`:''}`; };
  const adv = [['Success rate, offense', 'off','success'], ['Success rate allowed', 'def','success'], ['Explosive plays, offense', 'off','explosive'], ['Explosive plays allowed', 'def','explosive'],
    ['Third-down conversions', 'off','third_down'], ['Third downs allowed', 'def','third_down'], ['Red-zone trips ending in a TD', 'off','red_zone_td'], ['Red-zone TD rate allowed', 'def','red_zone_td'],
    ['Sacks taken per dropback', 'off','sack_rate'], ['Sacks per opponent dropback', 'def','sack_rate'], ['EPA per pass play', 'off','epa_pass','e'], ['EPA per pass play allowed', 'def','epa_pass','e'],
    ['EPA per run', 'off','epa_rush','e'], ['EPA per run allowed', 'def','epa_rush','e'], ['Seconds per play (neutral)', 'off','pace','s'], ['Pass rate over expected (neutral)', 'off','proe']];
  rows.push(...adv.map(([lab, side, k, f]) => [lab + (side==='def'?'':''), pr(a, A, side, k, f), pr(h, Hh, side, k, f)]));
  return rows.map(r=>`<tr><td>${r[0]}</td><td>${r[1]??'–'}</td><td>${r[2]??'–'}</td></tr>`).join(''); }
function qbRows(q){ const p=q.profile; if(!p) return `<p class="small">${esc(q.name||'unknown')}: no NFL passing record in the data.</p>`;
  return `<p class="small"><b>${esc(q.name)}</b> (${esc(q.source||'')}) · ${p.games} games in the profile · ${p.ypdb} yds/dropback (x${p.ypdb_mult} after shrinkage) · ${p.yds_per_game} yds/game · ${p.td_per_game} TD/game · EPA/dropback ${p.epa_per_db}</p>
  <table><tr><th>date</th><th>opp</th><th>db</th><th>yds</th><th>td</th><th>int</th></tr>${(p.last_games||[]).slice().reverse().map(x=>`<tr><td>${x.date}</td><td>${x.opp}</td><td>${x.db}</td><td>${x.yds}</td><td>${x.td}</td><td>${x.int}</td></tr>`).join('')}</table>`; }
function injList(arr){ const a=(arr||[]).filter(x=>x.status||/Did Not/.test(x.practice||'')); if(!a.length) return '<span class="small">nothing reported</span>';
  return a.slice(0,18).map(x=>`<span class="flag ${x.status==='Out'?'':(x.status?'':'dim')}">${esc(x.name)} ${esc(x.pos)} · ${esc(x.status||x.practice||'')}${x.injury?' ('+esc(x.injury)+')':''}</span>`).join(' '); }
function inputsTable(g){ const NAMES={offense:'Team offense', opp_defense:'Opposing defense', home_field:'Home field', rest_adv:'Rest advantage', rest_dis:'Rest disadvantage', short_week:'Short week (both)', dome:'Dome', wind15:'Wind 15+ mph', cold:'Cold (32°F or less)', division:'Division game', qb_change:'Quarterback change'};
  const one = side => { const x=g.inputs[side]; const rows=Object.entries(x.parts).map(([k,v])=>`<tr><td>${NAMES[k]||k}</td>${v.map((u,i)=>orCell2(u,i)).join('')}</tr>`).join('');
    return `<table><tr><th>${esc(x.team)} offense</th><th>TD</th><th>FG try</th><th>TO</th></tr>${rows}<tr><td><b>Total</b></td>${x.total.map((v,i)=>orCell2(v,i)).join('')}</tr></table>
    <p class="small">pace x${x.pace} · dropbacks x${x.db_mult} · yds/dropback x${x.ypdb_mult} · TD is a pass ${pct(x.p_pass_td,0)} · kicker make shift ${x.make_shift>=0?'+':''}${x.make_shift} (log odds) · XP ${pct(x.xp,1)}${x.notes&&x.notes.length?' · '+x.notes.map(esc).join('; '):''}</p>`; };
  const anc=g.model.anchor; return `<div class="dgrid"><div class="box">${one('away')}</div><div class="box">${one('home')}</div></div>
  <p class="small">Model alone: ${g.home} ${g.model.margin>=0?'by '+g.model.margin.toFixed(1):'trails by '+(-g.model.margin).toFixed(1)}, total ${g.model.total.toFixed(1)}, ${g.home} wins ${pct(g.model.home_win)}.${g.model.target_margin!=null?` Anchored to the market at margin ${g.model.target_margin.toFixed(1)}, total ${g.model.target_total.toFixed(1)} (scoring shift ${anc.shift_home>=0?'+':''}${anc.shift_home} ${g.home}, ${anc.shift_away>=0?'+':''}${anc.shift_away} ${g.away}).`:' No market line: the model alone is used.'}</p>`; }
function orCell2(v, i){ const r=Math.exp(v); return `<td>${orCell(r, i===1?'n':(i===2?'bad':'good'))}</td>`; }
function renderSources(){ const S=M.sources||[]; if(!S.length) return; const cls={verified:'beats', projected:'marginal', unavailable:'none'};
  document.getElementById('sources').innerHTML = `<h3>Data sources and freshness</h3><div class="tbl"><table class="kv"><tr><th>Source</th><th>Status</th><th>What it covers</th><th>Fetched</th></tr>${S.map(x=>`<tr><td>${esc(x.name)}</td><td><span class="verd ${cls[x.status]||'marginal'}">${esc(x.status)}</span></td><td>${esc(x.detail)}</td><td>${esc(x.fetched||'')}</td></tr>`).join('')}</table></div>
  <p class="small">Verified: taken directly from the source. Projected: an estimate (starting QB vote, depth charts, forecasts). Unavailable: not used, and nothing is substituted for it.</p>`; }
function renderResearch(){ renderSources(); const L=M.league||{}; const ctx=L.context||{}; const H=L.home||{};
  const crow = (k,lab) => { const c=ctx[k]; if(!c) return ''; return `<tr><td>${lab}</td><td>${orCell(Math.exp(c.TD),'n')}</td><td>${orCell(Math.exp(c.FG),'n')}</td><td>${orCell(Math.exp(c.TO),'n')}</td><td>${c.n.toLocaleString()}</td></tr>`; };
  const sw=M.switches||{};
  document.getElementById('factors').innerHTML = `<h3>Measured factors (league, ${esc((L.seasons||[]).join(', '))})</h3>
  <p>${(L.games||0).toLocaleString()} games and ${(L.drives||0).toLocaleString()} drives. Effects are odds ratios on a drive's chance of a touchdown, a field-goal try and a turnover, against the league table for the same situation, shrunk toward no effect.</p>
  <div class="tbl"><table class="cmp"><tr><th>Factor</th><th>TD</th><th>FG try</th><th>TO</th><th>drives</th></tr>
  <tr><td>Home field (each side)</td><td>${orCell(Math.exp(H.TD||0),'n')}</td><td>${orCell(Math.exp(H.FG||0),'n')}</td><td>${orCell(Math.exp(H.TO||0),'n')}</td><td>${(H.n||0).toLocaleString()}</td></tr>
  ${crow('rest_adv','Rest advantage (3+ days)')}${crow('rest_dis','Rest disadvantage')}${crow('short_week','Short week, both teams')}${crow('dome','Dome or closed roof')}${crow('wind15','Wind 15+ mph')}${crow('cold','Cold, 32°F or less')}${crow('division','Division game')}
  <tr><td>Quarterback change (mid-season)</td><td>${orCell(Math.exp((M.new_qb||{}).TD||0))}</td><td>${orCell(Math.exp((M.new_qb||{}).FG||0),'n')}</td><td>${orCell(Math.exp((M.new_qb||{}).TO||0),'bad')}</td><td>${((M.new_qb||{}).n||0).toLocaleString()}</td></tr></table></div>
  <p class="small">Switches: ${Object.entries(sw).map(([k,v])=>`${k.replace('use_','').replace('_',' ')} <b>${v?'on':'off'}</b>`).join(' · ')}. League: ${L.total_mean} points per game · XP ${pct(L.xp_make)} · two-point tries on ${pct(L.two_rate)} of touchdowns · ${pct(L.pass_td_share,0)} of offensive touchdowns are passes · ${L.ypdb} passing yds per dropback.</p>`;
  const T=M.tested||[]; if(T.length) document.getElementById('factors').innerHTML += `<h3 style="margin-top:14px">Tested in the walk-forward backtest</h3>
  <p>Each change was run over every week of three seasons and kept only if it improved the markets it targets.</p>
  <div class="tbl"><table class="cmp"><tr><th>Change</th><th>Result</th><th>Decision</th></tr>${T.map(t=>`<tr><td>${esc(t.name)}</td><td style="white-space:normal;text-align:left">${esc(t.result)}</td><td><span class="verd ${t.kept?'beats':'none'}">${t.kept?'kept':'rejected'}</span></td></tr>`).join('')}</table></div>`;
  document.getElementById('dossiers').innerHTML = [...P.games].sort((a,b)=>(a.kickoff_utc||'').localeCompare(b.kickoff_utc||'')).map(g=>{ const r=g.research||{}; const a=r.away||{}, h=r.home||{};
    return `<details class="dossier" id="d-${g.game_id}"><summary><span class="mu">${g.away} @ ${g.home}</span> ${tierTag(g.tier)} <span class="t">${whenTxt(g)} · ${wx(g)}</span></summary><div class="body">
    <div class="dgrid"><div class="box"><h4>Teams <span class="t" style="text-transform:none;letter-spacing:0">this season, league rank in grey</span></h4><table><tr><th></th><th>${g.away}</th><th>${g.home}</th></tr>${teamRows(a,h)}</table></div>
    <div class="box"><h4>Head to head (last meetings)</h4>${(r.h2h||[]).length?`<table><tr><th>date</th><th>score</th><th>1H</th><th>line</th></tr>${r.h2h.map(x=>`<tr><td>${x.date}</td><td>${x.away} ${x.as} @ ${x.home} ${x.hs}</td><td>${x.h1}</td><td>${spreadTxt(x.home,x.away,x.spread)} / ${x.total!=null?x.total:''}</td></tr>`).join('')}</table>`:'<p class="small">no meetings in the data window</p>'}
    <h4 style="margin-top:10px">Kickers</h4>${['away','home'].map(s=>{ const k=g.kicker[s]||{}; const p=k.profile; return `<p class="small"><b>${g[s]}</b> ${esc(k.name||k.id||'?')}: ${p?`${p.made}/${p.att} this season · make odds x${p.or} vs expected for his distances · 50+: ${p.long_50plus} · XP ${pct(p.xp_rate)}`:'no record'}</p>`; }).join('')}</div>
    <div class="box"><h4>${g.away} quarterback</h4>${qbRows(g.qb.away)}</div><div class="box"><h4>${g.home} quarterback</h4>${qbRows(g.qb.home)}</div>
    <div class="box"><h4>${g.away} injury report</h4>${injList((g.injuries||{}).away)}</div><div class="box"><h4>${g.home} injury report</h4>${injList((g.injuries||{}).home)}</div></div>
    <h4 style="margin:12px 0 6px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)">Inputs to the simulation</h4>${inputsTable(g)}
    <h4 style="margin:12px 0 6px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)">Touchdown shares</h4>
    <div class="dgrid">${['away','home'].map(s=>`<div class="box"><table><tr><th>${g[s]}</th><th>targets</th><th>carries</th><th>red zone</th><th>snaps, last 3</th><th>TD games</th></tr>${((g.anytime||{})[s]||[]).map(x=>`<tr><td>${esc(x.name)} <span class="t">${esc(x.pos||'')}</span></td><td>${pct(x.tgt_share,0)}</td><td>${pct(x.car_share,0)}</td><td>${pct(x.rz_share,0)}</td><td>${(x.snaps||[]).map(v=>Math.round(v*100)).join(' / ')||'–'}</td><td>${x.td_games}/${x.games}</td></tr>`).join('')}</table></div>`).join('')}</div>
    </div></details>`; }).join(''); }

// ------------------------------------------------------------- every selection (scanner), grades, book prices
const KIND = {ml:'Moneyline', spread:'Spread', total:'Total', h1:'1st half total', h2:'2nd half total', fg:'Team field goals', qb_yds:'QB passing yards', qb_td:'QB passing TDs', atd:'Anytime TD', rec_yds:'Receiving yards', rush_yds:'Rushing yards', recs:'Receptions'};
function propP(d, line){ const [off,vals]=d.pmf; const st=d.step; let o=0,p=0,u=0; vals.forEach((x,i)=>{ const v=(off+i)*st; if(v>line) o+=x; else if(v===line) p+=x; else u+=x; }); const s=o+p+u||1; return {over:o/s, push:p/s, under:u/s}; }
const am2dec = a => a==null ? null : (a>0 ? 1+a/100 : 1+100/(-a));
const VAL = (P.best_bets && P.best_bets.all) || {};
const evKey = (kind, line) => kind==='fg' ? 'fg_over'+(line<1?'0.5':(line<2?'1.5':'2.5')) : (kind==='qb_td' ? 'qb_td_over'+(line<1?'0.5':(line<2?'1.5':'2.5')) : VK[kind]);
function evidence(kind, line){ if(kind==='ml'||kind==='spread'||kind==='total') return 1; const v=verdictOf(evKey(kind,line)); return v==='beats baseline'?2:(v==='marginal'?1:0); }
function calBand(kind, line, side, p){ if(kind==='ml'||kind==='spread'||kind==='total') return null;
  const m = V && V.pooled && V.pooled[evKey(kind,line)]; if(!m || !m.calibration) return null;
  const flip = side==='under'; const q = flip ? 1-p : p; let best=null;
  for(const b of m.calibration){ if(!best || Math.abs(b.p-q) < Math.abs(best.p-q)) best=b; }
  return best ? {p: flip?1-best.p:best.p, hit: flip?1-best.hit:best.hit, n: best.n} : null; }
function gradeOf(o){ let v=null; if(o.ev!=null) v = o.ev>=0.05 ? 2 : (o.ev>=0 ? 1 : -1); o.Vv=v;
  if(v===null) return 'C';                          // no price: value unknown
  if(o.fairsrc!=='market') return o.ev < -0.04 ? 'D' : 'C';   // the model alone is never trusted against a price
  const need = o.need || 0.02, ok = !o.excluded;
  if(ok && o.ev>=need+0.03) return 'S'; if(ok && o.ev>=need) return 'A'; if(o.ev>=0) return 'B'; if(o.ev>=-0.04) return 'C'; return 'D'; }
let MYBOOK='DraftKings'; try{ const v=localStorage.getItem('egd_book'); if(v!==null) MYBOOK=v; }catch(e){}
function allBooks(){ const b=new Set(); for(const g of P.games){ const O=g.odds||{}; for(const k of ['ml','spread','total']){ if(O[k]) ['home','away','over','under'].forEach(s=>{ if(O[k]['book_'+s]) b.add(O[k]['book_'+s]); }); }
  const Pp=O.props||{}; for(const k of ['qb_yds','qb_td','atd']) for(const x of Object.values(Pp[k]||{})) Object.keys(x.books||{}).forEach(t=>b.add(t)); for(const k of ['h1','h2']) Object.keys((Pp[k]||{}).books||{}).forEach(t=>b.add(t)); } return [...b].sort(); }
function myLine(g, kind, who){ // the chosen book's own line and prices for a prop, else null
  if(!MYBOOK) return null; const Pp=(g.odds||{}).props||{}; let x=null;
  if(kind==='qb_yds'||kind==='qb_td'||kind==='rec_yds'||kind==='rush_yds'||kind==='recs') x=propRow(Pp[kind], who); else if(kind==='h1'||kind==='h2') x=Pp[kind]; else if(kind==='atd') x=propRow(Pp.atd, who);
  const b=x && x.books && x.books[MYBOOK]; return b ? {line:b.line, over:b.over, under:b.under, yes:b.yes, book:MYBOOK} : null; }
function bookPrice(g, kind, side, line, who){
  const mine = myLine(g, kind, who);
  if(mine && (mine.line===line || kind==='atd')){ const o = kind==='atd' ? mine.yes : mine[side]; if(o && o>1) return {odds:o, book:MYBOOK, cons:null, mine:true}; }
  if(MYBOOK){ const O=g.odds||{}; const gl = kind==='ml' ? O.ml : (kind==='spread' ? O.spread : (kind==='total' ? O.total : null));
    if(gl && gl.books && gl.books[MYBOOK]){ const b=gl.books[MYBOOK]; const ok = kind==='ml' || (kind==='spread' ? (side==='home' ? b.line===line : -b.line===line) : b.line===line); if(ok && b[side]>1) return {odds:b[side], book:MYBOOK, cons:null, mine:true}; }
    if(O.props || gl) return null;            // the feed is on but this book has no such price: do not substitute another book's
  }
  const O=g.odds||{}, Pp=O.props||{}, L=g.lines||{};
  const r = (odds, book, cons) => (odds && odds>1) ? {odds, book, cons} : null;
  const cons2 = (c, first) => c==null ? null : (first ? c : 1-c);
  if(kind==='ml'){ if(O.ml) return r(O.ml[side], O.ml['book_'+side], cons2(O.ml.consensus_home, side==='home')); return r(am2dec(L[side+'_ml']), 'consensus (nflverse)', null); }
  if(kind==='spread'){ if(O.spread){ const ok = side==='home' ? O.spread.line===line : -O.spread.line===line; if(ok) return r(O.spread[side], O.spread['book_'+side], cons2(O.spread.consensus_home, side==='home')); }
    if(L.spread!=null && (side==='home' ? -L.spread===line : L.spread===line)) return r(am2dec(L[side+'_spread_odds']), 'consensus (nflverse)', null); return null; }
  if(kind==='total'){ if(O.total && O.total.line===line) return r(O.total[side], O.total['book_'+side], cons2(O.total.consensus_over, side==='over'));
    if(L.total===line) return r(am2dec(L[side+'_odds']), 'consensus (nflverse)', null); return null; }
  if(kind==='h1'||kind==='h2'){ const x=Pp[kind]; return (x && x.line===line) ? r(x[side], x['book_'+side], cons2(x.consensus_over, side==='over')) : null; }
  if(kind==='qb_yds'||kind==='qb_td'||kind==='rec_yds'||kind==='rush_yds'||kind==='recs'){ const x=propRow(Pp[kind], who); return (x && x.line===line) ? r(x[side], x['book_'+side], cons2(x.consensus_over, side==='over')) : null; }
  if(kind==='atd'){ const x=propRow(Pp.atd, who); return x ? r(x.yes, x.book_yes, x.consensus_yes) : null; }
  return null; }
function legTxt(o){ return o.label; }
function buildSelections(){ const out=[];
  for(const g of P.games){ const mk=g.markets, L=g.lines||{}, O=g.odds||{}, Pp=O.props||{}; const mu=`${g.away} @ ${g.home}`;
    const uncertain = side => (g.tier_why||[]).some(w=>w.startsWith(g[side]+':') && w.includes('uncertain'));
    const add = o => { o.game_id=g.game_id; o.mu=mu; o.kick=g.kickoff_utc||''; o.tier=g.tier;
      o.id = [o.kind, g.game_id, o.side, o.line, o.who||o.team||''].join('|');
      const F = VAL[o.id];                                   // fair chance from the market (best-bets engine), when DraftKings lists it
      o.fair = o.p>0 ? (1-(o.push||0))/o.p : null;
      const bp = bookPrice(g, o.kind, o.side, o.line, o.who); if(bp){ o.odds=bp.odds; o.book=bp.book; o.cons=bp.cons;
        if(F){ o.p_ev=F.p; o.cons=F.p_market; o.fairsrc='market'; o.need=F.need; o.excluded=F.excluded; o.ev = F.p*(bp.odds-1) - (1-F.p-(F.push||0)); }
        else {
          // no market consensus for this selection: the model alone, which the backtest does not trust against a price
          let pe=o.p; if(o.kind==='atd'){ const imp=Math.min(0.95, 0.8/bp.odds); pe=(o.p+imp)/2; o.p_ev=pe; o.longshot = imp < o.p/2; }
          o.fairsrc='model'; o.ev = pe*(bp.odds-1) - (1-pe-(o.push||0)); } }
      o.E = evidence(o.kind, o.line); o.Q = Math.max(0, (g.tier==='A'?2:(g.tier==='B'?1:0)) - (o.questionable?1:0));
      o.grade = gradeOf(o); o.band = calBand(o.kind, o.line, o.side, o.p);
      out.push(o); };
    for(const side of ['away','home']) add({kind:'ml', side, line:null, team:g[side], label:`${g[side]} moneyline`, p:mk.ml[side], push:mk.ml.tie});
    const myS = MYBOOK && O.spread && O.spread.books && O.spread.books[MYBOOK]; const S = myS ? -myS.line : (O.spread ? -O.spread.line : L.spread);
    if(S!=null){ const r=marginP(g, S), hl=-S;
      add({kind:'spread', side:'away', line:-hl, team:g.away, label:`${g.away} ${-hl>0?'+':''}${-hl}`, p:r.away, push:r.push});
      add({kind:'spread', side:'home', line:hl, team:g.home, label:`${g.home} ${hl>0?'+':''}${hl}`, p:r.home, push:r.push}); }
    const myT = MYBOOK && O.total && O.total.books && O.total.books[MYBOOK]; const T = myT ? myT.line : (O.total ? O.total.line : L.total);
    if(T!=null){ const r=pOver(mk.dist.total, T); for(const s of ['over','under']) add({kind:'total', side:s, line:T, label:`${s==='over'?'Over':'Under'} ${T}`, p:r[s], push:r.push}); }
    for(const k of ['h1','h2']){ const mh=myLine(g,k,null); const bl = (mh && mh.line!=null) ? mh.line : ((Pp[k] && Pp[k].line!=null) ? Pp[k].line : refLine(g,k)); const r=pOver(mk.dist[k], bl);
      for(const s of ['over','under']) add({kind:k, side:s, line:bl, label:`${k==='h1'?'1st half':'2nd half'} ${s} ${bl}`, p:r[s], push:r.push}); }
    for(const side of ['away','home']){ const t=g[side];
      for(const ln of [0.5,1.5,2.5]){ const r=fgP(g,side,ln); for(const s of ['over','under']) add({kind:'fg', side:s, line:ln, team:t, tside:side, label:`${t} ${s} ${ln} field goals`, p:r[s], push:r.push}); }
      const q=g.qb[side]||{}; if(q.name){ const who=q.name, qq=!!q.status||uncertain(side);
        const bq=propRow(Pp.qb_yds, who); const my=myLine(g,'qb_yds',who); const yl=(my && my.line!=null) ? my.line : ((bq && bq.line!=null) ? bq.line : g.markets.qb[side].yds_fair_line); const ry=qbYdsP(g,side,yl);
        for(const s of ['over','under']) add({kind:'qb_yds', side:s, line:yl, team:t, tside:side, who, label:`${who} ${s} ${yl} passing yds`, p:ry[s], push:ry.push, questionable:qq});
        const bt=propRow(Pp.qb_td, who); const lines=[0.5,1.5,2.5]; if(bt && bt.line!=null && !lines.includes(bt.line)) lines.push(bt.line); const mt=myLine(g,'qb_td',who); if(mt && mt.line!=null && !lines.includes(mt.line)) lines.push(mt.line);
        for(const ln of lines){ const r=qbTdP(g,side,ln); for(const s of ['over','under']) add({kind:'qb_td', side:s, line:ln, team:t, tside:side, who, label:`${who} ${s} ${ln} TD passes`, p:r[s], push:r.push, questionable:qq}); } }
      for(const a of ((g.anytime||{})[side]||[])) add({kind:'atd', side:'yes', line:null, team:t, tside:side, who:a.name, pid:a.id, rec:a.rec_share, rush:a.rush_share, label:`${a.name} (${t}) anytime TD`, p:a.p, push:0, questionable:!!a.q});
      for(const x of ((g.props||{})[side]||[])){ for(const [key,lab] of [['rec_yds','receiving yds'],['rush_yds','rushing yds'],['recs','receptions']]){ const d=x[key]; if(!d) continue; if(d.q[2] < (key==='recs'?2.5:20) && !propRow(Pp[key], x.name)) continue;
        const my=myLine(g,key,x.name); const bq=propRow(Pp[key], x.name); const ln=(my&&my.line!=null)?my.line:((bq&&bq.line!=null)?bq.line:d.fair_line); const r=propP(d, ln);
        for(const s of ['over','under']) add({kind:key, side:s, line:ln, team:t, tside:side, who:x.name, pid:x.id, label:`${x.name} ${s} ${ln} ${lab}`, p:r[s], push:r.push, questionable:!!x.q, median:d.q[2]}); } }
    } }
  return out; }
const SELS = buildSelections(); const SEL_BY = {}; SELS.forEach(s=>SEL_BY[s.id]=s);
const GRADE_ORDER = {S:0, A:1, B:2, C:3, D:4};
let SC = {kind:'all', game:'all', team:'', grades:['S','A','B','C','D'], minp:0, odds:true, q:'', sort:'grade', n:60};
try{ SC = Object.assign(SC, JSON.parse(localStorage.getItem('egd_nfl_scan')||'{}'), {n:60}); }catch(e){}
function saveSC(){ try{ localStorage.setItem('egd_nfl_scan', JSON.stringify(SC)); }catch(e){} }
function selResult(o){ const g=byId[o.game_id]; return legResult(o, g, true); }
function renderScanner(){ const el=document.getElementById('scanner');
  const teams=[...new Set(P.games.flatMap(g=>[g.away,g.home]))].sort();
  const gs=[...P.games].sort((a,b)=>(a.kickoff_utc||'').localeCompare(b.kickoff_utc||''));
  const withOdds = SELS.filter(s=>s.odds!=null).length;
  let rows = SELS.filter(s=>(SC.kind==='all'||s.kind===SC.kind) && (SC.game==='all'||s.game_id===SC.game) && (!SC.team||s.team===SC.team||s.mu.includes(SC.team))
    && SC.grades.includes(s.grade) && s.p*100>=SC.minp && (!SC.odds||!withOdds||s.odds!=null) && (!SC.q || s.label.toLowerCase().includes(SC.q.toLowerCase())));
  const key = {p:s=>-s.p, ev:s=>-(s.ev==null?-9:s.ev), grade:s=>GRADE_ORDER[s.grade]*10-(s.ev==null?s.p:s.ev), fair:s=>s.fair||99, kick:s=>s.kick}[SC.sort];
  rows.sort((a,b)=>{ const x=key(a), y=key(b); return x<y?-1:(x>y?1:0); });
  const total=rows.length; rows=rows.slice(0, SC.n);
  el.innerHTML = `<div class="scanbar">
   <label>Market<select id="sc-kind"><option value="all">All markets</option>${Object.entries(KIND).map(([k,v])=>`<option value="${k}" ${SC.kind===k?'selected':''}>${v}</option>`).join('')}</select></label>
   <label>Game<select id="sc-game"><option value="all">All games</option>${gs.map(g=>`<option value="${g.game_id}" ${SC.game===g.game_id?'selected':''}>${g.away} @ ${g.home}</option>`).join('')}</select></label>
   <label>Team<select id="sc-team"><option value="">All teams</option>${teams.map(t=>`<option ${SC.team===t?'selected':''}>${t}</option>`).join('')}</select></label>
   <label>Sort<select id="sc-sort"><option value="p" ${SC.sort==='p'?'selected':''}>Win probability</option><option value="ev" ${SC.sort==='ev'?'selected':''}>Expected value</option><option value="grade" ${SC.sort==='grade'?'selected':''}>Grade</option><option value="fair" ${SC.sort==='fair'?'selected':''}>Fair odds (low first)</option><option value="kick" ${SC.sort==='kick'?'selected':''}>Kickoff</option></select></label>
   <label>Min win %<input id="sc-minp" type="number" min="0" max="99" step="5" value="${SC.minp}"></label>
   <label>Search<input id="sc-q" placeholder="player or team" value="${esc(SC.q)}"></label>
   <label>My sportsbook<select id="sc-book">${['DraftKings',...allBooks().filter(b=>b!=='DraftKings')].map(b=>`<option ${MYBOOK===b?'selected':''}>${esc(b)}</option>`).join('')}<option value="" ${MYBOOK===''?'selected':''}>Best price (any book)</option></select></label>
   <div class="chips" id="sc-grades">${['S','A','B','C','D'].map(x=>`<button data-g="${x}" class="${SC.grades.includes(x)?'on':''}">${x}</button>`).join('')}<button id="sc-odds" class="${SC.odds?'on':''}">${MYBOOK?'only bets '+esc(MYBOOK)+' offers':'with book odds'}</button></div></div>
   <p class="mini" style="margin:6px 0">${total.toLocaleString()} of ${SELS.length.toLocaleString()} selections · book odds on ${withOdds.toLocaleString()} ${withOdds? (MYBOOK?`· props priced at ${esc(MYBOOK)}'s own lines`:'· props priced at the line most books post') : '(add the Odds API key for live prices on props; game lines use the nflverse consensus)'} · tap a row to add it to the slip</p>
   <div class="scan">${rows.map(o=>{ const r=selResult(o); const inSlip=SLIP.find(s=>s.id===o.id);
     return `<div class="srow ${inSlip?'on':''}" data-id="${esc(o.id)}"><span class="gr g${o.grade}" title="${esc(gradeWhy(o))}">${o.grade}</span>
      <span class="sel"><b>${esc(o.label)}</b> ${markTxt(r)}<span class="t">${esc(o.mu)} · ${KIND[o.kind]}${o.questionable?' · questionable / uncertain':''}</span></span>
      <span class="num n-win"><span class="k">win</span><b>${pct(o.p)}</b>${o.push>0.005?`<span class="t">push ${pct(o.push)}</span>`:''}</span>
      <span class="num n-fair"><span class="k">fair</span>${o.fair?o.fair.toFixed(2):'–'}<span class="t">${o.fair?dec2am(o.fair):''}</span></span>
      <span class="num n-book"><span class="k">book</span>${o.odds?o.odds.toFixed(2):'–'}<span class="t">${o.odds?esc(o.book||''):'no price'}</span></span>
      <span class="num n-ev"><span class="k">EV</span>${o.ev==null?'–':`<b style="color:${o.ev>=0?'var(--green)':'var(--red)'}">${o.ev>=0?'+':''}${(o.ev*100).toFixed(1)}%</b>`}${o.cons!=null?`<span class="t">market ${pct(o.cons,0)}</span>`:(o.p_ev!=null?`<span class="t">on ${pct(o.p_ev,0)} blended</span>`:'')}</span>
      <span class="num n-bt"><span class="k">backtest</span>${o.band?`${pct(o.band.hit,0)} hit<span class="t">when rated ~${pct(o.band.p,0)} (n ${o.band.n})</span>`:'<span class="t">market price</span>'}</span></div>`; }).join('')}</div>
   ${total>SC.n?`<div style="text-align:center;margin-top:8px"><button class="rbtn" style="margin:0" id="sc-more">show ${Math.min(60,total-SC.n)} more</button></div>`:''}`;
  const on = (id, ev, fn) => { const e=document.getElementById(id); if(e) e[ev]=fn; };
  on('sc-kind','onchange',e=>{ SC.kind=e.target.value; SC.n=60; saveSC(); renderScanner(); }); on('sc-game','onchange',e=>{ SC.game=e.target.value; SC.n=60; saveSC(); renderScanner(); });
  on('sc-team','onchange',e=>{ SC.team=e.target.value; SC.n=60; saveSC(); renderScanner(); }); on('sc-sort','onchange',e=>{ SC.sort=e.target.value; saveSC(); renderScanner(); });
  on('sc-minp','onchange',e=>{ SC.minp=+e.target.value||0; saveSC(); renderScanner(); });
  on('sc-q','onchange',e=>{ SC.q=e.target.value; saveSC(); renderScanner(); });
  on('sc-more','onclick',()=>{ SC.n+=60; renderScanner(); });
  on('sc-book','onchange',e=>{ MYBOOK=e.target.value; try{ localStorage.setItem('egd_book', MYBOOK); }catch(ex){} SELS.length=0; buildSelections().forEach(x=>SELS.push(x)); Object.keys(SEL_BY).forEach(k=>delete SEL_BY[k]); SELS.forEach(x=>SEL_BY[x.id]=x); renderScanner(); renderPC(); }); on('sc-odds','onclick',()=>{ SC.odds=!SC.odds; saveSC(); renderScanner(); });
  document.querySelectorAll('#sc-grades button[data-g]').forEach(b=>b.onclick=()=>{ const x=b.dataset.g; SC.grades = SC.grades.includes(x) ? SC.grades.filter(y=>y!==x) : [...SC.grades, x]; saveSC(); renderScanner(); });
  document.querySelectorAll('#scanner .srow').forEach(d=>d.onclick=()=>toggleLeg(SEL_BY[d.dataset.id])); }
function gradeWhy(o){ if(o.Vv==null) return `${o.grade}: no book price, so the value is unknown.`;
  const src = o.fairsrc==='market' ? 'win chance from the market consensus (all books, no vig), nudged by the model' : 'no market consensus for this selection, model alone (never graded above C)';
  const ex = o.excluded ? ` Not listed as good: ${o.excluded}.` : '';
  return `${o.grade}: EV ${o.ev>=0?'+':''}${(o.ev*100).toFixed(1)}% at ${o.book||'the book'}; ${src}.${ex}`; }

// ------------------------------------------------------------- slip: correlation-aware parlays
let SLIP=[]; try{ SLIP=JSON.parse(localStorage.getItem('egd_nfl_slip_'+P.season+'_'+P.week)||'[]').filter(x=>x && x.kind); }catch(e){}
function saveSlip(){ try{ localStorage.setItem('egd_nfl_slip_'+P.season+'_'+P.week, JSON.stringify(SLIP)); }catch(e){} }
function toggleLeg(o){ if(!o) return; const i=SLIP.findIndex(s=>s.id===o.id); if(i>=0) SLIP.splice(i,1); else SLIP.push(Object.assign({}, o)); saveSlip(); renderScanner(); renderTop(); renderSlip(); renderBest(); }
function legFromPick(k, x){ const g=byId[x.game_id]; let o;
  if(k==='ml') o={kind:'ml', side:x.side, line:null}; else if(k==='spread') o={kind:'spread', side:x.side, line: x.side==='home' ? -x.line : x.line};
  else if(k==='total'||k==='h1'||k==='h2') o={kind:k, side:x.side, line:x.line}; else if(k==='fg') o={kind:'fg', side:x.side, line:x.line, tside:x.side_team, team:x.team};
  else if(k==='qb_yds'||k==='qb_td') o={kind:k, side:x.side, line:x.line, tside:x.side_team, who:x.qb, team:x.team};
  else if(k==='rec_yds'||k==='rush_yds'||k==='recs') o={kind:k, side:x.side, line:x.line, tside:x.side_team, who:x.player, pid:x.id, team:x.team};
  else { const side = g.home===x.team ? 'home':'away'; const a=((g.anytime||{})[side]||[]).find(z=>z.id===x.id)||{}; o={kind:'atd', side:'yes', line:null, tside:side, who:x.player, pid:x.id, rec:a.rec_share||0, rush:a.rush_share||0, team:x.team}; }
  const id=[o.kind, x.game_id, o.side, o.line, o.who||o.team||''].join('|'); if(SEL_BY[id]) return SEL_BY[id];
  return Object.assign(o, {id, game_id:x.game_id, mu:x.mu, p:x.p, push:0, label:pickText(k,x), grade:'C', tier:g.tier}); }
let SIMS=null, SIMS_P=null;
function loadSims(){ if(SIMS_P) return SIMS_P; const name=P.season+'-w'+String(P.week).padStart(2,'0');
  SIMS_P = fetchJSON(BASE+'weeks/'+name+'.sims.json', 25000).then(j=>{ SIMS={}; for(const [gid,b64] of Object.entries(j.games||{})){ const bin=atob(b64); const u=new Uint8Array(bin.length); for(let i=0;i<bin.length;i++) u[i]=bin.charCodeAt(i); SIMS[gid]=u; } return SIMS; })
    .catch(()=>{ SIMS={}; return SIMS; }); return SIMS_P; }
function simAt(u, i){ const o=i*17, dv=new DataView(u.buffer, u.byteOffset); return {hp:u[o],ap:u[o+1],h1h:u[o+2],h1a:u[o+3],fgh:u[o+4],fga:u[o+5],tdh:u[o+6],tda:u[o+7],rth:u[o+8],rta:u[o+9],ot:u[o+10],yh:dv.getInt16(o+11,true),ya:dv.getInt16(o+13,true),w:dv.getUint16(o+15,true)/10000}; }
function legWin(l, s){ const H = (l.tside||l.side)==='home';
  switch(l.kind){
    case 'ml': return l.side==='home' ? +(s.hp>s.ap) : +(s.ap>s.hp);
    case 'spread': { const m = l.side==='home' ? s.hp-s.ap : s.ap-s.hp; return +(m + l.line > 0); }
    case 'total': { const v=s.hp+s.ap; return l.side==='over' ? +(v>l.line) : +(v<l.line); }
    case 'h1': { const v=s.h1h+s.h1a; return l.side==='over' ? +(v>l.line) : +(v<l.line); }
    case 'h2': { const v=s.hp+s.ap-s.h1h-s.h1a; return l.side==='over' ? +(v>l.line) : +(v<l.line); }
    case 'fg': { const v=H?s.fgh:s.fga; return l.side==='over' ? +(v>l.line) : +(v<l.line); }
    case 'qb_yds': { const v=H?s.yh:s.ya; return l.side==='over' ? +(v>l.line) : +(v<l.line); }
    case 'qb_td': { const v=H?s.tdh:s.tda; return l.side==='over' ? +(v>l.line) : +(v<l.line); }
    case 'atd': { const np=H?s.tdh:s.tda, nr=H?s.rth:s.rta; return 1 - Math.pow(1-(l.rec||0), np)*Math.pow(1-(l.rush||0), nr); }
    case 'rec_yds': case 'rush_yds': case 'recs': return l.p;   // not in the packed samples: priced as independent of the other legs
  } return 0; }
function slipMath(){ // combined probability: independent across games, joint within a game from the simulated games
  const groups={}; SLIP.forEach(l=>(groups[l.game_id]=groups[l.game_id]||[]).push(l));
  let naive=1, adj=1, corr=false, pending=false; const notes=[];
  for(const [gid, legs] of Object.entries(groups)){ const prod = legs.reduce((a,l)=>a*l.p, 1); naive*=prod;
    if(legs.length<2){ adj*=prod; continue; }
    const u = SIMS && SIMS[gid]; if(!u){ adj*=prod; pending=true; continue; }
    const n=u.length/17; let W=0, J=0; const S=legs.map(()=>0);
    for(let i=0;i<n;i++){ const s=simAt(u,i); let j=s.w; for(let k=0;k<legs.length;k++){ const v=legWin(legs[k], s); S[k]+=s.w*v; j*=v; } W+=s.w; J+=j; }
    const singles=S.map(x=>x/W), joint=J/W, indep=singles.reduce((a,b)=>a*b,1);
    const ratio = indep>0 ? Math.min(6, Math.max(0.05, joint/indep)) : 1; adj*=prod*ratio; corr=true;
    notes.push({mu:legs[0].mu, ratio, n}); }
  return {naive, adj, corr, pending, notes}; }
function renderSlip(){ const el=document.getElementById('slip');
  if(!SLIP.length){ el.innerHTML='<h3>Slip</h3><p>Tap any selection to add it. Legs from the same game are priced together from the simulated games (a quarterback\'s yards and his team\'s total move together), not multiplied as if independent.</p>'; return; }
  const sameGame = new Set(SLIP.map(l=>l.game_id)).size < SLIP.length;
  if(sameGame && !SIMS) loadSims().then(()=>renderSlip());
  const m = slipMath(); const p=m.adj;
  let st={}; try{ st=JSON.parse(localStorage.getItem('egd_nfl_slipin')||'{}'); }catch(e){}
  el.innerHTML = `<h3>Slip · ${SLIP.length} leg${SLIP.length>1?'s':''}</h3><div class="slip">
   <div class="row" style="margin-top:0"><span>combined win probability</span></div><div class="big">${pct(p)}</div>
   <div class="row"><span>fair odds <b>${(1/p).toFixed(2)}</b> (${dec2am(1/p)})</span>${sameGame?`<span>if independent: ${pct(m.naive)}</span>`:''}
    ${m.notes.map(x=>`<span>${esc(x.mu)}: correlation x${x.ratio.toFixed(2)} (${x.n.toLocaleString()} simulated games)</span>`).join('')}${m.pending?'<span>loading the simulated games…</span>':''}</div>
   <div class="row"><label>book odds <input id="slip-o" placeholder="3.10 or +210" value="${esc(st.o||'')}"></label><label>stake $<input id="slip-s" inputmode="decimal" value="${esc(st.s||'10')}"></label><span id="slip-ev"></span>
    <button class="abtn" id="slip-log">log bet</button><button class="rbtn" id="slip-clear">clear</button></div>
   <div class="row">${SLIP.map(l=>`<span class="lg">${esc(l.label)} <b>${pct(l.p,0)}</b> <span class="gr g${l.grade||'C'} sm">${l.grade||'C'}</span> <a href="#" data-x="${esc(l.id)}">remove</a></span>`).join('')}</div>
   <div class="warn" style="color:var(--muted)">Win probability counts a pushed leg as not winning. Simulation sampling adds about ±1 point on same-game joint probabilities; no parlay is a sure thing.</div></div>`;
  const O=document.getElementById('slip-o'), Sk=document.getElementById('slip-s');
  const upd=()=>{ try{ localStorage.setItem('egd_nfl_slipin', JSON.stringify({o:O.value, s:Sk.value})); }catch(e){}
    const d=parseOdds(O.value); const s=parseFloat(Sk.value)||0; const ev=d?p*d-1:null;
    document.getElementById('slip-ev').innerHTML = ev==null ? '' : `EV <b style="color:${ev>=0?'var(--green)':'var(--red)'}">${ev>=0?'+':''}${(ev*100).toFixed(1)}%</b> · pays $${(s*d).toFixed(2)} · expected $${(s*ev).toFixed(2)}`; };
  O.oninput=upd; Sk.oninput=upd; upd();
  document.getElementById('slip-clear').onclick=()=>{ SLIP=[]; saveSlip(); renderScanner(); renderTop(); renderSlip(); };
  document.getElementById('slip-log').onclick=()=>{ const d=parseOdds(O.value), s=parseFloat(Sk.value);
    if(!d || !s){ alert('Enter the book odds and the stake to log the bet.'); return; } logBet(d, s, p); };
  el.querySelectorAll('a[data-x]').forEach(a=>a.onclick=e=>{ e.preventDefault(); const i=SLIP.findIndex(l=>l.id===a.dataset.x); if(i>=0){ SLIP.splice(i,1); saveSlip(); renderScanner(); renderTop(); renderSlip(); } }); }
// top leans (the published leans, graded in the track record)
function renderTop(){ const keys=['ml','spread','total','h1','h2','fg','qb_yds','qb_td','atd','rec_yds','rush_yds','recs'];
  const ks = keys.filter(k=>(P.picks[k]||[]).length);
  document.getElementById('picks').innerHTML = ks.length ? ks.map(k=>{ const L=P.picks[k]||[]; return `<div class="pk"><h3>${PK_LABEL[k]}</h3><p class="why">Clears the bar at DraftKings' price, judged on the market's fair odds.</p><ol>${L.map((x,i)=>{ const o=legFromPick(k,x); const r=legResult(o, byId[x.game_id], true);
    return `<li class="leg2 ${SLIP.find(s=>s.id===o.id)?'on':''}" data-k="${k}" data-i="${i}"><span><span class="mu">${esc(x.label||pickText(k,x))}</span> ${markTxt(r)}<br><span class="t">${esc(x.mu)} · DraftKings ${x.odds!=null?x.odds.toFixed(2)+' ('+dec2am(x.odds)+')':'–'} · win ${pct(x.p)}</span></span><span class="p">${evTxt(x.ev)}</span></li>`; }).join('')}</ol></div>`; }).join('')
    : '<div class="pk"><p class="why">No bet clears the bar at DraftKings right now.</p></div>';
  document.querySelectorAll('#picks .leg2').forEach(li=>li.onclick=()=>{ const x=P.picks[li.dataset.k][+li.dataset.i]; toggleLeg(legFromPick(li.dataset.k, x)); }); }

// ------------------------------------------------------------- grading a leg from final (or live) results
function legResult(l, g, live){ if(!g) return null; const A=g.actual||{}; let hs=A.hs, as_=A.as, h1=A.h1?A.h1[0]+A.h1[1]:null, final=hs!=null;
  if(!final && live){ const F=finalOf(g); if(!F || (!F.final && !F.live)) return null; hs=F.hs; as_=F.as; h1=F.h1; final=F.final; }
  if(hs==null) return null;
  const ou = (v, done) => v==null ? null : ouRes(v, l.line, l.side, done);
  switch(l.kind){
    case 'ml': return final ? ((l.side==='home'?hs-as_:as_-hs)>0?'hit':(hs===as_?'tie':'miss')) : 'pending';
    case 'spread': { if(!final) return 'pending'; const m=(l.side==='home'?hs-as_:as_-hs)+l.line; return m>0?'hit':(m===0?'tie':'miss'); }
    case 'total': return ou(hs+as_, final);
    case 'h1': return h1==null ? 'pending' : ouRes(h1, l.line, l.side, true);
    case 'h2': return (final && h1!=null) ? ouRes(hs+as_-h1, l.line, l.side, true) : 'pending';
  }
  const o = live ? outc(g) : null; const H=l.tside==='home'; const side=H?'home':'away';
  if(l.kind==='fg'){ const fg = A.fg || (o && o.fg); return fg ? ou(fg[side], final) : 'pending'; }
  if(l.kind==='qb_yds'||l.kind==='qb_td'){ let q=null; if(A.qb && A.qb[side] && nameKey(A.qb[side].name)===nameKey(l.who)) q=A.qb[side]; else if(o && o.qb[side]) q=o.qb[side];
    if(!q) return (A.qb ? 'void' : 'pending'); return ou(l.kind==='qb_yds'?q.yds:q.td, final && (!!A.qb || (o && o.propsFinal))); }
  if(l.kind==='atd'){ if(A.scorers){ return A.scorers.includes(l.pid) ? 'hit' : 'miss'; } return o ? scored(o, {id:l.pid, name:l.who}) : 'pending'; }
  if(l.kind==='rec_yds'||l.kind==='rush_yds'||l.kind==='recs'){ const st=(A.stats||{})[l.pid]; if(!st) return A.scorers ? 'void' : 'pending'; const v = l.kind==='rec_yds'?st.recyds:(l.kind==='rush_yds'?st.ryds:st.rec); return ou(v, true); }
  return null; }

// ------------------------------------------------------------- bet tracker (this browser)
let BETS=[]; try{ BETS=JSON.parse(localStorage.getItem('egd_nfl_bets')||'[]'); }catch(e){}
function saveBets(){ try{ localStorage.setItem('egd_nfl_bets', JSON.stringify(BETS)); }catch(e){} }
function logBet(odds, stake, p){ const wk=P.season+'-w'+String(P.week).padStart(2,'0');
  BETS.push({id:Date.now().toString(36), ts:new Date().toISOString(), week:wk, legs:SLIP.map(l=>({id:l.id, kind:l.kind, side:l.side, line:l.line, tside:l.tside, who:l.who, pid:l.pid, game_id:l.game_id, mu:l.mu, label:l.label, p:l.p, grade:l.grade, odds:l.odds||null})),
    odds, stake, p, grade: SLIP.length===1 ? (SLIP[0].grade||'C') : 'parlay', model: M.model_version, status:'open'});
  saveBets(); SLIP=[]; saveSlip(); renderScanner(); renderTop(); renderSlip(); renderTracker(); showTab('results', true); }
const WEEKS_CACHE = {};
async function gradeBets(){ const now=P.season+'-w'+String(P.week).padStart(2,'0'); let changed=false;
  for(const b of BETS){ if(b.status!=='open') continue;
    let games=null; if(b.week===now) games=byId; else { try{ if(!WEEKS_CACHE[b.week]) WEEKS_CACHE[b.week]=await fetchJSON(BASE+'weeks/'+b.week+'.json'); const gg={}; WEEKS_CACHE[b.week].games.forEach(g=>gg[g.game_id]=g); games=gg; }catch(e){ continue; } }
    const rs=b.legs.map(l=>legResult(l, games[l.game_id], b.week===now)); b.results=rs;
    if(rs.some(r=>r==='miss')){ b.status='lost'; b.ret=0; changed=true; }
    else if(rs.every(r=>r==='hit'||r==='tie'||r==='void')){ const live=rs.filter(r=>r==='hit').length;
      if(!live){ b.status='push'; b.ret=b.stake; } else { // a pushed or void leg drops out of a parlay: divide its price out when known
        let o=b.odds; b.legs.forEach((l,i)=>{ if((rs[i]==='tie'||rs[i]==='void') && b.legs.length>1 && l.odds) o/=l.odds; }); b.status='won'; b.ret=b.stake*(b.legs.length===1?b.odds:o); }
      changed=true; }
    // closing price: the selection's price in the last build before kickoff (single bets with a book price)
    if(b.legs.length===1 && b.closing==null){ const l=b.legs[0]; const g=games[l.game_id]; if(g && g.frozen){ const bp=bookPrice(g, l.kind, l.side, l.line, l.who); if(bp){ b.closing=bp.odds; changed=true; } } }
  }
  if(changed){ saveBets(); renderTracker(); } }
function renderTracker(){ const el=document.getElementById('tracker'); const s=BETS.filter(b=>b.status!=='open'), open=BETS.length-s.length;
  const staked=s.reduce((a,b)=>a+b.stake,0), ret=s.reduce((a,b)=>a+(b.ret||0),0), won=s.filter(b=>b.status==='won').length, lost=s.filter(b=>b.status==='lost').length, push=s.filter(b=>b.status==='push').length;
  const avgO = BETS.length ? BETS.reduce((a,b)=>a+b.odds,0)/BETS.length : null; const avgP = (won+lost) ? s.filter(b=>b.status!=='push').reduce((a,b)=>a+b.p,0)/(won+lost) : null;
  const clv = BETS.filter(b=>b.closing); const avgClv = clv.length ? clv.reduce((a,b)=>a+(b.odds/b.closing-1),0)/clv.length : null;
  const group = keyf => { const t={}; s.forEach(b=>{ const k=keyf(b); t[k]=t[k]||{n:0,w:0,st:0,ret:0}; t[k].n++; t[k].w+=b.status==='won'; t[k].st+=b.stake; t[k].ret+=b.ret||0; }); return t; };
  const tbl = (title, t, lab) => Object.keys(t).length ? `<div class="tbl"><table><tr><th>${title}</th><th>bets</th><th>won</th><th>staked</th><th>P/L</th><th>ROI</th></tr>${Object.entries(t).map(([k,v])=>`<tr><td>${esc(lab?lab(k):k)}</td><td>${v.n}</td><td>${v.w}</td><td>$${v.st.toFixed(2)}</td><td style="color:${v.ret-v.st>=0?'var(--green)':'var(--red)'}">${v.ret-v.st>=0?'+':''}$${(v.ret-v.st).toFixed(2)}</td><td>${v.st?((v.ret-v.st)/v.st*100).toFixed(1)+'%':'–'}</td></tr>`).join('')}</table></div>` : '';
  el.innerHTML = `<h3>My bets <span class="mini" style="text-transform:none;letter-spacing:0">kept in this browser only; graded automatically from the results</span></h3>
   ${BETS.length ? `<div class="kpis"><div><span class="k">bets</span><span class="v">${BETS.length}</span></div><div><span class="k">open</span><span class="v">${open}</span></div><div><span class="k">won-lost-push</span><span class="v">${won}-${lost}-${push}</span></div>
     <div><span class="k">staked (settled)</span><span class="v">$${staked.toFixed(0)}</span><span class="t">${open?'$'+BETS.filter(b=>b.status==='open').reduce((a,b)=>a+b.stake,0).toFixed(0)+' open':''}</span></div><div><span class="k">profit</span><span class="v" style="color:${ret-staked>=0?'var(--green)':'var(--red)'}">${ret-staked>=0?'+':''}$${(ret-staked).toFixed(2)}</span></div>
     <div><span class="k">ROI</span><span class="v">${staked?((ret-staked)/staked*100).toFixed(1)+'%':'–'}</span></div><div><span class="k">avg odds</span><span class="v">${avgO?avgO.toFixed(2):'–'}</span></div>
     <div><span class="k">model said / won</span><span class="v">${avgP!=null?pct(avgP,0)+' / '+pct(won/Math.max(1,won+lost),0):'–'}</span></div><div><span class="k">avg CLV</span><span class="v">${avgClv!=null?(avgClv>=0?'+':'')+(avgClv*100).toFixed(1)+'%':'–'}</span></div></div>
     ${tbl('Market', group(b=>b.legs.length>1?'parlay':(KIND[b.legs[0].kind]||b.legs[0].kind)))}${tbl('Grade at bet time', group(b=>b.grade))}
     <div class="tbl"><table><tr><th>Placed</th><th>Bet</th><th>odds</th><th>model</th><th>stake</th><th>result</th><th>CLV</th><th></th></tr>${BETS.slice().reverse().map(b=>`<tr><td>${b.ts.slice(5,10)}</td><td style="white-space:normal;text-align:left">${b.legs.map(l=>esc(l.label)).join(' + ')}<span class="t"> ${esc(b.legs[0].mu)}${b.legs.length>1?' …':''}</span></td><td>${b.odds.toFixed(2)}</td><td>${pct(b.p,0)}</td><td>$${b.stake}</td><td>${b.status==='open'?'open':(b.status==='won'?`<b style="color:var(--green)">won $${(b.ret-b.stake).toFixed(2)}</b>`:(b.status==='push'?'push':`<b style="color:var(--red)">lost</b>`))}</td><td>${b.closing?((b.odds/b.closing-1)*100).toFixed(1)+'%':''}</td><td><a href="#" data-del="${b.id}">delete</a></td></tr>`).join('')}</table></div>
     <p><button class="rbtn" style="margin:0" id="bets-csv">download CSV</button></p>` : '<p>No bets logged yet. Build a slip in the Scanner, enter your book\'s odds and stake, and press "log bet". Results grade themselves after the games; closing-line value appears once book odds are connected.</p>'}`;
  el.querySelectorAll('a[data-del]').forEach(a=>a.onclick=e=>{ e.preventDefault(); if(!confirm('Delete this bet?')) return; BETS=BETS.filter(b=>b.id!==a.dataset.del); saveBets(); renderTracker(); });
  const c=document.getElementById('bets-csv'); if(c) c.onclick=()=>{ const rows=[['placed','week','legs','game','odds','stake','model_prob','grade','status','return','closing_odds','model_version']].concat(BETS.map(b=>[b.ts,b.week,b.legs.map(l=>l.label).join(' + '),b.legs.map(l=>l.mu).join(' + '),b.odds,b.stake,b.p.toFixed(4),b.grade,b.status,b.ret==null?'':b.ret.toFixed(2),b.closing||'',b.model]));
    const blob=new Blob([rows.map(r=>r.map(x=>'"'+String(x).replace(/"/g,'""')+'"').join(',')).join('\n')], {type:'text/csv'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='nfl-bets.csv'; a.click(); }; }

// ------------------------------------------------------------- results
function renderResults(){ const keys=['desk','ml','spread','total','h1','h2','fg','qb_yds','qb_td','atd','rec_yds','rush_yds','recs']; const t={};
  for(const k of keys) for(const x of (P.picks[k]||[])){ const r=legResult(k==='desk'?legFromPick(x.market,x):legFromPick(k,x), byId[x.game_id], true); if(!r||r==='pending'||r==='void') continue; t[k]=t[k]||{hit:0,miss:0,tie:0}; t[k][r]++; }
  const any=Object.keys(t).length;
  document.getElementById('wkresults').innerHTML = `<h3>This week's best bets</h3>${any?`<div class="tbl"><table><tr><th>Market</th><th>won</th><th>lost</th><th>push</th></tr>${keys.filter(k=>t[k]).map(k=>`<tr><td>${PK_LABEL[k]}</td><td>${t[k].hit}</td><td>${t[k].miss}</td><td>${t[k].tie}</td></tr>`).join('')}</table></div>`:'<p>No lean has been decided yet. Results fill in live as the games are played (scores and box scores from ESPN), and are confirmed from the play-by-play the next morning.</p>'}`;
  fetchJSON(BASE+'scorecard.json').then(sc=>{ const S=sc.summary||{}; const ks=keys.filter(k=>S[k]);
    const u = x => x==null ? '–' : `<span style="color:${x>=0?'var(--green)':'var(--red)'}">${x>=0?'+':''}${x.toFixed(2)}</span>`;
    const T=sc.total||null;
    document.getElementById('track').innerHTML = `<h3>Track record, every published week</h3>${ks.length?`<div class="tbl"><table><tr><th>Market</th><th>won</th><th>lost</th><th>push</th><th>rate</th><th>units</th><th>ROI</th></tr>${ks.map(k=>`<tr><td>${PK_LABEL[k]}</td><td>${S[k].won}</td><td>${S[k].lost}</td><td>${S[k].push}</td><td>${S[k].rate!=null?pct(S[k].rate):'–'}</td><td>${u(S[k].units)}</td><td>${S[k].roi!=null?evTxt(S[k].roi):'–'}</td></tr>`).join('')}${T?`<tr><td><b>All</b></td><td>${T.won}</td><td>${T.lost}</td><td>${T.push}</td><td>${(T.won+T.lost)?pct(T.won/(T.won+T.lost)):'–'}</td><td>${u(T.units)}</td><td>${T.roi!=null?evTxt(T.roi):'–'}</td></tr>`:''}</table></div><p class="small">updated ${esc(sc.updated_utc)}. One unit per best bet at the DraftKings price shown before kickoff.</p>`:'<p>No completed week yet.</p>'}`; })
  .catch(()=>{ document.getElementById('track').innerHTML='<h3>Track record</h3><p>Not available yet.</p>'; });
  fetchJSON(BASE+'weeks.json').then(w=>{ document.getElementById('weeklist').innerHTML=(w.weeks||[]).map(x=>`<a class="${x.name===(P.season+'-w'+String(P.week).padStart(2,'0'))?'now':''}" href="${BASE}weeks/${x.name}.html">${x.season} week ${x.week}</a>`).join(''); }).catch(()=>{}); }

// ------------------------------------------------------------- about
function renderAbout(){ const el=document.getElementById('validation'); const C=M.cfg||{};
  if(!V){ el.innerHTML='<h3>Validation</h3><p>The walk-forward backtest has not been published yet.</p>'; }
  else { const keys=[['moneyline','Moneyline'],['spread','Spread'],['total','Total'],['h1_total','1st half total'],['h2_total','2nd half total'],['fg_over0.5','Team FGs o0.5'],['fg_over1.5','Team FGs o1.5'],['fg_over2.5','Team FGs o2.5'],['qb_yards','QB passing yards'],['qb_td_over0.5','QB TDs o0.5'],['qb_td_over1.5','QB TDs o1.5'],['qb_td_over2.5','QB TDs o2.5'],['anytime_td','Anytime TD'],['rec_yds','Receiving yards'],['rush_yds','Rushing yards'],['recs','Receptions']];
    const row = (S,k,l) => { const m=S[k]; if(!m||!m.n) return ''; const v=m.verdict; return `<tr><td>${l}</td><td>${m.n.toLocaleString()}</td><td>${m.ll_model}</td><td>${m.ll_base}</td><td>${m.brier_model??''}</td><td>${m.brier_base??''}</td><td>${m.accuracy!=null?pct(m.accuracy,1):''}</td><td>${m.gain>=0?'+':''}${m.gain} ± ${m.se}</td><td><span class="verd ${v==='beats baseline'?'beats':(v==='marginal'?'marginal':'none')}">${v}</span></td></tr>`; };
    const cal = (k,l) => { const m=V.pooled[k]; if(!m||!m.calibration||!m.calibration.length) return ''; return `<details style="margin:4px 0"><summary class="small" style="cursor:pointer">${l}: predicted vs actual by probability band</summary><div class="tbl"><table><tr><th>band</th><th>predicted</th><th>actual</th><th>n</th></tr>${m.calibration.map((b,i)=>`<tr><td>${i+1}</td><td>${pct(b.p)}</td><td>${pct(b.hit)}</td><td>${b.n.toLocaleString()}</td></tr>`).join('')}</table></div></details>`; };
    const bets = m => (m && m.bets) ? m.bets.map(b=>`${pct(b.threshold,0)}+: ${b.bets} bets, ${b.win_rate!=null?pct(b.win_rate):'–'} won, ROI ${b.roi!=null?(b.roi>=0?'+':'')+(b.roi*100).toFixed(1)+'%':'–'}`).join(' · ') : '';
    const B=V.pooled.blend||{};
    el.innerHTML = `<h3>Walk-forward validation · seasons ${esc((V.seasons||[]).join(', '))}</h3>
    <p>Every week of each test season was predicted using only games played before it. Log loss (lower is better) is compared with a baseline that needs no model; the difference is the model's gain, with its standard error. "Beats baseline" means the gain is more than two standard errors.</p>
    <div class="tbl"><table><tr><th>Market</th><th>n</th><th>log loss</th><th>baseline</th><th>Brier</th><th>baseline</th><th>right side</th><th>gain (log loss)</th><th>verdict</th></tr>${keys.map(([k,l])=>row(V.pooled,k,l)).join('')}</table></div>
    <p class="small">Calibration: each market's predictions split into ten bands of equal size; a well-calibrated model's "actual" matches its "predicted".</p>${keys.map(([k,l])=>cal(k,l)).join('')}
    <p class="small">Baselines: moneyline = the closing line with the vig removed; spread and total = 50/50 at the closing number; halves and field goals = the hit rate of the same line over the same games (known only in hindsight, which flatters the baseline); quarterback yards = 50/50 at his recent average; touchdowns = a Poisson at his recent rate; anytime touchdown = each player's own recent rate.</p>
    <p class="small">Betting the model alone against the closing spread: ${bets(V.pooled.spread)}.<br>Against the closing total: ${bets(V.pooled.total)}.</p>
    <p class="small">How much of the model's disagreement with the closing line to keep (regression of the result on model minus line): margin w = ${B.margin?B.margin.w+' ± '+B.margin.se:'n/a'}, total w = ${B.total?B.total.w+' ± '+B.total.se:'n/a'}. In use: margin ${(M.blend||{}).margin??0}, total ${(M.blend||{}).total??0}.</p>
    <p class="small">Moneyline and spread on the cards: the simulated margins are about 7% wider than real NFL margins around the closing spread, which on its own understated favourites (a 7.5-point favourite near 70% where the market says 78%). Each game's simulated outcomes are therefore reweighted to match the market's vig-free moneyline and spread prices; walk-forward this matched or beat the raw simulation in both test seasons.</p>
    ${V.pooled.qb_yards?`<p class="small">Quarterback yards, mean absolute error: model median ${V.pooled.qb_yards.mae_model_median} vs his recent average ${V.pooled.qb_yards.mae_recent_avg}.</p>`:''}
    ${V.pooled.pregame_candidates?`<p class="small">Player markets in the test use pregame information only: touchdown and yardage candidates come from that week's active roster and the official injury report (Out / Doubtful removed), the same way the live page picks them, in ${V.pooled.pregame_candidates.from_pregame_rosters} of ${V.pooled.pregame_candidates.games} games. A candidate who did not take the field is a void bet at the book and is not scored. Listed candidates scored ${V.pooled.td_coverage!=null?pct(V.pooled.td_coverage,1):'n/a'} of their teams' offensive touchdowns.</p>`:''}
    <p class="small">One joint distribution: the halves, field goals, passing and player markets are read from the same market-reweighted simulations as the moneyline and spread, and the slip prices same-game parlays from the same weighted samples.</p>
    <h3 style="margin-top:12px">By season</h3><div class="tbl"><table><tr><th>Season</th>${keys.slice(0,9).map(([,l])=>`<th>${l}</th>`).join('')}</tr>${Object.entries(V.by_season||{}).map(([s,S])=>`<tr><td>${s}</td>${keys.slice(0,9).map(([k])=>{const m=S[k]; return `<td>${m&&m.n?(m.gain>=0?'+':'')+m.gain:''}</td>`;}).join('')}</tr>`).join('')}</table></div>
    <p class="small">generated ${esc(V.generated_utc||'')} · ${(V.sims||0).toLocaleString()} sims per game in the backtest · <a href="${BASE}validation.json">full validation JSON</a> · <a href="${BASE}factors.json">factor switches and tested changes</a> · <a href="https://github.com/Moneyg604/nhl-early-goal/tree/main/nfl">model source code</a></p>`; }
  document.getElementById('method').innerHTML = `<h3>How the numbers are made</h3>
  <p><b>Data.</b> nflverse play-by-play for every regular-season game (current season refreshed every run), the nflverse schedule with the market's spread, total and moneylines, the official injury report, depth charts and weekly rosters; Open-Meteo for kickoff weather at outdoor stadiums; ESPN for live scores and box scores.</p>
  <p><b>The league table.</b> Every drive of the last three seasons is classified by half, how it started (kickoff, punt, turnover), time left in the half (six buckets) and score margin (seven states). For each situation the table holds the share of drives ending in a touchdown, field goal, missed field goal, punt, turnover, turnover on downs, end of half, defensive touchdown or safety, plus how long they took and how many dropbacks they used.</p>
  <p><b>Teams.</b> A team's offense is its touchdowns, field-goal tries and turnovers against what the league table expects from the same drives, as log odds ratios shrunk toward zero (${C.k_drive_team||300} pseudo-drives for touchdowns and turnovers, ${C.k_drive_fg||600} for field-goal tries). The same for the defense, pace, dropbacks per drive and passing yards per dropback. A game last season counts ${Math.round(((C.prior_season_weights||[0.35])[0])*100)}% of a current-season game, two seasons back ${Math.round(((C.prior_season_weights||[0,0.15])[1])*100)}%. Each of these settings won a walk-forward comparison (Research tab).</p>
  <p><b>Quarterbacks and kickers.</b> The starting quarterback's own yards per dropback and touchdown-pass share replace the team's when he has enough dropbacks; a mid-season change applies the measured effect of new starters. The kicker's makes against the league curve for his distances shift field-goal accuracy.</p>
  <p><b>Simulation.</b> ${(M.sims||100000).toLocaleString()} games per matchup, drive by drive, with overtime. When the book's spread and total are known the scoring rates are shifted until the simulation's mean margin and total match them (plus the measured share of the model's own disagreement). Every market is read from the same simulated games, so halves, field goals, quarterback lines and touchdown scorers agree with each other and with the game line.</p>
  <p><b>Anytime touchdown.</b> Each player's share of the team's passing and rushing touchdowns is his own rate shrunk toward his usage (half overall share, half red-zone share), rescaled across the active, healthy players; the probability is computed against every simulated game's touchdown count.</p>
  <p><b>Best bets.</b> For every bet DraftKings lists, each book's two-way price has its margin removed. Books post different lines, so each one is moved onto DraftKings' line by shifting the simulation's distribution for that stat (its spread and where pushes fall) until it reproduces that book's price at that book's line; the consensus is the weighted median (Pinnacle counts double). The simulation may then move the market's chance by at most 4 points, less when the two disagree by more than 10 points and not at all past 20 (a disagreement that large with several books is usually something the model cannot see). Game lines get no model nudge. Expected value is that chance against DraftKings' price; a bet is listed as good at +2% or better with at least three books quoting it (+5% for anytime touchdowns, whose one-sided prices need an assumed margin; never past +700). Bets lock at kickoff and are graded at the price shown.</p>
  <p><b>Limits.</b> No play-level personnel model (offensive line, cornerbacks), no in-game injuries, no garbage-time substitutions; questionable players are included and flagged. The market already prices most of this, which is why the game lines follow it.</p>`;
  document.getElementById('foot').innerHTML = `Model ${esc(M.model_version)} · generated ${esc(P.generated_utc)} in ${M.seconds}s · <a href="${BASE}weeks/${P.season}-w${String(P.week).padStart(2,'0')}.json">payload JSON</a> · <a href="${BASE}weeks/${P.season}-w${String(P.week).padStart(2,'0')}.csv">CSV</a>`; }

// ------------------------------------------------------------- best bets (DraftKings, ranked by win chance; the bot's judgment on top)
const BB = P.best_bets || null;
const BOT = P.bot || null;
const BTZ = 'America/Toronto';
const bIso = s => { s=String(s||''); if(/^\d{4}-\d\d-\d\d \d\d:\d\d UTC$/.test(s)) s=s.replace(' ','T').replace(' UTC','Z'); return new Date(/T\d\d:\d\dZ$/.test(s) ? s.replace('Z',':00Z') : s); };
const bNow = () => new Date().toISOString().slice(0,16)+'Z';
const bKick = s => s ? bIso(s).toLocaleString('en-US',{timeZone:BTZ,weekday:'short',month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})+' ET' : '';
const bStamp = s => { if(!s) return 'not available'; const d=bIso(s); return isNaN(d) ? esc(s) : d.toLocaleString('en-US',{timeZone:BTZ,month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})+' ET'; };
const bAgo = s => { if(!s) return 'not yet'; const m=Math.round((Date.now()-bIso(s))/60000); if(m<1) return 'just now'; if(m<60) return m+' min ago'; const h=Math.round(m/60); if(h<48) return h+' h ago'; return Math.round(h/24)+' days ago'; };
const evTxt = ev => ev==null ? '–' : `${ev>=0?'+':''}${(ev*100).toFixed(1)}%`;
const BKIND = {ml:'Moneyline', spread:'Spread', total:'Game total', h1:'1st half total', h2:'2nd half total', qb_yds:'Passing yards', qb_td:'Passing TDs', rec_yds:'Receiving yards', rush_yds:'Rushing yards', recs:'Receptions', atd:'Anytime TD', fg:'Kicker field goals'};
const DESK = (BOT && BOT.desk && BOT.desk.ok) ? BOT.desk : null;
const BGROUPS = [['desk','Research desk'],['bot',"Bot's picks"],['tdboard','Anytime TD'],['winners','Team winners'],['spreads','Spreads'],['totals','Totals'],['props','Player props'],['kickers','Kicker FGs'],['alts','Alt lines']];
const BPRICE = {attractive:['Attractive','pos'], fair:['Fair','mid'], poor:['Poor','neg'], unreliable:['Unreliable','neg'], 'no price':['Not in feed','mid']};
const BOARD = ((BB&&BB.ranked)||[]).concat((BOT&&BOT.extra)||[]);
const BYID = {}; BOARD.forEach(b=>BYID[b.id]=b);
let BF = {grp:DESK?'desk':'bot', kind:'all', game:'all', sort:'p', more:0};
try{ Object.assign(BF, JSON.parse(localStorage.getItem('gs_nfl_best2')||'{}'), {more:0}); }catch(e){}
const saveBF = () => { try{ localStorage.setItem('gs_nfl_best2', JSON.stringify({grp:BF.grp, kind:BF.kind, game:BF.game, sort:BF.sort})); }catch(e){} };
let SHOW_COMBINE = false;
function bWhy(b){ const I=b.inputs||{}; const parts=[]; const n=b.books;
  const ls=(I.lines||[]).filter(x=>x!=null); const lines = ls.length>1 ? `, lines ${ls[0]} to ${ls[ls.length-1]}` : '';
  parts.push(`<b>Market ${pct(b.p_market)}</b> (${n} book${n===1?'':'s'}, no vig${lines}${b.one_sided?`, ${Math.round((I.margin_assumed||0.07)*100)}% margin assumed on one-sided prices`:''})`);
  if(b.p_model!=null) parts.push(`<b>simulation ${pct(b.p_model)}</b>: ${esc(String(b.note||'').replace(/^model \d+% /,''))}`); else parts.push(esc(b.note||''));
  if(I.market_median!=null && I.model_median!=null && ['qb_yds','rec_yds','rush_yds','recs'].includes(b.kind)) parts.push(`market median ${I.market_median}, simulation ${I.model_median}`);
  return parts.join(' · '); }
function bBooks(b){ const rows=(b.inputs||{}).books||[]; if(!rows.length) return '';
  const s1 = ('home' in rows[0]) ? 'home' : 'over', s2 = s1==='home'?'away':'under';
  const h = b.kind==='atd' ? '<tr><th>Book</th><th>Yes</th><th>No-vig</th></tr>' : `<tr><th>Book</th><th>Line</th><th>${s1}</th><th>${s2}</th><th>No-vig ${s1}</th></tr>`;
  const r = rows.slice().sort((a,c)=>(a.book==='DraftKings'?-1:(c.book==='DraftKings'?1:0))).map(x=> b.kind==='atd'
     ? `<tr class="${x.book==='DraftKings'?'dk':''}"><td>${esc(x.book)}</td><td>${x.yes!=null?x.yes.toFixed(2):'–'}</td><td>${pct(x.nv)}</td></tr>`
     : `<tr class="${x.book==='DraftKings'?'dk':''}"><td>${esc(x.book)}</td><td>${x.line!=null?x.line:'–'}</td><td>${x[s1]!=null?x[s1].toFixed(2):'–'}</td><td>${x[s2]!=null?x[s2].toFixed(2):'–'}</td><td>${pct(x.nv)}</td></tr>`).join('');
  return `<div class="bt"><table>${h}${r}</table></div>`; }
function bCard(b, i){
  const A=b.analysis||{}; const fl = (b.flags||[]).length ? `<div class="warn">⚠ ${b.flags.map(esc).join(' · ')}</div>` : '';
  const pr = BPRICE[b.price]||BPRICE.fair; const cf=b.conf||{score:50,label:'medium'};
  const stale = b.priced_at && (Date.now()-bIso(b.priced_at) > 12*3600000);
  const st=A.stamps||{}; const inS = SLIP.find(s=>s.id===b.id);
  const lineTxt = b.line!=null ? (b.kind==='spread' ? `${b.line>0?'+':''}${b.line}` : `${b.side} ${b.line}`) : (b.kind==='atd'?'anytime':(b.kind==='ml'?'moneyline':''));
  const J=b.judge;
  return `<article class="bb ${b.price==='attractive'?'good':''} ${inS?'insl':''}">
   <div class="top"><span class="rk">${i}</span><div class="ti"><b>${esc(b.label)}</b><span class="t">${esc(b.mu)} · ${esc(bKick(b.kick))} · ${esc(b.market)}${lineTxt?' · line '+esc(lineTxt):''}</span></div>
   <div class="evb pos">${pct(b.p,0)}<span class="k">Win chance</span></div></div>
   <div class="three">
     <div><span class="k">Model probability</span><span class="v">${pct(b.p)}</span><span class="s">fair odds ${b.fair_odds?b.fair_odds.toFixed(2):'–'}${b.fair_odds?' ('+dec2am(b.fair_odds)+')':''}${b.p_model!=null&&b.p_market!=null?` · sim ${pct(b.p_model,0)}, market ${pct(b.p_market,0)}`:(b.p_market!=null?' · market-derived':' · simulation only')}</span></div>
     <div><span class="k">Evidence confidence</span><span class="v"><span class="cf ${cf.label}">${cf.label}</span> ${cf.score}</span><span class="s">${b.books||0} book${b.books===1?'':'s'} · data tier ${esc(b.tier||'?')} · rates data quality, not win likelihood</span></div>
     <div><span class="k">DraftKings price</span><span class="v ${pr[1]}">${pr[0]}</span><span class="s">${b.odds!=null?`${b.odds.toFixed(2)} (${dec2am(b.odds)}) · EV ${evTxt(b.ev)}`:'not in the odds feed: check DraftKings'}${stale?' · <b style="color:var(--amber)">stale</b>':''}</span></div>
   </div>
   ${b.desk?`<div class="chk"><span class="c ok">★ Research desk ${pct(b.desk.p,0)} · grade ${esc(b.desk.grade)}</span></div>`:''}
   ${J?`<div class="chk">${J.checks.map(c=>`<span class="c ${c.ok===true?'ok':(c.ok===false?'bad':'na')}" title="${esc(c.txt)}">${c.ok===true?'✓':(c.ok===false?'✗':'·')} ${esc(c.name)}</span>`).join('')}</div>`:''}
   ${fl}
   <div class="brow"><details class="books"><summary>Research, risk, formulas and every book's price</summary>
     ${b.desk?dBlock(b.desk):''}
     ${J?`<div class="chkl"><b>Bot's checks (score ${J.score.toFixed(2)})</b><ul>${J.checks.map(c=>`<li class="${c.ok===true?'ok':(c.ok===false?'bad':'na')}">${c.ok===true?'✓':(c.ok===false?'✗':'·')} <b>${esc(c.name)}:</b> ${esc(c.txt)}</li>`).join('')}</ul></div>`:''}
     ${A.proj?`<div class="proj"><b>Projection:</b> ${esc(A.proj)}${A.range?` · <span>${esc(A.range)}</span>`:''}</div>`:''}
     ${(A.reasons||[]).length?`<ul class="rs">${A.reasons.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
     ${A.risk?`<div class="risk"><b>Biggest risk:</b> ${esc(A.risk)}</div>`:''}
     ${(A.personnel||[]).length?`<div class="pers"><b>Personnel:</b> ${A.personnel.map(esc).join(' · ')}</div>`:''}
     ${(A.formula||[]).length?`<div class="fm"><b style="color:var(--text)">Formulas</b>${A.formula.map(x=>`<p>${esc(x)}</p>`).join('')}</div>`:''}
     ${(A.limits||[]).length?`<div class="lim"><b>Limits:</b> ${A.limits.map(esc).join(' · ')}</div>`:''}
     <div class="stamps">Sources: odds ${bStamp(st.odds||b.priced_at)} · injury report ${bStamp(st.injuries)} · usage / snaps ${bStamp(st.usage)} (play-by-play through ${esc(st.data_through||'?')}) · weather forecast ${bStamp(st.weather)} · simulation run ${bStamp(st.model)}</div>
     ${b.p_market!=null?`<div class="why">${bWhy(b)}</div>`:''}${bBooks(b)}</details>${SEL_BY[b.id]?`<button class="addb" data-add="${esc(b.id)}">${inS?'remove from slip':'+ slip'}</button>`:''}</div></article>`; }
function bCombine(C){ const R=(BOT||{}).rules||{}; if(!C||!C.n) return `<p class="empty">No combined top ${R.legs||6}: fewer than ${R.legs||6} qualifying legs this week.</p>`;
  const band=C.odds_band||R.combine_odds||[1.35,2.2];
  const rows = C.legs.map((l,i)=>`<tr><td>${i+1}</td><td class="lbl"><b>${esc(l.label)}</b><br><span style="color:var(--dim)">${esc(l.mu)} · ${esc(bKick(l.kick))}</span><br><span style="color:var(--muted)">${esc(l.basis)}${l.why?' · '+esc(String(l.why).split(';')[0]):''}</span></td><td>${l.odds!=null?l.odds.toFixed(2):'–'}</td><td>${pct(l.p,0)}</td><td>${l.p_model!=null?pct(l.p_model,0):'–'}</td></tr>`).join('');
  return `<article class="bb parlay"><div class="top"><span class="rk">6</span><div class="ti"><b>The bot's top ${C.n} this week</b><span class="t">the highest-scoring legs across the lists by the bot's judgment · one per game · real DraftKings prices ${band[0]} to ${band[1]} · no anytime touchdowns · ${C.n_candidates||0} eligible${C.complete?'':' · only '+C.n+' legs qualify this week'}</span></div>
    <div class="evb ${C.ev>=0?'pos':'neg'}">${C.odds.toFixed(2)}<span class="k">combined odds</span></div></div>
    <div class="three"><div><span class="k">Chance all legs win</span><span class="v">${pct(C.prob,1)}</span><span class="s">legs treated as independent (different games)</span></div>
      <div><span class="k">Fair combined odds</span><span class="v">${C.fair_odds?C.fair_odds.toFixed(2):'–'}</span><span class="s">1 ÷ chance</span></div>
      <div><span class="k">Parlay EV</span><span class="v ${C.ev>=0?'pos':'neg'}">${evTxt(C.ev)}</span><span class="s">DraftKings' cut compounds across legs</span></div></div>
    <div class="bt"><table><tr><th>#</th><th class="lbl">Leg</th><th>DK</th><th>Win</th><th>Sim</th></tr>${rows}</table></div>
    <div class="why">Singles or a parlay, as you like: a ${C.n}-leg parlay at these probabilities wins about one time in ${C.prob>0?Math.round(1/C.prob):'–'}. Check each leg's DraftKings price before placing it; a scratched player voids that leg at DraftKings.</div></article>`; }
function dSrc(list){ return (list||[]).map(x=>`${x.url?`<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a>`:esc(x.name)} (${esc(bStamp(x.fetched))})`).join(' · '); }
function dBlock(D){ return `<div class="deskr"><h4>Research desk · ${pct(D.p,0)} to win · grade ${esc(D.grade)} · evidence ${esc(D.evidence)} · confidence ${D.confidence}</h4>
   <p><b>Verdict:</b> ${esc(D.verdict)}</p>
   ${(D.inputs||[]).length?`<p><b>Inputs</b></p><ul>${D.inputs.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
   ${(D.arithmetic||[]).length?`<p><b>Arithmetic</b></p><ul class="ar">${D.arithmetic.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
   ${(D.pros||[]).length?`<p><b>For</b></p><ul class="pr">${D.pros.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
   ${(D.risks||[]).length?`<p><b>Risks</b></p><ul class="ri">${D.risks.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
   <div class="src">Sources: ${dSrc(D.sources)||'none listed'}${D.odds_source?` · DraftKings price ${D.odds!=null?D.odds.toFixed(2):'–'} (${esc(D.odds_source==='feed'?'odds feed':(D.odds_source==='draftkings'?'checked on DraftKings':'not verified'))})`:''}</div></div>`; }
function dLeg(x){ const o={kind:x.kind, side:x.side, line:x.line, tside:x.tside, who:x.who, pid:x.pid, team:x.team, game_id:x.game_id}; if(x.kind==='atd'){ o.side='yes'; } return o; }
function dCard(x, i){ const g=byId[x.game_id]; const now=bNow(); const started = x.kick && x.kick <= now;
  let r = null; try{ r = started ? legResult(dLeg(x), g, true) : null; }catch(e){ r=null; }
  const live = started && (!r || r==='pending');
  const res = started ? (r && r!=='pending' ? `<span class="res ${r}">${r==='hit'?'won':(r==='miss'?'lost':(r==='tie'?'push':'void'))}</span>` : `<span class="res live">in play</span>`) : '';
  const B=x.board||{}; const bp = B.p!=null ? ` · site ${pct(B.p,0)}${B.p_model!=null?' (sim '+pct(B.p_model,0)+')':''}` : ' · not on the site board';
  const osrc = {feed:'odds feed', draftkings:'checked on DraftKings', unverified:'not verified'}[x.odds_source]||'';
  const lineTxt = x.line!=null ? (x.kind==='spread' ? `${x.line>0?'+':''}${x.line}` : `${x.side} ${x.line}`) : (x.kind==='atd'?'anytime':(x.kind==='ml'?'moneyline':''));
  const inS = SLIP.find(s=>s.id===x.id);
  return `<article class="bb desk ${inS?'insl':''}">
   <div class="top"><span class="rk">${i}</span><div class="ti"><b>${esc(x.label)}<span class="gr ${esc(x.grade)}">${esc(x.grade)}</span>${res}</b><span class="t">${esc(x.mu)} · ${esc(bKick(x.kick))} · ${esc(BKIND[x.kind]||x.kind)}${lineTxt?' · line '+esc(lineTxt):''}</span></div>
   <div class="evb pos">${pct(x.p,0)}<span class="k">Desk win chance</span></div></div>
   <div class="three">
     <div><span class="k">DraftKings price</span><span class="v ${x.ev>=0.02?'pos':(x.ev>=-0.03?'mid':'neg')}">${x.odds.toFixed(2)}</span><span class="s">${dec2am(x.odds)} · ${esc(osrc)} · EV at the desk's chance ${evTxt(x.ev)}</span></div>
     <div><span class="k">Evidence</span><span class="v"><span class="cf ${x.evidence==='measured'?'high':(x.evidence==='partial'?'medium':'low')}">${esc(x.evidence)}</span> ${x.confidence}</span><span class="s">fair odds ${x.fair_odds.toFixed(2)}${bp}</span></div>
     <div><span class="k">Biggest risk</span><span class="v" style="font-size:12.5px;white-space:normal;font-family:var(--body);font-weight:500;color:#ffd37a">${esc((x.risks||[])[0]||'ordinary variance')}</span></div>
   </div>
   <div class="brow"><details class="books"><summary>Verdict, inputs, arithmetic, risks and sources</summary>${dBlock(x)}</details>${SEL_BY[x.id]?`<button class="addb" data-add="${esc(x.id)}">${inS?'remove from slip':'+ slip'}</button>`:''}</div></article>`; }
function bDesk(){ const D=DESK; if(!D) return `<p class="empty">No research desk file for this week yet. The desk runs before each kickoff window (Thursday, Saturday evening, Sunday morning, Monday afternoon).</p>`;
  const now=bNow();
  const rows=(D.selections||[]).filter(x=>BF.game==='all'||x.game_id===BF.game);
  const up=rows.filter(x=>x.kick>now), done=rows.filter(x=>x.kick<=now);
  let h = `<div class="deskhead"><h2>★ Research desk · ${D.n} selection${D.n===1?'':'s'}</h2>
    <p>${esc(D.analyst||'Research desk')} read the week's news (practice reports, Friday designations, beat-writer notes, weather, line moves) and wrote every selection up with its inputs, its arithmetic and its risks. Ranked by the desk's own win chance; DraftKings prices ${(D.band||[1.35,2.2])[0].toFixed(2)} to ${(D.band||[1.35,2.2])[1].toFixed(2)} only. Open a card for the full write-up. The desk's chance is a judgment, not a simulation: its record is graded on its own line in Results.</p>
    ${D.summary?`<p>${esc(D.summary)}</p>`:''}<p class="st">Desk run ${esc(bStamp(D.generated))} (${esc(bAgo(D.generated))}) · site simulation ${esc(bStamp(((BOT||{}).stamps||{}).model))}</p></div>`;
  h += up.length ? up.map((x,i)=>dCard(x,i+1)).join('') : `<p class="empty">No desk selection for the games still to play${BF.game!=='all'?' in this game':''}.</p>`;
  if(done.length) h += `<div class="bbsep">Already kicked off</div>` + done.map((x,i)=>dCard(x,up.length+i+1)).join('');
  const dec=(D.declined||[]); if(dec.length) h += `<h2>Looked at and declined</h2><div class="bt"><table><tr><th class="lbl">Candidate</th><th class="lbl">Why not</th></tr>${dec.map(x=>`<tr><td class="lbl"><b>${esc(x.label)}</b></td><td class="lbl" style="white-space:normal">${esc(x.why)}</td></tr>`).join('')}</table></div>`;
  const gn=Object.entries(D.games||{}).map(([gid,v])=>[byId[gid],v]).filter(([g])=>g).sort((a,c)=>(a[0].kickoff_utc||'').localeCompare(c[0].kickoff_utc||''));
  if(gn.length) h += `<h2>Game notes</h2>` + gn.map(([g,v])=>`<details class="gnotes"><summary>${esc(g.away)} @ ${esc(g.home)} · ${esc(bKick(g.kickoff_utc))}</summary>${v.weather?`<ul><li><b>Weather:</b> ${esc(v.weather)}</li></ul>`:''}${(v.injuries||[]).length?`<ul>${v.injuries.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}${(v.notes||[]).length?`<ul>${v.notes.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}${(v.sources||[]).length?`<div class="small" style="color:var(--dim);margin:0 0 8px">Sources: ${dSrc(v.sources)}</div>`:''}</details>`).join('');
  return h; }
function bBot(up){
  const B = BOT||{}; const now=bNow(); const cats=B.cats||{};
  let h = `<p class="note">The bot runs the checks an analyst would on every bet: this season's form against the line, the matchup rank, the game script from the spread, injuries and workload shifts, weather, how fresh the price is, and how far the simulation sits from the market. Each list shows its best bets by that judgment, with the checks on every card. Open a card's drop-down for the full reasoning.</p>`;
  h += `<div style="margin:6px 0 12px"><button type="button" class="combine" id="combine">${SHOW_COMBINE?'Hide the top 6':'Combine into the top 6'}</button></div>`;
  if(SHOW_COMBINE) h += bCombine(B.combine);
  const order=['passing','receiving','rushing','totals','moneyline','spread','fieldgoals'];
  for(const key of order){ const c=cats[key]; if(!c) continue;
    const bs=(c.ids||[]).map(i=>BYID[i]).filter(b=>b && b.kick>now && (BF.game==='all'||b.game_id===BF.game));
    h += `<h2>${esc(c.label)} <small style="color:var(--dim);font-size:13px;font-weight:500">best ${c.n}</small></h2>`;
    if((key==='receiving'||key==='rushing') && !bs.some(b=>b.odds!=null)) h += `<p class="note">DraftKings' receiving and rushing props were not in this week's odds pull. These are the simulation's projections at its own fair line: compare DraftKings' line by hand.</p>`;
    if(key==='fieldgoals') h += `<p class="note">DraftKings' kicker market is not in the odds feed: fair odds only, check DraftKings' price.</p>`;
    h += bs.length ? bs.map((b,i)=>bCard(b,i+1)).join('') : `<p class="empty">Nothing passes the checks in this view.</p>`; }
  const leans = (B.leans||[]).filter(p=>p.kick>now && (BF.game==='all'||p.game_id===BF.game));
  h += `<h2>Where the simulation disagrees with the market</h2><p class="note">The simulation alone (before it is anchored to the market) prefers these sides. Leans, not proven edges; underdogs marked.</p>`;
  h += leans.length ? `<div class="bt"><table><tr><th class="lbl">Lean</th><th>DK</th><th>Sim alone</th><th>Market</th><th>Blended</th></tr>${leans.map(l=>`<tr><td class="lbl">${esc(l.label)}${l.underdog?' <span class="cf medium">underdog</span>':''}<br><span style="color:var(--dim)">${esc(l.mu)} · ${esc(bKick(l.kick))}</span><br><span style="color:var(--muted)">${esc(l.why)}</span></td><td>${l.odds.toFixed(2)}</td><td>${l.p_pure!=null?pct(l.p_pure,0):'–'}</td><td>${l.p_market!=null?pct(l.p_market,0):'–'}</td><td>${pct(l.p,0)}</td></tr>`).join('')}</table></div>` : `<p class="empty">No material disagreement this week.</p>`;
  return h; }
function bTd(){ const now=bNow(); const rows=((BOT||{}).tds||[]).filter(t=>t.kick>now && (BF.game==='all'||t.game_id===BF.game));
  let h = `<p class="note">Every anytime-touchdown price DraftKings posts this week, every team, every player, with the blended chance of a touchdown, the simulation's own chance and the market's. Sorted by game, then chance. Not part of the bot's pick lists.</p>`;
  if(!rows.length) return h + `<p class="empty">No anytime-touchdown prices for upcoming games.</p>`;
  let g=''; let body='';
  for(const t of rows){ if(t.mu!==g){ g=t.mu; body += `<tr class="g"><td colspan="7">${esc(t.mu)} · ${esc(bKick(t.kick))}</td></tr>`; }
    body += `<tr><td>${esc(t.who)}${(t.flags||[]).length?' ⚠':''}</td><td>${esc(t.team)} ${esc(t.pos||'')}</td><td><b>${pct(t.p,0)}</b></td><td>${t.p_model!=null?pct(t.p_model,0):'–'}</td><td>${t.p_market!=null?pct(t.p_market,0):'–'}</td><td>${t.odds.toFixed(2)} <span style="color:var(--dim)">${dec2am(t.odds)}</span></td><td class="${t.price==='attractive'?'pos':(t.price==='poor'?'neg':'')}">${esc(t.price)}</td></tr>`; }
  return h + `<div class="bt"><table class="tdb"><tr><th>Player</th><th>Team</th><th>TD chance</th><th>Sim</th><th>Market</th><th>DraftKings</th><th>Price</th></tr>${body}</table></div>`; }
function renderBest(){ const el=document.getElementById('best'); if(!el) return;
  if(!BB){ el.innerHTML='<div class="panel"><p>Best bets appear once the odds feed has DraftKings prices for this week.</p></div>'; return; }
  const now = bNow();
  const up = BOARD.filter(b => b.kick && b.kick > now);
  const games = P.games.filter(g => g.kickoff_utc && g.kickoff_utc > now && (g.odds||{}).fetched).map(g=>({game_id:g.game_id, mu:`${g.away} @ ${g.home}`, kick:g.kickoff_utc, props:!!((g.odds||{}).props_fetched)})).sort((a,c)=>a.kick.localeCompare(c.kick));
  if(!DESK && BF.grp==='desk') BF.grp = BOT ? 'bot' : 'winners';
  if(!BOT && BF.grp==='bot') BF.grp='winners';
  if(!['bot','tdboard','desk'].includes(BF.grp) && !up.some(b=>b.group===BF.grp)) BF.grp = DESK ? 'desk' : (BOT ? 'bot' : 'winners');
  const kinds = [...new Set(up.filter(b=>b.group===BF.grp).map(b=>b.kind))];
  if(BF.kind!=='all' && !kinds.includes(BF.kind)) BF.kind='all';
  if(BF.game!=='all' && !games.find(g=>g.game_id===BF.game)) BF.game='all';
  let rows = up.filter(b => b.group===BF.grp && (BF.kind==='all'||b.kind===BF.kind) && (BF.game==='all'||b.game_id===BF.game));
  const key = {p:b=>-b.p, ev:b=>-(b.ev==null?-9:b.ev), conf:b=>-((b.conf||{}).score||0)}[BF.sort]||(b=>-b.p);
  rows.sort((a,c)=>key(a)-key(c) || ((c.ev==null?-9:c.ev)-(a.ev==null?-9:a.ev)));
  const attractive = up.filter(b=>b.price==='attractive').length;
  const ages = up.filter(b=>b.priced_at).map(b=>b.priced_at).sort(); const oldest = ages[0];
  const stale = (oldest && Date.now()-bIso(oldest) > 12*3600000) ? `<p class="stale"><b>These DraftKings prices are from ${esc(bKick(oldest))}.</b> Lines move, so check that DraftKings still shows the same price before you bet. Fresh prices arrive about 75 minutes before each kickoff window.</p>` : '';
  const soon = new Date(Date.now()+4*86400000).toISOString().slice(0,16)+'Z';
  const noProps = games.filter(g=>!g.props && g.kick < soon).length;
  const SS=(BOT||{}).stamps||{};
  const fresh = `<p class="note"><b>Data as of (ET):</b> DraftKings game lines ${bStamp(BB.odds_fetched)} · player props ${bStamp(BB.props_fetched_oldest)} · injury report ${bStamp(SS.injuries)} · usage and snap counts ${bStamp(SS.usage)} (play-by-play through ${esc(SS.data_through||'?')}) · weather forecast ${bStamp(SS.weather)} · simulation run ${bStamp(SS.model)}.`
    + (noProps ? ` Player props for ${noProps} game${noProps===1?' are':'s are'} not priced yet: they are pulled about 75 minutes before each kickoff window.` : '') + `</p>`;
  const stats = `<div class="bbhead"><span><b>${up.length}</b> DraftKings markets across <b>${games.length}</b> games</span><span><b>${attractive}</b> attractively priced</span><span>${BOT?esc(BOT.week_label||''):''}</span></div>`;
  const bar = `<div class="bbbar"><div class="chips" id="bb-grp">${BGROUPS.filter(([k])=>k==='desk' ? !!DESK : (k!=='bot'&&k!=='tdboard' ? true : !!BOT)).map(([k,l])=>`<button type="button" data-g="${k}" class="${BF.grp===k?'on':''}">${k==='desk'?'★ ':''}${l} <small>${k==='desk'?(DESK.selections||[]).filter(x=>x.kick>now).length:(k==='bot'?Object.values((BOT||{}).cats||{}).reduce((a,c)=>a+(c.ids||[]).length,0):(k==='tdboard'?((BOT||{}).tds||[]).filter(t=>t.kick>now).length:up.filter(b=>b.group===k).length))}</small></button>`).join('')}</div>
    <select id="bb-kind" aria-label="Market"><option value="all">Every market</option>${kinds.map(k=>`<option value="${k}" ${BF.kind===k?'selected':''}>${esc(BKIND[k]||k)}</option>`).join('')}</select>
    <select id="bb-game" aria-label="Game"><option value="all">Every game</option>${games.map(g=>`<option value="${g.game_id}" ${BF.game===g.game_id?'selected':''}>${esc(g.mu)} · ${esc(bKick(g.kick))}</option>`).join('')}</select>
    <select id="bb-sort" aria-label="Sort"><option value="p" ${BF.sort==='p'?'selected':''}>Sort: win chance</option><option value="conf" ${BF.sort==='conf'?'selected':''}>Sort: evidence</option><option value="ev" ${BF.sort==='ev'?'selected':''}>Sort: price (EV)</option></select></div>`;
  const nShow = BF.more || 15;
  const shown = rows.slice(0, nShow);
  let h;
  if(BF.grp==='desk') h = bDesk();
  else if(BF.grp==='bot') h = bBot(up);
  else if(BF.grp==='tdboard') h = bTd();
  else { h = rows.length ? shown.map((b,i)=>bCard(b,i+1)).join('') : (up.length ? `<p class="empty">Nothing in this view.</p>` : `<p class="empty"><b>No DraftKings prices for upcoming games yet.</b> Lines for the next week usually arrive Wednesday morning.</p>`);
    if(BF.grp==='alts') h = `<p class="note">Alternate lines priced from the simulation's distribution and the market's consensus shift. DraftKings' alternate prices are not in the odds feed: bet one only when DraftKings pays more than the fair odds shown.</p>` + h;
    if(rows.length>shown.length) h += `<div style="text-align:center;margin-top:8px"><button type="button" class="rbtn" style="margin:0" id="bb-more">show ${Math.min(25, rows.length-shown.length)} more of ${rows.length}</button></div>`; }
  el.innerHTML = stale + stats + fresh + bar + `<div class="bbl">${h}</div>`;
  el.querySelectorAll('#bb-grp button').forEach(x=>x.onclick=()=>{ BF.grp=x.dataset.g; BF.kind='all'; BF.more=0; saveBF(); renderBest(); });
  const ks=document.getElementById('bb-kind'); if(ks) ks.onchange=e=>{ BF.kind=e.target.value; BF.more=0; saveBF(); renderBest(); };
  const gsel=document.getElementById('bb-game'); if(gsel) gsel.onchange=e=>{ BF.game=e.target.value; BF.more=0; saveBF(); renderBest(); };
  const ss=document.getElementById('bb-sort'); if(ss) ss.onchange=e=>{ BF.sort=e.target.value; BF.more=0; saveBF(); renderBest(); };
  const mb=document.getElementById('bb-more'); if(mb) mb.onclick=()=>{ BF.more = nShow + 25; renderBest(); };
  const cb=document.getElementById('combine'); if(cb) cb.onclick=()=>{ SHOW_COMBINE=!SHOW_COMBINE; renderBest(); if(SHOW_COMBINE){ const e=el.querySelector('.parlay'); if(e) e.scrollIntoView({behavior:'smooth',block:'start'}); } };
  el.querySelectorAll('button[data-add]').forEach(x=>x.onclick=()=>toggleLeg(SEL_BY[x.dataset.add])); }

function render(){ renderLivebar(); renderBest(); renderBoard(); renderCards(); renderScanner(); renderTop(); renderSlip(); renderResults(); renderTracker(); gradeBets(); }
renderToolbar(); renderPC(); renderResearch(); renderAbout(); render();
document.getElementById('fab').onclick=()=>{ const f=document.getElementById('fab'); f.classList.add('spin'); refreshLive().finally(()=>setTimeout(()=>f.classList.remove('spin'),400)); };
refreshLive();
setInterval(()=>{ const now=Date.now(); const near=P.games.some(g=>{ const k=kickoff(g); return k && now>k-15*60000 && now<k.getTime()+5*3600000; }); if(near && document.visibilityState==='visible') refreshLive(); }, 30000);
</script>
</body>
</html>
"""


def _book_spread(home: str, away: str, s) -> str:
    """nflverse's spread_line is the expected home margin; books write it as the favourite minus the points."""
    if s is None:
        return "no line"
    return f"{home} -{s:g}" if s > 0 else (f"{away} -{-s:g}" if s < 0 else "pick'em")


def static_summary(p: dict) -> str:
    """No-JS summary (for readers and tools that do not run scripts). Every number names its team."""
    rows = []
    for g in sorted(p["games"], key=lambda g: g.get("kickoff_utc") or ""):
        mk = g["markets"]; L = g.get("lines") or {}
        a, h = g["away"], g["home"]
        sp = mk.get("spread") or {}; to = mk.get("total") or {}
        qa, qh = mk["qb"]["away"], mk["qb"]["home"]
        s = L.get("spread")
        fav_side = "home" if (s or 0) > 0 else "away"
        cover = sp.get("home_cover") if fav_side == "home" else sp.get("away_cover")
        spread_txt = f"{_book_spread(h, a, s)}: {cover*100:.1f}% covers" if s not in (None, 0) and cover is not None else _book_spread(h, a, s)
        tops = []
        for side in ("away", "home"):
            lst = (g.get("anytime") or {}).get(side, [])[:2]
            if lst:
                tops.append(f"{g[side]}: " + ", ".join("%s %.0f%%" % (x["name"], x["p"] * 100) for x in lst))
        rows.append(f"<tr><td>{a} @ {h}</td><td>{g['date']} {g['time']}</td><td>{a} {mk['ml']['away']*100:.1f}% · {h} {mk['ml']['home']*100:.1f}%</td>"
                    f"<td>{spread_txt}</td><td>{L.get('total', '')}: over {to.get('over', 0)*100:.1f}%</td>"
                    f"<td>{mk['h1_fair_line']} / {mk['h2_fair_line']}</td><td>{a} {mk['fg']['away']['over1.5']*100:.0f}% · {h} {mk['fg']['home']['over1.5']*100:.0f}%</td>"
                    f"<td>{g['qb']['away'].get('name','')} {qa['yds_fair_line']} · {g['qb']['home'].get('name','')} {qh['yds_fair_line']}</td>"
                    f"<td>{a} {qa['td_over1.5']*100:.0f}% · {h} {qh['td_over1.5']*100:.0f}%</td><td>{' | '.join(tops)}</td></tr>")
    return (f'<div class="static" id="static"><h1>NFL {p["season"]} week {p["week"]}</h1><p>Probabilities from {p["meta"]["sims"]:,} simulated games per matchup. '
            f'Away team listed first. Spread in sportsbook form (favourite minus points) with the favourite\'s cover probability; '
            f'fair 1st / 2nd half total lines; team field goals made over 1.5; fair QB passing-yard lines; QB over 1.5 TD passes; top anytime touchdown scorers per team. Updated {p["generated_utc"]}.</p>'
            f'<table><tr><th>Game</th><th>Kickoff (ET)</th><th>Moneyline</th><th>Spread</th><th>Total</th><th>1H/2H fair</th><th>FG o1.5</th><th>QB yds fair</th><th>QB TD o1.5</th><th>Anytime TD</th></tr>'
            + "".join(rows) + "</table></div>")


def render(payload: dict, nhl_href: str = "../index.html", root: str = "../") -> str:
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    return (TEMPLATE.replace("__CSS__", BASE_CSS + NFL_CSS + BRAND_CSS).replace("__PAYLOAD__", data).replace("__STATIC__", static_summary(payload))
            .replace("__WEEK__", str(payload["week"])).replace("__BRAND__", brand_html(root, "nfl", nhl_href)))


__all__ = ["render", "TEMPLATE", "static_summary"]
