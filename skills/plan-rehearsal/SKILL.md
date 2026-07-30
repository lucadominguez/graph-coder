---
name: plan-rehearsal
description: Cold-test every implementation unit with fresh-context agents using the exact future task packet, and convert valid confusion into canonical plan changes before execution.
---
# Plan Rehearsal

Bounded authority: simulate execution and report findings. Do not implement, edit files, repair the plan, or reveal an expected critique. Manager-advisory boundary: the Director supplies packets, accepts findings, and decides when the release bar is met; `plan-forge` performs every plan mutation.

This is an executability trial, not an execution review. It answers one question per unit: could a fresh worker complete and verify this from its packet alone? It does not replace the manager review that happens during execution, and it never substitutes for it.

## Cold protocol

For each unit, start a fresh agent that has not seen the planning conversation. Give it the exact task packet the future worker will receive, and nothing more:

```text
COLD TASK PACKET
├── exact unit objective
├── repository commit
├── relevant repository instructions
├── exact files the agent may inspect
├── allowed read scope
├── allowed write scope
├── forbidden scope
├── dependencies
├── upstream artifact contracts
├── schema or example for artifacts that do not exist yet
├── required interfaces
├── implementation procedure
├── acceptance criteria
├── exact verification commands
├── known existing failures
├── required completion evidence
├── manager and review contract
└── STOP and escalation conditions
```

No hidden answer. No expected critique. No implementation permission. No full-repository context.

## Rehearsal agent instructions

Give the fresh agent this, verbatim in substance:

```text
You are simulating this task, not implementing it.

Determine whether a fresh implementation agent could complete this task using
only this packet and its allowed repository access.

Report:
1. Missing information
2. Ambiguous instructions
3. Missing upstream contracts
4. Unsafe assumptions
5. Unverifiable acceptance criteria
6. Incorrect file ownership
7. Likely integration failures
8. Exact plan changes required

Do not edit application files.
Do not invent missing information.
Do not treat a future artifact as missing when its producer, path, schema, and
example are already defined.
```

That last rule matters. A rehearsal agent that flags every not-yet-existing artifact produces noise instead of findings.

## Judging a pass

Do not pass a unit because the agent sounds confident. Pass only when it identifies no valid blocker and can name, unprompted: its exact inputs, its allowed writes, the procedure, the commands, the expected evidence, the review handoff to its manager, and its stop conditions.

A valid blocking question is a plan defect. Convert it to defect format and return it to `plan-forge`. After the plan mutates, rerun every affected rehearsal. Unaffected units keep their existing passes and their unit IDs.

High-risk and critical units require two independent cold passes with different fresh agents, preferably using different model families or providers. These are executability trials run twice, not a reviewer role in disguise. If diversity is impossible, record the candidate evidence and keep the exception visible.

## Findings that are not defects

Discard a finding, with a recorded reason, when it: asks for context the unit genuinely does not need; requests the full repository; objects to a future artifact whose contract is already specified; restates a stop condition as a problem; or proposes scope the plan explicitly excluded.

Discarding is a decision with a reason attached, not a silent drop.

## Report integrity and coverage accounting

- Count a pass only from its complete persisted report artifact. A chat excerpt, a truncated delivery, an agent-ready state, or a coordinator's recollection is not a report.
- Persist the report before marking the pass complete. Record its path, content hash, unit, pass number, agent identity, model route, provider, and completion time.
- Classify every expected pass as `complete`, `missing`, `truncated`, `failed`, `superseded`, or `duplicate`. Never convert missing evidence into an inferred pass.
- A replacement pass supersedes only the exact failed or stale pass it replaces. Preserve both records and the supersession link.
- High-risk and critical units pass only when every required independent pass completed after the unit's latest material mutation.
- Deduplicate findings by evidence and consequence, not by similar wording. Preserve every source report reference on the merged finding.
- A dependency finding stays open until the exact producer artifact exists at its named path and version, validates against its contract, and every affected consumer rehearsal is rerun against it. Planned future work is not evidence of resolution.
- After a server reload, reconstruct expected passes from durable packets and report artifacts, reconcile agent state, and launch only genuinely missing passes. Do not restart completed passes or lose failed and superseded history.

## Decision surfaces

Executability, hidden context, ambiguity, dependency order, artifact availability, acceptance observability, unsafe scope, pre-existing failures, platform assumptions, destructive behavior, false completion, finding validity, and pass diversity.

## Evidence rules

Findings cite packet fields, plan IDs, repository paths or symbols the packet explicitly permits, or command definitions. Label speculation as speculation and give a falsifying check. Do not inspect unrelated context to rescue an under-specified packet; needing that context is itself the finding.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, unit_id: IU-id, evidence: [string], consequence: string, proposed_resolution: string}
rehearsal_schema: {unit_id: IU-id, pass: int, executable: boolean, blocking_questions: [string], missing_context: [string], ambiguous_steps: [string], false_completion_paths: [string], scope_escape_risks: [string], unsafe_assumptions: [string], discarded_findings: [{finding, reason}]}
task_schema: {plan_id: P-id, plan_version: int, unit_id: IU-id, semantic_hash: string, input_artifacts: [object], inspect_targets: [string], read_scope: [path], write_scope: [path], forbidden_scope: [path], commands: [string], manager_id: M-id, stop_conditions: [string]}
report_schema: {unit_id: IU-id, passes_required: int, passes_completed: int, pass_states: [complete|missing|truncated|failed|superseded|duplicate], report_paths: [path], report_hashes: [string], executable: boolean, defects: [defect-id], evidence: [string]}
```

## STOP/escalation rules

Stop on: an impossible acceptance check; a missing required input with no producer; an unknown destructive consequence; an unsafe concurrent writer; a circular dependency; a unit with no `manager_id`; a prohibited context dependency; or a blocker only the user can resolve. Never implement as a way to answer the rehearsal.
