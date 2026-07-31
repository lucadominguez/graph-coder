"""Deterministic model routing for Graph Coder.

Routing is a pure function of the registry and the unit: the same inputs always
produce the same route, and every assignment can emit a receipt explaining why.

Two policies live here rather than in skill prose, because prose cannot enforce
them. Subscription-first precedence decides between an eligible direct route and
a paid reseller route. Role categories pin the Director to its configured
frontier model so a cost heuristic can never quietly downgrade it.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from .errors import RoutingError

RouteRole = Literal["director", "manager", "worker", "research", "rehearsal"]

ROUTE_ROLES: frozenset[str] = frozenset({"director", "manager", "worker", "research", "rehearsal"})

NORMALIZATION_VERSION = "graph-coder/routing/v1"

# Provider classes, in subscription-first precedence order. A reseller route is
# only reached when no eligible direct or zero-marginal-cost route exists.
DIRECT_SUBSCRIPTION_CLASSES: frozenset[str] = frozenset({"direct_oauth"})
RESELLER_CLASSES: frozenset[str] = frozenset({"reseller"})


@dataclass(frozen=True)
class TaskRequirements:
    task_id: str
    role: RouteRole = "worker"
    pinned_model_id: str | None = None
    subscription_first: bool = False
    equivalence_class: str | None = None
    repair_cost_factor: float = 0.0
    escalation_cost: float = 0.0
    requires_auth: bool = True
    required_configuration: frozenset[str] = frozenset()
    min_context_tokens: int = 0
    min_output_tokens: int = 0
    required_tools: frozenset[str] = frozenset()
    required_modalities: frozenset[str] = frozenset()
    require_streaming: bool = False
    allowed_model_classes: frozenset[str] = frozenset()
    required_policies: frozenset[str] = frozenset()
    environment: str = "production"
    max_per_attempt_cost: float = math.inf
    min_confidence: float = 0.0
    quality_floor: float = 0.0
    prefer_open_weight: bool = False
    benchmark_weights: dict[str, float] = field(default_factory=dict)
    benchmark_version: str = "v1"
    max_attempts: int = 2
    allowed_provider_ids: frozenset[str] = frozenset()
    denied_provider_ids: frozenset[str] = frozenset()
    allowed_model_ids: frozenset[str] = frozenset()
    denied_model_ids: frozenset[str] = frozenset()
    max_evidence_age_hours: float = math.inf
    manual_override_model_id: str | None = None
    force_override: bool = False

    def __post_init__(self) -> None:
        # Widened deliberately. RouteRole is a Literal, but this object is built
        # from JSON payloads, so at runtime `role` is whatever the caller wrote.
        # Comparing the declared type against "reviewer" reads as unreachable to
        # a type checker; the check exists precisely because it is not.
        role: str = self.role
        if role not in ROUTE_ROLES:
            if role == "reviewer":
                raise RoutingError(
                    "there is no standalone reviewer route category: a worker's review "
                    "runs on its manager's route"
                )
            raise RoutingError(
                f"unknown route role {role!r}; expected one of {sorted(ROUTE_ROLES)}"
            )


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_id: str
    authenticated: bool
    configured: frozenset[str] = frozenset()
    reliability: float = 0.0
    environments: frozenset[str] = frozenset({"production"})
    provider_class: str = "direct_api"


@dataclass(frozen=True)
class ModelCapabilities:
    model_id: str
    provider_id: str
    context_tokens: int
    output_tokens: int
    tools: frozenset[str] = frozenset()
    modalities: frozenset[str] = frozenset({"text"})
    streaming: bool = False
    model_class: str = "general"
    policies: frozenset[str] = frozenset()
    per_attempt_cost: float = 0.0
    confidence: float = 0.0
    latency_ms: float = math.inf
    open_weight: bool = False
    benchmarks: dict[str, float] = field(default_factory=dict)
    evidence_age_hours: float = 0.0
    zero_marginal_cost: bool = False
    equivalence_class: str | None = None


@dataclass(frozen=True)
class VerifiedHistory:
    model_id: str
    successes: float = 0.0
    attempts: float = 0.0
    recency: float = 1.0


@dataclass(frozen=True)
class CandidateScore:
    model: ModelCapabilities
    provider: ProviderCapabilities
    external_score: float
    local_score: float
    quality: float
    expected_passing_cost: float
    fallback_model_id: str | None
    explanation: dict[str, Any]


@dataclass(frozen=True)
class RoutingDecision:
    selected: CandidateScore | None
    candidates: list[CandidateScore]
    eliminations: list[dict[str, Any]]
    explanation: dict[str, Any]
    scored: list[CandidateScore] = field(default_factory=list)
    """Every candidate that cleared the hard filters, before frontier pruning.

    Receipts report what was considered, not only what survived.
    """


def route_model(
    task: TaskRequirements,
    models: list[ModelCapabilities],
    providers: list[ProviderCapabilities],
    history: list[VerifiedHistory] | None = None,
    *,
    local_prior_successes: float = 1.0,
    local_prior_attempts: float = 2.0,
    external_weight: float = 0.60,
    local_weight: float = 0.30,
    retain_within_best: float = 0.05,
    fallback_failure_weight: float = 1.0,
) -> RoutingDecision:
    provider_by_id = {provider.provider_id: provider for provider in providers}
    history_by_model = {item.model_id: item for item in history or []}
    eliminations: list[dict[str, Any]] = []
    passed: list[tuple[ModelCapabilities, ProviderCapabilities]] = []

    if task.role == "director":
        return _route_pinned_director(
            task,
            models,
            provider_by_id,
            history_by_model,
            local_prior_successes,
            local_prior_attempts,
            external_weight,
            local_weight,
            fallback_failure_weight,
        )

    for model in sorted(models, key=lambda item: item.model_id):
        provider = provider_by_id.get(model.provider_id)
        reasons = _hard_filter_reasons(task, model, provider)
        if reasons:
            eliminations.append(
                {"model_id": model.model_id, "provider_id": model.provider_id, "reasons": reasons}
            )
        elif provider is not None:
            passed.append((model, provider))

    raw_scores = [
        _score_candidate(
            task,
            model,
            provider,
            history_by_model.get(model.model_id),
            local_prior_successes,
            local_prior_attempts,
            external_weight,
            local_weight,
        )
        for model, provider in passed
    ]
    if task.manual_override_model_id:
        override_model = next(
            (model for model in models if model.model_id == task.manual_override_model_id),
            None,
        )
        override_provider = (
            provider_by_id.get(override_model.provider_id) if override_model else None
        )
        override_reasons = (
            _hard_filter_reasons(task, override_model, override_provider)
            if override_model
            else ["manual override: model not found"]
        )
        if override_model and override_provider and (not override_reasons or task.force_override):
            override_score = _score_candidate(
                task,
                override_model,
                override_provider,
                history_by_model.get(override_model.model_id),
                local_prior_successes,
                local_prior_attempts,
                external_weight,
                local_weight,
            )
            fallback_pool = [
                score for score in raw_scores if score.model.model_id != override_model.model_id
            ]
            selected_override = _attach_fallback(
                override_score,
                [override_score, *fallback_pool],
                fallback_failure_weight,
                task.max_attempts,
            )
            return RoutingDecision(
                selected=selected_override,
                candidates=[selected_override],
                eliminations=sorted(
                    eliminations, key=lambda item: (item["model_id"], item["reasons"])
                ),
                explanation={
                    "task_id": task.task_id,
                    "benchmark_version": task.benchmark_version,
                    "quality_formula": "(0.60*external+0.30*local)/0.90",
                    "manual_override_model_id": task.manual_override_model_id,
                    "manual_override_forced": task.force_override,
                    "manual_override_warnings": override_reasons,
                    "selected_model_id": selected_override.model.model_id,
                },
            )
        return RoutingDecision(
            selected=None,
            candidates=[],
            eliminations=sorted(eliminations, key=lambda item: (item["model_id"], item["reasons"])),
            explanation={
                "task_id": task.task_id,
                "manual_override_model_id": task.manual_override_model_id,
                "manual_override_forced": task.force_override,
                "manual_override_rejected": override_reasons,
            },
        )
    quality_filtered = [score for score in raw_scores if score.quality >= task.quality_floor]
    for score in raw_scores:
        if score.quality < task.quality_floor:
            eliminations.append(
                {
                    "model_id": score.model.model_id,
                    "provider_id": score.provider.provider_id,
                    "reasons": [f"quality below floor {task.quality_floor:.6f}"],
                }
            )

    subscription = _apply_subscription_first(task, quality_filtered)
    eliminations.extend(subscription.eliminations)
    quality_filtered = subscription.pool

    frontier = _pareto_frontier(quality_filtered)
    if frontier:
        best_quality = max(score.quality for score in frontier)
        retained = [
            score for score in frontier if score.quality >= best_quality - retain_within_best
        ]
    else:
        retained = []

    with_fallbacks = [
        _attach_fallback(score, retained, fallback_failure_weight, task.max_attempts)
        for score in retained
    ]
    selection_pool = with_fallbacks
    if task.prefer_open_weight and any(score.model.open_weight for score in selection_pool):
        selection_pool = [score for score in selection_pool if score.model.open_weight]

    selected = min(selection_pool, key=_selection_key) if selection_pool else None
    return RoutingDecision(
        selected=selected,
        candidates=sorted(with_fallbacks, key=_selection_key),
        scored=sorted(raw_scores, key=_selection_key),
        eliminations=sorted(eliminations, key=lambda item: (item["model_id"], item["reasons"])),
        explanation={
            "task_id": task.task_id,
            "role": task.role,
            "pinned": False,
            "benchmark_version": task.benchmark_version,
            "normalization_version": NORMALIZATION_VERSION,
            "quality_formula": "(0.60*external+0.30*local)/0.90",
            "subscription_first_applied": subscription.applied,
            "reseller_exception_required": subscription.reseller_exception_required,
            "subscription_precedence_group": subscription.group,
            "pareto_frontier_model_ids": [
                score.model.model_id
                for score in sorted(frontier, key=lambda item: item.model.model_id)
            ],
            "retained_model_ids": [
                score.model.model_id
                for score in sorted(with_fallbacks, key=lambda item: item.model.model_id)
            ],
            "open_weight_preference_applied": bool(
                task.prefer_open_weight and any(score.model.open_weight for score in with_fallbacks)
            ),
            "selected_model_id": selected.model.model_id if selected else None,
            "eliminations": sorted(
                eliminations, key=lambda item: (item["model_id"], item["reasons"])
            ),
        },
    )


def _route_pinned_director(
    task: TaskRequirements,
    models: list[ModelCapabilities],
    provider_by_id: dict[str, ProviderCapabilities],
    history_by_model: dict[str, VerifiedHistory],
    local_prior_successes: float,
    local_prior_attempts: float,
    external_weight: float,
    local_weight: float,
    fallback_failure_weight: float,
) -> RoutingDecision:
    """Route the Director to its configured frontier model, or to nothing at all.

    There is deliberately no cheaper alternative and no automatic fallback. The
    frontier model's job is to make the expensive decisions once so that cheap
    models can execute many times; substituting a weaker model to save money
    defeats the design, so a pinned route that fails its requirements is
    reported as a refusal rather than quietly replaced.
    """

    if not task.pinned_model_id:
        raise RoutingError(
            "director role requires a pinned_model_id: the frontier model is configured, "
            "not selected by score"
        )

    pinned = next(
        (model for model in models if model.model_id == task.pinned_model_id),
        None,
    )
    provider = provider_by_id.get(pinned.provider_id) if pinned else None
    if pinned is None:
        reasons = [f"pinned model {task.pinned_model_id!r} is not in the registry"]
    else:
        reasons = _hard_filter_reasons(task, pinned, provider)

    base_explanation: dict[str, Any] = {
        "task_id": task.task_id,
        "role": "director",
        "pinned": True,
        "pinned_model_id": task.pinned_model_id,
        "normalization_version": NORMALIZATION_VERSION,
        "benchmark_version": task.benchmark_version,
        "subscription_first_applied": False,
        "reseller_exception_required": False,
        "downgrade_permitted": False,
    }

    if pinned is None or provider is None or reasons:
        return RoutingDecision(
            selected=None,
            candidates=[],
            scored=[],
            eliminations=[
                {
                    "model_id": task.pinned_model_id,
                    "provider_id": pinned.provider_id if pinned else None,
                    "reasons": reasons,
                }
            ],
            explanation={
                **base_explanation,
                "pinned_route_rejected": reasons,
                "selected_model_id": None,
            },
        )

    score = _score_candidate(
        task,
        pinned,
        provider,
        history_by_model.get(pinned.model_id),
        local_prior_successes,
        local_prior_attempts,
        external_weight,
        local_weight,
    )
    # Pool of one: no fallback is attached, by design.
    score = _attach_fallback(score, [score], fallback_failure_weight, task.max_attempts)
    return RoutingDecision(
        selected=score,
        candidates=[score],
        scored=[score],
        eliminations=[],
        explanation={**base_explanation, "selected_model_id": score.model.model_id},
    )


@dataclass(frozen=True)
class _SubscriptionOutcome:
    pool: list[CandidateScore]
    eliminations: list[dict[str, Any]]
    applied: bool
    reseller_exception_required: bool
    group: str | None


def _apply_subscription_first(
    task: TaskRequirements, scores: list[CandidateScore]
) -> _SubscriptionOutcome:
    """Prefer an already-paid-for route over a paid reseller route.

    Precedence, applied only among candidates that already cleared every hard
    requirement:

    1. eligible direct subscription routes;
    2. other eligible routes with zero marginal cost;
    3. reseller routes.

    The first non-empty group wins. Reaching group 3 is an exception worth
    recording, because it means real money is being spent on capability the user
    may already own. A reseller candidate that duplicates an eligible direct
    route, by model ID or by equivalence class, is eliminated outright.
    """

    if not task.subscription_first or not scores:
        return _SubscriptionOutcome(
            pool=scores,
            eliminations=[],
            applied=False,
            reseller_exception_required=False,
            group=None,
        )

    direct = [score for score in scores if _is_direct_subscription(score)]
    zero_cost = [
        score
        for score in scores
        if not _is_direct_subscription(score)
        and not _is_reseller(score)
        and score.model.zero_marginal_cost
    ]
    other_direct = [
        score
        for score in scores
        if not _is_direct_subscription(score)
        and not _is_reseller(score)
        and not score.model.zero_marginal_cost
    ]
    reseller = [score for score in scores if _is_reseller(score)]

    eliminations: list[dict[str, Any]] = []
    owned = [*direct, *zero_cost]
    if owned:
        for score in reseller:
            duplicate_of = _duplicate_of(task, score, owned)
            if duplicate_of is not None:
                eliminations.append(
                    {
                        "model_id": score.model.model_id,
                        "provider_id": score.provider.provider_id,
                        "reasons": [
                            f"subscription-first: duplicates the eligible route {duplicate_of}"
                        ],
                    }
                )
        eliminated_ids = {item["model_id"] for item in eliminations}
        reseller = [score for score in reseller if score.model.model_id not in eliminated_ids]

    for group_name, group in (
        ("direct_subscription", direct),
        ("zero_marginal_cost", zero_cost),
        ("other_direct", other_direct),
        ("reseller", reseller),
    ):
        if group:
            for score in scores:
                if score in group or score.model.model_id in {
                    item["model_id"] for item in eliminations
                }:
                    continue
                eliminations.append(
                    {
                        "model_id": score.model.model_id,
                        "provider_id": score.provider.provider_id,
                        "reasons": [
                            f"subscription-first: precedence group {group_name} is available"
                        ],
                    }
                )
            return _SubscriptionOutcome(
                pool=group,
                eliminations=eliminations,
                applied=True,
                reseller_exception_required=group_name == "reseller",
                group=group_name,
            )

    return _SubscriptionOutcome(
        pool=[],
        eliminations=eliminations,
        applied=True,
        reseller_exception_required=False,
        group=None,
    )


def _is_direct_subscription(score: CandidateScore) -> bool:
    return score.provider.provider_class in DIRECT_SUBSCRIPTION_CLASSES


def _is_reseller(score: CandidateScore) -> bool:
    return score.provider.provider_class in RESELLER_CLASSES


def _duplicate_of(
    task: TaskRequirements, reseller: CandidateScore, owned: list[CandidateScore]
) -> str | None:
    """Return the owned route a reseller candidate duplicates, if any.

    Two routes are duplicates when they name the same model, or when they share
    an equivalence class, which is how "materially equivalent capability" is
    expressed. The unit's own `equivalence_class` widens the match when the
    registry labels only one side of the pair.
    """

    def keys(score: CandidateScore) -> set[str]:
        return {key for key in (score.model.model_id, score.model.equivalence_class) if key}

    reseller_keys = keys(reseller)
    if task.equivalence_class and task.equivalence_class in reseller_keys:
        reseller_keys.add(task.equivalence_class)

    for candidate in sorted(owned, key=lambda item: item.model.model_id):
        if reseller_keys & keys(candidate):
            return candidate.model.model_id
    return None


def build_route_receipt(
    task: TaskRequirements,
    decision: RoutingDecision,
    *,
    registry_timestamp: str,
    evidence_freshness: str = "cache",
) -> dict[str, Any]:
    """Build the receipt that must accompany every route assignment.

    A route without a receipt is a guess. The receipt records what was
    considered, what was disqualified and why, the score inputs, the choice, the
    fallback, and the freshness of the evidence behind all of it.
    """

    if evidence_freshness not in {"network", "cache", "stale_cache"}:
        raise RoutingError(
            f"unknown evidence_freshness {evidence_freshness!r}; "
            "expected network, cache, or stale_cache"
        )

    selected = decision.selected
    fallback_id = selected.fallback_model_id if selected else None
    fallback_provider = None
    if fallback_id:
        fallback_provider = next(
            (
                score.provider.provider_id
                for score in decision.scored
                if score.model.model_id == fallback_id
            ),
            None,
        )

    considered = decision.scored or decision.candidates
    return {
        "receipt_contract": "graph-coder/route_receipt/v1",
        "node_id": task.task_id,
        "role": task.role,
        "considered_routes": [
            {
                "model": score.model.model_id,
                "provider": score.provider.provider_id,
                "quality": score.quality,
                "attempt_cost": score.model.per_attempt_cost,
                "expected_passing_cost": score.expected_passing_cost,
            }
            for score in considered
        ],
        "disqualifications": [
            {
                "model": item["model_id"],
                "provider": item.get("provider_id"),
                "reasons": item["reasons"],
            }
            for item in decision.eliminations
        ],
        "score_inputs": {
            "benchmark_weights": dict(sorted(task.benchmark_weights.items())),
            "benchmark_version": task.benchmark_version,
            "normalization_version": NORMALIZATION_VERSION,
            "quality_formula": "(0.60*external+0.30*local)/0.90",
            "quality_floor": task.quality_floor,
            "repair_cost_factor": task.repair_cost_factor,
            "escalation_cost": task.escalation_cost,
        },
        "chosen_route": (
            {
                "model": selected.model.model_id,
                "provider": selected.provider.provider_id,
                "expected_passing_cost": selected.expected_passing_cost,
            }
            if selected
            else None
        ),
        "fallback_route": (
            {"model": fallback_id, "provider": fallback_provider} if fallback_id else None
        ),
        "subscription_first_applied": bool(
            decision.explanation.get("subscription_first_applied", False)
        ),
        "reseller_exception_required": bool(
            decision.explanation.get("reseller_exception_required", False)
        ),
        "subscription_precedence_group": decision.explanation.get("subscription_precedence_group"),
        "open_weight_preference_effect": (
            "applied"
            if decision.explanation.get("open_weight_preference_applied")
            else "not applied"
        ),
        "pinned": bool(decision.explanation.get("pinned", False)),
        "pinned_route_rejected": decision.explanation.get("pinned_route_rejected"),
        "registry_timestamp": registry_timestamp,
        "evidence_freshness": evidence_freshness,
        "tie_breakers_used": [
            "expected_passing_cost",
            "evidence_confidence",
            "provider_reliability",
            "latency",
            "model_id",
        ],
        "escalation_conditions": [
            "verification failure",
            "repeated tool-use failure",
            "context overflow",
            "provider unavailability",
            "raised task risk or capability",
            "capability-attributable review failure",
        ],
    }


def _hard_filter_reasons(
    task: TaskRequirements, model: ModelCapabilities, provider: ProviderCapabilities | None
) -> list[str]:
    reasons: list[str] = []
    if provider is None:
        return ["authentication/configuration: provider missing"]
    if task.allowed_provider_ids and provider.provider_id not in task.allowed_provider_ids:
        reasons.append("provider policy: provider not allowed")
    if provider.provider_id in task.denied_provider_ids:
        reasons.append("provider policy: provider denied")
    if task.allowed_model_ids and model.model_id not in task.allowed_model_ids:
        reasons.append("model policy: model not allowed")
    if model.model_id in task.denied_model_ids:
        reasons.append("model policy: model denied")
    if task.requires_auth and not provider.authenticated:
        reasons.append("authentication/configuration: provider not authenticated")
    missing_config = sorted(task.required_configuration - provider.configured)
    if missing_config:
        reasons.append(f"authentication/configuration: missing {missing_config}")
    if model.context_tokens < task.min_context_tokens:
        reasons.append("context/output: insufficient context")
    if model.output_tokens < task.min_output_tokens:
        reasons.append("context/output: insufficient output")
    missing_tools = sorted(task.required_tools - model.tools)
    if missing_tools:
        reasons.append(f"tools/modalities/streaming: missing tools {missing_tools}")
    missing_modalities = sorted(task.required_modalities - model.modalities)
    if missing_modalities:
        reasons.append(f"tools/modalities/streaming: missing modalities {missing_modalities}")
    if task.require_streaming and not model.streaming:
        reasons.append("tools/modalities/streaming: streaming unavailable")
    if task.allowed_model_classes and model.model_class not in task.allowed_model_classes:
        reasons.append("model class: disallowed")
    missing_policies = sorted(task.required_policies - model.policies)
    if missing_policies:
        reasons.append(f"policies: missing {missing_policies}")
    if task.environment not in provider.environments:
        reasons.append("environment: unavailable")
    if model.per_attempt_cost > task.max_per_attempt_cost:
        reasons.append("per-attempt cost: exceeds maximum")
    if model.confidence < task.min_confidence:
        reasons.append("confidence: below minimum")
    if model.evidence_age_hours > task.max_evidence_age_hours:
        reasons.append("evidence freshness: too old")
    return reasons


def _score_candidate(
    task: TaskRequirements,
    model: ModelCapabilities,
    provider: ProviderCapabilities,
    history: VerifiedHistory | None,
    prior_successes: float,
    prior_attempts: float,
    external_weight: float,
    local_weight: float,
) -> CandidateScore:
    external = _external_score(task, model)
    local = _local_score(history, prior_successes, prior_attempts)
    denominator = external_weight + local_weight
    quality = (
        ((external_weight * external) + (local_weight * local)) / denominator
        if denominator
        else 0.0
    )
    pass_probability = quality * _bounded(provider.reliability)
    attempt_cost = _expected_cost(model.per_attempt_cost, pass_probability, task.max_attempts)

    # expected_passing_cost = attempt_cost
    #                       + probability_of_repair    * repair_cost
    #                       + probability_of_escalation * escalation_cost
    #
    # The repair and escalation terms use configured estimates. They default to
    # zero so an unconfigured registry never implies precision it does not have.
    probability_of_repair = _bounded(1.0 - pass_probability)
    repair_cost = model.per_attempt_cost * max(0.0, task.repair_cost_factor)
    probability_of_escalation = _bounded((1.0 - pass_probability) ** max(1, task.max_attempts))
    escalation_cost = max(0.0, task.escalation_cost)
    expected_cost = (
        attempt_cost
        + probability_of_repair * repair_cost
        + probability_of_escalation * escalation_cost
    )
    return CandidateScore(
        model=model,
        provider=provider,
        external_score=round(external, 12),
        local_score=round(local, 12),
        quality=round(quality, 12),
        expected_passing_cost=round(expected_cost, 12),
        fallback_model_id=None,
        explanation={
            "model": asdict(model),
            "provider": asdict(provider),
            "benchmark_version": task.benchmark_version,
            "normalization_version": NORMALIZATION_VERSION,
            "benchmark_weights": dict(sorted(task.benchmark_weights.items())),
            "benchmark_coverage": round(_benchmark_coverage(task, model), 12),
            "unscored_benchmark_weights": sorted(
                name for name in task.benchmark_weights if name not in model.benchmarks
            ),
            "external_score": round(external, 12),
            "local_score": round(local, 12),
            "quality": round(quality, 12),
            "provider_adjusted_pass_probability": round(pass_probability, 12),
            "attempt_cost": round(attempt_cost, 12),
            "probability_of_repair": round(probability_of_repair, 12),
            "repair_cost": round(repair_cost, 12),
            "probability_of_escalation": round(probability_of_escalation, 12),
            "escalation_cost": round(escalation_cost, 12),
            "expected_passing_cost": round(expected_cost, 12),
        },
    )


def _benchmark_coverage(task: TaskRequirements, model: ModelCapabilities) -> float:
    """Share of the task's weight mass this model actually has evidence for.

    A weighted category the model does not report contributes nothing to the
    numerator and its full weight to the denominator, so missing evidence scores
    like a bad result rather than like an unknown. That is the conservative
    reading and it stays, but it must not be invisible: a candidate losing on
    absent benchmarks looks identical to one losing on poor ones unless the
    receipt says which. Coverage is that distinction.
    """

    weights = task.benchmark_weights or {name: 1.0 for name in model.benchmarks}
    total_weight = sum(max(0.0, weight) for weight in weights.values())
    if total_weight <= 0:
        return 0.0
    covered = sum(max(0.0, weight) for name, weight in weights.items() if name in model.benchmarks)
    return _bounded(covered / total_weight)


def _external_score(task: TaskRequirements, model: ModelCapabilities) -> float:
    weights = task.benchmark_weights or {name: 1.0 for name in model.benchmarks}
    total_weight = sum(max(0.0, weight) for weight in weights.values())
    if total_weight <= 0:
        base = 0.0
    else:
        base = (
            sum(
                max(0.0, weights.get(name, 0.0)) * model.benchmarks.get(name, 0.0)
                for name in weights
            )
            / total_weight
        )
    return _bounded(base * model.confidence)


def _local_score(
    history: VerifiedHistory | None, prior_successes: float, prior_attempts: float
) -> float:
    if history is None:
        return _bounded(prior_successes / prior_attempts if prior_attempts else 0.0)
    recency = max(0.0, history.recency)
    attempts = history.attempts * recency
    successes = history.successes * recency
    return _bounded((prior_successes + successes) / (prior_attempts + attempts))


def _pareto_frontier(scores: list[CandidateScore]) -> list[CandidateScore]:
    frontier: list[CandidateScore] = []
    for score in scores:
        dominated = False
        for other in scores:
            if other is score:
                continue
            if (
                other.quality >= score.quality
                and other.expected_passing_cost <= score.expected_passing_cost
                and other.provider.reliability >= score.provider.reliability
                and other.model.latency_ms <= score.model.latency_ms
                and (
                    other.quality > score.quality
                    or other.expected_passing_cost < score.expected_passing_cost
                    or other.provider.reliability > score.provider.reliability
                    or other.model.latency_ms < score.model.latency_ms
                )
            ):
                dominated = True
                break
        if not dominated:
            frontier.append(score)
    return frontier


def _attach_fallback(
    score: CandidateScore,
    candidates: list[CandidateScore],
    failure_weight: float,
    max_attempts: int,
) -> CandidateScore:
    fallback_pool = [item for item in candidates if item.model.model_id != score.model.model_id]
    different_provider = [
        item for item in fallback_pool if item.provider.provider_id != score.provider.provider_id
    ]
    fallback = (
        min(different_provider or fallback_pool, key=_selection_key) if fallback_pool else None
    )
    total_cost = score.expected_passing_cost
    if fallback is not None:
        pass_probability = _bounded(score.quality * score.provider.reliability)
        failure_probability = (1.0 - pass_probability) ** max(1, max_attempts)
        total_cost += failure_weight * failure_probability * fallback.expected_passing_cost
    explanation = dict(score.explanation)
    explanation["fallback_model_id"] = fallback.model.model_id if fallback else None
    explanation["fallback_provider_id"] = fallback.provider.provider_id if fallback else None
    explanation["expected_passing_cost_with_fallback"] = round(total_cost, 12)
    return CandidateScore(
        model=score.model,
        provider=score.provider,
        external_score=score.external_score,
        local_score=score.local_score,
        quality=score.quality,
        expected_passing_cost=round(total_cost, 12),
        fallback_model_id=fallback.model.model_id if fallback else None,
        explanation=explanation,
    )


def _expected_cost(per_attempt_cost: float, pass_probability: float, max_attempts: int) -> float:
    """Expected spend across a bounded geometric sequence of attempts."""

    probability = _bounded(pass_probability)
    attempts = max(1, max_attempts)
    failure_probability = 1.0 - probability
    return per_attempt_cost * sum(failure_probability**index for index in range(attempts))


def _selection_key(score: CandidateScore) -> tuple[float, float, float, float, str]:
    return (
        score.expected_passing_cost,
        -score.model.confidence,
        -score.provider.reliability,
        score.model.latency_ms,
        score.model.model_id,
    )


def _bounded(value: float) -> float:
    if math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, value))
