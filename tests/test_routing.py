from __future__ import annotations

import json
from pathlib import Path

from graph_coder.routing import (
    ModelCapabilities,
    ProviderCapabilities,
    TaskRequirements,
    VerifiedHistory,
    route_model,
)


def _providers() -> list[ProviderCapabilities]:
    return [
        ProviderCapabilities(
            "openai", True, frozenset({"region-us"}), 0.99, frozenset({"production"})
        ),
        ProviderCapabilities(
            "local", True, frozenset({"region-us"}), 0.96, frozenset({"production"})
        ),
        ProviderCapabilities(
            "bad-auth-provider", False, frozenset({"region-us"}), 0.90, frozenset({"production"})
        ),
        ProviderCapabilities(
            "bad-env-provider", True, frozenset({"region-us"}), 0.90, frozenset({"dev"})
        ),
    ]


def _model(model_id: str, provider_id: str = "openai", **overrides: object) -> ModelCapabilities:
    data = {
        "model_id": model_id,
        "provider_id": provider_id,
        "context_tokens": 128_000,
        "output_tokens": 16_000,
        "tools": frozenset({"function_calling"}),
        "modalities": frozenset({"text", "image"}),
        "streaming": True,
        "model_class": "reasoning",
        "policies": frozenset({"commercial"}),
        "per_attempt_cost": 1.0,
        "confidence": 0.90,
        "latency_ms": 100.0,
        "open_weight": False,
        "benchmarks": {"coding": 0.90, "planning": 0.80},
    }
    data.update(overrides)
    return ModelCapabilities(**data)  # type: ignore[arg-type]


def _task(*, prefer_open_weight: bool = True, quality_floor: float = 0.70) -> TaskRequirements:
    return TaskRequirements(
        "task-golden",
        required_configuration=frozenset({"region-us"}),
        min_context_tokens=64_000,
        min_output_tokens=8_000,
        required_tools=frozenset({"function_calling"}),
        required_modalities=frozenset({"text", "image"}),
        require_streaming=True,
        allowed_model_classes=frozenset({"reasoning"}),
        required_policies=frozenset({"commercial"}),
        environment="production",
        max_per_attempt_cost=2.0,
        min_confidence=0.70,
        quality_floor=quality_floor,
        prefer_open_weight=prefer_open_weight,
        benchmark_version="bench-2026-07",
        benchmark_weights={"coding": 0.70, "planning": 0.30},
    )


def test_golden_routing_explanations_and_eliminations() -> None:
    expected = json.loads(Path("tests/fixtures/routing/golden.json").read_text(encoding="utf-8"))[0]
    models = [
        _model(
            "open/steady",
            "local",
            per_attempt_cost=0.90,
            confidence=0.91,
            latency_ms=120,
            open_weight=True,
            benchmarks={"coding": 0.91, "planning": 0.85},
        ),
        _model(
            "closed/fast",
            "openai",
            per_attempt_cost=0.80,
            confidence=0.93,
            latency_ms=80,
            benchmarks={"coding": 0.92, "planning": 0.85},
        ),
        _model("bad/auth", "bad-auth-provider"),
        _model("bad/context", context_tokens=4_000),
        _model("bad/output", output_tokens=1_000),
        _model("bad/tools", tools=frozenset()),
        _model("bad/modalities", modalities=frozenset({"text"})),
        _model("bad/streaming", streaming=False),
        _model("bad/class", model_class="embedding"),
        _model("bad/policy", policies=frozenset()),
        _model("bad/environment", "bad-env-provider"),
        _model("bad/cost", per_attempt_cost=3.0),
        _model("bad/confidence", confidence=0.20),
    ]
    history = [
        VerifiedHistory("open/steady", successes=9, attempts=10, recency=1.0),
        VerifiedHistory("closed/fast", successes=8, attempts=10, recency=0.5),
    ]

    decision = route_model(_task(), models, _providers(), history)

    assert decision.selected is not None
    assert decision.selected.model.model_id == expected["selected"]
    assert decision.selected.fallback_model_id == expected["fallback"]
    assert decision.explanation["retained_model_ids"] == expected["retained"]
    assert [item["model_id"] for item in decision.eliminations] == expected["eliminated"]
    assert decision.explanation["benchmark_version"] == "bench-2026-07"
    assert decision.explanation["quality_formula"] == "(0.60*external+0.30*local)/0.90"
    assert "authentication/configuration" in decision.eliminations[0]["reasons"][0]
    assert decision.selected.explanation["fallback_provider_id"] == "openai"


def test_external_local_quality_math_and_recency_prior() -> None:
    model = _model("math", confidence=0.8, benchmarks={"coding": 1.0, "planning": 0.5})
    decision = route_model(
        _task(prefer_open_weight=False, quality_floor=0),
        [model],
        _providers(),
        [VerifiedHistory("math", successes=4, attempts=8, recency=0.5)],
    )
    selected = decision.selected
    assert selected is not None
    assert selected.external_score == 0.68  # ((1*.7)+(.5*.3))*.8
    assert (
        selected.local_score == 0.5
    )  # (1 prior success + 2 recency successes)/(2 prior attempts + 4 recency attempts)
    assert selected.quality == 0.62  # (.6*.68 + .3*.5)/.9


def test_tie_breakers_are_deterministic() -> None:
    models = [
        _model("b", confidence=0.9, latency_ms=100, benchmarks={"coding": 0.8, "planning": 0.8}),
        _model("a", confidence=0.9, latency_ms=100, benchmarks={"coding": 0.8, "planning": 0.8}),
    ]

    decision = route_model(_task(prefer_open_weight=False, quality_floor=0), models, _providers())

    assert decision.selected is not None
    assert decision.selected.model.model_id == "a"


def test_quality_floor_can_eliminate_everything() -> None:
    decision = route_model(_task(quality_floor=0.99), [_model("too-low")], _providers())

    assert decision.selected is None
    assert decision.eliminations == [
        {
            "model_id": "too-low",
            "provider_id": "openai",
            "reasons": ["quality below floor 0.990000"],
        }
    ]


def test_policy_freshness_and_manual_override_are_explicit() -> None:
    models = [
        _model("allowed", evidence_age_hours=1),
        _model("stale", evidence_age_hours=100),
    ]
    task = _task(prefer_open_weight=False, quality_floor=0)
    task = TaskRequirements(
        **{
            **task.__dict__,
            "allowed_model_ids": frozenset({"allowed", "stale"}),
            "max_evidence_age_hours": 24,
        }
    )
    decision = route_model(task, models, _providers())
    assert decision.selected is not None
    assert decision.selected.model.model_id == "allowed"
    assert decision.eliminations[0]["reasons"] == ["evidence freshness: too old"]

    rejected = route_model(
        TaskRequirements(**{**task.__dict__, "manual_override_model_id": "stale"}),
        models,
        _providers(),
    )
    assert rejected.selected is None
    assert "evidence freshness" in rejected.explanation["manual_override_rejected"][0]

    forced = route_model(
        TaskRequirements(
            **{
                **task.__dict__,
                "manual_override_model_id": "stale",
                "force_override": True,
            }
        ),
        models,
        _providers(),
    )
    assert forced.selected is not None
    assert forced.selected.model.model_id == "stale"
    assert forced.explanation["manual_override_warnings"]


def test_expected_cost_is_bounded_and_provider_adjusted() -> None:
    model = _model("bounded", per_attempt_cost=1.0)
    decision = route_model(_task(prefer_open_weight=False, quality_floor=0), [model], _providers())
    selected = decision.selected
    assert selected is not None
    assert 1.0 <= selected.expected_passing_cost < 2.0
    assert selected.explanation["provider_adjusted_pass_probability"] < selected.quality
