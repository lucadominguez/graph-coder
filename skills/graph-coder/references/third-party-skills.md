# Third-party skill dependencies

Graph Coder orchestrates third-party skills. It does not copy their prompt bodies.
Reuse means invoking the installed skill at runtime, or declaring it as a documented
dependency. Vendoring another project's prompt text into this repository is out of
scope, and none of it is permitted without a license review recorded here.

Verified on 2026-07-30 against a Windows 11 workstation with both Claude Code and
Codex plugin caches present. Re-verify before relying on any row: plugin trigger
names and paths change between versions.

## Concept grilling

| Field | Value |
| --- | --- |
| Role | Default dependency |
| Trigger | `ce-brainstorm` |
| Project | Compound Engineering |
| Repository | `compound-engineering-plugin` (marketplace plugin `compound-engineering`) |
| Version verified | 3.20.0 |
| License | MIT, Copyright (c) 2025 Every |
| Observed path | `~/.codex/plugins/cache/compound-engineering-plugin/compound-engineering/3.20.0/skills/ce-brainstorm` |
| Status | Installed for Codex; **not** present in `~/.claude/skills` |
| Purpose | Adversarial concept development before any plan exists |

| Field | Value |
| --- | --- |
| Role | Optional dependency |
| Trigger | `office-hours` |
| Project | gstack |
| License | Not reviewed; the skill was not installed at verification time |
| Observed path | Not found |
| Status | **Absent** |
| Purpose | Product viability, user value, positioning, and startup strategy |
| Condition | Invoke only when product viability is materially uncertain. Never by default. |

| Field | Value |
| --- | --- |
| Role | Fallback only, with disclosure |
| Trigger | `superpowers:brainstorming` |
| Project | Superpowers |
| Version verified | 6.2.0 (`openai-curated-remote`) |
| License | MIT, Copyright (c) 2025 Jesse Vincent |
| Observed path | `~/.codex/plugins/cache/openai-curated-remote/superpowers/6.2.0/skills/brainstorming` |
| Status | Installed for Codex; **not** present in `~/.claude/skills` |
| Purpose | Degraded-mode concept grilling |

Exactly one primary workflow runs, plus at most one conditional supplemental
workflow. Do not run all three by default.

## Technical research

Use the research capabilities Compound Engineering already maintains, when the
installed dependency exposes them. At version 3.20.0 these are prompt assets under
`skills/ce-plan/agents/`:

| Capability | Asset | Dispatch when |
| --- | --- | --- |
| Repository research | `repo-research-analyst.md` | The question is about this codebase |
| Learnings research | `learnings-researcher.md` | Prior project decisions may already answer it |
| Framework documentation | `framework-docs-researcher.md` | The question is version-sensitive or API-shaped |
| Best practices | `best-practices-researcher.md` | The question is about approach, not fact |
| Web research | `web-researcher.md` | The answer is outside the repository and outside official docs |
| Specification flow | `spec-flow-analyzer.md` | The question is about end-to-end behavior across components |

Dispatch is driven by the research-question inventory, never by a fixed swarm. A
repository-only question must not trigger web research. A version-sensitive
framework question must trigger official documentation research.

## Preflight

Run before `CONCEPT_GRILL` and before `TECHNICAL_RESEARCH`.

1. Resolve each required trigger in the harness actually running Graph Coder.
   Presence in a different harness's cache does not count.
2. If the default concept dependency is missing, stop before plan approval and
   give the user the exact installation step. Do not proceed into a simulated
   equivalent.
3. If only the fallback is available, disclose the degradation, name what is
   weaker about it, and continue only with the user's explicit acceptance.
4. If an optional dependency is missing, note it and continue. Absence of an
   optional skill is not a blocker.
5. Record the resolved trigger, version, and harness in the plan's
   `Sources and Evidence` section, and append a `dependency.preflight` event.

## Installation

These are plugin marketplace installs, not files to copy:

```text
# Compound Engineering (required for concept grilling and research assets)
/plugin marketplace add compound-engineering-plugin
/plugin install compound-engineering

# Superpowers (fallback concept grilling only)
/plugin install superpowers
```

If a required dependency cannot be installed, say so plainly and stop. Never
report a concept or research phase as complete when its dependency was absent.
