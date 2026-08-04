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
6. **Refresh the model evidence before every routing pass.** Run `graph-coder route refresh` and record whether the result is `network`, `cache`, or `stale_cache`. Never claim current data when the live fetch failed.
7. Run `graph-coder route assign --from-cache --input <profile> --output <decision>` and `graph-coder route explain --from-cache --input <profile>`.

## Freshness is mandatory

Routing decides how the user's money is spent. Doing that on a week-old price table is worse than stopping to ask.

```text
graph-coder route refresh
graph-coder route assign --from-cache --input <profile> --max-age-hours 24
```

`--from-cache` builds the model registry from the cached LLM Stats records instead of a hand-written `models` array, and refuses to run when the evidence is older than `--max-age-hours` (default 24) or when the client already flagged the cache stale. The refusal names the fix. Do not work around it by hand-assembling a profile: that is how a stale price silently becomes a routing decision.

Every decision carries a `registry` report with the evidence age, the number of routes built, and the cost assumptions used. Attach it to the plan alongside the route receipt.

### Two limits to state, not hide

- **The API reports no context window.** Every model returned on 2026-07-30 had `context_window: null`. A unit that declares `min_context_tokens` will therefore eliminate every candidate. Supply `registry.context_window_overrides` with values you have actually verified, and say where they came from. Never invent one.
- **Per-attempt cost is derived.** The API publishes `input_price_per_m` and `output_price_per_m`; converting those into a per-attempt cost requires assuming the tokens an attempt spends. Those assumptions are inputs (`registry.input_tokens_per_attempt`, `registry.output_tokens_per_attempt`) and appear in the report. Present the resulting cost as an estimate.
8. Attach the receipt to the same canonical plan, in section 11.
9. Add expected and observed spend to the cumulative project ledger for all metered services, not only model tokens. Refuse a dispatch that would exceed the applicable hard cap.
10. A manual override must still meet hard requirements. Use a force flag only with an explicit recorded warning and Director authority.

## When the evidence source is unavailable

LLM Stats can be down, unreachable, or reject the key. `HTTP 401` and `HTTP 403` mean the key is invalid, expired, or lacks access rather than missing, and the client now quotes the API's own message and the remedy. Fix the key first: regenerate it at `https://llm-stats.com/settings?tab=api-keys` and export it into the process environment. Auth failures on this API can take about 25 seconds to return, so a request that seems to hang is usually about to tell you something useful.

If it is genuinely unavailable and no policy-valid cache exists, you may route from the harness's own model list (`swarm list_models` in JCode) instead of stopping. This is a degraded path, not an equivalent one, and it is only legitimate when it is declared:

```text
routing_evidence: harness_model_list
benchmark_scores: unavailable
selection_basis: availability, price, and context limits only
confidence: low
```

Under this path the quality term has no input, so the router cannot rank on capability. Choose on the hard filters and price alone, record every candidate the harness listed, and name the model you took and why. Then surface it at full-plan approval as an explicit degradation, because the user is approving a cost estimate built on weaker evidence than the plan format implies.

What makes this a failure is doing it silently. A run that hit `403`, hand-picked a cheap model, and carried on left no receipt, no candidate list, and no signal that the plan's cost figures rested on a guess. Declaring the degradation costs one paragraph and keeps the plan honest.

Recover as soon as the source returns: refresh, re-assign, and record that the routes changed.

## Subscription-first eligibility

Subscription-first is enforced by the router, not by prose. Never buy through a reseller a model, or a materially equivalent capability, that is already eligible through the user's direct subscription, unless the direct route is unavailable or fails a documented hard requirement.

The preference applies only among candidates that already cleared the hard filters. It is a tie-breaker on cost, never a licence to route through a model that cannot do the job.

Never route through an exhausted or excluded provider.

## Deterministic policy

The router hard-filters first, then computes:

```text
quality = (0.60 * external_task_score + 0.30 * local_verified_score) / 0.90
```

`external_task_score` is a weighted mean over `benchmark_weights`. The scores it averages are normalized per category by the registry, because LLM Stats categories do not share a scale: `code` and `tool_calling` arrive in 0..1 while `reasoning` and `finance` arrive in the hundreds. You do not normalize anything yourself, and you must not rescale a weight to compensate for a category you believe reads high.

Weight the categories the unit's work actually depends on. Naming a category the data does not carry is not an error and will not stop the route: it contributes zero to the numerator and its full weight to the denominator, so it silently drags every candidate down. Read `benchmark_coverage` and `unscored_benchmark_weights` in the receipt before accepting an assignment. Coverage below 1.0 means part of your weight vector scored nothing.

Two registry warnings change what a score is worth, and both belong in the routing section of the plan when they appear:

- `benchmark_warning` names categories that rank nothing, because fewer than two models report them or every model scored alike. Weighting one contributes a flat neutral value to every candidate, so it cannot break a tie and should not be presented as evidence.
- `benchmark_mixed_unit_warning` names categories whose own values span more than 50x, which is more than one benchmark produces. A model scoring low in such a category may be measured on a different benchmark rather than being worse. Do not let a single mixed-unit category decide a route.

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
score_inputs: {weights, normalization_version, external_score, local_score,
               benchmark_coverage, unscored_benchmark_weights}
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

It reads `LLM_STATS_API_KEY` only from the environment, emits JSON, bounds retries and timeouts, and labels results as `network`, `cache`, or `stale_cache`. Never print or persist the key.

The API is served by ZeroEval at `https://api.zeroeval.com/stats/v1`, verified live on 2026-07-30 against `GET /stats/v1/models` returning `{models, next_cursor, total}` for 335 models. Pagination is by opaque cursor. The endpoint sits behind Cloudflare, which rejects a default urllib User-Agent with error 1010, so the client sends a conventional one.

## Decision surfaces

Role category, task capability profile, hard versus soft requirement, evidence freshness, benchmark mapping, verified local cohort, quality floor, cost ceiling, subscription eligibility, open-weight preference, fallback diversity, and escalation threshold.

## Evidence rules

Use persisted LLM Stats source records and independently verified local outcomes only. Never store `LLM_STATS_API_KEY`. Record actual model and provider receipts where the harness exposes them. Record the evidence age and source label on every routing pass, and every user exclusion, direct-subscription candidate, reseller duplicate elimination, fallback activation reason, and cumulative all-service cost check. State derived costs and any supplied context-window override as what they are.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, node_id: string, unit_id: IU-id, evidence: [string], routing_consequence: string, proposed_resolution: string}
rehearsal_schema: {node_id: string, profile_complete: boolean, hard_requirements_satisfied: boolean, stale_evidence: boolean, receipt_emitted: boolean}
task_schema: {node_id: string, role: string, required_tools: [string], min_context_tokens: int, max_output_tokens: int, risk: string, benchmark_weights: object, cost_ceiling: number, provider_allow: [string], provider_deny: [string]}
report_schema: {node_id: string, role: string, selected: string, fallback: string|null, eliminations: [object], freshness: string, expected_passing_cost: number, subscription_first_applied: boolean, escalation_conditions: [string]}
```

## STOP/escalation rules

Stop when: no model meets a node's hard requirements; the evidence confidence floor fails; credentials are unavailable with no valid cache; a requested override violates policy without force authority; the task profile is incomplete; routing would silently substitute the Director's pinned model; or an assignment would be made without a receipt.
