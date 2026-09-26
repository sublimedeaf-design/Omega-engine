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
  "serialized_recovery_no_livelock" => "cancel-in-progress: false",
  "bounded_recovery_queue" => "queue: max",
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
fail!("recovery_helper_must_not_override_model_url") if recovery.include?("OMEGA_LOCAL_BRAIN_MODEL_URL:")
fail!("recovery_helper_must_not_override_qa_model_url") if recovery.include?("OMEGA_LOCAL_QA_BRAIN_MODEL_URL:")
fail!("recovery_helper_must_not_override_model_sha") if recovery.include?("OMEGA_LOCAL_BRAIN_MODEL_SHA256:")
fail!("recovery_helper_must_not_override_qa_model_sha") if recovery.include?("OMEGA_LOCAL_QA_BRAIN_MODEL_SHA256:")
fail!("recovery_helper_must_not_override_llama_commit") if recovery.include?("OMEGA_LLAMA_CPP_COMMIT:")
fail!("recovery_model_cache_must_follow_manifest") unless recovery.include?("hashFiles('omega/deploy/hosted/hf-model-manifest.json')")

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
fail!("gate_failure_router_must_use_run_log_archive") unless router.include?('/actions/runs/$RUN_ID/logs') && router.include?("zipfile.ZipFile")
fail!("gate_failure_router_gh_run_view_forbidden") if router.include?('gh run view "$RUN_ID"')
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
fail!("candidate_evidence_must_fail_closed") unless File.read(WORKFLOWS.join("omega-candidate-evidence-root.yml"), encoding: "UTF-8").include?("OMEGA_EVIDENCE_ROOT_UPSTREAM_NOT_PASS") && File.read(WORKFLOWS.join("omega-candidate-evidence-root.yml"), encoding: "UTF-8").include?("exit 75")
candidate_root = File.read(WORKFLOWS.join("omega-candidate-evidence-root.yml"), encoding: "UTF-8")
fail!("candidate_root_stager_dispatch_missing") unless candidate_root.include?("gh workflow run omega-recovery-evidence-release-stager.yml") && candidate_root.include?('evidence_run_id="$EVIDENCE_RUN_ID"')
fail!("candidate_root_actions_write_missing") unless candidate_root.include?("actions: write")
stager_text = File.read(WORKFLOWS.join("omega-recovery-evidence-release-stager.yml"), encoding: "UTF-8")
fail!("release_stager_must_not_use_workflow_run") if stager_text.include?("workflow_run:")
fail!("release_stager_exact_evidence_input_missing") unless stager_text.include?("evidence_run_id:") && stager_text.include?("inputs.evidence_run_id")
fail!("release_stager_missing_artifact_must_fail") unless stager_text.include?("OMEGA_RELEASE_STAGE_NOT_EXECUTED_NO_EVIDENCE_ARTIFACT") && stager_text.include?("exit 75")
fail!("signer_workflow_handoff_must_fail") unless signer.include?("OMEGA_SIGNER_NO_UNSIGNED_HANDOFF upstream_run=") && signer.include?("exit 75")
postlive = File.read(WORKFLOWS.join("omega-post-live-verification.yml"), encoding: "UTF-8")
fail!("postlive_must_not_use_workflow_run") if postlive.include?("workflow_run:")
fail!("postlive_exact_dispatch_inputs_missing") unless postlive.include?("final_sha:") && postlive.include?("promoter_run_id:")
fail!("promoter_postlive_dispatch_missing") unless promoter.include?("gh workflow run omega-post-live-verification.yml") && promoter.include?('promoter_run_id="$PROMOTER_RUN_ID"')
fail!("promoter_actions_write_missing") unless promoter.include?("actions: write")
fail!("production_provenance_application_id_missing") unless promoter.include?('"application_id":app_id.group(1)') && promoter.include?("OMEGA_FINAL_ANDROID_APPLICATION_ID_MISSING")
fail!("single_promotion_release_ref_guard_missing") unless promoter.include?("release/recovery-evidence-")
fail!("promoter_must_not_trigger_from_signer") if promoter.include?('workflows:\n      - "OMEGA Canonical Android Signer"')
fail!("promoter_must_not_trigger_from_private_bridge") if promoter.include?('workflows:\n      - "OMEGA Private PR Hosted Bridge"')
fail!("promoter_coldstart_trigger_missing") unless promoter.include?('- "OMEGA Android Runtime Cold Start"')

puts "OMEGA_CONTROL_PLANE_INTEGRITY_GREEN workflows=#{files.length}"
# support fastpath restack v2 exact-head trigger
