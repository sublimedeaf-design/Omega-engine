const PRIVATE_REPO="sublimedeaf-design/Omega-engines";
const SHA=/^[0-9a-f]{40}$/;

function headers(token){return {
  accept:"application/vnd.github+json",
  authorization:`Bearer ${token}`,
  "x-github-api-version":"2022-11-28",
  "user-agent":"OMEGA-Resilience-Certifier/1",
};}
async function gh(token,path,options={}){
  const r=await fetch(`https://api.github.com${path}`,{...options,headers:{...headers(token),...(options.headers||{})}});
  const t=await r.text();
  if(!r.ok) throw new Error(`GITHUB_HTTP_${r.status}:${t.slice(0,220)}`);
  return t?JSON.parse(t):{};
}
function latest(rows){
  const sorted=[...rows].sort((a,b)=>String(b.updated_at||b.created_at||"").localeCompare(String(a.updated_at||a.created_at||"")));
  const out={};
  for(const row of sorted){const c=String(row.context||""); if(c && !(c in out)) out[c]=row;}
  return out;
}
function fresh(row,now,maxMinutes){
  const at=Date.parse(String(row?.updated_at||row?.created_at||""));
  return Number.isFinite(at) && now-at>=-300000 && now-at<=maxMinutes*60000;
}
function green(map,context,now,maxMinutes){
  const row=map[context];
  return Boolean(row && row.state==="success" && fresh(row,now,maxMinutes));
}
async function refSha(token,ref){
  try{return String((await gh(token,`/repos/${PRIVATE_REPO}/git/ref/heads/${encodeURIComponent(ref)}`))?.object?.sha||"");}
  catch(e){if(String(e).includes("GITHUB_HTTP_404:")) return ""; throw e;}
}
async function policy(token,sha){
  const row=await gh(token,`/repos/${PRIVATE_REPO}/contents/.omega/external-validation.json?ref=${sha}`);
  const raw=String(row.content||"").replace(/\n/g,"");
  return JSON.parse(atob(raw));
}
function externalQuorum(map,p,now){
  const suites=[...p.required_suites,p.android_suite];
  const providers={};
  const greens=[];
  for(const [name,spec] of Object.entries(p.providers||{})){
    let ok=true;
    const checks={};
    for(const suite of suites){
      const context=`${spec.context_prefix}/${suite}`;
      const row=map[context];
      const host=(()=>{try{return new URL(String(row?.target_url||"")).hostname.toLowerCase();}catch{return "";}})();
      const pass=Boolean(
        row && row.state==="success" &&
        fresh(row,now,Number(p.max_status_age_minutes||180)) &&
        (spec.target_hosts||[]).map(x=>String(x).toLowerCase()).includes(host)
      );
      checks[suite]={ok:pass,host};
      if(!pass) ok=false;
    }
    providers[name]={green:ok,checks};
    if(ok) greens.push(name);
  }
  return {green:greens.length>=Number(p.min_green_providers||2),greenProviders:greens,providers};
}
async function post(token,sha,state,description,targetUrl){
  await gh(token,`/repos/${PRIVATE_REPO}/statuses/${sha}`,{
    method:"POST",headers:{"content-type":"application/json"},
    body:JSON.stringify({state,context:"omega/resilience-certified",description:String(description).slice(0,140),target_url:targetUrl||undefined}),
  });
}
export async function certify({token,targetUrl="",now=Date.now()}={}){
  if(!token) throw new Error("OMEGA_GITHUB_TOKEN_MISSING");
  const main=await gh(token,`/repos/${PRIVATE_REPO}/commits/main`);
  const sha=String(main.sha||"");
  if(!SHA.test(sha)) throw new Error("MAIN_SHA_INVALID");
  const rows=(await gh(token,`/repos/${PRIVATE_REPO}/commits/${sha}/status?per_page=100`)).statuses||[];
  const map=latest(rows);
  const p=await policy(token,sha);
  const ext=externalQuorum(map,p,now);
  const [light,android]=await Promise.all([
    refSha(token,p.trigger_branch),
    refSha(token,p.android_trigger_branch),
  ]);

  const hosted=[
    "omega/hosted-ci/python311","omega/hosted-ci/python313","omega/hosted-ci/python314",
    "omega/hosted-ci/storage","omega/hosted-governance","omega/hosted-android",
  ];
  const federation=[
    "omega-runtime/main-exact","omega-federation/peer-http-5x",
    "omega-federation/exact-sha-executor","omega-federation/evidence-verifier",
    "omega-federation/evidence-publish",
  ];
  const layers={
    hosted_exact:hosted.every(x=>green(map,x,now,180)),
    external_quorum:ext.green,
    validation_refs:light===sha && android===sha,
    control_plane:green(map,"omega/control-plane/ref-sync",now,180),
    clean_recovery:green(map,"omega/hosted-recovery",now,1440),
    federation:federation.every(x=>green(map,x,now,1440)),
    signer_continuity:green(map,"omega/signer/continuity",now,10080),
  };
  const missing=Object.entries(layers).filter(([,v])=>!v).map(([k])=>k);
  const ok=missing.length===0;
  const state=ok?"success":"pending";
  const description=ok?"resilience certified: all independent proof layers green":`resilience pending: ${missing.slice(0,4).join(",")}`;
  await post(token,sha,state,description,targetUrl);
  return {ok,sha,state,layers,missing,external:ext,refs:{light,android}};
}
