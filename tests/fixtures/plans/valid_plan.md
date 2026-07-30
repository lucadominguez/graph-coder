---
artifact_contract: agent-planning-system/v1
artifact_readiness: implementation-ready
plan_id: P-demo
plan_version: 1
planned_at_commit: abc123
primary_planning_model: test-model
planning_model_receipt: verified
approved: true
requirements:
  - requirement_id: R-demo
    description: Implement contracts
    unit_ids: [U-demo]
acceptance_examples:
  - example_id: AE-demo
    description: Valid and invalid fixtures exercise contracts
    unit_ids: [U-demo]
invariants:
  - invariant_id: I-demo
    description: Only allowed files are edited
    unit_ids: [U-demo]
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
  - unit_id: U-demo
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
    output_artifacts: [schemas/plan.schema.json]
    risk: medium
    complexity: medium
    capability_profile: {}
    primary_route: local
    fallback_route: local
    attempt_limit: 2
    escalation_conditions: [test failure]
    reviewer: aps-review
    stop_conditions: [unexpected file scope]
    completion_evidence: [pytest passed]
    status: pending
---
## Goal Capsule
Implement Graph Coder validation helpers.

## Product Contract
Valid fixtures pass and invalid fixtures fail.

## Planning Contract
Plan is implementation-ready with stable metadata.

## System Impact
Only allowed contract and plan files are modified.

## Implementation Units
U-demo owns validation helpers.

## Execution Graph
U-demo has no dependencies.

## Routing Assignments
U-demo routes to local implementation.

## Verification Contract
Run focused pytest contract and plan tests.

## Failure and Recovery Contract
Rollback is file revert and failed gates reopen units.

## Definition of Done
Contracts validate and lifecycle checks pass.

## Sources and Evidence
Fixtures and tests provide evidence.
