"""Self-contained dark dashboard (single HTML file, no external assets)."""
from __future__ import annotations

import json
from pathlib import Path

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Early Goal Desk</title>
<style>
:root{--bg:#070c14;--panel:#0d1522;--panel2:#111c2d;--line:#1b2a3f;--text:#e7eef8;--muted:#8da0b9;--dim:#5f7390;
--ice:#6fd3ff;--green:#3ddc84;--amber:#f6b73c;--red:#ff6b6b;--violet:#a78bfa;color-scheme:dark}
*{box-sizing:border-box}
html,body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.4;-webkit-font-smoothing:antialiased}
body{background:radial-gradient(1200px 500px at 50% -120px,rgba(111,211,255,.10),transparent 60%),var(--bg)}
.num{font-variant-numeric:tabular-nums;font-feature-settings:"tnum"}
.wrap{max-width:1360px;margin:0 auto;padding-block:18px 60px;padding-inline:16px}
header{display:flex;flex-wrap:wrap;align-items:flex-end;justify-content:space-between;gap:12px;margin-bottom:14px}
.brand{display:flex;flex-direction:column;gap:4px}
.brand h1{margin:0;font-size:22px;letter-spacing:.14em;font-weight:800;text-transform:uppercase}
.brand h1 span{color:var(--ice)}
.brand .sub{color:var(--muted);font-size:13px}
.chips{display:flex;flex-wrap:wrap;gap:6px}
.chip{border:1px solid var(--line);background:var(--panel);border-radius:999px;padding:5px 11px;font-size:12px;color:var(--muted)}
.chip b{color:var(--text);font-weight:600}
.banner{border:1px solid rgba(246,183,60,.5);background:rgba(246,183,60,.08);color:#ffd27a;border-radius:10px;padding:10px 14px;margin:10px 0 16px;font-size:13px}
.pricebar{display:flex;flex-wrap:wrap;align-items:center;gap:10px 16px;border:1px solid var(--line);background:var(--panel);border-radius:12px;padding:10px 14px;margin:0 0 12px;font-size:13px;color:var(--muted)}
.pricebar label{display:flex;align-items:center;gap:8px;color:var(--text);font-weight:600}
.pricebar input{width:76px;background:#0a1220;border:1px solid var(--line);color:var(--text);border-radius:8px;padding:6px 8px;font-size:14px;font-variant-numeric:tabular-nums}
.pricebar input:focus{outline:2px solid var(--ice);outline-offset:1px}
.pricebar .verdict{font-weight:700}
.pricebar .verdict.neg{color:var(--red)}.pricebar .verdict.pos{color:var(--green)}
.valid{border:1px solid var(--line);background:var(--panel);border-radius:14px;padding:14px 16px;margin-top:18px}
.valid h3{margin:0 0 6px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted)}
.valid .tbl{overflow-x:auto;margin:6px 0}
.valid table{min-width:0;width:100%}
.valid td,.valid th{padding:5px 6px;font-size:12px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
.valid td:first-child,.valid th:first-child{text-align:left}
.valid th{position:static;background:transparent;cursor:default;letter-spacing:.06em}
.valid .ok{color:var(--green);font-weight:700}.valid .no{color:var(--amber);font-weight:700}
.valid p{margin:6px 0;font-size:13px;color:var(--muted);max-width:70ch}
.res{display:inline-block;font-size:11px;font-weight:800;margin-left:5px;vertical-align:middle;border-radius:5px;padding:0 5px}
.res.hit{color:var(--green);background:rgba(61,220,132,.14)}.res.miss{color:var(--red);background:rgba(255,107,107,.14)}.res.tie{color:var(--amber);background:rgba(246,183,60,.14)}.res.pending{color:var(--dim)}
.lv{display:inline-block;font-size:10.5px;font-weight:700;letter-spacing:.06em;border-radius:6px;padding:2px 7px;margin-top:3px}
.lv.live{color:#ff8a8a;background:rgba(255,107,107,.12);border:1px solid rgba(255,107,107,.35)}
.lv.final{color:var(--text);background:rgba(255,255,255,.08);border:1px solid var(--line)}
.lv.pre{color:var(--dim);border:1px solid var(--line)}
.livebar{border:1px solid rgba(255,138,138,.35);background:rgba(255,107,107,.06);border-radius:12px;padding:10px 14px;margin:0 0 12px;font-size:13px;color:var(--muted);display:none}
.livebar b{color:var(--text)}
.rbtn{background:var(--panel);border:1px solid var(--line);color:var(--ice);border-radius:8px;padding:5px 10px;font-size:12px;cursor:pointer;margin-left:8px;vertical-align:middle}
.rbtn:disabled{opacity:.6;cursor:default}
#ptr{position:fixed;top:0;left:0;right:0;text-align:center;font-size:12px;color:var(--muted);background:var(--panel);border-bottom:1px solid var(--line);padding:8px;transform:translateY(-100%);transition:transform .15s;z-index:20;padding-top:calc(8px + env(safe-area-inset-top, 0px))}
#ptr.show{transform:translateY(0)}
#fab{position:fixed;right:16px;bottom:calc(16px + env(safe-area-inset-bottom, 0px));width:46px;height:46px;border-radius:50%;background:var(--panel2);border:1px solid var(--ice);color:var(--ice);font-size:22px;line-height:44px;text-align:center;cursor:pointer;z-index:19;box-shadow:0 6px 20px rgba(0,0,0,.4);display:none}
@media (max-width:700px){#fab{display:block}}
#fab.spin{animation:spin 1s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion: reduce){#fab.spin{animation:none}}
.livebar .k{display:inline-block;margin:2px 14px 2px 0;white-space:nowrap}
.grid-cards{display:grid;grid-template-columns:1.4fr repeat(3,1fr);gap:12px;margin-bottom:12px}
.grid-cards2{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
@media (max-width:980px){.grid-cards{grid-template-columns:1fr 1fr}.grid-cards2{grid-template-columns:1fr 1fr}}
@media (max-width:560px){.grid-cards,.grid-cards2{grid-template-columns:1fr}}
.card{background:linear-gradient(180deg,var(--panel2),var(--panel));border:1px solid var(--line);border-radius:14px;padding:14px 16px;min-height:120px;position:relative;overflow:hidden}
.card h3{margin:0 0 8px;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);font-weight:700}
.potd{border-color:rgba(111,211,255,.45);box-shadow:0 0 0 1px rgba(111,211,255,.12) inset,0 12px 40px rgba(111,211,255,.08)}
.potd .big{font-size:42px;font-weight:800;color:var(--green);line-height:1;margin:6px 0 4px}
.potd .mu{font-size:20px;font-weight:700}
.potd .mk{color:var(--muted);font-size:13px}
.potd .ru{margin-top:8px;color:var(--dim);font-size:12px}
.top li{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-top:1px dashed var(--line);font-size:13px}
.top li:first-child{border-top:0}
.top ol{margin:0;padding:0;list-style:none}
.top .p{font-weight:700;color:var(--green)}
.top .mu{font-weight:600}
.top .pk{color:var(--ice);font-weight:700;margin-left:6px}
.tier{display:inline-block;font-size:10px;font-weight:800;border-radius:6px;padding:2px 6px;letter-spacing:.08em;vertical-align:middle}
.tier.A{background:rgba(61,220,132,.15);color:var(--green);border:1px solid rgba(61,220,132,.4)}
.tier.B{background:rgba(246,183,60,.14);color:var(--amber);border:1px solid rgba(246,183,60,.4)}
.tier.C{background:rgba(255,107,107,.12);color:var(--red);border:1px solid rgba(255,107,107,.4)}
.toolbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:6px 0 10px;color:var(--muted);font-size:12px}
.toolbar button{background:var(--panel);border:1px solid var(--line);color:var(--text);border-radius:8px;padding:6px 10px;font-size:12px;cursor:pointer}
.toolbar button.on{border-color:var(--ice);color:var(--ice)}
.toolbar select{background:var(--panel);border:1px solid var(--line);color:var(--text);border-radius:8px;padding:6px 8px;font-size:12px}
.toolbar .sorthint{display:inline}
@media (max-width:700px){.toolbar .sorthint{display:none}}
.tablewrap{overflow:auto;border:1px solid var(--line);border-radius:14px;background:var(--panel)}
.cards{display:none;flex-direction:column;gap:10px}
.gc{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px;cursor:pointer}
.gc .hd{display:flex;justify-content:space-between;align-items:baseline;gap:8px}
.gc .hd .mu{font-size:16px}
.gc .gl{display:flex;flex-direction:column;gap:2px;margin:6px 0 8px;font-size:12px;color:var(--muted)}
.gc .mk{display:grid;grid-template-columns:repeat(3,1fr);gap:8px 10px}
.gc .mk div{background:#0a1220;border:1px solid var(--line);border-radius:10px;padding:7px 9px;min-width:0}
.gc .mk .k{display:block;font-size:9.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--dim);margin-bottom:2px;white-space:nowrap}
.gc .mk .v{font-weight:700;font-size:14px}
.gc .mk .s{display:block;font-size:11px;color:var(--muted);white-space:nowrap}
.gc .mk .big{grid-column:span 3;display:flex;justify-content:space-between;align-items:center}
.gc .mk .big .v{font-size:22px}
.gc .dt{margin-top:10px;cursor:default}
@media (max-width:700px){.tablewrap{display:none}.cards{display:flex}}
table{border-collapse:separate;border-spacing:0;width:100%;min-width:1180px}
thead th{position:sticky;top:0;background:#0b1320;z-index:3;font-size:10.5px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);font-weight:700;padding:10px 8px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap;cursor:pointer;user-select:none}
thead th.l{text-align:left}
thead th .u{font-size:9px;display:block;color:var(--dim);letter-spacing:.06em;margin-top:2px}
tbody td{padding:9px 7px;border-bottom:1px solid var(--line);text-align:center;white-space:nowrap;vertical-align:middle}
tbody tr.g:hover td{background:rgba(111,211,255,.04)}
tbody tr.g{cursor:pointer}
td.l{text-align:left}
td.sticky,th.sticky{position:sticky;left:0;background:var(--panel);z-index:2}
th.sticky{z-index:4;background:#0b1320}
.mu{font-weight:700}
.t{color:var(--dim);font-size:11px}
.pct{font-weight:700}
.hi{color:var(--green)}.mid{color:var(--text)}.lo{color:var(--muted)}
.pick{color:var(--ice);font-weight:700;margin-right:5px}
.fair{color:var(--dim);font-size:11px}
.edge{font-size:11px;font-weight:700}
.edge.pos{color:var(--green)}.edge.neg{color:var(--red)}
.goalie{font-size:12px;text-align:left}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px;vertical-align:middle}
.dot.confirmed{background:var(--green)}.dot.expected{background:var(--amber)}.dot.projected,.dot.unconfirmed{background:var(--amber);opacity:.6}.dot.unknown{background:var(--red)}
.bar{height:5px;background:#162236;border-radius:3px;overflow:hidden;margin-top:4px}
.bar i{display:block;height:100%;background:linear-gradient(90deg,var(--ice),var(--green))}
tr.d td{background:#0a111c;padding:12px 10px;white-space:normal;cursor:default}
.detwrap{position:sticky;left:0;max-width:calc(100vw - 36px)}
.gc .det{grid-template-columns:1fr}
.det{display:grid;grid-template-columns:1.1fr 1.1fr 1fr;gap:14px}
@media (max-width:900px){.det{grid-template-columns:1fr}}
.box{background:var(--panel2);border:1px solid var(--line);border-radius:12px;padding:12px 14px;text-align:left;min-width:0;overflow:hidden}
.dets{min-width:0}
.box h4{margin:0 0 8px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.box table{min-width:0;width:100%}
.dets .box td,.dets .box th{padding:4px 6px;font-size:12px;border:0;background:transparent;text-align:right;white-space:normal;line-height:1.35}
.dets .box td:first-child,.dets .box th:first-child{text-align:left;color:var(--muted)}
.dets .box tr:nth-child(even) td{background:rgba(255,255,255,.025)}
.dets .box th{position:static;cursor:default;text-transform:none;letter-spacing:0;font-size:11px}
.lbl{display:inline-block;font-size:10px;font-weight:800;letter-spacing:.06em;border-radius:5px;padding:1px 6px;margin-left:6px}
.lbl.measured{color:var(--green);background:rgba(61,220,132,.12)}.lbl.partial{color:var(--amber);background:rgba(246,183,60,.12)}.lbl.unmeasured{color:var(--red);background:rgba(255,107,107,.12)}
.arith{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11.5px;color:#bcd3f0;background:#0a1220;border:1px solid var(--line);border-radius:8px;padding:8px 10px;overflow:auto;white-space:pre}
.small{font-size:12px;color:var(--muted)}
.gap{margin-top:10px}
svg text{font-family:inherit}
footer{margin-top:28px;color:var(--muted);font-size:12px;line-height:1.55}
footer h5{color:var(--text);margin:14px 0 4px;font-size:12px;letter-spacing:.1em;text-transform:uppercase}
details summary{cursor:pointer;color:var(--ice)}
</style>
</head>
<body>
<div class="wrap">
<header>
  <div class="brand">
    <h1>Early <span>Goal</span> Desk</h1>
    <div class="sub" id="sub"></div>
  </div>
  <div class="chips" id="chips"></div>
</header>
<div id="banner"></div>
<div class="pricebar" id="pricebar"></div>
<div class="livebar" id="livebar"></div>
<div id="ptr">Release to refresh</div>
<button id="fab" title="Refresh live results" aria-label="Refresh live results">↻</button>
<div class="grid-cards" id="cards1"></div>
<div class="grid-cards2" id="cards2"></div>
<div class="toolbar" id="toolbar"></div>
<div class="tablewrap"><table id="tbl"><thead></thead><tbody></tbody></table></div>
<div class="cards" id="cards"></div>
<div id="validation"></div>
<footer id="foot"></footer>
</div>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
const P = JSON.parse(document.getElementById('payload').textContent);
const pct = x => (x*100).toFixed(1)+'%';
const cls = (x, hi, mid) => x>=hi?'hi':(x>=mid?'mid':'lo');
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const tier = t => `<span class="tier ${t}">${t}</span>`;
const fair = m => m.fair ? `<span class="fair">fair ${m.fair.toFixed(2)}</span>` : '';
const edge = m => (m.edge==null) ? '' : `<span class="edge ${m.edge>=0?'pos':'neg'}">${m.edge>=0?'+':''}${(m.edge*100).toFixed(1)}% vs ${m.book}</span>`;
const M = P.meta || {};

document.getElementById('sub').textContent = `${P.date} · ${P.games.length} games · ${P.games[0]?P.games[0].sims.toLocaleString():0} simulations per game · generated ${P.generated_utc}`;
document.getElementById('chips').innerHTML = [
  `model <b>v${P.model_version}</b>`,
  `profile <b>${P.league.games_in_profile}</b> games (<b>${P.league.current_season_games}</b> this season)`,
  P.league.p_no_goal_5_observed!=null ? `league no-goal first 5 <b>${pct(P.league.p_no_goal_5_observed)}</b>` : 'league priors',
  P.league.p_no_goal_10_observed!=null ? `first 10 <b>${pct(P.league.p_no_goal_10_observed)}</b>` : '',
  M.data_through ? `data through <b>${esc(M.data_through)}</b>` : '',
  M.goalie_source ? `goalies <b>${esc(M.goalie_source)}</b>` : ''
].filter(Boolean).map(c=>`<span class="chip">${c}</span>`).join('');

if (M.demo) document.getElementById('banner').innerHTML = `<div class="banner"><b>DEMO DATA.</b> Team and goalie inputs are synthetic. Run <code>python -m earlygoal ingest</code> then <code>python -m earlygoal run</code> to build this from real NHL play-by-play.</div>`;
else if (M.data_through) { const lag = Math.round((new Date(P.date) - new Date(M.data_through)) / 86400000); if (lag > 2) document.getElementById('banner').innerHTML = `<div class="banner"><b>Data is ${lag} days behind this slate</b> (play-by-play through ${esc(M.data_through)}). Profiles and rest days may be stale; treat the numbers with extra caution until the data source catches up.</div>`; }

// ---- cards
const potd = P.pick_of_day;
const ps5 = P.games.map(g=>g.markets.u05_first5.p), lo5=Math.min(...ps5), hi5=Math.max(...ps5);
function renderTopCards(){
let c1 = '';
if (potd) c1 += `<div class="card potd"><h3>Highest probability tonight · ${tier(potd.tier)}</h3><div class="mu">${esc(potd.matchup)}</div><div class="mk">${esc(potd.market)}</div><div class="big num">${pct(potd.p)}${(function(){const g=P.games.find(x=>x.game_id===potd.game_id);return g?mark(g,'u05_first5'):''})()}</div><div class="small">fair price ${potd.fair.toFixed(2)} · slate range ${pct(lo5)} to ${pct(hi5)} · league rate ${P.league.p_no_goal_5_observed!=null?pct(P.league.p_no_goal_5_observed):'n/a'}</div>${potd.runner_up?`<div class="ru">runner-up ${esc(potd.runner_up.matchup)} ${pct(potd.runner_up.p)} ${tier(potd.runner_up.tier)}</div>`:''}</div>`;
const VN = (M.validation||{});
const edgeNote = key => { const map = {u05_first5:['first5',null], u05_first10:['first10',null], fg_ml:[null,'fg_ml_home'], fg_spread:[null,'fg_home_minus15'], p1_plus05:[null,'p1_home_win'], p1_minus05:[null,'p1_home_win'], p1_ml:[null,'p1_away_win']};
  const [e, j] = map[key]||[]; let ok = null;
  if (e && VN[e]) ok = VN[e].logloss_model < VN[e].logloss_baseline; else if (j && VN[j]) ok = VN[j].logloss_model < VN[j].logloss_constant;
  if (ok === null) return ''; return `<div class="t" style="margin-top:6px">${ok ? 'backtest: ranking beats the league constant' : 'backtest: no ranking edge, sorted by probability'}</div>`; };
const byId = {}; P.games.forEach(g=>byId[g.game_id]=g);
const topMark = (x, key) => { const g = byId[x.game_id]; return g ? mark(g, key) : ''; };
const topCard = (title, key, showPick) => `<div class="card top"><h3>${title}</h3><ol>${(P.top[key]||[]).map((x,i)=>`<li><span><span class="num t">${i+1}.</span> <span class="mu">${esc(x.matchup)}</span>${showPick&&x.pick?`<span class="pk">${esc(x.pick)}</span>`:''} ${tier(x.tier)}</span><span class="p num">${pct(x.p)}${topMark(x,key)}</span></li>`).join('')}</ol>${edgeNote(key)}</div>`;
c1 += topCard('Top 3 · Under 0.5, first 5:00','u05_first5',false);
c1 += topCard('Top 3 · Under 0.5, first 10:00','u05_first10',false);
c1 += topCard('Top 3 · 1P +0.5','p1_plus05',true);
document.getElementById('cards1').innerHTML = c1;
document.getElementById('cards2').innerHTML = topCard('Top 3 · 1P -0.5','p1_minus05',true)+topCard('Top 3 · 1P moneyline (win period)','p1_ml',true)+topCard('Top 3 · FG moneyline','fg_ml',true)+topCard('Top 3 · FG -1.5','fg_spread',true);
}

// ---- live results (facts in live.json, published by the live update; picks come from the page)
let LIVE = null;
function liveFor(g){ return LIVE && LIVE.date===P.date && LIVE.games ? LIVE.games[String(g.game_id)] : null; }
function outcomes(g){
  const L = liveFor(g); if(!L) return null;
  const m = g.markets, home = g.home, fg = L.first_goal_min, started = L.live || L.final;
  const o = {};
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
  o.started = started;
  return o;
}
const RES = {hit:'✓', miss:'✗', tie:'tie', pending:'…', over:'over', under:'under'};
function mark(g, key){ const o = outcomes(g); if(!o || !o.started) return ''; const r = o[key]; if(!r) return ''; return `<span class="res ${r==='over'||r==='under'?'tie':r}" title="${r}">${RES[r]}</span>`; }
function liveChip(g){
  const L = liveFor(g); if(!L) return '';
  if (L.final) return `<span class="lv final">FINAL ${L.away} ${L.away_score} · ${L.home} ${L.home_score}${L.ended_in && L.ended_in!=='REG' ? ' ('+L.ended_in+')' : ''}</span>`;
  if (L.live) return `<span class="lv live">LIVE P${L.period} ${esc(L.time_remaining||'')} · ${L.away} ${L.away_score} · ${L.home} ${L.home_score}</span>`;
  if (L.state==='PRE') return `<span class="lv pre">warm-up</span>`;
  return '';
}
function renderLiveBar(){
  const bar = document.getElementById('livebar');
  if (!LIVE || LIVE.date!==P.date) { bar.style.display='none'; return; }
  const keys = [['u05_first5','U0.5 first 5'],['u05_first10','U0.5 first 10'],['p1_minus05','1P −0.5'],['p1_plus05','1P +0.5'],['p1_ml','1P ML'],['fg_ml','FG ML'],['fg_spread','FG −1.5']];
  const tally = {}; let started=0, finals=0;
  P.games.forEach(g=>{ const o=outcomes(g); if(!o||!o.started) return; started++; const L=liveFor(g); if(L.final) finals++;
    keys.forEach(([k])=>{ const t = tally[k] = tally[k]||{hit:0,miss:0,tie:0,pending:0}; t[o[k]] = (t[o[k]]||0)+1; }); });
  if (!started) { bar.innerHTML = `<div><b>Live results</b> · no game has started yet (as of ${esc(LIVE.updated_et)}) · snapshots every 20 minutes once games begin<button class="rbtn">↻ Refresh</button></div>`; bar.style.display='block'; return; }
  const parts = keys.map(([k,n])=>{ const t=tally[k]; const dec=t.hit+t.miss+t.tie; return dec ? `<span class="k">${n}: <b>${t.hit}</b> hit / ${t.miss} miss${t.tie?' / '+t.tie+' tie':''}${t.pending?' / '+t.pending+' pending':''}</span>` : ''; }).filter(Boolean).join('');
  bar.innerHTML = `<div><b>${finals===started&&started===P.games.length?'Results':'Live results'}</b> ${LIVE.updated_et==='final results'?'(all games final)':'as of '+esc(LIVE.updated_et)} · ${started} of ${P.games.length} games started, ${finals} final${LIVE.updated_et==='final results'?'':(LIVE.source==='scoreboard'?' · live from the NHL scoreboard, refreshed every 30 seconds':' · scoreboard snapshots every 20 minutes during games')}<button class="rbtn">↻ Refresh</button></div><div style="margin-top:4px">${parts}</div>`;
  bar.style.display='block';
}
function liveFromScorecard(sc){
  // a past day's page: rebuild the live facts from the scored results so the marks still show
  const day = sc && sc.days && sc.days[P.date]; if(!day || !day.games) return null;
  const games = {};
  for (const [gid, sg] of Object.entries(day.games)) {
    if (sg.home_score==null) continue;
    games[gid] = {state:'FINAL', live:false, final:true, period:null, time_remaining:null, elapsed_min:60, home:sg.home, away:sg.away,
      home_score:sg.home_score, away_score:sg.away_score, first_goal_min:sg.first_goal_min, p1_done:true, p1_home:sg.p1_home, p1_away:sg.p1_away, ended_in:sg.ended_in, goals:[]};
  }
  return Object.keys(games).length ? {date:P.date, updated_et:'final results', games} : null;
}
// On a normal host the page reads the NHL scoreboard itself (direct, then through public CORS relays) every
// 30 seconds, so results resolve as they happen; where page requests are blocked it falls back to live.json.
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
  return {date:P.date, updated_utc: now.toISOString(), updated_et: now.toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',timeZone:'America/Toronto'})+' ET (live)', games, source:'scoreboard'};
}
function fetchScoreboard(){
  const order = directOk ? [0] : [0,1,2,3].slice(relayIdx).concat([0,1,2,3].slice(0,relayIdx));
  const attempt = i => { if (i>=order.length) return Promise.reject('no relay'); const k=order[i];
    const ctrl = new AbortController(); const timer = setTimeout(()=>ctrl.abort(), 6000);
    return fetch(RELAYS[k](NHL_SCORE), {cache:'no-store', signal: ctrl.signal}).then(r=>{ clearTimeout(timer); if(!r.ok) throw r.status; return r.json(); })
      .then(j=>{ if(!j || !j.games) throw 'shape'; if(k===0) directOk=true; else relayIdx=k; return j; }).catch(()=>attempt(i+1)); };
  return attempt(0);
}
let lastLoad = null, loading = false;
function setRefreshState(txt, busy){
  document.querySelectorAll('.rbtn').forEach(b=>{ b.disabled=!!busy; b.textContent = txt; });
  const f = document.getElementById('fab'); if(f) f.classList.toggle('spin', !!busy);
}
function loadLive(){
  if (loading) return Promise.resolve();
  loading = true; setRefreshState('Refreshing…', true);
  const tryUrl = u => fetch(u + '?t=' + Date.now(), {cache:'no-store'}).then(r=>r.ok?r.json():Promise.reject(r.status));
  return fetchScoreboard().then(sb=>{ const L=liveFromScoreboard(sb); if(L){ LIVE=L; renderLiveBar(); render(); return true; } return false; }).catch(()=>false)
    .then(ok=>{ if(ok) return true; return tryUrl('./live.json').catch(()=>tryUrl('../live.json')).then(j=>{ if(j && j.games && j.date===P.date){ LIVE=j; renderLiveBar(); render(); return true; } return false; }).catch(()=>false); })
    .then(ok=>{ if(ok) return; return tryUrl('./scorecard.json').catch(()=>tryUrl('../scorecard.json')).then(sc=>{ const L=liveFromScorecard(sc); if(L){ LIVE=L; renderLiveBar(); render(); } }).catch(()=>{}); })
    .then(()=>{ lastLoad = new Date(); loading=false; setRefreshState('↻ Refresh', false); });
}
// manual refresh: button in the live bar, floating button on phones, and pull-to-refresh at the top of the page
document.getElementById('fab').onclick = ()=>loadLive();
document.addEventListener('click', e=>{ if(e.target.classList && e.target.classList.contains('rbtn')) loadLive(); });
(function(){
  let y0=null, pulled=false; const ptr=document.getElementById('ptr');
  document.addEventListener('touchstart', e=>{ y0 = (window.scrollY<=0) ? e.touches[0].clientY : null; pulled=false; }, {passive:true});
  document.addEventListener('touchmove', e=>{ if(y0==null) return; const dy=e.touches[0].clientY-y0; if(dy>70 && window.scrollY<=0){ pulled=true; ptr.classList.add('show'); } else if(dy<40){ pulled=false; ptr.classList.remove('show'); } }, {passive:true});
  document.addEventListener('touchend', ()=>{ if(pulled){ ptr.textContent='Refreshing…'; loadLive().then(()=>{ ptr.textContent='Updated'; setTimeout(()=>{ptr.classList.remove('show'); ptr.textContent='Release to refresh';}, 900); }); } else ptr.classList.remove('show'); y0=null; pulled=false; }, {passive:true});
})();
// keep it fresh while open: re-read the published results every 2 minutes, and when the app comes back to the foreground
setInterval(()=>{ if(!document.hidden && (LIVE && LIVE.source==='scoreboard')) loadLive(); }, 30000);
setInterval(()=>{ if(!document.hidden && !(LIVE && LIVE.source==='scoreboard')) loadLive(); }, 120000);
document.addEventListener('visibilitychange', ()=>{ if(!document.hidden) loadLive(); });

// ---- table
const cols = [
  {k:'rank', h:'#', u:'U0.5 F5 rank', sticky:false, v:g=>g.rank_u05_first5, r:g=>`<span class="num t">${g.rank_u05_first5}</span>`},
  {k:'matchup', h:'Matchup', u:'away @ home · ET', l:true, sticky:true, v:g=>g.matchup, r:g=>`<span class="mu">${esc(g.matchup)}</span> ${tier(g.tier)}<div class="t">${esc(g.time_et)}</div>${liveChip(g)}`},
  {k:'goalies', h:'Goalies', u:'away / home', l:true, v:g=>g.goalies.home.name, r:g=>['away','home'].map(s=>{const q=g.goalies[s];return `<div class="goalie"><span class="dot ${q.status}"></span>${esc(q.name||'unknown')} <span class="t">${q.sv_shrunk?('.'+String(q.sv_shrunk.toFixed(3)).slice(2)):''} ${esc(q.status)}</span></div>`}).join('')},
  {k:'u5', h:'U0.5 first 5:00', u:'no goal · fair', v:g=>g.markets.u05_first5.p, r:g=>{const m=g.markets.u05_first5;return `<span class="pct num ${cls(m.p,0.70,0.64)}">${pct(m.p)}</span> ${fair(m)}<div class="bar"><i style="width:${(m.p*100).toFixed(1)}%"></i></div>${edge(m)}`}},
  {k:'u10', h:'U0.5 first 10:00', u:'no goal · fair', v:g=>g.markets.u05_first10.p, r:g=>{const m=g.markets.u05_first10;return `<span class="pct num ${cls(m.p,0.47,0.42)}">${pct(m.p)}</span> ${fair(m)}<div class="bar"><i style="width:${(m.p*100).toFixed(1)}%"></i></div>${edge(m)}`}},
  {k:'p1m', h:'1P -0.5', u:'pick · cover', v:g=>g.markets.p1_minus05.p, r:g=>{const m=g.markets.p1_minus05;return `<span class="pick">${esc(m.pick)}</span><span class="num ${cls(m.p,0.42,0.36)}">${pct(m.p)}</span>${mark(g,'p1_minus05')}`}},
  {k:'p1p', h:'1P +0.5', u:'pick · cover', v:g=>g.markets.p1_plus05.p, r:g=>{const m=g.markets.p1_plus05;return `<span class="pick">${esc(m.pick)}</span><span class="num ${cls(m.p,0.66,0.60)}">${pct(m.p)}</span>${mark(g,'p1_plus05')}`}},
  {k:'p1ml', h:'1P ML', u:'H / tie / A', v:g=>g.markets.p1_ml.p, r:g=>{const m=g.markets.p1_ml;return `<span class="pick">${esc(m.pick)}</span><span class="num ${cls(m.p,0.42,0.36)}">${pct(m.p)}</span>${mark(g,'p1_ml')}<div class="t num">${pct(m.home)} / ${pct(m.tie)} / ${pct(m.away)}</div>`}},
  {k:'fgml', h:'FG ML', u:'incl. OT/SO', v:g=>g.markets.fg_ml.p, r:g=>{const m=g.markets.fg_ml;return `<span class="pick">${esc(m.pick)}</span><span class="num ${cls(m.p,0.60,0.54)}">${pct(m.p)}</span>${mark(g,'fg_ml')}`}},
  {k:'fgs', h:'FG spread', u:'-1.5 cover · +1.5', v:g=>g.markets.fg_spread.p, r:g=>{const m=g.markets.fg_spread;return `<span class="pick">${esc(m.pick)} -1.5</span><span class="num ${cls(m.p,0.38,0.32)}">${pct(m.p)}</span>${mark(g,'fg_spread')}<div class="t num">${esc(m.plus_pick)} +1.5 ${pct(m.plus_p)}</div>`}},
  {k:'proj', h:'Projected', u:'home – away · total', v:g=>g.projected.home+g.projected.away, r:g=>`<span class="num">${g.projected.home.toFixed(2)} – ${g.projected.away.toFixed(2)}</span><div class="t num">total ${g.markets.fg_total.mean.toFixed(2)} · O5.5 ${pct(g.markets.fg_total.over55)}${mark(g,'fg_over55')}</div>`},
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
    s+=`<rect x="${x+2}" y="${H-16-h}" width="${bw-4}" height="${h}" fill="#1f6f8f" rx="2"/><rect x="${x+2}" y="${H-16-hh}" width="${bw-4}" height="${hh}" fill="#6fd3ff" rx="2"/><text x="${x+bw/2}" y="${H-4}" font-size="9" fill="#5f7390" text-anchor="middle">${i+1}</text>`;}
  s+=`<text x="${pad-4}" y="12" font-size="9" fill="#5f7390" text-anchor="end">${mx.toFixed(3)}</text><text x="${pad-4}" y="${H-16}" font-size="9" fill="#5f7390" text-anchor="end">0</text><line x1="${pad}" y1="${H-16}" x2="${W-4}" y2="${H-16}" stroke="#1b2a3f"/></svg>`;
  return s;
}
function histSvg(g){
  const h=g.first_goal_hist,W=320,H=90,pad=22,bw=(W-pad-6)/10,mx=Math.max(...h)*1.15||0.1;
  let s=`<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}">`;
  h.forEach((v,i)=>{const hh=(v/mx)*(H-28),x=pad+i*bw;s+=`<rect x="${x+2}" y="${H-16-hh}" width="${bw-4}" height="${hh}" fill="#3ddc84" rx="2" opacity=".85"/><text x="${x+bw/2}" y="${H-4}" font-size="9" fill="#5f7390" text-anchor="middle">${i+1}</text>`;});
  s+=`<text x="${pad-4}" y="12" font-size="9" fill="#5f7390" text-anchor="end">${(mx*100).toFixed(0)}%</text><line x1="${pad}" y1="${H-16}" x2="${W-4}" y2="${H-16}" stroke="#1b2a3f"/></svg>`;
  return s;
}
function lbl(x){return `<span class="lbl ${x.label}">${x.label}</span>`}
function goalieBox(g, side){
  const q=g.goalies[side];
  const f=v=>v==null?'n/a':('.'+String(v.toFixed(3)).slice(2));
  return `<table><tr><td>starter</td><td><span class="dot ${q.status}"></span>${esc(q.name||'unknown')} <span class="t">${esc(q.status)} · ${esc(q.source)}</span></td></tr>
  <tr><td>sv% raw / shrunk</td><td class="num">${f(q.sv_raw)} / ${f(q.sv_shrunk)}</td></tr>
  <tr><td>last 5 starts sv%</td><td class="num">${f(q.sv_last5)}</td></tr>
  <tr><td>first-10-min sv% raw</td><td class="num">${f(q.e10_sv_raw)}</td></tr>
  <tr><td>starts this season / shots in sample</td><td class="num">${q.starts_cur??'n/a'} / ${q.shots_weighted}</td></tr></table>${q.note?`<div class="small gap">${esc(q.note)}</div>`:''}`;
}
function restBox(side){
  const r=side.rest||{};
  if(!r||r.days_rest===undefined)return '<div class="small">schedule context missing</div>';
  const ctx=Object.entries(side.context_detail||{});
  return `<table><tr><td>days rest</td><td class="num">${r.days_rest==null?'first game':r.days_rest}${r.b2b?' <span class="lbl partial">B2B</span>':''}${r.three_in_four?' <span class="lbl partial">3-in-4</span>':''}</td></tr>
  <tr><td>travel since last game</td><td class="num">${(r.travel_km||0).toFixed(0)} km · ${r.tz_shift||0} tz</td></tr>
  <tr><td>games last 7 days</td><td class="num">${r.games_last_7d??'n/a'}</td></tr>
  <tr><td>previous</td><td>${r.prev_opponent?esc(r.prev_opponent)+' · '+esc(r.prev_date):'n/a'}</td></tr>
  ${ctx.map(([k,v])=>`<tr><td>${esc(k)}</td><td class="num">× ${v.toFixed(3)}</td></tr>`).join('')}</table>`;
}
function profBox(side){
  const p=side.profile||{};
  if(!p.games_cur && !p.games_prior) return '<div class="small">no profile data</div>';
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
  <tr><td>this season: scored / allowed in first 5</td><td class="num">${p.cur_scored_first5_share==null?'n/a':pct(p.cur_scored_first5_share)} / ${p.cur_allowed_first5_share==null?'n/a':pct(p.cur_allowed_first5_share)}</td></tr>
  </table>${lg?`<div class="small gap">${lg}</div>`:''}`;
}
function details(g){
  const H=g.sides.home, A=g.sides.away;
  const lh=H.lambda_first_10_per_min, la=A.lambda_first_10_per_min;
  const s5=lh.slice(0,5).reduce((a,b)=>a+b,0)+la.slice(0,5).reduce((a,b)=>a+b,0);
  const s10=lh.reduce((a,b)=>a+b,0)+la.reduce((a,b)=>a+b,0);
  const ar=`λ(home) first 5 min  = ${lh.slice(0,5).map(x=>x.toFixed(4)).join(' + ')} = ${lh.slice(0,5).reduce((a,b)=>a+b,0).toFixed(4)}
λ(away) first 5 min  = ${la.slice(0,5).map(x=>x.toFixed(4)).join(' + ')} = ${la.slice(0,5).reduce((a,b)=>a+b,0).toFixed(4)}
P(no goal, first 5)  = exp(-${s5.toFixed(4)}) = ${Math.exp(-s5).toFixed(4)}   analytic ${g.analytic.u05_first5.toFixed(4)} · simulated ${g.markets.u05_first5.p.toFixed(4)} ± ${(g.mc_se.first5*2).toFixed(4)} (95% MC)
P(no goal, first 10) = exp(-${s10.toFixed(4)}) = ${Math.exp(-s10).toFixed(4)}   analytic ${g.analytic.u05_first10.toFixed(4)} · simulated ${g.markets.u05_first10.p.toFixed(4)} ± ${(g.mc_se.first10*2).toFixed(4)} (95% MC)`;
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
    <div class="small gap">1P total distribution 0 / 1 / 2 / 3+: <span class="num">${g.p1.total_dist.map(pct).join(' / ')}</span> · mean ${g.p1.mean_total.toFixed(2)} · FG O6.5 ${pct(g.markets.fg_total.over65)} · regulation ${esc(g.home)} ${pct(g.markets.fg_ml.home_reg)} / tie ${pct(g.markets.fg_ml.reg_tie)} / ${esc(g.away)} ${pct(g.markets.fg_ml.away_reg)}</div>
  </div></div>`;
}
function render(){
  const col=cols.find(c=>c.k===sortKey);
  let rows=P.games.filter(g=>tierFilter==='ALL'||g.tier===tierFilter);
  rows.sort((a,b)=>{const x=col.v(a),y=col.v(b);return (x>y?1:x<y?-1:0)*sortDir;});
  tbody.innerHTML=rows.map(g=>`<tr class="g" data-id="${g.game_id}">${cols.map(c=>`<td class="${c.l?'l':''} ${c.sticky?'sticky':''}">${c.r(g)}</td>`).join('')}</tr>`+(open.has(g.game_id)?`<tr class="d"><td colspan="${cols.length}"><div class="detwrap">${details(g)}</div></td></tr>`:'')).join('');
  tbody.querySelectorAll('tr.g').forEach(tr=>tr.onclick=()=>{const id=+tr.dataset.id;open.has(id)?open.delete(id):open.add(id);render();});
  renderCards(rows);
  if (LIVE) renderTopCards();
}
function card(g){
  const m=g.markets, u5=Object.assign({},m.u05_first5), u10=Object.assign({},m.u05_first10);
  if(u5.edge==null&&userPrice5){u5.book=userPrice5;u5.edge=u5.p*userPrice5-1;}
  if(u10.edge==null&&userPrice10){u10.book=userPrice10;u10.edge=u10.p*userPrice10-1;}
  const gl=['away','home'].map(s=>{const q=g.goalies[s];return `<span><span class="dot ${q.status}"></span>${esc(q.name||'unknown')} <span class="t">${q.sv_shrunk?('.'+String(q.sv_shrunk.toFixed(3)).slice(2)):''} ${esc(q.status)}</span></span>`}).join('');
  return `<div class="gc" data-id="${g.game_id}">
    <div class="hd"><span><span class="mu">${esc(g.matchup)}</span> ${tier(g.tier)}</span><span class="t">#${g.rank_u05_first5} · ${esc(g.time_et)}</span></div>
    ${liveChip(g)?`<div>${liveChip(g)}</div>`:''}
    <div class="gl">${gl}</div>
    <div class="mk">
      <div class="big"><span><span class="k">Under 0.5 · first 5:00</span><span class="v num ${cls(u5.p,0.70,0.64)}">${pct(u5.p)}</span>${mark(g,'u05_first5')}</span><span style="text-align:right"><span class="s">fair ${u5.fair?u5.fair.toFixed(2):'n/a'}</span>${edge(u5)}</span></div>
      <div><span class="k">U0.5 first 10</span><span class="v num ${cls(u10.p,0.47,0.42)}">${pct(u10.p)}${mark(g,'u05_first10')}</span><span class="s">fair ${u10.fair?u10.fair.toFixed(2):'n/a'} ${u10.edge!=null?((u10.edge>=0?'+':'')+(u10.edge*100).toFixed(1)+'%'):''}</span></div>
      <div><span class="k">1P −0.5</span><span class="v"><span class="pick">${esc(m.p1_minus05.pick)}</span><span class="num">${pct(m.p1_minus05.p)}</span>${mark(g,'p1_minus05')}</span></div>
      <div><span class="k">1P +0.5</span><span class="v"><span class="pick">${esc(m.p1_plus05.pick)}</span><span class="num">${pct(m.p1_plus05.p)}</span>${mark(g,'p1_plus05')}</span></div>
      <div><span class="k">1P ML</span><span class="v"><span class="pick">${esc(m.p1_ml.pick)}</span><span class="num">${pct(m.p1_ml.p)}</span>${mark(g,'p1_ml')}</span><span class="s num">tie ${pct(m.p1_ml.tie)}</span></div>
      <div><span class="k">FG ML</span><span class="v"><span class="pick">${esc(m.fg_ml.pick)}</span><span class="num">${pct(m.fg_ml.p)}</span>${mark(g,'fg_ml')}</span></div>
      <div><span class="k">FG −1.5</span><span class="v"><span class="pick">${esc(m.fg_spread.pick)}</span><span class="num">${pct(m.fg_spread.p)}</span>${mark(g,'fg_spread')}</span><span class="s num">${esc(m.fg_spread.plus_pick)} +1.5 ${pct(m.fg_spread.plus_p)}</span></div>
      <div class="big" style="grid-column:span 3;justify-content:flex-start;gap:14px"><span><span class="k">Projected</span><span class="v num" style="font-size:15px">${g.projected.home.toFixed(2)} – ${g.projected.away.toFixed(2)}</span></span><span class="s num">total ${m.fg_total.mean.toFixed(2)} · O5.5 ${pct(m.fg_total.over55)}${mark(g,'fg_over55')} · O6.5 ${pct(m.fg_total.over65)}</span></div>
    </div>
    ${open.has(g.game_id)?`<div class="dt">${details(g)}</div>`:''}
  </div>`;
}
function renderCards(rows){
  const c=document.getElementById('cards');
  c.innerHTML=rows.map(card).join('');
  c.querySelectorAll('.gc').forEach(el=>{el.onclick=(ev)=>{if(ev.target.closest('.dt'))return;const id=+el.dataset.id;open.has(id)?open.delete(id):open.add(id);render();};});
}
const tb=document.getElementById('toolbar');
tb.innerHTML=`<span class="sorthint">sort by clicking a column · tap a game for inputs &amp; arithmetic · filter:</span>`+`<select id="sortsel"><option value="rank">sort: U0.5 first 5</option><option value="u10">sort: U0.5 first 10</option><option value="p1m">sort: 1P −0.5</option><option value="p1p">sort: 1P +0.5</option><option value="fgml">sort: FG ML</option><option value="fgs">sort: FG −1.5</option><option value="proj">sort: projected total</option><option value="matchup">sort: start time</option></select>`+['ALL','A','B','C'].map(t=>`<button data-t="${t}" class="${t==='ALL'?'on':''}">${t==='ALL'?'all tiers':'tier '+t}</button>`).join('')+`<button id="expand">expand all</button>`;
tb.querySelectorAll('button[data-t]').forEach(b=>b.onclick=()=>{tierFilter=b.dataset.t;tb.querySelectorAll('button[data-t]').forEach(x=>x.classList.toggle('on',x===b));render();});
document.getElementById('expand').onclick=()=>{if(open.size===P.games.length)open.clear();else P.games.forEach(g=>open.add(g.game_id));render();};
document.getElementById('sortsel').onchange=(e)=>{sortKey=e.target.value;sortDir=(sortKey==='rank'||sortKey==='matchup')?1:-1;if(sortKey==='matchup'){sortKey='matchup';}render();};
let userPrice5 = null, userPrice10 = null;
try{ userPrice5 = parseFloat(localStorage.getItem('egd_price5'))||null; userPrice10 = parseFloat(localStorage.getItem('egd_price10'))||null; }catch(e){}
function priceVerdict(price, pRange, lg){
  if(!price||price<=1) return '';
  const be = 1/price;
  const evLo = pRange[0]*price-1, evHi = pRange[1]*price-1;
  const cls = evHi<0?'neg':(evLo>0?'pos':'');
  return `<span class="verdict ${cls}">break-even ${pct(be)} · EV ${(evLo*100).toFixed(1)}% to ${(evHi*100).toFixed(1)}% per unit</span>`;
}
function renderPriceBar(){
  const ps10 = P.games.map(g=>g.markets.u05_first10.p);
  document.getElementById('pricebar').innerHTML = `<span>Price check (your book):</span>
    <label>U0.5 first 5:00 <input id="price5" type="number" step="0.01" min="1.01" placeholder="1.30" value="${userPrice5||''}"></label>${priceVerdict(userPrice5,[lo5,hi5])}
    <label>U0.5 first 10:00 <input id="price10" type="number" step="0.01" min="1.01" placeholder="1.90" value="${userPrice10||''}"></label>${priceVerdict(userPrice10,[Math.min(...ps10),Math.max(...ps10)])}
    <span class="small">EV = model probability × price − 1. The slate range is the model's spread; the backtest says that spread carries no ranking edge, so read the EV as a verdict on the price, not on the game.</span>`;
  const bind=(id,setter,key)=>{const el=document.getElementById(id);el.onchange=el.onkeyup=()=>{const v=parseFloat(el.value);setter(v>1?v:null);try{localStorage.setItem(key,v>1?String(v):'');}catch(e){}renderPriceBar();render();document.getElementById(id).focus();};};
  bind('price5',v=>userPrice5=v,'egd_price5'); bind('price10',v=>userPrice10=v,'egd_price10');
}
// inject the user's price into the edge display when no odds file was supplied
const origEdge = edge;
cols.find(c=>c.k==='u5').r = g=>{const m=Object.assign({},g.markets.u05_first5); if(m.edge==null&&userPrice5){m.book=userPrice5;m.edge=m.p*userPrice5-1;} return `<span class="pct num ${cls(m.p,0.70,0.64)}">${pct(m.p)}</span> ${fair(m)}${mark(g,'u05_first5')}<div class="bar"><i style="width:${(m.p*100).toFixed(1)}%"></i></div>${origEdge(m)}`};
cols.find(c=>c.k==='u10').r = g=>{const m=Object.assign({},g.markets.u05_first10); if(m.edge==null&&userPrice10){m.book=userPrice10;m.edge=m.p*userPrice10-1;} return `<span class="pct num ${cls(m.p,0.47,0.42)}">${pct(m.p)}</span> ${fair(m)}${mark(g,'u05_first10')}<div class="bar"><i style="width:${(m.p*100).toFixed(1)}%"></i></div>${origEdge(m)}`};
renderPriceBar();
renderTopCards();
render();
loadLive();

const V = M.validation;
if (V && V.first5) {
  const rowsV = [
    ['Under 0.5, first 5:00', V.first5.logloss_model, V.first5.logloss_baseline, V.first5.top_quintile_actual, V.first5.bottom_quintile_actual, V.first5.mean_pred, V.first5.actual_rate],
    ['Under 0.5, first 10:00', V.first10.logloss_model, V.first10.logloss_baseline, V.first10.top_quintile_actual, V.first10.bottom_quintile_actual, V.first10.mean_pred, V.first10.actual_rate],
  ];
  const jm = {fg_ml_home:'FG moneyline (home)', fg_home_minus15:'FG home −1.5', fg_away_minus15:'FG away −1.5', fg_over55:'FG over 5.5', p1_home_win:'1P home win', p1_away_win:'1P away win', p1_tie:'1P tie'};
  for (const [k,label] of Object.entries(jm)) if (V[k]) rowsV.push([label, V[k].logloss_model, V[k].logloss_constant, V[k].top_quintile_actual, V[k].bottom_quintile_actual, V[k].mean_pred, V[k].actual]);
  document.getElementById('validation').innerHTML = `<div class="valid"><h3>Validation · walk-forward on the ${V.season?String(V.season).slice(0,4)+'-'+String(V.season).slice(6):''} season, ${V.n} real games, actual starters</h3>
  <p>Each game was predicted using only games played before it. Log loss below the league constant means the ranking carries information; top vs bottom quintile shows how much the ranking separates outcomes in reality.</p>
  <div class="tbl"><table><thead><tr><th>market</th><th>log loss model</th><th>league constant</th><th>verdict</th><th>top quintile hit</th><th>bottom quintile hit</th><th>mean pred</th><th>actual</th></tr></thead><tbody>
  ${rowsV.map(r=>`<tr><td>${r[0]}</td><td class="num">${r[1].toFixed(4)}</td><td class="num">${r[2].toFixed(4)}</td><td class="${r[1]<r[2]?'ok':'no'}">${r[1]<r[2]?'beats constant':'no edge'}</td><td class="num">${pct(r[3])}</td><td class="num">${pct(r[4])}</td><td class="num">${pct(r[5])}</td><td class="num">${pct(r[6])}</td></tr>`).join('')}
  </tbody></table></div>
  <p>Read this before betting the early markets: the first-5 and first-10 probabilities are calibrated (they land where they say they land), but no pre-game input separated games that produced an early goal from games that did not. Fair price is the useful output; a book price below the fair price is a losing bet in the long run regardless of which game is picked.</p></div>`;
}

const SC = M.scorecard;
if (SC && SC.games_scored) {
  const names = {u05_first5:'Under 0.5, first 5:00', u05_first10:'Under 0.5, first 10:00', p1_minus05:'1P −0.5 pick', p1_plus05:'1P +0.5 pick', p1_ml:'1P ML pick', fg_ml:'FG ML pick', fg_spread:'FG −1.5 pick', fg_over55:'FG over 5.5'};
  const rows = Object.entries(SC.markets||{}).map(([k,v])=>`<tr><td>${names[k]||k}</td><td class="num">${v.n}</td><td class="num">${pct(v.hit_rate)}</td><td class="num">${pct(v.mean_pred)}</td><td class="num">${v.brier.toFixed(4)}</td></tr>`).join('');
  const top = Object.entries(SC.top3||{}).map(([k,v])=>`<tr><td>Top 3 · ${names[k]||k}</td><td class="num">${v.n}</td><td class="num">${pct(v.hit_rate)}</td><td class="num">${pct(v.mean_pred)}</td><td></td></tr>`).join('');
  const potd = SC.pick_of_day && SC.pick_of_day.n ? `<tr><td>Highest-probability first-5 pick</td><td class="num">${SC.pick_of_day.n}</td><td class="num">${pct(SC.pick_of_day.hit_rate)}</td><td class="num">${pct(SC.pick_of_day.mean_pred)}</td><td></td></tr>` : '';
  const v = document.getElementById('validation');
  v.innerHTML = `<div class="valid"><h3>Track record · ${SC.games_scored} games over ${SC.days_scored} published days, scored on the numbers that were on the page</h3>
  <p>Hit rate is what happened; predicted is what the page said. Over enough games the two should sit close together. Brier is lower when the probabilities are sharper and still honest.</p>
  <div class="tbl"><table><thead><tr><th>market</th><th>n</th><th>hit rate</th><th>predicted</th><th>brier</th></tr></thead><tbody>${rows}${top}${potd}</tbody></table></div></div>` + v.innerHTML;
}

document.getElementById('foot').innerHTML=`
<h5>How the numbers are made</h5>
Every team's goal rate per minute is a chain of multiplicative factors on the league hazard curve for that minute of the game: home ice, the team's shot rate for and the opponent's shot rate against (first-10-minute profile blended with the full-game profile), finishing talent (shrunk hard toward league shooting%), the opposing starting goalie's save% (shrunk in shots), and rest / back-to-back / travel / time-zone effects measured from the schedule. Under 0.5 in the first 5:00 is exp(−Σλ) over those minutes; the Monte Carlo (${P.games[0]?P.games[0].sims.toLocaleString():''} paths per game) reproduces it and adds the joint markets: period winner, full-game result with 3-on-3 OT and shootout, −1.5 / +1.5 with empty-net dynamics, score distribution.
<h5>Tiers</h5>
<b>A</b>: both team profiles measured on this season's data and both starting goalies confirmed. <b>B</b>: a goalie is only expected/projected, or a profile leans on last season. <b>C</b>: an input is unmeasured. Top-3 cards only draw from A and B.
<h5>What the model cannot see</h5>
Line deployment, referee tendencies, late scratches and injuries (unless entered in overrides.json), and anything that happens after the puck drops. Book prices never enter the ranking; if an odds file is supplied they are shown after the fact as fair price vs book and edge.
<h5>Precision</h5>
Simulation error at ${P.games[0]?P.games[0].sims.toLocaleString():''} paths is about ±0.3 percentage points. Model error is larger: on real seasons the first-5 probability lands within about 1.5 points of the stated figure on average, and the ranking between games is within that noise. Judge the engine on the validation table, not on the number of simulations.`;
</script>
</body>
</html>
"""


def render(payload: dict) -> str:
    return TEMPLATE.replace("__PAYLOAD__", json.dumps(payload).replace("</", "<\\/"))


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
