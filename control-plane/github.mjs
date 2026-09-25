import {reconcile} from "./reconcile.mjs";

try {
  const result=await reconcile({
    token: process.env.OMEGA_GITHUB_TOKEN || "",
    ledgerToken: process.env.OMEGA_LEDGER_TOKEN || "",
    provider: "github-hosted",
    targetUrl: process.env.OMEGA_CONTROL_TARGET_URL || "",
  });
  process.stdout.write("OMEGA_GITHUB_CONTROL "+JSON.stringify(result)+"\n");
} catch (error) {
  process.stderr.write("OMEGA_GITHUB_CONTROL_FAILED "+String(error).slice(0,240)+"\n");
  process.exitCode=1;
}
