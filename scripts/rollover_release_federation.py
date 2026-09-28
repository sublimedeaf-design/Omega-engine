#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

API = "https://api.github.com"
PRIVATE_TOKEN = os.environ["OMEGA_BOOTSTRAP_TOKEN"].strip()
CONTROL_TOKEN = os.environ["OMEGA_CONTROL_TOKEN"].strip()
TARGET = os.environ["OMEGA_TARGET_SOURCE_SHA"].strip()
SOURCE_REF = os.environ["OMEGA_TARGET_SOURCE_REF"].strip()
CONTROL_CONTRACT_SHA = os.environ["OMEGA_CONTROL_CONTRACT_SHA"].strip()

CORE = "sublimedeaf-design/Omega-engines"
CONTROL = "sublimedeaf-design/Omega-engine"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
RELEASE_REF = re.compile(r"^release/[A-Za-z0-9._/-]+$")
PEERS = [
    ("sublimedeaf-design/Omega-recovery", "control_recovery"),
    ("sublimedeaf-design/Omega-agents", "agent_execution"),
    ("sublimedeaf-design/Omega-validation", "independent_validation"),
    ("sublimedeaf-design/Omega-release", "release_promotion"),
]
FILES = [
    "OMEGA_INTEGRATION_CONTRACT.json",
    "OMEGA_MESH.json",
    *[f"agents/agent-{i:02d}.json" for i in range(1, 7)],
    "state/source-pin.json",
]
IMMUTABLE_PREFIX = "federation/epochs/releases"


def api(token: str, method: str, path: str, payload=None, *, allow_404: bool = False):
    data = None if payload is None else json.dumps(payload, separators=(",", ":")).encode()
    req = urllib.request.Request(
        API + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "OMEGA-immutable-release-epoch",
            **({"Content-Type": "application/json"} if data is not None else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as response:
            raw = response.read(8 * 1024 * 1024 + 1)
            if len(raw) > 8 * 1024 * 1024:
                raise SystemExit("OMEGA_FEDERATION_API_RESPONSE_TOO_LARGE")
            return json.loads(raw or b"{}")
    except urllib.error.HTTPError as exc:
        if allow_404 and exc.code == 404:
            return None
        detail = exc.read(65536).decode("utf-8", "replace")
        raise SystemExit(
            f"OMEGA_FEDERATION_GITHUB_HTTP_{exc.code}:{path}:{detail[:1000]}"
        ) from exc


def private_api(method: str, path: str, payload=None, *, allow_404: bool = False):
    return api(PRIVATE_TOKEN, method, path, payload, allow_404=allow_404)


def control_api(method: str, path: str, payload=None, *, allow_404: bool = False):
    return api(CONTROL_TOKEN, method, path, payload, allow_404=allow_404)


def content(token: str, repo: str, path: str, ref: str):
    q = urllib.parse.quote(ref, safe="")
    row = api(token, "GET", f"/repos/{repo}/contents/{path}?ref={q}")
    raw = base64.b64decode(str(row["content"]).replace("\n", ""), validate=True)
    return row, raw


def latest_main(repo: str) -> str:
    return private_api("GET", f"/repos/{repo}/git/ref/heads/main")["object"]["sha"]


def verify_peer_baseline(repo: str, expected_source: str, expected_commit: str) -> dict:
    # Read-only peer verification. Release epochs never mutate peer repositories.
    base = latest_main(repo)
    if base != expected_commit:
        raise SystemExit(f"OMEGA_PEER_MAIN_DRIFT:{repo}:{base}!={expected_commit}")

    docs = {}
    for peer_path in FILES:
        _, raw = content(PRIVATE_TOKEN, repo, peer_path, base)
        docs[peer_path] = json.loads(raw)

    pinned = str(docs["state/source-pin.json"].get("source_sha") or "")
    contract = str((docs["OMEGA_INTEGRATION_CONTRACT.json"].get("source") or {}).get("sha") or "")
    mesh = str(docs["OMEGA_MESH.json"].get("source_pin") or "")
    agents = {
        str(docs[f"agents/agent-{i:02d}.json"].get("source_sha") or "")
        for i in range(1, 7)
    }
    if not HEX40.fullmatch(pinned):
        raise SystemExit(f"OMEGA_PEER_SOURCE_INVALID:{repo}:{pinned}")
    if contract != pinned or mesh != pinned or agents != {pinned}:
        raise SystemExit(f"OMEGA_PEER_BASELINE_SPLIT:{repo}")
    if pinned != expected_source:
        raise SystemExit(
            f"OMEGA_PEER_UNEXPECTED_BASELINE_SOURCE:{repo}:{pinned}!={expected_source}"
        )
    return {
        "repository": repo,
        "sha": base,
        "baseline_source_sha": pinned,
    }


def canonical_sha256(payload: dict) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


if not HEX40.fullmatch(TARGET):
    raise SystemExit("OMEGA_RELEASE_FEDERATION_TARGET_INVALID")
if not HEX40.fullmatch(CONTROL_CONTRACT_SHA):
    raise SystemExit("OMEGA_RELEASE_FEDERATION_CONTROL_SHA_INVALID")
if (
    not RELEASE_REF.fullmatch(SOURCE_REF)
    or ".." in SOURCE_REF
    or SOURCE_REF.startswith("/")
    or SOURCE_REF.startswith("-")
):
    raise SystemExit("OMEGA_RELEASE_FEDERATION_REF_INVALID")

tip = private_api(
    "GET", f"/repos/{CORE}/commits/{urllib.parse.quote(SOURCE_REF, safe='')}"
)["sha"]
if tip != TARGET:
    raise SystemExit(f"OMEGA_RELEASE_FEDERATION_REF_MOVED:{tip}!={TARGET}")

current_private_main = latest_main(CORE)
if current_private_main != TARGET:
    raise SystemExit(
        f"OMEGA_RELEASE_FEDERATION_STALE_GENERATION:{TARGET}!={current_private_main}"
    )

status = private_api("GET", f"/repos/{CORE}/commits/{TARGET}/status?per_page=100")
latest = {}
for row in status.get("statuses", []):
    ctx = str(row.get("context") or "")
    stamp = str(row.get("updated_at") or row.get("created_at") or "")
    if ctx and (ctx not in latest or stamp > str(latest[ctx].get("_omega_stamp") or "")):
        latest[ctx] = {**row, "_omega_stamp": stamp}
required = {
    "omega/hosted-ci/python311",
    "omega/hosted-ci/python313",
    "omega/hosted-ci/python314",
    "omega/hosted-ci/storage",
    "omega/hosted-governance",
    "omega/hosted-android",
    "omega/exact-final-validation",
}
bad = sorted(x for x in required if (latest.get(x) or {}).get("state") != "success")
if bad:
    raise SystemExit(
        "OMEGA_RELEASE_FEDERATION_PREREQUISITE_NOT_PASS:" + ",".join(bad)
    )

control_head = control_api("GET", f"/repos/{CONTROL}/git/ref/heads/main")["object"]["sha"]
meta, raw = content(CONTROL_TOKEN, CONTROL, "federation/epochs/current.json", "main")
epoch = json.loads(raw)
primary_epoch = epoch.get("primary") or {}
prior_release_epoch = epoch.get("release_epoch") or {}
prior_control_contract = str(prior_release_epoch.get("control_contract_sha") or "")
prior_sequence_raw = prior_release_epoch.get("sequence", 0)
if isinstance(prior_sequence_raw, bool) or not isinstance(prior_sequence_raw, int) or prior_sequence_raw < 0:
    raise SystemExit("OMEGA_RELEASE_EPOCH_SEQUENCE_INVALID")
prior_sequence = int(prior_sequence_raw)
prior_state = str(epoch.get("state") or "")
prior_certification = str(primary_epoch.get("certification_state") or "")
same_target = str(primary_epoch.get("source_sha") or "") == TARGET
same_ref = str(primary_epoch.get("source_ref") or "") == SOURCE_REF
control_deviation = bool(
    prior_control_contract
    and HEX40.fullmatch(prior_control_contract)
    and prior_control_contract != CONTROL_CONTRACT_SHA
)
authority_pass = prior_state == "PASS" and prior_certification == "PASS"
live_certified = (
    (latest.get("omega/live-certified") or {}).get("state") == "success"
    or (latest.get("omega/limited-distribution/live-certified") or {}).get("state") == "success"
)
safe_unfinished_supersede = (
    prior_state == "NOT_EXECUTED"
    and prior_certification == "NOT_EXECUTED"
    and TARGET == current_private_main
    and (
        control_deviation
        or not same_target
        or not same_ref
    )
)
safe_certified_pre_live_supersede = (
    authority_pass
    and same_target
    and same_ref
    and control_deviation
    and not live_certified
)
if not authority_pass and not safe_unfinished_supersede:
    raise SystemExit("OMEGA_FEDERATION_AUTHORITY_NOT_PASS")
if live_certified and same_target and same_ref and control_deviation:
    raise SystemExit("OMEGA_RELEASE_EPOCH_LIVE_CERTIFIED_IMMUTABLE")
if safe_unfinished_supersede:
    print(
        f"OMEGA_RELEASE_EPOCH_SUPERSEDE_UNFINISHED_CONTROL_DEVIATION:"
        f"{prior_control_contract}->{CONTROL_CONTRACT_SHA}"
    )
if safe_certified_pre_live_supersede:
    print(
        f"OMEGA_RELEASE_EPOCH_SUPERSEDE_CERTIFIED_PRE_LIVE_CONTROL_DEVIATION:"
        f"{prior_control_contract}->{CONTROL_CONTRACT_SHA}"
    )

current_source = str(primary_epoch.get("source_sha") or "")
if not HEX40.fullmatch(current_source):
    raise SystemExit("OMEGA_FEDERATION_AUTHORITY_SOURCE_INVALID")

authority_peers = {
    str(row.get("repository") or ""): row for row in (epoch.get("peers") or [])
}
if set(authority_peers) != {repo for repo, _ in PEERS}:
    raise SystemExit("OMEGA_FEDERATION_AUTHORITY_PEER_SET_MISMATCH")

baseline_source = str(
    prior_release_epoch.get("peer_contract_source_sha") or current_source
)
sequence = prior_sequence + 1
if not HEX40.fullmatch(baseline_source):
    raise SystemExit("OMEGA_FEDERATION_PEER_BASELINE_SOURCE_INVALID")

peer_rows = []
for repo, role in PEERS:
    row = authority_peers[repo]
    expected_commit = str(row.get("sha") or "")
    if not HEX40.fullmatch(expected_commit):
        raise SystemExit(f"OMEGA_FEDERATION_AUTHORITY_PEER_SHA_INVALID:{repo}")
    # Keep the historic variable name expected_source deliberately: the control
    # integrity contract asserts that a rollover is CAS-bound to the prior
    # peer source identity. The operation is read-only.
    expected_source = baseline_source
    checked = verify_peer_baseline(repo, expected_source, expected_commit)
    peer_rows.append(
        {
            "repository": repo,
            "role": role,
            "sha": checked["sha"],
            "baseline_source_sha": checked["baseline_source_sha"],
        }
    )

seed_core = {
    "schema_version": 1,
    "release_epoch_version": 2,
    "sequence": sequence,
    "authority_repository": CONTROL,
    "control_contract_sha": CONTROL_CONTRACT_SHA,
    "source": {
        "repository": CORE,
        "sha": TARGET,
        "ref": SOURCE_REF,
    },
    "parent": {
        "source_sha": current_source,
        "release_epoch_id": prior_release_epoch.get("id"),
        "control_contract_sha": prior_control_contract or None,
        "sequence": prior_sequence,
    },
    "source_binding_mode": "external_epoch",
    "peer_contract_source_sha": baseline_source,
    "peers": peer_rows,
    "hf": epoch.get("hf") or {},
    "policy": {
        "immutable_seed": True,
        "new_deviation_requires_new_epoch": True,
        "peer_repositories_are_read_only_during_rollover": True,
        "old_evidence_runs_are_never_mutated": True,
        "one_staged_child_sha_per_epoch": True,
        "monotonic_epoch_sequence": True,
        "supersedes_unfinished_epoch_on_control_deviation": True,
        "supersedes_unfinished_epoch_on_new_private_generation": True,
        "current_private_main_is_generation_fence": True,
        "supersedes_certified_pre_live_epoch_on_control_deviation": True,
        "live_certified_epoch_is_immutable": True,
    },
}
epoch_id = canonical_sha256(seed_core)
seed_path = f"{IMMUTABLE_PREFIX}/{TARGET}-{epoch_id[:16]}.json"
seed = {
    **seed_core,
    "release_epoch_id": epoch_id,
    "state": "OPEN",
    "immutable_path": seed_path,
}

existing = control_api(
    "GET",
    f"/repos/{CONTROL}/contents/{urllib.parse.quote(seed_path, safe='/')}?ref=main",
    allow_404=True,
)
resume_existing_seed = False
if existing is not None:
    existing_raw = base64.b64decode(
        str(existing["content"]).replace("\n", ""), validate=True
    )
    existing_seed = json.loads(existing_raw)
    if canonical_sha256({k: v for k, v in existing_seed.items() if k not in {"release_epoch_id", "state", "immutable_path"}}) != epoch_id:
        raise SystemExit("OMEGA_RELEASE_EPOCH_IMMUTABLE_SEED_COLLISION")
    current_release_epoch = epoch.get("release_epoch") or {}
    if (
        (epoch.get("primary") or {}).get("source_sha") == TARGET
        and current_release_epoch.get("id") == epoch_id
    ):
        print(
            json.dumps(
                {
                    "ok": True,
                    "already_current": True,
                    "source_sha": TARGET,
                    "source_ref": SOURCE_REF,
                    "release_epoch_id": epoch_id,
                    "immutable_path": seed_path,
                },
                sort_keys=True,
            )
        )
        raise SystemExit(0)

    # GitHub may commit a Contents API mutation and still return a transient
    # 5xx to the client. Treat an exact matching immutable seed as the durable
    # side effect and resume projection only when all control-head movement
    # since the requested contract is state-only.
    resume_head = control_api("GET", f"/repos/{CONTROL}/git/ref/heads/main")["object"]["sha"]
    if not HEX40.fullmatch(resume_head):
        raise SystemExit("OMEGA_RELEASE_EPOCH_RESUME_HEAD_INVALID")
    compare = control_api(
        "GET",
        f"/repos/{CONTROL}/compare/{CONTROL_CONTRACT_SHA}...{resume_head}",
    )
    compare_status = str(compare.get("status") or "")
    behind_by = int(compare.get("behind_by") or 0)
    if compare_status not in {"ahead", "identical"} or behind_by != 0:
        raise SystemExit(
            f"OMEGA_RELEASE_EPOCH_RESUME_HISTORY_INVALID:{compare_status}:behind={behind_by}"
        )
    changed = [str(row.get("filename") or "") for row in (compare.get("files") or [])]
    unsafe = [
        path for path in changed
        if not (
            path == seed_path
            or path.startswith("federation/epochs/")
            or path.startswith("bootstrap/omega/")
        )
    ]
    if unsafe:
        raise SystemExit(
            "OMEGA_RELEASE_EPOCH_RESUME_UNSAFE_CONTROL_DRIFT:" + ",".join(sorted(unsafe))
        )
    resume_existing_seed = True
    print(
        f"OMEGA_RELEASE_EPOCH_RESUME_EXISTING_SEED:"
        f"epoch={epoch_id}:head={resume_head}:files={len(changed)}"
    )

if not resume_existing_seed:
    if control_head != CONTROL_CONTRACT_SHA:
        raise SystemExit(
            f"OMEGA_CONTROL_MAIN_DRIFT:{control_head}!={CONTROL_CONTRACT_SHA}"
        )

    seed_payload = {
        "message": f"Release epoch: freeze immutable seed {TARGET[:12]} {epoch_id[:12]}",
        "content": base64.b64encode(
            (json.dumps(seed, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        ).decode(),
        "branch": "main",
    }
    seed_result = control_api(
        "PUT",
        f"/repos/{CONTROL}/contents/{urllib.parse.quote(seed_path, safe='/')}",
        seed_payload,
    )
    seed_commit = str((seed_result.get("commit") or {}).get("sha") or "")
    if not HEX40.fullmatch(seed_commit):
        raise SystemExit("OMEGA_RELEASE_EPOCH_SEED_COMMIT_INVALID")

    after_seed_head = control_api("GET", f"/repos/{CONTROL}/git/ref/heads/main")["object"]["sha"]
    if after_seed_head != seed_commit:
        raise SystemExit(
            f"OMEGA_RELEASE_EPOCH_CONTROL_DRIFT_AFTER_SEED:{after_seed_head}!={seed_commit}"
        )

projection = json.loads(json.dumps(epoch))
projection["state"] = "NOT_EXECUTED"
projection["blockers"] = ["external read-only exact-SHA peer proof pending"]
primary = projection.setdefault("primary", {})
primary["source_sha"] = TARGET
primary["source_ref"] = SOURCE_REF
primary["certification_state"] = "NOT_EXECUTED"
primary["pull_request"] = None
projection["release_epoch"] = {
    "contract_version": 2,
    "id": epoch_id,
    "sequence": sequence,
    "immutable_path": seed_path,
    "control_contract_sha": CONTROL_CONTRACT_SHA,
    "parent_epoch_id": prior_release_epoch.get("id"),
    "parent_control_contract_sha": prior_control_contract or None,
    "parent_sequence": prior_sequence,
    "source_binding_mode": "external_epoch",
    "peer_contract_source_sha": baseline_source,
    "new_deviation_requires_new_epoch": True,
    "old_evidence_runs_are_never_mutated": True,
    "monotonic_epoch_sequence": True,
    "supersedes_unfinished_epoch_on_control_deviation": True,
    "supersedes_unfinished_epoch_on_new_private_generation": True,
    "current_private_main_is_generation_fence": True,
    "supersedes_certified_pre_live_epoch_on_control_deviation": True,
    "live_certified_epoch_is_immutable": True,
}
by_repo = {row["repository"]: row for row in projection["peers"]}
for repo, role in PEERS:
    row = by_repo[repo]
    row["role"] = role
    row["state"] = "NOT_EXECUTED"
    row["contract_state"] = "NOT_EXECUTED"
    row["reason"] = (
        "external read-only exact-SHA federation proof pending; "
        "peer repository is not mutated for release rollover"
    )
projection["release_rollover"] = {
    "source_ref": SOURCE_REF,
    "stage": "IMMUTABLE_EPOCH_STAGED_PENDING_READ_ONLY_PEER_PROOF",
    "release_epoch_id": epoch_id,
    "immutable_path": seed_path,
}

fresh_meta, _ = content(
    CONTROL_TOKEN, CONTROL, "federation/epochs/current.json", "main"
)
body = (json.dumps(projection, indent=2, ensure_ascii=False) + "\n").encode()
control_api(
    "PUT",
    f"/repos/{CONTROL}/contents/federation/epochs/current.json",
    {
        "message": f"Federation v3: project immutable release epoch {TARGET[:12]}",
        "content": base64.b64encode(body).decode(),
        "sha": fresh_meta["sha"],
        "branch": "main",
    },
)

print(
    json.dumps(
        {
            "ok": True,
            "source_sha": TARGET,
            "source_ref": SOURCE_REF,
            "release_epoch_id": epoch_id,
            "immutable_path": seed_path,
            "peer_mode": "read_only",
            "peers": {row["repository"]: row["sha"] for row in peer_rows},
        },
        sort_keys=True,
    )
)
