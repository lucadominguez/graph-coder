# Graph Coder

Graph Coder (Graph Coder) is an external Python control layer and portable Agent Skills suite that turns rough product intent into a repository-grounded, reviewed, rehearsed, routed, and approved execution graph for coding agents.

Graph Coder targets JCode on Windows first while preserving adapter boundaries for other coding agents. It does not fork JCode, replace its swarm engine, or let an LLM make final routing decisions.

## Status

Early v0.1 implementation. The user-facing orchestration command is `/aps-plan`; JCode's built-in `/plan` remains untouched.

## Core flow

```text
mind dump
  -> concept grill
  -> product contract
  -> repository-grounded plan
  -> specialist review and cold rehearsal
  -> deterministic routing
  -> approved typed DAG
  -> JCode swarm execution
```

## Install for development

```shell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"   # Windows
# .venv/bin/python -m pip install -e ".[dev]"     # POSIX
.venv\Scripts\aps --help
```

Python 3.11 or later is required. Provider credentials (for example `LLM_STATS_API_KEY` for `aps route refresh`) are read from environment variables at request time and are never persisted by Graph Coder. See `docs/installation.md` for the portable skills installers.

## CLI surface

The `aps` command exposes exactly these operations:

| Command | Purpose |
| --- | --- |
| `aps init` | Initialize durable Graph Coder state (`.graph-coder/` layout, SQLite ledger) |
| `aps inspect` | Repository context plus JCode adapter compatibility |
| `aps plan status\|validate\|snapshot\|reconcile` | Canonical Markdown plan operations |
| `aps graph compile\|validate` | Compile a plan into a typed DAG and validate it |
| `aps route refresh\|assign\|explain` | Deterministic model routing (LLM Stats cache plus capability filters) |
| `aps event append` | Append to the hash-linked event ledger |
| `aps run status\|recover` | Execution status projections and recovery packets |
| `aps context build` | Role-specific context packet |
| `aps jcode emit` | Public JCode swarm `task_graph`/`run_plan` operation bundle |
| `aps terminal open` | Windows Terminal layout (dry run by default; `--execute` opens tabs) |

There are no `aps new`, `aps approve`, `aps execute`, or `aps status` commands. Approval and lifecycle transitions are recorded with `aps event append`, and orchestration is driven by the `/aps-plan` skill.

## Deterministic workflow

Global options such as `--root` precede the subcommand. Given an implementation-ready canonical plan and a router input matrix:

```shell
aps --root . init
aps --root . plan validate --file docs/plans/2026-07-27-example-plan.md
aps --root . plan snapshot --file docs/plans/2026-07-27-example-plan.md
aps --root . graph compile --plan docs/plans/2026-07-27-example-plan.md --output .graph-coder/artifacts/graph.json
aps --root . route assign --input .graph-coder/artifacts/routes.json
aps --root . event append --type plan.approved --payload "{}" --role Director --plan-id P-example --repository-commit <commit>
aps --root . jcode emit --graph .graph-coder/artifacts/graph.json --output .graph-coder/artifacts/jcode-operations.json
aps --root . run status
```

`route explain` performs the same deterministic calculation without writing state. The Director applies the emitted public JCode operations only after the consolidated approval. Canonical plan versions, requirements, units, graphs, routes, and event receipts are persisted in `.graph-coder/state.db`; snapshots and generated artifacts remain under `.graph-coder/`.

## Limitations and provisional validation

- The LLM Stats client (`aps route refresh`) targets the provisional `https://llm-stats.com/api/v1` schema. It is validated against fixtures and cached responses; live API validation remains provisional until a successful authenticated fetch is recorded.
- The JCode adapter targets JCode v0.55.0, detects the installed version via `jcode --version`, and emits public swarm operation bundles only. Compatibility with future JCode releases is not guaranteed.
- `aps terminal open --execute` requires Windows with `wt.exe` available. Komorebi is intentionally not required.
- Graph Coder emits operation bundles for the Director to apply. It does not spawn or manage JCode workers itself in v1.

## Safety boundaries

- One canonical plan, mutated in place with atomic snapshots.
- One consolidated user approval before execution.
- Deterministic lifecycle, routing, budgets, graph validation, and recovery.
- Bounded worker authority and spawning.
- Local failures block dependent descendants only.
- The foreground JCode session remains the Director.
- No private JCode socket protocol dependency in v1.

See `docs/architecture.md` for the implementation architecture, `docs/design-contract.md` for the v1 design contract, `docs/skills.md` for the seven portable skills, `docs/installation.md` for installers, and `CHANGELOG.md` for release history.
