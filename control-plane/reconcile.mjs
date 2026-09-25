const PRIVATE_REPO = "sublimedeaf-design/Omega-engines";
const HELPER_REPO = "sublimedeaf-design/Omega-engine";
const LEDGER_ISSUE = 2;
const LIGHT_REF = "omega-external-validation";
const ANDROID_REF = "omega-external-validation-android";
const REQUIRED = [
  "omega/hosted-ci/python311",
  "omega/hosted-ci/python313",
  "omega/hosted-ci/python314",
  "omega/hosted-ci/storage",
  "omega/hosted-governance",
];
const STABILITY_MS = 15 * 60 * 1000;
const COOLDOWN_MS = 15 * 60 * 1000;
const MAX_24H = 2;
const MAX_30D = 6;
const SHA = /^[0-9a-f]{40}$/;

function authHeaders(token) {
  return {
    "accept": "application/vnd.github+json",
    "authorization": `Bearer ${token}`,
    "x-github-api-version": "2022-11-28",
    "user-agent": "OMEGA-Failproof-Control/1",
  };
}

async function gh(token, path, options = {}) {
  const response = await fetch(`https://api.github.com${path}`, {
    ...options,
    headers: {...authHeaders(token), ...(options.headers || {})},
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`GITHUB_HTTP_${response.status}:${text.slice(0,240)}`);
  return text ? JSON.parse(text) : {};
}

function latestStates(rows) {
  const sorted = [...rows].sort((a,b) =>
    String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || ""))
  );
  const out = {};
  for (const row of sorted) {
    const key = String(row.context || "");
    if (key && !(key in out)) out[key] = String(row.state || "");
  }
  return out;
}

function parseLedger(rows, nowMs) {
  const re = /^OMEGA_EXTERNAL_DISPATCH at=([^ ]+) android=(true|false)$/;
  const times = [];
  for (const row of rows) {
    const m = re.exec(String(row.body || "").trim());
    if (!m) continue;
    const t = Date.parse(m[1]);
    if (Number.isFinite(t)) times.push(t);
  }
  times.sort((a,b)=>a-b);
  const last = times.length ? times[times.length-1] : 0;
  const c24 = times.filter(t => t >= nowMs - 86400000).length;
  const c30 = times.filter(t => t >= nowMs - 30*86400000).length;
  return {
    allowed: nowMs-last >= COOLDOWN_MS && c24 < MAX_24H && c30 < MAX_30D,
    last, c24, c30,
  };
}

async function refSha(token, ref) {
  try {
    const row = await gh(token, `/repos/${PRIVATE_REPO}/git/ref/heads/${encodeURIComponent(ref)}`);
    return String(row?.object?.sha || "");
  } catch (error) {
    if (String(error).includes("GITHUB_HTTP_404:")) return "";
    throw error;
  }
}

async function updateRef(token, ref, sha, current) {
  if (current === sha) return "current";
  if (!current) {
    await gh(token, `/repos/${PRIVATE_REPO}/git/refs`, {
      method:"POST",
      headers:{"content-type":"application/json"},
      body:JSON.stringify({ref:`refs/heads/${ref}`, sha}),
    });
    return "created";
  }
  await gh(token, `/repos/${PRIVATE_REPO}/git/refs/heads/${encodeURIComponent(ref)}`, {
    method:"PATCH",
    headers:{"content-type":"application/json"},
    body:JSON.stringify({sha, force:true}),
  });
  return "updated";
}

async function postPrivateStatus(token, sha, state, description, targetUrl) {
  await gh(token, `/repos/${PRIVATE_REPO}/statuses/${sha}`, {
    method:"POST",
    headers:{"content-type":"application/json"},
    body:JSON.stringify({
      state,
      context:"omega/control-plane/ref-sync",
      description:String(description).slice(0,140),
      target_url:targetUrl || undefined,
    }),
  });
}

export async function reconcile({token, ledgerToken=token, provider="unknown", targetUrl="", nowMs=Date.now()} = {}) {
  if (!token) throw new Error("OMEGA_GITHUB_TOKEN_MISSING");
  if (!ledgerToken) throw new Error("OMEGA_LEDGER_TOKEN_MISSING");

  const main = await gh(token, `/repos/${PRIVATE_REPO}/commits/main`);
  const sha = String(main.sha || "");
  const committedAt = Date.parse(String(main?.commit?.committer?.date || ""));
  if (!SHA.test(sha) || !Number.isFinite(committedAt)) throw new Error("MAIN_PROVENANCE_INVALID");
  const combined = await gh(token, `/repos/${PRIVATE_REPO}/commits/${sha}/status?per_page=100`);
  const states = latestStates(Array.isArray(combined.statuses) ? combined.statuses : []);
  const coreGreen = REQUIRED.every(k => states[k] === "success");
  const androidGreen = states["omega/hosted-android"] === "success";
  if (!coreGreen) {
    if (nowMs - committedAt < STABILITY_MS) return {ok:true, action:"wait_stability", sha, provider};
    return {ok:true, action:"wait_hosted_core", sha, provider};
  }

  const [lightOld, androidOld] = await Promise.all([
    refSha(token, LIGHT_REF), refSha(token, ANDROID_REF),
  ]);
  const needLight = lightOld !== sha;
  let needAndroid = false;

  if (androidGreen && androidOld !== sha) {
    if (!androidOld) {
      needAndroid = true;
    } else {
      let compare = {};
      try {
        compare = await gh(token, `/repos/${PRIVATE_REPO}/compare/${androidOld}...${sha}`);
      } catch {
        compare = {};
      }
      const files = Array.isArray(compare.files) ? compare.files.map(x=>String(x.filename||"")) : [];
      needAndroid = files.some(name =>
        name.startsWith("android/") ||
        name.startsWith(".github/workflows/android") ||
        name.startsWith("tests/test_android") ||
        name === "evidence/release-stage.json"
      );
    }
  }

  if (!needLight && !needAndroid) {
    await postPrivateStatus(token, sha, "success", "external validation refs already current", targetUrl);
    return {ok:true, action:"current", sha, provider, android:false};
  }

  const comments = await gh(ledgerToken, `/repos/${HELPER_REPO}/issues/${LEDGER_ISSUE}/comments?per_page=100`);
  const budget = parseLedger(Array.isArray(comments) ? comments : [], nowMs);
  if (!budget.allowed) {
    await postPrivateStatus(token, sha, "pending", "external validation budget/cooldown active", targetUrl);
    return {ok:true, action:"budget_wait", sha, provider, budget};
  }

  const result = {};
  if (needLight) result.light = await updateRef(token, LIGHT_REF, sha, lightOld);
  if (needAndroid) result.android = await updateRef(token, ANDROID_REF, sha, androidOld);

  const at = new Date(nowMs).toISOString().replace(".000Z","Z");
  await gh(ledgerToken, `/repos/${HELPER_REPO}/issues/${LEDGER_ISSUE}/comments`, {
    method:"POST",
    headers:{"content-type":"application/json"},
    body:JSON.stringify({body:`OMEGA_EXTERNAL_DISPATCH at=${at} android=${needAndroid}`}),
  });
  await postPrivateStatus(token, sha, "success", `external refs reconciled by ${provider}`, targetUrl);
  return {ok:true, action:"dispatched", sha, provider, android:needAndroid, result};
}

export const POLICY = Object.freeze({
  privateRepo:PRIVATE_REPO,
  helperRepo:HELPER_REPO,
  lightRef:LIGHT_REF,
  androidRef:ANDROID_REF,
  stabilitySeconds:STABILITY_MS/1000,
  cooldownSeconds:COOLDOWN_MS/1000,
  max24h:MAX_24H,
  max30d:MAX_30D,
  authority:["read-main","read-status","read-compare","update-validation-refs","write-control-status","append-public-ledger"],
  forbidden:["merge","release","sign","write-main","write-model","write-evidence"],
});
