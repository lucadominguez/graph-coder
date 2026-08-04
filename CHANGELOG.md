# Changelog

All notable changes to Graph Coder. This project follows semantic versioning once
it reaches 1.0; until then, minor versions may change contracts.

## [Unreleased]

### Fixed

- **Units had no output gate, so an empty result passed review.** A scraper unit
  was "scrape and submit report", with nothing saying the output needed the right
  fields or any rows at all: the code ran, the file existed, no criterion was
  violated, and the Director had to invent a check on the spot. Units now carry a
  required `output_contract` of checkable assertions about the artifact's contents.
  A plan whose units lack one is not implementation-ready and cannot reach
  approval. The worker is told the contract before it starts, and the manager
  review checks the artifact's contents rather than its existence.
- **Nothing in the plan said what progress should look like.** Over a long
  iterative job, an agent 900 items in and an agent wedged in a dead loop produce
  the same observation, which is nothing new on disk. Units now carry a required
  `progress_contract`: `checkpoint_every` in the unit's own terms, whether output
  accumulates incrementally, and `command_timeout_seconds`. The packet's progress
  instructions are generated from it, so a single-pass unit and a per-page unit get
  opposite instructions instead of one generic rule, and the Director's stall math
  reads the same field rather than timing every unit identically.
- **Report-to-manager assumed a worker that can still respond.** A worker inside a
  long blocking call cannot answer a message, cannot report, and cannot be told
  apart from a hung one, so the whole review pattern silently stops working.
  `command_timeout_seconds` is now required and non-optional per unit, the packet
  instructs the worker to bound its own long commands or split them into reporting
  batches, and plan-forge requires long work to be batched with a checkpoint
  between rather than run as one command that either returns or does not.
- **`manager_id` was checked with `(unit.manager_id,)`.** A one-tuple is always
  truthy, so the check could not fail and a unit with no manager passed readiness
  and reached execution with nobody assigned to review it. Found while adding the
  checks above.

- **The preflight named a problem it gave you no way to fix.** `jcode emit` would
  report that MODEL_ROUTING was skipped and then offer nothing to act on. A run had
  to hand-edit `graph.json`, could not, because all four nodes carry the identical
  line `"model": "local"` and a text edit cannot target one of four identical
  occurrences, and wrote a throwaway script instead. `graph-coder route set` now
  writes routes onto nodes: with `--node` it sets exactly those, without it fills
  every node still holding a placeholder. It records `route_evidence` per node and
  returns a `degraded` notice when the basis is not LLM Stats, so a harness-list
  choice is never later mistaken for a router decision.
- **The fallback route was compiled and then dropped.** `fallback_route` sat in node
  metadata and never reached the emitted task, so retrying on the fallback meant
  re-deriving the model by hand mid-run. Tasks now carry `fallback_model` beside
  `model`, and a placeholder is withheld rather than offered as a fallback.
- **`swarm cleanup --force` was recommended as a routine preflight, and it is
  global.** A run followed that advice and stopped every worker on the machine,
  including agents belonging to unrelated projects. That instruction was added here
  and is now withdrawn: inspect with `swarm list`, remove stale nodes by id, and
  treat the global cleanup as a last resort only after confirming no unrelated
  agent is running. When the removal cannot be scoped, dispatch per node with
  `swarm spawn`, which needs no clean plan registry.
- **Stall detection had no threshold and no exit.** `heartbeat_seconds` was a
  declared bound that nothing enforced, and "never respawn a live worker" gave no
  criteria for when to stop waiting, so a run sat on a stuck worker for over two
  minutes. Dispatch now carries a table keyed on time since the last observed
  change, separating a worker that is alive but unproductive (tokens growing, no
  files) from one that is frozen, and crossing `heartbeat_seconds` ends the wait:
  count the attempt, take the fallback, escalate. The no-respawn rule protects a
  working worker, not a hung one.
- **A running worker's transcript cannot be read at all**, since
  `swarm read_context` returns busy and `session_search` returns metadata only.
  Worker packets now carry a progress protocol requiring a per-node log line at
  each step and early creation of output files, so the filesystem shows the
  progress the transcript will not. Watchers are now one per round rather than one
  per node, because overlapping `await_members` calls resolve on top of each other
  and bury the event that mattered.

- **Execution now tells the Director to spawn, in so many words.** A real run
  reached `DIRECTED_EXECUTION` and the root session implemented the plan itself
  instead of dispatching workers. Nothing in the skills was wrong, and nothing in
  them said "spawn a subagent" either: phase 10 described dispatch as a state
  machine, and `graph-coder jcode emit` was listed under Commands without ever
  appearing in the lifecycle that consumes it. Phase 10 now opens with the
  mandate, names self-implementation as a failed run rather than a shortcut, and
  walks the round: read the frontier, emit the packets, spawn one subagent per
  ready node in parallel, hold `max_active_workers`, record the dispatch events.

- **An auth failure read as a permission wall, and routing was abandoned.** The
  client raised a bare `LLM Stats request failed with HTTP 401`, discarding the
  response body that says `Invalid API key. Create or manage your keys at ...`.
  A run read the code as "no access", fell back to `swarm list_models`, and
  hand-picked a model with no receipt. The error now quotes the API's own message
  and, for `401` and `403`, states that the key is invalid, expired, or lacks
  access rather than missing, and where to regenerate it.
- **The client timed out before that message could arrive.** Measured on
  2026-08-03, this API takes about 24 seconds to return an auth failure, against a
  10-second default timeout, so a bad key surfaced as a generic timeout. The
  default is now 45 seconds; success paths are fast, and the budget exists for the
  error path.
- **Liveness and completion were the same signal, and neither covered the gap.**
  The previous release said to verify completion from the filesystem rather than
  waiting on a swarm report, which is right about completion and wrong as the only
  poll. A worker blocked on a `429` writes nothing, exactly like a worker that is
  thinking. One run watched a directory for two minutes while its worker sat rate
  limited. Dispatch now separates the two questions: the filesystem answers "is it
  done", `swarm status` answers "is it alive", and both are polled every cycle.
  Rate limits are classed as transient infrastructure, with the standing rule that
  a node whose worker is still alive is never respawned, because two workers in one
  write scope is the write conflict the graph exists to prevent.
- **Workers spawned invisibly.** `graph compile` hardcoded `spawn_mode="headless"`
  and the JCode adapter never emitted the field at all, so it was dead in the
  bundle and the harness picked its own default. Headless and inline workers do
  the work and never appear in `swarm list`, which leaves the Director unable to
  see a worker start, stall, or finish and makes the status roster it is required
  to keep fiction. The compiler now defaults to `visible` and the adapter emits it
  on every task.
- **`MODEL_ROUTING` was skippable in practice, and got skipped.** A run reached
  execution with `primary_route: local` on every unit, so `route refresh` and
  `route assign` never ran and the workers took whatever default model the harness
  supplied, unrouted and unmetered, while the approved plan's cost estimate
  described a run that did not happen. `local` is the placeholder that lets the
  shipped example plan compile without network evidence, and copying that example
  is how it spreads. Phase 8 now states it is not optional, its gate refuses a
  graph still holding a placeholder, and `docs/plans/example-plan.md` says in the
  file itself that `local` must never reach execution.

### Added

- **A declared degraded-routing path** in `routing-plan`, for when LLM Stats is
  genuinely unreachable and no policy-valid cache exists. Routing from the
  harness's own model list is legitimate; doing it silently is not. The path
  requires `routing_evidence: harness_model_list`, no benchmark scores, selection
  on hard filters and price alone, the full candidate list, and an explicit
  degradation notice at full-plan approval, because the user is otherwise
  approving a cost estimate built on weaker evidence than the plan format implies.
- **`jcode emit` returns a `preflight` block**: `ready_to_dispatch`, the unrouted
  nodes, the nodes that would spawn invisibly, and a warning naming the fix for
  each. It reports rather than raises, because the unrouted example plan must
  still emit for the quickstart, and the skill tells the Director to stop unless
  `ready_to_dispatch` is true. This is the machine-checkable version of two rules
  that prose alone did not hold.
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
- Field-tested dispatch guidance, all of it from one real run. `swarm cleanup
  --force` before emitting, because plan nodes left by an earlier session merge
  into yours and turned a 3-node graph into 55. The literal `swarm spawn --label
  ... --spawn_mode visible` call, because "spawn one subagent per ready node" left
  the actual tool call to be guessed. `run_plan` documented as the brittle batch
  path with per-node spawns as the stated fallback, after it failed on both stale
  plans and `Only the coordinator can assign tasks.` Completion verified from the
  filesystem and the unit's verification commands rather than by waiting on a
  swarm report, since a worker that never joined the swarm still did its work.
  Spawn width taken from the dependency DAG in both directions: parallel where
  nodes are independent, and one at a time down a chain like
  `IU-STORE -> IU-BACKEND -> IU-FRONTEND`, where spawning all three at once hands
  the later workers a repository that lacks what their packets told them to build
  on.

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
