"""Tests for the LLM Stats to router bridge.

The fixture `llm-stats-models-page.json` is a real, unedited slice of a live
`GET https://api.zeroeval.com/stats/v1/models` response captured on 2026-07-30. It
deliberately includes a priced first-party model, reseller-served models, a model
with no providers, and a model whose inference is unavailable, so the mapping is
tested against the shapes the API actually returns rather than invented ones.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from graph_coder.errors import RoutingError
from graph_coder.llm_stats import DEFAULT_API_BASE, LLMStatsClient
from graph_coder.registry import (
    assert_fresh,
    build_registry,
    per_attempt_cost,
)
from graph_coder.routing import TaskRequirements, route_model

FIXTURE = Path(__file__).parent / "fixtures" / "routing" / "llm-stats-models-page.json"


def records() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["models"]


# --- the endpoint itself -----------------------------------------------------


def test_default_base_url_points_at_the_live_api() -> None:
    # The previous value, https://llm-stats.com/api/v1, returns 404. It was never
    # a live endpoint, which is why the integration was only ever fixture-deep.
    assert DEFAULT_API_BASE == "https://api.zeroeval.com/stats/v1"


def test_client_sends_a_user_agent_because_cloudflare_requires_one() -> None:
    from graph_coder.llm_stats import USER_AGENT

    source = Path("src/graph_coder/llm_stats.py").read_text(encoding="utf-8")
    assert '"User-Agent": USER_AGENT' in source
    assert "Mozilla/5.0" in USER_AGENT


def test_live_envelope_shape_is_parsed() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert set(payload) == {"models", "next_cursor", "total"}
    items, cursor = LLMStatsClient._validate_page(payload)
    assert cursor is None
    assert len(items) == len(payload["models"])
    assert all("id" in item for item in items)


def test_cursor_pagination_is_used_not_page_urls() -> None:
    client = LLMStatsClient(base_url="https://api.zeroeval.com/stats/v1")
    client._paginated_endpoint = "models"
    client._paginated_params = {"limit": 100}
    nxt = client._absolute_next("OPAQUECURSOR")
    assert "cursor=OPAQUECURSOR" in nxt
    assert "limit=100" in nxt


# --- cost derivation ---------------------------------------------------------


def test_per_attempt_cost_is_derived_from_published_per_million_prices() -> None:
    # 10 USD/M input, 50 USD/M output, 40k in and 8k out.
    cost = per_attempt_cost(10.0, 50.0, input_tokens=40_000, output_tokens=8_000)
    assert cost == pytest.approx(10.0 * 0.04 + 50.0 * 0.008)
    assert cost == pytest.approx(0.8)


def test_missing_prices_do_not_become_free() -> None:
    assert per_attempt_cost(None, None, input_tokens=1000, output_tokens=100) == 0.0
    build = build_registry(records())
    # Anything priced None is reported, never silently treated as a bargain.
    assert "routes_missing_price" in build.report


# --- registry mapping --------------------------------------------------------


def test_one_route_per_model_and_provider_pair() -> None:
    build = build_registry(records())
    assert build.models, "the fixture must yield routes"
    for model in build.models:
        assert model.model_id.startswith(f"{model.provider_id}:")
        # equivalence_class is the bare model id, which is how the router spots the
        # same capability offered by two providers.
        assert model.equivalence_class
        assert not model.equivalence_class.startswith(f"{model.provider_id}:")


def test_models_without_providers_or_inference_are_excluded_and_counted() -> None:
    build = build_registry(records())
    assert build.report["models_without_providers"] >= 1
    assert build.report["models_skipped_inference_unavailable"] >= 1
    ids = {model.equivalence_class for model in build.models}
    unavailable = [
        record["id"]
        for record in records()
        if not (record.get("inference") or {}).get("available")
    ]
    for model_id in unavailable:
        assert model_id not in ids


def test_absent_context_window_is_reported_not_invented() -> None:
    build = build_registry(records())

    # The live API returns context_window: null for every model. Mapping that to a
    # plausible-looking number would be fabrication, so it stays 0 and is counted.
    assert build.report["models_missing_context_window"] >= 1
    assert "context_warning" in build.report
    assert all(model.context_tokens == 0 for model in build.models)

    # A unit that needs context therefore eliminates everything, loudly.
    task = TaskRequirements(task_id="IU-1", min_context_tokens=200_000)
    decision = route_model(task, build.models, build.providers)
    assert decision.selected is None
    assert any(
        "insufficient context" in reason
        for item in decision.eliminations
        for reason in item["reasons"]
    )


def test_context_overrides_make_routing_on_context_possible() -> None:
    target = next(
        record["id"]
        for record in records()
        if (record.get("inference") or {}).get("available") and record.get("providers")
    )
    build = build_registry(records(), context_window_overrides={target: 500_000})

    overridden = [model for model in build.models if model.equivalence_class == target]
    assert overridden and all(model.context_tokens == 500_000 for model in overridden)
    assert target in build.report["context_window_overrides_applied"]


def test_subscription_providers_become_zero_marginal_cost_direct_routes() -> None:
    build = build_registry(records(), subscription_provider_ids={"anthropic"})
    anthropic = [model for model in build.models if model.provider_id == "anthropic"]
    assert anthropic, "the fixture must contain an anthropic route"
    assert all(model.zero_marginal_cost for model in anthropic)
    assert all(model.per_attempt_cost == 0.0 for model in anthropic)
    provider = next(p for p in build.providers if p.provider_id == "anthropic")
    assert provider.provider_class == "direct_oauth"


def test_reseller_providers_are_classified_as_resellers() -> None:
    build = build_registry(records())
    classes = {p.provider_id: p.provider_class for p in build.providers}
    resellers = [pid for pid, cls in classes.items() if cls == "reseller"]
    for provider_id in resellers:
        assert provider_id in {
            "openrouter",
            "together",
            "fireworks",
            "deepinfra",
            "novita",
            "hyperbolic",
        }


def test_top_scores_become_the_benchmark_vector() -> None:
    build = build_registry(records())
    scored = [model for model in build.models if model.benchmarks]
    assert scored, "the fixture must contain scored models"
    for model in scored:
        assert all(isinstance(value, float) for value in model.benchmarks.values())
        assert model.confidence == 1.0


def test_the_build_report_records_its_cost_assumptions() -> None:
    build = build_registry(records(), input_tokens_per_attempt=1000, output_tokens_per_attempt=100)
    assumptions = build.report["assumptions"]
    assert assumptions["input_tokens_per_attempt"] == 1000
    assert assumptions["output_tokens_per_attempt"] == 100
    assert "estimate" in assumptions["note"]


def test_registry_feeds_the_router_end_to_end() -> None:
    build = build_registry(records(), subscription_provider_ids={"anthropic"})
    task = TaskRequirements(
        task_id="IU-1",
        role="worker",
        subscription_first=True,
        max_attempts=1,
        required_modalities=frozenset({"text"}),
    )
    decision = route_model(task, build.models, build.providers)

    assert decision.selected is not None
    # Subscription routes cost nothing marginal, so one of them must win.
    assert decision.selected.provider.provider_id == "anthropic"
    assert decision.explanation["subscription_first_applied"] is True
    assert decision.explanation["reseller_exception_required"] is False


# --- freshness ---------------------------------------------------------------


def now_minus(hours: float) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat().replace("+00:00", "Z")


def test_fresh_evidence_passes() -> None:
    age = assert_fresh(now_minus(2), max_age_hours=24.0, source="network", stale=False)
    assert 1.5 < age < 2.5


def test_stale_flagged_evidence_is_refused() -> None:
    with pytest.raises(RoutingError, match="flagged stale"):
        assert_fresh(now_minus(1), max_age_hours=24.0, source="stale_cache", stale=True)


def test_evidence_older_than_the_requirement_is_refused() -> None:
    with pytest.raises(RoutingError, match="older than"):
        assert_fresh(now_minus(80), max_age_hours=24.0, source="cache", stale=False)


def test_missing_timestamp_is_refused_rather_than_assumed_fresh() -> None:
    with pytest.raises(RoutingError, match="never"):
        assert_fresh(None, max_age_hours=24.0, source="cache", stale=False)


def test_the_refusal_names_the_fix() -> None:
    with pytest.raises(RoutingError, match="route refresh"):
        assert_fresh(now_minus(99), max_age_hours=1.0, source="cache", stale=False)
