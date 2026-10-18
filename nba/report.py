"""The NBA page: one HTML file per day with the payload embedded (docs/nba/days/<date>.html, docs/nba/index.html).

Tabs: Best bets (the research desk first, then the bot's picks and every DraftKings market), Tonight (every game with
DraftKings' lines, the model's numbers, injuries and live scores from ESPN), Players (every projection, lookup),
Results (the leaderboard and the track record) and About.
"""
from __future__ import annotations

import json

from earlygoal.brand import BRAND_CSS, brand_html, finish_page, head_tags
from nfl.report import BASE_CSS, NFL_CSS

NBA_CSS = r"""
.gcard{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:12px 14px;margin-bottom:10px}
.gcard .top{display:flex;justify-content:space-between;gap:10px;align-items:flex-start}
.gcard h3{margin:0;font-size:17px}.gcard .t{font-size:12px;color:var(--dim)}
.gcard .score{font-family:var(--display);font-size:22px;font-weight:800;white-space:nowrap}.gcard .score small{display:block;font-size:10px;letter-spacing:.08em;color:var(--dim);text-transform:uppercase;font-family:var(--body)}
.gcard .lines{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:6px;margin-top:8px}
.gcard .lines div{background:#0a1017;border:1px solid var(--line);border-radius:9px;padding:6px 9px;min-width:0}
.gcard .lines .k{display:block;font-size:9.5px;letter-spacing:.08em;text-transform:uppercase;color:var(--dim)}
.gcard .lines .v{display:block;font-family:var(--display);font-size:18px;font-weight:700;white-space:nowrap}
.gcard .lines .s{display:block;font-size:11px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.gcard .inj{margin-top:8px;font-size:12px;color:var(--muted)}.gcard .inj b{color:var(--text)}.gcard .inj .out{color:var(--red)}.gcard .inj .q{color:var(--amber)}
.gcard details{margin-top:8px}.gcard summary{cursor:pointer;color:var(--ice);font-size:12.5px}
.ptable{overflow-x:auto}.ptable table{width:100%;border-collapse:collapse;font-size:12px;font-variant-numeric:tabular-nums}
.ptable th,.ptable td{padding:4px 6px;border-top:1px solid var(--line);text-align:right;white-space:nowrap}.ptable th:first-child,.ptable td:first-child{text-align:left}
.ptable th{color:var(--dim);font-weight:600;font-size:10.5px;letter-spacing:.06em;text-transform:uppercase;cursor:pointer}
.ptable td.dk{color:var(--ice)}
"""

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Gill Sports · NBA</title>
<meta name="description" content="NBA __DATE__: DraftKings game lines and player props with the model's win chance, the bot's picks and the research desk">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap">
__HEAD__
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
    <button data-tab="tonight">Tonight</button>
    <button data-tab="players">Players</button>
    <button data-tab="results">Results</button>
    <button data-tab="about">About</button>
  </nav>
</div></div>

<div class="wrap">
<div id="banner"></div>
__STATIC__

<section class="tab on" id="tab-best">
  <p class="lead" style="margin-bottom:4px">Every DraftKings market for tonight's games with its win chance, the evidence behind it and whether the price is attractive, fair or poor. The research desk comes first (what the desk read, worked out and chose), then the bot's picks by category, then every priced market.</p>
  <div id="best"></div>
</section>

<section class="tab" id="tab-tonight">
  <div class="livebar" id="livebar"></div>
  <div id="games"></div>
</section>

<section class="tab" id="tab-players">
  <p class="lead">Every player the model projects tonight: minutes, points, rebounds, assists, threes and PRA, with DraftKings' line beside the projection wherever the feed priced it. Tap a column to sort; type a name to look one up.</p>
  <div id="players"></div>
</section>

<section class="tab" id="tab-results">
  <div class="panel" id="today"></div>
  <div class="panel" id="track"></div>
</section>

<section class="tab" id="tab-about">
  <div class="panel" id="method"></div>
  <div class="panel small" id="foot"></div>
</section>
</div>

<script>
const P = __PAYLOAD__;
(function(){ const s=document.getElementById('static'); if(s) s.remove(); })();
const M = P.meta || {}; const BB = P.best_bets || null; const BOT = P.bot || null; const DESK = (BOT && BOT.desk && BOT.desk.ok) ? BOT.desk : null; const DCFG = (BOT && BOT.desk_config) || {};
const BASE = window.NBA_BASE || './';
const byId = {}; P.games.forEach(g=>byId[g.game_id]=g);
const pct = (x,d=1) => x==null ? '–' : (x*100).toFixed(d)+'%';
const esc = s => String(s==null?'':s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const dec2am = d => d==null ? '' : (d>=2 ? '+'+Math.round((d-1)*100) : '-'+Math.round(100/(d-1)));
const evTxt = ev => ev==null ? '–' : `${ev>=0?'+':''}${(ev*100).toFixed(1)}%`;
const BTZ='America/Toronto';
const bIso = s => { s=String(s||''); if(/^\d{4}-\d\d-\d\d \d\d:\d\d UTC$/.test(s)) s=s.replace(' ','T').replace(' UTC','Z'); return new Date(/T\d\d:\d\dZ$/.test(s) ? s.replace('Z',':00Z') : s); };
const bNow = () => new Date().toISOString().slice(0,16)+'Z';
const bKick = s => s ? bIso(s).toLocaleString('en-US',{timeZone:BTZ,weekday:'short',hour:'numeric',minute:'2-digit'})+' ET' : '';
const bStamp = s => { if(!s) return 'not available'; const d=bIso(s); return isNaN(d) ? esc(s) : d.toLocaleString('en-US',{timeZone:BTZ,month:'short',day:'numeric',hour:'numeric',minute:'2-digit'})+' ET'; };
const bAgo = s => { if(!s) return 'not yet'; const m=Math.round((Date.now()-bIso(s))/60000); if(m<1) return 'just now'; if(m<60) return m+' min ago'; const h=Math.round(m/60); if(h<48) return h+' h ago'; return Math.round(h/24)+' days ago'; };
const BKIND = {ml:'Moneyline', spread:'Spread', total:'Game total', pts:'Points', reb:'Rebounds', ast:'Assists', threes:'Threes', pra:'PRA'};
const BGROUPS = [['desk','Research desk'],['bot',"Bot's picks"],['winners','Team winners'],['spreads','Spreads'],['totals','Totals'],['props','Player props'],['model','Model lines']];
const BPRICE = {attractive:['Attractive','pos'], fair:['Fair','mid'], poor:['Poor','neg'], 'no price':['Not in feed','mid']};
const BOARD = ((BB&&BB.ranked)||[]).concat((BOT&&BOT.extra)||[]); const BYID={}; BOARD.forEach(b=>BYID[b.id]=b);
let BF = {grp:DESK?'desk':'bot', kind:'all', game:'all', sort:'p', more:0};
try{ Object.assign(BF, JSON.parse(localStorage.getItem('gs_nba_best')||'{}'), {more:0}); }catch(e){}
const saveBF = () => { try{ localStorage.setItem('gs_nba_best', JSON.stringify({grp:BF.grp, kind:BF.kind, game:BF.game, sort:BF.sort})); }catch(e){} };
let SHOW_COMBINE=false;

// ------------------------------------------------------------- tabs
const tabs=document.getElementById('tabs');
function showTab(name, push){ document.body.dataset.tab=name; document.querySelectorAll('section.tab').forEach(s=>s.classList.toggle('on', s.id==='tab-'+name));
  tabs.querySelectorAll('button').forEach(b=>b.classList.toggle('on', b.dataset.tab===name)); try{localStorage.setItem('gs_nba_tab',name);}catch(e){}
  if(push && history.replaceState) history.replaceState(null,'','#'+name); window.scrollTo({top:0}); }
tabs.querySelectorAll('button').forEach(b=>b.onclick=()=>showTab(b.dataset.tab,true));
(function(){ let h=(location.hash||'').replace('#',''); if(!['best','tonight','players','results','about'].includes(h)){ try{ h=localStorage.getItem('gs_nba_tab')||'best'; }catch(e){ h='best'; } } showTab(h,false); })();

// ------------------------------------------------------------- results of a leg (from the day's box scores)
function legResult(l, g){ const A=g.actual; if(!A) return null; const hs=A.hs, as_=A.as;
  const ou=(v)=> v==null?null:(v>l.line?(l.side==='over'?'hit':'miss'):(v<l.line?(l.side==='over'?'miss':'hit'):'tie'));
  switch(l.kind){
    case 'ml': return (l.side==='home'?hs-as_:as_-hs)>0?'hit':'miss';
    case 'spread': { const m=(l.side==='home'?hs-as_:as_-hs)+l.line; return m>0?'hit':(m===0?'tie':'miss'); }
    case 'total': return ou(hs+as_);
  }
  const team = l.team; const st=((A.players||{})[team]||{})[l.pid]; if(!st){ const byName=Object.values((A.players||{})[team]||{}).find(x=>x.name===l.who); if(!byName) return 'void'; return ou(byName[l.kind]); }
  return ou(st[l.kind]); }

// ------------------------------------------------------------- desk (settings kept on this phone)
function dDefaults(){ const c=DCFG; const sel=c.selection||{}; const w=c.wild_cards||{};
  return {band:[(c.odds_band||[1.35,2.2])[0],(c.odds_band||[1.35,2.2])[1]], minp:Math.round(((sel.min_p||0.52))*100), grades:['A','B','C'].filter(g=>g<=(sel.min_grade||'C')), ev:{measured:true,partial:true,unmeasured:(sel.min_evidence||'unmeasured')==='unmeasured'},
    markets:Object.assign({ml:true,spread:true,total:true,pts:true,reb:true,ast:true,threes:true,pra:true,alts:true}, c.markets||{}), src:{feed:true,draftkings:true,unverified:true}, perGame:sel.max_per_game||3, sort:'p', wild:w.enabled!==false, wband:[(w.odds_band||[2.21,4.5])[0],(w.odds_band||[2.21,4.5])[1]]}; }
let DS = dDefaults(); DS.grades=['A','B','C'];
try{ const sv=JSON.parse(localStorage.getItem('gs_nba_desk')||'null'); if(sv) DS=Object.assign(dDefaults(), sv, {grades: sv.grades||['A','B','C']}); }catch(e){}
const saveDS = () => { try{ localStorage.setItem('gs_nba_desk', JSON.stringify(DS)); }catch(e){} };
function dPass(x, wild){ const band = wild ? DS.wband : DS.band; if(x.odds < band[0] || x.odds > band[1]) return false; if(!wild && x.p*100 < DS.minp) return false; if(!DS.grades.includes(x.grade)) return false; if(!DS.ev[x.evidence]) return false; if(DS.markets[x.kind]===false) return false; if(DS.src[x.odds_source]===false) return false; return true; }
function dFilter(list, wild){ const per={}; const out=[]; const key={p:x=>-x.p, ev:x=>-(x.ev||0), conf:x=>-(x.confidence||0), kick:x=>x.kick}[DS.sort]||(x=>-x.p);
  const rows=list.filter(x=>dPass(x,wild) && (BF.game==='all'||x.game_id===BF.game)).slice().sort((a,c)=>{const ka=key(a),kc=key(c); return ka<kc?-1:(ka>kc?1:0);});
  for(const x of rows){ per[x.game_id]=(per[x.game_id]||0)+1; if(per[x.game_id]>DS.perGame) continue; out.push(x); } return out; }
function dSettings(){ const mk=[['ml','Moneyline'],['spread','Spread'],['total','Total'],['pts','Points'],['reb','Rebounds'],['ast','Assists'],['threes','Threes'],['pra','PRA'],['alts','Alt lines']];
  const chip=(group,k,l,on)=>`<label class="${on?'on':''}"><input type="checkbox" data-grp="${group}" data-k="${k}" ${on?'checked':''}>${l}</label>`;
  const vars=Object.entries(DCFG.variables||{}).map(([k,v])=>`<span class="${v&&v.on!==false?'on':''}" title="${esc((v&&v.label)||k)}">${v&&v.on!==false?'✓':'✗'} ${esc(k.replace(/_/g,' '))}</span>`).join('');
  return `<details class="dset" id="dset"><summary>Desk settings · band ${DS.band[0].toFixed(2)} to ${DS.band[1].toFixed(2)} · min ${DS.minp}% · ${DS.perGame} per game${DS.wild?' · wild cards on':''}</summary>
   <div class="grid">
    <div><label class="f">Odds band (DraftKings decimal)</label><div class="val"><span id="ds-lo">${DS.band[0].toFixed(2)}</span> to <span id="ds-hi">${DS.band[1].toFixed(2)}</span></div><input type="range" id="ds-blo" min="1.01" max="3" step="0.01" value="${DS.band[0]}"><input type="range" id="ds-bhi" min="1.1" max="6" step="0.01" value="${DS.band[1]}"></div>
    <div><label class="f">Minimum desk win chance</label><div class="val"><span id="ds-mp">${DS.minp}</span>%</div><input type="range" id="ds-minp" min="50" max="80" step="1" value="${DS.minp}"></div>
    <div><label class="f">Most selections per game</label><div class="val"><span id="ds-pg">${DS.perGame}</span></div><input type="range" id="ds-per" min="1" max="6" step="1" value="${DS.perGame}"></div>
    <div><label class="f">Sort</label><select id="ds-sort"><option value="p" ${DS.sort==='p'?'selected':''}>Desk win chance</option><option value="ev" ${DS.sort==='ev'?'selected':''}>EV at the price</option><option value="conf" ${DS.sort==='conf'?'selected':''}>Evidence confidence</option><option value="kick" ${DS.sort==='kick'?'selected':''}>Tip-off</option></select></div>
    <div><label class="f">Grades</label><div class="chips2">${['A','B','C'].map(g=>chip('grades',g,'Grade '+g,DS.grades.includes(g))).join('')}</div></div>
    <div><label class="f">Evidence</label><div class="chips2">${['measured','partial','unmeasured'].map(g=>chip('ev',g,g,DS.ev[g])).join('')}</div></div>
    <div><label class="f">Price source</label><div class="chips2">${[['feed','odds feed'],['draftkings','DK checked'],['unverified','unverified']].map(([k,l])=>chip('src',k,l,DS.src[k])).join('')}</div></div>
    <div style="grid-column:1/-1"><label class="f">Markets</label><div class="chips2">${mk.map(([k,l])=>chip('markets',k,l,DS.markets[k]!==false)).join('')}</div></div>
    <div style="grid-column:1/-1"><label class="f">Wild cards</label><div class="chips2">${chip('wild','on','Show wild cards',DS.wild)}</div><div class="val" style="margin-top:6px;font-size:14px">band <span id="ds-wlo">${DS.wband[0].toFixed(2)}</span> to <span id="ds-whi">${DS.wband[1].toFixed(2)}</span></div><input type="range" id="ds-wlo-r" min="1.5" max="6" step="0.01" value="${DS.wband[0]}"><input type="range" id="ds-whi-r" min="2" max="12" step="0.01" value="${DS.wband[1]}"></div>
    <div style="grid-column:1/-1"><label class="f">Variables the desk run checks (from the repo's data/nba/desk_config.json)</label><div class="vars">${vars||'<span>defaults</span>'}</div></div>
   </div>
   <div class="btns"><button type="button" id="ds-reset">Reset to the desk's defaults</button><button type="button" id="ds-copy">Copy config JSON</button></div>
   <p class="note2">These settings filter what you see on this phone and are kept here. The desk's scheduled runs follow <code>data/nba/desk_config.json</code> in the repository: copy the JSON and paste it there (or ask Claude) to change what the desk looks for.</p></details>`; }
function dWire(el){ const q=id=>el.querySelector('#'+id); const rr=()=>{ saveDS(); renderBest(); };
  const bl=q('ds-blo'), bh=q('ds-bhi'); if(bl){ bl.oninput=e=>{ DS.band[0]=Math.min(+e.target.value, DS.band[1]-0.01); q('ds-lo').textContent=DS.band[0].toFixed(2); }; bl.onchange=rr; }
  if(bh){ bh.oninput=e=>{ DS.band[1]=Math.max(+e.target.value, DS.band[0]+0.01); q('ds-hi').textContent=DS.band[1].toFixed(2); }; bh.onchange=rr; }
  const mp=q('ds-minp'); if(mp){ mp.oninput=e=>{ DS.minp=+e.target.value; q('ds-mp').textContent=DS.minp; }; mp.onchange=rr; }
  const pg=q('ds-per'); if(pg){ pg.oninput=e=>{ DS.perGame=+e.target.value; q('ds-pg').textContent=DS.perGame; }; pg.onchange=rr; }
  const wl=q('ds-wlo-r'), wh=q('ds-whi-r'); if(wl){ wl.oninput=e=>{ DS.wband[0]=Math.min(+e.target.value, DS.wband[1]-0.01); q('ds-wlo').textContent=DS.wband[0].toFixed(2); }; wl.onchange=rr; }
  if(wh){ wh.oninput=e=>{ DS.wband[1]=Math.max(+e.target.value, DS.wband[0]+0.01); q('ds-whi').textContent=DS.wband[1].toFixed(2); }; wh.onchange=rr; }
  const so=q('ds-sort'); if(so) so.onchange=e=>{ DS.sort=e.target.value; rr(); };
  el.querySelectorAll('.dset input[type=checkbox]').forEach(cb=>cb.onchange=()=>{ const g=cb.dataset.grp, k=cb.dataset.k; if(g==='grades'){ DS.grades = cb.checked ? [...new Set(DS.grades.concat([k]))] : DS.grades.filter(x=>x!==k); } else if(g==='wild'){ DS.wild=cb.checked; } else { DS[g][k]=cb.checked; } rr(); });
  const rs=q('ds-reset'); if(rs) rs.onclick=()=>{ DS=dDefaults(); DS.grades=['A','B','C']; rr(); };
  const cp=q('ds-copy'); if(cp) cp.onclick=()=>{ const sel=DCFG.selection||{}; const cfg=Object.assign({}, DCFG, {odds_band:[+DS.band[0].toFixed(2), +DS.band[1].toFixed(2)], wild_cards:Object.assign({}, DCFG.wild_cards||{}, {enabled:DS.wild, odds_band:[+DS.wband[0].toFixed(2), +DS.wband[1].toFixed(2)]}), markets:DS.markets, selection:Object.assign({}, sel, {min_p:DS.minp/100, max_per_game:DS.perGame, min_grade:DS.grades.slice().sort().pop()||'C', min_evidence: DS.ev.unmeasured?'unmeasured':(DS.ev.partial?'partial':'measured')}), updated_utc:new Date().toISOString().slice(0,16).replace('T',' ')+' UTC'});
    const txt=JSON.stringify(cfg,null,1); (navigator.clipboard?navigator.clipboard.writeText(txt):Promise.reject()).then(()=>{ cp.textContent='Copied: paste into data/nba/desk_config.json'; },()=>{ prompt('Copy this into data/nba/desk_config.json', txt); }); }; }
function dSrc(list){ return (list||[]).map(x=>`${x.url?`<a href="${esc(x.url)}" target="_blank" rel="noopener">${esc(x.name)}</a>`:esc(x.name)} (${esc(bStamp(x.fetched))})`).join(' · '); }
function dBlock(D){ return `<div class="deskr"><h4>Research desk · ${pct(D.p,0)} to win · grade ${esc(D.grade)} · evidence ${esc(D.evidence)} · confidence ${D.confidence}</h4>
   <p><b>Verdict:</b> ${esc(D.verdict)}</p>
   ${(D.inputs||[]).length?`<p><b>Inputs</b></p><ul>${D.inputs.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
   ${(D.arithmetic||[]).length?`<p><b>Arithmetic</b></p><ul class="ar">${D.arithmetic.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
   ${(D.pros||[]).length?`<p><b>For</b></p><ul class="pr">${D.pros.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
   ${(D.risks||[]).length?`<p><b>Risks</b></p><ul class="ri">${D.risks.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
   <div class="src">Sources: ${dSrc(D.sources)||'none listed'}${D.odds_source?` · DraftKings price ${D.odds!=null?D.odds.toFixed(2):'–'} (${esc(D.odds_source==='feed'?'odds feed':(D.odds_source==='draftkings'?'checked on DraftKings':'not verified'))})`:''}</div></div>`; }
function dCard(x, i){ const g=byId[x.game_id]; const now=bNow(); const started = x.kick && x.kick <= now;
  let r=null; try{ r = started ? legResult({kind:x.kind, side:x.side, line:x.line, team:x.team, pid:x.pid, who:x.who}, g) : null; }catch(e){ r=null; }
  const res = started ? (r && r!=='pending' ? `<span class="res ${r}">${r==='hit'?'won':(r==='miss'?'lost':(r==='tie'?'push':'void'))}</span>` : `<span class="res live">in play</span>`) : '';
  const B=x.board||{}; const bp = B.p!=null ? ` · site ${pct(B.p,0)}${B.p_model!=null?' (model '+pct(B.p_model,0)+')':''}` : ' · not on the site board';
  const osrc = {feed:'odds feed', draftkings:'checked on DraftKings', unverified:'not verified'}[x.odds_source]||'';
  const lineTxt = x.line!=null ? (x.kind==='spread' ? `${x.line>0?'+':''}${x.line}` : `${x.side} ${x.line}`) : (x.kind==='ml'?'moneyline':'');
  return `<article class="bb desk"><div class="top"><span class="rk">${i}</span><div class="ti"><b>${esc(x.label)}<span class="gr ${esc(x.grade)}">${esc(x.grade)}</span>${res}</b><span class="t">${esc(x.mu)} · ${esc(bKick(x.kick))} · ${esc(BKIND[x.kind]||x.kind)}${lineTxt?' · line '+esc(lineTxt):''}</span></div>
   <div class="evb pos">${pct(x.p,0)}<span class="k">Desk win chance</span></div></div>
   <div class="three"><div><span class="k">DraftKings price</span><span class="v ${x.ev>=0.02?'pos':(x.ev>=-0.03?'mid':'neg')}">${x.odds.toFixed(2)}</span><span class="s">${dec2am(x.odds)} · ${esc(osrc)} · EV at the desk's chance ${evTxt(x.ev)}</span></div>
     <div><span class="k">Evidence</span><span class="v"><span class="cf ${x.evidence==='measured'?'high':(x.evidence==='partial'?'medium':'low')}">${esc(x.evidence)}</span> ${x.confidence}</span><span class="s">fair odds ${x.fair_odds.toFixed(2)}${bp}</span></div>
     <div><span class="k">Biggest risk</span><span class="v" style="font-size:12.5px;white-space:normal;font-family:var(--body);font-weight:500;color:#ffd37a">${esc((x.risks||[])[0]||'ordinary variance')}</span></div></div>
   <div class="brow"><details class="books"><summary title="Verdict, inputs, arithmetic, risks and sources">Full write-up</summary>${dBlock(x)}</details></div></article>`; }
function dAlerts(D){ const now=bNow(); const rows=(D.alerts||[]).filter(a=>a.kick>now && (BF.game==='all'||a.game_id===BF.game)); if(!rows.length) return '';
  return `<div class="alertbar"><b>🚨 DraftKings moved against ${rows.length} desk pick${rows.length===1?'':'s'} since the desk priced them.</b> Re-check before betting.<ul>${rows.map(a=>`<li>${esc(a.label)} (${esc(a.mu)}): ${esc(a.why)}${a.fetched?' · feed '+esc(bStamp(a.fetched)):''}</li>`).join('')}</ul></div>`; }
function dHot(){ const H=(BOT&&BOT.hot)||{}; const now=bNow(); const mv=(H.movers||[]).filter(m=>m.kick>now && (BF.game==='all'||m.game_id===BF.game)); const ed=(H.edges||[]).filter(e=>e.kick>now); const fd=(H.fades||[]).filter(e=>e.kick>now);
  const row=m=>`<div class="row"><span>${esc(m.label)}</span><span><span class="hot">🔥 ${esc(m.hot)}</span> · <span class="cold">🧊 ${esc(m.cold)}</span></span></div>`;
  const erow=e=>`<div class="row"><span>${esc(e.label)} <span style="color:var(--dim)">${esc(e.mu)}</span></span><span class="mv ${e.gap>=0?'hot':'cold'}">desk ${pct(e.desk,0)} vs mkt ${pct(e.market,0)}</span></div>`;
  return `<h2>What's hot, what's not</h2><div class="hotgrid"><div class="hotbox"><h3>DraftKings line moves since the opener</h3>${mv.length?mv.slice(0,10).map(row).join(''):'<div class="row"><span style="color:var(--dim)">Line moves appear once the day has two line pulls (morning and pre-tip).</span></div>'}</div>
   <div class="hotbox"><h3>Desk vs market: biggest edges and fades</h3>${ed.length?ed.slice(0,6).map(erow).join(''):'<div class="row"><span style="color:var(--dim)">No desk selection on a priced market yet.</span></div>'}${fd.length&&fd[0].gap<0?`<h3 style="margin-top:8px">Where the desk is below the market</h3>${fd.map(erow).join('')}`:''}</div></div>`; }
function pFind(q){ q=(q||'').trim().toLowerCase(); if(q.length<2) return []; const out=[];
  for(const g of P.games) for(const side of ['home','away']) for(const x of ((g.props||{})[side]||[])) if((x.name||'').toLowerCase().includes(q)) out.push({x, g, team:g[side], side});
  return out.slice(0,6); }
function pCard(o){ const x=o.x, g=o.g; const opp=o.side==='home'?g.away:g.home; const now=bNow();
  const inj=(((g.injuries||{})[o.team])||[]).find(i=>i.id===x.id||i.name===x.name);
  const lines = BOARD.filter(b=>b.pid===x.id && b.game_id===g.game_id && b.odds);
  const desk = DESK ? (DESK.selections||[]).concat(DESK.wild_cards||[]).filter(s=>s.who===x.name && s.game_id===g.game_id) : [];
  const kv=[['minutes', x.minutes],['games', x.games]].concat(['pts','reb','ast','threes','pra'].map(k=>[k, `${x.stats[k].mean}${x.stats[k].dk?' · DK '+x.stats[k].dk.line:''}`]));
  const last=(x.last||[]).slice(-5).map(r=>`${r.pts}/${r.reb}/${r.ast} in ${Math.round(r.min)} min vs ${r.opp}`).join(' · ');
  return `<div class="pcard"><h3>${esc(x.name)} <span class="sub">${esc(o.team)} ${esc(x.pos||'')} · vs ${esc(opp)} · ${esc(bKick(g.tip_utc))}</span></h3>
    ${inj?`<div class="warn" style="color:var(--amber);font-size:12.5px">⚠ Injury report: ${esc(inj.status||'')}${inj.injury?', '+esc(inj.injury):''}${inj.detail?' ('+esc(inj.detail)+')':''}</div>`:''}
    <div class="kv">${kv.map(([k,v])=>`<div><span class="k">${esc(k)}</span><span class="v">${esc(String(v))}</span></div>`).join('')}</div>
    ${last?`<ul><li><b>Last games (pts/reb/ast):</b> ${esc(last)}</li></ul>`:''}
    ${lines.length?`<ul>${lines.map(b=>`<li>${esc(b.label)} · DK ${b.odds.toFixed(2)} · site ${pct(b.p,0)}${b.desk?` · <b style="color:#ffd37a">desk ${pct(b.desk.p,0)} ${esc(b.desk.grade)}</b>`:''}</li>`).join('')}</ul>`:'<ul><li style="color:var(--dim)">No DraftKings prop for him in tonight\'s feed.</li></ul>'}
    ${desk.length?`<ul>${desk.map(s=>`<li><b style="color:#ffd37a">★ Desk:</b> ${esc(s.label)} ${pct(s.p,0)} @ ${s.odds.toFixed(2)} · ${esc(s.verdict)}</li>`).join('')}</ul>`:''}</div>`; }
function dSearch(){ return `<h2>Player lookup</h2><div class="psearch"><input id="ps-q" type="search" placeholder="Type a player's name (tonight's games)" value="${esc(DS.q||'')}" autocomplete="off"></div><div id="ps-out">${(DS.q&&DS.q.length>=2)?(pFind(DS.q).map(pCard).join('')||'<p class="empty">No player by that name tonight.</p>'):''}</div>`; }
function bDesk(){ const D=DESK; let h=dSettings();
  if(!D){ h += `<p class="empty">No research desk file for tonight yet. The desk runs every game day in the afternoon (and a second pass before the late games).</p>`; return h + dHot() + dSearch(); }
  const now=bNow(); h += dAlerts(D);
  const all=(D.selections||[]); const rows=dFilter(all,false); const up=rows.filter(x=>x.kick>now), done=rows.filter(x=>x.kick<=now);
  const hidden = all.filter(x=>x.kick>now && (BF.game==='all'||x.game_id===BF.game)).length - up.length;
  h += `<div class="deskhead"><h2>★ Research desk · ${up.length} selection${up.length===1?'':'s'} to play${hidden>0?` <small style="color:var(--dim);font-weight:500">(${hidden} hidden by your settings)</small>`:''}</h2>
    <p>${esc(D.analyst||'Research desk')} read the day's news (injury reports, shootaround notes, rotations, line moves) and wrote every selection up with its inputs, its arithmetic and its risks. Ranked by ${{p:"the desk's own win chance",ev:'EV at the DraftKings price',conf:'evidence confidence',kick:'tip-off'}[DS.sort]||"the desk's own win chance"}; DraftKings prices ${DS.band[0].toFixed(2)} to ${DS.band[1].toFixed(2)}. The desk's chance is a judgment, not a model: its record is graded on its own line in Results.</p>
    ${D.summary?`<p>${esc(D.summary)}</p>`:''}<p class="st">Desk run ${esc(bStamp(D.generated))} (${esc(bAgo(D.generated))}) · model run ${esc(bStamp(P.generated_utc))}</p></div>`;
  h += up.length ? up.map((x,i)=>dCard(x,i+1)).join('') : `<p class="empty">No desk selection passes your settings for the games still to play.</p>`;
  if(DS.wild){ const w=dFilter(D.wild_cards||[], true).filter(x=>x.kick>now); h += `<h2>🃏 Wild cards <small style="color:var(--dim);font-size:13px;font-weight:500">longer prices ${DS.wband[0].toFixed(2)} to ${DS.wband[1].toFixed(2)}, smaller stakes</small></h2>`;
    h += w.length ? w.map((x,i)=>dCard(x,i+1).replace('class="bb desk','class="bb desk wild')).join('') : `<p class="empty">No wild card tonight${(D.wild_cards||[]).length?' passes your settings':''}.</p>`; }
  if(done.length) h += `<div class="bbsep">Already tipped off</div>` + done.map((x,i)=>dCard(x,up.length+i+1)).join('');
  h += dHot(); h += dSearch();
  const dec=(D.declined||[]); if(dec.length) h += `<h2>Looked at and declined</h2><table class="decl"><thead><tr><th>Candidate</th><th>Why not</th></tr></thead><tbody>${dec.map(x=>`<tr><td>${esc(x.label)}</td><td>${esc(x.why)}</td></tr>`).join('')}</tbody></table>`;
  const gn=Object.entries(D.games||{}).map(([gid,v])=>[byId[gid],v]).filter(([g])=>g).sort((a,c)=>(a[0].tip_utc||'').localeCompare(c[0].tip_utc||''));
  if(gn.length) h += `<h2>Game notes</h2>` + gn.map(([g,v])=>`<details class="gnotes"><summary>${esc(g.away)} @ ${esc(g.home)} · ${esc(bKick(g.tip_utc))}</summary>${(v.injuries||[]).length?`<ul>${v.injuries.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}${(v.notes||[]).length?`<ul>${v.notes.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}${(v.sources||[]).length?`<div class="small" style="color:var(--dim);margin:0 0 8px">Sources: ${dSrc(v.sources)}</div>`:''}</details>`).join('');
  return h; }

// ------------------------------------------------------------- board cards
function bCard(b, i){ const A=b.analysis||{}; const pr=BPRICE[b.price]||BPRICE.fair; const cf=b.conf||{score:50,label:'medium'}; const J=b.judge;
  const lineTxt = b.line!=null ? (b.kind==='spread' ? `${b.line>0?'+':''}${b.line}` : `${b.side} ${b.line}`) : (b.kind==='ml'?'moneyline':'');
  const books=((b.inputs||{}).books||[]);
  return `<article class="bb ${b.price==='attractive'?'good':''}"><div class="top"><span class="rk">${i}</span><div class="ti"><b>${esc(b.label)}</b><span class="t">${esc(b.mu)} · ${esc(bKick(b.kick))} · ${esc(b.market)}${lineTxt?' · line '+esc(lineTxt):''}</span></div><div class="evb pos">${pct(b.p,0)}<span class="k">Win chance</span></div></div>
   <div class="three"><div><span class="k">Model probability</span><span class="v">${pct(b.p)}</span><span class="s">fair odds ${b.fair_odds?b.fair_odds.toFixed(2):'–'}${b.p_model!=null&&b.p_market!=null?` · model ${pct(b.p_model,0)}, market ${pct(b.p_market,0)}`:(b.p_market!=null?' · market':' · model only')}</span></div>
     <div><span class="k">Evidence confidence</span><span class="v"><span class="cf ${cf.label}">${cf.label}</span> ${cf.score}</span><span class="s">${b.books||0} book${b.books===1?'':'s'} · rates data quality, not win likelihood</span></div>
     <div><span class="k">DraftKings price</span><span class="v ${pr[1]}">${pr[0]}</span><span class="s">${b.odds!=null?`${b.odds.toFixed(2)} (${dec2am(b.odds)}) · EV ${evTxt(b.ev)}`:'not in the feed: check DraftKings'}</span></div></div>
   ${b.desk?`<div class="chk"><span class="c ok">★ Research desk ${pct(b.desk.p,0)} · grade ${esc(b.desk.grade)}</span></div>`:''}
   ${J?`<div class="chk">${J.checks.map(c=>`<span class="c ${c.ok===true?'ok':(c.ok===false?'bad':'na')}" title="${esc(c.txt)}">${c.ok===true?'✓':(c.ok===false?'✗':'·')} ${esc(c.name)}</span>`).join('')}</div>`:''}
   <div class="brow"><details class="books"><summary>Research, risk, formulas and every book's price</summary>${b.desk?dBlock(b.desk):''}
     ${J?`<div class="chkl"><b>Bot's checks (score ${J.score.toFixed(2)})</b><ul>${J.checks.map(c=>`<li class="${c.ok===true?'ok':(c.ok===false?'bad':'na')}">${c.ok===true?'✓':(c.ok===false?'✗':'·')} <b>${esc(c.name)}:</b> ${esc(c.txt)}</li>`).join('')}</ul></div>`:''}
     ${A.proj?`<div class="proj"><b>Projection:</b> ${esc(A.proj)}</div>`:''}${(A.reasons||[]).length?`<ul class="rs">${A.reasons.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:''}
     ${A.risk?`<div class="risk"><b>Biggest risk:</b> ${esc(A.risk)}</div>`:''}${(A.formula||[]).length?`<div class="fm"><b style="color:var(--text)">Formulas</b>${A.formula.map(x=>`<p>${esc(x)}</p>`).join('')}</div>`:''}
     ${(A.limits||[]).length?`<div class="lim"><b>Limits:</b> ${A.limits.map(esc).join(' · ')}</div>`:''}
     ${books.length?`<div class="bt"><table><tr><th>Book</th><th>Line</th><th>over</th><th>under</th></tr>${books.map(x=>`<tr class="${x.book==='DraftKings'?'dk':''}"><td>${esc(x.book)}</td><td>${x.line!=null?x.line:'–'}</td><td>${x.over!=null?x.over.toFixed(2):'–'}</td><td>${x.under!=null?x.under.toFixed(2):'–'}</td></tr>`).join('')}</table></div>`:''}
     <div class="stamps">Sources: model ${bStamp((A.stamps||{}).model)} · props feed ${bStamp((A.stamps||{}).odds)}</div></details></div></article>`; }
function bCombine(C){ const R=(BOT||{}).rules||{}; if(!C||!C.n) return `<p class="empty">No combined top ${R.legs||5}: fewer than ${R.legs||5} qualifying legs tonight.</p>`; const band=C.odds_band||[1.35,2.2];
  return `<article class="bb parlay"><div class="top"><span class="rk">${C.n}</span><div class="ti"><b>The bot's top ${C.n} tonight</b><span class="t">highest-scoring legs across the lists · one per game · DraftKings ${band[0]} to ${band[1]}</span></div><div class="evb ${C.ev>=0?'pos':'neg'}">${C.odds.toFixed(2)}<span class="k">combined odds</span></div></div>
   <div class="bt"><table><tr><th>#</th><th class="lbl">Leg</th><th>DK</th><th>Win</th></tr>${C.legs.map((l,i)=>`<tr><td>${i+1}</td><td class="lbl"><b>${esc(l.label)}</b><br><span style="color:var(--dim)">${esc(l.mu)} · ${esc(bKick(l.kick))}</span><br><span style="color:var(--muted)">${esc(l.basis)}</span></td><td>${l.odds.toFixed(2)}</td><td>${pct(l.p,0)}</td></tr>`).join('')}</table></div>
   <div class="why">Singles or a parlay: all ${C.n} together win about one time in ${C.prob>0?Math.round(1/C.prob):'–'} (${pct(C.prob,1)}). Check each DraftKings price before betting.</div></article>`; }
function bBot(){ const B=BOT||{}; const now=bNow(); const cats=B.cats||{};
  let h=`<p class="note">The bot runs an analyst's checks on every priced bet: model vs market, availability, sample size, recent form against the line, the price. Each list shows its best by that judgment. Open a card for the full reasoning.</p>`;
  h += `<div style="margin:6px 0 12px"><button type="button" class="combine" id="combine">${SHOW_COMBINE?'Hide the top 5':'Combine into the top 5'}</button></div>`; if(SHOW_COMBINE) h += bCombine(B.combine);
  for(const c of (B.rules||{}).categories||[]){ const cat=cats[c.key]; if(!cat) continue; const bs=(cat.ids||[]).map(i=>BYID[i]).filter(b=>b && b.kick>now && (BF.game==='all'||b.game_id===BF.game));
    h += `<h2>${esc(cat.label)} <small style="color:var(--dim);font-size:13px;font-weight:500">best ${cat.n}</small></h2>`; h += bs.length ? bs.map((b,i)=>bCard(b,i+1)).join('') : `<p class="empty">Nothing passes the checks in this view${['points','rebounds','assists','threes','pra'].includes(c.key)?' (props are priced on two games a night within the free credits; the rest show as model lines)':''}.</p>`; }
  return h; }
function renderBest(){ const el=document.getElementById('best'); if(!el) return; const now=bNow();
  const up=BOARD.filter(b=>b.kick && b.kick>now); const games=P.games.filter(g=>g.tip_utc && g.tip_utc>now).map(g=>({game_id:g.game_id, mu:`${g.away} @ ${g.home}`, kick:g.tip_utc}));
  if(!DESK && BF.grp==='desk') BF.grp='bot';
  if(BF.game!=='all' && !games.find(g=>g.game_id===BF.game)) BF.game='all';
  let rows = up.filter(b => (BF.grp==='model' ? !b.odds : (b.group===BF.grp && !!b.odds)) && (BF.kind==='all'||b.kind===BF.kind) && (BF.game==='all'||b.game_id===BF.game));
  const key={p:b=>-b.p, ev:b=>-(b.ev==null?-9:b.ev), conf:b=>-((b.conf||{}).score||0)}[BF.sort]||(b=>-b.p); rows.sort((a,c)=>key(a)-key(c));
  const kinds=[...new Set(rows.map(b=>b.kind))];
  const stats=`<div class="bbhead"><span><b>${up.filter(b=>b.odds).length}</b> DraftKings markets across <b>${games.length}</b> games</span><span><b>${up.filter(b=>b.price==='attractive').length}</b> attractively priced</span><span>${esc(P.date)}</span></div>`;
  const fresh=`<p class="note"><b>Data as of (ET):</b> DraftKings game lines ${bStamp(P.generated_utc)} (ESPN) · player props ${bStamp(BB&&BB.odds_fetched)} · model ${bStamp(P.generated_utc)}${M.credits_remaining!=null?' · '+M.credits_remaining+' Odds API credits left this month':''}.</p>`;
  const bar=`<div class="bbbar"><div class="chips" id="bb-grp">${BGROUPS.filter(([k])=>k==='desk'?!!DESK:(k==='bot'?!!BOT:true)).map(([k,l])=>`<button type="button" data-g="${k}" class="${BF.grp===k?'on':''}">${k==='desk'?'★ ':''}${l} <small>${k==='desk'?(DESK.selections||[]).filter(x=>x.kick>now).length:(k==='bot'?Object.values((BOT||{}).cats||{}).reduce((a,c)=>a+(c.ids||[]).length,0):(k==='model'?up.filter(b=>!b.odds).length:up.filter(b=>b.group===k&&b.odds).length))}</small></button>`).join('')}</div>
    <select id="bb-kind" aria-label="Market"><option value="all">Every market</option>${kinds.map(k=>`<option value="${k}" ${BF.kind===k?'selected':''}>${esc(BKIND[k]||k)}</option>`).join('')}</select>
    <select id="bb-game" aria-label="Game"><option value="all">Every game</option>${games.map(g=>`<option value="${g.game_id}" ${BF.game===g.game_id?'selected':''}>${esc(g.mu)} · ${esc(bKick(g.kick))}</option>`).join('')}</select>
    <select id="bb-sort" aria-label="Sort"><option value="p" ${BF.sort==='p'?'selected':''}>Sort: win chance</option><option value="conf" ${BF.sort==='conf'?'selected':''}>Sort: evidence</option><option value="ev" ${BF.sort==='ev'?'selected':''}>Sort: price (EV)</option></select></div>`;
  const nShow=BF.more||15; const shown=rows.slice(0,nShow); let h;
  if(BF.grp==='desk') h=bDesk(); else if(BF.grp==='bot') h=bBot();
  else { h = rows.length ? shown.map((b,i)=>bCard(b,i+1)).join('') : `<p class="empty">${up.length?'Nothing in this view.':'No priced market for upcoming games yet; lines arrive in the morning, props before the first tip.'}</p>`;
    if(BF.grp==='model') h = `<p class="note">Props the free credits did not price tonight: the model's own line and chance, compare DraftKings' line by hand.</p>` + h;
    if(rows.length>shown.length) h += `<div style="text-align:center;margin-top:8px"><button type="button" class="rbtn" style="margin:0" id="bb-more">show ${Math.min(25, rows.length-shown.length)} more of ${rows.length}</button></div>`; }
  el.innerHTML = stats + fresh + bar + `<div class="bbl">${h}</div>`;
  el.querySelectorAll('#bb-grp button').forEach(x=>x.onclick=()=>{ BF.grp=x.dataset.g; BF.kind='all'; BF.more=0; saveBF(); renderBest(); });
  const ks=document.getElementById('bb-kind'); if(ks) ks.onchange=e=>{ BF.kind=e.target.value; BF.more=0; saveBF(); renderBest(); };
  const gsel=document.getElementById('bb-game'); if(gsel) gsel.onchange=e=>{ BF.game=e.target.value; BF.more=0; saveBF(); renderBest(); };
  const ss=document.getElementById('bb-sort'); if(ss) ss.onchange=e=>{ BF.sort=e.target.value; BF.more=0; saveBF(); renderBest(); };
  const mb=document.getElementById('bb-more'); if(mb) mb.onclick=()=>{ BF.more=nShow+25; renderBest(); };
  const cb=document.getElementById('combine'); if(cb) cb.onclick=()=>{ SHOW_COMBINE=!SHOW_COMBINE; renderBest(); };
  if(BF.grp==='desk'){ dWire(el); const ps=el.querySelector('#ps-q'); if(ps){ ps.oninput=()=>{ DS.q=ps.value; saveDS(); const o=el.querySelector('#ps-out'); if(o) o.innerHTML = DS.q.length>=2 ? (pFind(DS.q).map(pCard).join('')||'<p class="empty">No player by that name tonight.</p>') : ''; }; } } }

// ------------------------------------------------------------- tonight
let LIVE={};
function gCard(g){ const L=g.lines||{}; const m=g.model||{}; const r=g.research||{}; const lv=LIVE[g.espn_id]||g.live||null; const A=g.actual;
  const score = A ? `<div class="score">${g.away} ${A.as} · ${g.home} ${A.hs}<small>final</small></div>` : (lv ? `<div class="score">${g.away} ${lv.as} · ${g.home} ${lv.hs}<small>${esc(lv.status||'live')}</small></div>` : `<div class="score">${pct(m.home_win,0)}<small>${g.home} wins</small></div>`);
  const inj=['away','home'].map(s=>{ const rows=((g.injuries||{})[g[s]]||[]); if(!rows.length) return ''; return `<div><b>${g[s]}:</b> ${rows.slice(0,8).map(i=>`<span class="${/out|doubtful/i.test(i.status||'')?'out':'q'}">${esc(i.name)} ${esc(i.status||'')}${i.injury?' ('+esc(i.injury)+')':''}</span>`).join(', ')}</div>`; }).join('');
  const sp = L.spread!=null ? `${g.home} ${L.spread>0?'+':''}${L.spread}` : 'no line';
  return `<div class="gcard"><div class="top"><div><h3>${g.away} @ ${g.home}</h3><div class="t">${esc(bKick(g.tip_utc))}${g.venue?' · '+esc(g.venue):''}</div></div>${score}</div>
   <div class="lines"><div><span class="k">DraftKings spread</span><span class="v">${esc(sp)}</span><span class="s">model margin ${g.home} ${m.margin>0?'+':''}${m.margin} · cover ${pct((g.markets||{}).spread?g.markets.spread.home_cover:null,0)}</span></div>
     <div><span class="k">Total</span><span class="v">${L.total!=null?L.total:'–'}</span><span class="s">model ${m.total} · over ${pct((g.markets||{}).over,0)} · pace ${m.pace}</span></div>
     <div><span class="k">Moneyline</span><span class="v">${L.home_ml?L.home_ml.toFixed(2):'–'} / ${L.away_ml?L.away_ml.toFixed(2):'–'}</span><span class="s">home / away · model ${pct(m.home_win,0)} ${g.home}</span></div></div>
   <div class="inj"><b>Ratings:</b> ${g.home} ${r.home?`${r.home.ortg} / ${r.home.drtg}, pace ${r.home.pace}, ${r.home.record}`:'–'} · ${g.away} ${r.away?`${r.away.ortg} / ${r.away.drtg}, pace ${r.away.pace}, ${r.away.record}`:'–'}</div>
   ${inj?`<div class="inj">${inj}</div>`:''}</div>`; }
function renderGames(){ const el=document.getElementById('games'); el.innerHTML = P.games.length ? P.games.map(gCard).join('') : '<p class="empty">No NBA games on this date.</p>';
  const ds=document.getElementById('dayslot'); if(ds) ds.innerHTML = `<span class="lbl2">Day</span> ${esc(P.date)} <span class="pub">published ${esc(bStamp(P.generated_utc))}</span>`; }
async function refreshLive(){ try{ const d=new Date(P.date+'T12:00:00'); const r=await fetch(`https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=${P.date.replace(/-/g,'')}`); const j=await r.json();
  for(const ev of j.events||[]){ const c=(ev.competitions||[])[0]||{}; const home=(c.competitors||[]).find(x=>x.homeAway==='home')||{}; const away=(c.competitors||[]).find(x=>x.homeAway==='away')||{}; const st=(ev.status||{}).type||{};
    if(st.state!=='pre') LIVE[ev.id]={hs:+home.score, as:+away.score, status:st.shortDetail||st.name, final:!!st.completed}; }
  renderGames(); document.getElementById('livebar').innerHTML = `<span class="small">Live scores from ESPN · ${new Date().toLocaleTimeString('en-US',{timeZone:BTZ,hour:'numeric',minute:'2-digit'})} ET</span>`; }catch(e){} }

// ------------------------------------------------------------- players
let PS={sort:'minutes', q:''};
function renderPlayers(){ const el=document.getElementById('players'); const rows=[];
  for(const g of P.games) for(const side of ['home','away']) for(const x of ((g.props||{})[side]||[])) rows.push({x, g, team:g[side], opp:side==='home'?g.away:g.home});
  const q=(PS.q||'').toLowerCase(); const list=rows.filter(r=>!q||r.x.name.toLowerCase().includes(q)||r.team.toLowerCase()===q);
  const key=PS.sort; list.sort((a,c)=> (key==='minutes'?c.x.minutes-a.x.minutes:(key==='name'?a.x.name.localeCompare(c.x.name):(c.x.stats[key]||{}).mean-(a.x.stats[key]||{}).mean)));
  const cell=(x,k)=>{ const s=x.stats[k]||{}; return `<td>${s.mean!=null?s.mean.toFixed(1):'–'}${s.dk?`<br><span class="dk">DK ${s.dk.line}</span>`:''}</td>`; };
  el.innerHTML = `<div class="psearch"><input id="pl-q" type="search" placeholder="Player or team" value="${esc(PS.q)}"></div><div class="ptable"><table><tr><th data-k="name">Player</th><th>Game</th><th data-k="minutes">Min</th><th data-k="pts">Pts</th><th data-k="reb">Reb</th><th data-k="ast">Ast</th><th data-k="threes">3PM</th><th data-k="pra">PRA</th></tr>
    ${list.slice(0,120).map(r=>`<tr><td>${esc(r.x.name)} <span style="color:var(--dim)">${esc(r.team)} ${esc(r.x.pos||'')}${r.x.q?' ⚠':''}</span></td><td>${esc(r.g.away)}@${esc(r.g.home)}</td><td>${r.x.minutes}</td>${cell(r.x,'pts')}${cell(r.x,'reb')}${cell(r.x,'ast')}${cell(r.x,'threes')}${cell(r.x,'pra')}</tr>`).join('')}</table></div>${list.length>120?`<p class="small">${list.length-120} more: narrow the search.</p>`:''}`;
  el.querySelectorAll('th[data-k]').forEach(th=>th.onclick=()=>{ PS.sort=th.dataset.k; renderPlayers(); });
  const qi=el.querySelector('#pl-q'); qi.oninput=()=>{ PS.q=qi.value; renderPlayers(); const n=el.querySelector('#pl-q'); n.focus(); n.setSelectionRange(n.value.length,n.value.length); }; }

// ------------------------------------------------------------- results
function renderResults(){ const t={}; const PK={desk_best:'Desk best picks', desk:'Research desk', desk_wild:'Desk wild cards', bot:"Bot's picks", market:'DraftKings favourites'};
  for(const [k,lst] of Object.entries(P.picks||{})){ for(const x of lst){ const g=byId[x.game_id]; if(!g||!g.actual) continue; const leg={kind:x.market, side:x.side, line:x.market==='spread'?(x.side==='home'?x.line:-x.line):x.line, team:x.team, pid:x.id, who:x.player}; const r=legResult(leg,g); if(!r||r==='void') continue; t[k]=t[k]||{hit:0,miss:0,tie:0}; t[k][r]++; } }
  document.getElementById('today').innerHTML = `<h3>${esc(P.date)}: graded from the box scores</h3>${Object.keys(t).length?`<div class="tbl"><table><tr><th>Line</th><th>won</th><th>lost</th><th>push</th></tr>${Object.entries(t).map(([k,v])=>`<tr><td>${esc(PK[k]||k)}</td><td>${v.hit}</td><td>${v.miss}</td><td>${v.tie}</td></tr>`).join('')}</table></div>`:'<p>Nothing decided yet tonight. Results fill in from ESPN after each game.</p>'}`;
  fetch(BASE+'scorecard.json').then(r=>r.json()).then(sc=>{ const LB=(sc.leaderboard||[]).filter(r=>r.n); const S=sc.summary||{};
    document.getElementById('track').innerHTML = `<h3>Leaderboard · who is actually winning</h3><p class="small">One unit per pick at the DraftKings price shown before tip-off, every published day. Judge after 300 picks, not 30.</p>${LB.length?`<div class="tbl lb"><table><tr><th>Line</th><th>picks</th><th>won</th><th>lost</th><th>push</th><th>rate</th><th>units</th><th>ROI</th></tr>${LB.map(r=>`<tr><td><b>${esc(r.label)}</b></td><td>${r.n}</td><td>${r.won}</td><td>${r.lost}</td><td>${r.push}</td><td>${r.rate!=null?pct(r.rate):'–'}</td><td class="${(r.units||0)>=0?'pos':'neg'}">${(r.units||0)>=0?'+':''}${(r.units||0).toFixed(2)}</td><td class="${(r.roi||0)>=0?'pos':'neg'}">${r.roi!=null?evTxt(r.roi):'–'}</td></tr>`).join('')}</table></div>`:'<p>No graded pick yet.</p>'}<p class="small">updated ${esc(sc.updated_utc||'')}</p>`; })
  .catch(()=>{ document.getElementById('track').innerHTML='<h3>Leaderboard</h3><p>Not available yet.</p>'; }); }

// ------------------------------------------------------------- about
function renderAbout(){ const L=M.league||{};
  document.getElementById('method').innerHTML = `<h3>How the numbers are made</h3>
  <p><b>Data.</b> ESPN box scores for every game (this season and last), ESPN's injury report, and DraftKings' game lines from ESPN; player props from The Odds API for two games a night inside the free plan's credits (the rest show as model lines).</p>
  <p><b>Teams.</b> Points per 100 possessions scored and allowed (possessions = FGA − OREB + TOV + 0.44 FTA) and pace, exponentially weighted over the season (half-life 15 games), adjusted for the opponent and shrunk toward the league; last season counts about a third per game. Expected points = pace × offense × opponent defense ÷ league; home court +${(DCFG&&DCFG.home_court)||2.3}. Final margin ~ N(margin, 12.6), total ~ N(total, 18.5). League tonight: offensive rating ${L.ortg}, pace ${L.pace}.</p>
  <p><b>Players.</b> Minutes from the last games (half-life 8) shrunk toward the season average and trimmed when the spread says blowout; per-minute rates for points, rebounds, assists, threes and PRA shrunk toward last season's or the position's; scaled by the game's pace and (for points) the opponent's defensive rating. Spread of outcomes from the player's own game-to-game variance. P(over) = Φ((mean − line) ÷ sd).</p>
  <p><b>Best bets.</b> Props: the market's vig-free consensus over the books quoting the line, moved onto DraftKings' line, nudged by the model by at most 5 points. Game lines: DraftKings' price with the vig removed, the model's chance beside it. The bot's checks: model vs market, availability, sample size, recent form against the line, the price. The research desk is a separate Claude session that reads the day's news and writes its selections up; it never edits the model's numbers.</p>
  <p><b>Limits.</b> No lineup-level model yet: when a starter sits, the players who inherit his minutes are under-projected until their games show it. Early in the season last season's rates carry most of the weight. The market already prices most of this, which is why props follow the consensus.</p>`;
  document.getElementById('foot').innerHTML = `Model ${esc(M.model_version)} · generated ${esc(P.generated_utc)} in ${M.seconds}s · ${M.games_fit} games fitted · <a href="${BASE}days/${P.date}.json">payload JSON</a> · <a href="https://github.com/Moneyg604/nhl-early-goal/tree/main/nba">model source code</a>`; }

renderBest(); renderGames(); renderPlayers(); renderResults(); renderAbout();
document.getElementById('fab').onclick=()=>{ const f=document.getElementById('fab'); f.classList.add('spin'); refreshLive().finally(()=>setTimeout(()=>f.classList.remove('spin'),400)); };
refreshLive(); setInterval(()=>{ const now=Date.now(); const near=P.games.some(g=>{ const k=g.tip_utc?bIso(g.tip_utc).getTime():0; return k && now>k-15*60000 && now<k+4*3600000; }); if(near && document.visibilityState==='visible') refreshLive(); }, 30000);
</script>
</body>
</html>
"""


def static_summary(p: dict) -> str:
    rows = []
    for g in p["games"]:
        L = g.get("lines") or {}; m = g.get("model") or {}
        rows.append(f"<tr><td>{g['away']} @ {g['home']}</td><td>{g.get('tip_utc')}</td><td>{g['home']} {L.get('spread')}</td><td>{L.get('total')}</td><td>{m.get('home_win', 0)*100:.0f}% {g['home']}</td><td>{m.get('margin')}</td><td>{m.get('total')}</td></tr>")
    return (f'<div class="static" id="static"><h1>NBA {p["date"]}</h1><p>DraftKings lines and the model\'s numbers. Updated {p["generated_utc"]}.</p>'
            f'<table><tr><th>Game</th><th>Tip (UTC)</th><th>Spread</th><th>Total</th><th>Model win</th><th>Model margin</th><th>Model total</th></tr>' + "".join(rows) + "</table></div>")


def render(payload: dict, nhl_href: str = "../index.html", root: str = "../") -> str:
    data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    html = (TEMPLATE.replace("__CSS__", BASE_CSS + NFL_CSS + NBA_CSS + BRAND_CSS).replace("__PAYLOAD__", data).replace("__STATIC__", static_summary(payload))
            .replace("__DATE__", payload["date"]).replace("__BRAND__", brand_html(root, "nba", nhl_href))
            .replace("__HEAD__", head_tags(root, "Gill Sports · NBA", "NBA game lines, player props, the bot's picks and the research desk")))
    return finish_page(html, root, "nba", nhl_href)


__all__ = ["render", "TEMPLATE"]
