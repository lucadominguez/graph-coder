# Phase gates

Each phase has an entry condition, an exit condition, and stop conditions. A phase
that cannot meet its exit condition does not advance; it either loops with new
evidence or stops and asks. Never advance on optimism.

"Stop" means: report what is known, what is missing, and what decision is needed,
then wait. It does not mean abandon the run.

## 1. INTAKE_AND_CONTEXT

**Enter** with a user goal, or with existing durable state.

**Exit** when the run mode is decided, the project kernel exists, and the change
delta since the last acknowledged event is computed.

**Stop** when the goal is too vague to distinguish from a different goal, when
durable state is corrupt, or when the ledger fails hash-chain verification.

## 2. REPOSITORY_GROUNDING

**Enter** with the project kernel.

**Exit** when the code the change will touch has been read, the build, typecheck,
lint, and test commands have been run, the pre-existing failure baseline is
recorded, and facts are separated from assumptions.

**Stop** when the repository cannot be built or tested at all and the plan depends
on knowing whether it works.

Do not skip the baseline. Without it, no later claim about new failures is checkable.

## 3. CONCEPT_GRILL

**Enter** with the goal, grounding facts, and a passing dependency preflight.

**Exit** when `Concept and Requirements` in the canonical plan states the problem,
the users, the value, the non-goals, and the requirements, and every requirement is
testable.

**Stop** when the required dependency is missing, when the concept depends on a
product decision only the user can make, or when the value proposition cannot be
stated without inventing user demand.

## 4. TECHNICAL_RESEARCH

**Enter** with a question inventory derived from the plan's open decisions.

**Exit** when every material question is answered or explicitly marked unresolved;
critical claims cite authoritative sources where those exist; version-sensitive
claims carry a version or retrieval date; conflicting claims are resolved or
surfaced in the plan; and every retained claim affects a decision, risk, acceptance
criterion, or unit.

**Stop** when a critical claim has no authoritative source and the decision cannot
be deferred, or when two authoritative sources conflict on a load-bearing fact.

Research does not stop because it has been running a while. It stops on the
conditions above.

## 5. PLAN_AUTHORING

**Enter** with concept, grounding, and research settled.

**Exit** when all sixteen sections are present and populated; every unit carries the
complete unit contract; traceability runs both ways between requirements,
acceptance criteria, and units; write scopes do not overlap unsafely; and the plan
status is `implementation-ready`.

`requirements-ready` is a valid intermediate status. Execution may only begin from
`implementation-ready`.

**Stop** on unverifiable acceptance, unbounded scope, a destructive migration
without authorization, invalid shared architecture, or a unit that cannot be owned
and verified independently.

## 6. COLD_REHEARSAL

**Enter** with `implementation-ready` and one task packet per unit.

**Exit** when every unit has a complete persisted rehearsal report concluding it is
executable from its packet alone; every valid finding has been routed into the plan
and the affected units reran; and high-risk and critical units have two independent
passes.

**Stop** when a rehearsal reveals an impossible acceptance check, a missing required
input with no producer, an unsafe concurrent writer, a circular dependency, or a
blocker only the user can resolve.

A confident rehearsal agent is not a passing rehearsal. Pass only when the agent can
name its inputs, allowed writes, procedure, commands, expected evidence, review
handoff, and stop conditions.

## 7. GRAPH_COMPILATION

**Enter** with a rehearsed `implementation-ready` plan.

**Exit** when the graph validates: acyclic dependencies and artifacts; every unit
mapped; `manage` nodes composite, advisory-only, and holding empty write scopes;
every atomic executable node carrying `authority: implementation` and an ancestor
manager as `review_owner`; no node reviewing itself; no manager reviewing outside
its subtree; no node of kind `review`; no unsafe write-scope overlap between
concurrent nodes; and bounds respected.

**Stop** on a cycle, a missing owner, an unknown dependency, an incomplete artifact
handoff, a duplicate producer, an unsafe concurrent writer, unbounded expansion, a
node needing authority outside the approved plan, or any graph that would require a
reviewer node to be valid.

Graph optimization must never group managers with workers, nodes with different
managers, writers with overlapping write scopes, or nodes from failure domains whose
coupling would spread a failure.

Unchanged plan units keep their node IDs across recompilation. Stability is what
makes resume and recovery meaningful.

## 8. MODEL_ROUTING

**Enter** with a validated graph.

**Exit** when every node has a primary route and, where possible, a
provider-diverse fallback; the Director is pinned to the configured frontier model;
every route emitted a receipt; and the cost estimate states its assumptions.

A route the plan carried in before this phase is not an exit. `local` is the
placeholder that lets an example plan compile without network evidence, so a graph
still holding `local` after phase 8 means the phase did not run. Exit requires a
receipt per node produced by `route assign` against refreshed evidence. Every phase
in this lifecycle is mandatory; this is the one that gets skipped, because a plan
that already names something in its route field looks finished.

**Stop** when no model meets a node's hard requirements, when the evidence
confidence floor fails, when credentials are unavailable and no policy-valid cache
exists, or when routing would silently substitute the Director's model.

Infrastructure failure is never evidence of model incapability.

## 9. FULL_PLAN_APPROVAL

**Enter** with plan, graph, and routes all valid.

**Exit** when the complete canonical plan has been rendered to the user, together
with the graph, routing assignments and fallbacks, context contract, cost estimate
with assumptions, and unresolved risks; and the user's approval is recorded bound to
the plan, graph, route, and render hashes.

**Stop** when the user asks to approve without seeing the plan, when a material
change lands mid-approval, or when a required human decision is still open.

Rendering the whole plan is the gate. A summary, a diff, or a consolidated document
does not satisfy it, however long the plan is.

## 10. DIRECTED_EXECUTION

**Enter** with a recorded approval whose four hashes still match current state, and
with a confirmed way to spawn subagents in this harness. Without one, stop here and
say so; a Graph Coder graph cannot be executed by the root session alone. Enter also
requires a cleared swarm (`swarm cleanup --force`), routed models rather than
`local`, and `spawn_mode: visible` on every emitted task.

**Exit** when every node is `completed` through a passing manager review, or is
`human_required` with its blocked descendants recorded and every independent branch
carried as far as it can go; and the Definition of Done is met with fresh command
output. Exit also requires that at least one subagent was spawned per dispatchable
node and that the root session wrote no implementation file during the phase. A run
that produced code without spawns did not execute the graph and does not exit.

**Stop** and escalate on a hash mismatch against the approval, a destructive
operation without authorization, secret exposure, an unsafe write conflict, global
budget exhaustion, an exhausted escalation ladder, or any recovery that would
silently change the approved contract.

Per-node gates during execution:

- A node becomes `ready` only when every dependency reached `completed` through a
  passing manager review.
- A node moves from `ready` to `running` only when a subagent has been spawned for
  it with its emitted packet. The Director doing the work is not a running node.
- A worker moves to `awaiting_review` on submitting a complete report.
- Only a `pass` verdict moves it to `completed`.
- `repair_required` returns it to a worker, with bounded defects and instructions.
- `human_required` blocks its transitive dependents and nothing else.

## Reliability gates that apply in every phase

- Dependency preflight before phases 3 and 4.
- No claim without a citation: file, symbol, command result, artifact hash, or
  dated source.
- No completion without evidence that postdates the last material change.
- Secrets read from the environment at request time, never requested in chat and
  never written to a tracked file.
- After a reload, rebuild from the ledger and artifacts, reconcile against harness
  state, and keep `unknown`, `interrupted`, `failed`, and `superseded` distinct.
- Every phase transition appends an event before the next phase reads state.
