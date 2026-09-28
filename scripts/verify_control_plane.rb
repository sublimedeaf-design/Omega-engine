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
  "serialized_recovery_explicit_supersede" => "OMEGA_RECOVERY_TRIGGER_QUEUED_SUPERSEDE",
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
fail!("recovery_active_proof_must_not_cancel") unless recovery.include?("cancel-in-progress: false")
fail!("recovery_single_writer_lane_missing") unless recovery.include?("group: omega-hosted-recovery-v5") && recovery.include?("queue: single")
fail!("recovery_split_writer_lane_forbidden") if recovery.include?("omega-hosted-recovery-v4-") || recovery.include?("omega-hosted-recovery-v3-")
fail!("recovery_active_proof_preservation_missing") unless recovery.include?("no schedule or push can cancel evidence already in flight")
fail!("recovery_helper_must_not_override_model_url") if recovery.include?("OMEGA_LOCAL_BRAIN_MODEL_URL:")
fail!("recovery_helper_must_not_override_qa_model_url") if recovery.include?("OMEGA_LOCAL_QA_BRAIN_MODEL_URL:")
fail!("recovery_helper_must_not_override_model_sha") if recovery.include?("OMEGA_LOCAL_BRAIN_MODEL_SHA256:")
fail!("recovery_helper_must_not_override_qa_model_sha") if recovery.include?("OMEGA_LOCAL_QA_BRAIN_MODEL_SHA256:")
fail!("recovery_helper_must_not_override_llama_commit") if recovery.include?("OMEGA_LLAMA_CPP_COMMIT:")
fail!("recovery_model_cache_must_follow_manifest") unless recovery.include?("hashFiles('omega/deploy/hosted/hf-model-manifest.json')")


validation_dispatcher = File.read(WORKFLOWS.join("omega-immutable-validation-request-dispatcher.yml"), encoding: "UTF-8")
fail!("immutable_validation_request_path_missing") unless validation_dispatcher.include?("bootstrap/omega/validation-requests/*.json")
fail!("immutable_validation_request_actions_write_missing") unless validation_dispatcher.include?("actions: write")
fail!("immutable_validation_request_exact_path_binding_missing") unless validation_dispatcher.include?("OMEGA_VALIDATION_REQUEST_PATH_MISMATCH")
fail!("immutable_validation_request_bridge_dispatch_missing") unless validation_dispatcher.include?("gh workflow run omega-private-pr-hosted-bridge.yml") && validation_dispatcher.include?('-f source_sha="$SOURCE_SHA"') && validation_dispatcher.include?('-f source_ref="$SOURCE_REF"')
fail!("immutable_validation_request_dispatch_marker_missing") unless validation_dispatcher.include?("OMEGA_IMMUTABLE_VALIDATION_DISPATCHED")
pr_bridge = File.read(WORKFLOWS.join("omega-private-pr-hosted-bridge.yml"), encoding: "UTF-8")
fail!("pr_bridge_immutable_dispatch_sha_input_missing") unless pr_bridge.include?("source_sha:") && pr_bridge.include?("inputs.source_sha")
fail!("pr_bridge_immutable_dispatch_ref_input_missing") unless pr_bridge.include?("source_ref:") && pr_bridge.include?("inputs.source_ref")
fail!("pr_bridge_immutable_dispatch_guard_missing") unless pr_bridge.include?("OMEGA_HOSTED_PR_DISPATCH_INPUT_PASS") && pr_bridge.include?("OMEGA_HOSTED_PR_DISPATCH_SHA_INVALID") && pr_bridge.include?("OMEGA_HOSTED_PR_DISPATCH_REF_INVALID")

fail!("pr_bridge_stale_ref_rejection_missing") unless pr_bridge.include?("OMEGA_EXACT_TRIGGER_STALE")
fail!("pr_bridge_stale_automatic_noop_missing") unless pr_bridge.include?("OMEGA_EXACT_TRIGGER_STALE_NOOP") && pr_bridge.include?('[ "$EVENT_NAME" != workflow_dispatch ]')
fail!("pr_bridge_explicit_stale_fail_closed_missing") unless pr_bridge.include?("OMEGA_EXACT_TRIGGER_STALE requested=") && pr_bridge.include?("exit 68")
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
fail!("control_plane_integrity_concurrency_scope_missing") unless integrity_workflow.include?('group: omega-control-plane-integrity-${{ github.event_name }}-${{ github.event.pull_request.number || github.ref }}')

google_one_click = File.read(WORKFLOWS.join("omega-google-one-click-release.yml"), encoding: "UTF-8")
fail!("google_one_click_must_not_write_control_contents") if google_one_click.include?("contents: write") || google_one_click.include?("/contents/$TRIGGER_PATH") || google_one_click.include?("bootstrap/omega/google-one-click-release.json")
fail!("google_one_click_status_reconciler_missing") unless google_one_click.include?('context="omega/google-one-click"') && google_one_click.include?("workflow_dispatch:") && google_one_click.include?("schedule:")
fail!("google_one_click_oidc_missing") unless google_one_click.include?("id-token: write") && google_one_click.include?("google-github-actions/auth@")
fail!("google_one_click_exact_source_missing") unless google_one_click.include?('commits/main" --jq .sha') && google_one_click.include?("OMEGA_GOOGLE_PRE_GATES_PASS")
fail!("google_one_click_generation_fence_missing") unless google_one_click.include?("OMEGA_GOOGLE_STALE_GENERATION_NOOP") && google_one_click.include?("generation_id") && google_one_click.include?('epoch_prefix="epoch=')
fail!("google_internal_sharing_must_not_certify_primary_distribution") unless google_one_click.include?("Internal App Sharing cannot certify canonical Play distribution") && google_one_click.include?("OMEGA_GOOGLE_DIAGNOSTIC_FALLBACK_ONLY")
play_builder = File.read(WORKFLOWS.join("omega-play-content-addressed-builder.yml"), encoding: "UTF-8")
fail!("legacy_play_builder_wrong_package_identity") if play_builder.include?("com.omega.app")
fail!("legacy_play_builder_must_not_autostart") if play_builder.include?("push:")
fail!("legacy_play_builder_must_not_publish_primary_signer_trigger") if play_builder.include?('context="omega/play-aab-build-unsigned"')
fail!("legacy_play_builder_current_package_missing") unless play_builder.include?("com.sublimedeafdesign.omegaengine")

resilience_certifier = File.read(ROOT.join("control-plane", "certify.mjs"), encoding: "UTF-8")
fail!("resilience_scope_must_be_pre_signing") unless resilience_certifier.include?('scope:"PRE_SIGNING"') && resilience_certifier.include?("const releaseSignals=")
resilience_required_segment = resilience_certifier.split("const layers={", 2)[1].to_s.split("const releaseSignals=", 2)[0]
fail!("resilience_must_not_gate_on_signer") if resilience_required_segment.include?("signer_continuity:")

%w[
  incident_id
  diagnostic_sha256
  retryable
  max_attempts
  next_action
  github_state
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
fail!("gate_classifier_not_executed_pending_missing") unless classifier.include?('if normalized in {"PENDING", "NOT_EXECUTED"}') && classifier.include?('return "pending"')
fail!("gate_failure_router_canonical_github_state_missing") unless router.include?("steps.classify.outputs.github_state") && router.include?("gen=${SOURCE_SHA:0:12}")
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

resilience_workflow = File.read(WORKFLOWS.join("omega-resilience-certifier.yml"), encoding: "UTF-8")
resilience_certifier = File.read(ROOT.join("control-plane", "certify.mjs"), encoding: "UTF-8")
fail!("resilience_candidate_root_trigger_missing") unless resilience_workflow.include?('"OMEGA Candidate Evidence Root"')
fail!("resilience_current_generation_recovery_fence_missing") unless resilience_certifier.include?("recovery_generation_binding") && resilience_certifier.include?('green(map,"omega/candidate-evidence-root",now,1440)') && resilience_certifier.include?('green(map,"omega/recovery-attestation",now,1440)')

stager = File.read(WORKFLOWS.join("omega-recovery-evidence-release-stager.yml"), encoding: "UTF-8")
fail!("single_promotion_parent_check_missing") unless stager.include?('parent="$(git rev-parse HEAD^)"') && stager.include?('[ "$parent" = "$SOURCE_SHA" ]')
fail!("single_promotion_trigger_missing") unless stager.include?('validate-exact-pr $FINAL_SHA $RELEASE_BRANCH')
fail!("single_promotion_branch_missing") unless stager.include?('release/recovery-evidence-')
signer = File.read(WORKFLOWS.join("omega-canonical-android-signer.yml"), encoding: "UTF-8")
fail!("signer_current_promotion_binding_missing") unless signer.include?("OMEGA_SIGNER_CURRENT_MAIN_HANDOFF_PASS") && signer.include?("OMEGA_SIGNER_CURRENT_PRIVATE_MAIN_PASS") && signer.include?("OMEGA_SIGNER_PRIVATE_MAIN_MOVED") && signer.include?("OMEGA_SIGNER_CURRENT_MAIN_UNSIGNED_HANDOFF_MISSING")
coldstart = File.read(WORKFLOWS.join("omega-android-runtime-coldstart.yml"), encoding: "UTF-8")
fail!("coldstart_registered_package_missing") unless coldstart.include?("com.sublimedeafdesign.omegaengine")
fail!("coldstart_legacy_package_forbidden") if coldstart.include?("com.omega.app")
fail!("coldstart_signed_digest_compat_missing") unless coldstart.include?('p.get("signed_apk_sha256") or p.get("apk_sha256")')
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
fail!("candidate_root_reconciliation_dispatch_missing") unless candidate_root.include?("workflow_dispatch:") && candidate_root.include?("recovery_run_id:") && candidate_root.include?("github.event_name == 'workflow_dispatch'")
fail!("candidate_root_reconciliation_run_verification_missing") unless candidate_root.include?("OMEGA_EVIDENCE_ROOT_RECOVERY_RUN_VERIFIED") && candidate_root.include?("OMEGA_EVIDENCE_ROOT_RECOVERY_WORKFLOW_PATH_MISMATCH") && candidate_root.include?("OMEGA_EVIDENCE_ROOT_RECOVERY_RUN_NOT_SUCCESS")
fail!("candidate_root_reconciliation_artifact_binding_missing") unless candidate_root.include?("OMEGA_EVIDENCE_ROOT_RECOVERY_ARTIFACTS_VERIFIED") && candidate_root.include?("omega-recovery-attestation-") && candidate_root.include?("omega-hosted-recovery-")
fail!("candidate_root_release_epoch_fence_missing") unless candidate_root.include?("OMEGA_EVIDENCE_ROOT_RELEASE_EPOCH_STALE") && candidate_root.include?("CURRENT_FEDERATION_EPOCH") && candidate_root.include?("federation/epochs/current.json?ref=main") && candidate_root.include?("control_contract_sha")
fail!("candidate_root_control_generation_fence_missing") unless candidate_root.include?("OMEGA_EVIDENCE_ROOT_CONTROL_GENERATION_STALE") && candidate_root.include?("federation/epochs/") && candidate_root.include?("bootstrap/omega/")
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
fail!("release_stager_signer_dispatch_missing") unless stager_text.include?("OMEGA_RELEASE_STAGER_SIGNER_DISPATCHED") && stager_text.include?('gh workflow run "$SIGNER_WORKFLOW"') && stager_text.include?("OMEGA_RELEASE_STAGER_SIGNER_ALREADY_ACTIVE")
fail!("stager_explicit_final_dispatch_missing") unless stager_text.include?('gh workflow run omega-private-pr-hosted-bridge.yml') && stager_text.include?('gh workflow run omega-hosted-recovery-failover.yml') && stager_text.include?('-R "$GITHUB_REPOSITORY" --ref main')
fail!("release_stager_capability_preflight_missing") unless stager_text.include?("OMEGA_RELEASE_CAPABILITY_PASS:private_contents_write") && stager_text.include?("OMEGA_RELEASE_CAPABILITY_MISSING:private_contents_write")
fail!("release_stager_legacy_write_forbidden") unless stager_text.include?("OMEGA_RELEASE_CAPABILITY_ARTIFACT_FIRST_REQUIRED") && stager_text.include?('AUTH_SOURCE: ${{ env.OMEGA_RELEASE_AUTH_SOURCE }}') && stager_text.include?('if [ "${AUTH_SOURCE:-}" != github-app ]')
fail!("release_stager_artifact_first_mode_missing") unless stager_text.include?("mode=artifact-first") && stager_text.include?('final="$SOURCE_SHA"')
fail!("release_stager_missing_artifact_must_fail") unless stager_text.include?("OMEGA_RELEASE_STAGE_NOT_EXECUTED_NO_EVIDENCE_ARTIFACT") && stager_text.include?("exit 75")
fail!("release_stager_rerun_source_fence_missing") unless stager_text.include?("OMEGA_RELEASE_STAGE_EVIDENCE_SOURCE_AMBIGUOUS") && stager_text.include?("newest immutable artifact deterministically")
fail!("release_stager_artifact_id_binding_missing") unless stager_text.include?('artifact-ids: ${{ steps.pin.outputs.artifact_id }}')
fail!("release_stager_release_epoch_fence_missing") unless stager_text.include?("OMEGA_RELEASE_STAGE_RELEASE_EPOCH_STALE") && stager_text.include?("OMEGA_RELEASE_STAGE_CONTROL_GENERATION_STALE") && stager_text.include?("OMEGA_RELEASE_EPOCH_ID") && stager_text.include?("omega_release_id")
fail!("release_stager_unsigned_epoch_provenance_missing") unless stager_text.include?('"release_epoch_id":stage.get("release_epoch_id")') && stager_text.include?('"omega_release_id":stage.get("omega_release_id")') && stager_text.include?('"release_epoch_control_contract_sha":payload["release_epoch_control_contract_sha"]')
fail!("signer_release_epoch_fence_missing") unless signer.include?("OMEGA_SIGNER_RELEASE_EPOCH_STALE") && signer.include?("OMEGA_SIGNER_CONTROL_GENERATION_STALE") && signer.include?("federation/epochs/current.json?ref=main")
fail!("signer_release_epoch_slsa_binding_missing") unless signer.include?("OMEGA_SIGNER_SLSA_RELEASE_EPOCH_MISMATCH") && signer.include?('external.get("omega_release_id")') && signer.include?('external.get("release_epoch_id")')
fail!("signer_signed_generation_identity_missing") unless signer.include?('"release_id":release_id') && signer.include?('"release_epoch_id":epoch_id') && signer.include?('"release_epoch_sequence":int(epoch_sequence)') && signer.include?('"release_epoch_control_contract_sha":epoch_control')
fail!("coldstart_signed_generation_fence_missing") unless coldstart.include?("OMEGA_ANDROID_COLDSTART_RELEASE_EPOCH_STALE") && coldstart.include?("OMEGA_ANDROID_COLDSTART_RELEASE_ID_INVALID") && coldstart.include?("current-federation-epoch.json")
fail!("promoter_signed_generation_identity_missing") unless promoter.include?("OMEGA_FINAL_SIGNED_RELEASE_EPOCH_STALE") && promoter.include?("OMEGA_FINAL_STAGE_RELEASE_IDENTITY_MISMATCH") && promoter.include?('"release_id":release_id') && promoter.include?('"release_epoch_id":epoch_id')
fail!("signer_missing_handoff_pending_reconcile_missing") unless signer.match?(/if \[ -z "\$found" \]; then.*?ready=false.*?OMEGA_SIGNER_CURRENT_MAIN_UNSIGNED_HANDOFF_MISSING.*?exit 0/m)
fail!("classifier_missing_handoff_pending_missing") unless classifier.include?('OMEGA_SIGNER_CURRENT_MAIN_UNSIGNED_HANDOFF_MISSING') && classifier.include?('"NOT_EXECUTED", "NOT_EXECUTED", "handoff", "release-stager"')
fail!("classifier_promotion_prerequisite_pending_missing") unless classifier.include?('OMEGA_FINAL_RELEASE_NO_STAGED_CANDIDATE') && classifier.include?('OMEGA_FINAL_RELEASE_WAITING_FOR=')
postlive = File.read(WORKFLOWS.join("omega-post-live-verification.yml"), encoding: "UTF-8")
fail!("postlive_must_not_use_workflow_run") if postlive.include?("workflow_run:")
fail!("postlive_release_generation_fence_missing") unless postlive.include?("OMEGA_POST_LIVE_RELEASE_EPOCH_STALE") && postlive.include?("OMEGA_POST_LIVE_RELEASE_ID_INVALID") && postlive.include?('"release_epoch_id":prov.get("release_epoch_id")')
fail!("postlive_exact_dispatch_inputs_missing") unless postlive.include?("final_sha:") && postlive.include?("promoter_run_id:")
fail!("promoter_postlive_dispatch_missing") unless promoter.include?("gh workflow run omega-post-live-verification.yml") && promoter.include?('promoter_run_id="$PROMOTER_RUN_ID"')
fail!("promoter_actions_write_missing") unless promoter.include?("actions: write")
fail!("production_provenance_application_id_missing") unless promoter.include?('"application_id":app_id.group(1)') && promoter.include?("OMEGA_FINAL_ANDROID_APPLICATION_ID_MISSING")
fail!("single_promotion_release_ref_guard_missing") unless promoter.include?("^release/[A-Za-z0-9._/-]+$") && promoter.include?("OMEGA_FINAL_RELEASE_REF_UNSAFE") && promoter.include?("OMEGA_FINAL_RELEASE_BRANCH_MOVED")
fail!("promoter_epoch_must_be_single_authority") unless promoter.include?("federation/epochs/current.json?ref=main") && promoter.include?("OMEGA_FINAL_FEDERATION_STAGE_NOT_CERTIFIED") && promoter.include?("OMEGA_FINAL_RELEASE_STALE_GENERATION")
fail!("promoter_mutable_validation_trigger_authority_forbidden") if promoter.include?('read -r marker candidate source_ref _ < bootstrap/omega/pr-validation-trigger.txt')
fail!("promoter_pending_reconcile_semantics_missing") unless promoter.include?("OMEGA_FINAL_RELEASE_NOT_READY_RECONCILE_PENDING")
fail!("promoter_not_ready_hard_failure_forbidden") if promoter.include?("OMEGA_FINAL_RELEASE_NOT_READY_FAIL_CLOSED")
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
fail!("federation_second_proof_exact_sha_dispatch_missing") unless certifier.include?('gh workflow run omega-federation-v3-peer-bridge.yml -R "$CONTROL_REPOSITORY" --ref main') && certifier.include?('current_main="$(gh api "/repos/$CONTROL_REPOSITORY/git/ref/heads/main" --jq') && certifier.include?('[ "$current_main" = "$PROMOTED_HEAD_SHA" ]') && certifier.include?("OMEGA_RELEASE_FEDERATION_SECOND_PROOF_DISPATCHED") && certifier.include?("OMEGA_RELEASE_FEDERATION_SECOND_PROOF_REF_INVALID")
fail!("federation_recovery_dispatch_missing") unless certifier.include?('gh workflow run omega-hosted-recovery-failover.yml -R "$CONTROL_REPOSITORY" --ref main') && certifier.include?("OMEGA_RELEASE_FINAL_RECOVERY_DISPATCHED")
fail!("promoter_must_not_trigger_from_signer") if promoter.include?('workflows:\n      - "OMEGA Canonical Android Signer"')
fail!("promoter_must_not_trigger_from_private_bridge") if promoter.include?('workflows:\n      - "OMEGA Private PR Hosted Bridge"')
fail!("promoter_coldstart_trigger_missing") unless promoter.include?('- "OMEGA Android Runtime Cold Start"')

# Immutable release-epoch contract: the public control authority owns the epoch,
# while private federation peers are read-only during rollover.
rollover_workflow = File.read(WORKFLOWS.join("omega-release-federation-rollover.yml"), encoding: "UTF-8")
fail!("federation_rollover_must_be_controller_dispatch_only") if rollover_workflow.include?("workflow_run:")
fail!("federation_rollover_generation_inputs_missing") unless rollover_workflow.include?("source_sha:") && rollover_workflow.include?("source_ref:") && rollover_workflow.include?("OMEGA_RELEASE_FEDERATION_STALE_GENERATION")
fail!("federation_rollover_stale_generation_must_noop") unless rollover_workflow.include?("OMEGA_RELEASE_FEDERATION_STALE_GENERATION_NOOP") && rollover_workflow.match?(/if \[ "\$main" != "\$candidate" \]; then.*?found=false.*?exit 0/m)
fail!("federation_rollover_private_main_fence_missing") unless rollover_script.include?("OMEGA_RELEASE_FEDERATION_STALE_GENERATION")
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

fail!("postlive_release_certified_artifact_missing") unless postlive.include?('"state":"RELEASE_CERTIFIED"') && postlive.include?("release-certified.json")
fail!("postlive_generic_release_status_missing") unless postlive.include?("omega/release-post-live-smoke") && postlive.include?("omega/release-certified")
fail!("postlive_must_not_claim_distribution_live") if postlive.include?("omega/post-live-smoke omega/live-certified")
fail!("postlive_limited_distribution_dispatch_missing") unless postlive.include?("omega-limited-distribution-release-adapter.yml") && postlive.include?("OMEGA_LD_ADAPTER_DISPATCHED") && postlive.include?("actions: write")
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
fail!("promoter_legacy_private_main_write_forbidden") unless promoter.include?("OMEGA_FINAL_RELEASE_SCOPED_MUTATION_AUTHORITY_REQUIRED") && promoter.include?('AUTH_SOURCE: ${{ env.OMEGA_RELEASE_AUTH_SOURCE }}') && promoter.include?('[ "${AUTH_SOURCE:-}" = github-app ]')

# GITHUB_TOKEN-authored pushes intentionally do not recurse into new workflow
# runs. Every immutable epoch projection therefore needs an explicit dispatch.
fail!("federation_rollover_actions_write_missing") unless rollover_workflow.include?("actions: write")
fail!("federation_rollover_explicit_peer_dispatch_missing") unless rollover_workflow.include?("gh workflow run omega-federation-v3-peer-bridge.yml") && rollover_workflow.include?("OMEGA_RELEASE_FEDERATION_PROOF_DISPATCHED")
fail!("federation_rollover_duplicate_active_guard_missing") unless rollover_workflow.include?("status=queued") && rollover_workflow.include?("status=in_progress") && rollover_workflow.include?("OMEGA_RELEASE_FEDERATION_PROOF_ALREADY_ACTIVE")

# Signer identity and operational key availability are separate security
# objects. Canonical signing is owned by the public control plane so private
# Actions availability cannot become a single point of failure.
signer_arm = File.read(WORKFLOWS.join("omega-signer-continuity-arm.yml"), encoding: "UTF-8")
fail!("signer_arm_actions_write_missing") unless signer_arm.include?("actions: write")
fail!("signer_arm_event_reconciliation_missing") unless signer_arm.include?("workflow_run:") && signer_arm.include?("OMEGA Recovery Evidence Release Stager") && signer_arm.include?("OMEGA Private PR Hosted Bridge") && signer_arm.include?("OMEGA Release Federation Certifier")
fail!("signer_arm_reconcile_marker_missing") unless signer_arm.include?("bootstrap/omega/signer-trigger.txt")
fail!("signer_arm_failed_upstream_must_skip") unless signer_arm.include?("github.event.workflow_run.conclusion == 'success'")
fail!("signer_arm_public_canonical_workflow_missing") unless signer_arm.include?("SIGNER_WORKFLOW: omega-canonical-android-signer.yml")
fail!("signer_arm_hosted_escrow_missing") unless signer_arm.include?("OMEGA_ANDROID_KEYSTORE_B64")
fail!("signer_key_availability_status_missing") unless signer_arm.include?('"omega/signer/key-availability"')
fail!("signer_escrow_status_missing") unless signer_arm.include?('"omega/signer/escrow"')
fail!("signer_hosted_escrow_optional_fallback_missing") unless signer_arm.include?("OMEGA_SIGNER_ARM_HOSTED_ESCROW_OPTIONAL") && signer_arm.include?("alternate signer backends")
fail!("signer_upstream_gate_missing") unless signer_arm.include?("OMEGA_SIGNER_ARM_UPSTREAM_READY") && signer_arm.include?('"omega/android-release-unsigned"') && signer_arm.include?('"omega/candidate-evidence-root"')
fail!("signer_public_dispatch_missing") unless signer_arm.include?("OMEGA_SIGNER_ARM_PUBLIC_SIGNER_DISPATCHED") && signer_arm.include?('gh workflow run "$SIGNER_WORKFLOW"')
fail!("signer_private_actions_dependency_present") if signer_arm.include?("android-signing-keepalive.yml") || signer_arm.include?("OMEGA_RELEASE_APP_PRIVATE_KEY") || signer_arm.include?("/repos/$PRIVATE_REPOSITORY/actions/workflows/")

runner_authority_probe = File.read(WORKFLOWS.join("omega-signer-runner-authority-probe.yml"), encoding: "UTF-8")
fail!("signer_runner_probe_opt_in_missing") unless runner_authority_probe.include?("OMEGA_ENABLE_PRIVATE_SELF_HOSTED") && runner_authority_probe.include?("OMEGA_SIGNER_RUNNER_OPT_IN_PASS") && runner_authority_probe.include?("OMEGA_SIGNER_RUNNER_OPT_IN_BLOCKED")
fail!("signer_runner_probe_labels_missing") unless runner_authority_probe.include?("omega-signer-rescue-v2") && runner_authority_probe.include?("self-hosted") && runner_authority_probe.include?("arm64")
fail!("signer_runner_probe_online_state_missing") unless runner_authority_probe.include?("OMEGA_SIGNER_RUNNER_ONLINE_PASS") && runner_authority_probe.include?("OMEGA_SIGNER_RUNNER_OFFLINE") && runner_authority_probe.include?("OMEGA_SIGNER_RUNNER_REGISTRATION_MISSING")
fail!("signer_runner_probe_registration_authority_missing") unless runner_authority_probe.include?("OMEGA_SIGNER_RUNNER_AUTHORITY_PASS") && runner_authority_probe.include?("registration-token")
fail!("signer_runner_probe_failure_containment_missing") unless runner_authority_probe.scan('if: ${{ always() }}').length >= 2

hosted_signer = File.read(WORKFLOWS.join("omega-hosted-signer-readiness.yml"), encoding: "UTF-8")
fail!("signer_hosted_escrow_optional_state_missing") unless hosted_signer.include?("OMEGA_HOSTED_SIGNER_ESCROW_OPTIONAL") && hosted_signer.include?("alternate signer backends remain eligible")
fail!("signer_key_availability_context_missing") unless hosted_signer.include?('"omega/signer/key-availability"')
fail!("signer_escrow_compat_context_missing") unless hosted_signer.include?('"omega/signer/escrow"')
fail!("signer_hosted_escrow_optional_pending_missing") unless hosted_signer.include?('publish pending "omega/signer/key-availability"') && hosted_signer.include?('publish pending "omega/signer/escrow"')
fail!("signer_key_availability_ready_status_missing") unless hosted_signer.include?('publish success "omega/signer/key-availability"') && hosted_signer.include?("OMEGA_HOSTED_SIGNER_ESCROW_READY")

identity_anchor = File.read(WORKFLOWS.join("omega-signer-identity-anchor.yml"), encoding: "UTF-8")
fail!("signer_identity_anchor_release_missing") unless identity_anchor.include?("omega-android-v3.5.4-live.10-code14")
fail!("signer_identity_anchor_source_pin_missing") unless identity_anchor.include?("6f7511f477c0a96fb28206061c30a6c4a40414f0")
fail!("signer_identity_anchor_asset_digest_missing") unless identity_anchor.include?("32da40b75fe01a75e3b66001f084f6bf737c3d5e9ffb325829318319b17896f3")
fail!("signer_identity_anchor_apksigner_missing") unless identity_anchor.include?("apksigner") && identity_anchor.include?("Signer #1 certificate SHA-256 digest")
fail!("signer_identity_anchor_context_missing") unless identity_anchor.include?("omega/signer/identity-continuity") && identity_anchor.include?("omega/signer/continuity")
fail!("signer_identity_anchor_candidate_binding_missing") unless identity_anchor.include?("pr-validation-trigger.txt") && identity_anchor.include?("commits/$source_ref")

# A successful 4-of-4 peer proof must explicitly hand off its exact run identity.
# Do not depend solely on workflow_run delivery/chaining for a release transition.
peer_bridge = File.read(WORKFLOWS.join("omega-federation-v3-peer-bridge.yml"), encoding: "UTF-8")
certifier = File.read(WORKFLOWS.join("omega-release-federation-certifier.yml"), encoding: "UTF-8")
fail!("federation_peer_certifier_actions_write_missing") unless peer_bridge.include?("actions: write")
fail!("federation_peer_explicit_certifier_dispatch_missing") unless peer_bridge.include?("OMEGA_FEDERATION_CERTIFIER_DISPATCHED") && peer_bridge.include?("bridge_run_id=") && peer_bridge.include?("bridge_head_sha=")
fail!("federation_peer_certifier_duplicate_guard_missing") unless peer_bridge.include?("OMEGA_FEDERATION_CERTIFIER_ALREADY_ACTIVE") && peer_bridge.include?("status=queued") && peer_bridge.include?("status=in_progress")
fail!("federation_certifier_manual_exact_handoff_missing") unless certifier.include?("bridge_run_id:") && certifier.include?("bridge_head_sha:") && certifier.include?("inputs.bridge_run_id") && certifier.include?("inputs.bridge_head_sha")
fail!("federation_certifier_exact_bridge_api_verification_missing") unless certifier.include?("OMEGA_RELEASE_CERTIFIER_BRIDGE_IDENTITY_MISMATCH") && certifier.include?("/actions/runs/$BRIDGE_RUN_ID")

# TUF-style rollback/freeze semantics for release control identity: every
# orchestrator deviation creates a new immutable, monotonically sequenced epoch.
fail!("release_epoch_monotonic_sequence_missing") unless rollover_script.include?('"monotonic_epoch_sequence": True') && rollover_script.include?("sequence = prior_sequence + 1")
fail!("release_epoch_unfinished_supersede_missing") unless rollover_script.include?("safe_unfinished_supersede") && rollover_script.include?("OMEGA_RELEASE_EPOCH_SUPERSEDE_UNFINISHED_CONTROL_DEVIATION")
fail!("release_epoch_certified_pre_live_supersede_missing") unless rollover_script.include?("safe_certified_pre_live_supersede") && rollover_script.include?("OMEGA_RELEASE_EPOCH_SUPERSEDE_CERTIFIED_PRE_LIVE_CONTROL_DEVIATION")
fail!("release_epoch_live_immutability_missing") unless rollover_script.include?("OMEGA_RELEASE_EPOCH_LIVE_CERTIFIED_IMMUTABLE")
fail!("release_epoch_limited_distribution_live_boundary_missing") unless rollover_script.include?("omega/limited-distribution/live-certified")
fail!("release_epoch_supersede_policy_missing") unless rollover_script.include?('"supersedes_unfinished_epoch_on_control_deviation": True') && rollover_script.include?('"supersedes_unfinished_epoch_on_new_private_generation": True') && rollover_script.include?('"current_private_main_is_generation_fence": True') && rollover_script.include?('"supersedes_certified_pre_live_epoch_on_control_deviation": True') && rollover_script.include?('"live_certified_epoch_is_immutable": True')
fail!("release_epoch_parent_control_binding_missing") unless rollover_script.include?('"control_contract_sha": prior_control_contract or None') && rollover_script.include?('"parent_sequence": prior_sequence')

epoch_verifier = File.read(ROOT.join("scripts", "verify_federation_epoch.py"), encoding: "UTF-8")
fail!("release_epoch_sequence_verifier_missing") unless epoch_verifier.include?("release_epoch_sequence_not_monotonic") && epoch_verifier.include?("release_epoch_parent_control_sha")
fail!("release_epoch_live_bound_verifier_missing") unless epoch_verifier.include?("release_epoch_pre_live_supersede_policy") && epoch_verifier.include?("release_epoch_live_immutability_policy")

peer_bridge = File.read(WORKFLOWS.join("omega-federation-v3-peer-bridge.yml"), encoding: "UTF-8")
fail!("federation_control_rollback_guard_missing") unless peer_bridge.include?("OMEGA_FEDERATION_CONTROL_ROLLBACK_DETECTED") && peer_bridge.include?("git merge-base --is-ancestor")
fail!("federation_control_drift_guard_missing") unless peer_bridge.include?("OMEGA_FEDERATION_CONTROL_DRIFT_REQUIRES_NEW_EPOCH")
fail!("federation_epoch_sequence_required_missing") unless peer_bridge.include?("OMEGA_FEDERATION_EPOCH_SEQUENCE_REQUIRED")
fail!("federation_peer_control_binding_missing") unless peer_bridge.include?('"control_contract_sha":control_contract') && peer_bridge.include?('"release_epoch_sequence":sequence')

certifier = File.read(WORKFLOWS.join("omega-release-federation-certifier.yml"), encoding: "UTF-8")
fail!("federation_certifier_control_binding_missing") unless certifier.include?("OMEGA_RELEASE_CERTIFIER_PROOF_CONTROL_BINDING_MISMATCH") && certifier.include?("release_epoch_sequence")

# Release orchestration is explicit and idempotent. Public control-plane pushes
# and a low-frequency watchdog must wake a stale unfinished epoch without
# touching evidence files merely to manufacture an event.
orchestrator_path = WORKFLOWS.join("omega-release-orchestrator-arm.yml")
fail!("release_orchestrator_arm_missing") unless orchestrator_path.exist?
orchestrator = File.read(orchestrator_path, encoding: "UTF-8")
fail!("release_orchestrator_actions_write_missing") unless orchestrator.include?("actions: write")
fail!("release_orchestrator_schedule_missing") unless orchestrator.include?('cron: "3,18,33,48 * * * *"')
fail!("release_orchestrator_exact_proof_event_missing") unless orchestrator.include?("workflow_run:") && orchestrator.include?('OMEGA Private PR Hosted Bridge') && orchestrator.include?("types: [completed]")
fail!("release_orchestrator_exact_final_reconcile_missing") unless orchestrator.include?('gh workflow run omega-private-pr-hosted-bridge.yml') && orchestrator.include?('-f source_sha="$candidate" -f source_ref=main') && orchestrator.include?("OMEGA_RELEASE_CONTROLLER_EXACT_FINAL_DISPATCHED")
fail!("release_orchestrator_exact_final_duplicate_guard_missing") unless orchestrator.include?("OMEGA_RELEASE_CONTROLLER_EXACT_FINAL_ALREADY_ACTIVE") && orchestrator.include?("omega-private-pr-hosted-bridge.yml/runs?status=queued") && orchestrator.include?("omega-private-pr-hosted-bridge.yml/runs?status=in_progress")
fail!("release_orchestrator_explicit_rollover_missing") unless orchestrator.include?('gh workflow run "$ROLLOVER_WORKFLOW" -R "$GITHUB_REPOSITORY" --ref main')
fail!("release_orchestrator_duplicate_guard_missing") unless orchestrator.include?("OMEGA_RELEASE_ORCHESTRATOR_ROLLOVER_ALREADY_ACTIVE") && orchestrator.include?("status=queued") && orchestrator.include?("status=in_progress")
fail!("release_orchestrator_control_deviation_missing") unless orchestrator.include?("pre-live-control-deviation") && orchestrator.include?("live-certified-generation-immutable") && orchestrator.include?('omega/live-certified') && orchestrator.include?('omega/limited-distribution/live-certified')
fail!("release_orchestrator_private_main_reconcile_missing") unless orchestrator.include?('commits/main" --jq .sha') && orchestrator.include?('source_ref="release/auto-') && orchestrator.include?("OMEGA_RELEASE_CONTROLLER_REF_CREATED")
fail!("release_orchestrator_trigger_file_authority_forbidden") if orchestrator.include?("read -r marker candidate source_ref")
fail!("release_orchestrator_generation_inputs_missing") unless orchestrator.include?('-f source_sha="$SOURCE_SHA" -f source_ref="$SOURCE_REF"')
fail!("release_orchestrator_state_only_drift_missing") unless orchestrator.include?("state-only-control-head-advance") && orchestrator.include?('path.startswith("federation/epochs/")') && orchestrator.include?("bootstrap/omega/")
fail!("release_orchestrator_compare_guard_missing") unless orchestrator.include?("/compare/$contract...$control_main") && orchestrator.include?("control-diff-too-large") && orchestrator.include?("control-history-")
fail!("release_orchestrator_missing_ref_json_guard") unless orchestrator.include?('if ref_json="$(gh api "/repos/$PRIVATE_REPOSITORY/git/ref/heads/$source_ref" 2>/dev/null)"; then') && orchestrator.include?("OMEGA_RELEASE_CONTROLLER_REF_RESPONSE_INVALID")
fail!("release_orchestrator_404_stdout_collision_regression") if orchestrator.include?('--jq .object.sha 2>/dev/null || true')
fail!("release_orchestrator_scoped_app_authority_missing") unless orchestrator.include?("actions/create-github-app-token@bcd2ba49218906704ab6c1aa796996da409d3eb1") && orchestrator.include?("repositories: Omega-engines") && orchestrator.include?("permission-contents: write") && orchestrator.include?("permission-statuses: write")
fail!("release_orchestrator_private_token_selection_missing") unless orchestrator.include?("OMEGA_PRIVATE_RELEASE_TOKEN") && orchestrator.include?("OMEGA_RELEASE_AUTHORITY_SELECTED")
fail!("release_orchestrator_reconcile_must_use_selected_private_authority") unless orchestrator.include?('GH_TOKEN: ${{ env.OMEGA_PRIVATE_RELEASE_TOKEN }}')
fail!("release_orchestrator_large_state_must_be_file_backed") unless orchestrator.include?('status_file="$RUNNER_TEMP/omega-release-statuses.json"') && orchestrator.include?('epoch_file="$RUNNER_TEMP/omega-release-epoch.json"') && orchestrator.include?('compare_file="$RUNNER_TEMP/omega-release-compare.json"') && orchestrator.include?('python3 - "$epoch_file" "$compare_file" "$status_file"')
fail!("release_orchestrator_large_state_env_regression") if orchestrator.include?('STATUS_PAYLOAD="$statuses"') || orchestrator.include?('EPOCH="$epoch" COMPARE_PAYLOAD="$compare"')
fail!("release_orchestrator_missing_authority_wait_state") unless orchestrator.include?("OMEGA_RELEASE_CONTROLLER_AUTHORITY_WAIT") && orchestrator.include?('context="omega/authority/private-actions"') && orchestrator.include?("repo-local immutable release-ref actuator pending")
fail!("release_orchestrator_private_actuator_observer_missing") unless orchestrator.include?("OMEGA_RELEASE_CONTROLLER_PRIVATE_ACTUATOR_WAIT") && orchestrator.include?("OMEGA_RELEASE_CONTROLLER_PRIVATE_ACTUATOR_SATISFIED")
fail!("release_orchestrator_cross_repo_actuator_dispatch_forbidden") if orchestrator.include?("gh workflow run omega-release-ref-actuator.yml")
fail!("release_orchestrator_private_actuator_bounded_poll_missing") unless orchestrator.include?("for _ in $(seq 1 18)") && orchestrator.include?("sleep 5")
fail!("release_orchestrator_scoped_write_guard_missing") unless orchestrator.include?('if [ "${OMEGA_RELEASE_AUTH_SOURCE:-}" = github-app ]') && orchestrator.include?("direct_created=false") && orchestrator.include?("authority=github-app")
fail!("release_orchestrator_legacy_write_must_delegate") unless orchestrator.include?("OMEGA_RELEASE_CONTROLLER_PRIVATE_ACTUATOR_WAIT") && orchestrator.include?('if [ "$direct_created" != true ]') && orchestrator.include?("OMEGA_RELEASE_CONTROLLER_AUTHORITY_WAIT")
fail!("release_orchestrator_must_not_mutate_epoch") if orchestrator.include?("/contents/federation/epochs/current.json") && orchestrator.include?("--method PUT")

# Supply-chain provenance must survive the unsigned handoff and be verified before
# any canonical key operation. This is intentionally independent of paid attestation features.
fail!("release_stager_slsa_statement_missing") unless stager.include?("https://in-toto.io/Statement/v1") && stager.include?("https://slsa.dev/provenance/v1") && stager.include?("resolvedDependencies") && stager.include?("OMEGA-Engine-unsigned.intoto.jsonl")
fail!("release_stager_builder_binding_missing") unless stager.include?("OMEGA_CONTROL_WORKFLOW_SHA") && stager.include?("github.workflow_sha")
fail!("signer_slsa_subject_verification_missing") unless signer.include?("OMEGA_SIGNER_SLSA_SUBJECT_MISMATCH") && signer.include?("OMEGA_SIGNER_SLSA_BUILDER_INVALID")
fail!("signer_slsa_dependency_verification_missing") unless signer.include?("OMEGA_SIGNER_SLSA_DEPENDENCY_MISMATCH") && signer.include?("omega-sbom.spdx.json") && signer.include?("release-stage-supply-chain.json")

# Large GitHub API collections must cross process boundaries through files,
# never environment variables: Linux execve(2) ARG_MAX is finite and status /
# release history grows over time.
public_live = File.read(WORKFLOWS.join("omega-limited-distribution-public-live-certifier.yml"), encoding: "UTF-8")
fail!("limited_distribution_public_status_payload_must_be_file_backed") unless public_live.include?('status-pages.json') && public_live.include?('python3 - "$RUNNER_TEMP/status-pages.json"')
fail!("limited_distribution_public_release_payload_must_be_file_backed") unless public_live.include?('releases.json') && public_live.include?('python3 - "$RUNNER_TEMP/releases.json"')
fail!("limited_distribution_public_large_env_regression") if public_live.include?('STATUS_PAYLOAD="$statuses"') || public_live.include?('RELEASES="$releases"')
fail!("limited_distribution_public_generation_fence_missing") unless public_live.include?("ld-public-current-federation-epoch.json") && public_live.include?('"identity_epoch"') && public_live.include?('"provenance_epoch"') && public_live.include?('"release_epoch_id":p["release_epoch_id"]')

adapter_path = WORKFLOWS.join("omega-limited-distribution-release-adapter.yml")
fail!("limited_distribution_adapter_missing") unless adapter_path.exist?
adapter = File.read(adapter_path, encoding: "UTF-8")
fail!("limited_distribution_adapter_exact_inputs_missing") unless adapter.include?("final_sha:") && adapter.include?("post_live_run_id:")
fail!("limited_distribution_adapter_registered_package_missing") unless adapter.include?("com.sublimedeafdesign.omegaengine")
fail!("limited_distribution_adapter_canonical_signer_missing") unless adapter.include?("0738b245ec8a557edc0600a6961d7bb2586cc22f886ed5273560ce6ab2db447f")
fail!("limited_distribution_adapter_production_reuse_missing") unless adapter.include?("PRODUCTION_FINAL") && adapter.include?("re_attested_from_production_final")
fail!("limited_distribution_adapter_release_identity_missing") unless adapter.include?("release-identity.json") && adapter.include?("OMEGA_LIMITED_DISTRIBUTION_SIGNED_CANDIDATE")
fail!("limited_distribution_adapter_inherited_generation_missing") unless adapter.include?("OMEGA_LD_ADAPTER_RELEASE_EPOCH_STALE") && adapter.include?("OMEGA_LD_ADAPTER_INHERITED_RELEASE_IDENTITY_INVALID") && adapter.include?('"release_epoch_id":epoch_id') && !adapter.include?("omega-limited-distribution-v1\\0")
fail!("limited_distribution_adapter_statuses_missing") unless adapter.include?("omega/limited-distribution/apk-signed") && adapter.include?("omega/limited-distribution/signer-continuity") && adapter.include?("omega/limited-distribution/emulator-coldstart") && adapter.include?("omega/limited-distribution/device-install")
fail!("limited_distribution_adapter_must_not_certify_live") if adapter.include?("omega/limited-distribution/live-certified") || adapter.include?("omega/live-certified")
fail!("limited_distribution_adapter_device_gate_pending_missing") unless adapter.include?('state=pending -f context="omega/limited-distribution/device-install"')
fail!("limited_distribution_adapter_runtime_exact_source_missing") unless adapter.include?('gh workflow run omega-android-runtime-certify.yml') && adapter.include?('-f source_sha="$FINAL_SHA"') && adapter.include?('-f allow_private_self_hosted=true')

puts "OMEGA_CONTROL_PLANE_INTEGRITY_GREEN workflows=#{files.length}"
# support fastpath restack v2 exact-head trigger

# The hosted federation fallback must consume the same certifying peer set as
# the exact-source federation executor. Legacy witness repositories (Jarv) are
# explicitly outside the certifying set and must never be reintroduced here.
federation_fallback = File.read(WORKFLOWS.join("omega-hosted-federation-fallback.yml"), encoding: "UTF-8")
fail!("federation_fallback_legacy_jarv_peer") if federation_fallback.include?('"Jarv"')
fail!("federation_fallback_config_peer_derivation_missing") unless federation_fallback.scan('expected={str(item["repository"]) for item in cfg.get("peers",[]) if item.get("repository")}').length == 3
fail!("federation_fallback_peer_config_guard_missing") unless federation_fallback.scan("OMEGA_HOSTED_FEDERATION_PEER_CONFIG_INVALID").length == 3

# Hosted federation fallback must bind the executor to the exact checked-out
# private source SHA. repository-mesh schema v2 intentionally carries no
# validated_federation_source_pin; external epochs are the source authority.
fail!("federation_fallback_legacy_mesh_source_pin") if federation_fallback.include?('validated_federation_source_pin')
fail!("federation_fallback_exact_source_binding_missing") unless federation_fallback.include?('source_pin="$SOURCE_SHA"') && federation_fallback.include?('report.get("source_pin")!=source')
fail!("federation_fallback_verifier_config_reload_missing") unless federation_fallback.scan('cfg=json.loads').length >= 3
fail!("federation_fallback_external_epoch_delegation_missing") unless federation_fallback.include?("OMEGA_FEDERATION_EXTERNAL_EPOCH_CERTIFIED") && federation_fallback.include?('omega/federation-v3-release') && federation_fallback.include?("source_binding_mode")
