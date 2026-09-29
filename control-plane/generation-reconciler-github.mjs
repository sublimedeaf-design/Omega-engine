import { reconcileGeneration, POLICY } from "./generation-reconciler.mjs";

try {
  const result = await reconcileGeneration({
    privateToken: process.env.OMEGA_PRIVATE_TOKEN || "",
    controlToken: process.env.OMEGA_CONTROL_TOKEN || "",
    targetUrl: process.env.OMEGA_RECONCILER_TARGET_URL || "",
  });
  process.stdout.write("OMEGA_GENERATION_RECONCILER " + JSON.stringify({ ...result, policy: POLICY }) + "\n");
  if (result.ok === false && result.action === "blocked") process.exitCode = 2;
} catch (error) {
  process.stderr.write("OMEGA_GENERATION_RECONCILER_FAILED " + String(error).slice(0, 400) + "\n");
  process.exitCode = 1;
}
