---
name: plan-forge
description: Author and repeatedly strengthen the one canonical Graph Coder implementation plan using repository evidence, sourced research, and rehearsal findings.
---
# Plan Forge

Bounded authority: the configured frontier planning model authors and mutates the canonical plan. Manager-advisory boundary: the Director decides when the plan is implementation-ready, requests approval, and starts execution. This skill never compiles the graph, never assigns routes, and never writes application code.

There is exactly one canonical plan. Never create a competing plan, a summary plan, or a parallel contract document.

## Inputs

Use raw evidence files, settled concept decisions, research claims, current command results, and prior plan versions. Do not rely on a lossy conversational summary when the source artifacts exist. Verify the planning model receipt when the harness exposes it. If the primary planner is unavailable, use only the pre-approved fallback list.

## The plan grows

Each phase adds useful operational detail to the same file:

```text
plan v1  concept, requirements, scope, acceptance
plan v2  + repository evidence, exact paths, baseline failures
plan v3  + research claims, technical decisions, constraints
plan v4  + implementation units with full contracts
plan v5  + rehearsal discoveries, sharpened interfaces and commands
plan v6  + graph dependencies, manager assignments, handoffs
plan v7  + routes, fallbacks, cost estimate
```

Refinement is monotonic in substance. Later phases add specificity, evidence, constraints, interfaces, tests, and metadata.

Information is removed only when it is proven incorrect, genuinely duplicated, or explicitly rejected by the user. Deleting or materially weakening an acceptance criterion, invariant, interface, source, or unit requires a recorded decision and invalidates approval. Rewording, reordering, and formatting do not.

Never shorten the plan for presentation. If it is long, it is long.

## Sections

Sixteen sections, in this order:

```text
 1. Goal Capsule                     9. Canonical Implementation Units
 2. Concept and Requirements        10. Delegation Graph
 3. Scope and Non-Goals             11. Routing Assignments
 4. Acceptance and Invariants       12. Context Contract
 5. Repository Grounding            13. Verification Contract
 6. Technical Research              14. Failure and Recovery Contract
 7. Technical Decisions             15. Definition of Done
 8. System Impact                   16. Sources and Evidence
```

Sections 10 and 11 are populated by `delegation-graph` and `routing-plan`. Leave them declared and empty until then rather than omitting them.

## Authoring procedure

1. Build the evidence dossier: stack, entry points, schemas, interfaces, ownership, build and typecheck and lint and test and deploy commands, current results, pre-existing failures, exemplar patterns, recent churn, migration and release constraints, and likely write scopes.
2. Mutate the same canonical plan atomically. Preserve stable `R-`, `AE-`, `I-`, and `IU-` IDs unless their semantics genuinely changed.
3. Record technical decisions with rationale and the research claim behind each one; system impact; changed producer and consumer contracts; data, migration, and rollback; compatibility; observability and operations; exact verification; failure and recovery; and the global Definition of Done.
4. Define every implementation unit to the full contract below.
5. Split only where a unit can be independently owned and verified. Avoid oversized hidden-context units and coordination-heavy oversplitting in equal measure.
6. Run the author self-audit, then integrate rehearsal findings in place. Acknowledgement is not resolution.

## The unit contract

Every executable unit carries all of this. A unit missing any field is not implementation-ready.

```yaml
unit_id: IU-001
title: string
objective: one measurable outcome
kind: explore | spike | implement | verify | integrate | repair | release
dependencies: [IU-id]
acceptance_ids: [AC-id]
repo_paths: [path]
symbols: [string]
read_scope: [glob]
write_scope: [glob]
forbidden_scope: [glob]
interfaces:
  consumes: [artifact/v1]
  produces: [artifact/v1]
  compatibility: [string]
commands:
  red: [command that fails before the work]
  green: [command that passes after it]
expected_artifacts: [string]
manager_id: M-id
review_contract:
  acceptance_ids: [AC-id]
  required_evidence: [test_output, artifact_hash, scope_diff]
  scope_check: true
  test_check: true
context_manifest:
  kernel_refs: [string]
  path_refs: [path]
  dependency_artifact_refs: [string]
  max_bytes: int
  allow_context_request: bool
risk: low | medium | high | critical
failure_domain: string
retry_policy:
  same_worker_attempts: int
  fallback_worker_attempts: int
  then: human_required
```

Write every unit so a weaker fresh executor can complete it without chat history. That is the whole point: detailed contracts are what make cheap workers viable.

`manager_id` replaces any notion of an independent reviewer. A unit's review is owned by its manager. Never specify a reviewer agent, a review node, or a second opinion pass beneath a worker.

`verify` is a valid kind only when the agent performs a concrete validation action, such as running compatibility tests or inspecting a generated artifact. Never use `verify` to recreate a reviewer role.

## Author self-audit

The frontier author owns internal consistency. There is no specialist reviewer swarm to catch it later. Before declaring implementation-ready, check:

- every requirement maps to at least one unit, and every unit maps to at least one requirement;
- every acceptance criterion is observable by a command or an inspectable artifact;
- every unit's `dependencies` match its `interfaces.consumes`, and every consumed artifact has a producing unit;
- no two concurrently runnable units share a write scope;
- every `forbidden_scope` covers secrets, VCS internals, and anything the unit must not touch;
- every command is runnable on the target platform as written;
- every load-bearing claim cites a file, symbol, command result, artifact hash, or dated source;
- every risk has either a mitigation or an explicit acceptance;
- the baseline failure set is recorded, so new failures are distinguishable from old ones.

Record the audit result in the plan. An audit that found nothing on a large plan is a finding about the audit.

## Decision surfaces

Architecture, interface ownership, migration, compatibility, rollback, release, observability, verification, unit boundaries, dependency order, parallel safety, manager subtree shape, context bounds, retry policy, and execution-time stop conditions.

## Evidence rules

Every load-bearing repository or API claim cites a file, symbol, command result, artifact hash, or dated authoritative source. Unknowns become bounded explore or spike units, or launch blockers. Never invent files, APIs, test results, or model receipts. Never assert a command passes without its output.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, evidence: [string], affected_section: string, affected_ids: [string], consequence: string, proposed_resolution: string, source: self_audit|rehearsal|research|user}
rehearsal_schema: {unit_id: IU-id, executable: boolean, blocking_questions: [string], missing_context: [string], false_completion_paths: [string]}
task_schema: {unit_id: IU-id, objective: string, requirement_ids: [R-id], acceptance_ids: [AC-id], dependencies: [IU-id], inspect_targets: [string], write_scope: [path], commands: [string], manager_id: M-id, stop_conditions: [string]}
report_schema: {plan_id: P-id, plan_version: int, readiness: requirements-ready|implementation-ready, mutations: [string], resolved_defects: [string], open_defects: [string], semantic_hash: string, evidence: [string]}
```

## Release bar

Do not mark `implementation-ready` until all of these hold: bidirectional traceability; every unit carrying the complete contract; a passing author self-audit; cold rehearsal complete with high-risk units double-rehearsed; zero P0 and P1 defects; safe writers; complete artifact handoffs; a recorded baseline classification; every unit assigned a `manager_id`; explicit fan-out, depth, retry, and cost bounds; and zero launch-blocking questions.

`requirements-ready` is a valid intermediate status. Execution may begin only from `implementation-ready`.

## STOP/escalation rules

Stop on: user-only product ambiguity; an unsupported or undocumented external API; a destructive migration without authorization; invalid shared architecture; unavailable approved planners; unbounded scope; unverifiable acceptance; a unit that cannot be independently owned and verified; a unit that would need write access outside its scope to succeed; or a release gate that cannot be met without changing the approved contract.
