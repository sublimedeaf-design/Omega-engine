import {reconcile, POLICY} from "./reconcile.mjs";

async function run(targetUrl="") {
  return await reconcile({
    token: Deno.env.get("OMEGA_GITHUB_TOKEN") || "",
    provider: "deno",
    targetUrl,
  });
}

Deno.cron("omega-failproof-control", "*/15 * * * *", async () => {
  try { await run(); } catch (error) {
    console.error("OMEGA_DENO_CONTROL_FAILED", String(error).slice(0,200));
  }
});

Deno.serve(async (request) => {
  const url=new URL(request.url);
  if (url.pathname === "/healthz") {
    return Response.json({ok:true,service:"omega-deno-control",policy:POLICY});
  }
  if (url.pathname !== "/reconcile" || request.method !== "POST") {
    return new Response("not found\n",{status:404});
  }
  const key=request.headers.get("x-omega-control-key") || "";
  if (!Deno.env.get("OMEGA_CONTROL_KEY") || key !== Deno.env.get("OMEGA_CONTROL_KEY")) {
    return new Response("unauthorized\n",{status:401});
  }
  try {
    return Response.json(await run(request.url));
  } catch (error) {
    return Response.json({ok:false,error:String(error).slice(0,240)},{status:503});
  }
});
