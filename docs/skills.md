# Graph Coder portable skills

The installers deliver seven Agent Skills: `aps-plan`, `idea-grill`, `plan-forge`, `plan-rehearsal`, `routing-plan`, `delegation-graph`, and `execution-manager`.

`/aps-plan` is the only slash invocation. It never claims or shadows JCode's built-in `/plan`. The other six skills are bounded advisory specialists invoked by the Director during the lifecycle.

## Skill roles

| Skill | Role |
| --- | --- |
| `aps-plan` | Foreground Director. Drives the persisted 17-phase lifecycle (`INTAKE` through `COMPLETION`), owns the canonical plan, one consolidated approval, and coordinator-gated graph changes. |
| `idea-grill` | Converts a rough mind dump into a requirements-ready Product Contract by resolving only subjective product decisions. |
| `plan-forge` | Authors and repeatedly strengthens the one canonical implementation plan using repository evidence and structured specialist defects. |
| `plan-rehearsal` | Cold-tests every leaf task with fresh-context executors and converts valid confusion into canonical plan defects before execution. |
| `routing-plan` | Profiles implementation units and invokes the deterministic Graph Coder router. It never selects models through LLM judgment and never launches workers. |
| `delegation-graph` | Compiles implementation units into a bounded typed DAG with explicit ownership, artifacts, review gates, and safe parallel groups. |
| `execution-manager` | Advises the Director during approved execution, isolates failures, and assembles evidence-backed recovery and escalation packets. It applies no coordinator-gated mutations. |

Before live model evidence refresh, `aps-plan` and `routing-plan` verify that `LLM_STATS_API_KEY` is available without printing it. If it is absent and no policy-valid cache is sufficient, they ask the user to configure the environment or secret manager. They never request a plaintext key in chat or persist one in plans, commands, events, caches, or tracked files.

## Command discipline

The Director uses only the implemented deterministic `aps` CLI surface (`init`, `inspect`, `plan status|validate|snapshot|reconcile`, `graph compile|validate`, `route refresh|assign|explain`, `event append`, `run status|recover`, `context build`, `jcode emit`, `terminal open`). Commands such as `aps new`, `aps approve`, `aps execute`, or `aps status` do not exist. The Director keeps one approval before execution and records it with `aps --root <repo> event append --type plan.approved --payload "{}" --role Director --plan-id <plan-id> --repository-commit <commit>`. Specialists remain bounded advisory roles only.
