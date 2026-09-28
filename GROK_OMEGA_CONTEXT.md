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
