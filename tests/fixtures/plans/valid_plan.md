---
artifact_contract: graph-coder/v1
artifact_readiness: implementation-ready
plan_id: P-demo
plan_version: 1
planned_at_commit: abc123
primary_planning_model: test-model
planning_model_receipt: verified
approved: true
approval:
  plan_hash: sha256:1111111111111111111111111111111111111111111111111111111111111111
  graph_hash: sha256:2222222222222222222222222222222222222222222222222222222222222222
  route_hash: sha256:3333333333333333333333333333333333333333333333333333333333333333
  render_hash: sha256:4444444444444444444444444444444444444444444444444444444444444444
  rendered_full_plan: true
requirements:
  - requirement_id: R-demo
    description: Implement contracts
    unit_ids: [IU-demo]
acceptance_examples:
  - example_id: AE-demo
    description: Valid and invalid fixtures exercise contracts
    unit_ids: [IU-demo]
invariants:
  - invariant_id: I-demo
    description: Only allowed files are edited
    unit_ids: [IU-demo]
release_gate:
  all_leaf_rehearsals_passed: true
  high_risk_double_rehearsed: true
  artifact_handoffs_complete: true
  existing_failures_classified: true
  operations_complete_when_applicable: true
  manager_failure_classes_complete: true
  open_p0_defects: 0
  open_p1_defects: 0
  unsafe_write_overlaps: 0
  launch_blocking_questions: 0
  max_active_workers: 2
  max_total_nodes: 4
  max_graph_depth: 2
  attempt_limit: 2
  execution_cost_ceiling: 1.0
units:
  - unit_id: IU-demo
    title: Contract helpers
    objective: Implement Graph Coder validation helpers
    acceptance:
      - JSON schema fixtures validate
    requirement_ids: [R-demo]
    acceptance_example_ids: [AE-demo]
    rationale: Required for reliable artifact exchange
    dependencies: []
    input_artifacts: [schemas]
    inspect_targets: [src/graph_coder/contracts.py]
    read_scope: [src/graph_coder/contracts.py]
    write_scope: [src/graph_coder/contracts.py]
    forbidden_scope: [README.md]
    interfaces: [validate_artifact]
    procedure: [implement, test]
    forward_proof: [pytest]
    regression_proof: [invalid fixture fails]
    commands: [uv run pytest tests/test_contracts.py tests/test_plans.py]
    output_artifacts: [schemas/v1/plan.schema.json]
    output_contract:
      - The schema file parses as JSON Schema and declares required properties.
      - A known-invalid fixture is rejected by it, so the schema is not vacuous.
    progress_contract:
      checkpoint_every: single pass, one schema written once
      writes_incrementally: false
      command_timeout_seconds: 120
    risk: medium
    complexity: medium
    failure_domain: contracts
    capability_profile: {}
    primary_route: local
    fallback_route: local
    attempt_limit: 2
    escalation_conditions: [test failure]
    manager_id: M-CONTRACTS
    review_contract:
      acceptance_ids: [AE-demo]
      required_evidence: [test_output, artifact_hash, scope_diff]
      scope_check: true
      test_check: true
    context_manifest:
      kernel_refs: ["project:test-command"]
      path_refs: [src/graph_coder/contracts.py]
      dependency_artifact_refs: []
      max_bytes: 48000
      allow_context_request: true
    retry_policy:
      same_worker_attempts: 1
      fallback_worker_attempts: 1
      then: human_required
    stop_conditions: [unexpected file scope]
    completion_evidence: [pytest passed]
    status: pending
---
## Goal Capsule
Implement Graph Coder validation helpers.

## Concept and Requirements
Artifacts must be exchangeable between agents without ambiguity. R-demo covers it.

## Scope and Non-Goals
In scope: contract validation helpers. Not in scope: schema authoring.

## Acceptance and Invariants
AE-demo exercises valid and invalid fixtures. I-demo forbids edits outside scope.

## Repository Grounding
Contracts live in `src/graph_coder/contracts.py`. The test baseline is green.

## Technical Research
No external dependency questions were open for this change.

## Technical Decisions
Validation is schema-driven and selected by artifact contract and type.

## System Impact
Only allowed contract and plan files are modified.

## Canonical Implementation Units
IU-demo owns validation helpers and is reviewed by M-CONTRACTS.

## Delegation Graph
IU-demo has no dependencies and sits under manager M-CONTRACTS.

## Routing Assignments
IU-demo routes to local implementation with a local fallback.

## Context Contract
The worker receives only `src/graph_coder/contracts.py` and its unit contract.

## Verification Contract
Run focused pytest contract and plan tests.

## Failure and Recovery Contract
Rollback is a file revert. A failed manager review reopens the unit for repair.

## Definition of Done
Contracts validate, lifecycle checks pass, and the manager review passed.

## Sources and Evidence
Fixtures and tests provide evidence.
