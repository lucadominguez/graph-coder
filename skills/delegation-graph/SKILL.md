---
name: delegation-graph
description: Compile implementation units into a bounded typed DAG with explicit ownership, artifacts, review gates, and safe parallel groups.
---
# Delegation Graph

Bounded authority: compile and validate a portable graph; do not execute or approve it. Manager-advisory boundary: the Director owns global graph changes and coordinator-gated JCode operations. Supervisors may decompose only an approved subtree within its child cap.

## Compilation rules

- Create atomic leaf nodes and composite coordination nodes. Supported initial types are `explore`, `spike`, `implement`, `verify`, `integrate`, `review`, `repair`, and `release`.
- Give every node role, unit IDs, parent owner, dependencies, typed artifact inputs/outputs, read/write scope, acceptance, review gate, primary/fallback route, risk, priority, estimated cost, attempt/heartbeat/expansion limits, and failure-isolation domain.
- Use literal acyclic dependencies. Represent iteration through bounded attempts or newly appended repair nodes, never a graph cycle.
- Validate every dependency and artifact producer. Reject duplicate producers and consumers that do not depend on their producer.
- Detect exact, nested-directory, case-normalized Windows, and glob write overlap. Serialize conflicting writers unless a proven merge strategy and integration owner exist.
- Build safe parallel groups only from dependency-ready nodes with no unsafe write overlap or shared contract race.
- Default bounds: 100 total nodes, depth 6, eight active workers/fan-out, two attempts, no recursive spawning.
- A failed node blocks dependent descendants only. Independent ready nodes continue. Global failure domains are exceptional and explicit.
- The root Director is graph metadata/owner, not a dispatched worker. JCode emission defaults to light/nonrecursive mode and public swarm operations.

Run `aps graph compile --plan <plan> --output <graph>` then `aps graph validate --file <graph>`. Reject a graph that does not map every unit, review gate, handoff, recovery path, and release duty.

## Decision surfaces

Atomicity, role, ownership, dependency, artifact contract, integration owner, safe concurrency, failure domain, expansion authority, retry/heartbeat/timeout, and release ordering.

## Evidence rules

Each edge cites the producer/consumer or ordering reason. Each parallel group cites dependency readiness and scope-disjoint evidence. Each custom role has bounded authority and report schema. Do not assume merge safety from different task titles.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, node_ids: [string], evidence: [string], consequence: string, proposed_resolution: string}
rehearsal_schema: {graph_id: string, acyclic: boolean, artifacts_complete: boolean, writers_safe: boolean, bounds_valid: boolean, ready_frontier: [string]}
task_schema: {node_id: string, type: string, atomicity: atomic|composite, owner: string, dependencies: [string], write_scope: [path], failure_domain: node|branch|graph|external}
report_schema: {graph_id: string, node_count: int, depth: int, safe_parallel_groups: [[string]], serialized_conflicts: [object], validation: [string]}
```

## STOP/escalation rules

Stop on a cycle, missing owner, unknown dependency, incomplete artifact handoff, duplicate producer, unsafe concurrent writer, unbounded expansion, missing review gate, exceeded graph budget, or a node requiring authority outside the approved plan.
