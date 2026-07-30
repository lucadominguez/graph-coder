"""Deterministic model routing for Graph Coder."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class TaskRequirements:
    task_id: str
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


@dataclass(frozen=True)
class ProviderCapabilities:
    provider_id: str
    authenticated: bool
    configured: frozenset[str] = frozenset()
    reliability: float = 0.0
    environments: frozenset[str] = frozenset({"production"})


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
        eliminations=sorted(eliminations, key=lambda item: (item["model_id"], item["reasons"])),
        explanation={
            "task_id": task.task_id,
            "benchmark_version": task.benchmark_version,
            "quality_formula": "(0.60*external+0.30*local)/0.90",
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
    expected_cost = _expected_cost(model.per_attempt_cost, pass_probability, task.max_attempts)
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
            "benchmark_weights": dict(sorted(task.benchmark_weights.items())),
            "external_score": round(external, 12),
            "local_score": round(local, 12),
            "quality": round(quality, 12),
            "provider_adjusted_pass_probability": round(pass_probability, 12),
            "expected_passing_cost": round(expected_cost, 12),
        },
    )


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
