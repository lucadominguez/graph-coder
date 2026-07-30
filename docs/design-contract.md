# Design Contract

This document is the concise implementation contract for Graph Coder v1. The detailed product design was approved on 2026-07-27.

## Purpose

Graph Coder turns a mind dump into a maximum-reliability implementation and orchestration artifact:

```text
INTAKE_AND_CONTEXT
  -> REPOSITORY_GROUNDING
  -> CONCEPT_GRILL
  -> TECHNICAL_RESEARCH
  -> PLAN_AUTHORING
  -> COLD_REHEARSAL
  -> GRAPH_COMPILATION
  -> MODEL_ROUTING
  -> FULL_PLAN_APPROVAL
  -> DIRECTED_EXECUTION
```

Every transition is durable. Re-entry resumes or revises the current plan, reconciles semantic unit hashes and evidence, and avoids repeating valid completed work.

## Product authority

1. Explicit user decisions and approved plan revisions.
2. The canonical plan and its stable requirement, example, invariant, and unit IDs.
3. Repository evidence, current command results, and authoritative external documentation.
4. Documented defaults where the user delegated judgment.
5. Worker interpretation only inside a bounded task packet.

Subjective unresolved decisions are grilled. Technical questions are investigated rather than delegated back to the user. One full-plan approval gates execution: the complete canonical plan is rendered and the approval is bound to the plan, graph, route, and render hashes. A summary is not an approval view.

## Canonical artifacts

The plan is Markdown with YAML frontmatter and stable headings. Portable graph and handoff artifacts are JSON validated against versioned schemas. Authoritative lifecycle state is SQLite. Every material decision, route, attempt, artifact, review, transition, escalation, and result is recorded in a hash-linked ledger.

Required implementation-ready plan headings:

- Goal Capsule
- Concept and Requirements
- Scope and Non-Goals
- Acceptance and Invariants
- Repository Grounding
- Technical Research
- Technical Decisions
- System Impact
- Canonical Implementation Units
- Delegation Graph
- Routing Assignments
- Context Contract
- Verification Contract
- Failure and Recovery Contract
- Definition of Done
- Sources and Evidence

There is no Product Contract section. Concept and requirements live in the plan itself rather than in a parallel document that can drift away from it.

## Control boundaries

Python owns state, constraints, snapshots, hashes, graph validation, routing calculations, budgets, redaction, recovery, and adapter payload generation. LLMs own bounded product judgment, technical reasoning, implementation, rehearsal, and evidence-backed review.

The original root JCode session remains the Director. Managers advise and review; the Director applies coordinator-gated mutations. Neither may edit implementation files, and neither is dispatched as a swarm task. Graph Coder emits public task-graph/action bundles and does not depend on JCode private sockets.

## Authority matrix

| Role | `authority` | Repository write scope | Reviews | Implements |
| --- | --- | --- | --- | --- |
| Director | `advisory_only` | none | top-level manager outputs | never |
| Manager | `advisory_only` | none (enforced at compile time) | its own subtree only | never |
| Worker | `implementation` | its declared `write_scope` | never itself | yes |

A worker reaches `completed` only through a passing manager review. There are no reviewer agents beneath workers and no `review` nodes in the graph.

## Release gate

Implementation readiness requires all of the following:

- Bidirectional requirements-to-units traceability.
- Evidence for every load-bearing repository or API claim.
- Named producers, consumers, compatibility duties, scopes, inputs, outputs, tests, acceptance, and STOP conditions.
- Successful cold rehearsal for every leaf, with two passes for high-risk leaves.
- No unresolved P0/P1 defects.
- No unsafe concurrent writers.
- Complete graph dependencies and typed handoffs.
- Existing failures distinguished from introduced failures.
- Migration, rollback, deployment, observability, and recovery coverage when applicable.
- Explicit fan-out, depth, retry, timeout, and execution-cost bounds.
- No launch-blocking user-only question.

Planning budgets warn but never lower this quality bar.

## Routing contract

Routing is deterministic and provider-neutral. Hard capability and policy filters run first. Quality combines benchmark and verified local evidence using configurable defaults:

```text
quality = (0.60 * external_task_score + 0.30 * local_score) / 0.90
```

Graph Coder builds a non-dominated quality, cost, reliability, and latency frontier, applies the task quality floor, keeps candidates within 0.05 of the best eligible quality, prefers open-weight candidates in that set, and selects the lowest bounded expected passing cost. Deterministic tie-breakers are evidence confidence, provider reliability, latency, and stable model ID. Fallbacks must pass the same hard requirements and should use another provider.

## Explicit non-goals

Graph Coder v1 does not fork JCode, modify its Rust code, replace its swarm engine, run thesis/antithesis/debate/voting workflows, allow unbounded recursive spawning, ask an LLM to choose routes, persist provider secrets, silently substitute an unapproved planner, require Komorebi, or claim that runtime failure is impossible.
