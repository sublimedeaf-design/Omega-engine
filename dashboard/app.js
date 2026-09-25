const state={data:null,query:"",filter:"all"};
const fmtPct=v=>Number.isFinite(Number(v))?(Number(v)*100).toFixed(1)+"%":"—";
const fmtDate=v=>{if(!v)return"—";const d=new Date(v);return Number.isNaN(d.valueOf())?v:d.toLocaleString("nl-NL",{dateStyle:"short",timeStyle:"short"})};
const ageHours=v=>v?(Date.now()-new Date(v).getTime())/36e5:Infinity;
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function health(){
 const d=state.data, t24=d?.t24||{}, t60=d?.t60||{};
 const h24=ageHours(t24.generated_at), h60=ageHours(t60.generated_at);
 const cards=[
  ["T−24 data",h24<2?"ACTUEEL":h24<26?"OUDER":"VEROUDERD",h24<2?"ok":h24<26?"warn":"bad"],
  ["T−24 engine",t24.engine_health||"ONBEKEND",t24.engine_health==="OK"?"ok":"bad"],
  ["Provider",t24.provider_health||"ONBEKEND",t24.provider_health==="OK"?"ok":"bad"],
  ["T−60 data",h60<1.5?"ACTUEEL":h60<26?"OUDER":"VEROUDERD",h60<1.5?"ok":h60<26?"warn":"bad"]
 ];
 document.querySelector("#health").innerHTML=cards.map(([a,b,c])=>`<div class="health-card"><span>${esc(a)}</span><b class="${c}">${esc(b)}</b></div>`).join("");
 document.querySelector("#t24Meta").textContent=`${fmtDate(t24.generated_at)} · ${t24.predicted??0} fixtures`;
 document.querySelector("#t60Meta").textContent=`${fmtDate(t60.generated_at)} · ${(t60.recommendations||[]).length} aanbevelingen`;
 document.querySelector("#footerStatus").textContent=`Snapshot: ${fmtDate(d?.published_at)}`;
}
function visible(r){
 const text=(r.home+" "+r.away+" "+r.competition).toLowerCase();
 if(state.query&&!text.includes(state.query))return false;
 if(state.filter==="eligible"&&!r.bet_eligible)return false;
 if(state.filter==="upcoming"&&new Date(r.kickoff).getTime()<Date.now())return false;
 return true;
}
function predictionCard(r){
 const p=r.probabilities||{}, odds=r.fair_odds||{}, stale=new Date(r.kickoff).getTime()<Date.now();
 return `<article class="card ${stale?"stale":""}">
  <div class="card-top"><span>${esc(r.competition||"Onbekende competitie")}</span><span>${fmtDate(r.kickoff)}</span></div>
  <div class="match">${esc(r.home)} — ${esc(r.away)}</div>
  <div class="reason">${esc(r.reason||r.probability_label||"")}</div>
  <div class="probs">
   <div class="prob"><strong>${fmtPct(p.home)}</strong><span>1 · fair ${odds.home??"—"}</span></div>
   <div class="prob"><strong>${fmtPct(p.draw)}</strong><span>X · fair ${odds.draw??"—"}</span></div>
   <div class="prob"><strong>${fmtPct(p.away)}</strong><span>2 · fair ${odds.away??"—"}</span></div>
  </div>
  <div class="tags">
   <span class="tag">${esc(r.prediction_source||"model")}</span>
   <span class="tag">kwaliteit ${esc(r.quality_tier??"—")}</span>
   <span class="tag ${r.bet_eligible?"good":"no"}">${r.bet_eligible?"BET-ELIGIBLE":"NO BET"}</span>
  </div>
 </article>`;
}
function render(){
 health();
 const rows=(state.data?.t24?.results||[]).filter(visible);
 document.querySelector("#predictions").innerHTML=rows.length?rows.map(predictionCard).join(""):'<div class="empty">Geen T−24 voorspellingen voor dit filter.</div>';
 const t60=state.data?.t60?.recommendations||[];
 document.querySelector("#t60").innerHTML=t60.length?t60.map(r=>`<article class="card"><div class="card-top"><span>${esc(r.competition)}</span><span>${fmtDate(r.kickoff)}</span></div><div class="match">${esc(r.home)} — ${esc(r.away)}</div><div class="reason">${esc(r.reason||r.recommendation||"")}</div><div class="tags"><span class="tag">${esc(r.market||"T−60")}</span><span class="tag">${esc(r.recommendation||"NO BET")}</span></div></article>`).join(""):'<div class="empty">Momenteel zijn er geen T−60 aanbevelingen. Dat is een geldige NO BET-uitkomst.</div>';
}
async function load(){
 document.querySelector("#refresh").disabled=true;
 try{const r=await fetch("./data/predictions.json?ts="+Date.now(),{cache:"no-store"});if(!r.ok)throw new Error("HTTP "+r.status);state.data=await r.json();render()}
 catch(e){document.querySelector("#predictions").innerHTML='<div class="empty">Dashboarddata kon niet worden geladen: '+esc(e.message)+'</div>'}
 finally{document.querySelector("#refresh").disabled=false}
}
document.querySelector("#refresh").addEventListener("click",load);
document.querySelector("#search").addEventListener("input",e=>{state.query=e.target.value.trim().toLowerCase();render()});
document.querySelector("#filter").addEventListener("change",e=>{state.filter=e.target.value;render()});
load();setInterval(load,60000);
