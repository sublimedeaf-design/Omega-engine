import assert from "node:assert/strict";
import { test } from "node:test";
import { signerRetryAdmission } from "../control-plane/generation-reconciler.mjs";

const blocked = {
  "omega/control-plane/signer": {
    state: "error", description: "AUTHORIZATION gen=9980fbd6f051 incident=abc",
    updated_at: "2026-09-30T12:00:00Z",
  },
};

test("unchanged authorization failure waits instead of dispatching again", () => {
  assert.equal(signerRetryAdmission(blocked).allowed, false);
  assert.equal(signerRetryAdmission({ ...blocked, "omega/signer/key-availability": {
    state: "pending", updated_at: "2026-09-30T13:00:00Z",
  } }).allowed, false);
});

test("an older or malformed readiness success cannot resume signing", () => {
  for (const updated_at of ["2026-09-30T11:00:00Z", "2026-09-30T12:00:00Z", "invalid"]) {
    assert.equal(signerRetryAdmission({ ...blocked, "omega/signer/key-availability": {
      state: "success", updated_at,
    } }).allowed, false);
  }
});

test("new verified availability resumes signing", () => {
  assert.equal(signerRetryAdmission({ ...blocked, "omega/signer/key-availability": {
    state: "success", updated_at: "2026-09-30T12:01:00Z",
  } }).allowed, true);
});

test("an initial attempt or stale failure does not exclude alternative backends", () => {
  assert.equal(signerRetryAdmission({}).allowed, true);
  assert.equal(signerRetryAdmission({ "omega/control-plane/signer": {
    ...blocked["omega/control-plane/signer"], state: "stale-control-generation",
  } }).allowed, true);
});
