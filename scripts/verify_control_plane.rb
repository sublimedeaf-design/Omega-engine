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

files = Dir[WORKFLOWS.join("*.{yml,yaml}").to_s].sort
fail!("no_workflows_found") if files.empty?

files.each do |file|
  begin
    tree = Psych.parse_file(file)
  rescue Psych::SyntaxError => e
    fail!("#{file}:yaml_syntax:#{e.message.lines.first.to_s.strip}")
  end
  fail!("#{file}:empty_yaml") unless tree
  check_duplicate_keys(tree, file)
  text = File.read(file, encoding: "UTF-8")
  text.scan(/^\s*-\s+uses:\s+([^\s#]+)/).flatten.each do |action|
    next if action.start_with?("./", "docker://")
    name, ref = action.split("@", 2)
    fail!("#{file}:action_without_ref:#{action}") if name.to_s.empty? || ref.to_s.empty?
    fail!("#{file}:mutable_action_ref:#{action}") unless ref.match?(/\A[0-9a-f]{40}\z/)
  end
end

recovery_path = WORKFLOWS.join("omega-hosted-recovery-failover.yml")
recovery = File.read(recovery_path, encoding: "UTF-8")
{
  "stale_ref_tip_reconciled" => "OMEGA_RECOVERY_TRIGGER_ADVANCED",
  "stale_ref_tip_base_guard" => "OMEGA_RECOVERY_TRIGGER_NOT_CURRENT_BASE",
  "serialized_recovery_no_livelock" => "cancel-in-progress: false",
  "bounded_recovery_queue" => "queue: max",
  "worker_model_pin" => "cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046",
  "qa_model_pin" => "1d9614638d18024d0fbb36575a15f1302a3adf044df10345688ec4f6e1c4ff32",
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

pr_bridge = File.read(WORKFLOWS.join("omega-private-pr-hosted-bridge.yml"), encoding: "UTF-8")
fail!("pr_bridge_stale_ref_rejection_missing") unless pr_bridge.include?("OMEGA_EXACT_TRIGGER_STALE")
fail!("pr_bridge_stale_ref_base_guard_missing") unless pr_bridge.include?("OMEGA_EXACT_TRIGGER_NOT_CURRENT_BASE")

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
fail!("gate_failure_router_retry_budget_missing") unless router.include?("run_attempt") && router.include?("max_attempts")
fail!("gate_failure_router_failed_only_retry_missing") unless router.include?('gh run rerun "$RUN_ID" -R "$GITHUB_REPOSITORY" --failed')
fail!("gate_failure_router_fifo_missing") unless router.include?("cancel-in-progress: false") && router.include?("queue: max")


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
coldstart = File.read(WORKFLOWS.join("omega-android-runtime-coldstart.yml"), encoding: "UTF-8")
promoter = File.read(WORKFLOWS.join("omega-final-release-promoter.yml"), encoding: "UTF-8")
fail!("single_promotion_unsigned_handoff_missing") unless signer.include?("OMEGA-Unsigned-Release-")
fail!("single_promotion_signed_handoff_missing") unless signer.include?("OMEGA-Signed-Release-") && coldstart.include?("OMEGA-Signed-Release-") && promoter.include?("OMEGA-Signed-Release-")
fail!("coldstart_must_break_workflow_run_depth") if coldstart.include?("workflow_run:")
fail!("coldstart_exact_signer_input_missing") unless coldstart.include?("signer_run_id:")
fail!("signer_coldstart_dispatch_missing") unless signer.include?("gh workflow run omega-android-runtime-coldstart.yml") && signer.include?('signer_run_id="$SIGNER_RUN_ID"')
fail!("signer_actions_write_missing") unless signer.include?("actions: write")
fail!("single_promotion_release_ref_guard_missing") unless promoter.include?("release/recovery-evidence-")

puts "OMEGA_CONTROL_PLANE_INTEGRITY_GREEN workflows=#{files.length}"
# support fastpath restack v2 exact-head trigger
