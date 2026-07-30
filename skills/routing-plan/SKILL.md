---
name: routing-plan
description: Profile implementation units and invoke the deterministic Graph Coder router without selecting models through LLM judgment or launching workers.
---
# Routing Plan

Bounded authority: translate unit requirements into a versioned task profile and inspect deterministic results. Manager-advisory boundary: the Director owns policy, validated overrides, approval, graph mutation, and worker launch. This skill never launches workers and never makes the final routing choice.

## Procedure

1. Snapshot the canonical plan before routing mutates it.
2. Before a live refresh, check whether `LLM_STATS_API_KEY` is available without printing it. If it is missing and no policy-valid cache is sufficient, ask the user to configure it in the process environment or a secret manager. Never ask for the plaintext value in chat, a command, a plan, an event, or a tracked file.
3. Persist the user's provider, model, subscription, budget, and diversity constraints before scoring candidates. A user deny rule is a hard filter. Never route through an exhausted or excluded provider, and never buy through OpenRouter a model or materially equivalent capability already eligible through the user's direct subscription unless the direct route is unavailable or fails a documented hard requirement.
4. For every `U-` unit, derive hard requirements from evidence: authenticated/configured provider, context/output limits, tools, modalities, streaming, model class, provider/model allow/deny rules, execution environment, per-attempt cost ceiling, minimum evidence confidence/freshness, risk, stack, and complexity.
5. Map task categories to a versioned benchmark-weight vector. Do not choose a model while profiling.
6. Run `aps route refresh`. Record whether evidence is network, cache, or labeled stale cache. Do not claim current data when live validation failed.
7. Run `aps route assign --input <profile> --output <decision>` and `aps route explain --input <profile>`.
8. Attach the selected primary, provider-diverse fallback where possible, source data/hash, benchmark/local values, weights, normalization version, freshness, bounded expected passing cost, eliminations, open-weight preference effect, deterministic tie-breakers, and escalation conditions to the same canonical plan.
9. Add the route's expected and observed spend to the cumulative project ledger for all metered services, not only AI tokens. Refuse a dispatch that would exceed the applicable hard cap.
10. A manual override must still meet hard requirements. Use a force flag only with an explicit recorded warning and Director authority.

## LLM Stats helper

The repository ships a noninteractive helper with this skill:

```text
python skills/routing-plan/scripts/llm_stats.py --help
python skills/routing-plan/scripts/llm_stats.py --cache .graph-coder/cache/llm-stats.json models
python skills/routing-plan/scripts/llm_stats.py model <model-id>
python skills/routing-plan/scripts/llm_stats.py rankings <category>
python skills/routing-plan/scripts/llm_stats.py benchmarks <model-id>
```

It reads `LLM_STATS_API_KEY` only from the environment, emits JSON, bounds retries and timeouts, and labels model-list results as `network`, `cache`, or `stale_cache`. Never print or persist the key. The endpoint mapping remains provisional until a configured live smoke test succeeds.

## Deterministic policy

The router hard-filters first, computes `quality = (0.60 * external_task_score + 0.30 * local_score) / 0.90`, builds the quality/cost/reliability/latency frontier, applies the quality floor, keeps candidates within the configured margin, prefers open-weight candidates inside that set, and chooses lowest bounded expected passing cost. Tie-breakers are evidence confidence, provider reliability, latency, then stable model ID.

Infrastructure failure is not evidence of model inability. Fallbacks meet the same hard requirements and preferably use a different provider. Escalate on verification failure, repeated tool-use failure, context overflow, provider unavailability, raised task risk/capability, or capability-attributable review failure.

## Decision surfaces

Task capability profile, hard versus soft requirement, evidence freshness, benchmark mapping, verified local cohort, quality floor, cost ceiling, open-weight preference, fallback diversity, and escalation threshold.

## Evidence rules

Use persisted LLM Stats source records and independently verified local outcomes only. Never store `LLM_STATS_API_KEY`. Record actual model/provider receipts where available. Mark the installed JCode endpoint shape provisional until a live configured smoke test succeeds. Record every user exclusion, direct-subscription candidate, OpenRouter duplicate elimination, fallback activation reason, and cumulative all-service cost check.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, unit_id: U-id, evidence: [string], routing_consequence: string, proposed_resolution: string}
rehearsal_schema: {unit_id: U-id, profile_complete: boolean, hard_requirements_satisfied: boolean, stale_evidence: boolean}
task_schema: {task_id: U-id, required_tools: [string], min_context_tokens: int, risk: string, benchmark_weights: object, cost_ceiling: number}
report_schema: {unit_id: U-id, selected: string, fallback: string|null, eliminations: [object], freshness: string, expected_passing_cost: number, escalation_conditions: [string]}
```

## STOP/escalation rules

Stop when no model meets hard requirements, the evidence confidence floor fails, credentials are unavailable with no valid cache, a requested override violates policy without force authority, the task profile is incomplete, or routing would silently use an unapproved planning model.
