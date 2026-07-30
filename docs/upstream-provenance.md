# Upstream provenance

Graph Coder is an independent repository. It is not a fork or a branch of the
Agent Planning System (APS). This document records the exact APS commit that was
studied and the origin of every substantially ported file.

| Field | Value |
| --- | --- |
| Upstream repository | `https://github.com/lucadominguez/agent-planning-system` |
| Pinned commit | `f4c28164062432140d7f7620ffdac56ce0a442c5` |
| Upstream license | MIT (reproduced in `NOTICE`) |
| Inspected at | 2026-07-30 |
| Files considered | 95 |

The pinned commit is authoritative and lives in `upstream/aps.lock.json`.
`scripts/check_aps_upstream.py` reports drift against APS `main` without importing
anything; see `docs/importing-from-aps.md` for the artifact-level import path.

## Classification

- `ported`: copied without semantic change.
- `adapted`: copied then renamed or reshaped for Graph Coder.
- `rewritten`: reimplemented against the Graph Coder contract.
- `new`: no APS counterpart.

## File map

| Graph Coder file | APS source | Classification |
| --- | --- | --- |
| `.env.example` | `.env.example` | ported |
| `.gitignore` | `.gitignore` | ported |
| `LICENSE` | `LICENSE` | adapted |
| `README.md` | `README.md` | adapted |
| `docs/architecture.md` | `docs/architecture.md` | adapted |
| `docs/design-contract.md` | `docs/design-contract.md` | adapted |
| `docs/installation.md` | `docs/installation.md` | adapted |
| `docs/skills.md` | `docs/skills.md` | adapted |
| `docs/sources/agent-skills-conventions.md` | `docs/sources/agent-skills-conventions.md` | ported |
| `docs/superpowers/operator-terminal.md` | `docs/superpowers/operator-terminal.md` | adapted |
| `pyproject.toml` | `pyproject.toml` | adapted |
| `schemas/import/aps-v1/base-artifact.schema.json` | `schemas/base-artifact.schema.json` | ported |
| `schemas/import/aps-v1/event.schema.json` | `schemas/event.schema.json` | ported |
| `schemas/import/aps-v1/graph.schema.json` | `schemas/graph.schema.json` | ported |
| `schemas/import/aps-v1/manager_advice.schema.json` | `schemas/manager_advice.schema.json` | ported |
| `schemas/import/aps-v1/plan.schema.json` | `schemas/plan.schema.json` | ported |
| `schemas/import/aps-v1/review_defect.schema.json` | `schemas/review_defect.schema.json` | ported |
| `schemas/import/aps-v1/task_packet.schema.json` | `schemas/task_packet.schema.json` | ported |
| `schemas/import/aps-v1/worker_report.schema.json` | `schemas/worker_report.schema.json` | ported |
| `schemas/v1/base-artifact.schema.json` | `schemas/base-artifact.schema.json` | adapted |
| `schemas/v1/event.schema.json` | `schemas/event.schema.json` | adapted |
| `schemas/v1/graph.schema.json` | `schemas/graph.schema.json` | adapted |
| `schemas/v1/manager_advice.schema.json` | `schemas/manager_advice.schema.json` | adapted |
| `schemas/v1/plan.schema.json` | `schemas/plan.schema.json` | adapted |
| `schemas/v1/review_defect.schema.json` | `schemas/review_defect.schema.json` | adapted |
| `schemas/v1/task_packet.schema.json` | `schemas/task_packet.schema.json` | adapted |
| `schemas/v1/worker_report.schema.json` | `schemas/worker_report.schema.json` | adapted |
| `scripts/graph-coder-terminal-helper.ps1` | `scripts/aps-terminal-helper.ps1` | ported |
| `scripts/graph-coder-terminal-helper.sh` | `scripts/aps-terminal-helper.sh` | ported |
| `scripts/install.ps1` | `scripts/install.ps1` | adapted |
| `scripts/install.sh` | `scripts/install.sh` | adapted |
| `skills/delegation-graph/SKILL.md` | `skills/delegation-graph/SKILL.md` | ported |
| `skills/execution-manager/SKILL.md` | `skills/execution-manager/SKILL.md` | adapted |
| `skills/plan-forge/SKILL.md` | `skills/plan-forge/SKILL.md` | adapted |
| `skills/plan-rehearsal/SKILL.md` | `skills/plan-rehearsal/SKILL.md` | ported |
| `skills/routing-plan/SKILL.md` | `skills/routing-plan/SKILL.md` | adapted |
| `skills/routing-plan/scripts/llm_stats.py` | `skills/routing-plan/scripts/llm_stats.py` | adapted |
| `src/graph_coder/__init__.py` | `src/agent_planning_system/__init__.py` | adapted |
| `src/graph_coder/__main__.py` | `src/agent_planning_system/__main__.py` | adapted |
| `src/graph_coder/adapters/__init__.py` | `src/agent_planning_system/adapters/__init__.py` | adapted |
| `src/graph_coder/adapters/jcode.py` | `src/agent_planning_system/adapters/jcode.py` | adapted |
| `src/graph_coder/cli.py` | `src/agent_planning_system/cli.py` | adapted |
| `src/graph_coder/config.py` | `src/agent_planning_system/config.py` | adapted |
| `src/graph_coder/context.py` | `src/agent_planning_system/context.py` | ported |
| `src/graph_coder/contracts.py` | `src/agent_planning_system/contracts.py` | adapted |
| `src/graph_coder/db.py` | `src/agent_planning_system/db.py` | adapted |
| `src/graph_coder/errors.py` | `src/agent_planning_system/errors.py` | adapted |
| `src/graph_coder/events.py` | `src/agent_planning_system/events.py` | adapted |
| `src/graph_coder/graph.py` | `src/agent_planning_system/graph.py` | adapted |
| `src/graph_coder/llm_stats.py` | `src/agent_planning_system/llm_stats.py` | ported |
| `src/graph_coder/plans.py` | `src/agent_planning_system/plans.py` | adapted |
| `src/graph_coder/py.typed` | `src/agent_planning_system/py.typed` | ported |
| `src/graph_coder/recovery.py` | `src/agent_planning_system/recovery.py` | ported |
| `src/graph_coder/redaction.py` | `src/agent_planning_system/redaction.py` | ported |
| `src/graph_coder/routing.py` | `src/agent_planning_system/routing.py` | adapted |
| `src/graph_coder/terminal.py` | `src/agent_planning_system/terminal.py` | adapted |
| `tests/fixtures/contracts/invalid/plan_bad_contract.json` | `tests/fixtures/contracts/invalid/plan_bad_contract.json` | ported |
| `tests/fixtures/contracts/valid/plan.json` | `tests/fixtures/contracts/valid/plan.json` | adapted |
| `tests/fixtures/jcode/version.txt` | `tests/fixtures/jcode/version.txt` | ported |
| `tests/fixtures/plans/invalid_plan.md` | `tests/fixtures/plans/invalid_plan.md` | ported |
| `tests/fixtures/plans/valid_plan.md` | `tests/fixtures/plans/valid_plan.md` | adapted |
| `tests/fixtures/routing/cli_input.json` | `tests/fixtures/routing/cli_input.json` | ported |
| `tests/fixtures/routing/golden.json` | `tests/fixtures/routing/golden.json` | ported |
| `tests/pressure/README.md` | `tests/pressure/README.md` | adapted |
| `tests/pressure/ambiguous_product_intent.json` | `tests/pressure/ambiguous_product_intent.json` | adapted |
| `tests/pressure/approval_after_material_revision.json` | `tests/pressure/approval_after_material_revision.json` | adapted |
| `tests/pressure/built_in_plan_shadowing.json` | `tests/pressure/built_in_plan_shadowing.json` | adapted |
| `tests/pressure/cycle_in_delegation_graph.json` | `tests/pressure/cycle_in_delegation_graph.json` | adapted |
| `tests/pressure/destructive_migration_request.json` | `tests/pressure/destructive_migration_request.json` | adapted |
| `tests/pressure/excluded_provider_and_duplicate_route.json` | `tests/pressure/excluded_provider_and_duplicate_route.json` | adapted |
| `tests/pressure/manager_attempts_to_execute.json` | `tests/pressure/manager_attempts_to_execute.json` | adapted |
| `tests/pressure/missing_acceptance_checks.json` | `tests/pressure/missing_acceptance_checks.json` | adapted |
| `tests/pressure/parallel_file_conflict.json` | `tests/pressure/parallel_file_conflict.json` | adapted |
| `tests/pressure/reload_with_unknown_workers.json` | `tests/pressure/reload_with_unknown_workers.json` | adapted |
| `tests/pressure/resume_after_partial_failure.json` | `tests/pressure/resume_after_partial_failure.json` | adapted |
| `tests/pressure/route_requires_external_capability.json` | `tests/pressure/route_requires_external_capability.json` | adapted |
| `tests/pressure/secret_handling_pressure.json` | `tests/pressure/secret_handling_pressure.json` | adapted |
| `tests/pressure/sidepanel_over_30_workers.json` | `tests/pressure/sidepanel_over_30_workers.json` | adapted |
| `tests/pressure/truncated_rehearsal_report.json` | `tests/pressure/truncated_rehearsal_report.json` | adapted |
| `tests/pressure/windows_terminal_no_komorebi.json` | `tests/pressure/windows_terminal_no_komorebi.json` | adapted |
| `tests/test_cli.py` | `tests/test_cli.py` | adapted |
| `tests/test_config.py` | `tests/test_config.py` | adapted |
| `tests/test_context.py` | `tests/test_context.py` | adapted |
| `tests/test_contracts.py` | `tests/test_contracts.py` | adapted |
| `tests/test_db.py` | `tests/test_db.py` | adapted |
| `tests/test_events.py` | `tests/test_events.py` | adapted |
| `tests/test_graph.py` | `tests/test_graph.py` | adapted |
| `tests/test_installers.py` | `tests/test_installers.py` | adapted |
| `tests/test_jcode_adapter.py` | `tests/test_jcode_adapter.py` | adapted |
| `tests/test_llm_stats.py` | `tests/test_llm_stats.py` | adapted |
| `tests/test_plans.py` | `tests/test_plans.py` | adapted |
| `tests/test_recovery.py` | `tests/test_recovery.py` | adapted |
| `tests/test_redaction.py` | `tests/test_redaction.py` | adapted |
| `tests/test_routing.py` | `tests/test_routing.py` | adapted |
| `tests/test_session_reliability.py` | `tests/test_session_reliability.py` | ported |
| `tests/test_skill_contracts.py` | `tests/test_skill_contracts.py` | ported |
| `tests/test_terminal.py` | `tests/test_terminal.py` | adapted |

## Files with no APS counterpart

Everything not listed above is `new`: written for Graph Coder and owned by this
repository. That includes the `graph-coder/v1` contracts, the manager review and
context artifacts, the APS importer, the upstream-awareness checker, and all eight
active skills.
