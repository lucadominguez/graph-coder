# Architecture

Graph Coder is two things: a skill suite that carries the rules, and a small
Python layer that makes artifacts durable and routing deterministic. The split is
deliberate. Instructions cover the judgment; code covers the invariants a model
should not be trusted to hold under pressure.

## Layers

```text
skills/                        instructions the agent reads
  graph-coder                  the /graph-coder orchestrator
  concept-grill                third-party brainstorming controller
  technical-research           question router, evidence normalizer
  plan-forge                   canonical plan authoring
  plan-rehearsal               cold executability trials
  delegation-graph             manager and worker compilation
  routing-plan                 role profiling
  execution-manager            manager advice and review

src/graph_coder/               the control layer
  plans.py       canonical plan, semantic hash, approval binding
  graph.py       node model, authority, review ownership, validation
  execution.py   states, manager verdicts, failure isolation
  routing.py     hard filters, expected passing cost, receipts
  db.py          SQLite schema and transactions
  events.py      hash-linked append-only ledger
  recovery.py    replay, ready frontier, human-required resume
  context.py     repository status for the project kernel
  contracts.py   JSON Schema validation by contract and type
  cli.py         the graph-coder command
  adapters/jcode.py  public swarm task_graph and run_plan bundles
```

Ownership, unchanged from the APS split it inherits: the root JCode session is the
Director and owns intent, approval, the canonical plan, and coordinator-gated
graph mutations. Skills conduct concept grilling, research, planning, rehearsal,
compilation, routing, and execution management. Python owns persisted state,
schemas, hashes, snapshots, deterministic route selection, graph validation, and
recovery. JCode owns worker execution.

## Execution hierarchy

```text
Frontier Director (main JCode terminal, advisory_only)
│  full project access through kernel, indexes, deltas, on-demand retrieval
│  directs, routes, advises, reviews top-level branch outputs
│  write scope for application code: none
│
├─ Manager A (manage, composite, advisory_only, write scope [])
│  ├─ Worker A1 (implement, review_owner = Manager A)
│  ├─ Worker A2 (implement, review_owner = Manager A)
│  └─ Repair Worker A3 (created only when Manager A rejects a result)
│
└─ Manager B (manage, composite, advisory_only, write scope [])
   ├─ Worker B1
   └─ Worker B2

review path:      Worker -> its Manager -> pass | repair_required | human_required
advice path:      Worker -> Manager -> higher Manager -> Director
context path:     Worker -> Manager -> Director or context store -> minimal patch
failure boundary: failed node plus transitive dependents pause; siblings continue
```

Managers replace what APS modelled as reviewer nodes. The difference is
structural, not cosmetic: a review is a state transition and an artifact, so it
never appears in the DAG, never consumes a dispatch slot, and never acquires a
write scope.

Advice, context requests, and escalations are control-plane events rather than
dependency edges. That is what keeps the implementation DAG acyclic however much a
branch negotiates.

## State machine

```text
pending -> ready -> running -> awaiting_review -> completed
                                     |
                                     +-> repair_required -> running
                                     |
                                     +-> human_required -> ready (after a decision)

blocked, failed, and cancelled are reachable from the states that produce them.
```

Enforced in `execution.py`:

- `running -> completed` does not exist. A worker cannot complete itself.
- The only exits from `awaiting_review` are the three manager verdicts.
- `DEPENDENCY_SATISFYING_STATES` is exactly `{completed}`. `done` is not accepted;
  it was the APS spelling for a self-declared finish.
- `repair_required` requires a bounded defect and a repair instruction.
- `human_required` requires the question, the attempts made, and the impacted nodes.
- `block_descendants` walks dependents only, so isolation is structural rather
  than a matter of remembering to check.

## Durability

Every phase transition is an event before the next phase reads state.

- SQLite holds projects, runs, plan versions, requirements, units, graph nodes and
  edges, routes, agents, tasks, attempts, artifacts, reviews, decisions,
  escalations, model history, and projections. WAL mode, foreign keys, explicit
  migrations, short transactions, and a busy timeout.
- The event ledger is append-only and hash-linked: each row hashes its canonical
  content plus the previous hash, so `verify_chain` detects tampering, reordering,
  and gaps.
- Plan snapshots are written atomically to `.graph-coder/snapshots/<plan>/vN.json`.
- Recovery marks in-flight attempts interrupted, reopens completed units with no
  evidence, verifies the chain, rebuilds projections, and recomputes the frontier.
- `run resume` records a human decision in the node's durable record and appends
  `branch.resumed`, preserving the prior failure evidence rather than erasing it.

Authoritative state lives in `.graph-coder/state.db`. Projections, snapshots,
caches, context packets, and artifacts are derived from it or from
content-addressed source files.

Semantic hashing separates substance from presentation. The plan's semantic hash
covers objectives, acceptance, dependencies, interfaces, scopes, commands,
expected artifacts, manager and review contracts, context manifests, and routing
constraints, and excludes titles, rationale, and formatting. An editorial pass
does not invalidate an approval; a changed write scope does.

Approval is bound to four hashes: plan, graph, route, and render. Any of them
moving voids it.

## Routing

Deterministic by construction: the same registry and unit always produce the same
route, and the receipt explains why.

```text
hard filters (auth, context, output, tools, modalities, streaming, class,
              policies, environment, cost ceiling, confidence, freshness,
              provider and model allow and deny rules)
  -> external = weighted mean of per-category normalized benchmark scores
  -> quality = (0.60 * external + 0.30 * local) / 0.90
  -> quality floor
  -> subscription-first precedence
       direct subscription > other zero-marginal-cost > reseller
       reseller duplicates of eligible direct routes are eliminated
  -> quality, cost, reliability, latency Pareto frontier
  -> retain within the configured quality margin
  -> open-weight preference, when enabled
  -> lowest expected passing cost
  -> tie-breakers: confidence, reliability, latency, model id
```

```text
expected_passing_cost = attempt_cost
                      + probability_of_repair     * repair_cost
                      + probability_of_escalation * escalation_cost
```

The repair and escalation terms use configured estimates and default to zero, so
an unconfigured registry never implies precision it does not have.

### Benchmark normalization

`top_scores` categories do not share a scale. On live data `code` and
`tool_calling` arrive in 0..1 while `reasoning` sits near 150 and `finance` near
900. The external score is a weighted mean bounded to 0..1, so raw values pinned
every model weighted on a large-scale category to exactly 1.0. Quality stopped
discriminating, the Pareto frontier collapsed, and the tie-breakers picked the
cheapest candidate while the receipt reported a perfect score. Cheap is often
right, but arriving there by accident is not routing.

Scores are therefore min-max normalized per category, against the field the
router may actually choose from, before they reach `route_model`. Normalization
lives in `registry.py` so `route_model` stays a pure function over prepared
inputs. Three properties keep it honest:

- The bounds used are recorded per category in the build report, so a route is
  reproducible and a human can see what a score was measured against.
- A category fewer than two models report, or where every model scored the same,
  ranks nothing and yields a neutral 0.5 rather than a 0.0 that would read as a
  bad result.
- A category whose own values span more than 50x is flagged as carrying mixed
  units. `reasoning` spans 0.6 to 419.1 on real data, which no single benchmark
  produces, so a low scorer there is likely measured on a different benchmark
  rather than being hundreds of times worse.

A weighted category a model does not report still contributes its full weight to
the denominator and nothing to the numerator, so absent evidence scores like a
poor result. That is the conservative reading and it is deliberate, but the
receipt now carries `benchmark_coverage` and `unscored_benchmark_weights` so a
candidate losing on missing benchmarks is distinguishable from one losing on bad
ones.

Role categories replace per-unit routing alone. The Director is pinned to its
configured frontier model and receives no automatic fallback: a pinned route that
fails its hard requirements is reported as a refusal, never swapped for something
cheaper. There is no reviewer route category, because there are no standalone
reviewers.

Subscription-first used to live only in a validator script beside the skill, which
meant the engine did not enforce it. It is now precedence inside the router, and
APS's original validator cases are parametrized tests driving the real router.

## Cost model

Repeated context often dominates raw token counts, but output and reasoning tokens
are priced far above input, and cached input far below. The optimization order is
therefore:

1. failed and repeated implementation attempts;
2. unnecessary model elevation;
3. excessive frontier output;
4. repeated uncached context.

This is why the escalation ladder is bounded and why routing scores expected
passing cost. Context delivery follows the same logic: a stable cached prefix, a
per-turn delta, and on-demand retrieval. Writing context to a file saves nothing
if the harness reinserts the whole file every turn.

## JCode boundary

The adapter emits public swarm operation bundles and depends on no private socket
or protocol.

- `task_graph` carries the dispatchable nodes, which is everything except the
  Director and the managers.
- Metadata carries the manager roster with its advisory authority, empty write
  scopes, and the nodes each manager reviews, plus `review_assignments`.
- Every worker prompt names its manager and states that only the manager's passing
  review completes the node.
- The Director prompt states that it never edits implementation files.
- `native_kind(MANAGE)` raises rather than disguising a manager as a worker.

The bundle is a spawn list, not a description of one. Every entry in
`task_graph.arguments.nodes` is meant to become its own subagent, prompted with
that entry's `content` verbatim; JCode drives them through the public `swarm` tool
and any other harness makes one subagent call per entry. A root session that reads
the bundle and then writes the code itself has produced a diff with none of the
isolation, review, or cost properties the plan was approved on, so the skills name
that outcome as a failed run rather than leaving it implied. The recipe and its
self-check live in `skills/graph-coder/references/dispatch.md`.

Version detection reads `jcode --version` and compares against the v0.55.0 target.
`/graph-coder` is the orchestration command because JCode dispatches built-ins
before skill lookup, so `/plan` cannot be safely overridden.

## Upstream boundary

APS is a fetch-only reference. `origin` is `lucadominguez/graph-coder`;
`aps-reference` has its push URL disabled. The pinned commit lives in
`upstream/aps.lock.json`, the file map in `docs/upstream-provenance.md`, and the
upstream MIT notice in `NOTICE`. `scripts/check_aps_upstream.py` reports drift and
takes no action.
