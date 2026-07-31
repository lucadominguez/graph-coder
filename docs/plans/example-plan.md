---
artifact_contract: graph-coder/v1
artifact_readiness: implementation-ready
plan_id: P-example
plan_version: 1
planned_at_commit: 0000000000000000000000000000000000000000
primary_planning_model: example/frontier
planning_model_receipt: verified
approved: true
approval:
  plan_hash: sha256:1111111111111111111111111111111111111111111111111111111111111111
  graph_hash: sha256:2222222222222222222222222222222222222222222222222222222222222222
  route_hash: sha256:3333333333333333333333333333333333333333333333333333333333333333
  render_hash: sha256:4444444444444444444444444444444444444444444444444444444444444444
  rendered_full_plan: true
requirements:
  - requirement_id: R-REVOKE
    description: An operator can revoke a single API token immediately, and the revoked token stops authenticating on the next request.
    unit_ids: [IU-MIGRATION, IU-STORE, IU-SCHEMA, IU-ENDPOINT]
  - requirement_id: R-AUDIT
    description: Every revocation records who revoked which token and when, and the record survives a process restart.
    unit_ids: [IU-MIGRATION, IU-STORE]
acceptance_examples:
  - example_id: AE-REVOKED-TOKEN-FAILS
    description: A token revoked by POST /tokens/{id}/revoke returns 401 on its next authenticated request, not on a later cache expiry.
    unit_ids: [IU-ENDPOINT, IU-STORE, IU-SCHEMA]
  - example_id: AE-DOUBLE-REVOKE
    description: Revoking an already revoked token returns 200 and leaves exactly one audit row, so a retried request is safe.
    unit_ids: [IU-ENDPOINT, IU-STORE]
  - example_id: AE-AUDIT-SURVIVES-RESTART
    description: An audit row written before a restart is present and unchanged after it.
    unit_ids: [IU-MIGRATION, IU-STORE]
invariants:
  - invariant_id: I-NO-PLAINTEXT
    description: No token secret is written to the database, a log line, or an error body.
    unit_ids: [IU-MIGRATION, IU-STORE, IU-SCHEMA, IU-ENDPOINT]
  - invariant_id: I-SCOPE
    description: Each unit edits only the files in its write scope.
    unit_ids: [IU-MIGRATION, IU-STORE, IU-SCHEMA, IU-ENDPOINT]
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
  max_total_nodes: 7
  # Bounds the longest dependency chain, not the manager tree:
  # IU-MIGRATION -> IU-STORE -> IU-ENDPOINT.
  max_graph_depth: 3
  attempt_limit: 2
  execution_cost_ceiling: 4.0
units:
  - unit_id: IU-MIGRATION
    title: Revocation columns and audit table
    objective: Add revoked_at and revoked_by to api_tokens, and create the token_revocations audit table.
    acceptance:
      - Applying the migration on a populated database leaves existing rows valid with revoked_at NULL.
      - The migration is reversible, and the down path drops only what the up path created.
    requirement_ids: [R-REVOKE, R-AUDIT]
    acceptance_example_ids: [AE-AUDIT-SURVIVES-RESTART]
    rationale: Revocation has to outlive the process, so it is a schema change before it is an endpoint.
    dependencies: []
    input_artifacts: [migrations/001_initial.sql]
    inspect_targets: [migrations/001_initial.sql, src/store/models.py]
    read_scope: [migrations/001_initial.sql, src/store/models.py]
    write_scope: [migrations/002_token_revocation.sql]
    forbidden_scope: [src/api/, migrations/001_initial.sql]
    interfaces: [api_tokens.revoked_at, api_tokens.revoked_by, token_revocations]
    procedure:
      - Read 001_initial.sql and record the exact api_tokens column set.
      - Write the up and down migration in one file.
      - Apply, roll back, and apply again against a seeded copy.
    forward_proof: [make migrate-test]
    regression_proof: [Existing rows still load through src/store/models.py after the migration]
    commands: [make migrate-test]
    output_artifacts: [migrations/002_token_revocation.sql]
    risk: high
    complexity: medium
    failure_domain: storage
    capability_profile: {}
    primary_route: local
    fallback_route: local
    attempt_limit: 2
    escalation_conditions: [The down path is not clean, Existing rows fail to load after the up path]
    manager_id: M-STORAGE
    review_contract:
      acceptance_ids: [AE-AUDIT-SURVIVES-RESTART]
      required_evidence: [test_output, artifact_hash, scope_diff]
      scope_check: true
      test_check: true
    context_manifest:
      kernel_refs: ["project:test-command", "project:migration-tool"]
      path_refs: [migrations/001_initial.sql, src/store/models.py]
      dependency_artifact_refs: []
      max_bytes: 48000
      allow_context_request: true
    retry_policy:
      same_worker_attempts: 1
      fallback_worker_attempts: 1
      then: human_required
    stop_conditions: [A column name collides with an existing one, The seeded copy is unavailable]
    completion_evidence: [make migrate-test output, migration file hash]
    status: pending
  - unit_id: IU-STORE
    title: Revocation repository and audit write
    objective: Add revoke_token and is_revoked to the token store, writing one audit row per revocation and none on a repeat.
    acceptance:
      - revoke_token is idempotent, so a second call leaves exactly one audit row.
      - is_revoked reads committed state, not a cache populated at process start.
    requirement_ids: [R-REVOKE, R-AUDIT]
    acceptance_example_ids: [AE-REVOKED-TOKEN-FAILS, AE-DOUBLE-REVOKE, AE-AUDIT-SURVIVES-RESTART]
    rationale: The endpoint must not carry idempotency or audit logic that belongs with the data.
    dependencies: [IU-MIGRATION]
    input_artifacts: [migrations/002_token_revocation.sql]
    inspect_targets: [src/store/tokens.py, tests/test_token_store.py]
    read_scope: [src/store/tokens.py, src/store/models.py, migrations/002_token_revocation.sql]
    write_scope: [src/store/tokens.py, tests/test_token_store.py]
    forbidden_scope: [src/api/, migrations/]
    interfaces: [revoke_token, is_revoked]
    procedure:
      - Read the applied migration for the exact column and table names.
      - Implement revoke_token as an upsert so a retry cannot duplicate the audit row.
      - Implement is_revoked as a committed read.
    forward_proof: [pytest tests/test_token_store.py]
    regression_proof: [The existing token store suite still passes unchanged]
    commands: [pytest tests/test_token_store.py]
    output_artifacts: [src/store/tokens.py, tests/test_token_store.py]
    risk: medium
    complexity: medium
    failure_domain: storage
    capability_profile: {}
    primary_route: local
    fallback_route: local
    attempt_limit: 2
    escalation_conditions: [A second revoke produces a second audit row]
    manager_id: M-STORAGE
    review_contract:
      acceptance_ids: [AE-DOUBLE-REVOKE, AE-AUDIT-SURVIVES-RESTART]
      required_evidence: [test_output, scope_diff]
      scope_check: true
      test_check: true
    context_manifest:
      kernel_refs: ["project:test-command"]
      path_refs: [src/store/tokens.py, src/store/models.py]
      dependency_artifact_refs: [migrations/002_token_revocation.sql]
      max_bytes: 64000
      allow_context_request: true
    retry_policy:
      same_worker_attempts: 1
      fallback_worker_attempts: 1
      then: human_required
    stop_conditions: [The migration artifact is absent, The audit table shape differs from the plan]
    completion_evidence: [pytest output, scope diff]
    status: pending
  - unit_id: IU-SCHEMA
    title: Revocation request and response schema
    objective: Define the request and response bodies for the revoke endpoint, including the error shape for an unknown token.
    acceptance:
      - An unknown token id produces the documented 404 body, not a stack trace.
      - No schema field can carry a token secret.
    requirement_ids: [R-REVOKE]
    acceptance_example_ids: [AE-REVOKED-TOKEN-FAILS]
    rationale: The endpoint and its tests both bind to this shape, so it is settled before either is written.
    dependencies: []
    input_artifacts: [src/api/schema.py]
    inspect_targets: [src/api/schema.py]
    read_scope: [src/api/schema.py, docs/api.md]
    write_scope: [src/api/schema.py]
    forbidden_scope: [src/store/, migrations/]
    interfaces: [RevokeTokenResponse, TokenNotFoundError]
    procedure:
      - Match the existing error envelope in schema.py rather than inventing one.
      - Assert at the type level that no response field is the secret.
    forward_proof: [pytest tests/test_schema.py]
    regression_proof: [Existing schema tests pass unchanged]
    commands: [pytest tests/test_schema.py]
    output_artifacts: [src/api/schema.py]
    risk: low
    complexity: low
    failure_domain: api
    capability_profile: {}
    primary_route: local
    fallback_route: local
    attempt_limit: 2
    escalation_conditions: [The existing error envelope cannot express a 404 for this case]
    manager_id: M-API
    review_contract:
      acceptance_ids: [AE-REVOKED-TOKEN-FAILS]
      required_evidence: [test_output, scope_diff]
      scope_check: true
      test_check: true
    context_manifest:
      kernel_refs: ["project:test-command"]
      path_refs: [src/api/schema.py, docs/api.md]
      dependency_artifact_refs: []
      max_bytes: 32000
      allow_context_request: true
    stop_conditions: [The error envelope is ambiguous]
    retry_policy:
      same_worker_attempts: 1
      fallback_worker_attempts: 1
      then: human_required
    completion_evidence: [pytest output]
    status: pending
  - unit_id: IU-ENDPOINT
    title: Revoke endpoint
    objective: Add POST /tokens/{id}/revoke, authorized to operators, returning the schema response and calling the store.
    acceptance:
      - A revoked token returns 401 on its next authenticated request.
      - A non-operator caller receives 403 and no audit row is written.
    requirement_ids: [R-REVOKE]
    acceptance_example_ids: [AE-REVOKED-TOKEN-FAILS, AE-DOUBLE-REVOKE]
    rationale: The endpoint is the last layer, so it composes settled pieces instead of defining them.
    dependencies: [IU-STORE, IU-SCHEMA]
    input_artifacts: [src/store/tokens.py, src/api/schema.py]
    inspect_targets: [src/api/routes.py, tests/test_routes.py]
    read_scope: [src/api/routes.py, src/api/schema.py, src/store/tokens.py]
    write_scope: [src/api/routes.py, tests/test_routes.py]
    forbidden_scope: [src/store/, migrations/, src/api/schema.py]
    interfaces: ["POST /tokens/{id}/revoke"]
    procedure:
      - Bind the handler to the schema types from IU-SCHEMA without redefining them.
      - Call revoke_token and return its result, adding no idempotency logic here.
      - Cover the 401-on-next-request path end to end.
    forward_proof: [pytest tests/test_routes.py]
    regression_proof: [The full route suite passes, and no existing route changes status codes]
    commands: [pytest tests/test_routes.py, pytest]
    output_artifacts: [src/api/routes.py, tests/test_routes.py]
    risk: medium
    complexity: medium
    failure_domain: api
    capability_profile: {}
    primary_route: local
    fallback_route: local
    attempt_limit: 2
    escalation_conditions: [Authorization cannot distinguish an operator, The 401 arrives only after a cache expiry]
    manager_id: M-API
    review_contract:
      acceptance_ids: [AE-REVOKED-TOKEN-FAILS, AE-DOUBLE-REVOKE]
      required_evidence: [test_output, scope_diff, artifact_hash]
      scope_check: true
      test_check: true
    context_manifest:
      kernel_refs: ["project:test-command", "project:auth-model"]
      path_refs: [src/api/routes.py, src/api/schema.py]
      dependency_artifact_refs: [src/store/tokens.py, src/api/schema.py]
      max_bytes: 64000
      allow_context_request: true
    retry_policy:
      same_worker_attempts: 1
      fallback_worker_attempts: 1
      then: human_required
    stop_conditions: [A dependency artifact is missing, The auth model has no operator concept]
    completion_evidence: [pytest output, scope diff, route table hash]
    status: pending
---
## Goal Capsule

An operator can revoke one API token and have it stop working immediately, with a
durable record of who did it. This plan exists to be read, not run: it is the
worked example the README quickstart validates, snapshots, and compiles.

## Concept and Requirements

R-REVOKE is the feature. R-AUDIT is the reason it cannot be a cache flag. Both
are testable as written, which is the gate the concept phase enforces: "revocation
should be fast" would not have survived it, and "the revoked token stops
authenticating on the next request" did.

## Scope and Non-Goals

In scope: the migration, the store methods, the response schema, and the endpoint.
Not in scope: bulk revocation, an operator UI, key rotation, and any change to how
tokens are issued. Those are separate requirements and would need their own units.

## Acceptance and Invariants

The three acceptance examples pin behavior a reviewer can check: revoked tokens
fail on the next request, a repeated revoke stays at one audit row, and audit rows
survive a restart. I-NO-PLAINTEXT and I-SCOPE hold across every unit, which is why
each carries them rather than one unit owning them.

## Repository Grounding

Facts: tokens live in `api_tokens`, created by `migrations/001_initial.sql`; the
store is `src/store/tokens.py`; routes are `src/api/routes.py`; the error envelope
already exists in `src/api/schema.py`. Assumption, flagged rather than assumed
away: the auth model has an operator role. IU-ENDPOINT stops if it does not.

## Technical Research

One question was open: whether revocation could be a cache flag. It could not,
because R-AUDIT requires the record to survive a restart. No external research was
needed, and nothing here rests on an undocumented framework behavior.

## Technical Decisions

Revocation is a column plus an audit table, not a delete, so the record outlives
the token. `revoke_token` is an upsert, which makes idempotency a property of the
data rather than of the endpoint, so AE-DOUBLE-REVOKE cannot regress by way of a
retry. `is_revoked` reads committed state, because a process-start cache is exactly
the bug AE-REVOKED-TOKEN-FAILS is written to catch.

## System Impact

Two tables change and two modules gain methods. Every existing token keeps working
with `revoked_at` NULL. The blast radius is the auth path, which is why IU-MIGRATION
is high risk and double-rehearsed under the release gate.

## Canonical Implementation Units

Four units. IU-MIGRATION and IU-SCHEMA have no dependencies and may run in
parallel. IU-STORE waits on the migration. IU-ENDPOINT waits on both the store and
the schema. Write scopes do not overlap, so no two concurrent units touch a file.

## Delegation Graph

M-STORAGE reviews IU-MIGRATION and IU-STORE. M-API reviews IU-SCHEMA and
IU-ENDPOINT. Both managers are advisory and hold no write scope, so the graph is
Director over two managers over four workers: seven nodes, which is the
`max_total_nodes` bound.

`max_graph_depth` is a separate measurement and a common place to get the gate
wrong. It bounds the longest chain in the dependency DAG, not the depth of the
management tree. Here that chain is IU-MIGRATION into IU-STORE into IU-ENDPOINT,
so the bound is 3. A plan whose managers nest three levels deep but whose units
all run in parallel still has a dependency depth of 1.

## Routing Assignments

Every unit declares `local` as primary and fallback so the example compiles without
network evidence. Real routing replaces these through `route assign`, which refuses
to run on stale LLM Stats data. See `docs/plans/example-route-request.json`.

## Context Contract

No unit receives the repository. Each gets its own files, its dependency artifacts,
and its unit contract, bounded by `max_bytes`. IU-ENDPOINT gets the store and schema
it calls, not the migration underneath them, because it never touches the database
directly.

## Verification Contract

Each unit names the command that proves it forward and the one that proves it broke
nothing. IU-ENDPOINT runs the full suite because it is the last unit to land and the
one that can break an unrelated route.

## Failure and Recovery Contract

Every retry policy ends in `human_required`, so no branch retries forever. A failed
IU-MIGRATION blocks IU-STORE and IU-ENDPOINT as its transitive dependents, and
leaves IU-SCHEMA running, which is the failure isolation the graph is compiled for.
Rollback is the migration down path plus a file revert.

## Definition of Done

All four units completed by a passing manager review, both invariants held, the
three acceptance examples demonstrated, and the release gate satisfied with zero
open P0 or P1 defects and zero unsafe write overlaps.

## Sources and Evidence

`migrations/001_initial.sql` for the current schema, `src/api/schema.py` for the
error envelope, and the existing store and route suites for the regression
baseline. No external sources were required.
