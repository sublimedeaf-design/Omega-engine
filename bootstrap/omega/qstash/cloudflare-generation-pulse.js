const CONTROL_REPOSITORY = "sublimedeaf-design/Omega-engine";
const GENERATION_WORKFLOW = "omega-generation-reconciler.yml";

function response(status, payload) {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "content-type": "application/json; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}

function controlHeaders(token) {
  return {
    accept: "application/vnd.github+json",
    authorization: `Bearer ${token}`,
    "x-github-api-version": "2022-11-28",
    "user-agent": "OMEGA-External-Generation-Pulse/1",
  };
}

async function github(token, path, options = {}) {
  const res = await fetch(`https://api.github.com${path}`, {
    ...options,
    headers: {
      ...controlHeaders(token),
      ...(options.headers || {}),
    },
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(`GITHUB_HTTP_${res.status}:${path}:${text.slice(0, 240)}`);
  }
  return text ? JSON.parse(text) : {};
}

async function activeReconcilerRuns(token) {
  const states = ["queued", "in_progress"];
  let count = 0;
  for (const state of states) {
    const row = await github(
      token,
      `/repos/${CONTROL_REPOSITORY}/actions/workflows/${GENERATION_WORKFLOW}/runs?status=${state}&per_page=20`,
    );
    count += Number(row.total_count || 0);
  }
  return count;
}

async function dispatchGeneration(env, source) {
  const token = String(env.OMEGA_CONTROL_DISPATCH_TOKEN || "");
  if (!token) throw new Error("OMEGA_CONTROL_DISPATCH_TOKEN_MISSING");

  const active = await activeReconcilerRuns(token);
  if (active > 0) {
    return {
      ok: true,
      action: "already_active",
      active,
      source,
      workflow: GENERATION_WORKFLOW,
    };
  }

  await github(
    token,
    `/repos/${CONTROL_REPOSITORY}/actions/workflows/${GENERATION_WORKFLOW}/dispatches`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ref: "main" }),
    },
  );

  return {
    ok: true,
    action: "dispatched",
    active: 0,
    source,
    workflow: GENERATION_WORKFLOW,
  };
}

function authorized(request, env) {
  const expected = String(env.OMEGA_CONTROL_KEY || "");
  if (!expected) return false;
  const bearer = request.headers.get("authorization") || "";
  const alternate = request.headers.get("x-omega-control-key") || "";
  return bearer === `Bearer ${expected}` || alternate === expected;
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (request.method === "GET" && url.pathname === "/healthz") {
      return response(200, {
        ok: true,
        service: "omega-generation-pulse",
        authority: "wake_reconcile_only",
      });
    }

    if (request.method !== "POST" || url.pathname !== "/pulse") {
      return response(404, { ok: false, error: "not_found" });
    }

    if (!authorized(request, env)) {
      return response(403, { ok: false, error: "forbidden" });
    }

    try {
      return response(200, await dispatchGeneration(env, "external-http"));
    } catch (error) {
      return response(503, {
        ok: false,
        error: String(error && error.message ? error.message : error).slice(0, 400),
      });
    }
  },

  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(
      dispatchGeneration(env, "cloudflare-cron").catch((error) => {
        console.error("OMEGA_GENERATION_PULSE_FAILED", String(error && error.message ? error.message : error));
      }),
    );
  },
};
