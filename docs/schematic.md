# Graph Coder schematic

How the whole system fits together, from a rough request to reviewed code.

## 1. The two layers

```text
                          YOU, in the root JCode session
                                      │
                                 /graph-coder
                                      │
                                      v
   ┌──────────────────────────────────────────────────────────────────────┐
   │  SKILLS  ── instructions the agent reads (the judgment)              │
   │                                                                      │
   │   graph-coder ......... orchestrator: 10 phases, authority, gates    │
   │   concept-grill ....... controls a third-party brainstorming skill   │
   │   technical-research .. question router + evidence normalizer        │
   │   plan-forge .......... authors the one canonical plan               │
   │   plan-rehearsal ...... cold executability trials                    │
   │   delegation-graph .... compiles managers over workers               │
   │   routing-plan ........ profiles roles, demands fresh evidence       │
   │   execution-manager ... advises + reviews, never implements          │
   └──────────────────────────────┬───────────────────────────────────────┘
                                  │  calls
                                  v
   ┌──────────────────────────────────────────────────────────────────────┐
   │  CODE  ── src/graph_coder (the invariants)                           │
   │                                                                      │
   │   plans.py ...... 16 sections, semantic hash, approval binding       │
   │   graph.py ...... node model, authority, review_owner, validation    │
   │   execution.py .. states, manager verdicts, failure isolation        │
   │   registry.py ... LLM Stats records -> router inputs, freshness      │
   │   routing.py .... hard filters, expected passing cost, receipts      │
   │   llm_stats.py .. the ZeroEval Stats API client + cache              │
   │   db.py ......... SQLite schema                                      │
   │   events.py ..... hash-linked append-only ledger                     │
   │   recovery.py ... replay, ready frontier, human-required resume      │
   │   adapters/jcode  public swarm task_graph / run_plan bundles         │
   └──────────────────────────────┬───────────────────────────────────────┘
                                  │  emits bundles
                                  v
                     JCode swarm  (owns worker execution)
```

The split is the point. Skills hold what needs judgment. Code holds what a model
should not be trusted to hold under pressure.

## 2. The lifecycle

```text
  PHASE                        PRODUCES                    GATE TO LEAVE
  ─────────────────────────────────────────────────────────────────────────────
   1 INTAKE_AND_CONTEXT        project kernel              mode decided,
     mode | resume | recover   change delta                ledger verified
        │
        v
   2 REPOSITORY_GROUNDING      facts vs assumptions        baseline failures
     read the code it touches  baseline command results    recorded
        │
        v
   3 CONCEPT_GRILL ───────────> ce-brainstorm (3rd party)  every requirement
     preflight first           plan §2 Concept & Reqs      is testable
        │                      plan §3 Scope & Non-Goals
        │  [dependency missing -> STOP with install message]
        v
   4 TECHNICAL_RESEARCH        question inventory          every question
     questions, THEN agents    research_claim[]            answered or marked
        │                      plan §6, §16                unresolved
        │
        │   RQ shape ──> capability
        │   repo?     ──> repo-research-analyst
        │   version?  ──> framework-docs-researcher
        │   approach? ──> best-practices-researcher
        │   outside?  ──> web-researcher
        v
   5 PLAN_AUTHORING            canonical plan, 16 sections  all units carry the
     one file, grows only      unit contracts               full contract;
        │                      author self-audit            self-audit passes
        v
   6 COLD_REHEARSAL            rehearsal_report[]           every unit
     fresh agent per unit,     plan mutations               executable from
     exact future packet,      (high risk: 2 passes)        its packet alone
     no edits allowed
        │  findings ──> back to 5, affected units rerun
        v
   7 GRAPH_COMPILATION         delegation graph             invariants hold
     managers over workers     manager assignments          (see §4)
        │
        v
   8 MODEL_ROUTING             route_assignment[]           every node routed,
     Director pinned           route_receipt[]              every route has a
        │                                                   receipt
        v
   9 FULL_PLAN_APPROVAL        approval bound to 4 hashes   the WHOLE plan was
     render everything                                      rendered
        │
        │  [summary offered instead -> STOP]
        v
  10 DIRECTED_EXECUTION        worker_report[]              all completed via
     dispatch, review, isolate manager_review[]             manager review, or
                               manager_advice[]             human_required with
                                                            evidence
```

Plan growth is monotonic. Later phases add specificity; nothing is dropped for
presentation. Information leaves only when proven wrong, duplicated, or rejected
by you.

## 3. Execution hierarchy and the three paths

```text
              ┌──────────────────────────────────────────┐
              │  FRONTIER DIRECTOR   (root JCode)        │
              │  authority: advisory_only                │
              │  app-code write scope: NONE              │
              │  full project access via kernel/deltas   │
              └───────────────┬──────────────────────────┘
                              │
        ┌─────────────────────┴─────────────────────┐
        v                                           v
┌───────────────────────────┐            ┌───────────────────────────┐
│ MANAGER A                 │            │ MANAGER B                 │
│ kind=manage composite     │            │ kind=manage composite     │
│ authority: advisory_only  │            │ authority: advisory_only  │
│ write_scopes: []          │            │ write_scopes: []          │
│ reviews its subtree only  │            │ reviews its subtree only  │
└──────┬─────────────┬──────┘            └──────┬─────────────┬──────┘
       v             v                          v             v
  ┌─────────┐  ┌─────────┐               ┌─────────┐   ┌─────────┐
  │WORKER A1│  │WORKER A2│               │WORKER B1│   │WORKER B2│
  │implement│  │implement│               │implement│   │implement│
  │writes:  │  │writes:  │               │writes:  │   │writes:  │
  │ src/a.py│  │ src/b.py│               │ src/c.py│   │ src/d.py│
  └─────────┘  └─────────┘               └─────────┘   └─────────┘

  REVIEW    Worker ──report──> its Manager ──> pass | repair_required
                                                    | human_required

  ADVICE    Worker ──> Manager ──> higher Manager ──> Director
            (advice never contains a patch, diff, or replacement code)

  CONTEXT   Worker ──request──> Manager ──> Director / store
                    <──minimal patch, scope-enforced, byte-bounded──

  All three are CONTROL-PLANE EVENTS, not dependency edges.
  The implementation DAG stays acyclic no matter how much a branch negotiates.
```

Why no reviewers under workers: a manager already has the branch context and the
authority to reject. Adding a reviewer doubles the agent count to re-derive what
the manager already knows.

## 4. What the graph refuses to compile

```text
   NodeKind:  manage | explore | spike | implement | verify | integrate
              | repair | release          <-- no `review`, ever
                                              NodeKind("review") raises

   ✗ manage node that is not composite
   ✗ manage node whose authority != advisory_only
   ✗ manage node with ANY write scope
   ✗ advisory_only node with ANY write scope
   ✗ node whose review_owner is itself
   ✗ review_owner that is not a manager or the root
   ✗ dependency or artifact cycle
   ✗ two concurrent nodes with overlapping write scopes
   ✗ a `verify` node that only reads and opines (a reviewer in disguise)
```

## 5. The state machine

```text
   pending ──> ready ──> running ──> awaiting_review ─┬─> completed
                 ^          │                          │      │
                 │          │                          │      └─ dependents
                 │          │                          │         become eligible
                 │          │                          │
                 │          │                          ├─> repair_required
                 │          └────────────────────────────────────┘  (a WORKER
                 │                                     │             repairs it,
                 │                                     │             never the
                 │                                     │             manager)
                 │                                     │
                 └─────────────────────────────────────┴─> human_required
                        (after a recorded human decision)

   ✗ running ──> completed        does not exist. A worker cannot complete
                                  itself. Only a manager verdict leaves
                                  awaiting_review.

   A dependency is satisfied ONLY in `completed`.
   `done` is not accepted: that was the APS spelling for a self-declared finish.
```

### Failure isolation

```text
                  A1 human_required
                        │
              block_descendants(A1) = {A2}      <- transitive dependents ONLY
                        │
        ┌───────────────┴───────────────┐
        v                               v
   A2 blocked                     B1, B2 keep running
                                  (independent branch, untouched)

   frontier: ready=[B1]  blocked=[A2]  human_required=[A1]
```

The escalation ladder is bounded and ends with a person:

```text
   worker attempt
     -> manager advice
     -> same-worker repair attempt
     -> fallback-worker repair attempt
     -> higher-manager or Director advice
     -> human_required   ──> HUMAN-REQUIRED PACKET
                              blocked node, objective, model route,
                              attempts made, advice given, exact blocker,
                              evidence, paused descendants,
                              work still running, options, decision needed
                              │
                              v
                    graph-coder run resume --node-id --decision
                    (records the decision, PRESERVES the failure evidence)
```

A unit's `retry_policy` may shorten the ladder. Nothing may make it unbounded.

## 6. Routing, from live data to a receipt

```text
   https://api.zeroeval.com/stats/v1/models          335 models
   Authorization: Bearer $LLM_STATS_API_KEY          (env only, never stored)
   User-Agent: conventional                          (Cloudflare 1010 otherwise)
        │
        │  graph-coder route refresh
        v
   .graph-coder/cache/llm-stats/models.json
   labelled: network | cache | stale_cache
        │
        │  --from-cache   ┌─────────────────────────────────────────┐
        v                 │ FRESHNESS GATE                          │
   registry.py ───────────│ stale flag?        -> REFUSE            │
   build_registry()       │ age > max-age-hours -> REFUSE           │
        │                 │ error names `route refresh` as the fix  │
        │                 └─────────────────────────────────────────┘
        │
        │  one route per (model, provider) pair
        │  organization == provider -> direct_oauth
        │  openrouter/together/... -> reseller
        │  top_scores{}     -> benchmarks vector
        │  input/output_price_per_m + assumed tokens -> per_attempt_cost
        │  context_window is null for ALL models -> counted + warned,
        │                                            never invented
        v
   126 ModelCapabilities across 20 ProviderCapabilities
        │
        v
   ┌─────────────────────────────────────────────────────────────────────┐
   │ routing.py  route_model()   pure function, no I/O, no clock         │
   │                                                                     │
   │  HARD FILTERS   auth, context, output, tools, modalities,           │
   │                 streaming, class, policies, environment,            │
   │                 cost ceiling, confidence, freshness,                │
   │                 provider/model allow+deny                          │
   │        │                                                            │
   │        v                                                            │
   │  quality = (0.60*external + 0.30*local) / 0.90                     │
   │        │                                                            │
   │        v   quality floor                                            │
   │        v                                                            │
   │  SUBSCRIPTION-FIRST  direct subscription                            │
   │                   >  other zero-marginal-cost                       │
   │                   >  reseller           <- reaching here sets       │
   │                                            reseller_exception       │
   │        reseller duplicates of an eligible direct route are          │
   │        eliminated by model id or equivalence class                  │
   │        │                                                            │
   │        v   quality/cost/reliability/latency Pareto frontier         │
   │        v   retain within quality margin                             │
   │        v   open-weight preference (if enabled)                      │
   │        v                                                            │
   │  LOWEST EXPECTED PASSING COST                                       │
   │     attempt_cost                                                    │
   │   + P(repair)     * repair_cost                                     │
   │   + P(escalation) * escalation_cost                                 │
   │        │                                                            │
   │        v   ties: confidence, reliability, latency, model id         │
   └────────┬────────────────────────────────────────────────────────────┘
            v
   ROUTE RECEIPT  (emitted always, even on refusal)
     considered routes | disqualifications + reasons | score inputs
     chosen | fallback | subscription decision | registry timestamp
     evidence freshness | tie-breakers used | escalation conditions
```

### Role categories

```text
   Director   ──> PINNED to the configured frontier model.
                  No automatic fallback. A pinned route that fails its
                  hard requirements is a REFUSAL, never a cheaper swap.
   Manager    ──> must meet advice, review, context, and tool needs
   Worker     ──> cheapest route that clears the floor
   Research   ──> must meet freshness and context needs
   Rehearsal  ──> capable enough that its findings mean something
   Reviewer   ──> DOES NOT EXIST. role="reviewer" raises.
```

## 7. Context and cost

```text
   Director   full access via  ─┐  stable cached prefix
                                │    goals, invariants, terminology, graph
                                │  per-turn delta
                                │    changed nodes, new evidence, escalations
                                │  on-demand retrieval
                                ┘    the exact sections/files/symbols asked for

   Manager    branch-local: its subtree, shared interfaces, child reports

   Worker     unit-local: its unit, acceptance, exact paths/symbols,
              dependency artifacts, commands, review contract

   ✗ "the whole repository" is rejected unless it comes from the Director
     with your explicit authorization.
   ✗ Writing context to a file saves nothing if the harness reinserts the
     whole file every turn. Selective retrieval is the saving.
```

Optimization order, because output tokens cost multiples of input and cached
input costs a fraction:

```text
   1. failed and repeated implementation attempts   <- most expensive mistake
   2. unnecessary model elevation
   3. excessive frontier output
   4. repeated uncached context
```

A cheap worker that fails twice and escalates costs more than a capable worker
that passes once. That is why the ladder is bounded and why routing scores
expected passing cost instead of sticker price.

## 8. Durability

```text
   every phase transition ──> event appended BEFORE the next phase reads state

   .graph-coder/
     state.db            projects, runs, plan_versions, requirements, units,
                         graph_nodes, graph_edges, routes, agents, tasks,
                         attempts, artifacts, reviews, decisions, escalations,
                         model_history, projections
     snapshots/<plan>/vN.json    atomic plan snapshots
     cache/llm-stats/models.json labelled model evidence
     artifacts/                  graphs, routes, jcode bundles

   EVENT LEDGER  append-only, hash-linked
     event_hash = sha256(canonical(row) + prev_hash)
     verify_chain() detects tampering, reordering, and gaps

   RECOVERY
     mark in-flight attempts interrupted
     reopen "completed" units with no evidence
     verify the chain, rebuild projections, recompute the frontier
     keep unknown / interrupted / failed / superseded DISTINCT

   APPROVAL bound to four hashes
     plan_hash + graph_hash + route_hash + render_hash
     any one moves -> approval VOID -> render the full plan again

   SEMANTIC HASH  covers substance, ignores presentation
     in:  objectives, acceptance, dependencies, interfaces,
          read/write/forbidden scopes, commands, expected artifacts,
          manager + review contract, context manifest, routing constraints
     out: titles, rationale, prose, ordering, whitespace
     so an editorial pass does not void an approval, and a changed
     write scope does
```

## 9. Handoff to JCode

```text
   graph-coder jcode emit --graph graph.json
        │
        v
   [ task_graph ]  nodes = everything EXCEPT the Director and the managers
                   metadata.managers = roster with advisory authority,
                                       empty write scopes, nodes reviewed
                   metadata.review_assignments = {worker: manager}
                   each worker prompt names its manager and states that
                   only the manager's passing review completes the node
   [ run_plan  ]   background, Director preserved, concurrency limit,
                   Director prompt states it never edits implementation files

   native_kind(MANAGE) raises. A manager is never disguised as a worker.
   Public swarm operations only. No private socket or protocol dependency.
```
