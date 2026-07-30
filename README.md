# Graph Coder

Graph Coder turns a rough request into an implementation-ready plan, compiles that
plan into a delegation graph of advisory managers over implementing workers,
routes every role by expected cost, and directs execution without letting the
expensive models take over the work.

It is a skill suite plus a small Python control layer for durability and routing.
It targets JCode on Windows first, through public swarm operations only. It does
not fork JCode, replace its swarm engine, or let a model make the final routing
decision.

## The idea

Front-load the thinking. A frontier model resolves ambiguity, architecture,
interfaces, risk, and graph structure once. Cheap models then translate precise
unit contracts into code. That only works if the contracts are genuinely complete,
which is what most of this repository is about.

Three roles, and the boundaries between them are the product:

| Role | May do | May never do |
| --- | --- | --- |
| Frontier Director | Direct, route, advise, review branch outputs | Edit implementation files; finish a worker's task |
| Manager | Advise its children, supply bounded context, review submissions, delegate repair, escalate | Edit files; repair anything itself; complete work without evidence |
| Worker | Implement its unit, run its commands, request context, submit a report | Read or write outside its scope; review itself |

There are no reviewer agents beneath workers. A worker's own manager reviews it.
No node in a Graph Coder graph has kind `review`, and `NodeKind("review")` raises.

## Lifecycle

```text
/graph-coder
 1. INTAKE_AND_CONTEXT      mode, durable state, project kernel, change delta
 2. REPOSITORY_GROUNDING    code, tests, conventions, baseline failures
 3. CONCEPT_GRILL           concept and requirements
 4. TECHNICAL_RESEARCH      question inventory, evidence ledger, decisions
 5. PLAN_AUTHORING          one canonical implementation-ready plan
 6. COLD_REHEARSAL          executability trial per unit, with fresh agents
 7. GRAPH_COMPILATION       managers and workers, review assignment
 8. MODEL_ROUTING           Director pinned, workers cheapest-passing
 9. FULL_PLAN_APPROVAL      the entire plan rendered, approval bound to hashes
10. DIRECTED_EXECUTION      dispatch, review, advise, isolate, continue
```

Only a passing manager review moves a unit from `awaiting_review` to `completed`,
and only that transition makes its dependents eligible. A branch that exhausts
advice, retry, and fallback becomes `human_required`, which blocks its transitive
dependents and nothing else. Every independent branch keeps running.

## Skills

Eight skills, installed into `.agents/skills` and optionally `.jcode/skills`.

| Skill | Role |
| --- | --- |
| `graph-coder` | The `/graph-coder` orchestrator: phases, gates, authority, approval |
| `concept-grill` | Controller for an installed third-party brainstorming skill |
| `technical-research` | Question router and evidence normalizer |
| `plan-forge` | Authors and strengthens the one canonical plan |
| `plan-rehearsal` | Cold-tests each unit with the exact future worker packet |
| `delegation-graph` | Compiles managers and workers, validates the invariants |
| `routing-plan` | Profiles roles and invokes the deterministic router |
| `execution-manager` | Advises and reviews as a manager, without implementing |

`concept-grill` and `technical-research` orchestrate third-party skills rather
than reimplementing them. They do not copy prompt bodies, and a missing required
dependency is a preflight failure, not something to simulate. See
`skills/graph-coder/references/third-party-skills.md` for verified trigger names,
versions, and licenses.

## Install

```shell
# Python control layer
uv venv && uv pip install -e ".[dev]"
.venv\Scripts\graph-coder --help     # Windows
# .venv/bin/graph-coder --help       # POSIX

# Portable skills, idempotent
bash scripts/install.sh --project-root /path/to/project
./scripts/install.ps1 -ProjectRoot C:\path\to\project
```

Python 3.11 or later. Credentials such as `LLM_STATS_API_KEY` are read from the
environment at request time and never persisted. See `docs/installation.md`.

## CLI surface

| Command | Purpose |
| --- | --- |
| `graph-coder init` | Initialize durable state (`.graph-coder/`, SQLite ledger) |
| `graph-coder inspect` | Repository context plus JCode adapter compatibility |
| `graph-coder plan status\|validate\|snapshot\|reconcile` | Canonical plan operations |
| `graph-coder graph compile\|validate` | Compile a plan into managers and workers, and validate |
| `graph-coder route refresh\|assign\|explain` | Deterministic routing with receipts |
| `graph-coder event append` | Append to the hash-linked event ledger |
| `graph-coder run status\|recover\|resume` | Status, recovery, and human-required resume |
| `graph-coder context build` | Role-scoped context packet |
| `graph-coder jcode emit` | Public JCode swarm `task_graph`/`run_plan` bundle |
| `graph-coder terminal open` | Windows Terminal layout (dry run unless `--execute`) |

There are no `new`, `approve`, `execute`, or `status` top-level commands.
Approval and lifecycle transitions are recorded with `event append`.

```shell
graph-coder --root . init
graph-coder --root . plan validate   --file docs/plans/example-plan.md
graph-coder --root . plan snapshot   --file docs/plans/example-plan.md
graph-coder --root . graph compile   --plan docs/plans/example-plan.md --output .graph-coder/artifacts/graph.json
graph-coder --root . route assign    --input .graph-coder/artifacts/routes.json
graph-coder --root . event append    --type plan.approved --payload "{}" --role Director --plan-id P-example
graph-coder --root . jcode emit      --graph .graph-coder/artifacts/graph.json
graph-coder --root . run status
```

## What the code enforces

The skills carry the rules. These are the ones the Python layer refuses to let
you violate:

- `NodeKind` has no `review` member, so no durable graph can record a reviewer node.
- A `manage` node must be composite, advisory-only, and hold an empty write scope.
- A `review_owner` must exist, must not be the node itself, and must be a manager
  or the root Director.
- `running -> completed` is not a legal transition; only a manager verdict leaves
  `awaiting_review`.
- A dependency is satisfied only in `completed`. `done` is not accepted.
- `repair_required` needs a bounded defect and a repair instruction;
  `human_required` needs the question, the attempts made, and the impacted nodes.
- `block_descendants` returns transitive dependents only, so an isolated failure
  cannot stop an independent branch.
- An approved plan must bind plan, graph, route, and render hashes, with
  `rendered_full_plan: true`. A summary is not an approval view.
- The Director's route is pinned and never silently downgraded, and there is no
  reviewer route category.
- Every route assignment emits a receipt, including on refusal.

## Provenance

Graph Coder is an independent repository seeded from the Agent Planning System
(APS), which remains unchanged and available as a comparison baseline. The exact
APS commit studied is pinned in `upstream/aps.lock.json`, every ported file is
mapped in `docs/upstream-provenance.md`, and APS's MIT notice is reproduced in
`NOTICE`.

`scripts/check_aps_upstream.py` reports whether APS has moved past the pinned
commit. It fetches into a throwaway directory and never merges, rebases, imports
code, or edits the lock. A weekly read-only workflow runs it and writes the report
to the job summary.

## Limitations

- Live behavioral evaluation has not been run. The rules above that live in skill
  prose are instructions, not guarantees; only the enforced list is mechanical.
- The LLM Stats client targets ZeroEval at `https://api.zeroeval.com/stats/v1`,
  verified live on 2026-07-30 against `GET /stats/v1/models`. The API reports no
  context window for any model, so a unit that declares `min_context_tokens`
  eliminates every route unless you supply `context_window_overrides`. Per-attempt
  cost is derived from published per-million prices and assumed token counts, and
  is labelled an estimate in the route receipt.
- The JCode adapter targets v0.55.0, detects the installed version via
  `jcode --version`, and emits public swarm bundles only. It was written against
  the documented public interface, not verified against a running JCode.
- Graph Coder emits operation bundles for the Director to apply. It does not spawn
  or manage workers itself.
- `terminal open --execute` needs Windows with `wt.exe`. Komorebi is not required.

`docs/schematic.md` draws the whole system in text: the skill/code split, the
10-phase lifecycle, the execution hierarchy, what the graph refuses to compile,
the state machine, routing from live data to a receipt, and durability. Start
there. Then see `docs/architecture.md`, `docs/design-contract.md`,
`docs/skills.md`, `docs/installation.md`, and `CHANGELOG.md`.
