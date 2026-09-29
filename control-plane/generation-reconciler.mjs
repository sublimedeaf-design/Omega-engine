const PRIVATE_REPO = "sublimedeaf-design/Omega-engines";
const CONTROL_REPO = "sublimedeaf-design/Omega-engine";
const SHA = /^[0-9a-f]{40}$/;
const RUN_URL = /\/actions\/runs\/([0-9]+)$/;

function headers(token) {
  return {
    accept: "application/vnd.github+json",
    authorization: `Bearer ${token}`,
    "x-github-api-version": "2022-11-28",
    "user-agent": "OMEGA-Generation-Reconciler/1",
  };
}

async function gh(token, path, options = {}) {
  const response = await fetch(`https://api.github.com${path}`, {
    ...options,
    headers: { ...headers(token), ...(options.headers || {}) },
  });
  const body = await response.text();
  if (!response.ok) {
    throw new Error(`GITHUB_HTTP_${response.status}:${path}:${body.slice(0, 300)}`);
  }
  return body ? JSON.parse(body) : {};
}

async function statusHistory(token, sha) {
  const rows = [];
  for (let page = 1; page <= 10; page += 1) {
    const batch = await gh(token, `/repos/${PRIVATE_REPO}/commits/${sha}/statuses?per_page=100&page=${page}`);
    if (!Array.isArray(batch)) throw new Error("OMEGA_STATUS_HISTORY_INVALID");
    rows.push(...batch);
    if (batch.length < 100) break;
  }
  return rows;
}

function latestStatusMap(rows) {
  const sorted = [...rows].sort((a, b) =>
    String(b.updated_at || b.created_at || "").localeCompare(String(a.updated_at || a.created_at || "")),
  );
  const out = {};
  for (const row of sorted) {
    const context = String(row.context || "");
    if (context && !(context in out)) out[context] = row;
  }
  return out;
}

function isSuccess(map, context) {
  return String(map[context]?.state || "") === "success";
}

function runId(map, context) {
  const target = String(map[context]?.target_url || "");
  const match = RUN_URL.exec(target);
  return match ? match[1] : "";
}

async function activeRuns(controlToken, workflow) {
  const counts = await Promise.all(["queued", "in_progress"].map(async status => {
    const row = await gh(
      controlToken,
      `/repos/${CONTROL_REPO}/actions/workflows/${workflow}/runs?status=${status}&per_page=20`,
    );
    return Number(row.total_count || 0);
  }));
  return counts.reduce((a, b) => a + b, 0);
}

async function dispatch(controlToken, workflow, inputs = {}) {
  const active = await activeRuns(controlToken, workflow);
  if (active > 0) return { dispatched: false, reason: "already_active", active };
  await gh(controlToken, `/repos/${CONTROL_REPO}/actions/workflows/${workflow}/dispatches`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ ref: "main", inputs }),
  });
  return { dispatched: true, reason: "dispatched", active: 0 };
}

async function postState(privateToken, sha, state, description, targetUrl) {
  await gh(privateToken, `/repos/${PRIVATE_REPO}/statuses/${sha}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      state,
      context: "omega/control-plane/generation-reconciler",
      description: String(description).slice(0, 140),
      target_url: targetUrl || undefined,
    }),
  });
}

async function observedEpoch(controlToken, sourceSha) {
  const row = await gh(
    controlToken,
    `/repos/${CONTROL_REPO}/contents/federation/epochs/current.json?ref=main`,
  );
  const raw = Buffer.from(String(row.content || "").replace(/\n/g, ""), "base64").toString("utf8");
  const epoch = JSON.parse(raw);
  const primary = epoch.primary || {};
  const releaseEpoch = epoch.release_epoch || {};
  const id = String(releaseEpoch.id || "");
  const source = String(primary.source_sha || "");
  const pass =
    epoch.state === "PASS" &&
    primary.certification_state === "PASS" &&
    source === sourceSha &&
    /^[0-9a-f]{64}$/.test(id);
  return { pass, source, id, sequence: Number(releaseEpoch.sequence || 0) };
}

function chooseStage(map) {
  if (!isSuccess(map, "omega/exact-final-validation") || !isSuccess(map, "omega/federation-v3-release")) {
    return { stage: "upstream-proof", workflow: "omega-release-orchestrator-arm.yml", inputs: {} };
  }

  if (!isSuccess(map, "omega/hosted-recovery") || !isSuccess(map, "omega/recovery-attestation")) {
    return { stage: "recovery", workflow: "omega-hosted-recovery-failover.yml", inputs: {} };
  }

  if (!isSuccess(map, "omega/candidate-evidence-root")) {
    const recovery = runId(map, "omega/hosted-recovery");
    const attestation = runId(map, "omega/recovery-attestation");
    if (!recovery || recovery !== attestation) {
      return { stage: "recovery-binding-invalid", blocked: true, reason: "recovery_run_binding_missing_or_mismatched" };
    }
    return {
      stage: "candidate-evidence-root",
      workflow: "omega-candidate-evidence-root.yml",
      inputs: { recovery_run_id: recovery },
    };
  }

  if (!isSuccess(map, "omega/release-evidence-staged") || !isSuccess(map, "omega/android-release-unsigned")) {
    const evidence = runId(map, "omega/candidate-evidence-root");
    if (!evidence) {
      return { stage: "release-stager-binding-invalid", blocked: true, reason: "evidence_run_binding_missing" };
    }
    return {
      stage: "release-stager",
      workflow: "omega-recovery-evidence-release-stager.yml",
      inputs: { evidence_run_id: evidence },
    };
  }

  if (!isSuccess(map, "omega/resilience-certified")) {
    return { stage: "resilience", workflow: "omega-resilience-certifier.yml", inputs: {} };
  }

  if (!isSuccess(map, "omega/signer/continuity") || !isSuccess(map, "omega/android-release-signed")) {
    return { stage: "canonical-signing", workflow: "omega-canonical-android-signer.yml", inputs: {} };
  }

  if (!isSuccess(map, "omega/android-runtime-coldstart")) {
    const signer = runId(map, "omega/android-release-signed");
    const continuity = runId(map, "omega/signer/continuity");
    if (!signer || signer !== continuity) {
      return { stage: "signer-binding-invalid", blocked: true, reason: "signer_run_binding_missing_or_mismatched" };
    }
    return {
      stage: "android-coldstart",
      workflow: "omega-android-runtime-coldstart.yml",
      inputs: { signer_run_id: signer },
    };
  }

  if (!isSuccess(map, "omega/release-live")) {
    return { stage: "final-promotion", workflow: "omega-final-release-promoter.yml", inputs: {} };
  }

  if (!isSuccess(map, "omega/release-certified")) {
    return {
      stage: "post-live",
      workflow: "omega-post-live-verification.yml",
      inputs: { final_sha: "__SOURCE_SHA__" },
      injectSourceSha: true,
    };
  }

  if (
    !isSuccess(map, "omega/limited-distribution/apk-signed") ||
    !isSuccess(map, "omega/limited-distribution/signer-continuity")
  ) {
    const postLive = runId(map, "omega/release-certified");
    if (!postLive) {
      return { stage: "limited-adapter-binding-invalid", blocked: true, reason: "post_live_run_binding_missing" };
    }
    return {
      stage: "limited-distribution-adapter",
      workflow: "omega-limited-distribution-release-adapter.yml",
      inputs: { final_sha: "__SOURCE_SHA__", post_live_run_id: postLive },
      injectSourceSha: true,
    };
  }

  if (!isSuccess(map, "omega/limited-distribution/live-certified")) {
    return {
      stage: "limited-live-certifier",
      workflow: "omega-limited-distribution-public-live-certifier.yml",
      inputs: { source_sha: "__SOURCE_SHA__" },
      injectSourceSha: true,
    };
  }

  return { stage: "complete", complete: true };
}

export async function reconcileGeneration({ privateToken, controlToken, targetUrl = "" } = {}) {
  if (!privateToken) throw new Error("OMEGA_PRIVATE_TOKEN_MISSING");
  if (!controlToken) throw new Error("OMEGA_CONTROL_TOKEN_MISSING");

  const main = await gh(privateToken, `/repos/${PRIVATE_REPO}/commits/main`);
  const sha = String(main.sha || "");
  if (!SHA.test(sha)) throw new Error("OMEGA_PRIVATE_MAIN_SHA_INVALID");

  const epoch = await observedEpoch(controlToken, sha);
  if (!epoch.pass) {
    await postState(privateToken, sha, "pending", "epoch not bound to current private main", targetUrl);
    return { ok: true, source_sha: sha, observed_generation: null, action: "wait_epoch", epoch };
  }

  const map = latestStatusMap(await statusHistory(privateToken, sha));
  const next = chooseStage(map);
  const generation = `${sha}:${epoch.id}`;

  if (next.complete) {
    await postState(privateToken, sha, "success", `generation converged epoch=${epoch.id.slice(0, 12)}`, targetUrl);
    return { ok: true, source_sha: sha, observed_generation: generation, action: "complete", stage: "complete" };
  }

  if (next.blocked) {
    await postState(privateToken, sha, "error", `${next.stage}:${next.reason}`, targetUrl);
    return { ok: false, source_sha: sha, observed_generation: generation, action: "blocked", ...next };
  }

  const inputs = { ...(next.inputs || {}) };
  if (next.injectSourceSha) {
    for (const key of Object.keys(inputs)) {
      if (inputs[key] === "__SOURCE_SHA__") inputs[key] = sha;
    }
  }

  const result = await dispatch(controlToken, next.workflow, inputs);
  await postState(
    privateToken,
    sha,
    "pending",
    `${next.stage}:${result.reason} epoch=${epoch.id.slice(0, 12)}`,
    targetUrl,
  );
  return {
    ok: true,
    source_sha: sha,
    observed_generation: generation,
    action: result.reason,
    stage: next.stage,
    workflow: next.workflow,
    inputs,
    active: result.active,
  };
}

export const POLICY = Object.freeze({
  model: "level-triggered-generation-reconciliation",
  privateRepo: PRIVATE_REPO,
  controlRepo: CONTROL_REPO,
  oneActionPerReconcile: true,
  staleStatusSource: "full-status-history-newest-per-context",
  generationFields: ["source_sha", "release_epoch_id"],
  stages: [
    "upstream-proof",
    "recovery",
    "candidate-evidence-root",
    "release-stager",
    "resilience",
    "canonical-signing",
    "android-coldstart",
    "final-promotion",
    "post-live",
    "limited-distribution-adapter",
    "limited-live-certifier",
    "complete",
  ],
});
