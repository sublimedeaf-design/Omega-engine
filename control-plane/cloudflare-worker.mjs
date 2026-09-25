import {reconcile, POLICY} from "./reconcile.mjs";

async function run(env, requestUrl="") {
  return reconcile({
    token: env.OMEGA_GITHUB_TOKEN,
    provider: "cloudflare",
    targetUrl: requestUrl,
  });
}

export default {
  async scheduled(_controller, env, ctx) {
    ctx.waitUntil(run(env));
  },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/healthz") {
      return Response.json({ok:true, service:"omega-cloudflare-control", policy:POLICY});
    }
    if (url.pathname !== "/reconcile" || request.method !== "POST") {
      return new Response("not found\n",{status:404});
    }
    const key=request.headers.get("x-omega-control-key") || "";
    if (!env.OMEGA_CONTROL_KEY || key !== env.OMEGA_CONTROL_KEY) {
      return new Response("unauthorized\n",{status:401});
    }
    try {
      return Response.json(await run(env, request.url));
    } catch (error) {
      return Response.json({ok:false,error:String(error).slice(0,240)},{status:503});
    }
  },
};
