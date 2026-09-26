#!/usr/bin/env ruby
# frozen_string_literal: true

require "psych"
require "pathname"

ROOT = Pathname.new(__dir__).parent
WORKFLOWS = ROOT.join(".github", "workflows")

def fail!(message)
  warn("OMEGA_CONTROL_PLANE_INTEGRITY_FAIL:#{message}")
  exit 1
end

def scalar_key(node)
  node.is_a?(Psych::Nodes::Scalar) ? node.value : nil
end

def check_duplicate_keys(node, file, path = [])
  if node.is_a?(Psych::Nodes::Mapping)
    seen = {}
    node.children.each_slice(2) do |key_node, value_node|
      key = scalar_key(key_node)
      if key
        here = (path + [key]).join(".")
        fail!("#{file}:duplicate_yaml_key:#{here}") if seen.key?(key)
        seen[key] = true
        check_duplicate_keys(value_node, file, path + [key])
      else
        check_duplicate_keys(value_node, file, path)
      end
    end
  elsif node.respond_to?(:children)
    Array(node.children).each { |child| check_duplicate_keys(child, file, path) if child }
  end
end

def check_forbidden_secret_conditionals(value, file, path = [])
  case value
  when Hash
    value.each do |key, child|
      here = path + [key.to_s]
      if key.to_s == "if" && child.to_s.include?("secrets.")
        fail!("#{file}:secret_context_forbidden_in_if:#{here.join('.')}")
      end
      check_forbidden_secret_conditionals(child, file, here)
    end
  when Array
    value.each_with_index do |child, index|
      check_forbidden_secret_conditionals(child, file, path + [index.to_s])
    end
  end
end

files = Dir[WORKFLOWS.join("*.{yml,yaml}").to_s].sort
fail!("no_workflows_found") if files.empty?

# Any gh workflow dispatch must be repository-explicit. Some release/control jobs
# intentionally run without a checkout, where gh cannot infer the repository.
files.each do |file|
  lines = File.readlines(file, encoding: "UTF-8")
  lines.each_with_index do |line, index|
    next unless line.include?("gh workflow run ")
    command = line.dup
    cursor = index
    while command.rstrip.end_with?("\\") && cursor + 1 < lines.length
      cursor += 1
      command << lines[cursor]
    end
    fail!("#{file}:workflow_dispatch_repository_missing:line_#{index + 1}") unless command.match?(/(?:^|\s)-R(?:\s|=)/)
  end
end

files.each do |file|
  begin
    tree = Psych.parse_file(file)
  rescue Psych::SyntaxError => e
    fail!("#{file}:yaml_syntax:#{e.message.lines.first.to_s.strip}")
  end
  fail!("#{file}:empty_yaml") unless tree
  check_duplicate_keys(tree, file)
  loaded = Psych.safe_load_file(file, aliases: true)
  check_forbidden_secret_conditionals(loaded, file)
  text = File.read(file, encoding: "UTF-8")
  text.scan(/^\s*-\s+uses:\s+([^\s#]+)/).flatten.each do |action|
    next if action.start_with?("./", "docker://")
    name, ref = action.split("@", 2)
    fail!("#{file}:action_without_ref:#{action}") if name.to_s.empty? || ref.to_s.empty?
    fail!("#{file}:mutable_action_ref:#{action}") unless ref.match?(/\A[0-9a-f]{40}\z/)
  end
end

# GitHub limits workflow_run chaining to three levels. Build the workflow_run
# dependency graph from parsed YAML so this platform limit cannot regress.
workflow_names = {}
workflow_run_deps = Hash.new { |h, k| h[k] = [] }
files.each do |file|
  doc = Psych.safe_load_file(file, aliases: true)
  next unless doc.is_a?(Hash)
  name = doc["name"].to_s.strip
  fail!("#{file}:workflow_name_missing") if name.empty?
  fail!("duplicate_workflow_name:#{name}") if workflow_names.key?(name)
  workflow_names[name] = file

  on_value = doc["on"] || doc[true]
  next unless on_value.is_a?(Hash)
  wr = on_value["workflow_run"]
  next unless wr.is_a?(Hash)
  deps = wr["workflows"]
  deps = [deps] if deps.is_a?(String)
  next if deps.nil?
  fail!("#{file}:workflow_run_workflows_invalid") unless deps.is_a?(Array)
  deps.each do |dep|
    dep_name = dep.to_s.strip
    fail!("#{file}:workflow_run_dependency_empty") if dep_name.empty?
    workflow_run_deps[name] << dep_name
  end
end

workflow_run_deps.each do |child, deps|
  deps.each do |parent|
    fail!("workflow_run_unknown_parent:#{child}:#{parent}") unless workflow_names.key?(parent)
  end
end

children = Hash.new { |h, k| h[k] = [] }
workflow_run_deps.each do |child, parents|
  parents.each { |parent| children[parent] << child }
end

visit = lambda do |name, path|
  if path.include?(name)
    cycle = (path[path.index(name)..] + [name]).join(" -> ")
    fail!("workflow_run_cycle:#{cycle}")
  end
  next_path = path + [name]
  if next_path.length - 1 > 3
    fail!("workflow_run_depth_exceeded:#{next_path.join(' -> ')}")
  end
  children[name].sort.each { |child| visit.call(child, next_path) }
end

workflow_names.keys.sort.each { |name| visit.call(name, []) }

recovery_path = WORKFLOWS.join("omega-hosted-recovery-failover.yml")
recovery = File.read(recovery_path, encoding: "UTF-8")
{
  "stale_ref_tip_reconciled" => "OMEGA_RECOVERY_TRIGGER_ADVANCED",
  "stale_ref_tip_base_guard" => "OMEGA_RECOVERY_TRIGGER_NOT_CURRENT_BASE",
  "serialized_recovery_explicit_supersede" => "cancel-in-progress: ${{ github.event_name == 'push' }}",
  "bounded_recovery_queue" => "queue: single",
  "dynamic_evidence_root_packaging" => 'source=(pathlib.Path(os.environ["OMEGA_STATE"])/"evidence").resolve()',
  "artifact_checksum_verify" => "sha256sum -c",
  "out_of_band_artifact_digest" => "recovery_package_sha256",
  "artifact_hash_mismatch_fails" => "OMEGA_RECOVERY_ARTIFACT_HASH_MISMATCH",
  "hard_missing_artifact_failure" => "if-no-files-found: error",
  "failure_diagnostics_preserved" => "Preserve failed pre-recovery diagnostics",
  "model_only_cache_restore" => "actions/cache/restore@55cc8345863c7cc4c66a329aec7e433d2d1c52a9",
  "workflow_cache_restore_only" => "cache-mode: read",
  "gradle_cache_restore_only" => "cache-read-only: true",
  "two_vm_post_recovery" => "post_recovery:",
  "bounded_job_timeout" => "timeout-minutes: 90"
}.each do |name, needle|
  fail!("recovery_contract_missing:#{name}") unless recovery.include?(needle)
end
fail!("recovery_must_not_continue_on_error") if recovery.include?("continue-on-error: true")
fail!("recovery_watchdog_must_not_supersede") unless recovery.include?("Scheduled watchdogs and routine-main never cancel active recovery")
fail!("recovery_helper_must_not_override_model_url") if recovery.include?("OMEGA_LOCAL_BRAIN_MODEL_URL:")
fail!("recovery_helper_must_not_override_qa_model_url") if recovery.include?("OMEGA_LOCAL_QA_BRAIN_MODEL_URL:")
fail!("recovery_helper_must_not_override_model_sha") if recovery.include?("OMEGA_LOCAL_BRAIN_MODEL_SHA256:")
fail!("recovery_helper_must_not_override_qa_model_sha") if recovery.include?("OMEGA_LOCAL_QA_BRAIN_MODEL_SHA256:")
fail!("recovery_helper_must_not_override_llama_commit") if recovery.include?("OMEGA_LLAMA_CPP_COMMIT:")
fail!("recovery_model_cache_must_follow_manifest") unless recovery.include?("hashFiles('omega/deploy/hosted/hf-model-manifest.json')")

pr_bridge = File.read(WORKFLOWS.join("omega-private-pr-hosted-bridge.yml"), encoding: "UTF-8")
fail!("pr_bridge_stale_ref_rejection_missing") unless pr_bridge.include?("OMEGA_EXACT_TRIGGER_STALE")
fail!("pr_bridge_stale_ref_base_guard_missing") unless pr_bridge.include?("OMEGA_EXACT_TRIGGER_NOT_CURRENT_BASE")
fail!("pr_bridge_stale_main_trigger_guard_missing") unless pr_bridge.include?("OMEGA_HOSTED_PR_STALE_TRIGGER_MAIN") && pr_bridge.include?("pr-validation-trigger.txt?ref=main") && pr_bridge.include?(".content // empty")
fail!("pr_bridge_proof_reattest_missing") unless pr_bridge.include?("OMEGA_HOSTED_PR_REUSE_PROOF") && pr_bridge.include?("PRIOR_RUN_ID") && pr_bridge.include?("exact final-SHA proof re-attested")
fail!("pr_bridge_python_syntax_preflight_missing") unless pr_bridge.include?("Preflight Python syntax once before matrix") && pr_bridge.include?("python -m compileall -q src scripts tests")

classifier_path = ROOT.join("scripts", "omega_gate_classifier.py")
fail!("gate_classifier_missing") unless classifier_path.exist?
classifier = File.read(classifier_path, encoding: "UTF-8")
%w[
  INFRA_PRESTART
  EXECUTION_IDENTITY
  ARTIFACT_INTEGRITY
  LEDGER_INTEGRITY
  MODEL_COVERAGE
  SIGNER_CONTINUITY
  FEDERATION_IDENTITY
  ANDROID_RUNTIME
  CODE_TEST
  SUCCESS_WITHOUT_PROOF
  UPSTREAM_PREREQUISITE
].each do |klass|
  fail!("gate_classifier_class_missing:#{klass}") unless classifier.include?(klass)
end
integrity_workflow = File.read(WORKFLOWS.join("omega-control-plane-integrity.yml"), encoding: "UTF-8")
fail!("gate_classifier_self_test_missing") unless integrity_workflow.include?("omega_gate_classifier.py --self-test")

%w[
  incident_id
  diagnostic_sha256
  retryable
  max_attempts
  next_action
].each do |field|
  fail!("gate_classifier_decision_field_missing:#{field}") unless classifier.include?(field)
end

router_path = WORKFLOWS.join("omega-gate-failure-router.yml")
fail!("gate_failure_router_missing") unless router_path.exist?
router = File.read(router_path, encoding: "UTF-8")
[
  "OMEGA Private PR Hosted Bridge",
  "OMEGA Hosted Recovery Failover",
  "OMEGA Candidate Evidence Root",
  "OMEGA Recovery Evidence Release Stager",
  "OMEGA Release Federation Certifier",
  "OMEGA Canonical Android Signer",
  "OMEGA Android Runtime Cold Start",
  "OMEGA Final Release Promoter",
  "OMEGA Post Live Verification"
].each do |workflow_name|
  fail!("gate_failure_router_workflow_missing:#{workflow_name}") unless router.include?(workflow_name)
end
fail!("gate_failure_router_classifier_missing") unless router.include?("scripts/omega_gate_classifier.py")
fail!("gate_failure_router_incident_missing") unless router.include?("incident_id")
fail!("gate_failure_router_execution_identity_missing") unless router.include?("omega_execution_id") && router.include?("evidence_root") && router.include?("execution-envelope.json")
fail!("gate_failure_router_missing_envelope_guard_missing") unless router.include?("envelope-api.json") && router.include?('payload.get("content")') && router.include?('write_text("{}\\n",encoding="utf-8")') && router.include?("base64.b64decode") && router.include?("validate=True")
fail!("gate_failure_router_retry_budget_missing") unless router.include?("run_attempt") && router.include?("max_attempts")
fail!("gate_failure_router_failed_only_retry_missing") unless router.include?('gh run rerun "$RUN_ID" -R "$GITHUB_REPOSITORY" --failed')
fail!("gate_failure_router_fifo_missing") unless router.include?("cancel-in-progress: false") && router.include?("queue: max")
%w[omega-release-federation-certifier.yml omega-final-release-promoter.yml omega-post-live-verification.yml].each do |name|
  text = File.read(WORKFLOWS.join(name), encoding: "UTF-8")
  fail!("validated_base64_decode_missing:#{name}") unless text.include?("base64.b64decode") && text.include?("validate=True")
end


release_fifo_workflows = %w[
  omega-candidate-evidence-root.yml
  omega-recovery-evidence-release-stager.yml
  omega-canonical-android-signer.yml
  omega-release-federation-rollover.yml
  omega-release-federation-certifier.yml
  omega-android-runtime-coldstart.yml
  omega-final-release-promoter.yml
  omega-post-live-verification.yml
]
release_fifo_workflows.each do |name|
  text = File.read(WORKFLOWS.join(name), encoding: "UTF-8")
  fail!("release_fifo_cancel_must_be_false:#{name}") unless text.include?("cancel-in-progress: false")
  fail!("release_fifo_queue_max_missing:#{name}") unless text.include?("queue: max")
end

stager = File.read(WORKFLOWS.join("omega-recovery-evidence-release-stager.yml"), encoding: "UTF-8")
fail!("single_promotion_parent_check_missing") unless stager.include?('parent="$(git rev-parse HEAD^)"') && stager.include?('[ "$parent" = "$SOURCE_SHA" ]')
fail!("single_promotion_trigger_missing") unless stager.include?('validate-exact-pr $FINAL_SHA $RELEASE_BRANCH')
fail!("single_promotion_branch_missing") unless stager.include?('release/recovery-evidence-')
signer = File.read(WORKFLOWS.join("omega-canonical-android-signer.yml"), encoding: "UTF-8")
fail!("signer_current_promotion_binding_missing") unless signer.include?("OMEGA_SIGNER_CURRENT_PROMOTION_PASS") && signer.include?("OMEGA_SIGNER_STALE_HANDOFF") && signer.include?('bootstrap/omega/pr-validation-trigger.txt')
coldstart = File.read(WORKFLOWS.join("omega-android-runtime-coldstart.yml"), encoding: "UTF-8")
promoter = File.read(WORKFLOWS.join("omega-final-release-promoter.yml"), encoding: "UTF-8")
fail!("single_promotion_unsigned_handoff_missing") unless signer.include?("OMEGA-Unsigned-Release-")
fail!("single_promotion_signed_handoff_missing") unless signer.include?("OMEGA-Signed-Release-") && coldstart.include?("OMEGA-Signed-Release-") && promoter.include?("OMEGA-Signed-Release-")
fail!("coldstart_must_break_workflow_run_depth") if coldstart.include?("workflow_run:")
fail!("coldstart_exact_signer_input_missing") unless coldstart.include?("signer_run_id:")
fail!("signer_coldstart_dispatch_missing") unless signer.include?("gh workflow run omega-android-runtime-coldstart.yml") && signer.include?('signer_run_id="$SIGNER_RUN_ID"')
fail!("signer_actions_write_missing") unless signer.include?("actions: write")
fail!("candidate_evidence_must_fail_closed") unless File.read(WORKFLOWS.join("omega-candidate-evidence-root.yml"), encoding: "UTF-8").include?("OMEGA_EVIDENCE_ROOT_UPSTREAM_NOT_PASS") && File.read(WORKFLOWS.join("omega-candidate-evidence-root.yml"), encoding: "UTF-8").include?("exit 75")
candidate_root = File.read(WORKFLOWS.join("omega-candidate-evidence-root.yml"), encoding: "UTF-8")
fail!("candidate_root_stager_dispatch_missing") unless candidate_root.include?("gh workflow run omega-recovery-evidence-release-stager.yml") && candidate_root.include?('evidence_run_id="$EVIDENCE_RUN_ID"')
fail!("candidate_root_recovery_package_contract_missing") unless candidate_root.include?("OMEGA_EVIDENCE_ROOT_RECOVERY_PACKAGE_PASS") && candidate_root.include?("recovery-package-manifest.json") && candidate_root.include?("OMEGA_EVIDENCE_ROOT_RECOVERY_MANIFEST_HASH_MISMATCH")
fail!("candidate_root_actions_write_missing") unless candidate_root.include?("actions: write")
stager_text = File.read(WORKFLOWS.join("omega-recovery-evidence-release-stager.yml"), encoding: "UTF-8")
fail!("release_stager_must_not_use_workflow_run") if stager_text.include?("workflow_run:")
fail!("release_stager_exact_evidence_input_missing") unless stager_text.include?("evidence_run_id:") && stager_text.include?("inputs.evidence_run_id")
%w[acceptance-agents.json latest-agent-promotion.json repo-audit-after-agents.json].each do |artifact|
  fail!("release_stager_qa_bound_artifact_missing:#{artifact}") unless stager_text.include?(artifact)
end
status_order_files = [
  "omega-candidate-evidence-root.yml",
  "omega-recovery-evidence-release-stager.yml",
  "omega-canonical-android-signer.yml",
  "omega-final-release-promoter.yml",
  "omega-post-live-verification.yml",
]
status_order_files.each do |name|
  text = File.read(WORKFLOWS.join(name), encoding: "UTF-8")
  fail!("latest_status_timestamp_resolution_missing:#{name}") unless text.include?("_omega_stamp") && text.include?("updated_at") && text.include?("created_at")
end

fail!("release_stager_fallback_trigger_forbidden") if stager_text.include?("bootstrap/omega/release-stager-trigger.txt") || stager_text.include?("OMEGA_RELEASE_STAGER_STALE_TRIGGER")
fail!("release_stager_explicit_handoff_marker_missing") unless stager_text.include?("OMEGA_RELEASE_STAGER_EXPLICIT_HANDOFF") && stager_text.include?('EVIDENCE_RUN_ID: ${{ inputs.evidence_run_id }}')
fail!("release_stager_actions_write_missing") unless stager_text.include?("actions: write")
fail!("stager_explicit_final_dispatch_missing") unless stager_text.include?('gh workflow run omega-private-pr-hosted-bridge.yml') && stager_text.include?('gh workflow run omega-hosted-recovery-failover.yml') && stager_text.include?('-R "$GITHUB_REPOSITORY" --ref main')
fail!("release_stager_capability_preflight_missing") unless stager_text.include?("OMEGA_RELEASE_CAPABILITY_PASS:private_contents_write") && stager_text.include?("OMEGA_RELEASE_CAPABILITY_MISSING:private_contents_write")
fail!("release_stager_missing_artifact_must_fail") unless stager_text.include?("OMEGA_RELEASE_STAGE_NOT_EXECUTED_NO_EVIDENCE_ARTIFACT") && stager_text.include?("exit 75")
fail!("signer_workflow_handoff_must_fail") unless signer.include?("OMEGA_SIGNER_NO_UNSIGNED_HANDOFF upstream_run=") && signer.include?("exit 75")
postlive = File.read(WORKFLOWS.join("omega-post-live-verification.yml"), encoding: "UTF-8")
fail!("postlive_must_not_use_workflow_run") if postlive.include?("workflow_run:")
fail!("postlive_exact_dispatch_inputs_missing") unless postlive.include?("final_sha:") && postlive.include?("promoter_run_id:")
fail!("promoter_postlive_dispatch_missing") unless promoter.include?("gh workflow run omega-post-live-verification.yml") && promoter.include?('promoter_run_id="$PROMOTER_RUN_ID"')
fail!("promoter_actions_write_missing") unless promoter.include?("actions: write")
fail!("production_provenance_application_id_missing") unless promoter.include?('"application_id":app_id.group(1)') && promoter.include?("OMEGA_FINAL_ANDROID_APPLICATION_ID_MISSING")
fail!("single_promotion_release_ref_guard_missing") unless promoter.include?("^release/[A-Za-z0-9._/-]+$") && promoter.include?("OMEGA_FINAL_RELEASE_REF_UNSAFE") && promoter.include?("OMEGA_FINAL_RELEASE_BRANCH_MOVED")
fail!("postlive_release_ref_guard_missing") unless postlive.include?("^release/[A-Za-z0-9._/-]+$") && postlive.include?("OMEGA_POST_LIVE_REF_UNSAFE") && postlive.include?("OMEGA_POST_LIVE_RELEASE_BRANCH_MOVED")
fail!("federation_rollover_release_ref_guard_missing") unless File.read(WORKFLOWS.join("omega-release-federation-rollover.yml"), encoding: "UTF-8").include?("^release/[A-Za-z0-9._/-]+$")
rollover_script = File.read(ROOT.join("scripts", "rollover_release_federation.py"), encoding: "UTF-8")
fail!("federation_rollover_script_ref_contract_missing") unless rollover_script.include?("RELEASE_REF") && rollover_script.include?("release/[A-Za-z0-9._/-]+") && rollover_script.include?("OMEGA_RELEASE_FEDERATION_REF_INVALID")
fail!("federation_rollover_epoch_cas_missing") unless rollover_script.include?("expected_source") && rollover_script.include?("expected_commit") && rollover_script.include?("OMEGA_PEER_MAIN_DRIFT") && rollover_script.include?("OMEGA_FEDERATION_AUTHORITY_NOT_PASS")
fail!("federation_rollover_historical_sha_forbidden") if rollover_script.include?("6560946cda03347289a76172b6a6a9b9b39bb1b2")
integrity_workflow = File.read(WORKFLOWS.join("omega-control-plane-integrity.yml"), encoding: "UTF-8")
fail!("federation_rollover_integrity_compile_missing") unless integrity_workflow.include?("scripts/rollover_release_federation.py") && integrity_workflow.include?("py_compile scripts/rollover_release_federation.py")
fail!("federation_certifier_release_ref_guard_missing") unless File.read(WORKFLOWS.join("omega-release-federation-certifier.yml"), encoding: "UTF-8").include?('re.fullmatch(r"release/[A-Za-z0-9._/-]+",ref)')
certifier = File.read(WORKFLOWS.join("omega-release-federation-certifier.yml"), encoding: "UTF-8")
fail!("federation_certifier_actions_write_missing") unless certifier.include?("actions: write")
fail!("federation_second_proof_dispatch_missing") unless certifier.include?('gh workflow run omega-federation-v3-peer-bridge.yml -R "$CONTROL_REPOSITORY" --ref main') && certifier.include?("OMEGA_RELEASE_FEDERATION_SECOND_PROOF_DISPATCHED")
fail!("federation_recovery_dispatch_missing") unless certifier.include?('gh workflow run omega-hosted-recovery-failover.yml -R "$CONTROL_REPOSITORY" --ref main') && certifier.include?("OMEGA_RELEASE_FINAL_RECOVERY_DISPATCHED")
fail!("promoter_must_not_trigger_from_signer") if promoter.include?('workflows:\n      - "OMEGA Canonical Android Signer"')
fail!("promoter_must_not_trigger_from_private_bridge") if promoter.include?('workflows:\n      - "OMEGA Private PR Hosted Bridge"')
fail!("promoter_coldstart_trigger_missing") unless promoter.include?('- "OMEGA Android Runtime Cold Start"')

# Immutable release-epoch contract: the public control authority owns the epoch,
# while private federation peers are read-only during rollover.
rollover_workflow = File.read(WORKFLOWS.join("omega-release-federation-rollover.yml"), encoding: "UTF-8")
fail!("release_epoch_control_token_missing") unless rollover_workflow.include?("OMEGA_CONTROL_TOKEN: ${{ github.token }}")
fail!("release_epoch_control_write_permission_missing") unless rollover_workflow.include?("permissions:\n  contents: write")
fail!("release_epoch_control_sha_binding_missing") unless rollover_workflow.include?("OMEGA_CONTROL_CONTRACT_SHA: ${{ github.sha }}")
%w[POST PUT PATCH DELETE].each do |method|
  fail!("release_epoch_private_peer_mutation_forbidden:#{method}") if rollover_script.include?("private_api(\"#{method}\"")
end
fail!("release_epoch_immutable_seed_missing") unless rollover_script.include?("IMMUTABLE_PREFIX = \"federation/epochs/releases\"")
fail!("release_epoch_new_deviation_policy_missing") unless rollover_script.include?("\"new_deviation_requires_new_epoch\": True")
fail!("release_epoch_old_evidence_mutation_policy_missing") unless rollover_script.include?("\"old_evidence_runs_are_never_mutated\": True")
fail!("release_epoch_read_only_peer_policy_missing") unless rollover_script.include?("\"peer_repositories_are_read_only_during_rollover\": True")

peer_bridge = File.read(WORKFLOWS.join("omega-federation-v3-peer-bridge.yml"), encoding: "UTF-8")
fail!("federation_peer_status_write_forbidden") if peer_bridge.include?("/statuses/$PEER_SHA")
fail!("federation_peer_proof_artifact_missing") unless peer_bridge.include?("OMEGA-Federation-Peer-Proof-") && peer_bridge.include?("peer_repository_mutated")
fail!("federation_peer_external_epoch_binding_missing") unless peer_bridge.include?("SOURCE_BINDING_MODE") && peer_bridge.include?("release_epoch_id")
fail!("federation_peer_four_of_four_proof_missing") unless peer_bridge.include?("OMEGA_FEDERATION_4_OF_4_READ_ONLY_PROOF_PASS")
fail!("federation_peer_schedule_forbidden") if peer_bridge.include?("schedule:")
fail!("federation_peer_trigger_must_be_epoch_only") unless peer_bridge.include?("'federation/epochs/current.json'")
fail!("federation_peer_self_trigger_forbidden") if peer_bridge.include?("'.github/workflows/omega-federation-v3-peer-bridge.yml'")
fail!("federation_peer_verifier_trigger_forbidden") if peer_bridge.include?("'scripts/verify_federation_epoch.py'")

fail!("federation_certifier_fresh_proof_missing") unless certifier.include?("OMEGA_RELEASE_CERTIFIER_FRESH_4_OF_4_PASS")
fail!("federation_certifier_stale_status_dependency_forbidden") if certifier.include?("OMEGA_RELEASE_PEER_STATUS_NOT_PASS")

epoch_verifier = File.read(ROOT.join("scripts", "verify_federation_epoch.py"), encoding: "UTF-8")
fail!("release_epoch_verifier_missing") unless epoch_verifier.include?("release_epoch_deviation_policy") && epoch_verifier.include?("external_epoch")

fail!("postlive_live_certified_artifact_missing") unless postlive.include?('"state":"LIVE-CERTIFIED"') && postlive.include?("live-certified.json")
fail!("postlive_release_epoch_policy_missing") unless postlive.include?('"new_deviation_requires_new_epoch":True') && postlive.include?('"old_evidence_runs_are_never_mutated":True')

# Cross-repository release authority must prefer a repository-scoped, short-lived
# GitHub App token when configured. Legacy bootstrap credentials remain only as a
# fail-closed compatibility fallback until the external App authority is installed.
release_app_action = "actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1"
[stager_text, promoter].each_with_index do |text, index|
  label = index.zero? ? "stager" : "promoter"
  fail!("release_app_action_missing:#{label}") unless text.include?(release_app_action)
  fail!("release_app_repo_scope_missing:#{label}") unless text.include?("repositories: Omega-engines")
  fail!("release_app_contents_write_missing:#{label}") unless text.include?("permission-contents: write")
  fail!("release_app_statuses_write_missing:#{label}") unless text.include?("permission-statuses: write")
  fail!("release_app_config_probe_missing:#{label}") unless text.include?("release_app_config.outputs.configured == 'true'") && text.include?("OMEGA_RELEASE_APP_CONFIG")
  fail!("release_app_selected_token_missing:#{label}") unless text.include?("OMEGA_PRIVATE_RELEASE_TOKEN")
end
fail!("release_app_stager_fail_fast_missing") unless stager_text.index("Preflight private release mutation capability").to_i < stager_text.index("actions/download-artifact@").to_i
fail!("release_app_promoter_preflight_missing") unless promoter.include?("OMEGA_FINAL_RELEASE_CAPABILITY_PASS:private_contents_write")

# GITHUB_TOKEN-authored pushes intentionally do not recurse into new workflow
# runs. Every immutable epoch projection therefore needs an explicit dispatch.
fail!("federation_rollover_actions_write_missing") unless rollover_workflow.include?("actions: write")
fail!("federation_rollover_explicit_peer_dispatch_missing") unless rollover_workflow.include?("gh workflow run omega-federation-v3-peer-bridge.yml") && rollover_workflow.include?("OMEGA_RELEASE_FEDERATION_PROOF_DISPATCHED")
fail!("federation_rollover_duplicate_active_guard_missing") unless rollover_workflow.include?("status=queued") && rollover_workflow.include?("status=in_progress") && rollover_workflow.include?("OMEGA_RELEASE_FEDERATION_PROOF_ALREADY_ACTIVE")

# External authority absence is a first-class blocked state, not a retryable
# workflow failure. This keeps the release fail-closed without feeding the
# generic failure router or creating hourly retry storms.
signer_arm = File.read(WORKFLOWS.join("omega-signer-continuity-arm.yml"), encoding: "UTF-8")
fail!("signer_authority_blocked_state_missing") unless signer_arm.include?("OMEGA_SIGNER_AUTHORITY_BLOCKED_STATE")
fail!("signer_authority_status_missing") unless signer_arm.include?('context="omega/authority/private-actions"')
fail!("signer_authority_blocked_must_not_exit_77") if signer_arm.match?(/OMEGA_SIGNER_AUTHORITY_BLOCKED_STATE[\s\S]{0,200}exit 77/)

hosted_signer = File.read(WORKFLOWS.join("omega-hosted-signer-readiness.yml"), encoding: "UTF-8")
fail!("signer_escrow_blocked_state_missing") unless hosted_signer.include?("OMEGA_HOSTED_SIGNER_ESCROW_BLOCKED_STATE")
fail!("signer_escrow_status_missing") unless hosted_signer.include?('context="omega/signer/escrow"')
fail!("signer_escrow_ready_status_missing") unless hosted_signer.include?('state=success') && hosted_signer.include?("OMEGA_HOSTED_SIGNER_ESCROW_READY")

puts "OMEGA_CONTROL_PLANE_INTEGRITY_GREEN workflows=#{files.length}"
# support fastpath restack v2 exact-head trigger
