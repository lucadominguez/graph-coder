# Changelog

All notable changes to Graph Coder. This project follows semantic versioning once
it reaches 1.0; until then, minor versions may change contracts.

## [Unreleased]

### Fixed

- **Execution now tells the Director to spawn, in so many words.** A real run
  reached `DIRECTED_EXECUTION` and the root session implemented the plan itself
  instead of dispatching workers. Nothing in the skills was wrong, and nothing in
  them said "spawn a subagent" either: phase 10 described dispatch as a state
  machine, and `graph-coder jcode emit` was listed under Commands without ever
  appearing in the lifecycle that consumes it. Phase 10 now opens with the
  mandate, names self-implementation as a failed run rather than a shortcut, and
  walks the round: read the frontier, emit the packets, spawn one subagent per
  ready node in parallel, hold `max_active_workers`, record the dispatch events.

### Added

- **`skills/graph-coder/references/dispatch.md`**: the mechanism behind that
  mandate. The shape of the emitted `task_graph` bundle, the instruction to pass
  each node's `content` verbatim, the JCode `swarm` path and the one-call-per-node
  path for every other harness, the refusal to run at all when a harness exposes
  no subagent tool, and a five-item self-check that fails a run which produced
  code without spawns.
- Phase-gate entry and exit conditions for `DIRECTED_EXECUTION` covering spawn
  capability, one spawn per dispatchable node, and no root-session writes, plus a
  `ready -> running` gate that a node reaches only once a subagent holds it.
- `execution-manager` now states that repairs are spawns too, and that a control
  plane with no subagent tool stops rather than falling back to the foreground.

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
- **`registry.py`**: live LLM Stats records become router inputs, one route per
  `(model, provider)` pair, so subscription-first has comparable candidates.
  `route assign|explain --from-cache` refuses stale or expired evidence and names
  `route refresh` as the fix.
- **`docs/schematic.md`**: a text-art schematic of the whole system, from the
  skill/code split through the lifecycle, hierarchy, state machine, routing, and
  durability.
- **`docs/plans/example-plan.md`**: a complete worked plan, four units under two
  advisory managers with one dependency chain, that the README quickstart runs
  against. A test validates and compiles it, so the quickstart cannot rot into
  pointing at a file that does not exist.
- **`docs/plans/example-route-request.json`**: a working routing request for the
  example plan's endpoint unit.

### Changed

- Package `agent_planning_system` is now `graph_coder`; the CLI `aps` is now
  `graph-coder`; the state directory `.agent-planning` is now `.graph-coder`.
- Native artifacts declare `graph-coder/v1`, not `agent-planning-system/v1`. The
  rebrand had reached the package, the CLI, and the state directory but not the
  artifact contract, so a compiled graph still announced itself as APS. The frozen
  copies under `schemas/import/aps-v1/` are unchanged and still validate genuine
  APS artifacts, which no native reader accepts.
- Every CLI failure is JSON with exit 2. `KeyError` and `TypeError` escaped as
  tracebacks with exit 1, which was reachable from any hand-authored
  `route assign --input` payload with a missing or misspelled field.
- Benchmark scores are min-max normalized per category against the routable field
  before the router sees them. LLM Stats categories do not share a scale, so the
  bounded weighted mean pinned every model weighted on a large-scale category to
  exactly 1.0: quality stopped discriminating and the tie-breakers silently chose
  the cheapest candidate while the receipt reported a perfect score. The bounds
  used are recorded per category, a category that ranks nothing yields a neutral
  0.5 instead of a 0.0 that would read as a bad result, and a category spanning
  more than 50x is flagged as carrying mixed units.
- Route receipts carry `benchmark_coverage` and `unscored_benchmark_weights`. A
  weighted category a model does not report still scores zero, which is the
  conservative reading, but it is no longer indistinguishable from a bad score.
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
- The LLM Stats base URL is ZeroEval's `https://api.zeroeval.com/stats/v1`. The
  inherited `https://llm-stats.com/api/v1` 404s and was never live. The response
  is `{models, next_cursor, total}` paginated by opaque cursor, not `{data, next}`,
  and the client sends a conventional User-Agent because Cloudflare rejects
  urllib's default with error 1010.
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
- The LLM Stats API reports no context window for any model, so a unit that
  declares `min_context_tokens` eliminates every route unless
  `context_window_overrides` supplies the numbers. The build counts and warns
  rather than inventing them.
- Per-attempt cost is derived from published per-million prices and assumed token
  counts. The assumptions are inputs and are labelled estimates in the receipt.
