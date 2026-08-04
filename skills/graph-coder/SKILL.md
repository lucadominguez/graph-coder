---
name: graph-coder
description: Use when a software change needs an implementation-ready plan compiled into a cost-routed agent graph with durable artifacts, bounded context, approval, and directed multi-agent execution.
---
# Graph Coder

Invocation is `/graph-coder`. It does not shadow JCode's built-in `/plan`. Run it from the root JCode session, which holds the frontier Director role for the whole run.

Graph Coder front-loads thinking. Premium effort resolves ambiguity, architecture, interfaces, risk, and graph structure before any implementation begins. Cheaper agents then translate precise unit contracts into code. That is a design target for where effort goes, not a token quota to enforce.

## Authority model

Three roles, and the boundaries between them are the product.

| Role | Has | May do | May never do |
| --- | --- | --- | --- |
| Frontier Director | Full project state through the kernel, indexes, deltas, and on-demand retrieval | Spawn every worker subagent, direct, route, advise, review top-level branch outputs, decide plan mutations | Edit implementation files after execution begins; implement a unit instead of spawning it; finish a worker's task |
| Manager | Its own subtree, shared branch interfaces, child reports | Advise children, supply bounded context, review child submissions, delegate repair, escalate | Edit repository files; run a repair itself; broaden a child's scope without plan mutation; mark work complete without evidence |
| Worker | Its unit packet only | Implement its unit, run its commands, request context, submit a report | Read outside its read scope; write outside its write scope; review its own work |

Managers are control-plane agents. A manager review is a state transition and an artifact, not a second implementation task in the graph. No reviewer agents are created beneath workers: a worker's own manager owns its review. No node in a Graph Coder graph has kind `review`.

A manager reviews the unit contract, the produced diff and artifacts, the acceptance criteria, the test evidence, and read and write scope compliance. It does not receive the worker's private reasoning, and it does not modify the implementation.

Advice, context requests, and escalations are control-plane events, not dependency edges. The implementation DAG stays acyclic no matter how much back-and-forth a branch needs.

The Director's write scope is explicit and permanent:

```text
Director may write        plan artifacts, graph artifacts, routing artifacts,
                          events and status, context packets, escalation packets
Director may write to application code        never
Director may implement a unit itself          never; it spawns a worker instead
```

The Director never becomes the implementer of last resort. When a branch cannot proceed after bounded advice, retry, and fallback, it becomes `human_required`.

## Entry modes

Determine the mode before doing anything else, from durable state rather than chat memory.

- **new plan**: no canonical plan exists for this goal.
- **resume**: a plan exists and execution is partially complete. Load state, rebuild the frontier, continue.
- **revise**: a plan exists and the goal or constraints changed. Mutate the canonical plan and re-derive everything downstream of the change.
- **recover**: durable state exists but the session was interrupted. Run `graph-coder run recover --role Director` first, reconcile, then pick one of the modes above.

Load durable state exactly once per phase entry. Do not re-read the whole ledger between steps.

## Lifecycle

Ten phases. Entry and exit conditions for each are in `references/phase-gates.md`; the artifact each produces and consumes is in `references/artifact-map.md`.

```text
1. INTAKE_AND_CONTEXT      mode, durable state, project kernel, change delta
2. REPOSITORY_GROUNDING    code, tests, conventions, history; facts kept apart from assumptions
3. CONCEPT_GRILL           concept and requirements, via concept-grill
4. TECHNICAL_RESEARCH      question inventory, evidence ledger, decisions, via technical-research
5. PLAN_AUTHORING          one canonical implementation-ready plan, via plan-forge
6. COLD_REHEARSAL          executability trial per unit with fresh agents, via plan-rehearsal
7. GRAPH_COMPILATION       managers and workers, ownership and review assignment, via delegation-graph
8. MODEL_ROUTING           Director pinned, managers capable, workers cheapest passing, via routing-plan
9. FULL_PLAN_APPROVAL      the entire plan rendered, approval bound to hashes
10. DIRECTED_EXECUTION     dispatch, review, advise, isolate, continue, via execution-manager
```

Phases run in order. A phase may send work backward: a rehearsal finding mutates the plan and reruns affected units, and a routing impossibility can force a plan change. Nothing runs forward past a failed gate.

### 1. INTAKE_AND_CONTEXT

Establish the mode. Build or update the project kernel: the small, stable facts every role needs (language and version, package layout, test and build commands, conventions, release constraints). Compute the change delta since the last acknowledged event so later refreshes ship differences instead of repeated full content.

Run `graph-coder init` if durable state does not exist, then `graph-coder inspect` and `graph-coder context build --role Director`.

### 2. REPOSITORY_GROUNDING

Inspect the code that the change will actually touch: entry points, schemas, interfaces, ownership, existing tests, recent churn, and the current results of the build, typecheck, lint, and test commands. Measure the pre-existing failure baseline before claiming anything about new failures.

Record facts separately from assumptions. A fact cites a file, symbol, command result, or artifact hash. An assumption becomes either a bounded explore unit or a launch-blocking question.

### 3. CONCEPT_GRILL

Invoke `concept-grill`. It orchestrates an installed third-party brainstorming workflow and normalizes the result into the `Concept and Requirements` section of the canonical plan. There is no separate Product Contract phase and no separate product document.

Run the dependency preflight first. If the required dependency is missing, stop and give the user the exact installation message. Never simulate a third-party skill and claim its reliability.

### 4. TECHNICAL_RESEARCH

Invoke `technical-research`. Research begins with a question inventory, not with agents. Only the capabilities relevant to the open questions are dispatched: a repository-only question does not trigger web research, and a version-sensitive framework question does trigger official documentation research.

Every retained claim must change a decision, risk, acceptance criterion, or unit. Unused findings are omitted.

### 5. PLAN_AUTHORING

Invoke `plan-forge`. There is exactly one canonical plan and it has these sections, in this order:

```text
 1. Goal Capsule                     9. Canonical Implementation Units
 2. Concept and Requirements        10. Delegation Graph
 3. Scope and Non-Goals             11. Routing Assignments
 4. Acceptance and Invariants       12. Context Contract
 5. Repository Grounding            13. Verification Contract
 6. Technical Research              14. Failure and Recovery Contract
 7. Technical Decisions             15. Definition of Done
 8. System Impact                   16. Sources and Evidence
```

Later phases append detail within these sections. They never create a parallel document and never discard earlier decisions.

Plan refinement is monotonic in substance. A later phase may add specificity, evidence, constraints, interfaces, tests, and graph metadata. Deleting or materially weakening an acceptance criterion, invariant, interface, source, or unit requires a recorded decision and invalidates approval. Rewording and reformatting do not.

Every executable unit carries the full contract: `unit_id`, `objective`, `kind`, `dependencies`, `acceptance_ids`, `repo_paths`, `symbols`, `read_scope`, `write_scope`, `forbidden_scope`, `interfaces`, `commands`, `expected_artifacts`, `manager_id`, `review_contract`, `context_manifest`, `risk`, `failure_domain`, and `retry_policy`. A unit missing any of these is not implementation-ready.

### 6. COLD_REHEARSAL

Invoke `plan-rehearsal`. This is an executability trial, not an execution review, and it does not replace the manager review that happens during execution.

Give each fresh agent the exact task packet the future worker will receive, and nothing else. Repository edits are prohibited. Ask whether the unit can be completed and verified from the packet alone. Route every valid finding back into the same canonical plan, then rerun the affected units. High-risk and critical units get two independent rehearsals.

Rehearsal has no authority to fix the plan. It reports; `plan-forge` mutates.

### 7. GRAPH_COMPILATION

Invoke `delegation-graph`. Compile the plan into managers and workers.

```text
kind:      manage | explore | spike | implement | verify | integrate | repair | release
role:      composite | atomic
authority: advisory_only | implementation
review_owner: <manager node id>
```

One advisory-only manager per meaningful branch or failure domain, not one per worker. A manager owns a coherent subtree whose shared context and interfaces fit inside its limits. Every worker's `review_owner` is its direct manager; top-level manager outputs are reviewed by the Director.

Do not compile review tasks. Review is represented by the worker's `review_contract` and by execution events. Keep `verify` nodes only where the agent performs a concrete validation action, such as running compatibility tests or inspecting a generated artifact; never use `verify` to smuggle a reviewer role back in.

Run `graph-coder graph compile --plan <plan> --output <graph>` then `graph-coder graph validate --file <graph>`.

### 8. MODEL_ROUTING

Invoke `routing-plan`. Routing is deterministic: the same registry and unit always produce the same route.

**This phase is not optional and cannot be satisfied by a plan that already names routes.** Run `graph-coder route refresh`, then `graph-coder route assign` per unit. A plan authored before this phase carries `primary_route: local`, which is the placeholder that lets a plan compile without network evidence. It is not a route. If `local` survives into the graph, the workers run on whatever default model the harness hands them, unrouted and unmetered, and every cost figure in the approved plan is fiction. Skipping this phase is the cheapest-looking mistake in the lifecycle and the one that quietly removes the reason the system exists.

- The Director is pinned to the configured frontier model and is never silently downgraded.
- Managers are routed for advice, review, context window, and tool requirements.
- Workers are routed for the lowest expected cost of a passing result, not the lowest sticker price.
- Research and cold-rehearsal routes must satisfy their evidence and context needs.
- There is no standalone reviewer route category.

Expected passing cost is `attempt_cost + probability_of_repair * repair_cost + probability_of_escalation * escalation_cost`, computed from configured estimates. Do not claim precision the registry data does not support.

Every assignment emits a route receipt: considered routes, disqualifications, score inputs, chosen route, fallback route, and registry timestamp.

### 9. FULL_PLAN_APPROVAL

Render the complete canonical plan to the user. All sixteen sections, every implementation unit, the delegation graph, routing assignments and fallbacks, the context contract, the cost estimate with its measurement assumptions, and every unresolved risk or human decision.

A summary is not an approval view. Never offer a compressed or consolidated document in place of the plan. If the plan is long, say so and render it anyway.

Bind approval to the plan hash, graph hash, route hash, and render hash, and record it with `graph-coder event append --type plan.approved`. Any material change to the plan, graph, routing, or context contract invalidates approval and requires a fresh full-plan approval.

### 10. DIRECTED_EXECUTION

Invoke `execution-manager`.

**Execution means spawning subagents. Settle this before anything else in the phase.**

Every node in the compiled graph except the Director and its managers runs inside its own freshly spawned subagent. Not a section of your own reply. Not a file you edit yourself. Not a plan you narrate and then carry out because by now you already know what the code should say. If this phase ends and you never called your harness's subagent tool, the run failed, however good the resulting code looks.

You are the Director, and the restriction is the entire point of the role: you spawn, you route, you review, you advise, you record. You do not implement. If you are about to open an implementation file during this phase, stop, because you have skipped dispatch.

Dispatch each round like this. The full worked recipe, including the shape of the emitted packet, is in `references/dispatch.md`.

0. Preflight. Check the swarm for plan nodes left by earlier sessions, which otherwise merge into yours and produce a graph many times the size of the one you compiled. Remove those nodes by id. Never open with `swarm cleanup --force`: it is global, and a run that followed that advice stopped every worker on the machine including unrelated projects' agents. Then read the `preflight` block that `graph-coder jcode emit` returns and stop unless `ready_to_dispatch` is true. It fails when a node still carries the placeholder route `local`, which means phase 8 was skipped and the workers will run on whatever default the harness supplies, and when a node would spawn without `spawn_mode: visible`, which does the work invisibly, absent from `swarm list`, leaving you a status roster you cannot honestly fill in.
1. `graph-coder run status` gives the current frontier: every node whose dependencies all reached `completed` through a passing review.
2. `graph-coder jcode emit --graph <graph>` gives the packets. Its `task_graph` operation carries one entry per dispatchable node, and each entry's `content` is that node's worker packet, already bounded to its read, write, and forbidden scopes. The Director and the managers are excluded from that list by construction, so everything the emit returns is meant to be spawned.
3. Spawn one subagent per ready node with whatever subagent tool the harness exposes. In JCode that is one `swarm spawn` per node, carrying the node's `content` verbatim as the prompt, its `id` as the label, its routed model, and `--spawn_mode visible`. Issue the whole round in one message. The emitted `run_plan` batch path exists but is brittle, having failed on both stale plan pollution and coordinator assignment errors; when it errors, fall back to per-node spawns rather than debugging it. Do not paraphrase a packet, do not merge two nodes into one spawn, and do not widen a scope to make a spawn simpler.
4. Spawn width comes from the dependency DAG. Independent nodes go together, up to `max_active_workers` (8), and never one at a time because sequential felt easier to follow. A linear chain such as `IU-STORE -> IU-BACKEND -> IU-FRONTEND` goes one at a time by necessity: spawn, wait for the artifacts, verify, review, then spawn the next. A worker handed a repository that does not yet contain what its packet told it to build on will fail for a reason the plan never predicted.
5. Monitor both signals while workers run. The filesystem says whether a node is done; `swarm status` says whether its worker is alive. A worker blocked on a `429` writes nothing, exactly like a worker that is thinking, so a filesystem-only poll cannot distinguish them and one run watched a directory for two minutes while its worker sat rate-limited. Treat a rate limit as transient infrastructure, and never respawn a node whose worker is still alive.
6. Verify completion from the filesystem and from commands, not from a swarm report. Check that the node's `write_scopes` changed, run the unit's verification commands, and quote the real output. That evidence is what the `review_owner` reviews. A worker's own claim of success is not evidence, and absence from `swarm list` is a monitoring gap to report rather than a verdict either way.
7. Record a dispatch event per spawn before relying on it.

Each of these counts as failing to execute the graph, whatever the final diff looks like:

- implementing the units yourself in the root session, in dependency order;
- spawning one subagent for the whole plan instead of one per node;
- spawning subagents to read, research, or summarize, then writing the code yourself;
- dispatching ready nodes one at a time when several were ready together;
- spawning a dependent node before its predecessor's artifacts exist;
- spawning headless or inline, so no worker is visible or monitorable;
- dispatching packets that still carry the placeholder route `local`;
- moving a node to `completed` on the worker's own say-so, with no manager review.

Manager review is a control-plane act, carried out by the manager agent when the harness gives you one and by you on that manager's behalf otherwise, always against the unit's `review_contract`. A manager is never spawned as an implementation task and never receives a write scope.

Then run one loop until the graph is finished or genuinely blocked.

```text
dispatch ready workers with bounded packets
  worker submits report            -> awaiting_review
  manager reviews against the unit contract
    pass                           -> completed, dependents become eligible
    repair_required                -> bounded repair by a worker, never by the manager
    human_required                 -> isolate this branch, continue every other
persist every transition; finish with evidence
```

Execution states:

```text
pending  ready  running  awaiting_review  repair_required
completed  blocked  human_required  failed  cancelled
```

Only a passing manager review moves a worker from `awaiting_review` to `completed`, and only that transition makes dependents eligible. A worker that says it is done is not done.

The escalation ladder is bounded:

```text
worker attempt
  -> manager advice
  -> same-worker repair attempt
  -> fallback-worker repair attempt
  -> higher-manager or Director advice
  -> human_required
```

A unit's `retry_policy` may shorten this ladder. Nothing may add unbounded retries.

`human_required` blocks that node's transitive dependents and nothing else. Independent ready nodes keep running. Report what is blocked, what continues, what was already attempted, and the exact decision the human needs to make. Resume with `graph-coder run resume`, which records the decision as an artifact and event and recomputes the frontier without erasing the failure evidence.

## Context contract

Leaf agents receive unit-local context. Managers receive branch-local context. The Director reaches full project state through the kernel, indexes, deltas, and on-demand retrieval; the repository is never copied into every prompt.

- A worker packet holds its unit, relevant acceptance criteria, exact path and symbol references, dependency artifacts, constraints, commands, and its review contract.
- A manager packet holds its subtree, shared branch interfaces, child reports, and relevant evidence.
- The Director packet holds the kernel, artifact indexes, state summaries, and changes since the last acknowledged event.

A context request travels upward and returns a minimal patch. Fulfilment enforces read scope, forbidden scope, repository boundaries, and byte limits. A request for the whole repository is rejected unless it comes from the Director with explicit user authorization. A superior may answer with advice or context; it may never convert the request into its own implementation task.

Writing the same context into a file and rereading it is not a saving. If the harness reinserts the whole file every turn, the model still reads all of it. Selective retrieval is what saves cost:

```text
stable cached prefix   goals, invariants, terminology, graph summary
per-turn delta         changed nodes, new evidence, escalations
on-demand retrieval    the exact plan sections, files, and symbols requested
```

## Cost model

Repeated context often dominates raw token counts, but it does not necessarily dominate billed cost, because output and reasoning tokens are priced far higher than input, and cached input is cheaper again. Optimize in this order:

1. Failed and repeated implementation attempts. A rejected unit pays for its context twice and its output twice.
2. Unnecessary model elevation. A frontier model doing a translation job is the most expensive mistake available.
3. Excessive frontier output. Direct, decide, and review; do not restate the plan.
4. Repeated uncached context. Keep the prefix stable so it caches, and ship deltas.

This is why the escalation ladder is bounded and why routing scores expected passing cost rather than sticker price. A cheap worker that fails twice and escalates is more expensive than a capable worker that passes once.

## Maximum-reliability gates

- Dependency preflight runs before concept grilling and technical research. A missing required dependency stops the run before approval with an exact installation message.
- Version-sensitive claims carry a version or retrieval date, and a deprecation or breaking-change check.
- Conflicting critical claims are resolved or surfaced in the plan; they never silently coexist.
- Secrets are read from the environment at request time. Never ask for a plaintext key in chat, a command, a plan, an event, or a tracked file.
- Command results are quoted from actual output. A green build is not evidence that a surface works.
- After a reload, rebuild from the ledger and repository artifacts, reconcile against harness state, and preserve `unknown`, `interrupted`, `failed`, and `superseded` as distinct states.

## Commands

```text
graph-coder init
graph-coder inspect
graph-coder plan status|validate|snapshot|reconcile --file <plan>
graph-coder graph compile --plan <plan> --output <graph>
graph-coder graph validate --file <graph>
graph-coder route refresh|assign|explain
graph-coder route set --graph <graph> [--node <id>] --model <model> [--fallback <model>] [--evidence <source>]
graph-coder event append --type <event> --payload <json> --role <role>
graph-coder run status|recover|resume
graph-coder context build --role <director|manager|worker>
graph-coder jcode emit --graph <graph>
```

Do not invent commands such as `graph-coder new`, `graph-coder approve`, `graph-coder execute`, or `graph-coder status`. Approval and lifecycle transitions are recorded with `graph-coder event append`.

## Decision surfaces

Entry mode, kernel contents, fact versus assumption, concept sufficiency, research stop condition, unit boundary, manager subtree shape, review ownership, route category, approval scope, invalidation trigger, escalation threshold, failure domain, and resume authority.

## Evidence rules

Every load-bearing claim cites a file, symbol, command result, artifact hash, or authoritative source with a date. Completion claims require a passing manager review with acceptance results, artifact hashes, and a scope diff. Never infer completion from a worker summary, and never convert missing evidence into an inferred pass.

## STOP/escalation rules

Stop and escalate on: a harness that exposes no way to spawn subagents; a missing required third-party dependency; user-only product ambiguity; an unresolved conflicting critical claim; a plan that cannot become implementation-ready; a unit with unverifiable acceptance; a graph that would need a reviewer node or a manager with write scope; no route meeting hard requirements; a request to approve without rendering the full plan; a material change after approval; a destructive operation without authorization; secret exposure; a plan, graph, or route hash mismatch; an exhausted escalation ladder; or any recovery that would silently change the approved contract.
