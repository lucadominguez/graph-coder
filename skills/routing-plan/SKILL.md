---
name: routing-plan
description: Profile each role and unit, then invoke the deterministic Graph Coder router to assign primary and fallback models by expected passing cost without selecting models through judgment.
---
# Routing Plan

Bounded authority: translate role and unit requirements into a versioned task profile and inspect deterministic results. Manager-advisory boundary: the Director owns policy, validated overrides, approval, graph mutation, and worker launch. This skill never launches workers and never makes the final routing choice by judgment.

Routing is deterministic. The same registry and the same unit always produce the same route. If a route changes, either the registry moved or the unit did, and the receipt says which.

## Role categories

| Role | Routed for | Rule |
| --- | --- | --- |
| Director | Frontier planning, direction, review of top-level outputs | Pinned to the configured frontier model. Never silently downgraded. |
| Manager | Advice quality, review judgment, context window, tools | Must meet review and context requirements for its whole subtree. |
| Worker | Lowest expected cost of a passing result | Cheapest route that clears the unit's hard requirements and quality floor. |
| Research | Evidence retrieval, source handling, long context | Must meet the freshness and context needs of its questions. |
| Cold rehearsal | Fresh-context reasoning over a packet | Must be capable enough that its findings mean something. |

There is no standalone reviewer route category, because there are no standalone reviewers. A manager's review runs on the manager's route.

Downgrading the Director to save money defeats the design: the frontier model's job is to make the expensive decisions once so that cheap models can execute many times.

## Procedure

1. Snapshot the canonical plan before routing mutates it.
2. Before a live refresh, check whether `LLM_STATS_API_KEY` is available without printing it. If it is missing and no policy-valid cache is sufficient, ask the user to configure it in the process environment or a secret manager. Never ask for the plaintext value in chat, a command, a plan, an event, or a tracked file.
3. Persist the user's provider, model, subscription, budget, and diversity constraints before scoring candidates. A user deny rule is a hard filter.
4. For every node, derive hard requirements from evidence: authenticated and configured provider, context and output limits, tools, modalities, streaming, model class, provider and model allow and deny rules, execution environment, per-attempt cost ceiling, minimum evidence confidence and freshness, risk, stack, and complexity.
5. Map task categories to a versioned benchmark-weight vector. Do not choose a model while profiling.
6. Run `graph-coder route refresh`. Record whether the evidence is network, cache, or labeled stale cache. Do not claim current data when live validation failed.
7. Run `graph-coder route assign --input <profile> --output <decision>` and `graph-coder route explain --input <profile>`.
8. Attach the receipt to the same canonical plan, in section 11.
9. Add expected and observed spend to the cumulative project ledger for all metered services, not only model tokens. Refuse a dispatch that would exceed the applicable hard cap.
10. A manual override must still meet hard requirements. Use a force flag only with an explicit recorded warning and Director authority.

## Subscription-first eligibility

Subscription-first is enforced by the router, not by prose. Never buy through a reseller a model, or a materially equivalent capability, that is already eligible through the user's direct subscription, unless the direct route is unavailable or fails a documented hard requirement.

The preference applies only among candidates that already cleared the hard filters. It is a tie-breaker on cost, never a licence to route through a model that cannot do the job.

Never route through an exhausted or excluded provider.

## Deterministic policy

The router hard-filters first, then computes:

```text
quality = (0.60 * external_task_score + 0.30 * local_verified_score) / 0.90
```

It builds the quality, cost, reliability, and latency frontier; applies the quality floor; keeps candidates within the configured margin of the best; prefers open-weight candidates inside that set when the preference is enabled; and selects the lowest bounded expected passing cost.

```text
expected_passing_cost =
    attempt_cost
    + probability_of_repair * repair_cost
    + probability_of_escalation * escalation_cost
```

These probabilities come from configured estimates and observed local history. State them as estimates. Do not claim precision the registry data does not support.

Tie-breakers, in order: evidence confidence, provider reliability, latency, then stable model ID.

## Cost model

Sticker price per token is the wrong optimization target. Output and reasoning tokens cost far more than input, and cached input costs far less again. In practice a cheap model that fails once and escalates costs more than a capable model that passes first time, because the failure pays for its context twice, its output twice, and a manager review it did not need.

Optimize, in order: failed and repeated attempts; unnecessary model elevation; excessive frontier output; repeated uncached context.

## Route receipt

Every assignment emits one:

```yaml
node_id: string
role: director | manager | worker | research | rehearsal
considered_routes: [{model, provider, quality, attempt_cost, expected_passing_cost}]
disqualifications: [{model, reason}]
score_inputs: {weights, normalization_version, external_score, local_score}
chosen_route: {model, provider, expected_passing_cost}
fallback_route: {model, provider} | null
subscription_first_applied: boolean
open_weight_preference_effect: string
registry_timestamp: iso8601
evidence_freshness: network | cache | stale_cache
tie_breakers_used: [string]
escalation_conditions: [string]
```

A route with no receipt is not an assignment; it is a guess.

Infrastructure failure is not evidence of model inability. Fallbacks meet the same hard requirements and preferably use a different provider. Escalate on verification failure, repeated tool-use failure, context overflow, provider unavailability, raised task risk or capability, or a review failure attributable to capability.

## Metrics

Record per run, so the cost design is measurable rather than asserted:

```text
frontier planning and advice cost
manager cost
worker cost
input and context tokens by role
first-pass worker acceptance rate
repairs per accepted unit
human-escalation rate
total cost per accepted implementation unit
```

## LLM Stats helper

```text
python skills/routing-plan/scripts/llm_stats.py --help
python skills/routing-plan/scripts/llm_stats.py --cache .graph-coder/cache/llm-stats.json models
python skills/routing-plan/scripts/llm_stats.py model <model-id>
python skills/routing-plan/scripts/llm_stats.py rankings <category>
python skills/routing-plan/scripts/llm_stats.py benchmarks <model-id>
```

It reads `LLM_STATS_API_KEY` only from the environment, emits JSON, bounds retries and timeouts, and labels results as `network`, `cache`, or `stale_cache`. Never print or persist the key. The endpoint mapping remains provisional until a configured live smoke test succeeds.

## Decision surfaces

Role category, task capability profile, hard versus soft requirement, evidence freshness, benchmark mapping, verified local cohort, quality floor, cost ceiling, subscription eligibility, open-weight preference, fallback diversity, and escalation threshold.

## Evidence rules

Use persisted LLM Stats source records and independently verified local outcomes only. Never store `LLM_STATS_API_KEY`. Record actual model and provider receipts where the harness exposes them. Mark the installed harness endpoint shape provisional until a live configured smoke test succeeds. Record every user exclusion, direct-subscription candidate, reseller duplicate elimination, fallback activation reason, and cumulative all-service cost check.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, node_id: string, unit_id: IU-id, evidence: [string], routing_consequence: string, proposed_resolution: string}
rehearsal_schema: {node_id: string, profile_complete: boolean, hard_requirements_satisfied: boolean, stale_evidence: boolean, receipt_emitted: boolean}
task_schema: {node_id: string, role: string, required_tools: [string], min_context_tokens: int, max_output_tokens: int, risk: string, benchmark_weights: object, cost_ceiling: number, provider_allow: [string], provider_deny: [string]}
report_schema: {node_id: string, role: string, selected: string, fallback: string|null, eliminations: [object], freshness: string, expected_passing_cost: number, subscription_first_applied: boolean, escalation_conditions: [string]}
```

## STOP/escalation rules

Stop when: no model meets a node's hard requirements; the evidence confidence floor fails; credentials are unavailable with no valid cache; a requested override violates policy without force authority; the task profile is incomplete; routing would silently substitute the Director's pinned model; or an assignment would be made without a receipt.
