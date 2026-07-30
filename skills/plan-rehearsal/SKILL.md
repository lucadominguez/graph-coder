---
name: plan-rehearsal
description: Cold-test every leaf task with fresh-context executors and convert valid confusion into canonical plan defects before execution.
---
# Plan Rehearsal

Bounded authority: simulate execution and report defects only. Do not implement, edit files, repair the plan, or reveal an expected critique. Manager-advisory boundary: the Director gives packets, accepts findings, invokes plan mutation, and decides when the release gate passes.

## Cold protocol

For each leaf, start a fresh agent that has not seen planning conversation. Give only:

- the exact versioned task packet;
- required dependency artifacts;
- explicitly allowed repository context and project instructions;
- no hidden answer, expected critique, or implementation permission.

Ask the executor to determine whether it can complete and verify the unit without inference outside the packet. Collect blocking questions, missing context, ambiguous steps, false-completion paths, likely scope escape, unverifiable acceptance, unsafe assumptions, dependency/artifact gaps, and STOP-condition conflicts.

A valid blocking question is a plan defect. Convert it to `review_defect` format and return it to the primary author. After plan mutation, rerun every affected rehearsal. High-risk or critical leaf nodes require two independent cold passes with different fresh agents.

Do not pass a unit because the executor sounds confident. Pass only when it identifies no valid blocker and can name the exact inputs, allowed writes, procedure, commands, expected evidence, review handoff, and stop conditions.

## Decision surfaces

Executability, hidden context, ambiguity, dependency order, artifact availability, acceptance observability, unsafe scope, pre-existing failures, platform assumptions, destructive behavior, and false completion.

## Evidence rules

Findings cite packet fields, plan IDs, repository paths/symbols explicitly permitted by the packet, or command definitions. Label speculation and give a falsifying check. Do not inspect unrelated context to rescue an under-specified packet.

## Report integrity and coverage accounting

- Count a pass only from its complete persisted report artifact. A chat excerpt, truncated delivery, worker-ready state, or coordinator recollection is not a report.
- Persist the report before marking the worker complete. Record its path, content hash, unit, pass number, agent/session identity, model route, provider, and completion time.
- Classify every expected pass as `complete`, `missing`, `truncated`, `failed`, `superseded`, or `duplicate`. Never convert missing evidence into an inferred pass.
- A replacement pass supersedes only the exact failed or stale pass it replaces. Preserve both records and the supersession link.
- High-risk or critical units pass only when every required independent pass completed after the unit's latest material mutation. Use different model families or providers when eligible. If diversity is impossible, record the candidate evidence and keep the diversity exception visible.
- Deduplicate defects by evidence and consequence, not by similar wording. Preserve every source report reference on the normalized defect.
- A dependency defect stays open until the exact producer artifact exists at its named path and version/hash, validates against its contract, and every affected consumer rehearsal is rerun against it. Planned future work is not evidence that the defect is resolved.
- After a server reload, reconstruct expected passes from durable packets and report artifacts, reconcile worker state, and launch only genuinely missing passes. Do not restart completed passes or lose failed/superseded history.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, unit_id: U-id, evidence: [string], consequence: string, proposed_resolution: string}
rehearsal_schema: {unit_id: U-id, pass: int, executable: boolean, blocking_questions: [string], missing_context: [string], ambiguous_steps: [string], false_completion_paths: [string], scope_escape_risks: [string], unsafe_assumptions: [string]}
task_schema: {plan_id: P-id, plan_version: int, unit_id: U-id, semantic_hash: string, input_artifacts: [object], inspect_targets: [string], write_scope: [path], commands: [string], stop_conditions: [string]}
report_schema: {unit_id: U-id, passes_required: int, passes_completed: int, pass_states: [complete|missing|truncated|failed|superseded|duplicate], report_paths: [path], report_hashes: [string], executable: boolean, defects: [defect-id], evidence: [string]}
```

## STOP/escalation rules

Stop on an impossible acceptance check, missing required input, unknown destructive consequence, unsafe concurrent writer, circular dependency, missing independent reviewer, prohibited context dependency, or a user-only blocker. Never implement as a way to answer the rehearsal.
