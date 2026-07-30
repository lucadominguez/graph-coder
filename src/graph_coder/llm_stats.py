"""LLM Stats API client with deterministic, secret-safe caching."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin
from urllib.request import Request, urlopen

from .config import atomic_write

DEFAULT_API_BASE = "https://llm-stats.com/api/v1"
API_KEY_ENV = "LLM_STATS_API_KEY"


class LLMStatsError(RuntimeError):
    """Base LLM Stats client error."""


class LLMStatsSchemaError(LLMStatsError):
    """Raised when the API payload does not match the expected shape."""


@dataclass(frozen=True)
class CacheResult:
    records: list[dict[str, Any]]
    source: str
    stale: bool
    fetched_at: float | None = None
    expires_at: float | None = None


class LLMStatsClient:
    """Small stdlib-only client for the provisional LLM Stats API.

    The API key is read exclusively from ``LLM_STATS_API_KEY`` when requests are
    made. It is never stored on the client and never serialized to cache.
    """

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_API_BASE,
        timeout: float = 10.0,
        max_retries: int = 2,
        retry_backoff: float = 0.25,
        cache_path: str | Path | None = None,
        cache_ttl_seconds: float = 3600.0,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.base_url = base_url.rstrip("/") + "/"
        self.timeout = timeout
        self.max_retries = max(0, max_retries)
        self.retry_backoff = max(0.0, retry_backoff)
        self.cache_path = Path(cache_path) if cache_path is not None else None
        self.cache_ttl_seconds = cache_ttl_seconds
        self._sleep = sleep
        self._now = now

    def fetch_models(
        self, *, endpoint: str = "models", params: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Fetch all paginated model capability/stat records."""
        return self.fetch_models_with_cache(endpoint=endpoint, params=params).records

    def fetch_model(self, model_id: str) -> dict[str, Any]:
        payload = self._request_json(self._url(f"models/{quote(model_id, safe='')}", {}))
        value = payload.get("data", payload)
        if not isinstance(value, dict):
            raise LLMStatsSchemaError("LLM Stats model response must contain an object")
        identifier = value.get("model_id", value.get("id"))
        if not isinstance(identifier, str) or not identifier:
            raise LLMStatsSchemaError("LLM Stats model requires model_id/id")
        return dict(value)

    def fetch_rankings(self, category: str) -> list[dict[str, Any]]:
        return self._fetch_collection(f"rankings/{quote(category, safe='')}", "model_id")

    def fetch_recent(self) -> list[dict[str, Any]]:
        return self._fetch_collection("models/recent", "model_id")

    def fetch_benchmarks(self, model_id: str) -> list[dict[str, Any]]:
        return self._fetch_collection(f"models/{quote(model_id, safe='')}/benchmarks", None)

    def fetch_models_with_cache(
        self, *, endpoint: str = "models", params: dict[str, Any] | None = None
    ) -> CacheResult:
        cached = self._read_cache()
        now = float(self._now())
        if cached and cached.expires_at is not None and cached.expires_at > now:
            return CacheResult(cached.records, "cache", False, cached.fetched_at, cached.expires_at)
        try:
            records = self._fetch_paginated(endpoint, params or {})
            result = CacheResult(records, "network", False, now, now + self.cache_ttl_seconds)
            self._write_cache(result)
            return result
        except Exception:
            if cached:
                return CacheResult(
                    cached.records, "stale_cache", True, cached.fetched_at, cached.expires_at
                )
            raise

    def _fetch_paginated(self, endpoint: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        url: str | None = self._url(endpoint, params)
        records: list[dict[str, Any]] = []
        while url:
            payload = self._request_json(url)
            page_records, next_url = self._validate_page(payload)
            records.extend(page_records)
            url = self._absolute_next(next_url)
        return records

    def _fetch_collection(self, endpoint: str, required_key: str | None) -> list[dict[str, Any]]:
        payload = self._request_json(self._url(endpoint, {}))
        raw_items = payload.get("data", payload.get("results"))
        if not isinstance(raw_items, list):
            raise LLMStatsSchemaError("LLM Stats collection requires data/results list")
        items: list[dict[str, Any]] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                raise LLMStatsSchemaError(f"LLM Stats item {index} must be an object")
            if required_key and (
                not isinstance(item.get(required_key), str) or not item[required_key]
            ):
                raise LLMStatsSchemaError(f"LLM Stats item {index} requires {required_key}")
            items.append(dict(item))
        return items

    def _request_json(self, url: str) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            key = os.environ.get(API_KEY_ENV)
            if not key:
                raise LLMStatsError(f"{API_KEY_ENV} is required")
            request = Request(
                url, headers={"Authorization": f"Bearer {key}", "Accept": "application/json"}
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8")
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise LLMStatsSchemaError("LLM Stats response must be a JSON object")
                return payload
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504} or attempt >= self.max_retries:
                    raise LLMStatsError(f"LLM Stats request failed with HTTP {exc.code}") from exc
                self._sleep(self._retry_delay(exc, attempt))
            except (TimeoutError, URLError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise LLMStatsError("LLM Stats request failed") from exc
                self._sleep(self.retry_backoff * (2**attempt))
        raise LLMStatsError("LLM Stats request failed") from last_error

    def _retry_delay(self, exc: HTTPError, attempt: int) -> float:
        value = exc.headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                try:
                    return max(0.0, parsedate_to_datetime(value).timestamp() - float(self._now()))
                except (TypeError, ValueError):
                    pass
        return float(self.retry_backoff * (2**attempt))

    def _url(self, endpoint: str, params: dict[str, Any]) -> str:
        query = f"?{urlencode(params)}" if params else ""
        return urljoin(self.base_url, endpoint.lstrip("/")) + query

    def _absolute_next(self, next_url: str | None) -> str | None:
        if not next_url:
            return None
        return urljoin(self.base_url, next_url)

    @staticmethod
    def _validate_page(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], str | None]:
        raw_items = payload.get("data", payload.get("results"))
        if not isinstance(raw_items, list):
            raise LLMStatsSchemaError("LLM Stats page requires data/results list")
        items: list[dict[str, Any]] = []
        for index, item in enumerate(raw_items):
            if not isinstance(item, dict):
                raise LLMStatsSchemaError(f"LLM Stats item {index} must be an object")
            if not isinstance(item.get("model_id"), str) or not item["model_id"]:
                raise LLMStatsSchemaError(f"LLM Stats item {index} requires model_id")
            items.append(dict(item))
        next_url = payload.get("next")
        if next_url is not None and not isinstance(next_url, str):
            raise LLMStatsSchemaError("LLM Stats next must be string or null")
        return items, next_url

    def _read_cache(self) -> CacheResult | None:
        if self.cache_path is None or not self.cache_path.exists():
            return None
        payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        records = payload.get("records")
        if not isinstance(records, list) or not all(isinstance(item, dict) for item in records):
            return None
        return CacheResult(
            [dict(item) for item in records],
            str(payload.get("source", "cache")),
            bool(payload.get("stale", False)),
            float(payload["fetched_at"])
            if isinstance(payload.get("fetched_at"), int | float)
            else None,
            float(payload["expires_at"])
            if isinstance(payload.get("expires_at"), int | float)
            else None,
        )

    def _write_cache(self, result: CacheResult) -> None:
        if self.cache_path is None:
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "records": result.records,
            "source": result.source,
            "stale": result.stale,
            "fetched_at": result.fetched_at,
            "expires_at": result.expires_at,
        }
        atomic_write(self.cache_path, json.dumps(payload, sort_keys=True))
