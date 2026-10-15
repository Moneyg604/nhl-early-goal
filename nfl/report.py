"""NFL week page: one self-contained HTML file in the same design system as the NHL slate.

Tabs: Week (every game with all nine markets, live scores), Research (dossiers and measured factors),
Picks (leans per market and a slip builder), Results (graded leans, track record), About (method and the
walk-forward validation). The page prices any line from the stored distributions, so the price check
works for the exact line and odds the book shows.
"""
from __future__ import annotations

import json

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
"""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Early Goal Desk</title>
<meta name="description" content="NFL week __WEEK__: moneyline, spread, totals, half totals, team field goals, quarterback passing and anytime touchdown probabilities from a drive-level simulation">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>__CSS__</style>
</head>
<body>
<button id="fab" title="Refresh live scores" aria-label="Refresh live scores">↻</button>
<div class="app"><div class="wrap">
  <div class="row">
    <div class="brand"><span class="bt">Early <span>Goal</span> Desk</span><nav class="sport" aria-label="sport"><a href="__NHL_HREF__">NHL</a><a class="on" href="#">NFL</a></nav></div>
    <div class="hmeta"><span id="dayslot"></span></div>
  </div>
  <nav class="tabs" id="tabs">
    <button data-tab="week" class="on">Week</button>
    <button data-tab="research">Research</button>
    <button data-tab="picks">Picks</button>
    <button data-tab="results">Results</button>
    <button data-tab="about">About</button>
  </nav>
</div></div>

<div class="wrap">
<div id="banner"></div>
__STATIC__

<section class="tab on" id="tab-week">
  <div class="status" id="status"></div>
  <div class="livebar" id="livebar"></div>
  <div class="board" id="board"></div>
  <div class="panel" id="pricecheck"></div>
  <div class="toolbar" id="toolbar"></div>
  <div class="ncards" id="cards"></div>
</section>

<section class="tab" id="tab-research">
  <p class="lead">What was measured before the numbers were produced: each team's drive results against what the league scores from the same situations, pace, passing, kicking, the quarterback, the injury report and the context of the game. Sample sizes are shown; every multiplier is shrunk toward the league in proportion to how little data stands behind it.</p>
  <div class="panel" id="factors"></div>
  <h2>Game dossiers</h2>
  <div id="dossiers"></div>
</section>

<section class="tab" id="tab-picks">
  <p class="lead">The strongest leans in each market, ranked. Each group carries the walk-forward verdict for that market: only trust a lean where the backtest found the model beats its baseline. Tap legs to build a slip.</p>
  <div class="panel" id="slip"></div>
  <div class="groups" id="picks"></div>
</section>

<section class="tab" id="tab-results">
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
const VK = {ml:'moneyline', spread:'spread', total:'total', h1:'h1_total', h2:'h2_total', fg:'fg_over1.5', qb_yds:'qb_yards', qb_td:'qb_td_over1.5', atd:'anytime_td'};
const verdTag = key => { const v=verdictOf(VK[key]||key); if(!v) return '<span class="verd marginal">not yet validated</span>'; return `<span class="verd ${v==='beats baseline'?'beats':(v==='marginal'?'marginal':'none')}">${esc(v)}</span>`; };
document.getElementById('status').innerHTML = [
  `<b>${P.season} · week ${P.week}</b>`, `<b>${P.games.length}</b> games`,
  `data through <b>${esc(M.data_through||'n/a')}</b>`, `updated <b>${esc(P.generated_utc)}</b>`, `${(M.sims||0).toLocaleString()} sims per game`].map(x=>`<span>${x}</span>`).join('');
(function(){ const b=[]; if(V && V.pooled){ const gl=['moneyline','spread','total'].map(k=>V.pooled[k]).filter(Boolean);
    const none = gl.every(x=>x.verdict!=='beats baseline');
    if(none) b.push(`<div class="banner"><b>Game lines follow the market.</b> In the walk-forward test the model alone did not beat the closing moneyline, spread or total, so the moneyline, spread and total probabilities below are the market's line re-simulated (with ${M.blend && (M.blend.margin||M.blend.total) ? 'a small measured share of the model\'s disagreement' : 'none of the model\'s disagreement'} kept). The model's own lean is shown next to it for reference. The derived markets (halves, field goals, passing, scorers) carry the team-specific information; their verdicts are on each pick group.</div>`); }
  else b.push(`<div class="banner"><b>Validation pending.</b> The walk-forward backtest has not been published yet; treat every number as unvalidated.</div>`);
  document.getElementById('banner').innerHTML = b.join(''); })();
const tabs=document.getElementById('tabs');
function showTab(name, push){ document.querySelectorAll('section.tab').forEach(s=>s.classList.toggle('on', s.id==='tab-'+name));
  tabs.querySelectorAll('button').forEach(b=>b.classList.toggle('on', b.dataset.tab===name)); try{localStorage.setItem('egd_nfl_tab',name);}catch(e){}
  if(push && history.replaceState) history.replaceState(null,'','#'+name); window.scrollTo({top:0}); }
tabs.querySelectorAll('button').forEach(b=>b.onclick=()=>showTab(b.dataset.tab,true));
function tabFromHash(){ const h=(location.hash||'').replace('#',''); if(['week','research','picks','results','about'].includes(h)) showTab(h,false); }
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
  const row = side => { const p=m[side]; const odds=L[side+'_ml']!=null ? (L[side+'_ml']>0?1+L[side+'_ml']/100:1+100/(-L[side+'_ml'])) : null;
    const ev = odds ? p/(1-m.tie)*odds - 1 : null; const r=o?o['ml_'+side]:null;
    return `<div class="row"><span>${g[side]} ${markTxt(r)}</span><span class="p ${side===fav?'hi':''}">${pct(p)}</span></div><span class="s">fair ${fmtOdds(fair(p/(1-m.tie)))}${odds?` · book ${amer(L[side+'_ml'])}${ev!=null?` <span class="edge ${ev>=0?'pos':'neg'}">${ev>=0?'+':''}${(ev*100).toFixed(1)}%</span>`:''}`:''}</span>`; };
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
const PK_LABEL = {ml:'Moneyline', spread:'Spread', total:'Total', h1:'1st half total', h2:'2nd half total', fg:'Team FGs 1.5', qb_yds:'QB pass yards', qb_td:'QB pass TDs 1.5', atd:'Anytime TD'};
function pickText(k, x){ if(k==='ml') return `${x.team} ML`; if(k==='spread'){ const hl=-x.line; return x.side==='home'?`${byId[x.game_id].home} ${hl>0?'+':''}${hl}`:`${byId[x.game_id].away} ${x.line>0?'+':''}${x.line}`; }
  if(k==='total'||k==='h1'||k==='h2') return `${x.side==='over'?'Over':'Under'} ${x.line}`; if(k==='fg') return `${x.team} ${x.side} ${x.line} FGs`;
  if(k==='qb_yds') return `${x.qb} ${x.side} ${x.line} yds`; if(k==='qb_td') return `${x.qb} ${x.side} ${x.line} TDs`; if(k==='atd') return `${x.player} (${x.team})`; return ''; }
function renderBoard(){ const keys=['ml','spread','total','h1','h2','fg','qb_yds','qb_td','atd'];
  document.getElementById('board').innerHTML = keys.filter(k=>(P.picks[k]||[]).length).map(k=>{ const x=P.picks[k][0];
    const v=verdictOf(VK[k]); const vi = v==='beats baseline'?'✓ validated':(v==='marginal'?'~ marginal':(v?'no edge':'unvalidated'));
    return `<a href="#g-${x.game_id}" onclick="SLOT='all';renderToolbar();renderCards();setTimeout(()=>{const e=document.getElementById('g-${x.game_id}'); if(e) e.scrollIntoView({behavior:'smooth'});},20);return false;"><span class="k">${PK_LABEL[k]}</span><span class="mu">${esc(pickText(k,x))}</span><span class="v" style="${v==='beats baseline'?'':'color:var(--text)'}">${pct(x.p)}</span><span class="s">${esc(x.mu)} · ${vi}</span></a>`; }).join(''); }

// ------------------------------------------------------------- price check
const PC_MARKETS = [['ml_home','Moneyline: home'],['ml_away','Moneyline: away'],['sp_home','Spread: home'],['sp_away','Spread: away'],['over','Total: over'],['under','Total: under'],
  ['h1_over','1st half: over'],['h1_under','1st half: under'],['h2_over','2nd half: over'],['h2_under','2nd half: under'],['fg_home_over','Home FGs: over'],['fg_home_under','Home FGs: under'],
  ['fg_away_over','Away FGs: over'],['fg_away_under','Away FGs: under'],['qy_home_over','Home QB yards: over'],['qy_home_under','Home QB yards: under'],['qy_away_over','Away QB yards: over'],['qy_away_under','Away QB yards: under'],
  ['qt_home_over','Home QB TDs: over'],['qt_home_under','Home QB TDs: under'],['qt_away_over','Away QB TDs: over'],['qt_away_under','Away QB TDs: under'],['atd','Anytime TD']];
function defaultLine(g, mk){ const L=g.lines||{};
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
  if(mk==='atd'){ const a=[...(g.anytime.home||[]),...(g.anytime.away||[])].find(x=>x.id===player); return a?{p:a.p,push:0}:null; } return null; }
function renderPC(){ const el=document.getElementById('pricecheck'); const gs=[...P.games].sort((a,b)=>(a.kickoff_utc||'').localeCompare(b.kickoff_utc||''));
  let st={}; try{ st=JSON.parse(localStorage.getItem('egd_nfl_pc')||'{}'); }catch(e){}
  el.innerHTML = `<h3>Price check <span class="mini" style="text-transform:none;letter-spacing:0">enter the book's line and odds; any line works, pushes included</span></h3>
  <div class="pc"><label>Game<select id="pc-g">${gs.map(g=>`<option value="${g.game_id}">${g.away} @ ${g.home}</option>`).join('')}</select></label>
  <label>Market<select id="pc-m">${PC_MARKETS.map(([k,l])=>`<option value="${k}">${l}</option>`).join('')}</select></label>
  <label id="pc-pl" style="display:none">Player<select id="pc-p"></select></label>
  <label id="pc-ll">Line<input id="pc-l" inputmode="decimal"></label>
  <label>Book odds<input id="pc-o" placeholder="1.91 or -110" inputmode="text"></label></div><div class="pcout" id="pc-out"></div>`;
  const G=document.getElementById('pc-g'), Mk=document.getElementById('pc-m'), Ln=document.getElementById('pc-l'), Od=document.getElementById('pc-o'), Pl=document.getElementById('pc-p');
  if(st.g && byId[st.g]) G.value=st.g; if(st.m) Mk.value=st.m;
  const syncPlayers = () => { const g=byId[G.value]; const a=[...(g.anytime.away||[]).map(x=>[x,g.away]),...(g.anytime.home||[]).map(x=>[x,g.home])];
    Pl.innerHTML = a.map(([x,t])=>`<option value="${x.id}">${esc(x.name)} (${t})</option>`).join(''); };
  const syncLine = (keep) => { const g=byId[G.value]; const atd = Mk.value==='atd'; document.getElementById('pc-pl').style.display = atd?'':'none'; document.getElementById('pc-ll').style.display = atd||Mk.value.startsWith('ml')?'none':'';
    if(!keep) Ln.value = defaultLine(g, Mk.value); if(atd) syncPlayers(); };
  const calc = () => { const g=byId[G.value]; const line=parseFloat(Ln.value); const r=pcProb(g, Mk.value, isNaN(line)?0:line, Pl.value); const out=document.getElementById('pc-out');
    try{ localStorage.setItem('egd_nfl_pc', JSON.stringify({g:G.value, m:Mk.value})); }catch(e){}
    if(!r){ out.innerHTML=''; return; } const d=parseOdds(Od.value); const pw=r.p, push=r.push||0; const fo = pw>0 ? (1-push)/pw : null;
    const ev = d ? pw*(d-1) - (1-pw-push) : null; const kelly = d && ev>0 ? ev/(d-1) : null;
    out.innerHTML = `<div><span class="k">Win</span><span class="v">${pct(pw)}</span></div>${push>0.001?`<div><span class="k">Push</span><span class="v">${pct(push)}</span></div>`:''}
      <div><span class="k">Fair odds</span><span class="v">${fo?fo.toFixed(2):'–'}</span><span class="t">${fo?dec2am(fo):''}</span></div>
      ${d?`<div><span class="k">EV per $10</span><span class="v ${ev>=0?'hi':''}" style="color:${ev>=0?'var(--green)':'var(--red)'}">${ev>=0?'+':''}$${(ev*10).toFixed(2)}</span></div><div><span class="k">Kelly</span><span class="v">${kelly?(kelly*100).toFixed(1)+'%':'no bet'}</span></div>`:''}`; };
  G.onchange=()=>{ syncLine(false); calc(); }; Mk.onchange=()=>{ syncLine(false); calc(); }; Ln.oninput=calc; Od.oninput=calc; Pl.onchange=calc; syncLine(false); calc(); }

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
function renderResearch(){ const L=M.league||{}; const ctx=L.context||{}; const H=L.home||{};
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
    <div class="dgrid"><div class="box"><h4>Teams</h4><table><tr><th></th><th>${g.away}</th><th>${g.home}</th></tr>${teamRows(a,h)}</table></div>
    <div class="box"><h4>Head to head (last meetings)</h4>${(r.h2h||[]).length?`<table><tr><th>date</th><th>score</th><th>1H</th><th>line</th></tr>${r.h2h.map(x=>`<tr><td>${x.date}</td><td>${x.away} ${x.as} @ ${x.home} ${x.hs}</td><td>${x.h1}</td><td>${spreadTxt(x.home,x.away,x.spread)} / ${x.total!=null?x.total:''}</td></tr>`).join('')}</table>`:'<p class="small">no meetings in the data window</p>'}
    <h4 style="margin-top:10px">Kickers</h4>${['away','home'].map(s=>{ const k=g.kicker[s]||{}; const p=k.profile; return `<p class="small"><b>${g[s]}</b> ${esc(k.name||k.id||'?')}: ${p?`${p.made}/${p.att} this season · make odds x${p.or} vs expected for his distances · 50+: ${p.long_50plus} · XP ${pct(p.xp_rate)}`:'no record'}</p>`; }).join('')}</div>
    <div class="box"><h4>${g.away} quarterback</h4>${qbRows(g.qb.away)}</div><div class="box"><h4>${g.home} quarterback</h4>${qbRows(g.qb.home)}</div>
    <div class="box"><h4>${g.away} injury report</h4>${injList((g.injuries||{}).away)}</div><div class="box"><h4>${g.home} injury report</h4>${injList((g.injuries||{}).home)}</div></div>
    <h4 style="margin:12px 0 6px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)">Inputs to the simulation</h4>${inputsTable(g)}
    <h4 style="margin:12px 0 6px;font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)">Touchdown shares</h4>
    <div class="dgrid">${['away','home'].map(s=>`<div class="box"><table><tr><th>${g[s]}</th><th>targets</th><th>carries</th><th>red zone</th><th>TD games</th></tr>${((g.anytime||{})[s]||[]).map(x=>`<tr><td>${esc(x.name)} <span class="t">${esc(x.pos||'')}</span></td><td>${pct(x.tgt_share,0)}</td><td>${pct(x.car_share,0)}</td><td>${pct(x.rz_share,0)}</td><td>${x.td_games}/${x.games}</td></tr>`).join('')}</table></div>`).join('')}</div>
    </div></details>`; }).join(''); }

// ------------------------------------------------------------- picks + slip
let SLIP=[]; try{ SLIP=JSON.parse(localStorage.getItem('egd_nfl_slip_'+P.season+'_'+P.week)||'[]'); }catch(e){}
const legId = (k,x) => k+'|'+x.game_id+'|'+(x.side||'')+'|'+(x.id||x.qb||x.team||'');
function pickResult(k, x){ const g=byId[x.game_id]; const o=outc(g); if(!o) return null;
  if(k==='ml') return o['ml_'+x.side]; if(k==='spread') return o['sp_'+x.side]; if(k==='total') return x.side==='over'?o.over:o.under;
  if(k==='h1') return o.h1!=null ? ouRes(o.h1, x.line, x.side, true) : 'pending'; if(k==='h2') return o.h2!=null ? ouRes(o.h2, x.line, x.side, true) : 'pending';
  if(k==='fg') return o.fg ? ouRes(o.fg[x.side_team], x.line, x.side, o.final) : 'pending';
  if(k==='qb_yds'||k==='qb_td'){ const q=o.qb[x.side_team]; if(!q) return 'pending'; return ouRes(k==='qb_yds'?q.yds:q.td, x.line, x.side, o.final && o.propsFinal); }
  if(k==='atd') return scored(o, {id:x.id, name:x.player}); return null; }
function renderPicks(){ const keys=['ml','spread','total','h1','h2','fg','qb_yds','qb_td','atd'];
  const why = {ml:'Highest win probability (market-anchored).', spread:'Largest gap between the model alone and the closing spread.', total:'Largest gap between the model alone and the total.',
    h1:'Farthest from 50% at the usual first-half line (total x league first-half share).', h2:'Same for the second half, overtime included.', fg:'Farthest from 50% at 1.5 field goals made.',
    qb_yds:'Farthest from 50% at a line set at the quarterback\'s recent average.', qb_td:'Farthest from 50% at 1.5 touchdown passes.', atd:'Highest anytime touchdown probability.'};
  document.getElementById('picks').innerHTML = keys.map(k=>{ const L=P.picks[k]||[]; return `<div class="pk"><h3>${PK_LABEL[k]} ${verdTag(k)}</h3><p class="why">${why[k]}</p><ol>${L.map(x=>{ const id=legId(k,x); const r=pickResult(k,x);
    return `<li class="leg2 ${SLIP.find(s=>s.id===id)?'on':''}" data-leg="${esc(id)}" data-k="${k}" data-x='${esc(JSON.stringify(x))}'><span><span class="mu">${esc(pickText(k,x))}</span> ${markTxt(r)}<br><span class="t">${esc(x.mu)}${x.edge_pts!=null?` · model ${x.edge_pts>0?'+':''}${x.edge_pts} pts vs line`:''}${x.median!=null?` · median ${Math.round(x.median)}`:''}</span></span><span class="p">${pct(x.p)}</span></li>`; }).join('')}</ol></div>`; }).join('');
  document.querySelectorAll('#picks .leg2').forEach(li=>li.onclick=()=>{ const id=li.dataset.leg; const i=SLIP.findIndex(s=>s.id===id);
    if(i>=0) SLIP.splice(i,1); else { const x=JSON.parse(li.dataset.x); SLIP.push({id, k:li.dataset.k, x}); }
    try{ localStorage.setItem('egd_nfl_slip_'+P.season+'_'+P.week, JSON.stringify(SLIP)); }catch(e){} renderPicks(); renderSlip(); }); }
function renderSlip(){ const el=document.getElementById('slip'); if(!SLIP.length){ el.innerHTML='<h3>Slip</h3><p>Tap any lean below to add it. Legs from the same game are correlated; the combined probability assumes independence and says so.</p>'; return; }
  const p = SLIP.reduce((a,s)=>a*s.x.p, 1); const games=new Set(SLIP.map(s=>s.x.game_id)); const same = games.size < SLIP.length;
  el.innerHTML = `<h3>Slip · ${SLIP.length} legs</h3><div class="slip"><div class="big">${pct(p)}</div><div class="row"><span>fair odds <b>${(1/p).toFixed(2)}</b> (${dec2am(1/p)})</span>
   <label>book odds <input id="slip-o" placeholder="3.10 or +210"></label><span id="slip-ev"></span><button class="rbtn" id="slip-clear">clear</button></div>
   ${same?'<div class="warn">Two or more legs share a game: they are correlated, so the true combined probability differs from the product shown.</div>':''}
   <div class="row">${SLIP.map(s=>`<span>${esc(pickText(s.k,s.x))} <b>${pct(s.x.p,0)}</b></span>`).join(' · ')}</div></div>`;
  const O=document.getElementById('slip-o'); O.oninput=()=>{ const d=parseOdds(O.value); const ev=d?p*d-1:null; document.getElementById('slip-ev').innerHTML = ev==null?'':`EV <b style="color:${ev>=0?'var(--green)':'var(--red)'}">${ev>=0?'+':''}${(ev*100).toFixed(1)}%</b>`; };
  document.getElementById('slip-clear').onclick=()=>{ SLIP=[]; try{ localStorage.removeItem('egd_nfl_slip_'+P.season+'_'+P.week); }catch(e){} renderPicks(); renderSlip(); }; }

// ------------------------------------------------------------- results
function renderResults(){ const keys=['ml','spread','total','h1','h2','fg','qb_yds','qb_td','atd']; const t={};
  for(const k of keys) for(const x of (P.picks[k]||[])){ const r=pickResult(k,x); if(!r||r==='pending') continue; t[k]=t[k]||{hit:0,miss:0,tie:0}; t[k][r]++; }
  const any=Object.keys(t).length;
  document.getElementById('wkresults').innerHTML = `<h3>This week's leans</h3>${any?`<div class="tbl"><table><tr><th>Market</th><th>won</th><th>lost</th><th>push</th></tr>${keys.filter(k=>t[k]).map(k=>`<tr><td>${PK_LABEL[k]}</td><td>${t[k].hit}</td><td>${t[k].miss}</td><td>${t[k].tie}</td></tr>`).join('')}</table></div>`:'<p>No lean has been decided yet. Results fill in live as the games are played (scores and box scores from ESPN), and are confirmed from the play-by-play the next morning.</p>'}`;
  fetchJSON(BASE+'scorecard.json').then(sc=>{ const S=sc.summary||{}; const ks=keys.filter(k=>S[k]);
    document.getElementById('track').innerHTML = `<h3>Track record, every published week</h3>${ks.length?`<div class="tbl"><table><tr><th>Market</th><th>won</th><th>lost</th><th>push</th><th>rate</th></tr>${ks.map(k=>`<tr><td>${PK_LABEL[k]}</td><td>${S[k].won}</td><td>${S[k].lost}</td><td>${S[k].push}</td><td>${S[k].rate!=null?pct(S[k].rate):'–'}</td></tr>`).join('')}</table></div><p class="small">updated ${esc(sc.updated_utc)}. A lean is graded at the line shown when it was published.</p>`:'<p>No completed week yet.</p>'}`; })
  .catch(()=>{ document.getElementById('track').innerHTML='<h3>Track record</h3><p>Not available yet.</p>'; });
  fetchJSON(BASE+'weeks.json').then(w=>{ document.getElementById('weeklist').innerHTML=(w.weeks||[]).map(x=>`<a class="${x.name===(P.season+'-w'+String(P.week).padStart(2,'0'))?'now':''}" href="${BASE}weeks/${x.name}.html">${x.season} week ${x.week}</a>`).join(''); }).catch(()=>{}); }

// ------------------------------------------------------------- about
function renderAbout(){ const el=document.getElementById('validation'); const C=M.cfg||{};
  if(!V){ el.innerHTML='<h3>Validation</h3><p>The walk-forward backtest has not been published yet.</p>'; }
  else { const keys=[['moneyline','Moneyline'],['spread','Spread'],['total','Total'],['h1_total','1st half total'],['h2_total','2nd half total'],['fg_over0.5','Team FGs o0.5'],['fg_over1.5','Team FGs o1.5'],['fg_over2.5','Team FGs o2.5'],['qb_yards','QB passing yards'],['qb_td_over0.5','QB TDs o0.5'],['qb_td_over1.5','QB TDs o1.5'],['qb_td_over2.5','QB TDs o2.5'],['anytime_td','Anytime TD']];
    const row = (S,k,l) => { const m=S[k]; if(!m||!m.n) return ''; const v=m.verdict; return `<tr><td>${l}</td><td>${m.n.toLocaleString()}</td><td>${m.ll_model}</td><td>${m.ll_base}</td><td>${m.gain>=0?'+':''}${m.gain} ± ${m.se}</td><td><span class="verd ${v==='beats baseline'?'beats':(v==='marginal'?'marginal':'none')}">${v}</span></td></tr>`; };
    const bets = m => (m && m.bets) ? m.bets.map(b=>`${pct(b.threshold,0)}+: ${b.bets} bets, ${b.win_rate!=null?pct(b.win_rate):'–'} won, ROI ${b.roi!=null?(b.roi>=0?'+':'')+(b.roi*100).toFixed(1)+'%':'–'}`).join(' · ') : '';
    const B=V.pooled.blend||{};
    el.innerHTML = `<h3>Walk-forward validation · seasons ${esc((V.seasons||[]).join(', '))}</h3>
    <p>Every week of each test season was predicted using only games played before it. Log loss (lower is better) is compared with a baseline that needs no model; the difference is the model's gain, with its standard error. "Beats baseline" means the gain is more than two standard errors.</p>
    <div class="tbl"><table><tr><th>Market</th><th>n</th><th>model</th><th>baseline</th><th>gain</th><th>verdict</th></tr>${keys.map(([k,l])=>row(V.pooled,k,l)).join('')}</table></div>
    <p class="small">Baselines: moneyline = the closing line with the vig removed; spread and total = 50/50 at the closing number; halves and field goals = the hit rate of the same line over the same games (known only in hindsight, which flatters the baseline); quarterback yards = 50/50 at his recent average; touchdowns = a Poisson at his recent rate; anytime touchdown = each player's own recent rate.</p>
    <p class="small">Betting the model alone against the closing spread: ${bets(V.pooled.spread)}.<br>Against the closing total: ${bets(V.pooled.total)}.</p>
    <p class="small">How much of the model's disagreement with the closing line to keep (regression of the result on model minus line): margin w = ${B.margin?B.margin.w+' ± '+B.margin.se:'n/a'}, total w = ${B.total?B.total.w+' ± '+B.total.se:'n/a'}. In use: margin ${(M.blend||{}).margin??0}, total ${(M.blend||{}).total??0}.</p>
    ${V.pooled.qb_yards?`<p class="small">Quarterback yards, mean absolute error: model median ${V.pooled.qb_yards.mae_model_median} vs his recent average ${V.pooled.qb_yards.mae_recent_avg}.</p>`:''}
    <h3 style="margin-top:12px">By season</h3><div class="tbl"><table><tr><th>Season</th>${keys.slice(0,9).map(([,l])=>`<th>${l}</th>`).join('')}</tr>${Object.entries(V.by_season||{}).map(([s,S])=>`<tr><td>${s}</td>${keys.slice(0,9).map(([k])=>{const m=S[k]; return `<td>${m&&m.n?(m.gain>=0?'+':'')+m.gain:''}</td>`;}).join('')}</tr>`).join('')}</table></div>
    <p class="small">generated ${esc(V.generated_utc||'')} · ${(V.sims||0).toLocaleString()} sims per game in the backtest.</p>`; }
  document.getElementById('method').innerHTML = `<h3>How the numbers are made</h3>
  <p><b>Data.</b> nflverse play-by-play for every regular-season game (current season refreshed every run), the nflverse schedule with the market's spread, total and moneylines, the official injury report, depth charts and weekly rosters; Open-Meteo for kickoff weather at outdoor stadiums; ESPN for live scores and box scores.</p>
  <p><b>The league table.</b> Every drive of the last three seasons is classified by half, how it started (kickoff, punt, turnover), time left in the half (six buckets) and score margin (seven states). For each situation the table holds the share of drives ending in a touchdown, field goal, missed field goal, punt, turnover, turnover on downs, end of half, defensive touchdown or safety, plus how long they took and how many dropbacks they used.</p>
  <p><b>Teams.</b> A team's offense is its touchdowns, field-goal tries and turnovers against what the league table expects from the same drives, as log odds ratios shrunk toward zero (${C.k_drive_team||300} pseudo-drives for touchdowns and turnovers, ${C.k_drive_fg||600} for field-goal tries). The same for the defense, pace, dropbacks per drive and passing yards per dropback. A game last season counts ${Math.round(((C.prior_season_weights||[0.35])[0])*100)}% of a current-season game, two seasons back ${Math.round(((C.prior_season_weights||[0,0.15])[1])*100)}%. Each of these settings won a walk-forward comparison (Research tab).</p>
  <p><b>Quarterbacks and kickers.</b> The starting quarterback's own yards per dropback and touchdown-pass share replace the team's when he has enough dropbacks; a mid-season change applies the measured effect of new starters. The kicker's makes against the league curve for his distances shift field-goal accuracy.</p>
  <p><b>Simulation.</b> ${(M.sims||100000).toLocaleString()} games per matchup, drive by drive, with overtime. When the book's spread and total are known the scoring rates are shifted until the simulation's mean margin and total match them (plus the measured share of the model's own disagreement). Every market is read from the same simulated games, so halves, field goals, quarterback lines and touchdown scorers agree with each other and with the game line.</p>
  <p><b>Anytime touchdown.</b> Each player's share of the team's passing and rushing touchdowns is his own rate shrunk toward his usage (half overall share, half red-zone share), rescaled across the active, healthy players; the probability is computed against every simulated game's touchdown count.</p>
  <p><b>Limits.</b> No play-level personnel model (offensive line, cornerbacks), no in-game injuries, no garbage-time substitutions; questionable players are included and flagged. The market already prices most of this, which is why the game lines follow it.</p>`;
  document.getElementById('foot').innerHTML = `Model ${esc(M.model_version)} · generated ${esc(P.generated_utc)} in ${M.seconds}s · <a href="${BASE}weeks/${P.season}-w${String(P.week).padStart(2,'0')}.json">payload JSON</a> · <a href="${BASE}weeks/${P.season}-w${String(P.week).padStart(2,'0')}.csv">CSV</a>`; }

function render(){ renderLivebar(); renderBoard(); renderCards(); renderPicks(); renderSlip(); renderResults(); }
renderToolbar(); renderPC(); renderResearch(); renderAbout(); render();
document.getElementById('fab').onclick=()=>{ const f=document.getElementById('fab'); f.classList.add('spin'); refreshLive().finally(()=>setTimeout(()=>f.classList.remove('spin'),400)); };
refreshLive();
setInterval(()=>{ const now=Date.now(); const near=P.games.some(g=>{ const k=kickoff(g); return k && now>k-15*60000 && now<k.getTime()+5*3600000; }); if(near && document.visibilityState==='visible') refreshLive(); }, 30000);
</script>
</body>
</html>
"""


def static_summary(p: dict) -> str:
    """No-JS summary (for readers and tools that do not run scripts)."""
    rows = []
    for g in sorted(p["games"], key=lambda g: g.get("kickoff_utc") or ""):
        mk = g["markets"]; L = g.get("lines") or {}
        sp = mk.get("spread") or {}; to = mk.get("total") or {}
        qa, qh = mk["qb"]["away"], mk["qb"]["home"]
        top = (g.get("anytime") or {}).get("home", [])[:1] + (g.get("anytime") or {}).get("away", [])[:1]
        tops = ", ".join("%s %.0f%%" % (x["name"], x["p"] * 100) for x in top)
        rows.append(f"<tr><td>{g['away']} @ {g['home']}</td><td>{g['date']} {g['time']}</td><td>{mk['ml']['away']*100:.1f}% / {mk['ml']['home']*100:.1f}%</td>"
                    f"<td>{L.get('spread', '')}: {sp.get('home_cover', 0)*100:.1f}% home</td><td>{L.get('total', '')}: {to.get('over', 0)*100:.1f}% over</td>"
                    f"<td>{mk['h1_fair_line']} / {mk['h2_fair_line']}</td><td>{mk['fg']['away']['over1.5']*100:.0f}% / {mk['fg']['home']['over1.5']*100:.0f}%</td>"
                    f"<td>{qa['yds_fair_line']} / {qh['yds_fair_line']}</td><td>{qa['td_over1.5']*100:.0f}% / {qh['td_over1.5']*100:.0f}%</td>"
                    f"<td>{tops}</td></tr>")
    return (f'<div class="static" id="static"><h1>NFL {p["season"]} week {p["week"]}</h1><p>Probabilities from {p["meta"]["sims"]:,} simulated games per matchup. '
            f'Columns: moneyline away / home; home cover at the market spread; over at the market total; fair 1st / 2nd half lines; team field goals over 1.5 away / home; '
            f'fair QB passing-yard lines away / home; QB over 1.5 TD passes away / home; top anytime touchdown per team. Updated {p["generated_utc"]}.</p>'
            f'<table><tr><th>Game</th><th>Kickoff (ET)</th><th>ML</th><th>Spread</th><th>Total</th><th>1H/2H</th><th>FG o1.5</th><th>QB yds</th><th>QB TD o1.5</th><th>Anytime TD</th></tr>'
            + "".join(rows) + "</table></div>")


def render(payload: dict, nhl_href: str = "../index.html") -> str:
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    return (TEMPLATE.replace("__CSS__", BASE_CSS + NFL_CSS).replace("__PAYLOAD__", data).replace("__STATIC__", static_summary(payload))
            .replace("__WEEK__", str(payload["week"])).replace("__NHL_HREF__", nhl_href))


__all__ = ["render", "TEMPLATE", "static_summary"]
