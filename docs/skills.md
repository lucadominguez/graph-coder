# Graph Coder portable skills

The installers deliver eight Agent Skills: `graph-coder`, `concept-grill`,
`technical-research`, `plan-forge`, `plan-rehearsal`, `delegation-graph`,
`routing-plan`, and `execution-manager`.

`/graph-coder` is the only slash invocation. It never claims or shadows JCode's
built-in `/plan`. The other seven are bounded roles the Director invokes during the
lifecycle.

## Skill roles

| Skill | Role |
| --- | --- |
| `graph-coder` | Foreground Director. Drives the persisted 10-phase lifecycle (`INTAKE_AND_CONTEXT` through `DIRECTED_EXECUTION`), owns the canonical plan, full-plan approval, and coordinator-gated graph changes. |
| `concept-grill` | Runs a dependency preflight, selects one installed third-party brainstorming workflow, invokes it, and normalizes the result into the canonical plan. It authors no units and conducts no technical research. |
| `technical-research` | Builds the research-question inventory, dispatches only the capabilities those questions need, normalizes answers into sourced claims, and converts them into plan decisions. |
| `plan-forge` | Authors and repeatedly strengthens the one canonical implementation plan using repository evidence, sourced research, rehearsal findings, and an author self-audit. |
| `plan-rehearsal` | Cold-tests every unit with fresh-context agents using the exact future worker packet, and returns findings for `plan-forge` to integrate. |
| `delegation-graph` | Compiles units into a bounded typed DAG of advisory managers over implementing workers, with explicit ownership, artifacts, review assignment, and safe parallel groups. |
| `routing-plan` | Profiles roles and units and invokes the deterministic router. It never selects models by judgment and never launches workers. |
| `execution-manager` | Acts as an advisory manager: advises its children with bounded information and reviews their submissions. It never edits files, repairs anything itself, or takes over a task. |

## What changed from APS

| APS | Graph Coder |
| --- | --- |
| `aps-plan`, 17 phases | `graph-coder`, 10 phases |
| `idea-grill` producing a Product Contract | `concept-grill` writing into the canonical plan |
| No dedicated research skill | `technical-research` |
| Risk-triggered specialist reviewer swarm | Author self-audit in `plan-forge` |
| Reviewer agents beneath workers | The worker's own manager reviews it |
| `review` nodes in the graph | `manage` nodes; review is a verdict and an artifact |
| Final simulation phase | Absorbed into graph and routing validation |
| Consolidated approval | Full-plan approval bound to four hashes |

## Third-party dependencies

`concept-grill` and `technical-research` orchestrate skills maintained elsewhere
rather than reimplementing them. They invoke the installed skill or declare it as a
dependency; they do not copy prompt bodies, and no third-party file is vendored
without a license review recorded in
`skills/graph-coder/references/third-party-skills.md`.

Preflight runs before concept grilling and before technical research. A missing
required dependency stops the run before approval with an exact installation
message. A missing optional dependency is noted and the run continues. Simulating a
third-party skill and reporting its reliability is prohibited.

## Secret discipline

Before a live model-evidence refresh, `graph-coder` and `routing-plan` verify that
`LLM_STATS_API_KEY` is available without printing it. If it is absent and no
policy-valid cache is sufficient, they ask the user to configure the process
environment or a secret manager. They never request a plaintext key in chat and
never persist one in plans, commands, events, caches, or tracked files.

## Command discipline

The Director uses only the implemented deterministic CLI surface: `init`,
`inspect`, `plan status|validate|snapshot|reconcile`, `graph compile|validate`,
`route refresh|assign|explain`, `event append`, `run status|recover|resume`,
`context build`, `jcode emit`, and `terminal open`.

Commands such as `graph-coder new`, `graph-coder approve`, `graph-coder execute`,
or `graph-coder status` do not exist. Approval is recorded with:

```shell
graph-coder --root <repo> event append --type plan.approved --payload "{}" \
  --role Director --plan-id <plan-id> --repository-commit <commit>
```

A human decision on a blocked branch is recorded with:

```shell
graph-coder --root <repo> run resume --node-id <node> --decision "<what and why>"
```
