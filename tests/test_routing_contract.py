"""Contract tests for Graph Coder role routing, subscription-first, and receipts.

Subscription-first used to live in a standalone validator script beside the skill,
which meant the router itself did not enforce it. These tests drive the real
router, so the policy cannot drift away from the engine again.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graph_coder.errors import RoutingError
from graph_coder.routing import (
    ModelCapabilities,
    ProviderCapabilities,
    TaskRequirements,
    build_route_receipt,
    route_model,
)

CASES = Path(__file__).resolve().parent / "fixtures" / "routing" / "subscription-first-cases.json"


def model(
    model_id: str,
    provider_id: str,
    *,
    cost: float = 1.0,
    quality: float = 0.9,
    context: int = 200_000,
    tools: frozenset[str] = frozenset({"edit"}),
    zero_marginal_cost: bool = False,
    equivalence_class: str | None = None,
) -> ModelCapabilities:
    return ModelCapabilities(
        model_id=model_id,
        provider_id=provider_id,
        context_tokens=context,
        output_tokens=32_000,
        tools=tools,
        streaming=True,
        per_attempt_cost=cost,
        confidence=1.0,
        latency_ms=1000.0,
        benchmarks={"coding": quality},
        zero_marginal_cost=zero_marginal_cost,
        equivalence_class=equivalence_class,
    )


def provider(
    provider_id: str, *, provider_class: str = "direct_api", authenticated: bool = True
) -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_id=provider_id,
        authenticated=authenticated,
        reliability=1.0,
        provider_class=provider_class,
    )


# --- role categories ---------------------------------------------------------


def test_director_is_pinned_to_the_configured_frontier_model() -> None:
    models = [
        model("frontier-1", "openai", cost=10.0, quality=0.99),
        model("cheap-1", "openai", cost=0.1, quality=0.80),
    ]
    task = TaskRequirements(
        task_id="N-director", role="director", pinned_model_id="frontier-1", max_attempts=1
    )

    decision = route_model(task, models, [provider("openai")])

    assert decision.selected is not None
    assert decision.selected.model.model_id == "frontier-1"
    assert decision.explanation["role"] == "director"
    assert decision.explanation["pinned"] is True
    # The cheap model is cheaper and eligible; it must not win anyway.
    assert decision.explanation["selected_model_id"] == "frontier-1"


def test_director_route_is_never_silently_downgraded() -> None:
    # The pinned model cannot satisfy the task. The router must refuse rather
    # than quietly hand the Director a weaker model.
    models = [
        model("frontier-1", "openai", context=1_000),
        model("cheap-1", "openai", cost=0.1, context=500_000),
    ]
    task = TaskRequirements(
        task_id="N-director",
        role="director",
        pinned_model_id="frontier-1",
        min_context_tokens=400_000,
    )

    decision = route_model(task, models, [provider("openai")])

    assert decision.selected is None
    assert decision.explanation["pinned_route_rejected"]
    assert "cheap-1" not in json.dumps(decision.explanation.get("selected_model_id"))


def test_director_without_a_pinned_model_is_an_error() -> None:
    with pytest.raises(RoutingError, match="pinned"):
        route_model(
            TaskRequirements(task_id="N-director", role="director"),
            [model("m", "openai")],
            [provider("openai")],
        )


def test_there_is_no_standalone_reviewer_route_category() -> None:
    with pytest.raises(RoutingError, match="reviewer"):
        TaskRequirements(task_id="N-1", role="reviewer")  # type: ignore[arg-type]


def test_worker_takes_the_lowest_expected_passing_cost() -> None:
    models = [
        model("expensive", "openai", cost=5.0, quality=0.95),
        model("cheap", "openai", cost=0.5, quality=0.94),
    ]
    task = TaskRequirements(task_id="IU-001", role="worker", max_attempts=1)

    decision = route_model(task, models, [provider("openai")])

    assert decision.selected is not None
    assert decision.selected.model.model_id == "cheap"


def test_manager_route_must_meet_review_context_and_tool_requirements() -> None:
    models = [
        model("narrow", "openai", cost=0.1, context=8_000, tools=frozenset()),
        model("capable", "openai", cost=2.0, context=400_000),
    ]
    task = TaskRequirements(
        task_id="M-CONTRACTS",
        role="manager",
        min_context_tokens=200_000,
        required_tools=frozenset({"edit"}),
    )

    decision = route_model(task, models, [provider("openai")])

    assert decision.selected is not None
    assert decision.selected.model.model_id == "capable"
    assert any(item["model_id"] == "narrow" for item in decision.eliminations)


def test_every_role_is_recorded_on_the_decision() -> None:
    for role in ("manager", "worker", "research", "rehearsal"):
        decision = route_model(
            TaskRequirements(task_id=f"N-{role}", role=role),  # type: ignore[arg-type]
            [model("m", "openai")],
            [provider("openai")],
        )
        assert decision.explanation["role"] == role


# --- expected passing cost ---------------------------------------------------


def test_expected_passing_cost_includes_repair_and_escalation_terms() -> None:
    candidate = model("m", "openai", cost=1.0, quality=0.5)
    providers = [ProviderCapabilities(provider_id="openai", authenticated=True, reliability=1.0)]

    without = route_model(TaskRequirements(task_id="IU-1", max_attempts=1), [candidate], providers)
    with_terms = route_model(
        TaskRequirements(
            task_id="IU-1",
            max_attempts=1,
            repair_cost_factor=2.0,
            escalation_cost=50.0,
        ),
        [candidate],
        providers,
    )

    assert without.selected is not None and with_terms.selected is not None
    assert with_terms.selected.expected_passing_cost > without.selected.expected_passing_cost
    explanation = with_terms.selected.explanation
    assert explanation["probability_of_repair"] == pytest.approx(0.5)
    assert explanation["repair_cost"] == pytest.approx(2.0)
    assert explanation["probability_of_escalation"] == pytest.approx(0.5)
    assert explanation["escalation_cost"] == pytest.approx(50.0)


def test_cost_terms_default_to_inert_so_estimates_are_never_invented() -> None:
    candidate = model("m", "openai", cost=1.0, quality=1.0)
    decision = route_model(
        TaskRequirements(task_id="IU-1", max_attempts=1), [candidate], [provider("openai")]
    )
    assert decision.selected is not None
    explanation = decision.selected.explanation
    assert explanation["repair_cost"] == 0.0
    assert explanation["escalation_cost"] == 0.0


def test_a_cheap_model_that_probably_fails_loses_to_a_capable_one() -> None:
    models = [
        model("flaky", "openai", cost=0.2, quality=0.30),
        model("solid", "openai", cost=1.0, quality=0.98),
    ]
    task = TaskRequirements(
        task_id="IU-1", max_attempts=2, repair_cost_factor=3.0, escalation_cost=100.0
    )

    decision = route_model(task, models, [provider("openai")])

    assert decision.selected is not None
    assert decision.selected.model.model_id == "solid"


# --- subscription-first ------------------------------------------------------


CaseInputs = tuple[TaskRequirements, list[ModelCapabilities], list[ProviderCapabilities]]


def build_case(case: dict) -> CaseInputs:
    models: list[ModelCapabilities] = []
    providers: list[ProviderCapabilities] = []
    for candidate in case["candidates"]:
        provider_id = candidate["id"].split(":", 1)[0]
        providers.append(
            provider(
                provider_id,
                provider_class=candidate["provider_class"],
                authenticated=candidate["available"],
            )
        )
        models.append(
            model(
                candidate["id"],
                provider_id,
                cost=0.0 if candidate["zero_marginal_cost"] else 1.0,
                # An incapable candidate fails a hard requirement.
                tools=frozenset({"edit"}) if candidate["capable"] else frozenset(),
                zero_marginal_cost=candidate["zero_marginal_cost"],
                equivalence_class=candidate.get("equivalence"),
            )
        )
    constraint = case["user_constraint"]
    task = TaskRequirements(
        task_id=case["name"],
        role="worker",
        required_tools=frozenset({"edit"}),
        allowed_model_ids=frozenset({constraint}) if constraint else frozenset(),
        subscription_first=True,
        max_attempts=1,
    )
    return task, models, providers


@pytest.mark.parametrize(
    "case",
    json.loads(CASES.read_text(encoding="utf-8")),
    ids=lambda case: case["name"],
)
def test_subscription_first_cases_are_enforced_by_the_router(case: dict) -> None:
    task, models, providers = build_case(case)

    decision = route_model(task, models, providers)

    assert decision.selected is not None, case["name"]
    assert decision.selected.model.model_id == case["expected"], case["name"]
    assert (
        decision.explanation["reseller_exception_required"] is case["reseller_exception_required"]
    ), case["name"]


def test_subscription_first_only_applies_among_eligible_routes() -> None:
    # The subscription route cannot do the job. Preference must not override a
    # hard requirement.
    models = [
        model("sub:weak", "direct", context=1_000, zero_marginal_cost=True),
        model("reseller:strong", "openrouter", context=500_000),
    ]
    providers = [
        provider("direct", provider_class="direct_oauth"),
        provider("openrouter", provider_class="reseller"),
    ]
    task = TaskRequirements(
        task_id="IU-1", subscription_first=True, min_context_tokens=400_000, max_attempts=1
    )

    decision = route_model(task, models, providers)

    assert decision.selected is not None
    assert decision.selected.model.model_id == "reseller:strong"
    assert decision.explanation["reseller_exception_required"] is True


def test_reseller_duplicate_of_a_direct_route_is_eliminated_with_a_reason() -> None:
    models = [
        model("gpt-5.5", "direct", cost=0.0, zero_marginal_cost=True),
        model("gpt-5.5-via-reseller", "openrouter", cost=0.0, equivalence_class="gpt-5.5"),
    ]
    providers = [
        provider("direct", provider_class="direct_oauth"),
        provider("openrouter", provider_class="reseller"),
    ]
    task = TaskRequirements(
        task_id="IU-1", subscription_first=True, equivalence_class="gpt-5.5", max_attempts=1
    )

    decision = route_model(task, models, providers)

    assert decision.selected is not None
    assert decision.selected.provider.provider_id == "direct"
    reasons = [
        reason
        for item in decision.eliminations
        if item["model_id"] == "gpt-5.5-via-reseller"
        for reason in item["reasons"]
    ]
    assert any("subscription-first" in reason for reason in reasons)


def test_subscription_first_can_be_disabled() -> None:
    models = [
        model("sub", "direct", cost=1.0, zero_marginal_cost=True),
        model("reseller", "openrouter", cost=0.1),
    ]
    providers = [
        provider("direct", provider_class="direct_oauth"),
        provider("openrouter", provider_class="reseller"),
    ]

    off = route_model(
        TaskRequirements(task_id="IU-1", subscription_first=False, max_attempts=1),
        models,
        providers,
    )
    on = route_model(
        TaskRequirements(task_id="IU-1", subscription_first=True, max_attempts=1), models, providers
    )

    assert off.selected is not None and on.selected is not None
    assert off.selected.model.model_id == "reseller"
    assert on.selected.model.model_id == "sub"


# --- determinism and receipts ------------------------------------------------


def test_route_selection_is_deterministic_for_the_same_registry_and_unit() -> None:
    models = [
        model("a", "openai", cost=1.0, quality=0.90),
        model("b", "anthropic", cost=1.0, quality=0.90),
        model("c", "google", cost=1.0, quality=0.90),
    ]
    providers = [provider("openai"), provider("anthropic"), provider("google")]
    task = TaskRequirements(task_id="IU-1", max_attempts=1)

    first = route_model(task, models, providers)
    second = route_model(task, list(reversed(models)), list(reversed(providers)))

    assert first.selected is not None and second.selected is not None
    assert first.selected.model.model_id == second.selected.model.model_id


def test_receipt_records_considered_routes_disqualifications_and_choice() -> None:
    models = [
        model("chosen", "openai", cost=0.5),
        model("pricey", "openai", cost=9.0),
        model("tiny", "openai", context=10),
    ]
    task = TaskRequirements(
        task_id="IU-001", role="worker", min_context_tokens=1_000, max_attempts=1
    )

    decision = route_model(task, models, [provider("openai")])
    receipt = build_route_receipt(task, decision, registry_timestamp="2026-07-30T00:00:00Z")

    assert receipt["node_id"] == "IU-001"
    assert receipt["role"] == "worker"
    assert receipt["chosen_route"]["model"] == "chosen"
    assert receipt["registry_timestamp"] == "2026-07-30T00:00:00Z"
    assert receipt["evidence_freshness"] in {"network", "cache", "stale_cache"}
    considered = {entry["model"] for entry in receipt["considered_routes"]}
    assert {"chosen", "pricey"} <= considered
    disqualified = {entry["model"] for entry in receipt["disqualifications"]}
    assert "tiny" in disqualified
    assert receipt["score_inputs"]["normalization_version"]
    assert "expected_passing_cost" in receipt["chosen_route"]


def test_receipt_is_emitted_even_when_nothing_is_eligible() -> None:
    task = TaskRequirements(task_id="IU-1", min_context_tokens=10**9)
    decision = route_model(task, [model("m", "openai")], [provider("openai")])
    receipt = build_route_receipt(task, decision, registry_timestamp="2026-07-30T00:00:00Z")

    assert decision.selected is None
    assert receipt["chosen_route"] is None
    assert receipt["disqualifications"]


def test_receipt_records_the_subscription_decision_and_tie_breakers() -> None:
    models = [
        model("sub", "direct", cost=1.0, zero_marginal_cost=True),
        model("reseller", "openrouter", cost=0.1),
    ]
    providers = [
        provider("direct", provider_class="direct_oauth"),
        provider("openrouter", provider_class="reseller"),
    ]
    task = TaskRequirements(task_id="IU-1", subscription_first=True, max_attempts=1)

    receipt = build_route_receipt(
        task, route_model(task, models, providers), registry_timestamp="2026-07-30T00:00:00Z"
    )

    assert receipt["subscription_first_applied"] is True
    assert receipt["reseller_exception_required"] is False
    assert isinstance(receipt["tie_breakers_used"], list)
