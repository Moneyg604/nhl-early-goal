"""Self-contained dashboard (single HTML file, no external assets except Google Fonts).

Layout: an app header with the slate date, four tabs (Today, Picks, Results, About),
and a phone card view / desktop table for the games. Live results, the price check,
the track record and the validation each live where a reader expects them.
"""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Early Goal Desk</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>
:root{--bg:#070b12;--panel:#0e141f;--panel2:#131b29;--line:#1d2838;--line2:#27344a;--text:#e8eef7;--muted:#93a3ba;--dim:#5e6f88;
--ice:#5ec8ff;--green:#3ddc84;--amber:#f3b63a;--red:#ff6b6b;--live:#ff7d7d;
--display:"Barlow Condensed",Impact,"Arial Narrow",sans-serif;--body:"IBM Plex Sans",-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color-scheme:dark}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);font-family:var(--body);font-size:14.5px;line-height:1.45;-webkit-font-smoothing:antialiased}
body{padding-bottom:calc(24px + env(safe-area-inset-bottom,0px))}
.num{font-variant-numeric:tabular-nums}
a{color:var(--ice)}
.wrap{max-width:1240px;margin:0 auto;padding-inline:16px}

/* app header */
.app{position:sticky;top:0;z-index:30;background:rgba(7,11,18,.92);backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);border-bottom:1px solid var(--line);padding-top:env(safe-area-inset-top,0px)}
.app .row{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:10px 0}
.brand{font-family:var(--display);font-weight:800;font-size:24px;letter-spacing:.04em;text-transform:uppercase;line-height:1;white-space:nowrap}
@media (max-width:420px){.brand{font-size:20px}.hmeta select{font-size:12px;padding:5px 6px;max-width:150px}}
.brand span{color:var(--ice)}
.hmeta{display:flex;align-items:center;gap:8px;font-size:12.5px;color:var(--muted);white-space:nowrap}
.hmeta select{background:var(--panel);border:1px solid var(--line2);color:var(--text);border-radius:8px;padding:6px 8px;font-size:13px;font-family:inherit}
.tabs{display:flex;gap:4px;padding-bottom:8px;overflow-x:auto;scrollbar-width:none}
.tabs::-webkit-scrollbar{display:none}
.tabs button{flex:1;min-width:84px;background:transparent;border:1px solid var(--line);color:var(--muted);border-radius:10px;padding:8px 10px;font-size:13px;font-weight:600;font-family:inherit;cursor:pointer;white-space:nowrap}
.tabs button.on{background:var(--panel2);border-color:var(--ice);color:var(--text)}
.tabs button .badge{display:inline-block;background:var(--live);color:#1a0a0a;border-radius:999px;font-size:10px;font-weight:800;padding:1px 6px;margin-left:5px;vertical-align:middle}
@media (max-width:480px){.tabs button{min-width:0;padding:8px 4px;font-size:12.5px}.tabs button .badge .w{display:none}.tabs button .badge{padding:1px 5px;margin-left:3px}}

section.tab{display:none;padding-top:14px}
section.tab.on{display:block}
h2{font-family:var(--display);font-weight:700;font-size:20px;letter-spacing:.03em;text-transform:uppercase;margin:18px 0 8px;color:var(--text)}
h2 small{font-family:var(--body);font-weight:500;font-size:12.5px;letter-spacing:0;text-transform:none;color:var(--muted);margin-left:8px}
.lead{color:var(--muted);font-size:13.5px;max-width:72ch;margin:0 0 10px}
.banner{border:1px solid rgba(243,182,58,.5);background:rgba(243,182,58,.08);color:#ffd37a;border-radius:12px;padding:10px 14px;margin:12px 0;font-size:13px}

/* status line + live bar */
.status{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:center;font-size:12.5px;color:var(--muted);margin:2px 0 10px}
.status b{color:var(--text);font-weight:600}
.livebar{display:none;border:1px solid rgba(255,125,125,.4);background:linear-gradient(180deg,rgba(255,107,107,.10),rgba(255,107,107,.04));border-radius:14px;padding:12px 14px;margin:0 0 12px}
.lhd{display:flex;flex-wrap:wrap;align-items:center;gap:8px;font-size:13px;color:var(--muted)}
.lhd b{color:var(--text)}
.pulse{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--live);box-shadow:0 0 0 0 rgba(255,125,125,.6);animation:pulse 1.6s infinite}
@keyframes pulse{0%{box-shadow:0 0 0 0 rgba(255,125,125,.55)}70%{box-shadow:0 0 0 8px rgba(255,125,125,0)}100%{box-shadow:0 0 0 0 rgba(255,125,125,0)}}
@media (prefers-reduced-motion:reduce){.pulse{animation:none}}
.tally{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:8px;margin-top:10px}
.tally div{background:rgba(7,11,18,.5);border:1px solid var(--line);border-radius:10px;padding:8px 10px}
.tally .k{display:block;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.tally .v{font-family:var(--display);font-size:20px;font-weight:700}
.tally .v .m{color:var(--red)}.tally .v .h{color:var(--green)}.tally .v .p{color:var(--dim);font-size:13px;font-family:var(--body);margin:0 6px 0 3px}
.tally .sub{display:block;font-size:11px;color:var(--dim);margin-top:1px;white-space:nowrap}
@media (max-width:480px){.tally{display:flex;flex-direction:column;gap:0;margin-top:8px;border:1px solid var(--line);border-radius:10px;overflow:hidden}.tally div{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 10px;border:0;border-top:1px solid var(--line);border-radius:0;background:rgba(7,11,18,.5)}.tally div:first-child{border-top:0}.tally .k{font-size:11px;letter-spacing:.02em;text-transform:none;color:var(--muted);white-space:nowrap}.tally .r{display:flex;align-items:baseline;gap:6px;white-space:nowrap}.tally .v{font-size:17px}.tally .v .p{margin:0 4px 0 2px;font-size:12px}.tally .sub{margin:0;font-size:10.5px}}
.rbtn{background:var(--panel);border:1px solid var(--line2);color:var(--ice);border-radius:8px;padding:5px 10px;font-size:12px;font-family:inherit;cursor:pointer;margin-left:auto}
.rbtn:disabled{opacity:.6;cursor:default}

/* featured + price */
.feature{display:grid;grid-template-columns:1.3fr 1fr;gap:12px;margin-bottom:14px}
@media (max-width:760px){.feature{grid-template-columns:1fr}}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:16px;padding:14px 16px}
.card h3{margin:0 0 6px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:700}
.feature .big{font-family:var(--display);font-size:52px;font-weight:800;line-height:1;color:var(--green);margin:4px 0 2px}
.feature .mu{font-size:19px;font-weight:600}
.feature .mk{color:var(--muted);font-size:13px}
.feature .ru{color:var(--dim);font-size:12.5px;margin-top:8px}
.price label{display:flex;align-items:center;justify-content:space-between;gap:10px;font-size:13.5px;margin:6px 0}
.price input{width:88px;background:#0a1017;border:1px solid var(--line2);color:var(--text);border-radius:8px;padding:7px 9px;font-size:15px;font-family:inherit;font-variant-numeric:tabular-nums}
.price input:focus{outline:2px solid var(--ice);outline-offset:1px}
.verdict{font-size:12.5px;color:var(--muted);margin-top:6px;line-height:1.5}
.verdict b.neg{color:var(--red)}.verdict b.pos{color:var(--green)}

/* toolbar */
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:8px 0 10px;font-size:12.5px;color:var(--muted)}
.toolbar select,.toolbar button{background:var(--panel);border:1px solid var(--line2);color:var(--text);border-radius:8px;padding:7px 10px;font-size:12.5px;font-family:inherit;cursor:pointer}
.toolbar button.on{border-color:var(--ice);color:var(--ice)}
.legend{margin-left:auto;display:flex;gap:10px;align-items:center;color:var(--dim)}
@media (max-width:480px){.toolbar select{flex:1;min-width:0}.legend{margin-left:0;width:100%;justify-content:flex-end}}
.legend .res{margin:0}

/* tier + result marks + live chip */
.tier{display:inline-block;font-size:10px;font-weight:800;border-radius:6px;padding:2px 6px;letter-spacing:.08em;vertical-align:middle}
.tier.A{background:rgba(61,220,132,.15);color:var(--green);border:1px solid rgba(61,220,132,.4)}
.tier.B{background:rgba(243,182,58,.14);color:var(--amber);border:1px solid rgba(243,182,58,.4)}
.tier.C{background:rgba(255,107,107,.12);color:var(--red);border:1px solid rgba(255,107,107,.4)}
.res{display:inline-block;font-size:11px;font-weight:800;margin-left:5px;vertical-align:middle;border-radius:5px;padding:0 5px;line-height:17px}
.res.hit{color:var(--green);background:rgba(61,220,132,.14)}.res.miss{color:var(--red);background:rgba(255,107,107,.14)}.res.tie{color:var(--amber);background:rgba(243,182,58,.14)}.res.pending{color:var(--dim)}
.lv{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.06em;border-radius:6px;padding:2px 7px;white-space:nowrap}
.lv.live{color:#ff9a9a;background:rgba(255,107,107,.12);border:1px solid rgba(255,107,107,.35)}
.lv.final{color:var(--text);background:rgba(255,255,255,.07);border:1px solid var(--line2)}
.lv.pre{color:var(--dim);border:1px solid var(--line)}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;vertical-align:middle}
.dot.confirmed{background:var(--green)}.dot.expected{background:var(--amber)}.dot.projected,.dot.unconfirmed{background:var(--amber);opacity:.6}.dot.unknown{background:var(--red)}
.hi{color:var(--green)}.mid{color:var(--text)}.lo{color:var(--muted)}
.pick{color:var(--ice);font-weight:700;margin-right:4px}
.t{color:var(--dim);font-size:11.5px}

/* game cards (phones) */
.cards{display:flex;flex-direction:column;gap:10px}
.gc{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:12px 14px}
.gc .hd{display:flex;justify-content:space-between;align-items:center;gap:8px;cursor:pointer}
.gc .hd .mu{font-family:var(--display);font-size:22px;font-weight:700;letter-spacing:.02em}
.gc .hd .when{font-size:12px;color:var(--muted);white-space:nowrap;text-align:right}
.gc .gl{display:flex;flex-wrap:wrap;gap:4px 14px;margin:6px 0 10px;font-size:12.5px;color:var(--muted)}
.gc .pri{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.gc .pri div{background:#0a1017;border:1px solid var(--line);border-radius:12px;padding:9px 11px;min-width:0}
.gc .k{display:block;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);margin-bottom:3px}
.gc .v{font-family:var(--display);font-size:28px;font-weight:800;line-height:1}
.gc .s{display:block;font-size:11.5px;color:var(--muted);margin-top:3px;white-space:nowrap}
.gc .sec{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-top:8px}
.gc .sec div{background:transparent;border:1px solid var(--line);border-radius:10px;padding:7px 9px;min-width:0}
.gc .sec .v{font-size:17px;font-family:var(--body);font-weight:700}
.gc .more{margin-top:8px;text-align:center}
.gc .more button{background:transparent;border:1px solid var(--line);color:var(--muted);border-radius:8px;padding:6px 12px;font-size:12px;font-family:inherit;cursor:pointer;width:100%}
.gc .dt{margin-top:10px}
.gc .pri div,.gc .sec div{position:relative}
.gc .pri .res,.gc .sec .res{position:absolute;top:6px;right:6px;margin:0;font-size:10px;line-height:15px;padding:0 4px}
.gc .sec div.pj .res{position:static;margin-left:4px}
.gc .o-hit{background:rgba(61,220,132,.08)!important;border-color:rgba(61,220,132,.35)!important}.gc .o-miss{background:rgba(255,107,107,.08)!important;border-color:rgba(255,107,107,.35)!important}.gc .o-tie{background:rgba(243,182,58,.08)!important;border-color:rgba(243,182,58,.35)!important}

/* table (desktop) */
.tablewrap{display:none;overflow:auto;border:1px solid var(--line);border-radius:16px;background:var(--panel)}
table{border-collapse:separate;border-spacing:0;width:100%;min-width:1040px}
thead th{position:sticky;top:0;background:#0b111a;z-index:3;font-size:10.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);font-weight:700;padding:10px 6px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap;cursor:pointer;user-select:none}
thead th.l{text-align:left}
thead th .u{font-size:9px;display:block;color:var(--dim);letter-spacing:.06em;margin-top:2px}
tbody td{padding:8px 6px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap;vertical-align:middle}
tbody tr.g{cursor:pointer}
tbody tr.g:hover td{background:rgba(94,200,255,.04)}
tbody tr.g td{position:relative}
tbody tr.g td .res{position:absolute;top:4px;right:4px;margin:0;font-size:10px;line-height:15px;padding:0 4px}
td.o-hit{background:rgba(61,220,132,.07)}td.o-miss{background:rgba(255,107,107,.07)}td.o-tie{background:rgba(243,182,58,.07)}
tbody tr.g:hover td.o-hit{background:rgba(61,220,132,.11)}tbody tr.g:hover td.o-miss{background:rgba(255,107,107,.11)}
td.l{text-align:left}
td.sticky,th.sticky{position:sticky;left:0;background:var(--panel);z-index:2}
th.sticky{z-index:4;background:#0b111a}
.pct{font-weight:700}
.fair{color:var(--dim);font-size:11px}
.edge{font-size:11px;font-weight:700}.edge.pos{color:var(--green)}.edge.neg{color:var(--red)}
.goalie{font-size:11.5px;text-align:left;line-height:1.3}
.bar{height:5px;background:#162236;border-radius:3px;overflow:hidden;margin-top:4px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--ice),var(--green))}
tr.d td{background:#0a1017;padding:12px 10px;white-space:normal;cursor:default}
.detwrap{position:sticky;left:0;max-width:calc(min(100vw,1240px) - 36px)}
@media (min-width:901px){.cards{display:none}.tablewrap{display:block}}

/* details */
.dets{min-width:0}
.det{display:grid;grid-template-columns:1.1fr 1.1fr 1fr;gap:12px}
@media (max-width:900px){.det{grid-template-columns:1fr}}
.box{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:12px 14px;text-align:left;min-width:0;overflow:hidden}
.box h4{margin:0 0 8px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.box table{min-width:0;width:100%}
.dets .box td,.dets .box th{padding:4px 6px;font-size:12px;border:0;background:transparent;text-align:right;white-space:normal;line-height:1.35}
.dets .box td:first-child,.dets .box th:first-child{text-align:left;color:var(--muted)}
.dets .box tr:nth-child(even) td{background:rgba(255,255,255,.025)}
.dets .box th{position:static;cursor:default;text-transform:none;letter-spacing:0;font-size:11px}
.lbl{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.06em;border-radius:5px;padding:1px 6px;margin-left:6px}
.lbl.measured{color:var(--green);background:rgba(61,220,132,.12)}.lbl.partial{color:var(--amber);background:rgba(243,182,58,.12)}.lbl.unmeasured{color:var(--red);background:rgba(255,107,107,.12)}
.arith{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;color:#bcd3f0;background:#0a1017;border:1px solid var(--line);border-radius:8px;padding:8px 10px;overflow:auto;white-space:pre}
.small{font-size:12.5px;color:var(--muted)}
.gap{margin-top:10px}
svg text{font-family:var(--body)}

/* picks */
.groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px}
.pk{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 16px}
.pk h3{margin:0;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:700}
.pk .why{font-size:12px;color:var(--dim);margin:4px 0 8px;line-height:1.4}
.pk ol{margin:0;padding:0;list-style:none}
.pk li{display:flex;justify-content:space-between;align-items:center;gap:8px;padding:8px 0;border-top:1px dashed var(--line);font-size:14px}
.pk li:first-child{border-top:0}
.pk .mu{font-weight:600}
.pk .p{font-family:var(--display);font-size:22px;font-weight:700;color:var(--green)}
.pk .note{font-size:11.5px;margin-top:8px;color:var(--dim)}
.pk .note.ok{color:var(--green)}.pk .note.no{color:var(--amber)}

/* results & about tables */
.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:14px 16px;margin-bottom:12px}
.tbl{overflow-x:auto}
.panel table{min-width:0;width:100%}
.panel td,.panel th{padding:7px 8px;font-size:13px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.panel td:first-child,.panel th:first-child{text-align:left;position:sticky;left:0;background:var(--panel);z-index:1}
.panel th{position:static;background:transparent;cursor:default;letter-spacing:.06em;color:var(--muted);font-size:11px;text-transform:uppercase}
.ok{color:var(--green);font-weight:700}.no{color:var(--amber);font-weight:700}
.panel p{margin:6px 0;font-size:13.5px;color:var(--muted);max-width:72ch;line-height:1.55}
.panel h3{margin:0 0 6px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:700}
.daylist{display:flex;flex-wrap:wrap;gap:8px}
.daylist a{display:inline-block;border:1px solid var(--line2);border-radius:8px;padding:6px 10px;color:var(--text);text-decoration:none;font-size:13px}
.daylist a.now{border-color:var(--ice);color:var(--ice)}
.glossary dt{font-weight:600;margin-top:8px}
.glossary dd{margin:2px 0 0;color:var(--muted);font-size:13.5px}

/* refresh affordances */
#ptr{position:fixed;top:0;left:0;right:0;text-align:center;font-size:12px;color:var(--muted);background:var(--panel);border-bottom:1px solid var(--line);padding:8px;transform:translateY(-100%);transition:transform .15s;z-index:40;padding-top:calc(8px + env(safe-area-inset-top,0px))}
#ptr.show{transform:translateY(0)}
#fab{position:fixed;right:16px;bottom:calc(16px + env(safe-area-inset-bottom,0px));width:48px;height:48px;border-radius:50%;background:var(--panel2);border:1px solid var(--ice);color:var(--ice);font-size:22px;line-height:46px;text-align:center;cursor:pointer;z-index:35;box-shadow:0 6px 20px rgba(0,0,0,.45)}
#fab.spin{animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){#fab.spin{animation:none}}
footer{margin-top:24px;color:var(--dim);font-size:12px;line-height:1.5}
.static{padding:14px 0}.static h1{font-family:var(--display);font-size:22px;text-transform:uppercase;letter-spacing:.03em;margin:0 0 8px}.static p{color:var(--muted);font-size:13.5px;max-width:80ch}
.static table{min-width:0;font-size:12.5px}.static td,.static th{padding:5px 7px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}.static{overflow-x:auto}
</style>
</head>
<body>
<div id="ptr">Release to refresh</div>
<button id="fab" title="Refresh live results" aria-label="Refresh live results">↻</button>
<div class="app"><div class="wrap">
  <div class="row">
    <div class="brand">Early <span>Goal</span> Desk</div>
    <div class="hmeta"><span id="dayslot"></span></div>
  </div>
  <nav class="tabs" id="tabs">
    <button data-tab="today" class="on">Today</button>
    <button data-tab="picks">Picks</button>
    <button data-tab="results">Results</button>
    <button data-tab="about">About</button>
  </nav>
</div></div>

<div class="wrap">
<div id="banner"></div>
__STATIC__

<section class="tab on" id="tab-today">
  <div class="status" id="status"></div>
  <div class="livebar" id="livebar"></div>
  <div class="feature" id="feature"></div>
  <div class="toolbar" id="toolbar"></div>
  <div class="tablewrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
  <div class="cards" id="cards"></div>
</section>

<section class="tab" id="tab-picks">
  <p class="lead">The three strongest games in each market, ranked by the model's probability. Each card says whether the backtest found that ranking games this way actually works.</p>
  <h2>Early goal <small>under 0.5 goals from the opening faceoff</small></h2>
  <div class="groups" id="picks-early"></div>
  <h2>First period</h2>
  <div class="groups" id="picks-p1"></div>
  <h2>Full game</h2>
  <div class="groups" id="picks-fg"></div>
</section>

<section class="tab" id="tab-results">
  <div id="results-live"></div>
  <div id="results-track"></div>
  <div class="panel"><h3>All slates</h3><p>Days ahead show projected starters until game day; past days keep the numbers that were on the page.</p><div class="daylist" id="daylist"></div></div>
</section>

<section class="tab" id="tab-about">
  <div id="validation"></div>
  <div class="panel" id="method"></div>
  <div class="panel glossary" id="glossary"></div>
  <footer id="foot"></footer>
</section>
</div>

<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
(function(){ const s=document.getElementById('static'); if(s) s.remove(); })();
const P = JSON.parse(document.getElementById('payload').textContent);
const M = P.meta || {};
const pct = x => (x*100).toFixed(1)+'%';
const cls = (x, hi, mid) => x>=hi?'hi':(x>=mid?'mid':'lo');
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const tier = t => `<span class="tier ${t}" title="${t==='A'?'both teams measured this season and both goalies confirmed':(t==='B'?'a goalie not yet confirmed, or a profile leaning on last season':'an input is unmeasured')}">${t}</span>`;
const fair = m => m.fair ? `<span class="fair">fair ${m.fair.toFixed(2)}</span>` : '';
const edge = m => (m.edge==null) ? '' : `<span class="edge ${m.edge>=0?'pos':'neg'}">${m.edge>=0?'+':''}${(m.edge*100).toFixed(1)}% vs ${m.book}</span>`;
const byId = {}; P.games.forEach(g=>byId[g.game_id]=g);
const niceDate = d => { try { const [y,m,dd]=d.split('-'); return new Date(+y,+m-1,+dd).toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric'}); } catch(e){ return d; } };
// the slate day rolls over at 4 am Eastern so late West Coast games still belong to the night before
const TODAY = new Date(Date.now()-4*3600*1000).toLocaleDateString('en-CA',{timeZone:'America/Toronto'});
const dayDiff = (a,b) => Math.round((new Date(a+'T12:00:00Z') - new Date(b+'T12:00:00Z'))/86400000);
const AHEAD = dayDiff(P.date, TODAY);            // 0 today, 1 tomorrow, negative for past slates
const whenWord = AHEAD===0 ? 'tonight' : (AHEAD===1 ? 'tomorrow' : 'on '+niceDate(P.date));

// ---------------------------------------------------------------- banners + status
if (M.demo) document.getElementById('banner').innerHTML = `<div class="banner"><b>Demo data.</b> Team and goalie inputs are synthetic.</div>`;
else if (AHEAD > 0) document.getElementById('banner').innerHTML = `<div class="banner"><b>Looking ahead: ${niceDate(P.date)}, ${AHEAD===1?'tomorrow':AHEAD+' days out'}.</b> Starting goalies are DailyFaceoff projections until they are confirmed on game day, so every game sits at tier B or C for now. The numbers refresh three times a day and firm up as starters are confirmed; rest and travel already count ${AHEAD===1?"tonight's":'the earlier'} games.</div>`;
else if (AHEAD < 0) document.getElementById('banner').innerHTML = `<div class="banner" style="border-color:var(--line2);background:var(--panel);color:var(--muted)"><b>Past slate, ${niceDate(P.date)}.</b> These are the numbers that were on the page before the games; the results are scored against them.</div>`;
if (M.data_through && !M.demo) { const lag = Math.round((new Date(P.date) - new Date(M.data_through)) / 86400000) - Math.max(0, AHEAD); if (lag > 2) document.getElementById('banner').innerHTML += `<div class="banner"><b>Data is ${lag} days behind this slate</b> (play-by-play through ${esc(M.data_through)}). Treat the numbers with extra caution until the data source catches up.</div>`; }
document.getElementById('status').innerHTML = [
  `<b>${niceDate(P.date)}</b>`, `<b>${P.games.length}</b> games`,
  (function(){ const qs=P.games.flatMap(g=>[g.goalies.home,g.goalies.away]); const c=qs.filter(q=>q.status==='confirmed').length; return `goalies: <b>${c} of ${qs.length} confirmed</b>${c?' (DailyFaceoff)':' (projected from usage)'}`; })(),
  `data through <b>${esc(M.data_through||'n/a')}</b>`, `updated <b>${esc(P.generated_utc)}</b>`
].map(x=>`<span>${x}</span>`).join('');

// ---------------------------------------------------------------- tabs
const tabs = document.getElementById('tabs');
function showTab(name, push){
  document.querySelectorAll('section.tab').forEach(s=>s.classList.toggle('on', s.id==='tab-'+name));
  tabs.querySelectorAll('button').forEach(b=>b.classList.toggle('on', b.dataset.tab===name));
  try{ localStorage.setItem('egd_tab', name); }catch(e){}
  if (push && history.replaceState) history.replaceState(null, '', '#'+name);
  window.scrollTo({top:0});
}
tabs.querySelectorAll('button').forEach(b=>b.onclick=()=>showTab(b.dataset.tab, true));
if (AHEAD!==0) tabs.querySelector('[data-tab="today"]').textContent = 'Slate';
function tabFromHash(){ const h=(location.hash||'').replace('#',''); if(['today','picks','results','about'].includes(h)) showTab(h,false); }
tabFromHash(); window.addEventListener('hashchange', tabFromHash);

// ---------------------------------------------------------------- live results
let LIVE = null;
const NHL_SCORE = 'https://api-web.nhle.com/v1/score/now';
const RELAYS = [u=>u, u=>'https://api.allorigins.win/raw?url='+encodeURIComponent(u), u=>'https://corsproxy.io/?url='+encodeURIComponent(u), u=>'https://api.codetabs.com/v1/proxy?quest='+encodeURIComponent(u)];
let relayIdx = 0, directOk = false;
function mmss(t){ const [m,s]=String(t).split(':'); return (+m)+(+s)/60; }
function liveFromScoreboard(sb){
  if(!sb || !sb.games) return null;
  const games = {};
  for (const g of sb.games) {
    if (g.gameDate !== P.date || g.gameType !== 2) continue;
    const home=g.homeTeam.abbrev, away=g.awayTeam.abbrev, state=String(g.gameState||'FUT').toUpperCase();
    const final = state==='OFF'||state==='FINAL', live = state==='LIVE'||state==='CRIT';
    const goals=[]; for (const x of (g.goals||[])) { const p=+x.period; if(p===5) continue; const t=mmss(x.timeInPeriod); goals.push({period:p, minute: p<=3 ? (p-1)*20+t : 60+t, team:x.teamAbbrev}); }
    let elapsed=0; const period=g.period||null, rem=(g.clock||{}).timeRemaining||null;
    if (final) elapsed=60; else if (live && period && rem) elapsed = period<=3 ? (period-1)*20+(20-mmss(rem)) : 60;
    const reg=goals.filter(x=>x.period<=3); if(reg.length) elapsed=Math.max(elapsed, Math.max(...reg.map(x=>x.minute)));
    const p1_done = final || (live && period>=2) || goals.some(x=>x.period>=2); if(p1_done && !final) elapsed=Math.max(elapsed,20);
    const first = goals.length ? Math.min(...goals.map(x=>x.minute)) : null;
    let ended=null; if(final){ const lpt=String((g.gameOutcome||{}).lastPeriodType||'REG').toUpperCase(); ended = lpt==='SO'?'SO':((lpt==='OT'||goals.some(x=>x.period===4))?'OT':'REG'); }
    games[String(g.id)] = {state, live, final, period, time_remaining:rem, elapsed_min:elapsed, home, away,
      home_score: g.homeTeam.score==null?null:+g.homeTeam.score, away_score: g.awayTeam.score==null?null:+g.awayTeam.score,
      first_goal_min:first, p1_done, p1_home: goals.filter(x=>x.period===1&&x.team===home).length, p1_away: goals.filter(x=>x.period===1&&x.team===away).length, ended_in:ended, goals};
  }
  if (!Object.keys(games).length) return null;
  const now = new Date();
  return {date:P.date, updated_utc: now.toISOString(), updated_et: now.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',timeZone:'America/Toronto'})+' ET', games, source:'scoreboard'};
}
function fetchScoreboard(){
  const order = directOk ? [0] : [0,1,2,3].slice(relayIdx).concat([0,1,2,3].slice(0,relayIdx));
  const attempt = i => { if (i>=order.length) return Promise.reject('no relay'); const k=order[i];
    const ctrl = new AbortController(); const timer = setTimeout(()=>ctrl.abort(), 6000);
    return fetch(RELAYS[k](NHL_SCORE), {cache:'no-store', signal: ctrl.signal}).then(r=>{ clearTimeout(timer); if(!r.ok) throw r.status; return r.json(); })
      .then(j=>{ if(!j || !j.games) throw 'shape'; if(k===0) directOk=true; else relayIdx=k; return j; }).catch(()=>attempt(i+1)); };
  return attempt(0);
}
function liveFromScorecard(sc){
  const day = sc && sc.days && sc.days[P.date]; if(!day || !day.games) return null;
  const games = {};
  for (const [gid, sg] of Object.entries(day.games)) {
    if (sg.home_score==null) continue;
    games[gid] = {state:'FINAL', live:false, final:true, period:null, time_remaining:null, elapsed_min:60, home:sg.home, away:sg.away,
      home_score:sg.home_score, away_score:sg.away_score, first_goal_min:sg.first_goal_min, p1_done:true, p1_home:sg.p1_home, p1_away:sg.p1_away, ended_in:sg.ended_in, goals:[]};
  }
  return Object.keys(games).length ? {date:P.date, updated_et:'final', games, source:'scorecard'} : null;
}
function liveFor(g){ return LIVE && LIVE.date===P.date && LIVE.games ? LIVE.games[String(g.game_id)] : null; }
function outcomes(g){
  const L = liveFor(g); if(!L) return null;
  const m = g.markets, home = g.home, fg = L.first_goal_min, started = L.live || L.final;
  const o = {started};
  o.u05_first5 = (fg!=null && fg<5) ? 'miss' : ((L.elapsed_min>=5 || L.final) ? 'hit' : 'pending');
  o.u05_first10 = (fg!=null && fg<10) ? 'miss' : ((L.elapsed_min>=10 || L.final) ? 'hit' : 'pending');
  const d1 = pick => (pick===home ? L.p1_home - L.p1_away : L.p1_away - L.p1_home);
  o.p1_minus05 = L.p1_done ? (d1(m.p1_minus05.pick)>0 ? 'hit' : 'miss') : 'pending';
  o.p1_plus05 = L.p1_done ? (d1(m.p1_plus05.pick)>=0 ? 'hit' : 'miss') : 'pending';
  o.p1_ml = L.p1_done ? (d1(m.p1_ml.pick)>0 ? 'hit' : (d1(m.p1_ml.pick)===0 ? 'tie' : 'miss')) : 'pending';
  const dg = pick => (pick===home ? L.home_score - L.away_score : L.away_score - L.home_score);
  o.fg_ml = L.final ? (dg(m.fg_ml.pick)>0 ? 'hit' : 'miss') : 'pending';
  o.fg_spread = L.final ? (dg(m.fg_spread.pick)>=2 ? 'hit' : 'miss') : 'pending';
  o.fg_over55 = L.final ? ((L.home_score + L.away_score)>5.5 ? 'over' : 'under') : 'pending';
  return o;
}
const RES = {hit:'✓', miss:'✗', tie:'tie', pending:'…', over:'over', under:'under'};
function mark(g, key){ const o = outcomes(g); if(!o || !o.started) return ''; const r = o[key]; if(!r) return ''; return `<span class="res ${r==='over'||r==='under'?'tie':r}" title="${r}">${RES[r]}</span>`; }
function clockTxt(L){
  // the scoreboard clock can lag the goal feed by minutes; never show a clock earlier than the last goal
  if(!L.live || !L.period) return '';
  const per = L.period<=3 ? L.period : 4;
  const fromClock = L.time_remaining ? (per<=3 ? (per-1)*20+(20-mmss(L.time_remaining)) : 60) : 0;
  let rem = L.time_remaining||'';
  if (per<=3 && L.elapsed_min > fromClock + 0.25) { const left = Math.max(0, per*20 - L.elapsed_min); rem = String(Math.floor(left)).padStart(2,'0')+':'+String(Math.min(59,Math.round((left%1)*60))).padStart(2,'0'); }
  return (per>=4?'OT':'P'+per)+(rem?' '+rem:'');
}
function liveChip(g){
  const L = liveFor(g); if(!L) return '';
  if (L.final) return `<span class="lv final">FINAL ${L.away} ${L.away_score} · ${L.home} ${L.home_score}${L.ended_in && L.ended_in!=='REG' ? ' ('+L.ended_in+')' : ''}</span>`;
  if (L.live) return `<span class="lv live">LIVE ${esc(clockTxt(L))} · ${L.away} ${L.away_score} · ${L.home} ${L.home_score}</span>`;
  if (L.state==='PRE') return `<span class="lv pre">warm-up</span>`;
  return '';
}
const MARKET_NAMES = {u05_first5:'Under 0.5 · first 5 min', u05_first10:'Under 0.5 · first 10 min', p1_minus05:'1P −0.5 pick', p1_plus05:'1P +0.5 pick', p1_ml:'1P moneyline pick', fg_ml:'FG moneyline pick', fg_spread:'FG −1.5 pick', fg_over55:'FG over 5.5'};
function tallies(){
  const keys = Object.keys(MARKET_NAMES).filter(k=>k!=='fg_over55');
  const t = {}; let started=0, finals=0;
  P.games.forEach(g=>{ const o=outcomes(g); if(!o||!o.started) return; started++; const L=liveFor(g); if(L.final) finals++;
    keys.forEach(k=>{ const x = t[k] = t[k]||{hit:0,miss:0,tie:0,pending:0}; x[o[k]] = (x[o[k]]||0)+1; }); });
  return {t, started, finals, keys};
}
function tallyHtml(){
  const {t, keys} = tallies();
  return `<div class="tally">${keys.map(k=>{ const x=t[k]; if(!x) return ''; const dec=x.hit+x.miss+x.tie; if(!dec && !x.pending) return '';
    const sub=[x.tie?`${x.tie} tie`:'', x.pending?`${x.pending} pending`:''].filter(Boolean).join(' · ');
    return `<div><span class="k">${MARKET_NAMES[k]}</span><span class="r"><span class="v"><span class="h">${x.hit}</span><span class="p">hit</span><span class="m">${x.miss}</span><span class="p">miss</span></span><span class="sub">${sub||'all decided'}</span></span></div>`; }).join('')}</div>`;
}
function renderLiveBar(){
  const bar = document.getElementById('livebar'), rl = document.getElementById('results-live');
  if (!LIVE || LIVE.date!==P.date) { bar.style.display='none'; rl.innerHTML=''; return; }
  const {started, finals} = tallies();
  const when = LIVE.updated_et==='final' ? 'all games final' : 'as of '+esc(LIVE.updated_et);
  const src = LIVE.source==='scoreboard' ? 'live scoreboard, checked every 30 s while open' : (LIVE.source==='scorecard' ? 'final results' : 'snapshot, refreshed every few minutes');
  const badge = (started && finals<P.games.length) ? `<span class="badge">${started-finals}<span class="w"> live</span></span>` : '';
  tabs.querySelector('[data-tab="results"]').innerHTML = 'Results'+badge;
  if (!started) { bar.innerHTML = `<div class="lhd"><span class="pulse"></span><b>Live results</b><span>no game has started yet · ${when}</span><button class="rbtn">↻ Refresh</button></div>`; bar.style.display='block'; rl.innerHTML=''; return; }
  const summary = `<span>${started} of ${P.games.length} started · ${finals} final · ${when} · ${src}</span><button class="rbtn">↻ Refresh</button>`;
  const head = `<div class="lhd">${finals<P.games.length?'<span class="pulse"></span>':''}<b>${finals===P.games.length?'Final results':'Live results'}</b>${summary}</div>`;
  bar.innerHTML = head + tallyHtml(); bar.style.display='block';
  rl.innerHTML = `<div class="panel"><h3>${finals===P.games.length?niceDate(P.date)+', final':niceDate(P.date)+', so far'}</h3><div class="lhd">${summary}</div>${tallyHtml()}
    <div class="gap tbl"><table class="num"><thead><tr><th>game</th><th>status</th><th>first 5</th><th>first 10</th><th>1P −0.5</th><th>1P +0.5</th><th>1P ML</th><th>FG ML</th><th>FG −1.5</th></tr></thead><tbody>
    ${P.games.filter(g=>outcomes(g)&&outcomes(g).started).map(g=>{ const o=outcomes(g); const L=liveFor(g); const c=k=>`<span class="res ${o[k]}">${RES[o[k]]}</span>`;
      return `<tr><td>${esc(g.matchup)}</td><td>${L.final?('FINAL '+L.away_score+'-'+L.home_score+(L.ended_in&&L.ended_in!=='REG'?' ('+L.ended_in+')':'')):(esc(clockTxt(L))+' · '+L.away_score+'-'+L.home_score)}</td><td>${c('u05_first5')}</td><td>${c('u05_first10')}</td><td>${esc(g.markets.p1_minus05.pick)} ${c('p1_minus05')}</td><td>${esc(g.markets.p1_plus05.pick)} ${c('p1_plus05')}</td><td>${esc(g.markets.p1_ml.pick)} ${c('p1_ml')}</td><td>${esc(g.markets.fg_ml.pick)} ${c('fg_ml')}</td><td>${esc(g.markets.fg_spread.pick)} ${c('fg_spread')}</td></tr>`; }).join('')}
    </tbody></table></div></div>`;
}
let loading = false;
function setRefreshState(txt, busy){ document.querySelectorAll('.rbtn').forEach(b=>{ b.disabled=!!busy; b.textContent = txt; }); const f=document.getElementById('fab'); if(f) f.classList.toggle('spin', !!busy); }
function loadLive(){
  if (loading) return Promise.resolve();
  loading = true; setRefreshState('Refreshing…', true);
  const tryUrl = u => fetch(u + '?t=' + Date.now(), {cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));
  const apply = L => { LIVE=L; renderLiveBar(); render(); renderFeature(); renderPicks(); };
  return fetchScoreboard().then(sb=>{ const L=liveFromScoreboard(sb); if(L){ apply(L); return true; } return false; }).catch(()=>false)
    .then(ok=>{ if(ok) return true; return tryUrl('./live.json').catch(()=>tryUrl('../live.json')).then(j=>{ if(j && j.games && j.date===P.date){ apply(j); return true; } return false; }).catch(()=>false); })
    .then(ok=>{ if(ok) return; return tryUrl('./scorecard.json').catch(()=>tryUrl('../scorecard.json')).then(sc=>{ const L=liveFromScorecard(sc); if(L) apply(L); }).catch(()=>{}); })
    .then(()=>{ loading=false; setRefreshState('↻ Refresh', false); });
}
document.getElementById('fab').onclick = ()=>loadLive();
document.addEventListener('click', e=>{ if(e.target.classList && e.target.classList.contains('rbtn')) loadLive(); });
(function(){
  let y0=null, pulled=false; const ptr=document.getElementById('ptr');
  document.addEventListener('touchstart', e=>{ y0 = (window.scrollY<=0) ? e.touches[0].clientY : null; pulled=false; }, {passive:true});
  document.addEventListener('touchmove', e=>{ if(y0==null) return; const dy=e.touches[0].clientY-y0; if(dy>70 && window.scrollY<=0){ pulled=true; ptr.classList.add('show'); } else if(dy<40){ pulled=false; ptr.classList.remove('show'); } }, {passive:true});
  document.addEventListener('touchend', ()=>{ if(pulled){ ptr.textContent='Refreshing…'; loadLive().then(()=>{ ptr.textContent='Updated'; setTimeout(()=>{ptr.classList.remove('show'); ptr.textContent='Release to refresh';}, 900); }); } else ptr.classList.remove('show'); y0=null; pulled=false; }, {passive:true});
})();
setInterval(()=>{ if(!document.hidden && (LIVE && LIVE.source==='scoreboard')) loadLive(); }, 30000);
setInterval(()=>{ if(!document.hidden && !(LIVE && LIVE.source==='scoreboard')) loadLive(); }, 120000);
document.addEventListener('visibilitychange', ()=>{ if(!document.hidden) loadLive(); });

// ---------------------------------------------------------------- price check (stays in the browser)
let userPrice5 = null, userPrice10 = null;
try{ userPrice5 = parseFloat(localStorage.getItem('egd_price5'))||null; userPrice10 = parseFloat(localStorage.getItem('egd_price10'))||null; }catch(e){}
const ps5 = P.games.map(g=>g.markets.u05_first5.p), lo5=Math.min(...ps5), hi5=Math.max(...ps5);
const ps10 = P.games.map(g=>g.markets.u05_first10.p), lo10=Math.min(...ps10), hi10=Math.max(...ps10);
function verdict(price, lo, hi){
  if(!price||price<=1) return 'Enter the price your book offers and this shows whether it beats the model.';
  const be=1/price, evLo=lo*price-1, evHi=hi*price-1; const c = evHi<0?'neg':(evLo>0?'pos':'');
  return `Break-even <b>${pct(be)}</b>. Across this slate the model's EV is <b class="${c}">${(evLo*100).toFixed(1)}% to ${(evHi*100).toFixed(1)}%</b> per unit.`;
}
function renderFeature(){
  const potd = P.pick_of_day; const f = document.getElementById('feature');
  const g = potd ? byId[potd.game_id] : null;
  f.innerHTML = (potd ? `<div class="card"><h3>Highest probability ${whenWord} · under 0.5, first 5 minutes ${tier(potd.tier)}</h3>
      <div class="mu">${esc(potd.matchup)}</div><div class="big num">${pct(potd.p)}${g?mark(g,'u05_first5'):''}</div>
      <div class="mk">fair price ${potd.fair.toFixed(2)} · slate range ${pct(lo5)} to ${pct(hi5)} · league rate ${P.league.p_no_goal_5_observed!=null?pct(P.league.p_no_goal_5_observed):'n/a'}</div>
      ${AHEAD>0?`<div class="ru">Projected starters; re-check on game day once goalies are confirmed.</div>`:''}
      ${potd.runner_up?`<div class="ru">runner-up ${esc(potd.runner_up.matchup)} ${pct(potd.runner_up.p)} ${tier(potd.runner_up.tier)}</div>`:''}
      <div class="ru">The spread between games is within noise; the price is what decides whether this bet is worth placing.</div></div>` : '') +
    `<div class="card price"><h3>Price check</h3>
      <label>Under 0.5 · first 5 min <input id="price5" type="number" step="0.01" min="1.01" placeholder="e.g. 1.30" value="${userPrice5||''}"></label>
      <div class="verdict">${verdict(userPrice5, lo5, hi5)}</div>
      <label>Under 0.5 · first 10 min <input id="price10" type="number" step="0.01" min="1.01" placeholder="e.g. 1.90" value="${userPrice10||''}"></label>
      <div class="verdict">${verdict(userPrice10, lo10, hi10)}</div></div>`;
  const bind=(id,setter,key)=>{const el=document.getElementById(id); if(!el) return; el.onchange=el.onkeyup=()=>{const v=parseFloat(el.value);setter(v>1?v:null);try{localStorage.setItem(key,v>1?String(v):'');}catch(e){} renderFeature(); render(); document.getElementById(id).focus();};};
  bind('price5',v=>userPrice5=v,'egd_price5'); bind('price10',v=>userPrice10=v,'egd_price10');
}

// ---------------------------------------------------------------- game list
const cols = [
  {k:'rank', h:'#', u:'rank', v:g=>g.rank_u05_first5, r:g=>`<span class="num t">${g.rank_u05_first5}</span>`},
  {k:'matchup', h:'Matchup', u:'away @ home · ET · goalies', l:true, sticky:true, v:g=>g.game_id, r:g=>`<span style="font-weight:700">${esc(g.matchup)}</span> ${tier(g.tier)} <span class="t">${esc(g.time_et)}</span><div>${liveChip(g)}</div>`+['away','home'].map(s=>{const q=g.goalies[s];return `<div class="goalie"><span class="dot ${q.status}"></span>${esc(q.name||'unknown')} <span class="t">${q.sv_shrunk?('.'+String(q.sv_shrunk.toFixed(3)).slice(2)):''} ${esc(q.status)}</span></div>`}).join('')},
  {k:'u5', m:'u05_first5', h:'Under 0.5 · first 5', u:'no goal · fair', v:g=>g.markets.u05_first5.p, r:g=>{const m=Object.assign({},g.markets.u05_first5); if(m.edge==null&&userPrice5){m.book=userPrice5;m.edge=m.p*userPrice5-1;} return `<span class="pct num ${cls(m.p,0.70,0.64)}">${pct(m.p)}</span> ${fair(m)}${mark(g,'u05_first5')}<div class="bar"><i style="width:${(m.p*100).toFixed(1)}%"></i></div>${edge(m)}`}},
  {k:'u10', m:'u05_first10', h:'Under 0.5 · first 10', u:'no goal · fair', v:g=>g.markets.u05_first10.p, r:g=>{const m=Object.assign({},g.markets.u05_first10); if(m.edge==null&&userPrice10){m.book=userPrice10;m.edge=m.p*userPrice10-1;} return `<span class="pct num ${cls(m.p,0.47,0.42)}">${pct(m.p)}</span> ${fair(m)}${mark(g,'u05_first10')}<div class="bar"><i style="width:${(m.p*100).toFixed(1)}%"></i></div>${edge(m)}`}},
  {k:'p1m', m:'p1_minus05', h:'1P −0.5', u:'pick · cover', v:g=>g.markets.p1_minus05.p, r:g=>{const m=g.markets.p1_minus05;return `<span class="pick">${esc(m.pick)}</span><span class="num">${pct(m.p)}</span>${mark(g,'p1_minus05')}`}},
  {k:'p1p', m:'p1_plus05', h:'1P +0.5', u:'pick · cover', v:g=>g.markets.p1_plus05.p, r:g=>{const m=g.markets.p1_plus05;return `<span class="pick">${esc(m.pick)}</span><span class="num ${cls(m.p,0.66,0.60)}">${pct(m.p)}</span>${mark(g,'p1_plus05')}`}},
  {k:'p1ml', m:'p1_ml', h:'1P ML', u:'home / tie / away', v:g=>g.markets.p1_ml.p, r:g=>{const m=g.markets.p1_ml;return `<span class="pick">${esc(m.pick)}</span><span class="num">${pct(m.p)}</span>${mark(g,'p1_ml')}<div class="t num">${(m.home*100).toFixed(0)} / ${(m.tie*100).toFixed(0)} / ${(m.away*100).toFixed(0)}%</div>`}},
  {k:'fgml', m:'fg_ml', h:'FG ML', u:'incl. OT/SO', v:g=>g.markets.fg_ml.p, r:g=>{const m=g.markets.fg_ml;return `<span class="pick">${esc(m.pick)}</span><span class="num ${cls(m.p,0.60,0.54)}">${pct(m.p)}</span>${mark(g,'fg_ml')}`}},
  {k:'fgs', m:'fg_spread', h:'FG spread', u:'−1.5 cover · +1.5', v:g=>g.markets.fg_spread.p, r:g=>{const m=g.markets.fg_spread;return `<span class="pick">${esc(m.pick)} −1.5</span><span class="num">${pct(m.p)}</span>${mark(g,'fg_spread')}<div class="t num">${esc(m.plus_pick)} +1.5 ${pct(m.plus_p)}</div>`}},
  {k:'proj', h:'Projected', u:'home – away · O5.5', v:g=>g.projected.home+g.projected.away, r:g=>`<span class="num">${g.projected.home.toFixed(1)} – ${g.projected.away.toFixed(1)}</span><div class="t num">O5.5 ${pct(g.markets.fg_total.over55)}${mark(g,'fg_over55')}</div>`},
];
let sortKey='rank', sortDir=1, tierFilter='ALL', open=new Set();
const thead=document.querySelector('#tbl thead'), tbody=document.querySelector('#tbl tbody');
thead.innerHTML='<tr>'+cols.map(c=>`<th class="${c.l?'l':''} ${c.sticky?'sticky':''}" data-k="${c.k}">${c.h}<span class="u">${c.u}</span></th>`).join('')+'</tr>';
thead.querySelectorAll('th').forEach(th=>th.onclick=()=>{const k=th.dataset.k;if(sortKey===k)sortDir*=-1;else{sortKey=k;sortDir=(k==='rank'||k==='matchup'||k==='goalies')?1:-1;}render();});

function factorRows(side, team){
  const m=side.mults, rows=[['home ice',m.home_ice],['shot rate for (early)',m.off_shot_early],['opp shot rate against (early)',m.opp_def_shot_early],['finishing',m.finish],['opp goalie',m.opp_goalie],['rest / travel',m.context_total]];
  const prod=rows.reduce((a,r)=>a*r[1],1);
  return `<table>${rows.map(r=>`<tr><td>${r[0]}</td><td class="num ${r[1]>1.02?'hi':(r[1]<0.98?'lo':'')}">× ${r[1].toFixed(3)}</td></tr>`).join('')}<tr><td><b>${team} early-goal multiplier</b></td><td class="num"><b>× ${prod.toFixed(3)}</b></td></tr></table>`;
}
function hazardSvg(g){
  const lh=g.sides.home.lambda_first_10_per_min, la=g.sides.away.lambda_first_10_per_min;
  const W=320,H=90,pad=22,bw=(W-pad-6)/10,mx=Math.max(...lh.map((x,i)=>x+la[i]))*1.15||0.1;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">`;
  for(let i=0;i<10;i++){const tot=lh[i]+la[i],h=(tot/mx)*(H-28),x=pad+i*bw,hh=(lh[i]/mx)*(H-28);
    s+=`<rect x="${x+2}" y="${H-16-h}" width="${bw-4}" height="${h}" fill="#1f6f8f" rx="2"/><rect x="${x+2}" y="${H-16-hh}" width="${bw-4}" height="${hh}" fill="#5ec8ff" rx="2"/><text x="${x+bw/2}" y="${H-4}" font-size="9" fill="#5e6f88" text-anchor="middle">${i+1}</text>`;}
  s+=`<text x="${pad-4}" y="12" font-size="9" fill="#5e6f88" text-anchor="end">${mx.toFixed(3)}</text><text x="${pad-4}" y="${H-16}" font-size="9" fill="#5e6f88" text-anchor="end">0</text><line x1="${pad}" y1="${H-16}" x2="${W-4}" y2="${H-16}" stroke="#1d2838"/></svg>`;
  return s;
}
function histSvg(g){
  const h=g.first_goal_hist,W=320,H=90,pad=22,bw=(W-pad-6)/10,mx=Math.max(...h)*1.15||0.1;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">`;
  h.forEach((v,i)=>{const hh=(v/mx)*(H-28),x=pad+i*bw;s+=`<rect x="${x+2}" y="${H-16-hh}" width="${bw-4}" height="${hh}" fill="#3ddc84" rx="2" opacity=".85"/><text x="${x+bw/2}" y="${H-4}" font-size="9" fill="#5e6f88" text-anchor="middle">${i+1}</text>`;});
  s+=`<text x="${pad-4}" y="12" font-size="9" fill="#5e6f88" text-anchor="end">${(mx*100).toFixed(0)}%</text><line x1="${pad}" y1="${H-16}" x2="${W-4}" y2="${H-16}" stroke="#1d2838"/></svg>`;
  return s;
}
function lbl(x){return `<span class="lbl ${x.label}">${x.label}</span>`}
function goalieBox(g, side){
  const q=g.goalies[side]; const f=v=>v==null?'n/a':('.'+String(v.toFixed(3)).slice(2));
  return `<table><tr><td>starter</td><td><span class="dot ${q.status}"></span>${esc(q.name||'unknown')} <span class="t">${esc(q.status)}</span></td></tr>
  <tr><td>sv% raw / shrunk</td><td class="num">${f(q.sv_raw)} / ${f(q.sv_shrunk)}</td></tr>
  <tr><td>last 5 starts sv%</td><td class="num">${f(q.sv_last5)}</td></tr>
  <tr><td>first-10-min sv% raw</td><td class="num">${f(q.e10_sv_raw)}</td></tr>
  <tr><td>starts this season / shots in sample</td><td class="num">${q.starts_cur??'n/a'} / ${q.shots_weighted}</td></tr></table>${q.note?`<div class="small gap">${esc(q.note)}</div>`:''}`;
}
function restBox(side){
  const r=side.rest||{}; if(!r||r.days_rest===undefined)return '<div class="small">schedule context missing</div>';
  const ctx=Object.entries(side.context_detail||{});
  return `<table><tr><td>days rest</td><td class="num">${r.days_rest==null?'first game':r.days_rest}${r.b2b?' <span class="lbl partial">B2B</span>':''}${r.three_in_four?' <span class="lbl partial">3-in-4</span>':''}</td></tr>
  <tr><td>travel since last game</td><td class="num">${(r.travel_km||0).toFixed(0)} km · ${r.tz_shift||0} tz</td></tr>
  <tr><td>games last 7 days</td><td class="num">${r.games_last_7d??'n/a'}</td></tr>
  <tr><td>previous</td><td>${r.prev_opponent?esc(r.prev_opponent)+' · '+esc(r.prev_date):'n/a'}</td></tr>
  ${ctx.map(([k,v])=>`<tr><td>${esc(k)}</td><td class="num">× ${v.toFixed(3)}</td></tr>`).join('')}</table>`;
}
function profBox(side){
  const p=side.profile||{}; if(!p.games_cur && !p.games_prior) return '<div class="small">no profile data</div>';
  const lg=(p.last_games||[]).slice(-5).map(x=>`${x.home?'vs':'@'} ${x.opp} ${x.score} · first goal ${x.first_goal_min==null?'none':x.first_goal_min.toFixed(1)+"'"}`).join('<br>');
  return `<table>
  <tr><td>sample</td><td class="num">${p.games_cur} this season + ${p.games_prior} prior</td></tr>
  <tr><td>goals for / against, first 10 (per game)</td><td class="num">${p.e10_gf_pg.toFixed(2)} / ${p.e10_ga_pg.toFixed(2)}</td></tr>
  <tr><td>goals for / against, first 5 (per game)</td><td class="num">${p.e5_gf_pg.toFixed(2)} / ${p.e5_ga_pg.toFixed(2)}</td></tr>
  <tr><td>SOG for / against, first 10</td><td class="num">${p.e10_sog_for_pg.toFixed(2)} / ${p.e10_sog_against_pg.toFixed(2)}</td></tr>
  <tr><td>SOG for / against, full game</td><td class="num">${p.sog_for_pg.toFixed(1)} / ${p.sog_against_pg.toFixed(1)}</td></tr>
  <tr><td>shooting%</td><td class="num">${p.sh_pct==null?'n/a':(p.sh_pct*100).toFixed(1)+'%'}</td></tr>
  <tr><td>early penalties taken / drawn (first 10)</td><td class="num">${p.e10_pen_taken_pg.toFixed(2)} / ${p.e10_pen_drawn_pg.toFixed(2)}</td></tr>
  <tr><td>this season: no goal by either side in first 5</td><td class="num">${p.cur_no_goal_5_share==null?'n/a':pct(p.cur_no_goal_5_share)}</td></tr>
  </table>${lg?`<div class="small gap">${lg}</div>`:''}`;
}
function details(g){
  const H=g.sides.home, A=g.sides.away, lh=H.lambda_first_10_per_min, la=A.lambda_first_10_per_min;
  const s5=lh.slice(0,5).reduce((a,b)=>a+b,0)+la.slice(0,5).reduce((a,b)=>a+b,0), s10=lh.reduce((a,b)=>a+b,0)+la.reduce((a,b)=>a+b,0);
  const ar=`λ(home) first 5 min  = ${lh.slice(0,5).map(x=>x.toFixed(4)).join(' + ')} = ${lh.slice(0,5).reduce((a,b)=>a+b,0).toFixed(4)}
λ(away) first 5 min  = ${la.slice(0,5).map(x=>x.toFixed(4)).join(' + ')} = ${la.slice(0,5).reduce((a,b)=>a+b,0).toFixed(4)}
P(no goal, first 5)  = exp(-${s5.toFixed(4)}) = ${Math.exp(-s5).toFixed(4)}   simulated ${g.markets.u05_first5.p.toFixed(4)} ± ${(g.mc_se.first5*2).toFixed(4)}
P(no goal, first 10) = exp(-${s10.toFixed(4)}) = ${Math.exp(-s10).toFixed(4)}   simulated ${g.markets.u05_first10.p.toFixed(4)} ± ${(g.mc_se.first10*2).toFixed(4)}`;
  const labels=(side,name)=>`<div class="small">${name}: profile ${lbl(side.labels.team_profile)} · opposing goalie ${lbl(side.labels.opp_goalie)} · rest/travel ${lbl(side.labels.rest_travel)}</div>`;
  return `<div class="dets"><div class="det">
    <div class="box"><h4>${esc(g.home)} (home) · factor chain</h4>${factorRows(H,g.home)}<h4 class="gap">${esc(g.home)} profile</h4>${profBox(H)}</div>
    <div class="box"><h4>${esc(g.away)} (away) · factor chain</h4>${factorRows(A,g.away)}<h4 class="gap">${esc(g.away)} profile</h4>${profBox(A)}</div>
    <div class="box"><h4>Goal hazard by minute, first 10 (home light / away dark)</h4>${hazardSvg(g)}<h4 class="gap">First-goal timing, simulated</h4>${histSvg(g)}
      <h4 class="gap">Goalie ${esc(g.home)}</h4>${goalieBox(g,'home')}<h4 class="gap">Goalie ${esc(g.away)}</h4>${goalieBox(g,'away')}
      <h4 class="gap">Rest &amp; travel · ${esc(g.home)}</h4>${restBox(H)}<h4 class="gap">Rest &amp; travel · ${esc(g.away)}</h4>${restBox(A)}</div>
  </div>
  <div class="box gap"><h4>Arithmetic</h4><div class="arith">${ar}</div>
    <div class="gap">${labels(H,g.home)}${labels(A,g.away)}</div>
    <div class="small gap"><b>Tier ${g.tier}</b>: ${g.tier_reasons.map(esc).join('; ')}</div>
    <div class="small gap"><b>Not measured</b>: ${g.unmeasured.map(esc).join(' · ')}</div>
    <div class="small gap">1P goals 0 / 1 / 2 / 3+: <span class="num">${g.p1.total_dist.map(pct).join(' / ')}</span> · FG O6.5 ${pct(g.markets.fg_total.over65)} · regulation ${esc(g.home)} ${pct(g.markets.fg_ml.home_reg)} / tie ${pct(g.markets.fg_ml.reg_tie)} / ${esc(g.away)} ${pct(g.markets.fg_ml.away_reg)}</div>
  </div></div>`;
}
function card(g){
  const m=g.markets, u5=Object.assign({},m.u05_first5), u10=Object.assign({},m.u05_first10);
  if(u5.edge==null&&userPrice5){u5.book=userPrice5;u5.edge=u5.p*userPrice5-1;}
  if(u10.edge==null&&userPrice10){u10.book=userPrice10;u10.edge=u10.p*userPrice10-1;}
  const gl=['away','home'].map(s=>{const q=g.goalies[s];return `<span><span class="dot ${q.status}"></span>${esc(q.name||'unknown')} <span class="t">${q.sv_shrunk?('.'+String(q.sv_shrunk.toFixed(3)).slice(2)):''} ${esc(q.status)}</span></span>`}).join('');
  const chip = liveChip(g);
  const o = outcomes(g), oc = k => (o && o.started && o[k]) ? ' o-'+o[k] : '';
  const isOpen = open.has(g.game_id);
  return `<div class="gc" data-id="${g.game_id}">
    <div class="hd"><span><span class="mu">${esc(g.matchup)}</span> ${tier(g.tier)}</span><span class="when">${chip || esc(g.time_et)}<br><span class="t">#${g.rank_u05_first5} for first-5 under${chip?' · '+esc(g.time_et):''}</span></span></div>
    <div class="gl">${gl}</div>
    <div class="pri">
      <div class="${oc('u05_first5')}"><span class="k">Under 0.5 · first 5 min</span><span class="v num ${cls(u5.p,0.70,0.64)}">${pct(u5.p)}${mark(g,'u05_first5')}</span><span class="s">fair ${u5.fair?u5.fair.toFixed(2):'n/a'} ${edge(u5)}</span></div>
      <div class="${oc('u05_first10')}"><span class="k">Under 0.5 · first 10 min</span><span class="v num ${cls(u10.p,0.47,0.42)}">${pct(u10.p)}${mark(g,'u05_first10')}</span><span class="s">fair ${u10.fair?u10.fair.toFixed(2):'n/a'} ${edge(u10)}</span></div>
    </div>
    <div class="sec">
      <div class="${oc('p1_minus05')}"><span class="k">1P −0.5</span><span class="v"><span class="pick">${esc(m.p1_minus05.pick)}</span><span class="num">${pct(m.p1_minus05.p)}</span>${mark(g,'p1_minus05')}</span></div>
      <div class="${oc('p1_plus05')}"><span class="k">1P +0.5</span><span class="v"><span class="pick">${esc(m.p1_plus05.pick)}</span><span class="num">${pct(m.p1_plus05.p)}</span>${mark(g,'p1_plus05')}</span></div>
      <div class="${oc('p1_ml')}"><span class="k">1P ML</span><span class="v"><span class="pick">${esc(m.p1_ml.pick)}</span><span class="num">${pct(m.p1_ml.p)}</span>${mark(g,'p1_ml')}</span><span class="s num">tie ${pct(m.p1_ml.tie)}</span></div>
      <div class="${oc('fg_ml')}"><span class="k">FG ML</span><span class="v"><span class="pick">${esc(m.fg_ml.pick)}</span><span class="num">${pct(m.fg_ml.p)}</span>${mark(g,'fg_ml')}</span></div>
      <div class="${oc('fg_spread')}"><span class="k">FG −1.5</span><span class="v"><span class="pick">${esc(m.fg_spread.pick)}</span><span class="num">${pct(m.fg_spread.p)}</span>${mark(g,'fg_spread')}</span><span class="s num">${esc(m.fg_spread.plus_pick)} +1.5 ${pct(m.fg_spread.plus_p)}</span></div>
      <div class="pj"><span class="k">Projected</span><span class="v num">${g.projected.home.toFixed(1)}–${g.projected.away.toFixed(1)}</span><span class="s num">O5.5 ${pct(m.fg_total.over55)}${mark(g,'fg_over55')}</span></div>
    </div>
    <div class="more"><button data-more="${g.game_id}">${isOpen?'Hide inputs':'Inputs & arithmetic'}</button></div>
    ${isOpen?`<div class="dt">${details(g)}</div>`:''}
  </div>`;
}
function render(){
  const col=cols.find(c=>c.k===sortKey);
  let rows=P.games.filter(g=>tierFilter==='ALL'||g.tier===tierFilter);
  rows.sort((a,b)=>{const x=col.v(a),y=col.v(b);return (x>y?1:x<y?-1:0)*sortDir;});
  tbody.innerHTML=rows.map(g=>{ const o=outcomes(g), live=o&&o.started; return `<tr class="g" data-id="${g.game_id}">${cols.map(c=>`<td class="${c.l?'l':''} ${c.sticky?'sticky':''} ${live&&c.m&&o[c.m]?'o-'+o[c.m]:''}">${c.r(g)}</td>`).join('')}</tr>`+(open.has(g.game_id)?`<tr class="d"><td colspan="${cols.length}"><div class="detwrap">${details(g)}</div></td></tr>`:''); }).join('');
  tbody.querySelectorAll('tr.g').forEach(tr=>tr.onclick=()=>{const id=+tr.dataset.id;open.has(id)?open.delete(id):open.add(id);render();});
  const c=document.getElementById('cards'); c.innerHTML=rows.map(card).join('');
  c.querySelectorAll('.gc .hd, .gc [data-more]').forEach(el=>{el.onclick=(ev)=>{ev.stopPropagation(); const id=+el.closest('.gc').dataset.id; open.has(id)?open.delete(id):open.add(id); render();};});
}
const tb=document.getElementById('toolbar');
tb.innerHTML=`<select id="sortsel" aria-label="sort"><option value="rank">Sort: under 0.5 first 5</option><option value="u10">Sort: under 0.5 first 10</option><option value="p1m">Sort: 1P −0.5</option><option value="p1p">Sort: 1P +0.5</option><option value="fgml">Sort: FG moneyline</option><option value="fgs">Sort: FG −1.5</option><option value="proj">Sort: projected total</option><option value="matchup">Sort: start time</option></select>`
 +`<select id="tiersel" aria-label="tier filter"><option value="ALL">All tiers</option><option value="A">Tier A only</option><option value="B">Tier B only</option><option value="C">Tier C only</option></select>`
 +`<button id="expand">Expand all</button><span class="legend"><span class="res hit">✓</span> hit <span class="res miss">✗</span> miss <span class="res pending">…</span> pending</span>`;
document.getElementById('tiersel').onchange=(e)=>{tierFilter=e.target.value;render();};
document.getElementById('expand').onclick=()=>{if(open.size===P.games.length)open.clear();else P.games.forEach(g=>open.add(g.game_id));render();};
document.getElementById('sortsel').onchange=(e)=>{sortKey=e.target.value;sortDir=(sortKey==='rank'||sortKey==='matchup')?1:-1;render();};

// ---------------------------------------------------------------- picks tab
const VN = (M.validation||{});
const EDGE_MAP = {u05_first5:{early:'first5'}, u05_first10:{early:'first10'}, fg_ml:{joint:['fg_ml_home']}, fg_spread:{joint:['fg_home_minus15','fg_away_minus15']}, p1_plus05:{joint:['p1_home_win','p1_away_win']}, p1_minus05:{joint:['p1_home_win','p1_away_win']}, p1_ml:{joint:['p1_home_win','p1_away_win']}};
const JOINT_LABEL = {fg_ml_home:'home win', fg_home_minus15:'home −1.5', fg_away_minus15:'away −1.5', p1_home_win:'1P home win', p1_away_win:'1P away win'};
function edgeNote(key){ const d=EDGE_MAP[key]; if(!d) return '';
  if(d.early){ const v=VN[d.early]; if(!v) return ''; const ok=v.logloss_model<v.logloss_baseline; return `<div class="note ${ok?'ok':'no'}">${ok?'Backtest: ranking games this way beat the league constant.':'Backtest: no ranking edge. These are calibrated probabilities, not a selection; the price decides.'}</div>`; }
  const have=d.joint.filter(k=>VN[k]); if(!have.length) return '';
  const good=have.filter(k=>VN[k].logloss_model<VN[k].logloss_constant), bad=have.filter(k=>!(VN[k].logloss_model<VN[k].logloss_constant));
  if(!bad.length) return `<div class="note ok">Backtest: ranking games this way beat the league constant.</div>`;
  if(!good.length) return `<div class="note no">Backtest: no ranking edge; treat these as calibrated probabilities, not a selection.</div>`;
  return `<div class="note ok">Backtest: edge on the ${good.map(k=>JOINT_LABEL[k]).join(', ')} side; none on the ${bad.map(k=>JOINT_LABEL[k]).join(', ')} side.</div>`; }
const PICK_DEFS = {
  u05_first5:{t:'Under 0.5 · first 5 minutes', w:'No goal by either team before 5:00. League rate about 66%.', showPick:false},
  u05_first10:{t:'Under 0.5 · first 10 minutes', w:'No goal by either team before 10:00. League rate about 42%.', showPick:false},
  p1_plus05:{t:'1P +0.5', w:'The pick wins or ties the first period.', showPick:true},
  p1_minus05:{t:'1P −0.5', w:'The pick wins the first period outright.', showPick:true},
  p1_ml:{t:'1P moneyline', w:'Three-way: win the period; a tie loses.', showPick:true},
  fg_ml:{t:'Full-game moneyline', w:'Wins the game, overtime and shootout included.', showPick:true},
  fg_spread:{t:'Full-game −1.5', w:'The pick wins by two or more goals.', showPick:true},
};
function pickCard(key){
  const d=PICK_DEFS[key], list=(P.top||{})[key]||[];
  return `<div class="pk"><h3>${d.t}</h3><div class="why">${d.w}</div><ol>${list.map((x,i)=>`<li><span><span class="t num">${i+1}.</span> <span class="mu">${esc(x.matchup)}</span>${d.showPick&&x.pick?`<span class="pick" style="margin-left:6px">${esc(x.pick)}</span>`:''} ${tier(x.tier)}</span><span class="p num">${pct(x.p)}${byId[x.game_id]?mark(byId[x.game_id],key):''}</span></li>`).join('')}</ol>${edgeNote(key)}</div>`;
}
function renderPicks(){
  document.getElementById('picks-early').innerHTML = pickCard('u05_first5')+pickCard('u05_first10');
  document.getElementById('picks-p1').innerHTML = pickCard('p1_plus05')+pickCard('p1_minus05')+pickCard('p1_ml');
  document.getElementById('picks-fg').innerHTML = pickCard('fg_ml')+pickCard('fg_spread');
}

// ---------------------------------------------------------------- results tab: track record + past days
const SC = M.scorecard;
if (SC && SC.games_scored) {
  const rows = Object.entries(SC.markets||{}).map(([k,v])=>`<tr><td>${MARKET_NAMES[k]||k}</td><td class="num">${v.n}</td><td class="num">${pct(v.hit_rate)}</td><td class="num">${pct(v.mean_pred)}</td><td class="num">${v.brier.toFixed(4)}</td></tr>`).join('');
  const top = Object.entries(SC.top3||{}).map(([k,v])=>`<tr><td>Top 3 · ${MARKET_NAMES[k]||k}</td><td class="num">${v.n}</td><td class="num">${pct(v.hit_rate)}</td><td class="num">${pct(v.mean_pred)}</td><td></td></tr>`).join('');
  const potd = SC.pick_of_day && SC.pick_of_day.n ? `<tr><td>Highest-probability first-5 pick</td><td class="num">${SC.pick_of_day.n}</td><td class="num">${pct(SC.pick_of_day.hit_rate)}</td><td class="num">${pct(SC.pick_of_day.mean_pred)}</td><td></td></tr>` : '';
  document.getElementById('results-track').innerHTML = `<div class="panel"><h3>Track record · ${SC.games_scored} games over ${SC.days_scored} published days</h3>
  <p>Scored every morning on the exact numbers that were on the page. Hit rate is what happened; predicted is what the page said; the two should sit close together over enough games.</p>
  <div class="tbl"><table><thead><tr><th>market</th><th>n</th><th>hit rate</th><th>predicted</th><th>brier</th></tr></thead><tbody>${rows}${top}${potd}</tbody></table></div></div>`;
} else {
  document.getElementById('results-track').innerHTML = `<div class="panel"><h3>Track record</h3><p>Starts accumulating the morning after the first published slate. Every market on every game is scored on the exact numbers that were on the page.</p></div>`;
}

// ---------------------------------------------------------------- about tab
const V = M.validation;
if (V && V.first5) {
  const rowsV = [
    ['Under 0.5 · first 5 min', V.first5.logloss_model, V.first5.logloss_baseline, V.first5.top_quintile_actual, V.first5.bottom_quintile_actual, V.first5.mean_pred, V.first5.actual_rate],
    ['Under 0.5 · first 10 min', V.first10.logloss_model, V.first10.logloss_baseline, V.first10.top_quintile_actual, V.first10.bottom_quintile_actual, V.first10.mean_pred, V.first10.actual_rate],
  ];
  const jm = {fg_ml_home:'FG moneyline (home)', fg_home_minus15:'FG home −1.5', fg_away_minus15:'FG away −1.5', fg_over55:'FG over 5.5', p1_home_win:'1P home win', p1_away_win:'1P away win', p1_tie:'1P tie'};
  for (const [k,label] of Object.entries(jm)) if (V[k]) rowsV.push([label, V[k].logloss_model, V[k].logloss_constant, V[k].top_quintile_actual, V[k].bottom_quintile_actual, V[k].mean_pred, V[k].actual]);
  document.getElementById('validation').innerHTML = `<div class="panel"><h3>Validation · ${V.season?String(V.season).slice(0,4)+'-'+String(V.season).slice(6):''} season, ${V.n} real games, each predicted only from games before it</h3>
  <p>Log loss below the league constant means ranking games this way carries information. Top vs bottom quintile shows how far the ranking separates outcomes in reality.</p>
  <div class="tbl"><table><thead><tr><th>market</th><th>verdict</th><th>log loss model</th><th>league constant</th><th>top 20% hit</th><th>bottom 20% hit</th><th>predicted</th><th>actual</th></tr></thead><tbody>
  ${rowsV.map(r=>`<tr><td>${r[0]}</td><td class="${r[1]<r[2]?'ok':'no'}">${r[1]<r[2]?'beats constant':'no edge'}</td><td class="num">${r[1].toFixed(4)}</td><td class="num">${r[2].toFixed(4)}</td><td class="num">${pct(r[3])}</td><td class="num">${pct(r[4])}</td><td class="num">${pct(r[5])}</td><td class="num">${pct(r[6])}</td></tr>`).join('')}
  </tbody></table></div>
  <p>The early-goal probabilities are calibrated: they land where they say they land. But no pre-game input separated games that produced an early goal from games that did not, so the fair price is the useful output there. The full-game markets and the 1P away win do carry a measurable edge.</p></div>`;
}
document.getElementById('method').innerHTML = `<h3>How the numbers are made</h3>
<p>Every team's goal rate per minute is a chain of factors on the league hazard curve for that minute of the game: home ice, shot rate for, the opponent's shot rate against, finishing, the opposing starting goalie's save% and rest / travel. Everything is measured from three seasons of play-by-play and shrunk toward the league average. Under 0.5 in the first 5 minutes is exp(−Σλ) over those minutes; the simulation (${P.games[0]?P.games[0].sims.toLocaleString():'100,000'} paths per game, with 3-on-3 overtime, shootout and goalie-pull dynamics) adds the period and full-game markets.</p>
<p>Starting goalies come from DailyFaceoff with the reporter who confirmed them; a goalie still only expected keeps the game at tier B. Line deployment, officials and late scratches are not visible pre-game and are listed as unmeasured on every game.</p>
<p>Precision: ±0.3 points from the simulation, about ±1.5 points from the model on the early markets. Judge the engine on the validation table and the track record, never on one night.</p>`;
document.getElementById('glossary').innerHTML = `<h3>Reading the page</h3><dl>
<dt>Under 0.5 · first 5 / first 10</dt><dd>Probability that neither team scores before 5:00 or 10:00 of the first period. "Fair" is the break-even decimal price (1 ÷ probability).</dd>
<dt>Price check</dt><dd>Type your book's price; the page shows break-even and expected value. Prices stay in your browser.</dd>
<dt>1P −0.5 / +0.5 / ML</dt><dd>First-period markets: win the period outright, win or tie, and the three-way moneyline where a tie loses.</dd>
<dt>FG ML / −1.5 / +1.5</dt><dd>Full-game moneyline including overtime and shootout; the spread needs a two-goal margin (or a loss by at most one).</dd>
<dt>Tier A / B / C</dt><dd>A: both profiles measured on this season and both goalies confirmed. B: a goalie not yet confirmed, or a profile leaning on last season. C: something unmeasured.</dd>
<dt>✓ ✗ … tie</dt><dd>Live result marks: hit, miss, pending, or a tie for the 1P moneyline.</dd>
<dt>Inputs &amp; arithmetic</dt><dd>Every game expands to its factor chain, goalie, rest and travel, the exact exp(−Σλ) line, and what was and was not measured.</dd></dl>`;
document.getElementById('foot').innerHTML = `Early Goal Desk v${P.model_version} · data: NHL play-by-play via the public NHL API and the sportsdataverse nightly release · generated ${esc(P.generated_utc)}`;

// past days list (filled by the site builder's days.json if present)
(function(){ const tryUrl = u => fetch(u, {cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));
  tryUrl('./days.json').catch(()=>tryUrl('../days.json')).then(j=>{ const dl=document.getElementById('daylist'); if(!j||!j.days){ dl.innerHTML='<span class="small">no history yet</span>'; return; }
    const base = location.pathname.includes('/days/') ? '../days/' : './days/';
    const lab = d => { const k=dayDiff(d,TODAY); return k===0?'Today · '+niceDate(d):(k===1?'Tomorrow · '+niceDate(d):niceDate(d)); };
    dl.innerHTML = j.days.map(d=>`<a class="${d===P.date?'now':''}" href="${base}${d}.html">${lab(d)}</a>`).join(''); }).catch(()=>{ document.getElementById('daylist').innerHTML='<span class="small">history appears once the site is published</span>'; });
})();

renderFeature(); renderPicks(); render(); loadLive();
</script>
</body>
</html>
"""


def _esc(x: object) -> str:
    return str("" if x is None else x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def static_summary(payload: dict) -> str:
    """A plain-HTML version of the slate for readers without JavaScript: URL fetchers, link previews,
    screen readers, search engines. The interactive page removes it on load."""
    games = sorted(payload["games"], key=lambda g: g["rank_u05_first5"])
    meta = payload.get("meta", {})
    potd = payload.get("pick_of_day")
    pc = lambda x: f"{x*100:.1f}%"  # noqa: E731
    rows = []
    for g in games:
        m = g["markets"]
        ga, gh = g["goalies"]["away"], g["goalies"]["home"]
        rows.append(
            f"<tr><td>{g['rank_u05_first5']}</td><td>{_esc(g['matchup'])} ({g['tier']})</td><td>{_esc(g['time_et'])}</td>"
            f"<td>{_esc(ga.get('name') or 'unknown')} ({_esc(ga.get('status'))}) / {_esc(gh.get('name') or 'unknown')} ({_esc(gh.get('status'))})</td>"
            f"<td>{pc(m['u05_first5']['p'])} (fair {m['u05_first5']['fair']:.2f})</td><td>{pc(m['u05_first10']['p'])} (fair {m['u05_first10']['fair']:.2f})</td>"
            f"<td>{_esc(m['p1_minus05']['pick'])} {pc(m['p1_minus05']['p'])}</td><td>{_esc(m['p1_plus05']['pick'])} {pc(m['p1_plus05']['p'])}</td>"
            f"<td>{_esc(m['p1_ml']['pick'])} {pc(m['p1_ml']['p'])}</td><td>{_esc(m['fg_ml']['pick'])} {pc(m['fg_ml']['p'])}</td>"
            f"<td>{_esc(m['fg_spread']['pick'])} -1.5 {pc(m['fg_spread']['p'])}</td><td>{g['projected']['home']:.2f} - {g['projected']['away']:.2f}</td></tr>"
        )
    head = (f"<h1>Early Goal Desk: NHL slate for {_esc(payload['date'])}</h1>"
            f"<p>{len(games)} games, {meta.get('sims', 100000):,} simulated paths per game, generated {_esc(payload.get('generated_utc'))}. "
            f"Goalies: {_esc(meta.get('goalie_source', 'projected'))}. Data through {_esc(meta.get('data_through', 'n/a'))}. "
            f"Tier A: both goalies confirmed and both team profiles measured this season; B: a goalie not yet confirmed; C: an input unmeasured.</p>")
    if potd:
        head += (f"<p>Highest probability for under 0.5 goals in the first 5 minutes: {_esc(potd['matchup'])} at {pc(potd['p'])} "
                 f"(fair price {potd['fair']:.2f}, tier {potd['tier']}). The spread between games is within noise; the price decides whether the bet is worth placing.</p>")
    table = ("<table><thead><tr><th>#</th><th>Matchup (tier)</th><th>Start</th><th>Goalies away / home</th><th>Under 0.5, first 5 min</th>"
             "<th>Under 0.5, first 10 min</th><th>1P -0.5</th><th>1P +0.5</th><th>1P ML</th><th>FG ML</th><th>FG spread</th><th>Projected home - away</th></tr></thead>"
             f"<tbody>{''.join(rows)}</tbody></table>")
    return f'<div id="static" class="static">{head}{table}<p>Open this page in a browser for live results, the price check, the ranked picks and every game\'s inputs.</p></div>'


def render(payload: dict) -> str:
    html = TEMPLATE.replace("__PAYLOAD__", json.dumps(payload).replace("</", "<\\/"))
    return html.replace("__STATIC__", static_summary(payload), 1)


def write_dashboard(payload: dict, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(payload), encoding="utf-8")
    return path


def render_fragment(payload: dict) -> str:
    """Body-only version (no document skeleton) for hosts that wrap the page themselves."""
    html = render(payload)
    start = html.index("<title>")
    end = html.rindex("</body>")
    return html[start:end]
