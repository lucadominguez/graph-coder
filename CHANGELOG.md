# Changelog

All notable changes to Graph Coder. This project follows semantic versioning once
it reaches 1.0; until then, minor versions may change contracts.

## [0.1.0] - 2026-07-30

First release. Graph Coder is an independent repository seeded from the Agent
Planning System at `f4c28164062432140d7f7620ffdac56ce0a442c5`, with public
identities renamed and provenance recorded before any behavior changed.

### Added

- **`/graph-coder` orchestrator skill** with a 10-phase lifecycle, the
  Director/manager/worker authority table, the context contract, the cost model,
  the bounded escalation ladder, and full-plan approval. Reference docs cover the
  artifact map, phase gates, and third-party dependencies.
- **`concept-grill`**: a controller for an installed third-party brainstorming
  skill that normalizes its output into the canonical plan. No Product Contract
  phase or document.
- **`technical-research`**: a question router and evidence normalizer with a source
  hierarchy, claim schema, and explicit stop conditions.
- **`execution.py`**: ten execution states and a transition table where the only
  exit from `awaiting_review` is a manager verdict, plus `block_descendants` and
  `compute_frontier` for branch-local failure isolation.
- **Role-aware routing**: `director`, `manager`, `worker`, `research`, and
  `rehearsal` categories. The Director is pinned to its configured frontier model
  and never silently downgraded.
- **Subscription-first precedence inside the router**, previously only in a
  detached validator script. APS's validator cases are now parametrized tests
  driving the real router.
- **Route receipts** (`graph-coder/route_receipt/v1`) on every assignment,
  including refusals.
- **Approval binding** to plan, graph, route, and render hashes, with
  `rendered_full_plan` required.
- **`graph-coder run resume`** to record a human decision on a `human_required`
  branch without erasing the failure evidence.
- **Upstream awareness**: `upstream/aps.lock.json`, `docs/upstream-provenance.md`,
  `NOTICE` with APS's MIT notice, `scripts/check_aps_upstream.py`, and a weekly
  read-only workflow that reports drift and imports nothing.
- **`docs/importing-from-aps.md`** documenting the by-hand path, since no
  automatic importer ships.

### Changed

- Package `agent_planning_system` is now `graph_coder`; the CLI `aps` is now
  `graph-coder`; the state directory `.agent-planning` is now `.graph-coder`.
- The canonical plan has 16 sections. The unit contract replaces `reviewer` with
  `manager_id` and adds `review_contract`, `context_manifest`, `retry_policy`, and
  `failure_domain`.
- The semantic hash covers the full execution contract and excludes prose, so an
  editorial pass no longer invalidates an approval.
- `plan-forge` replaces the risk-triggered specialist reviewer swarm with an author
  self-audit. `plan-rehearsal` is an executability trial using the exact future
  worker packet. `delegation-graph` compiles advisory managers over implementing
  workers. `execution-manager` advises and reviews and may never implement.
- `graph compile` emits one advisory manager per declared `manager_id` and sets
  each worker's `review_owner`.
- The ready frontier no longer accepts `done` as satisfying a dependency.
- Native schemas moved to `schemas/v1/`; byte-for-byte APS copies are frozen under
  `schemas/import/aps-v1/`.
- Installers deliver eight skills.

### Removed

- `NodeKind.REVIEW`. Review is a manager verdict and an artifact, so no durable
  graph can record a reviewer node. `NodeKind("review")` raises.
- The `aps-plan` and `idea-grill` skills.
- The `PRODUCT_CONTRACT`, `REVIEW_GRAPH`, `FINAL_SIMULATION`, and
  `CONSOLIDATED_APPROVAL` phases.

### Known limitations

- Live behavioral evaluation has not been run. Rules that live in skill prose are
  instructions, not guarantees; only the mechanically enforced list in the README
  is verified by tests.
- The JCode adapter was written against the documented public swarm interface and
  has not been verified against a running JCode.
- The LLM Stats endpoint mapping remains provisional until an authenticated live
  fetch is recorded.
