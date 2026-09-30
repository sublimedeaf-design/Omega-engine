import { readFileSync } from "node:fs";

const PRIVATE_REPO = "sublimedeaf-design/Omega-engines";
const CONTROL_REPO = "sublimedeaf-design/Omega-engine";
const SHA = /^[0-9a-f]{40}$/;
const RUN_URL = /\/actions\/runs\/([0-9]+)$/;
const STATE_ONLY_POLICY = JSON.parse(readFileSync(new URL("./state-only-paths.json", import.meta.url), "utf8"));
const STATE_ONLY_EXACT = new Set(STATE_ONLY_POLICY.exact_paths);
const STATE_ONLY_PATTERNS = STATE_ONLY_POLICY.patterns.map(value => new RegExp(value));

export function isStateOnlyPath(name) {
  if (typeof name !== "string" || !name || /[\\\r\n\0]/.test(name)) return false;
  if (name.split("/").some(part => ["", ".", ".."].includes(part))) return false;
  return STATE_ONLY_EXACT.has(name) || STATE_ONLY_PATTERNS.some(pattern => pattern.test(name));
}
const CONTROL_BOUND_CONTEXTS = [
  // Recovery proof is part of the release generation. A successful recovery from
  // an older control contract must be re-executed before candidate evidence can
  // consume it; otherwise mutable latest-status state can point at stale proof.
  "omega/hosted-recovery",
  "omega/recovery-attestation",
  "omega/federation-v3-release",
  "omega/candidate-evidence-root",
  "omega/release-evidence-staged",
  "omega/android-release-unsigned",
  "omega/resilience-certified",
  "omega/control-plane/signer",
  "omega/signer/key-availability",
  "omega/signer/continuity",
  "omega/android-release-signed",
  "omega/android-runtime-coldstart",
  "omega/release-live",
  "omega/release-certified",
  "omega/limited-distribution/apk-signed",
  "omega/limited-distribution/signer-continuity",
  "omega/limited-distribution/emulator-coldstart",
  "omega/limited-distribution/device-install",
  "omega/limited-distribution/android-installed-runtime",
  "omega/limited-distribution/evidence-autosync-scheduled",
  "omega/limited-distribution/evidence-autosync-live",
  "omega/limited-distribution/live-certified",
];

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

async function safeControlDescendant(controlToken, baseSha, headSha) {
  if (!SHA.test(baseSha) || !SHA.test(headSha)) return false;
  if (baseSha === headSha) return true;
  const compare = await gh(
    controlToken,
    `/repos/${CONTROL_REPO}/compare/${baseSha}...${headSha}?per_page=100`,
  );
  if (!["ahead", "identical"].includes(String(compare.status || ""))) return false;
  const files = Array.isArray(compare.files) ? compare.files : [];
  if (files.length >= 300) return false;
  return files.every(file => isStateOnlyPath(String(file.filename || "")) &&
    (!file.previous_filename || isStateOnlyPath(String(file.previous_filename))));
}

async function controlCompatibleStatus(controlToken, row, controlContractSha) {
  if (!row || String(row.state || "") !== "success") return false;
  const match = RUN_URL.exec(String(row.target_url || ""));
  if (!match) return false;

  const run = await gh(controlToken, `/repos/${CONTROL_REPO}/actions/runs/${match[1]}`);
  const head = String(run.head_sha || "");
  return safeControlDescendant(controlToken, controlContractSha, head);
}

async function generationAwareStatusMap(controlToken, map, controlContractSha) {
  const effective = { ...map };
  const freshness = {};
  for (const context of CONTROL_BOUND_CONTEXTS) {
    const row = map[context];
    if (!row || String(row.state || "") !== "success") {
      freshness[context] = false;
      continue;
    }
    const fresh = await controlCompatibleStatus(controlToken, row, controlContractSha);
    freshness[context] = fresh;
    if (!fresh) effective[context] = { ...row, state: "stale-control-generation" };
  }
  return { effective, freshness };
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
  const [row, controlMain] = await Promise.all([
    gh(controlToken, `/repos/${CONTROL_REPO}/contents/federation/epochs/current.json?ref=main`),
    gh(controlToken, `/repos/${CONTROL_REPO}/commits/main`),
  ]);
  const raw = Buffer.from(String(row.content || "").replace(/\n/g, ""), "base64").toString("utf8");
  const epoch = JSON.parse(raw);
  const primary = epoch.primary || {};
  const releaseEpoch = epoch.release_epoch || {};
  const rollover = epoch.release_rollover || {};
  const id = String(releaseEpoch.id || "");
  const source = String(primary.source_sha || "");
  const controlContractSha = String(releaseEpoch.control_contract_sha || "");
  const controlMainSha = String(controlMain.sha || "");
  const rolloverStage = String(rollover.stage || "");
  const controlCurrent = await safeControlDescendant(controlToken, controlContractSha, controlMainSha);
  const sourceCurrent = source === sourceSha;
  const certified =
    epoch.state === "PASS" &&
    primary.certification_state === "PASS" &&
    /^[0-9a-f]{64}$/.test(id) &&
    SHA.test(controlContractSha) &&
    ["CERTIFIED_PASS", "LIVE_CERTIFIED"].includes(rolloverStage) &&
    String(rollover.release_epoch_id || "") === id;
  const pass = certified && sourceCurrent && controlCurrent;
  return {
    pass,
    certified,
    sourceCurrent,
    controlCurrent,
    needsRollover: !sourceCurrent || !controlCurrent,
    source,
    id,
    sequence: Number(releaseEpoch.sequence || 0),
    controlContractSha,
    controlMainSha,
    rolloverStage,
  };
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

export function signerRetryAdmission(map) {
  const failure = map["omega/control-plane/signer"];
  if (!["failure", "error"].includes(String(failure?.state || "")) ||
      !/^AUTHORIZATION\b/.test(String(failure?.description || ""))) {
    return { allowed: true, reason: "no_current_authorization_failure" };
  }
  const failedAt = Date.parse(failure.updated_at || failure.created_at || "");
  const readiness = map["omega/signer/key-availability"];
  const readyAt = Date.parse(readiness?.updated_at || readiness?.created_at || "");
  if (readiness?.state === "success" && Number.isFinite(failedAt) &&
      Number.isFinite(readyAt) && readyAt > failedAt) {
    return { allowed: true, reason: "new_verified_key_availability" };
  }
  // Alternate backends remain eligible through explicit dispatch after their
  // capability is verified. A periodic wake is not evidence of changed authority.
  return { allowed: false, reason: "wait_for_changed_signer_authority" };
}

export async function reconcileGeneration({ privateToken, controlToken, targetUrl = "" } = {}) {
  if (!privateToken) throw new Error("OMEGA_PRIVATE_TOKEN_MISSING");
  if (!controlToken) throw new Error("OMEGA_CONTROL_TOKEN_MISSING");

  const main = await gh(privateToken, `/repos/${PRIVATE_REPO}/commits/main`);
  const sha = String(main.sha || "");
  if (!SHA.test(sha)) throw new Error("OMEGA_PRIVATE_MAIN_SHA_INVALID");

  const epoch = await observedEpoch(controlToken, sha);
  if (!epoch.pass) {
    if (epoch.needsRollover) {
      const rolloverActive =
        (await activeRuns(controlToken, "omega-release-federation-rollover.yml")) +
        (await activeRuns(controlToken, "omega-release-orchestrator-arm.yml"));
      let result;
      if (rolloverActive > 0) {
        result = { dispatched: false, reason: "already_active", active: rolloverActive };
      } else {
        result = await dispatch(controlToken, "omega-release-orchestrator-arm.yml", {});
      }
      await postState(
        privateToken,
        sha,
        "pending",
        `epoch-rollover:${result.reason} control=${epoch.controlMainSha.slice(0, 12)}`,
        targetUrl,
      );
      return {
        ok: true,
        source_sha: sha,
        observed_generation: null,
        action: result.reason,
        stage: "epoch-rollover",
        workflow: "omega-release-orchestrator-arm.yml",
        active: result.active,
        epoch,
      };
    }
    await postState(
      privateToken,
      sha,
      "pending",
      `wait-epoch-certification stage=${epoch.rolloverStage || "none"}`,
      targetUrl,
    );
    return { ok: true, source_sha: sha, observed_generation: null, action: "wait_epoch", epoch };
  }

  const observed = latestStatusMap(await statusHistory(privateToken, sha));
  const generationView = await generationAwareStatusMap(controlToken, observed, epoch.controlContractSha);
  const map = generationView.effective;
  const next = chooseStage(map);
  const generation = `${sha}:${epoch.id}`;

  if (next.stage === "canonical-signing") {
    const admission = signerRetryAdmission(map);
    if (!admission.allowed) {
      await postState(privateToken, sha, "pending", admission.reason, targetUrl);
      return {
        ok: true, source_sha: sha, observed_generation: generation,
        action: "wait_capability", stage: next.stage, reason: admission.reason,
        control_freshness: generationView.freshness,
      };
    }
  }

  if (next.complete) {
    await postState(privateToken, sha, "success", `generation converged epoch=${epoch.id.slice(0, 12)}`, targetUrl);
    return {
      ok: true,
      source_sha: sha,
      observed_generation: generation,
      action: "complete",
      stage: "complete",
      control_freshness: generationView.freshness,
    };
  }

  if (next.blocked) {
    await postState(privateToken, sha, "error", `${next.stage}:${next.reason}`, targetUrl);
    return {
      ok: false,
      source_sha: sha,
      observed_generation: generation,
      action: "blocked",
      control_freshness: generationView.freshness,
      ...next,
    };
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
    control_freshness: generationView.freshness,
  };
}

export const POLICY = Object.freeze({
  model: "level-triggered-generation-reconciliation",
  privateRepo: PRIVATE_REPO,
  controlRepo: CONTROL_REPO,
  oneActionPerReconcile: true,
  staleStatusSource: "full-status-history-newest-per-context",
  generationFields: ["source_sha", "release_epoch_id", "control_contract_sha"],
  requireCertifiedRollover: true,
  requireCurrentControlContract: true,
  controlDriftAction: "dispatch-release-orchestrator",
  controlBoundStatusRule: "status-run-head-must-be-control-contract-or-safe-descendant",
  recoveryProofGenerationBound: true,
  authorizationRetryRequiresChangedCapability: true,
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
