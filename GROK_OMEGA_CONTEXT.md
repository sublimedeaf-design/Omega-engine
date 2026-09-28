# OMEGA Context for Grok

> Public machine-readable/human-readable handoff for Grok/xAI and other coding agents.
>
> **Repository reality overrides this document.** Before changing OMEGA, resolve the live repository state, current `main` SHAs, current evidence, federation epoch/generation, release identity, active/stale writers and authoritative gates. Never treat this file as proof that a gate currently passes.

## 1. What OMEGA is

OMEGA is an evidence-driven, fail-closed football probability, market-value, release and runtime system.

It is not merely a prediction app. A result is considered valid only when source code, point-in-time data, model execution, evidence, release identity, signer identity and runtime state can be tied together reproducibly.

OMEGA must not claim success from assumptions.

Core operating principle:

```text
STATE -> EXECUTION -> MEASUREMENT -> EVIDENCE
```

Unknown, stale, conflicting, unverifiable or causally inconsistent state must fail closed.

Green engineering CI is not proof of predictive edge, profitability, runtime installation or Limited Distribution certification.

## 2. Repository authority model

### Canonical development authority

`sublimedeaf-design/Omega-engines`

This is the sole development source of truth and canonical evidence authority.

It contains the canonical football runtime, data/model logic, T-24/T-60 flows, settlement, Android source, CI, evidence contracts, security controls and release provenance.

### Dedicated federation peers

| Repository | Role | Production authority |
|---|---|---|
| `sublimedeaf-design/Omega-engines` | canonical core/runtime | source + canonical evidence |
| `sublimedeaf-design/Omega-agents` | bounded agent execution | none |
| `sublimedeaf-design/Omega-validation` | independent validation | approval only |
| `sublimedeaf-design/Omega-release` | exact-SHA release promotion | release only after validation |
| `sublimedeaf-design/Omega-recovery` | leases, recovery, backup runtime, disaster recovery | recovery coordinator only |
| `sublimedeaf-design/Jarv` | read-only federation witness / immutable anchor | none |

Hard federation rules:

- exact-SHA handoffs;
- a single authoritative writer for any canonical state;
- no split-brain;
- stale/conflicting/unverifiable state fails closed;
- no secrets in federation descriptors;
- success requires evidence;
- peer repositories do not replace `Omega-engines` as development source of truth;
- Jarv never promotes production code, T24/T60 evidence or Android releases.

### Public control-plane repository

`sublimedeaf-design/Omega-engine`

This public repository is a zero-cost control-plane/helper/validation/release-adapter and public handoff surface.

It is **not** the canonical development source of truth.

Do not let code or automation in this repository silently redefine canonical product state owned by `Omega-engines`.

## 3. Football and evidence pipeline

OMEGA uses point-in-time historical results, fixtures and timestamped market prices.

The canonical production path includes a Dixon-Coles + negative-binomial forecast engine. Research/challenger components may include calibration, residual ML, OOD/error detection, dynamic team state, Elo, player/replacement impact and market-consensus logic.

### T-24

T-24 must:

- discover eligible fixtures;
- use only information that was knowable at prediction time;
- generate history-only point-in-time forecasts;
- freeze eligible forecasts into immutable/hash-linked evidence;
- never leak future information.

### T-60

T-60 evaluates the approximately 45-75 minute pre-kickoff window.

It must use:

- the frozen T-24 forecast;
- current timestamped bookmaker/market prices;
- current validated metadata.

It must **not** silently refit the football model at T-60.

Provider-wide failure, unhealthy live candidates, stale data or unverifiable prices must fail closed rather than fabricate or overwrite canonical evidence.

### VALUE / selectivity

A `VALUE` result means only that the configured OMEGA value gate passed.

It does **not** mean:

- the wager is guaranteed to win;
- the model is profitable;
- predictive edge has been proven.

Required fields that are unknown/unverified, malformed or below configured thresholds must be rejected or remain unknown.

### Settlement

After an eligible post-kickoff delay, settlement records prospective evidence such as:

- outcome settlement;
- model-vs-market diagnostics;
- Brier score;
- log loss;
- shadow P&L;
- calibration/selection evidence.

Prospective and walk-forward evidence, not green CI alone, determines whether predictive claims are supportable.

## 4. Causal identity and provenance

OMEGA must bind execution and release claims to exact causal identity.

Relevant identity/provenance fields include, where applicable:

- canonical source SHA / PRODUCT_SOURCE_SHA;
- peer SHA vector;
- execution ID;
- release ID;
- release epoch/generation;
- federation epoch/generation;
- trusted clock/time authority;
- input/data hashes;
- evidence hashes;
- APK/AAB SHA-256;
- Android version/versionCode;
- signer certificate/signing identity;
- validated CI run;
- runtime/install/cold-start evidence.

A newer `main` commit is not automatically a validated release.

Promotion requires the normal validation/promotion chain for the exact SHA and current generation.

## 5. Android / Limited Distribution

The Android client is a read-only consumption layer for validated OMEGA evidence.

Release provenance must bind the APK/AAB to the exact validated source and signer identity.

A built or signed APK is **not** by itself `ANDROID_LIMITED_CERTIFIED`.

Separate runtime evidence may still be required, including:

- exact artifact cryptographic verification;
- release authority PASS;
- current-generation federation PASS;
- installation on the authorized physical device;
- physical cold starts;
- evidence autosync/runtime proof;
- post-live/exact-SHA verification;
- recovery/resilience evidence.

Never collapse build success, signing success, installation success and certification into one status.

## 6. Rules for Grok and other coding agents

Grok may act as an implementation, review, test and debugging agent, but must stay inside OMEGA authority boundaries.

Before any mutation:

1. verify tools and authentication;
2. read current canonical authorities;
3. resolve current `Omega-engines/main` SHA;
4. resolve the currently validated/promoted SHA separately;
5. resolve federation epoch/generation and peer SHA vector;
6. resolve execution/release identity;
7. read current evidence;
8. detect drift;
9. detect stale or concurrent writers;
10. determine the highest-priority executable blocker.

Then operate using:

```text
STATE -> EXECUTION -> MEASUREMENT -> EVIDENCE
```

Mandatory behavior:

- repository reality overrides prompt assumptions;
- do not invent PASS status;
- do not claim LIVE/CERTIFIED/FAILPROOF without direct current evidence;
- do not bypass exact-SHA validation;
- do not weaken fail-closed behavior;
- do not copy secrets into source, logs, prompts or evidence;
- do not make Jarv, Recovery, Agents or Validation the development source of truth;
- do not allow multiple canonical writers;
- do not silently replace working architecture just to introduce a new design;
- prefer idempotent, reversible, least-privilege changes;
- preserve causal identity, trusted time and provenance;
- validate after every mutation;
- merge/promote only through the canonical authority path;
- if evidence is missing, report UNKNOWN/BLOCKED rather than infer PASS.

## 7. Grok repository access model

Grok/xAI authorization is separate from ChatGPT/GitHub authorization.

Do not assume that a GitHub App installed for another agent automatically grants Grok access to private repositories.

For private repository work, Grok must operate in an explicitly GitHub-authorized checkout/runtime with the required least-privilege repository access.

Publicly readable context can be bootstrapped from this repository, but private repository content must only be consumed through an authorized Git/GitHub session.

No long-lived GitHub token, xAI credential, signing secret, provider API key or Android private key may be committed to this repository.

## 8. Current public handoff purpose

This file exists so Grok can learn the OMEGA architecture and invariants without relying on chat history.

It is an orientation document, not a current PASS certificate.

The first action of every Grok execution must therefore be to inspect the live repositories and evidence and reconcile this document against repository reality.

## 9. Definition of correctness for an agent

An agent has succeeded only when its claimed result is directly supported by current evidence for the exact affected SHA/generation.

A change that merely compiles, runs locally or passes one workflow is not sufficient to claim full OMEGA completion.

The invariant is:

```text
CLAIM <= EVIDENCE
```

Never allow the scope or certainty of a claim to exceed the evidence that directly proves it.

---

## 10. Canonical standards and norms registry

This section mirrors the current canonical governance registry from `sublimedeaf-design/Omega-engines/.omega/standards.json`.

**Repository reality still overrides this copy.** Grok must re-read the canonical registry before release-relevant work, because standard versions, review dates and invariant states may change.

### 10.1 Standards-governance policy

Current canonical policy:

- enforcement mode: `staged_enforcement`;
- standard-version drift action: `BLOCK_FINAL_AUDIT`;
- partial-control claim action: `FORBID_COMPLIANCE_CLAIM`;
- enforced-control regression action: `BLOCK_FINAL_AUDIT`;
- official HTTPS sources are required: `true`;
- maximum standards review interval: `30` days;
- future-clock tolerance: `300` seconds;
- strict target: `all_release_required_invariants_enforced`.

Governance semantics:

- release-relevant external standards require an official HTTPS source, a pinned/current baseline, `last_verified_at` and a bounded review interval;
- overdue release-relevant standards become `STANDARD_VERSION_DRIFT` and block final audit;
- universal invariants are explicitly `ENFORCED`, `PARTIAL` or `PLANNED`;
- only `ENFORCED` controls may be represented as OMEGA-compliant;
- `PARTIAL` and `PLANNED` are visible engineering debt, not PASS;
- an `ENFORCED` control may not silently regress;
- standards-complete certification requires every release-required invariant to be `ENFORCED` for the exact release generation.

### 10.2 External engineering/security baselines

| Standard / baseline | Canonical baseline | Registry status | Release-relevant | Review interval | Last verified |
|---|---|---:|---:|---:|---|
| `slsa` | 1.2 | approved | yes | 30 days | 2026-09-28T00:00:00Z |
| `nist_ssdf` | SP 800-218 v1.1 final | final_plus_draft_watch | yes | 14 days | 2026-09-28T00:00:00Z |
| `nist_ai_rmf` | AI RMF 1.0 | final_plus_revision_watch | yes | 14 days | 2026-09-28T00:00:00Z |
| `dora` | 2026 five-metric software delivery performance model | living | no | 30 days | 2026-09-28T00:00:00Z |
| `openssf_scorecard` | Scorecard 5.5.0 / scorecard-action 2.4.4 | current_release | yes | 14 days | 2026-09-28T00:00:00Z |
| `owasp_masvs` | current MASVS/MASTG living standard | living | yes | 30 days | 2026-09-28T00:00:00Z |
| `android_persistent_work` | WorkManager recommended for reliable persistent work | living_platform_guidance | yes | 30 days | 2026-09-28T00:00:00Z |

The canonical external baseline set therefore currently includes:

- **SLSA 1.2** for software supply-chain integrity/provenance;
- **NIST SSDF SP 800-218 v1.1 final**, while watching the Rev. 1 / SSDF v1.2 draft;
- **NIST AI RMF 1.0**, with revision watch;
- **DORA 2026 five-metric software-delivery performance model**;
- **OpenSSF Scorecard 5.5.0 / scorecard-action 2.4.4**;
- **OWASP MASVS/MASTG living standard** for mobile application security;
- **Android persistent-work guidance**, with WorkManager as the recommended reliable persistent-work path.

### 10.3 Universal OMEGA invariants

Current registry total: **37 invariants** — **15 ENFORCED**, **11 PARTIAL**, **11 PLANNED**.

| Invariant | Current state | Release-required |
|---|---:|---:|
| `CANONICAL_TRUTH` | **ENFORCED** | yes |
| `IMMUTABLE_GENERATION_IDENTITY` | **ENFORCED** | yes |
| `SINGLE_AUTHORITATIVE_WRITER` | **ENFORCED** | yes |
| `GENERATION_FENCED_WRITES` | **ENFORCED** | yes |
| `IDEMPOTENT_SIDE_EFFECTS` | **PARTIAL** | yes |
| `BUILD_ONCE_PROMOTE_SAME_BITS` | **PARTIAL** | yes |
| `NO_HIDDEN_STATE` | **PARTIAL** | yes |
| `MACHINE_ENFORCED_POLICY` | **ENFORCED** | yes |
| `DETERMINISTIC_FALLBACK_LADDER` | **PARTIAL** | yes |
| `BOUNDED_EXECUTION` | **PARTIAL** | yes |
| `END_TO_END_CAUSAL_IDENTITY` | **ENFORCED** | yes |
| `TIME_IS_CORRECTNESS` | **ENFORCED** | yes |
| `CLOCK_AUTHORITY` | **ENFORCED** | yes |
| `FRESHNESS_GATE` | **PARTIAL** | yes |
| `EXPLICIT_COMPATIBILITY` | **PARTIAL** | yes |
| `API_LIFECYCLE` | **PLANNED** | yes |
| `SEPARATION_OF_DUTIES` | **PLANNED** | yes |
| `LEAST_PRIVILEGE` | **PARTIAL** | yes |
| `DURABLE_FAILURE_EVIDENCE` | **PARTIAL** | yes |
| `UNAMBIGUOUS_PASS_SEMANTICS` | **ENFORCED** | yes |
| `PHASE_SPECIFIC_ATTESTATION` | **ENFORCED** | yes |
| `RELEASE_GENERATION_FREEZE` | **ENFORCED** | yes |
| `CLEAN_RECOVERY_RECONSTRUCTION` | **ENFORCED** | yes |
| `BACKUP_RESTORE_RTO_RPO` | **PARTIAL** | yes |
| `DEPENDENCY_CRITICALITY` | **PLANNED** | yes |
| `RESOURCE_QUOTA_ADMISSION` | **PLANNED** | yes |
| `CLAIM_EVIDENCE_MATCH` | **ENFORCED** | yes |
| `STANDARD_VERSION_DRIFT_BLOCKER` | **ENFORCED** | yes |
| `AUDITABLE_PRIVILEGED_ACTIONS` | **PARTIAL** | yes |
| `SUPPLY_CHAIN_STANDARD_MAPPING` | **ENFORCED** | yes |
| `THREAT_MODEL_SECURITY_BASELINE` | **PLANNED** | yes |
| `SLO_ERROR_BUDGET` | **PLANNED** | yes |
| `INCIDENT_POSTMORTEM_LEARNING` | **PLANNED** | no |
| `ANDROID_PERSISTENT_WORK_GOLDEN_PATH` | **PLANNED** | yes |
| `ML_TRAIN_SERVE_PARITY` | **PLANNED** | yes |
| `DATA_PRIVACY_LIFECYCLE` | **PLANNED** | yes |
| `LICENSE_COMPLIANCE` | **PLANNED** | yes |

Grok must preserve the distinction between implemented intent and proven enforcement. A `PARTIAL` or `PLANNED` invariant must never be rewritten into a success claim merely because related code exists.

### 10.4 Canonical invariant meanings

The registry names are normative. Grok must interpret them conservatively:

- `CANONICAL_TRUTH`: one declared source of truth; conversational assumptions never override repository reality.
- `IMMUTABLE_GENERATION_IDENTITY`: release/execution generation identity must be immutable and provenance-bound.
- `SINGLE_AUTHORITATIVE_WRITER`: no concurrent canonical writers for the same authoritative state.
- `GENERATION_FENCED_WRITES`: stale generations cannot write into current-generation canonical state.
- `IDEMPOTENT_SIDE_EFFECTS`: retries must not create duplicate or contradictory side effects.
- `BUILD_ONCE_PROMOTE_SAME_BITS`: promotion should use the exact already-validated artifact, not silently rebuild different bits.
- `NO_HIDDEN_STATE`: correctness-critical state must be explicit, reconstructable and inspectable.
- `MACHINE_ENFORCED_POLICY`: critical governance belongs in executable checks, not only prose.
- `DETERMINISTIC_FALLBACK_LADDER`: fallback ordering and outcomes must be explicit and reproducible.
- `BOUNDED_EXECUTION`: autonomous work must have bounded scope/resources/time/side effects.
- `END_TO_END_CAUSAL_IDENTITY`: data, execution, evidence, artifact and release claims must share traceable causal identity.
- `TIME_IS_CORRECTNESS`: temporal ordering and point-in-time boundaries are correctness properties.
- `CLOCK_AUTHORITY`: trusted clock authority governs time-sensitive state and evidence.
- `FRESHNESS_GATE`: stale evidence/data/configuration cannot be treated as current.
- `EXPLICIT_COMPATIBILITY`: compatibility must be proven/declared, never inferred from superficial success.
- `API_LIFECYCLE`: external/internal API versions, deprecation and compatibility need governed lifecycle management.
- `SEPARATION_OF_DUTIES`: implementation, validation and promotion authorities must remain appropriately separated.
- `LEAST_PRIVILEGE`: every human/agent/workflow receives only the permissions required for its bounded role.
- `DURABLE_FAILURE_EVIDENCE`: failures must leave durable inspectable evidence instead of disappearing into logs.
- `UNAMBIGUOUS_PASS_SEMANTICS`: PASS must have one machine-verifiable meaning for each phase/gate.
- `PHASE_SPECIFIC_ATTESTATION`: each lifecycle phase produces evidence specific to that phase.
- `RELEASE_GENERATION_FREEZE`: a release generation is frozen before final promotion/certification.
- `CLEAN_RECOVERY_RECONSTRUCTION`: recovery must reconstruct from canonical durable state rather than hidden mutable state.
- `BACKUP_RESTORE_RTO_RPO`: recovery objectives and restore evidence must be explicit and tested.
- `DEPENDENCY_CRITICALITY`: dependencies must be classified by their impact on correctness/release/runtime.
- `RESOURCE_QUOTA_ADMISSION`: work should be admitted only when required bounded resources/quotas are available.
- `CLAIM_EVIDENCE_MATCH`: claim scope and certainty may never exceed directly supporting evidence.
- `STANDARD_VERSION_DRIFT_BLOCKER`: stale required standards block final audit rather than silently aging out.
- `AUDITABLE_PRIVILEGED_ACTIONS`: privileged mutations must be attributable and auditable.
- `SUPPLY_CHAIN_STANDARD_MAPPING`: supply-chain controls, locks, SBOM/provenance and external standards must map to executable evidence.
- `THREAT_MODEL_SECURITY_BASELINE`: security-critical releases require an explicit threat-model baseline.
- `SLO_ERROR_BUDGET`: reliability needs measurable service objectives/error-budget policy, not subjective availability claims.
- `INCIDENT_POSTMORTEM_LEARNING`: incidents should become durable regressions, controls, runbooks or curriculum lessons.
- `ANDROID_PERSISTENT_WORK_GOLDEN_PATH`: Android background work must use the platform-supported reliable path.
- `ML_TRAIN_SERVE_PARITY`: training/evaluation/serving semantics must not drift silently.
- `DATA_PRIVACY_LIFECYCLE`: collection, retention, access and disposal of data require lifecycle controls.
- `LICENSE_COMPLIANCE`: code/data/model dependencies require licensing provenance and compatibility checks.

### 10.5 Canonical migration order

The registry currently prioritizes standards migration in this order:

1. `MACHINE_ENFORCED_POLICY`
2. `CANONICAL_TRUTH`
3. `IMMUTABLE_GENERATION_IDENTITY`
4. `SINGLE_AUTHORITATIVE_WRITER`
5. `GENERATION_FENCED_WRITES`
6. `IDEMPOTENT_SIDE_EFFECTS`
7. `BUILD_ONCE_PROMOTE_SAME_BITS`
8. `SEPARATION_OF_DUTIES`
9. `LEAST_PRIVILEGE`
10. `END_TO_END_CAUSAL_IDENTITY`
11. `CLOCK_AUTHORITY`
12. `FRESHNESS_GATE`
13. `DEPENDENCY_CRITICALITY`
14. `RESOURCE_QUOTA_ADMISSION`
15. `SLO_ERROR_BUDGET`
16. `ANDROID_PERSISTENT_WORK_GOLDEN_PATH`
17. `ML_TRAIN_SERVE_PARITY`
18. `THREAT_MODEL_SECURITY_BASELINE`
19. `DATA_PRIVACY_LIFECYCLE`
20. `LICENSE_COMPLIANCE`

This ordering is a migration priority, not permission to ignore other applicable release gates.

## 11. Acceptance and release gates

OMEGA uses evidence gates rather than feature-count or architecture-count claims.

### G0 — Handoff integrity

Every material handoff identifies owner role, base/head SHA, scope, risks, verification, evidence, temporal-integrity impact, security impact, rollback and next owner.

### G1 — Code correctness

Unit/regression tests pass, Python sources compile and dependency resolution is internally consistent.

### G2 — Temporal integrity

Forecast-affecting data/model/runtime changes must prove point-in-time boundaries, immutable T-24 behavior and leakage controls.

### G3 — Runtime integrity

Repository audit and runtime preflight pass; systemic/provider failures fail closed and evidence writes remain verifiable.

### G4 — Client integrity

Android changes require lint/build success, absence of embedded secrets, visible provenance and preservation of read-only client behavior.

### G5 — Final audit

The final release audit must pass on the exact PR-head SHA.

### G6 — Integration

Applicable pre-merge gates must pass before merge, and the resulting exact `main` SHA must be verified again. Pre-merge PASS is not post-merge evidence.

### G7 — Artifact provenance

Promoted APK/release artifacts must identify exact `main` SHA, cryptographic digest and signer identity; stale artifacts may not be promoted.

### G8 — Predictive and decision evidence

Champion/predictive/economic promotion additionally requires frozen chronological out-of-sample evidence with:

- point-in-time feature/market integrity;
- Brier score and log loss;
- calibration diagnostics;
- coverage and sample size;
- paired-fixture comparability;
- separation of history-only forecast quality from market-informed decision quality;
- EV assumptions, realised ROI/yield, CLV where available and drawdown;
- segmented robustness;
- shadow/prospective evidence where required;
- content hashes tied to exact code/model/data provenance.

No number of models, agents, LLMs or engineering features substitutes for G8.

## 12. Statistical, ML and data norms

- End-to-end reproducibility is mandatory.
- True chronological point-in-time walk-forward evaluation is mandatory for predictive evidence.
- Future results, same-event results, post-cutoff intelligence and leakage are prohibited.
- Calibration quality uses proper scoring rules; hit rate alone is insufficient.
- Economic/value evidence is separate from forecast quality.
- Robustness must survive relevant segmentation rather than cherry-picked slices.
- `NO BET` is a first-class correct output.
- Champion/challenger promotion uses frozen predeclared out-of-sample criteria.
- Backtests are hypothesis-generating until they survive the required shadow/prospective path.
- LLM/agent reasoning can explain, audit and orchestrate; it cannot override statistical evidence without new verifiable data.
- Training and held-out evaluation must remain separated; never tune on the held-out target.
- Market consensus is context/baseline, not automatically independent predictive edge.
- Settlement never retroactively mutates selection criteria after outcomes are known.

## 13. Security, supply-chain and platform norms

Grok must preserve at minimum:

- fail-closed input and provider handling;
- secrets never committed, logged or embedded in APKs;
- Android private keys protected by Android Keystore;
- repository/workflow credentials scoped by least privilege;
- agent workers do not hold unnecessary repository-write authority;
- third-party actions and release-critical toolchain inputs pinned;
- dependency/install integrity controls preserved;
- SBOM/provenance generation preserved;
- exact-source and signer continuity preserved;
- same-package/same-signer continuity for Android in-place updates;
- Android OS installer/device-owner security boundaries are never bypassed or falsely described;
- malformed/oversized/non-finite/untrusted inputs are adversarially tested;
- workflow/runner infrastructure failure is reported as infrastructure evidence, not falsely converted into code PASS/FAIL;
- privileged operations remain attributable and auditable.

## 14. Reliability, SRE and autonomous-operation norms

- State-producing workflows are serialized/transactional where authority requires it.
- Candidate evidence is created before canonical promotion.
- Canonical promotion happens only after integrity/health checks.
- Retries must trend toward idempotence and avoid duplicate writers or artifacts.
- Recovery reconstructs from canonical durable state.
- Failover never creates simultaneous authoritative writers.
- Queue/resource exhaustion must not silently degrade correctness.
- SLO/error-budget controls remain explicitly `PLANNED` until implemented and evidenced.
- Recovery/RTO/RPO controls remain `PARTIAL` until fully evidenced.
- Every material incident should become a regression test, invariant, runbook entry or curriculum lesson.

## 15. Multi-agent norms

Canonical roles include orchestrator, data/model, backend/prediction, Android/GUI, QA/audit and release/CI.

Rules:

- one bounded implementation owner per material change;
- independent QA/evaluation can veto;
- isolated branches/PRs are preferred for autonomous mutations;
- agents do not bypass CI, QA, release or temporal gates;
- handoffs record exact base/head SHA, evidence, risk, blockers, owner and safe next action;
- failed attempts do not become accepted knowledge;
- learned corrections become durable tests, curriculum, runbooks or evidence artifacts;
- autonomy means bounded execution, never unrestricted authority.

## 16. Grok bootstrap requirement

Before Grok treats this document as operational context, it must compare it against the current canonical files in `Omega-engines`, especially:

- `.omega/standards.json`;
- `ACCEPTANCE.md`;
- `.omega/OMEGA_AGENT_ACADEMY.md`;
- `STATUS.md`;
- `docs/REPOSITORY_MESH.md`;
- current control-plane/evidence contracts;
- current exact-main and validated/promoted SHAs.

If any conflict exists, the current canonical repository state wins.

This public file is therefore a complete **handoff snapshot**, not an immutable substitute for the canonical private governance registry.

