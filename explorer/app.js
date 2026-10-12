'use strict';
const $=id=>document.getElementById(id);
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const D=REVISION_DATA;
const repo=D.repository_base||'../';
const names={initial_three:'Three passages',reconsider:'Same evidence · second answer',fixed:(D.selected_k&&D.selected_k!==9?D.selected_k+' passages':'Nine passages'),adaptive:'Adaptive search',all_documents:'All 24 documents'};
const kinds={direct:'One policy',combined:'Combining policies',missing:'Information missing'};
for(const control of ['left','right'])$(control).innerHTML=Object.entries(names).map(([k,v])=>`<option value="${k}">${v}</option>`).join('');
$('left').value='fixed';$('right').value='adaptive';
const trial=(id,v)=>D.trials.find(t=>t.case_id===id&&t.variant===v);
$('results').innerHTML=Object.entries(names).map(([v,label])=>{const s=D.summary.variants[v];return `<tr><td>${label}</td><td class="chart-cell"><span class="bar"><i style="width:${s.passed/24*100}%"></i></span>${s.passed} / 24</td><td>${s.median_api_seconds.toFixed(2)} s</td><td>$${s.estimated_model_usd.toFixed(4)}</td></tr>`}).join('');
function highlight(text,facts){let value=esc(text);for(const fact of [...facts].sort((a,b)=>b.length-a.length)){const re=new RegExp(esc(fact).replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),'gi');value=value.replace(re,m=>`<mark>${m}</mark>`)}return value}
function menu(preferred=$('question').value){const kind=$('kind').value;const cases=D.cases.filter(c=>kind==='all'||c.kind===kind||kind==='changed'&&trial(c.id,$('left').value).review.pass!==trial(c.id,$('right').value).review.pass);$('question').innerHTML=cases.map(c=>`<option value="${c.id}">${c.id.toUpperCase()} · ${esc(c.question)}</option>`).join('');if(cases.some(c=>c.id===preferred))$('question').value=preferred;render()}
function passage(p,c,cited,rank){return `<details class="passage" data-source="${esc(p.source)}"><summary>${rank?`<span class="passage-rank">Rank ${rank}</span> `:''}${esc(p.source.slice(3).replaceAll('-',' '))}${cited.has(p.id)?'<span>CITED</span>':''}<small>${esc(p.id)}${typeof p.score==='number'?` · similarity ${p.score.toFixed(4)}`:''}</small></summary><p>${highlight(p.text,c.facts)}</p></details>`}
function render(){const params=new URLSearchParams({q:$('question').value,left:$('left').value,right:$('right').value,kind:$('kind').value});history.replaceState(null,'','#'+params.toString());const c=D.cases.find(c=>c.id===$('question').value);if(!c){$('answers').innerHTML='<p>No questions have different outcomes in this comparison.</p>';$('question-text').textContent='';$('case-label').textContent='';$('expected').textContent='';$('pair-note').textContent='';return}$('question-text').textContent=c.question;$('case-label').textContent=c.id.toUpperCase()+' · '+kinds[c.kind];$('expected').textContent=c.expected;$('pair-note').textContent=[$('left').value,$('right').value].includes('reconsider')&&[$('left').value,$('right').value].includes('initial_three')?'A paired comparison: the second answer checks this exact first draft against the same evidence.':'Same question and answer instructions. Open each search to inspect what changed.';
$('answers').innerHTML=[$('left').value,$('right').value].map(v=>{const t=trial(c.id,v),cited=new Set(t.answer.citations);const coverage=t.evidence_diagnostic;return `<article class="flow" data-variant="${v}"><div class="flow-head"><h3>${names[v]}</h3><div class="stats"><span>${t.searches.length} ${t.searches.length===1?'search':'searches'}</span><span>${t.model_calls} model call${t.model_calls===1?'':'s'}</span><span>${t.api_seconds.toFixed(2)} s</span><span>${(t.estimated_model_usd*100).toFixed(3)} US cents</span></div></div><div class="answer-area"><span class="badge ${t.review.pass?'':'fail'}">${t.review.pass?'Complete & supported':'Needs correction'}</span><p class="answer-copy">${esc(t.answer.answer)}</p><p class="review">${esc(t.review.reason)}</p>${v==='adaptive'?`<p class="prompt-note">${t.final_prompt_mode==='fresh_evidence_prompt'?'Final answer: fresh prompt with accumulated evidence and common instructions; search conversation, planning text, and tools removed.':'Final answer: returned in the search conversation while the planning instructions and search tool were available.'}</p>`:''}<a class="small" href="${esc(repo+t.source_trace)}">Recorded request and response ↗</a><div class="coverage">Required source phrases present: ${coverage.final_hits.filter(Boolean).length} / ${coverage.final_hits.length}. This checks exact text, not answer quality.</div></div>${t.searches.length?`<div class="searches">${t.searches.map((s,i)=>`<section class="search-step"><div class="step-label">${i===0?'FIRST SEARCH':'FOLLOW-UP '+i} · ${s.chunks.length} passages · ${s.api_seconds.toFixed(2)} s</div><p class="query">${esc(s.query)}</p>${s.chunks.map((p,index)=>passage(p,c,cited,index+1)).join('')}</section>`).join('')}</div>`:`<div class="evidence-all"><p class="step-label">ALL 24 COMPLETE DOCUMENTS</p>${t.evidence.map(p=>passage(p,c,cited,null)).join('')}</div>`}</article>`}).join('')}
function clearWarning(){ $('link-warning').hidden=true; $('link-warning').textContent=''; }
function route(){
  const p=new URLSearchParams(location.hash.slice(1));
  const warnings=[];
  for(const side of ['left','right']){
    const value=p.get(side);
    $(side).value=names[value]?value:(side==='left'?'fixed':'adaptive');
    if(value&&!names[value])warnings.push('An unknown flow in the link was replaced with the default.');
  }
  const kind=p.get('kind')||'all';
  const validKinds=['all','direct','combined','missing','changed'];
  $('kind').value=validKinds.includes(kind)?kind:'all';
  if(!validKinds.includes(kind))warnings.push('An unknown question filter was replaced with all questions.');
  const requested=p.get('q');
  const known=D.cases.some(c=>c.id===requested);
  if(requested&&!known)warnings.push('The question in the link was not found. Showing an available question.');
  menu(known?requested:'m03');
  if(known&&$('question').value!==requested)warnings.push('The linked question does not match this filter. Showing the first matching question, if available.');
  $('link-warning').textContent=[...new Set(warnings)].join(' ');
  $('link-warning').hidden=!warnings.length;
}
for(const id of ['left','right','kind'])$(id).addEventListener('change',()=>{clearWarning();menu()});
$('question').addEventListener('change',()=>{clearWarning();render()});
window.addEventListener('hashchange',route);route();
