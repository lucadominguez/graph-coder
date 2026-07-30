---
name: plan-forge
description: Author and repeatedly strengthen the one canonical Graph Coder implementation plan using repository evidence and structured specialist defects.
---
# Plan Forge

Bounded authority: the configured primary planning model authors patches to the canonical plan. Manager-advisory boundary: the Director selects the approved planner list, invokes reviewers, applies the final mutation, requests approval, and executes. Reviewers do not create alternative plans.

## Inputs

Use raw evidence files, settled decisions, current command results, prior plan versions, and authoritative documentation. Do not rely on a lossy conversational summary when source artifacts are available. Verify the planning model receipt when the harness exposes it. If the primary is unavailable, use only the pre-approved fallback list.

## Authoring procedure

1. Build the evidence dossier: stack, entry points, schemas, interfaces, ownership, build/typecheck/lint/test/deploy commands, current results, pre-existing failures, exemplar patterns, recent churn, migration/release constraints, and likely write scopes.
2. Mutate the same canonical plan atomically. Preserve stable `R-`, `AE-`, `I-`, and `U-` IDs unless their semantics genuinely change.
3. Add technical decisions and rationale; system impact; changed producer/consumer contracts; data/migration and rollback; compatibility; observability and operations; exact verification; failure/recovery; and global Definition of Done.
4. Define every `U-` unit so a weaker fresh executor can work without chat history: objective, mappings, rationale, dependencies, input artifacts, exact files/symbols to inspect, read/write/forbidden scope, interfaces and invariants, detailed procedure, forward and regression proof, exact commands and expected results, output artifacts, risk/complexity, capability profile, primary/fallback route placeholders, retry/escalation, independent reviewer, STOP conditions, and completion evidence schema.
5. Split only where a unit can be independently owned and verified. Avoid oversized hidden-context tasks and coordination-heavy oversplitting.
6. Activate specialist review from actual risk: public contract, persistent data, auth/permissions, UI fidelity, performance, infrastructure/release, large refactor, external service, weak baseline, concurrent writers, or unfamiliar technology.
7. Integrate every valid defect in place. Acknowledgement is not resolution. Re-run affected reviews after mutation.

## Decision surfaces

Architecture, interface ownership, migration, compatibility, rollback, release, observability, verification, task boundaries, dependency order, parallel safety, and execution-time stop conditions.

## Evidence rules

Every load-bearing repository/API claim cites a file/symbol, command result, artifact hash, or authoritative source. Unknowns become bounded explore/spike units or launch blockers. Never invent files, APIs, test results, or model receipts.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, evidence: [string], affected_section: string, affected_ids: [string], consequence: string, proposed_resolution: string, reviewer_identity: string, model_receipt: string}
rehearsal_schema: {unit_id: U-id, executable: boolean, blocking_questions: [string], missing_context: [string], false_completion_paths: [string]}
task_schema: {unit_id: U-id, objective: string, requirement_ids: [R-id], acceptance_example_ids: [AE-id], dependencies: [U-id], inspect_targets: [string], write_scope: [path], commands: [string], stop_conditions: [string]}
report_schema: {plan_id: P-id, plan_version: int, mutations: [string], resolved_defects: [string], open_defects: [string], evidence: [string]}
```

## Release bar

Do not mark implementation-ready until bidirectional traceability, evidence, changed contracts, cold rehearsal, high-risk double rehearsal, zero P0/P1 defects, safe writers, complete handoffs, baseline classification, applicable operations, manager responses, explicit fan-out/depth/retry/cost bounds, and zero launch-blocking questions all pass.

## STOP/escalation rules

Stop on user-only product ambiguity, unsupported or undocumented external API, destructive migration without authorization, invalid shared architecture, unavailable approved planners, unbounded scope, unverifiable acceptance, or a release gate that cannot be met without changing the contract.
