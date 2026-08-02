---
name: delegation-graph
description: Compile implementation units into a bounded typed DAG of advisory managers and implementing workers, with explicit ownership, artifacts, review assignment, and safe parallel groups.
---
# Delegation Graph

Bounded authority: compile and validate a portable graph. Do not execute it, route it, or approve it. Manager-advisory boundary: the Director owns global graph changes and coordinator-gated harness operations. A manager may decompose only its own approved subtree, within its child cap.

## Hierarchy

```text
Frontier Director                     root, advisory_only, never dispatched as a worker
├── Manager A                         advisory_only, reviews branch A
│   ├── Worker A1                     implements unit A1
│   ├── Worker A2                     implements unit A2
│   └── Repair Worker A3              created only when Manager A rejects a result
├── Manager B                         advisory_only, reviews branch B
│   ├── Worker B1
│   └── Worker B2
└── Manager C                         advisory_only, reviews integration and release
    └── Integration Worker C1
```

Compile one manager per meaningful branch or failure domain, never one manager per worker. A manager owns a coherent subtree whose shared context and interfaces fit inside its limits. If a manager's subtree needs context it cannot hold, the branch is drawn wrong.

## Node model

```text
kind:         manage | explore | spike | implement | verify | integrate | repair | release
role:         composite | atomic
authority:    advisory_only | implementation
review_owner: <manager node id>
```

Every node also carries: unit IDs, parent owner, dependencies, typed artifact inputs and outputs, read and write scope, acceptance, primary and fallback route, risk, priority, estimated cost, attempt and heartbeat and expansion limits, and failure-isolation domain.

Every node of a kind other than `manage` is a subagent that execution will spawn. Compile with that in mind: a node too vague to hand to a fresh agent that has read nothing else is a node the Director will be tempted to implement itself, which is the one outcome the graph exists to prevent.

## Invariants

Compilation fails if any of these is violated.

- `manage` nodes are `composite`, `advisory_only`, and hold empty write scopes.
- Atomic executable nodes are `authority: implementation` and name an ancestor manager as `review_owner`.
- No node reviews itself.
- A manager reviews only nodes inside its own subtree.
- The root Director is advisory-only and is never emitted as an implementation unit.
- No node has kind `review`. Review is a manager verdict and an artifact, not a task in the DAG.
- Dependencies and artifact edges are acyclic.
- Exactly one producer per artifact; every required artifact has a producer; every consumer depends on its producer.
- No unsafe concurrent write overlap, including exact, nested-directory, case-normalized Windows, and glob overlap.
- Child caps, depth, node count, and attempt bounds are respected.

Keep `verify` nodes only where the agent performs a concrete validation action, such as running compatibility tests or inspecting a generated artifact. A `verify` node that merely reads someone else's work and opines is a reviewer node with a different label; reject it.

Represent iteration through bounded attempts or newly appended repair nodes, never a graph cycle. Advice, context requests, and escalations are control-plane events, not dependency edges, so the implementation DAG stays acyclic however much a branch negotiates.

## Review assignment

Set every worker's `review_owner` to its direct manager. Set top-level manager outputs to be reviewed by the Director. Do not compile review tasks; the worker's `review_contract` and the execution events carry the review.

## Safe parallel groups

Build parallel groups only from dependency-ready nodes with no unsafe write overlap and no shared contract race. Serialize conflicting writers unless a proven merge strategy and a named integration owner both exist. Do not infer merge safety from differing task titles.

Graph optimization must never group:

- managers with workers;
- nodes owned by different managers;
- writing nodes with overlapping write scopes;
- nodes from different failure domains where grouping would couple their failures.

## Stability

Unchanged plan units keep their node IDs across recompilation. Stable IDs are what make resume, recovery, and supersession meaningful. Renumbering a graph because it was recompiled destroys the ledger's ability to explain itself.

## Bounds

```text
maximum nodes            100
maximum depth              6
maximum active workers     8
maximum fan-out            8
maximum attempts           2
recursive spawning   disabled
```

A failed node blocks its dependent descendants only. Independent ready nodes continue. Global failure domains are exceptional and explicit.

## Commands

```text
graph-coder graph compile --plan <plan> --output <graph>
graph-coder graph validate --file <graph>
graph-coder jcode emit --graph <graph>
```

Reject a graph that does not map every unit, review assignment, artifact handoff, recovery path, and release duty.

## Decision surfaces

Atomicity, node kind, authority, manager subtree shape, review ownership, dependency, artifact contract, integration owner, safe concurrency, failure domain, expansion authority, retry and heartbeat and timeout bounds, and release ordering.

## Evidence rules

Each edge cites its producer and consumer, or its ordering reason. Each parallel group cites dependency readiness and scope-disjoint evidence. Each manager cites the units in its subtree and why they share a context boundary. Do not assume merge safety, and do not assign a `review_owner` that is not an ancestor.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, node_ids: [string], evidence: [string], consequence: string, proposed_resolution: string}
rehearsal_schema: {graph_id: string, acyclic: boolean, artifacts_complete: boolean, writers_safe: boolean, bounds_valid: boolean, managers_advisory: boolean, review_owners_valid: boolean, review_nodes: 0, ready_frontier: [string]}
task_schema: {node_id: string, kind: string, role: atomic|composite, authority: advisory_only|implementation, review_owner: string, owner: string, dependencies: [string], write_scope: [path], failure_domain: string}
report_schema: {graph_id: string, node_count: int, manager_count: int, worker_count: int, depth: int, safe_parallel_groups: [[string]], serialized_conflicts: [object], critical_path: [string], validation: [string]}
```

## STOP/escalation rules

Stop on: a cycle; a missing owner; an unknown dependency; an incomplete artifact handoff; a duplicate producer; an unsafe concurrent writer; unbounded expansion; an exceeded graph budget; a `manage` node with a non-empty write scope; an executable node with no ancestor manager; a node that would need kind `review` for the graph to make sense; or a node requiring authority outside the approved plan.
