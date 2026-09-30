import assert from "node:assert/strict";
import { test } from "node:test";
import { isStateOnlyPath } from "../control-plane/generation-reconciler.mjs";

test("known wake pointers and epoch data can advance without code drift", () => {
  for (const path of [
    "bootstrap/omega/pr-validation-trigger.txt",
    "bootstrap/omega/recovery-trigger.txt",
    "bootstrap/omega/canonical-unsigned-lock.json",
    `bootstrap/omega/validation-requests/${"a".repeat(40)}.json`,
    "federation/epochs/current.json",
    "federation/epochs/releases/9980-proof.json",
  ]) assert.equal(isStateOnlyPath(path), true, path);
});

test("bootstrap code, configuration and unrecognized pointers require an epoch", () => {
  for (const path of [
    "bootstrap/omega/codespace_wake.py",
    "bootstrap/omega/hot_sync_runtime_remote.sh",
    "bootstrap/omega/cloudflare/worker.js",
    "bootstrap/omega/qstash/wrangler.toml",
    "bootstrap/omega/unknown-trigger.txt",
    "federation/epochs/run.sh",
    "control-plane/state-only-paths.json",
    "scripts/control_state_policy.py",
  ]) assert.equal(isStateOnlyPath(path), false, path);
});

test("malformed paths cannot bypass the state boundary", () => {
  for (const path of [
    "", "/federation/epochs/current.json", "federation/epochs/../current.json",
    "federation//epochs/current.json", "federation/epochs/./current.json",
    "federation/epochs/current.json\n", "federation\\epochs\\current.json",
    "bootstrap/omega/validation-requests/short.json", null,
  ]) assert.equal(isStateOnlyPath(path), false, String(path));
});
