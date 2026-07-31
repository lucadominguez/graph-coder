"""Build a router model registry from live LLM Stats records.

This is the bridge that was missing: `route refresh` fetches and caches, and this
module turns those records into the `ModelCapabilities` and `ProviderCapabilities`
the router scores. Without it, someone had to hand-assemble a routing profile and
the router never saw real model data.

Two honest limitations are surfaced rather than papered over:

1. **The API reports no context window.** Every one of the 335 models returned by
   `/stats/v1/models` on 2026-07-30 had `context_window: null`. A unit that
   declares `min_context_tokens` will therefore eliminate every candidate unless
   the caller supplies `context_window_overrides`. The build reports how many
   models lacked the field so the elimination is explicable rather than baffling.

2. **Per-attempt cost is derived, not reported.** The API gives
   `input_price_per_m` and `output_price_per_m` per provider. Converting those to
   a per-attempt cost requires assuming how many tokens an attempt spends, so the
   assumption is an explicit, recorded input.

3. **`top_scores` values are not on a common scale.** Categories carry whatever
   unit their leading benchmark uses: `code` and `tool_calling` arrive in 0..1
   while `reasoning` and `general` arrive near 150 and `finance` and `legal` near
   900. The router scores a weighted mean and bounds it to 0..1, so feeding raw
   values pinned every model weighted on a large-scale category to exactly 1.0,
   which silently destroyed discrimination and handed the decision to the
   tie-breakers. Values are normalized per category against the candidate field
   before they reach the router, and the bounds used are recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .errors import RoutingError
from .routing import ModelCapabilities, ProviderCapabilities

#: Provider classes we can infer. A direct first-party provider is treated as a
#: subscription route candidate; anything reselling other organizations' models is
#: a reseller. Everything else stays a plain direct API.
RESELLER_PROVIDER_IDS: frozenset[str] = frozenset(
    {"openrouter", "together", "fireworks", "deepinfra", "novita", "hyperbolic"}
)

#: Token spend assumed for one implementation attempt, used only to turn published
#: per-million prices into a comparable per-attempt cost. These are estimates and
#: are recorded in the build report.
DEFAULT_INPUT_TOKENS_PER_ATTEMPT = 40_000
DEFAULT_OUTPUT_TOKENS_PER_ATTEMPT = 8_000


#: Scores that cannot discriminate get this. It is deliberately the midpoint: a
#: category only one model reports, or one where every model scored identically,
#: is evidence of nothing, and both 0.0 and 1.0 would be claims the data does not
#: support.
NEUTRAL_BENCHMARK_SCORE = 0.5

#: A category whose largest value exceeds its smallest by more than this factor is
#: almost certainly carrying two different benchmarks under one name. Chosen well
#: above the spread any single benchmark produces across models, and well below
#: the ~700x seen in `reasoning` on live data.
MIXED_UNIT_RATIO = 50.0


@dataclass(frozen=True)
class BenchmarkScale:
    """The observed range of one `top_scores` category across the candidate field.

    Recorded so a route is auditable and reproducible: the same records always
    produce the same bounds, and a receipt can show what a normalized score was
    measured against.
    """

    category: str
    minimum: float
    maximum: float
    count: int

    @property
    def degenerate(self) -> bool:
        """True when the category cannot rank anything."""

        return self.count < 2 or self.maximum <= self.minimum

    @property
    def suspect_mixed_units(self) -> bool:
        """True when one category's own values look like two different benchmarks.

        `reasoning` arrived spanning 0.6 to 419.1 on real data. A single benchmark
        does not produce that, so the low scorer is probably measured on a
        different one rather than being 700 times worse. Normalizing still ranks
        them, and ranking them is still wrong, so the spread is reported instead
        of being quietly averaged away.
        """

        return (
            not self.degenerate
            and self.minimum > 0
            and self.maximum / self.minimum > MIXED_UNIT_RATIO
        )

    def normalize(self, value: float) -> float:
        if self.degenerate:
            return NEUTRAL_BENCHMARK_SCORE
        span = self.maximum - self.minimum
        return min(1.0, max(0.0, (value - self.minimum) / span))

    def to_dict(self) -> dict[str, Any]:
        return {
            "min": self.minimum,
            "max": self.maximum,
            "models": self.count,
            "degenerate": self.degenerate,
            "suspect_mixed_units": self.suspect_mixed_units,
        }


def _is_scoreable(value: Any) -> bool:
    """A usable benchmark value: a real number, not a bool, not NaN or infinite."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    numeric = float(value)
    return numeric == numeric and numeric not in (float("inf"), float("-inf"))


def benchmark_scales(
    records: list[dict[str, Any]], *, require_inference_available: bool = True
) -> dict[str, BenchmarkScale]:
    """Measure each `top_scores` category across the models that can be routed to.

    The population is the candidate field, not every record: a model filtered out
    for unavailable inference is not something the router may choose, so letting
    it set the bounds would rank the survivors against an option nobody has.
    """

    populations: dict[str, list[float]] = {}
    for record in records:
        inference = record.get("inference") or {}
        if require_inference_available and not inference.get("available"):
            continue
        for name, value in (record.get("top_scores") or {}).items():
            if _is_scoreable(value):
                populations.setdefault(str(name), []).append(float(value))
    return {
        category: BenchmarkScale(
            category=category,
            minimum=min(values),
            maximum=max(values),
            count=len(values),
        )
        for category, values in populations.items()
    }


@dataclass(frozen=True)
class RegistryBuild:
    """The router inputs plus everything a human needs to trust them."""

    models: list[ModelCapabilities]
    providers: list[ProviderCapabilities]
    report: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "models": [model.model_id for model in self.models],
            "providers": [provider.provider_id for provider in self.providers],
            "report": self.report,
        }


def _age_hours(timestamp: str | float | int | None, *, now: datetime | None = None) -> float:
    """Age of a timestamp in hours.

    Accepts both shapes the codebase produces: an ISO-8601 string, as the API
    reports on each model record, and epoch seconds, as the LLM Stats cache writes
    for `fetched_at`. An unusable value is treated as infinitely old rather than as
    fresh, so a malformed cache fails the freshness gate instead of passing it.
    """

    if timestamp is None or timestamp == "":
        return float("inf")
    reference = now or datetime.now(UTC)
    if isinstance(timestamp, (int, float)):
        parsed = datetime.fromtimestamp(float(timestamp), tz=UTC)
    else:
        try:
            parsed = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
        except ValueError:
            return float("inf")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return max(0.0, (reference - parsed).total_seconds() / 3600.0)


def _provider_class(provider_id: str, model_organization: str) -> str:
    if provider_id in RESELLER_PROVIDER_IDS:
        return "reseller"
    if provider_id == model_organization:
        # First-party: the organization that made the model is serving it.
        return "direct_oauth"
    return "direct_api"


def per_attempt_cost(
    input_price_per_m: float | None,
    output_price_per_m: float | None,
    *,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Convert published per-million prices into a per-attempt dollar cost."""

    input_rate = float(input_price_per_m or 0.0)
    output_rate = float(output_price_per_m or 0.0)
    return (input_rate * input_tokens + output_rate * output_tokens) / 1_000_000.0


def build_registry(
    records: list[dict[str, Any]],
    *,
    subscription_provider_ids: frozenset[str] | set[str] = frozenset(),
    context_window_overrides: dict[str, int] | None = None,
    input_tokens_per_attempt: int = DEFAULT_INPUT_TOKENS_PER_ATTEMPT,
    output_tokens_per_attempt: int = DEFAULT_OUTPUT_TOKENS_PER_ATTEMPT,
    require_inference_available: bool = True,
    now: datetime | None = None,
) -> RegistryBuild:
    """Turn `/stats/v1/models` records into router inputs.

    One `ModelCapabilities` is emitted per (model, provider) pair, because that is
    the unit the router actually chooses between: the same model served directly and
    through a reseller are two different routes with two different prices, which is
    exactly what subscription-first precedence exists to compare.
    """

    overrides = context_window_overrides or {}
    scales = benchmark_scales(records, require_inference_available=require_inference_available)
    models: list[ModelCapabilities] = []
    providers: dict[str, ProviderCapabilities] = {}

    missing_context: list[str] = []
    missing_price: list[str] = []
    no_providers: list[str] = []
    skipped_unavailable: list[str] = []

    for record in records:
        model_id = str(record.get("id") or "")
        if not model_id:
            continue

        inference = record.get("inference") or {}
        if require_inference_available and not inference.get("available"):
            skipped_unavailable.append(model_id)
            continue

        organization = str((record.get("organization") or {}).get("id") or "")
        context_window = record.get("context_window") or overrides.get(model_id)
        if not record.get("context_window"):
            missing_context.append(model_id)

        # top_scores is {category: raw_score}, and the units differ per category,
        # so every value is normalized against the field before the router sees
        # it. See BenchmarkScale and limitation 3 in the module docstring.
        benchmarks = {
            str(name): scales[str(name)].normalize(float(value))
            for name, value in (record.get("top_scores") or {}).items()
            if _is_scoreable(value) and str(name) in scales
        }

        tools: frozenset[str] = frozenset()
        if inference.get("supports_tools"):
            tools = frozenset({"edit", "bash", "read"})

        modalities = frozenset(str(item) for item in (record.get("modalities") or ["text"]))
        updated_at = record.get("updated_at")

        entries = record.get("providers") or []
        if not entries:
            no_providers.append(model_id)
            continue

        for entry in entries:
            provider_id = str(entry.get("provider_id") or "")
            if not provider_id or entry.get("status") not in (None, "active"):
                continue

            if entry.get("input_price_per_m") is None:
                missing_price.append(f"{model_id}@{provider_id}")

            latency_s = entry.get("latency_s")
            cost = per_attempt_cost(
                entry.get("input_price_per_m"),
                entry.get("output_price_per_m"),
                input_tokens=input_tokens_per_attempt,
                output_tokens=output_tokens_per_attempt,
            )
            provider_class = _provider_class(provider_id, organization)
            zero_marginal = provider_id in set(subscription_provider_ids)

            providers.setdefault(
                provider_id,
                ProviderCapabilities(
                    provider_id=provider_id,
                    authenticated=True,
                    reliability=1.0,
                    provider_class=(
                        "direct_oauth" if zero_marginal else provider_class
                    ),
                ),
            )
            models.append(
                ModelCapabilities(
                    # The route identity is the model-and-provider pair.
                    model_id=f"{provider_id}:{model_id}",
                    provider_id=provider_id,
                    context_tokens=int(context_window or 0),
                    output_tokens=int(record.get("max_output_tokens") or 0),
                    tools=tools,
                    modalities=modalities,
                    streaming=bool(inference.get("supports_streaming")),
                    model_class=str(record.get("model_type") or "llm"),
                    per_attempt_cost=0.0 if zero_marginal else cost,
                    # Evidence confidence: LLM Stats normalizes its own scores, and
                    # we have no independent verification here, so this is a flat
                    # prior rather than an invented per-model number.
                    confidence=1.0 if benchmarks else 0.0,
                    latency_ms=float(latency_s) * 1000.0 if latency_s else float("inf"),
                    open_weight=bool(record.get("open_weight")),
                    benchmarks=benchmarks,
                    evidence_age_hours=_age_hours(updated_at, now=now),
                    zero_marginal_cost=zero_marginal,
                    equivalence_class=model_id,
                )
            )

    report = {
        "records_in": len(records),
        "routes_out": len(models),
        "providers_out": len(providers),
        "assumptions": {
            "input_tokens_per_attempt": input_tokens_per_attempt,
            "output_tokens_per_attempt": output_tokens_per_attempt,
            "note": (
                "per_attempt_cost is derived from published per-million prices and "
                "these assumed token counts; it is an estimate"
            ),
        },
        "models_missing_context_window": len(missing_context),
        "models_missing_context_window_sample": sorted(missing_context)[:5],
        "context_window_overrides_applied": sorted(
            set(overrides) & {m.split(":", 1)[1] for m in (x.model_id for x in models)}
        ),
        "routes_missing_price": sorted(set(missing_price))[:10],
        "models_without_providers": len(no_providers),
        "models_skipped_inference_unavailable": len(skipped_unavailable),
        "subscription_provider_ids": sorted(set(subscription_provider_ids)),
        "benchmark_normalization": "min_max_per_category",
        "benchmark_scales": {
            category: scale.to_dict() for category, scale in sorted(scales.items())
        },
    }
    degenerate = sorted(category for category, scale in scales.items() if scale.degenerate)
    if degenerate:
        report["benchmark_warning"] = (
            f"{len(degenerate)} benchmark categories cannot rank anything, because "
            "fewer than two models report them or every model scored the same. "
            f"Weighting these contributes a flat {NEUTRAL_BENCHMARK_SCORE} to every "
            f"candidate: {', '.join(degenerate[:5])}"
        )
    mixed = sorted(category for category, scale in scales.items() if scale.suspect_mixed_units)
    if mixed:
        report["benchmark_mixed_unit_warning"] = (
            f"{len(mixed)} categories span more than {MIXED_UNIT_RATIO:g}x from "
            "smallest to largest, which is more than one benchmark produces. Models "
            "scored low in these may be measured on a different benchmark rather "
            f"than being worse: {', '.join(mixed[:5])}"
        )
    if missing_context:
        report["context_warning"] = (
            f"{len(missing_context)} models report no context_window. Any unit that "
            "declares min_context_tokens will eliminate them. Supply "
            "context_window_overrides to route on context."
        )
    return RegistryBuild(
        models=models,
        providers=sorted(providers.values(), key=lambda item: item.provider_id),
        report=report,
    )


def assert_fresh(
    fetched_at: str | float | int | None,
    *,
    max_age_hours: float,
    source: str,
    stale: bool,
) -> float:
    """Refuse to route on stale model evidence.

    Routing decides how the user's money is spent. Doing that on a week-old price
    table, or on a cache the client already flagged stale, is worse than stopping
    and asking for a refresh.
    """

    age = _age_hours(fetched_at)
    if stale or source == "stale_cache":
        raise RoutingError(
            "LLM Stats evidence is flagged stale: run `graph-coder route refresh` "
            "before assigning routes"
        )
    if age > max_age_hours:
        rendered = "never" if age == float("inf") else f"{age:.1f}h ago"
        raise RoutingError(
            f"LLM Stats evidence is {rendered}, older than the {max_age_hours:.1f}h "
            "freshness requirement: run `graph-coder route refresh`"
        )
    return age
