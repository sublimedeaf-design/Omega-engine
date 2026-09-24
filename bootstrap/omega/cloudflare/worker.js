const API = "https://api.github.com";
let last = {ok:false,action:"init"};

async function gh(env, method, path) {
  const r = await fetch(API + path, {
    method,
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": "Bearer " + env.OMEGA_CODESPACE_LIFECYCLE_TOKEN,
      "X-GitHub-Api-Version": "2026-03-10",
      "User-Agent": "OMEGA-Cloudflare-Wake/1",
    },
  });
  let body = {};
  try { body = await r.json(); } catch (_) {}
  return [r.status, body];
}

function refOf(row) {
  return String((row.git_status && row.git_status.ref) || row.ref || "");
}

function choose(rows, owner, repo, ref) {
  const owned = rows.filter(r => r.repository?.full_name === owner + "/" + repo);
  const exact = owned.filter(r => [ref, "refs/heads/" + ref].includes(refOf(r)));
  const candidates = exact.length ? exact : owned;
  candidates.sort((a,b) =>
    String(b.last_used_at || b.created_at || "").localeCompare(
      String(a.last_used_at || a.created_at || "")
    )
  );
  return candidates[0] || null;
}

async function reconcile(env) {
  if (!env.OMEGA_CODESPACE_LIFECYCLE_TOKEN) return {ok:false,error:"TOKEN_MISSING"};
  const owner = env.OMEGA_OWNER || "sublimedeaf-design";
  const repo = env.OMEGA_REPOSITORY || "Omega-engines";
  const ref = env.OMEGA_REF || "main";

  const [listHttp, list] = await gh(env, "GET", "/user/codespaces?per_page=100");
  if (listHttp !== 200) return {ok:false,stage:"list",http_status:listHttp};

  const target = choose(list.codespaces || [], owner, repo, ref);
  if (!target?.name) return {ok:false,stage:"discover",error:"CODESPACE_NOT_FOUND"};

  const name = target.name;
  let [detailHttp, detail] = await gh(env, "GET", "/user/codespaces/" + encodeURIComponent(name));
  let state = String(detail.state || target.state || "").toLowerCase();
  if (detailHttp !== 200) return {ok:false,stage:"detail",http_status:detailHttp};

  let startHttp = null;
  if (!["available","running"].includes(state)) {
    [startHttp] = await gh(env, "POST", "/user/codespaces/" + encodeURIComponent(name) + "/start");
    if (![200,202,304,409].includes(startHttp)) {
      return {ok:false,stage:"start",http_status:startHttp};
    }
    [detailHttp, detail] = await gh(env, "GET", "/user/codespaces/" + encodeURIComponent(name));
    state = String(detail.state || "").toLowerCase();
  }

  const available = ["available","running"].includes(state);
  return {
    ok:available,
    action:available ? "available" : (startHttp === null ? "unavailable" : "start_requested"),
    repository:owner + "/" + repo,
    ref,
    codespace_name:name,
    state,
    start_http:startHttp,
    credential_material_recorded:false,
    checked_at:new Date().toISOString(),
  };
}

export default {
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(reconcile(env).then(x => {
      last = x;
      console.log(JSON.stringify(x));
    }));
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/healthz") {
      return Response.json(last,{status:last.ok?200:503});
    }
    if (url.pathname === "/reconcile" && request.method === "POST") {
      const expected = env.OMEGA_CONTROL_KEY || "";
      const supplied = request.headers.get("authorization") || "";
      if (!expected || supplied !== "Bearer " + expected) {
        return new Response("forbidden",{status:403});
      }
      last = await reconcile(env);
      return Response.json(last,{status:last.ok?200:503});
    }
    return new Response("not found",{status:404});
  },
};
