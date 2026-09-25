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
  "stale_ref_tip_guard" => "OMEGA_RECOVERY_TRIGGER_NOT_REF_TIP",
  "serialized_recovery_no_livelock" => "cancel-in-progress: false",
  "bounded_recovery_queue" => "queue: max",
  "worker_model_pin" => "cc324af070c2ecbfd324a30884d2f951a7ff756aba85cb811a6ec436933bb046",
  "qa_model_pin" => "1d9614638d18024d0fbb36575a15f1302a3adf044df10345688ec4f6e1c4ff32",
  "artifact_checksum_verify" => "sha256sum -c",
  "hard_missing_artifact_failure" => "if-no-files-found: error",
  "two_vm_post_recovery" => "post_recovery:",
  "bounded_job_timeout" => "timeout-minutes: 90"
}.each do |name, needle|
  fail!("recovery_contract_missing:#{name}") unless recovery.include?(needle)
end
fail!("recovery_must_not_continue_on_error") if recovery.include?("continue-on-error: true")

pr_bridge = File.read(WORKFLOWS.join("omega-private-pr-hosted-bridge.yml"), encoding: "UTF-8")
fail!("pr_bridge_stale_ref_guard_missing") unless pr_bridge.include?("OMEGA_EXACT_TRIGGER_NOT_REF_TIP")

puts "OMEGA_CONTROL_PLANE_INTEGRITY_GREEN workflows=#{files.length}"
