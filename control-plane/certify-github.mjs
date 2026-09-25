import {certify} from "./certify.mjs";
try {
  const result=await certify({
    token: process.env.OMEGA_GITHUB_TOKEN || "",
    targetUrl: process.env.OMEGA_CERTIFIER_TARGET_URL || "",
  });
  process.stdout.write("OMEGA_RESILIENCE_CERTIFIER "+JSON.stringify(result)+"\n");
} catch (error) {
  process.stderr.write("OMEGA_RESILIENCE_CERTIFIER_FAILED "+String(error).slice(0,240)+"\n");
  process.exitCode=1;
}
