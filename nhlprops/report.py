"""The NHL props page: tonight's games with team totals, power-play goals and every skater's shots, points,
assists, anytime goal and blocked shots, a scanner of every selection graded against DraftKings' prices, a price
check for any line, and the walk-forward validation behind each market."""
from __future__ import annotations

import json
from pathlib import Path

from earlygoal.brand import BRAND_CSS, brand_html, finish_page
from nfl.report import BASE_CSS, NFL_CSS

PROPS_CSS = r"""
.sk{width:100%;min-width:0 !important;border-collapse:collapse;font-size:12.5px;font-variant-numeric:tabular-nums;table-layout:fixed}
.sk col.c0{width:34%}.sk col.cx{width:13.2%}
@media (max-width:520px){.sk{font-size:11.5px}.sk col.c0{width:30%}.sk col.cx{width:14%}.sk td{padding:4px 3px}}
.sk th{font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim);text-align:right;padding:4px 6px;border-bottom:1px solid var(--line);white-space:nowrap}
.sk th:first-child,.sk td:first-child{text-align:left}
.sk td{padding:4px 6px;border-top:1px solid var(--line);text-align:right;white-space:nowrap}
.sk td:first-child{white-space:normal;overflow:hidden;text-overflow:ellipsis}
.sk td .nm{font-weight:600}.sk td .ln{color:var(--dim);font-size:10.5px;margin-left:4px}
.sk td .l{color:var(--dim);font-size:10.5px;display:block}
.sk tr.dm td{color:var(--muted)}
.sk td.hi{color:var(--green);font-weight:700}.sk td.lo{color:var(--red)}
.sk td .bk{display:block;font-size:10px;color:var(--ice)}
.tt{display:grid;grid-template-columns:1fr 1fr;gap:6px;margin:6px 0}
@media (max-width:520px){.tt{grid-template-columns:1fr}}
.tblwrap{overflow-x:auto;-webkit-overflow-scrolling:touch}
.src{font-size:11px;color:var(--dim);margin:4px 0 2px}
.inj{color:var(--amber);font-size:10px;margin-left:4px}
"""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Gill Sports · NHL props</title>
<meta name="description" content="NHL props for __DATE__: shots on goal, points, assists, anytime goal, blocked shots, team totals and power-play goals, priced at DraftKings' lines and validated walk-forward">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
<style>__CSS__</style>
</head>
<body>
<div class="app"><div class="wrap">
  <div class="row">
    __BRAND__
    <div class="hmeta"><span id="dayslot"></span></div>
  </div>
  <nav class="tabs" id="tabs">
    <button data-tab="tonight" class="on">Tonight</button>
    <button data-tab="scanner">Scanner</button>
    <button data-tab="about">About</button>
  </nav>
</div></div>

<div class="wrap">
<div id="banner"></div>
__STATIC__

<section class="tab on" id="tab-tonight">
  <div class="status" id="status"></div>
  <div class="ncards" id="cards"></div>
  <div class="panel" id="pricecheck" style="margin-top:12px"></div>
</section>

<section class="tab" id="tab-scanner">
  <div class="panel" id="scanner"></div>
</section>

<section class="tab" id="tab-about">
  <div class="panel" id="validation"></div>
  <div class="panel" id="method"></div>
  <div class="panel" id="factors"></div>
  <footer id="foot"></footer>
</section>
</div>

<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
(function(){ const s=document.getElementById('static'); if(s) s.remove(); })();
const P = JSON.parse(document.getElementById('payload').textContent);
const V = P.validation; const LINES = P.lines;
const pct = (x,d=1) => (x*100).toFixed(d)+'%';
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const dec = x => x==null ? '' : Number(x).toFixed(2);
const niceDate = d => { try { const [y,m,dd]=d.split('-'); return new Date(+y,+m-1,+dd).toLocaleDateString('en-US',{weekday:'short',month:'short',day:'numeric'}); } catch(e){ return d; } };
const whenET = iso => { try{ return new Date(iso).toLocaleTimeString('en-US',{hour:'numeric',minute:'2-digit',timeZone:'America/Toronto'})+' ET'; }catch(e){ return ''; } };
const LABEL = {sog:'Shots on goal', pts:'Points', ast:'Assists', goal:'Anytime goal', blk:'Blocked shots', team_total:'Team total', ppg:'Power-play goals'};
const VKEY = {sog:'sog', pts:'pts', ast:'ast', goal:'goal', blk:'blk', team_total:'team_total', ppg:'ppg05'};
let MYBOOK='DraftKings'; try{ const v=localStorage.getItem('egd_book'); if(v!==null) MYBOOK=v; }catch(e){}
{ const ds=document.getElementById('dayslot'); if(ds) ds.textContent = niceDate(P.date); }

// ---------------------------------------------------------------- helpers
function ou(pmf, line){ let o=0,p=0,u=0; pmf.forEach((x,i)=>{ if(i>line) o+=x; else if(i===line) p+=x; else u+=x; }); const s=o+p+u||1; return {over:o/s, push:p/s, under:u/s}; }
function pNoPush(pmf, line, side){ const r=ou(pmf,line); const q=1-r.push||1; return (side==='under'?r.under:r.over)/q; }
const verdictOf = k => { const m=V && V.pooled && V.pooled[VKEY[k]||k]; return m && m.verdict ? m.verdict : null; };
const verdTag = k => { const v=verdictOf(k); if(!v) return '<span class="verd marginal">not yet validated</span>'; return `<span class="verd ${v==='beats baseline'?'beats':(v==='marginal'?'marginal':'none')}">${esc(v)}</span>`; };
function myBook(entry){ if(!entry || !entry.books) return null; const b = MYBOOK ? entry.books[MYBOOK] : null; if(b) return {line:b.line, prices:b.prices, book:MYBOOK};
  if(!MYBOOK){ const best={}; let line=entry.line; Object.entries(entry.books).forEach(([t,b])=>{ Object.entries(b.prices||{}).forEach(([s,pr])=>{ if(!best[s]||pr>best[s].pr) best[s]={pr,t}; }); }); const prices={}; Object.entries(best).forEach(([s,x])=>prices[s]=x.pr); return {line, prices, book:Object.values(best)[0]?.t||''}; }
  return null; }
function calBand(k, side, p){ const m=V && V.pooled && V.pooled[VKEY[k]]; if(!m||!m.calibration) return null; const q = side==='under'?1-p:p; let best=null; for(const b of m.calibration){ if(!best || Math.abs(b.pred-q)<Math.abs(best.pred-q)) best=b; } return best ? {pred: side==='under'?1-best.pred:best.pred, actual: side==='under'?1-best.actual:best.actual, n:best.n} : null; }
function evidence(k){ const v=verdictOf(k); return v==='beats baseline'?2:(v==='marginal'?1:0); }
function gradeOf(o){ const E=o.E, Q=o.Q; let v=null; if(o.ev!=null) v = o.ev>=0.05 ? 2 : (o.ev>=0 ? 1 : -1); o.Vv=v;
  if(v===-1) return 'D'; if(v===null) return (E===2 && Q>=1) ? 'B' : (E>=1 ? 'C' : 'D');
  if(E===2 && Q===2 && v===2) return 'S'; const s=E+Q+v; return s>=5 ? 'A' : (s>=4 ? 'B' : 'C'); }
const GRADE_ORDER={S:0,A:1,B:2,C:3,D:4};

// ---------------------------------------------------------------- status + banner
const nPriced = P.games.filter(g=>g.book_markets && g.book_markets.length).length;
document.getElementById('status').innerHTML = [
  `<b>${niceDate(P.date)}</b>`, `<b>${P.games.length}</b> games`, `skaters from <b>${P.games.filter(g=>/DailyFaceoff/.test(g.sides.home.lineup_source)).length*2}</b> projected lineups`,
  `data through <b>${esc(P.data_through||'n/a')}</b>`, `${MYBOOK||'book'} prices on <b>${nPriced}</b> of ${P.games.length} games${P.odds && P.odds.credits_remaining!=null ? ` (${P.odds.credits_remaining} API credits left this month)` : ''}`,
  `updated <b>${esc(P.generated_utc)}</b>`].map(x=>`<span>${x}</span>`).join('');
if(!V) document.getElementById('banner').innerHTML = `<div class="banner"><b>Validation pending.</b> The walk-forward backtest has not been published yet; treat every number as unvalidated.</div>`;

// ---------------------------------------------------------------- tabs
const tabs=document.getElementById('tabs');
function showTab(name){ document.querySelectorAll('section.tab').forEach(s=>s.classList.toggle('on', s.id==='tab-'+name)); tabs.querySelectorAll('button').forEach(b=>b.classList.toggle('on', b.dataset.tab===name)); try{ localStorage.setItem('props_tab', name); }catch(e){} }
tabs.querySelectorAll('button').forEach(b=>b.onclick=()=>showTab(b.dataset.tab));
try{ const t=localStorage.getItem('props_tab'); if(t && document.getElementById('tab-'+t)) showTab(t); }catch(e){}

// ---------------------------------------------------------------- selections (every market at the book's line, else the model's fair line)
function lineFor(k, entry, fairLine){ const b=myBook(entry); if(b && b.line!=null) return {line:b.line, book:b}; return {line:fairLine, book:null}; }
function buildSelections(){ const out=[];
  P.games.forEach(g=>{ ['home','away'].forEach(side=>{ const S=g.sides[side]; const mu=`${g.away} @ ${g.home}`;
    // team total
    { const ent=S.book_team_total; const {line,book}=lineFor('team_total', ent, S.markets.fair_total); const pmf=S.markets.team_total;
      ['over','under'].forEach(sd=>{ const p=pNoPush(pmf,line,sd); const odds=book && book.prices && book.prices[sd]>1 ? book.prices[sd] : null;
        out.push(sel({kind:'team_total', game:g, mu, who:S.team, side:sd, line, p, odds, book: book?book.book:null, Q:2, text:`${S.team} team total ${sd} ${line}`})); }); }
    // power-play goals
    { const pmf=S.markets.ppg; [0.5,1.5].forEach(line=>{ const p=pNoPush(pmf,line,'over'); out.push(sel({kind:'ppg', game:g, mu, who:S.team, side:'over', line, p, odds:null, book:null, Q:2, text:`${S.team} power-play goals over ${line}`})); }); }
    (S.skaters||[]).forEach(s=>{ if(!s.pmf) return; const Q = s.games>=15?2:(s.games>=6?1:0);
      ['sog','pts','ast','blk'].forEach(k=>{ const ent=s.book && s.book[k]; const {line,book}=lineFor(k, ent, s.fair[k]);
        if(!book && ((k==='blk' && s.mean.blk<0.9) || (k==='ast' && s.mean.ast<0.35) || (k==='pts' && s.mean.pts<0.4))) return;   // markets DraftKings does not post for this skater
        const pmf=s.pmf[k]; ['over','under'].forEach(sd=>{ const p=pNoPush(pmf,line,sd); if(!book && (p>0.75 || (sd==='under' && k!=='sog' && k!=='blk'))) return;
          const odds=book && book.prices && book.prices[sd]>1 ? book.prices[sd] : null;
          out.push(sel({kind:k, game:g, mu, who:s.name, pos:s.pos, team:S.team, side:sd, line, p, odds, book:book?book.book:null, Q, text:`${s.name} ${LABEL[k].toLowerCase()} ${sd} ${line}`, sk:s})); }); });
      { const ent=s.book && s.book.goal; const b=myBook(ent); const odds=b && b.prices && b.prices.yes>1 ? b.prices.yes : null; const p=s.p_goal;
        out.push(sel({kind:'goal', game:g, mu, who:s.name, pos:s.pos, team:S.team, side:'yes', line:0.5, p, odds, book:b?b.book:null, Q, text:`${s.name} anytime goal`, sk:s})); }
    }); }); });
  return out; }
function sel(o){ o.E=evidence(o.kind); o.fair = o.p>0 ? 1/o.p : null; o.ev = o.odds ? o.p*o.odds-1 : null; o.band=calBand(o.kind, o.side, o.p);
  if(o.odds && o.kind==='goal' && (1/o.odds) < o.p*0.5) o.longshot=true;
  o.grade = o.longshot ? 'C' : gradeOf(o); o.id=`${o.game.home}|${o.who}|${o.kind}|${o.side}|${o.line}`; return o; }
let SELS = buildSelections();

// ---------------------------------------------------------------- cards
function cell(p, hi){ const c = p>=0.6?'hi':(p<=0.4?'lo':''); return `<td class="${c}">${pct(p,0)}</td>`; }
function skRow(s, S){ if(!s.pmf) return `<tr class="dm"><td><span class="nm">${esc(s.name)}</span><span class="ln">${esc(s.pos)} ${esc(s.line||'')}${s.pp?' · '+esc(s.pp):''}</span></td><td colspan="6" style="text-align:left;color:var(--dim)">no record in the play-by-play yet (new to the league or the data)</td></tr>`;
  const m = k => { const ent=s.book && s.book[k]; const {line,book}=lineFor(k, ent, s.fair[k]); const po=pNoPush(s.pmf[k],line,'over'); const pu=1-po;
    const sd = po>=0.5?'over':'under'; const p = Math.max(po,pu); const odds = book && book.prices && book.prices[sd]>1 ? book.prices[sd] : null;
    const c = p>=0.62?'hi':''; return `<td class="${c}" title="${esc(LABEL[k])}: over ${pct(po)} / under ${pct(pu)} at ${line}${book?' ('+esc(book.book)+' line)':' (model fair line)'}"><span class="l">${sd[0]} ${line}${book?'':'*'}</span>${pct(p,0)}${odds?`<span class="bk">${dec(odds)} · EV ${(p*odds-1>=0?'+':'')+pct(p*odds-1,0)}</span>`:''}</td>`; };
  const goal = (()=>{ const ent=s.book && s.book.goal; const b=myBook(ent); const odds=b && b.prices && b.prices.yes>1 ? b.prices.yes : null; const p=s.p_goal; return `<td class="${p>=0.4?'hi':''}" title="anytime goal"><span class="l">yes</span>${pct(p,0)}${odds?`<span class="bk">${dec(odds)} · EV ${(p*odds-1>=0?'+':'')+pct(p*odds-1,0)}</span>`:''}</td>`; })();
  const inj = s.status ? `<span class="inj">${esc(s.status)}</span>` : '';
  return `<tr class="${s.pos==='D'?'dm':''}"><td><span class="nm">${esc(s.name)}</span><span class="ln">${esc(s.pos)} ${esc(s.line||'')}${s.pp?' · '+esc(s.pp):''}</span>${inj}<span class="l">${s.games} gp · L5 ${(s.last5||[]).map(x=>x.sog+'/'+x.pts).join(' ')}</span></td>${m('sog')}${m('pts')}${m('ast')}${goal}${m('blk')}</tr>`; }
function sideBlock(g, side){ const S=g.sides[side]; const tt=S.book_team_total; const {line,book}=lineFor('team_total', tt, S.markets.fair_total); const po=pNoPush(S.markets.team_total,line,'over');
  const oddsO = book && book.prices && book.prices.over>1 ? book.prices.over : null, oddsU = book && book.prices && book.prices.under>1 ? book.prices.under : null;
  const pp05 = ou(S.markets.ppg,0.5).over, pp15 = ou(S.markets.ppg,1.5).over;
  return `<h5>${esc(S.team)} <span class="mini" style="text-transform:none;letter-spacing:0">expected ${S.lam_goals.toFixed(2)} goals · ${S.markets.exp_sog} shots · ${S.markets.lam_opps.toFixed(1)} power plays at ${pct(S.markets.p_conv,0)}</span></h5>
   <div class="tt"><div class="mb"><span class="k">Team total ${line}${book?' · '+esc(book.book):' · fair line'} ${verdTag('team_total')}</span><div class="row"><span>over <span class="p">${pct(po)}</span>${oddsO?` <span class="mini">${dec(oddsO)} EV ${(po*oddsO-1>=0?'+':'')+pct(po*oddsO-1,0)}</span>`:''}</span><span>under <span class="p">${pct(1-po)}</span>${oddsU?` <span class="mini">${dec(oddsU)} EV ${((1-po)*oddsU-1>=0?'+':'')+pct((1-po)*oddsU-1,0)}</span>`:''}</span></div></div>
   <div class="mb"><span class="k">Power-play goals ${verdTag('ppg')}</span><div class="row"><span>over 0.5 <span class="p">${pct(pp05)}</span></span><span>over 1.5 <span class="p">${pct(pp15)}</span></span></div><span class="s">expected ${S.markets.lam_ppg.toFixed(2)}</span></div></div>
   <div class="src">${esc(S.lineup_source)} · ${S.n_lineup} skaters</div>
   <div class="tblwrap"><table class="sk"><colgroup><col class="c0"><col class="cx"><col class="cx"><col class="cx"><col class="cx"><col class="cx"></colgroup><tr><th>Skater <span style="font-weight:400;text-transform:none;letter-spacing:0">L5 shots/pts</span></th><th>SOG</th><th>Points</th><th>Assists</th><th>Goal</th><th>Blocks</th></tr>${(S.skaters||[]).map(s=>skRow(s,S)).join('')}</table></div>`; }
function renderCards(){ document.getElementById('cards').innerHTML = P.games.map(g=>`<div class="nc" id="g-${g.home}"><div class="hd"><span class="mu">${esc(g.away)} @ ${esc(g.home)}</span><span class="when">${whenET(g.start_utc)}${g.book_markets && g.book_markets.length ? ` · ${esc(MYBOOK||'book')}: ${g.book_markets.map(k=>LABEL[k]||k).join(', ')}` : ' · no book prices fetched for this game (model fair lines shown, marked *)'}</span></div>${sideBlock(g,'away')}${sideBlock(g,'home')}</div>`).join(''); }
renderCards();

// ---------------------------------------------------------------- price check
function renderPC(){ const el=document.getElementById('pricecheck'); const opts = P.games.map((g,i)=>`<option value="${i}">${esc(g.away)} @ ${esc(g.home)}</option>`).join('');
  el.innerHTML = `<h3>Price check <span class="mini" style="text-transform:none;letter-spacing:0">type the line and odds your book shows; pushes included</span></h3>
  <div class="pc"><label>Game<select id="pc-g">${opts}</select></label><label>Skater or team<select id="pc-w"></select></label><label>Market<select id="pc-k"></select></label><label>Line<input id="pc-l" type="number" step="0.5" value="2.5"></label><label>Side<select id="pc-s"><option>over</option><option>under</option></select></label><label>Decimal odds<input id="pc-o" type="number" step="0.01" value="1.91"></label></div><div class="pcout" id="pc-out"></div>`;
  const g=()=>P.games[+document.getElementById('pc-g').value];
  const fillW=()=>{ const G=g(); const w=document.getElementById('pc-w'); const items=[]; ['away','home'].forEach(sd=>{ const S=G.sides[sd]; items.push(`<option value="T:${sd}">${esc(S.team)} (team)</option>`); (S.skaters||[]).forEach((s,i)=>{ if(s.pmf) items.push(`<option value="${sd}:${i}">${esc(s.name)} (${esc(S.team)})</option>`); }); }); w.innerHTML=items.join(''); fillK(); };
  const fillK=()=>{ const v=document.getElementById('pc-w').value; const k=document.getElementById('pc-k'); k.innerHTML = v.startsWith('T:') ? `<option value="team_total">Team total</option><option value="ppg">Power-play goals</option>` : ['sog','pts','ast','goal','blk'].map(x=>`<option value="${x}">${LABEL[x]}</option>`).join(''); calc(); };
  const calc=()=>{ const G=g(); const v=document.getElementById('pc-w').value; const k=document.getElementById('pc-k').value; const L=+document.getElementById('pc-l').value; const sd=document.getElementById('pc-s').value; const o=+document.getElementById('pc-o').value;
    let pmf; if(v.startsWith('T:')){ pmf=G.sides[v.slice(2)].markets[k]; } else { const [side,i]=v.split(':'); pmf=G.sides[side].skaters[+i].pmf[k]; }
    if(!pmf) return; const r=ou(pmf,L); const p = (sd==='under'?r.under:r.over)/(1-r.push||1); const ev=o>1?p*o-1:null;
    document.getElementById('pc-out').innerHTML = `<div><span class="k">${sd} ${L}</span><span class="v">${pct(p)}</span></div><div><span class="k">push</span><span class="v">${pct(r.push)}</span></div><div><span class="k">fair odds</span><span class="v">${p>0?(1/p).toFixed(2):'-'}</span></div><div><span class="k">EV at ${o}</span><span class="v" style="color:${ev>=0?'var(--green)':'var(--red)'}">${ev==null?'-':(ev>=0?'+':'')+pct(ev)}</span></div><div><span class="k">validation</span><span class="v" style="font-size:13px">${verdTag(k)}</span></div>`; };
  document.getElementById('pc-g').onchange=fillW; document.getElementById('pc-w').onchange=fillK; ['pc-k','pc-l','pc-s','pc-o'].forEach(id=>{ document.getElementById(id).oninput=calc; document.getElementById(id).onchange=calc; }); fillW(); }
renderPC();

// ---------------------------------------------------------------- scanner
const SC = {grades:['S','A','B'], kinds:['sog','pts','ast','goal','blk','team_total','ppg'], odds:true, sort:'grade', q:''};
try{ const s=JSON.parse(localStorage.getItem('props_sc')||'null'); if(s) Object.assign(SC, s); }catch(e){}
const saveSC=()=>{ try{ localStorage.setItem('props_sc', JSON.stringify(SC)); }catch(e){} };
function renderScanner(){ const el=document.getElementById('scanner');
  const anyOdds = SELS.some(x=>x.odds); const useOdds = SC.odds && anyOdds;
  let rows = SELS.filter(x=>SC.kinds.includes(x.kind) && SC.grades.includes(x.grade) && (!useOdds || x.odds) && (!SC.q || (x.who+' '+x.mu).toLowerCase().includes(SC.q.toLowerCase())));
  rows.sort((a,b)=> SC.sort==='ev' ? ((b.ev??-9)-(a.ev??-9)) : (SC.sort==='p' ? b.p-a.p : (GRADE_ORDER[a.grade]-GRADE_ORDER[b.grade] || ((b.ev??-9)-(a.ev??-9)) || b.p-a.p)));
  const withOdds = SELS.filter(x=>x.odds).length;
  el.innerHTML = `<h3>Scanner <span class="mini" style="text-transform:none;letter-spacing:0">every selection, graded</span></h3>
   <div class="scanbar"><label>Sort<select id="sc-sort"><option value="grade" ${SC.sort==='grade'?'selected':''}>grade, then EV</option><option value="ev" ${SC.sort==='ev'?'selected':''}>EV</option><option value="p" ${SC.sort==='p'?'selected':''}>probability</option></select></label>
   <label>Search<input id="sc-q" value="${esc(SC.q)}" placeholder="player or team"></label>
   <label>My sportsbook<select id="sc-book"><option ${MYBOOK==='DraftKings'?'selected':''}>DraftKings</option><option value="" ${MYBOOK===''?'selected':''}>Best price (any book)</option></select></label>
   <div class="chips" id="sc-grades">${['S','A','B','C','D'].map(x=>`<button data-g="${x}" class="${SC.grades.includes(x)?'on':''}">${x}</button>`).join('')}<button id="sc-odds" class="${SC.odds?'on':''}">${MYBOOK?'only bets '+esc(MYBOOK)+' has posted':'with book odds'}</button></div>
   <div class="chips" id="sc-kinds">${Object.keys(LABEL).map(k=>`<button data-k="${k}" class="${SC.kinds.includes(k)?'on':''}">${LABEL[k]}</button>`).join('')}</div></div>
   <p class="mini" style="margin:6px 0">${rows.length.toLocaleString()} of ${SELS.length.toLocaleString()} selections · book odds on ${withOdds.toLocaleString()}${withOdds?'':' · no DraftKings prices fetched yet today (they are pulled on the afternoon runs within the free API budget), so every selection is at the model\'s fair line: grades top out at B until a price exists. Compare with your book using the price check.'}</p>
   <details class="gradehelp"><summary>How grades work</summary><p><b>S</b> validated market, a skater with 15+ games, and EV of 5% or more at your book's price. <b>A</b> two of those three plus a positive EV. <b>B</b> a validated market without a price yet, or a thinner edge. <b>C</b> a marginal market or a thin sample. <b>D</b> negative EV or an unvalidated market. Lines marked * are the model's own fair lines because the book had not posted that market when prices were fetched; check the book's line with the price check.</p></details>
   <div class="scan">${rows.slice(0,400).map(x=>`<div class="srow" onclick="document.getElementById('g-${x.game.home}').scrollIntoView({behavior:'smooth'});showTab('tonight')"><span class="gr g${x.grade}">${x.grade}</span>
     <span class="sel"><b>${esc(x.text)}</b><span class="t">${esc(x.mu)}${x.pos?' · '+esc(x.pos):''}${x.book?'':' · fair line'}</span></span>
     <span class="num n-win"><span class="k">model</span><span class="t">${pct(x.p)}</span></span><span class="num n-fair"><span class="k">fair</span><span class="t">${x.fair?x.fair.toFixed(2):'-'}</span></span>
     <span class="num n-book"><span class="k" title="${esc(x.book||'book')}">${esc(({DraftKings:'DK',FanDuel:'FD',BetMGM:'MGM',Caesars:'CZR',BetRivers:'BR',ESPNBet:'ESPN'})[x.book]||x.book||'book')}</span><span class="t">${x.odds?dec(x.odds):'-'}</span></span><span class="num n-ev"><span class="k">EV</span><span class="t" style="color:${x.ev==null?'var(--dim)':(x.ev>=0?'var(--green)':'var(--red)')}">${x.ev==null?'-':(x.ev>=0?'+':'')+pct(x.ev)}</span></span>
     <span class="num n-bt"><span class="k">backtest</span><span class="t">${x.band?`${pct(x.band.pred,0)} predicted → ${pct(x.band.actual,0)} hit (n=${x.band.n.toLocaleString()})`:'-'}</span></span></div>`).join('')}</div>`;
  const on=(id,ev,fn)=>{ const e=document.getElementById(id); if(e) e[ev]=fn; };
  on('sc-sort','onchange',e=>{ SC.sort=e.target.value; saveSC(); renderScanner(); }); on('sc-q','oninput',e=>{ SC.q=e.target.value; saveSC(); renderScanner(); });
  on('sc-book','onchange',e=>{ MYBOOK=e.target.value; try{ localStorage.setItem('egd_book', MYBOOK); }catch(ex){} SELS=buildSelections(); renderCards(); renderScanner(); });
  on('sc-odds','onclick',()=>{ SC.odds=!SC.odds; saveSC(); renderScanner(); });
  document.querySelectorAll('#sc-grades button[data-g]').forEach(b=>b.onclick=()=>{ const g=b.dataset.g; SC.grades = SC.grades.includes(g) ? SC.grades.filter(x=>x!==g) : [...SC.grades,g]; saveSC(); renderScanner(); });
  document.querySelectorAll('#sc-kinds button[data-k]').forEach(b=>b.onclick=()=>{ const k=b.dataset.k; SC.kinds = SC.kinds.includes(k) ? SC.kinds.filter(x=>x!==k) : [...SC.kinds,k]; saveSC(); renderScanner(); }); }
renderScanner();

// ---------------------------------------------------------------- about
(function(){ const el=document.getElementById('validation'); if(!V){ el.innerHTML='<h3>Validation</h3><p>The walk-forward backtest has not been published yet.</p>'; return; }
  const keys=[['sog','Shots on goal'],['pts','Points over 0.5'],['ast','Assists over 0.5'],['goal','Anytime goal'],['blk','Blocked shots'],['team_total','Team total'],['ppg05','Power-play goals over 0.5'],['ppg15','Power-play goals over 1.5']];
  const row=(k,l)=>{ const m=V.pooled[k]; if(!m||!m.n) return ''; const v=m.verdict; return `<tr><td>${l}</td><td>${m.n.toLocaleString()}</td><td>${m.ll_model}</td><td>${m.ll_base}</td><td>${m.accuracy!=null?pct(m.accuracy,1):''}</td><td>${m.gain>=0?'+':''}${m.gain} ± ${m.se}</td><td><span class="verd ${v==='beats baseline'?'beats':(v==='marginal'?'marginal':'none')}">${v}</span></td></tr>`; };
  const cal=(k,l)=>{ const m=V.pooled[k]; if(!m||!m.calibration) return ''; return `<details><summary>${l}: calibration by decile</summary><div class="tbl"><table><tr><th>n</th><th>predicted</th><th>actual</th></tr>${m.calibration.map(c=>`<tr><td>${c.n}</td><td>${pct(c.pred)}</td><td>${pct(c.actual)}</td></tr>`).join('')}</table></div></details>`; };
  el.innerHTML = `<h3>Walk-forward validation · seasons ${esc((V.seasons||[]).map(s=>(s-1)+'-'+String(s).slice(2)).join(', '))}</h3>
   <p>Every game day was priced with profiles built only from games before it, for the skaters who dressed in their team's previous game (what the live page uses), and a skater who did not play is a void bet. Log loss (lower is better) is compared with a baseline that needs no model; "beats baseline" means the gain is more than two standard errors above zero.</p>
   <div class="tbl"><table><tr><th>Market</th><th>n</th><th>log loss</th><th>baseline</th><th>right side</th><th>gain</th><th>verdict</th></tr>${keys.map(([k,l])=>row(k,l)).join('')}</table></div>
   <p class="small">Baselines: shots and blocks = a negative binomial at the skater's 25-game average (shrunk toward the league) at a line set at his 10-game average, as the books set it; points, assists, goals = a Poisson at his 25-game rate; team total and power-play goals = a Poisson at the team's 20-game rate. ${V.pooled.sog?`Shots on goal, mean absolute error: model ${V.pooled.sog.mae_model} vs his recent average ${V.pooled.sog.mae_recent_avg}.`:''} ${V.pooled.blk?`Blocks: ${V.pooled.blk.mae_model} vs ${V.pooled.blk.mae_recent_avg}.`:''}</p>
   ${keys.map(([k,l])=>cal(k,l)).join('')}
   <p class="small">By season (gain): ${Object.entries(V.by_season||{}).map(([s,S])=>`<b>${(s-1)}-${String(s).slice(2)}</b> `+keys.map(([k,l])=>{ const m=S[k]; return m&&m.n?`${l} ${m.gain>=0?'+':''}${m.gain}`:''; }).filter(Boolean).join(', ')).join('<br>')}</p>`;
})();
(function(){ const C=P.cfg||{}; document.getElementById('method').innerHTML = `<h3>Method</h3>
  <p><b>Data.</b> Every regular-season play since 2021-22 from the sportsdataverse NHL play-by-play releases (shooter, scorer, assists, blocker and the skaters on the ice for every event), refreshed nightly. Lineups, lines and power-play units from DailyFaceoff on game day; a skater listed as out is removed.</p>
  <p><b>Skaters.</b> Shots and blocks are rates per game weighted by recency (half-life ${C.half_life_games} games, last season at ${Math.round((C.prior_season_weight||0)*100)}%) and shrunk toward the league skater at his ice-time level. Points, assists and goals are shares of his team's goals while he played, so tonight's expectation is the team's expected goals from the full game model (goalies, rest, travel, market anchor) times his share: a thinned Poisson, which the data confirm (variance / mean 0.99). Shots and blocks are negative binomial with the measured spread (variance / mean 1.09 and 1.07). A recent change in his ice-time share moves his rates with weight ${C.deploy_weight}.</p>
  <p><b>Teams.</b> Shots and attempts for and against, blocks per opponent attempt, goals for and against, power plays drawn and taken, conversion and kill, each a log ratio to the league shrunk with ${C.k_team} pseudo-games (${C.k_pp} for the power play), with the home effect removed and re-applied for tonight's venue. Power-play goals = Poisson(opportunities x conversion); team totals come from the simulated game, shootout winner credited one goal as the books settle it.</p>
  <p><b>Prices.</b> DraftKings' own lines and odds (The Odds API) are fetched each day in start order while the free plan's budget lasts; a market the book had not posted shows the model's fair line marked *, and the price check prices any line. Nothing here is a guarantee: validated means the model beat a sensible baseline over three seasons, not that every bet wins.</p>`;
  const T=(P.factors||{}).tested||[]; document.getElementById('factors').innerHTML = T.length ? `<h3>Tested in the walk-forward backtest</h3><div class="tbl"><table><tr><th>Change</th><th>Result</th><th></th></tr>${T.map(t=>`<tr><td>${esc(t.name)}</td><td>${esc(t.result)}</td><td>${t.kept?'<span class="verd beats">kept</span>':'<span class="verd none">rejected</span>'}</td></tr>`).join('')}</table></div>` : '';
  document.getElementById('foot').innerHTML = `<p class="small">Gill Sports · NHL props · model ${esc(P.model_version)} · built in ${P.build_seconds}s · <a href="validation.json">validation.json</a> · <a href="factors.json">factors.json</a></p>`; })();
</script>
</body>
</html>
"""


def _esc(x) -> str:
    return str("" if x is None else x).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def static_summary(payload: dict) -> str:
    rows = []
    for g in payload["games"]:
        for side in ("away", "home"):
            S = g["sides"][side]
            top = [s for s in S["skaters"] if s.get("pmf")][:6]
            who = ", ".join(_esc(s["name"]) + f" {s['mean']['sog']:.1f} shots / {s['mean']['pts']:.2f} points / {s['p_goal']*100:.0f}% goal" for s in top)
            rows.append(f"<tr><td>{_esc(g['away'])} @ {_esc(g['home'])}</td><td>{_esc(S['team'])}</td><td>{S['lam_goals']:.2f}</td><td>{S['markets']['lam_ppg']:.2f}</td>"
                        f"<td>{who}</td></tr>")
    return (f'<div id="static" class="static"><h1>Gill Sports: NHL props for {_esc(payload["date"])}</h1><p>{len(payload["games"])} games, data through {_esc(payload.get("data_through"))}, '
            f'generated {_esc(payload.get("generated_utc"))}. Open in a browser for every skater, DraftKings prices, the scanner and the validation.</p>'
            f'<table><thead><tr><th>Game</th><th>Team</th><th>Expected goals</th><th>Expected PP goals</th><th>Top skaters</th></tr></thead><tbody>{"".join(rows)}</tbody></table></div>')


def render(payload: dict, root: str = "../", nhl_href: str = "../", nfl_href: str = "../nfl/") -> str:
    data = json.dumps(payload).replace("</", "<\\/")
    brand = brand_html(root, "props", nhl_href, props_href="#", nfl_href=nfl_href)
    html = (TEMPLATE.replace("__CSS__", BASE_CSS + NFL_CSS + PROPS_CSS + BRAND_CSS).replace("__PAYLOAD__", data).replace("__STATIC__", static_summary(payload))
            .replace("__DATE__", payload["date"]).replace("__BRAND__", brand))
    # the validation files live in docs/props/; archive day pages sit one folder deeper
    html = html.replace('href="validation.json"', f'href="{root}props/validation.json"').replace('href="factors.json"', f'href="{root}props/factors.json"')
    return finish_page(html, root, "props", nhl_href, props_href="#", nfl_href=nfl_href)


def write(payload: dict, path: Path, **kw) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render(payload, **kw), encoding="utf-8")
    return path


__all__ = ["render", "write", "static_summary"]
