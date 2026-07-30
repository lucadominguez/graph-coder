---
name: concept-grill
description: Grill a rough request into settled product decisions by orchestrating an installed third-party brainstorming skill, then normalize the result into the canonical plan.
---
# Concept Grill

Bounded authority: run the dependency preflight, select one concept workflow, invoke it, and normalize its output into the canonical plan. Manager-advisory boundary: the Director decides whether the concept is settled enough to leave the phase. This skill never authors implementation units, never conducts technical research, and never writes application code.

This is a controller and a normalizer. It is not a brainstorming framework. The questioning rigor comes from the installed third-party skill, which is better than anything worth rewriting here.

## Selection

Exactly one primary workflow runs. At most one conditional supplemental workflow runs before it.

```text
Is product viability, user value, positioning, or startup strategy
materially uncertain?
├── yes  -> gstack office-hours, then feed the approved conclusions
│           into ce-brainstorm as settled input
└── no   -> ce-brainstorm directly
```

| Order | Trigger | Role | On absence |
| --- | --- | --- | --- |
| 1 (conditional) | `office-hours` | Product and demand uncertainty | Note it, continue |
| 2 (default) | `ce-brainstorm` | Concept grilling | Stop, or fall back with disclosure |
| Fallback | `superpowers:brainstorming` | Degraded mode | Requires explicit user acceptance |

Never run all three by default. Duplicate questioning costs the user time and tokens and produces contradictory settled decisions.

`office-hours` earns its slot through six forcing questions: is there actual demand, what is the current workaround, what is the narrowest wedge, what evidence has been observed, does it fit where the product is going, and who specifically wants it. Use it when those answers are unknown, not as a warm-up.

`ce-brainstorm` earns its slot because it separates what to build from how to build it, challenges assumptions instead of collecting requirements, asks one focused question at a time, distinguishes settled decisions from unexamined claims, right-sizes the process for lightweight, standard, or deep work, and refuses to let several independently deliverable products get stuffed into one plan.

Exact triggers, versions, licenses, observed paths, and install commands are in `../graph-coder/references/third-party-skills.md`. Re-verify before relying on them.

## Preflight

1. Resolve the required trigger in the harness that is actually running Graph Coder. Presence in another harness's plugin cache does not count.
2. If the default dependency is missing, stop before plan approval. Give the user the exact installation step and wait.
3. If only the fallback is available, disclose the degradation, name what is weaker about it, and continue only with explicit acceptance.
4. Record the resolved trigger, version, and harness, and append a `dependency.preflight` event.

Never simulate a third-party skill and report its reliability. A phase that ran without its dependency did not happen.

## Scope of questioning

Ask only what the user alone can answer.

In scope: product intent, the problem and who has it, user journeys, features and priorities, taste and design, scope and non-goals, subjective tradeoffs, success thresholds, autonomy preferences, and anything sensitive or irreversible.

Out of scope: anything a repository read, a command run, or a documentation lookup would answer. Those become entries in the technical-research question inventory. Do not answer them here and do not let the third-party skill's own research tendencies pull the phase into architecture.

Never ask a question the repository can answer. Inspect first.

## Normalization

The third-party skill will produce its own artifact, and `ce-brainstorm` calls its output a requirements-only Product Contract. Graph Coder has no Product Contract phase and no Product Contract document. Normalize the result into the canonical plan instead:

```text
canonical plan
├── 2. Concept and Requirements
│      goal and problem
│      users and workflows
│      requirements with stable R- IDs
│      acceptance examples with stable AE- IDs
│      invariants with stable I- IDs
│      settled decisions, each with who decided and why
│      defaults applied where the user wanted minimal intervention
└── 3. Scope and Non-Goals
```

Preserve stable IDs across reruns. A requirement that survives rewording keeps its ID; only genuinely changed semantics get a new one.

Every requirement must be testable. A requirement that cannot be checked is a preference, and it belongs in settled decisions rather than in requirements.

Distinguish a settled decision from an unexamined claim. A settled decision names its owner and its reason. An unexamined claim becomes either a question for the user or an entry in the research inventory.

Open technical questions leave this phase as a queue, not as prose: `{question_id, decision_required, why_it_blocks, suggested_source_type}`.

Plan status after this phase is `requirements-ready`. That is not executable. Only `implementation-ready` is.

## Decision surfaces

Viability uncertainty, workflow selection, fallback acceptance, question scope, subjective versus technical, requirement testability, settled versus unexamined, ID stability, default application, and phase exit readiness.

## Evidence rules

A settled decision cites the user's answer or an explicitly accepted default. A requirement cites the decision it came from. Never invent user demand, never infer a preference the user did not state, and never record a default as a user decision. Repository claims cite a file, symbol, or command result.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, evidence: [string], affected_section: string, affected_ids: [R-id|AE-id|I-id], consequence: string, proposed_resolution: string}
rehearsal_schema: {concept_complete: boolean, untestable_requirements: [R-id], unexamined_claims: [string], user_blockers: [string]}
task_schema: {workflow: ce-brainstorm|office-hours|superpowers:brainstorming, harness: string, version: string, degraded: boolean, question_scope: [string]}
report_schema: {workflow_used: string, dependency_status: resolved|fallback|missing, settled_decisions: [object], requirements: [R-id], acceptance_examples: [AE-id], invariants: [I-id], research_queue: [object], open_user_blockers: [string]}
```

## STOP/escalation rules

Stop on: a missing required dependency; a fallback the user has not accepted; a product decision only the user can make; a concept that contains more than one independently deliverable product; a value proposition that cannot be stated without inventing demand; a requirement that cannot be made testable; or a user instruction that conflicts with a previously settled decision without acknowledging it.
