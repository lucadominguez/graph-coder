# Artifact map

Every phase consumes named artifacts and produces named artifacts. Nothing is
carried between phases in conversation alone. If an artifact is not persisted, the
phase did not happen.

Durable state lives under `.graph-coder/` and in the SQLite ledger. Artifact
hashes are `sha256:` prefixed and computed over canonical JSON with sorted keys.

## Phase transitions

| Phase | Consumes | Produces | Durable record |
| --- | --- | --- | --- |
| 1. INTAKE_AND_CONTEXT | user goal, prior ledger | `project_kernel`, `change_delta`, `run_mode` | `run` row, `intake.recorded` |
| 2. REPOSITORY_GROUNDING | `project_kernel` | `grounding_facts`, `grounding_assumptions`, `baseline_results` | plan section 5, `grounding.recorded` |
| 3. CONCEPT_GRILL | goal, `grounding_facts` | `concept_requirements` | plan section 2, `concept.normalized` |
| 4. TECHNICAL_RESEARCH | open questions | `question_inventory`, `research_claim[]`, `evidence_ledger` | plan sections 6 and 16, `research.claim_recorded` |
| 5. PLAN_AUTHORING | all of the above | `canonical_plan` at `requirements-ready` then `implementation-ready` | `plan_versions`, `plan.snapshotted` |
| 6. COLD_REHEARSAL | `task_packet` per unit | `rehearsal_report[]`, plan mutations | `plan.mutated`, `rehearsal.recorded` |
| 7. GRAPH_COMPILATION | `canonical_plan` | `delegation_graph`, `manager_assignments` | `graph_nodes`, `graph_edges`, `graph.compiled` |
| 8. MODEL_ROUTING | `delegation_graph`, registry | `route_assignment[]`, `route_receipt[]` | `routes`, `route.assigned` |
| 9. FULL_PLAN_APPROVAL | plan, graph, routes | `approval_record` bound to four hashes | `plan.approved` |
| 10. DIRECTED_EXECUTION | `task_packet`, `context_patch` | `worker_report[]`, `manager_review[]`, `manager_advice[]` | `attempts`, `artifacts`, `reviews`, execution events |

## Artifact shapes

### task_packet

What a worker receives. Nothing else.

```yaml
plan_id: P-id
plan_hash: sha256
graph_hash: sha256
node_id: N-id
unit_id: IU-id
manager_id: M-id
objective: string
acceptance: [{acceptance_id, statement, check}]
repo_paths: [path]
symbols: [string]
read_scope: [glob]
write_scope: [glob]
forbidden_scope: [glob]
interfaces: {consumes: [string], produces: [string], compatibility: [string]}
dependency_artifacts: [{unit_id, artifact, hash}]
commands: {red: [string], green: [string]}
expected_artifacts: [string]
review_contract: {acceptance_ids: [string], required_evidence: [string], scope_check: bool, test_check: bool}
retry_policy: {same_worker_attempts: int, fallback_worker_attempts: int, then: human_required}
context_hash: sha256
route_receipt: {model, provider, expected_passing_cost}
```

### worker_report

```yaml
node_id: N-id
unit_id: IU-id
manager_id: M-id
attempt: int
plan_hash: sha256
graph_hash: sha256
changed_paths: [path]
produced_artifacts: [{path, hash}]
commands_run: [{command, exit_code, output_excerpt}]
acceptance_evidence: [{acceptance_id, evidence}]
deviations: [string]
unresolved_questions: [string]
context_requests_made: [request_id]
status: submitted
```

A report that omits `changed_paths`, command results, or acceptance evidence is
incomplete and cannot be reviewed. Return it for completion; do not guess.

### manager_review

```yaml
artifact_type: manager_review
artifact_id: MR-<unit>-<attempt>
manager_id: M-id
node_id: N-id
unit_id: IU-id
attempt: int
plan_hash: sha256
graph_hash: sha256
reviewed_artifact_hashes: [sha256]
verdict: pass | repair_required | human_required
acceptance_results: [{acceptance_id, status, evidence: [string]}]
scope_result: {status, unexpected_writes: [path]}
verification_results: [{command, expected, observed}]
defects: [{defect_id, severity, evidence, consequence}]
repair_instructions: [string]
escalation: null | {question, attempts_made, impacted_nodes, runnable_independent_nodes}
model_receipt: {}
```

Rules that hold without exception:

- `repair_required` needs at least one bounded defect and one repair instruction.
- `human_required` needs the unresolved question, the attempts already made, the
  impacted nodes, and the independent nodes that remain runnable.
- A review contains no repository writes. It is a verdict and evidence.
- A node cannot review itself; a manager reviews only its own subtree.

### manager_advice

```yaml
manager_id: M-id
node_id: N-id
problem: string
evidence: [string]
likely_cause: string
allowed_recovery_options: [string]
recommended_option: string
tradeoff: string
worker_permitted_actions: [string]
proposed_plan_change: null | string
escalation_threshold: string
```

Advice never contains a patch, a diff, or replacement code. If the answer requires
editing a file, that is a repair for a worker, not advice.

### context_manifest, context_request, context_patch

```yaml
context_manifest:
  kernel_refs: [string]
  path_refs: [path]
  dependency_artifact_refs: [string]
  max_bytes: int
  allow_context_request: bool

context_request:
  request_id: string
  requester_node_id: N-id
  unit_id: IU-id
  manager_id: M-id
  question: string
  why_needed: string
  requested_paths: [path]
  requested_symbols: [string]
  current_blocker: string
  max_bytes: int

context_patch:
  request_id: string
  supplied_refs: [string]
  excerpts_or_artifact_refs: [string]
  omitted_requests: [{request, reason}]
  hashes: [sha256]
  byte_count: int
  supplied_by: string
```

An omitted request is recorded with its reason. Silently dropping part of a request
is how a worker ends up guessing.

### research_claim

```yaml
claim_id: RC-id
question_id: RQ-id
claim: string
source_url: string
source_type: official_documentation | primary_repository | standard | vendor_blog | community
version_or_date: string
retrieved_at: iso8601
confidence: high | medium | low
decision_impact: string
affected_unit_ids: [IU-id]
conflicts_with: [RC-id]
```

## Invalidation

Invalidation cascades forward, never backward.

| Change | Invalidates |
| --- | --- |
| Concept or requirements | plan readiness, rehearsal, graph, routes, approval |
| A unit's objective, acceptance, interfaces, scopes, or commands | that unit's rehearsal, its graph node, its route, approval |
| Unit added or removed | graph, routes, approval |
| Manager assignment or subtree shape | graph, approval |
| Route registry beyond its freshness window | routes, cost estimate, approval |
| Context contract | approval |
| Rewording, formatting, typo fix | nothing |

Approval is bound to the plan hash, graph hash, route hash, and render hash. If any
of the four changes, the previous approval is void and the full plan is rendered
again. Do not ask the user to approve a diff in place of the plan.

## Semantic hashing

The plan's semantic hash covers objectives, acceptance criteria, dependencies,
interfaces, read and write and forbidden scopes, commands, expected artifacts,
manager and review contracts, context manifests, and routing constraints. It
deliberately excludes prose ordering, whitespace, and section wording, so editorial
passes do not churn approval.
