from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar

import pytest

from graph_coder.llm_stats import (
    DEFAULT_API_BASE,
    LLMStatsClient,
    LLMStatsError,
    LLMStatsSchemaError,
)


class FakeStatsHandler(BaseHTTPRequestHandler):
    calls: ClassVar[list[dict[str, str]]] = []
    responses: ClassVar[list[tuple[int, dict[str, str], dict[str, object]]]] = []

    def do_GET(self) -> None:
        self.__class__.calls.append(
            {"path": self.path, "auth": self.headers.get("Authorization", "")}
        )
        status, headers, payload = self.__class__.responses.pop(0)
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture()
def fake_server() -> str:
    FakeStatsHandler.calls = []
    FakeStatsHandler.responses = []
    server = HTTPServer(("127.0.0.1", 0), FakeStatsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/api/v1"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_default_base_and_env_only_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LLMStatsClient()
    assert client.base_url == DEFAULT_API_BASE + "/"
    assert not hasattr(client, "api_key")
    monkeypatch.delenv("LLM_STATS_API_KEY", raising=False)
    with pytest.raises(LLMStatsError, match="LLM_STATS_API_KEY"):
        client.fetch_models()


def test_bearer_auth_pagination_timeout_and_cache(
    fake_server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_STATS_API_KEY", "secret-token")
    FakeStatsHandler.responses = [
        (200, {}, {"data": [{"model_id": "a"}], "next": "/api/v1/models?page=2"}),
        (200, {}, {"data": [{"model_id": "b"}], "next": None}),
    ]
    cache = tmp_path / "models.json"
    client = LLMStatsClient(base_url=fake_server, timeout=1.25, cache_path=cache, now=lambda: 100.0)

    result = client.fetch_models_with_cache()

    assert [item["model_id"] for item in result.records] == ["a", "b"]
    assert result.source == "network"
    assert result.stale is False
    assert [call["auth"] for call in FakeStatsHandler.calls] == [
        "Bearer secret-token",
        "Bearer secret-token",
    ]
    assert FakeStatsHandler.calls[0]["path"] == "/api/v1/models"
    assert FakeStatsHandler.calls[1]["path"] == "/api/v1/models?page=2"
    cache_text = cache.read_text(encoding="utf-8")
    assert "secret-token" not in cache_text
    assert list(tmp_path.glob(".models.json.*")) == []

    FakeStatsHandler.responses = []
    cached = client.fetch_models_with_cache()
    assert cached.source == "cache"
    assert cached.stale is False
    assert len(FakeStatsHandler.calls) == 2


def test_expired_cache_refresh_failure_returns_explicit_stale(
    fake_server: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_STATS_API_KEY", "secret-token")
    cache = tmp_path / "models.json"
    cache.write_text(
        json.dumps(
            {
                "records": [{"model_id": "old"}],
                "source": "network",
                "stale": False,
                "fetched_at": 1,
                "expires_at": 2,
            }
        ),
        encoding="utf-8",
    )
    FakeStatsHandler.responses = [(500, {}, {"error": "nope"})]
    sleeps: list[float] = []
    client = LLMStatsClient(
        base_url=fake_server,
        cache_path=cache,
        now=lambda: 100.0,
        max_retries=0,
        sleep=sleeps.append,
    )

    result = client.fetch_models_with_cache()

    assert result.records == [{"model_id": "old"}]
    assert result.source == "stale_cache"
    assert result.stale is True


def test_429_retry_after_and_bounded_retry(
    fake_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_STATS_API_KEY", "secret-token")
    FakeStatsHandler.responses = [
        (429, {"Retry-After": "3"}, {"error": "slow down"}),
        (200, {}, {"data": [{"model_id": "ok"}], "next": None}),
    ]
    sleeps: list[float] = []
    client = LLMStatsClient(base_url=fake_server, max_retries=1, sleep=sleeps.append)

    assert client.fetch_models() == [{"model_id": "ok"}]
    assert sleeps == [3.0]
    assert len(FakeStatsHandler.calls) == 2


def test_schema_validation(fake_server: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_STATS_API_KEY", "secret-token")
    FakeStatsHandler.responses = [(200, {}, {"data": [{"name": "missing-model-id"}], "next": None})]
    client = LLMStatsClient(base_url=fake_server)

    with pytest.raises(LLMStatsSchemaError, match="model_id"):
        client.fetch_models()


def test_provisional_documented_endpoint_mapping(
    fake_server: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("LLM_STATS_API_KEY", "secret-token")
    FakeStatsHandler.responses = [
        (200, {}, {"data": {"model_id": "open/model"}}),
        (200, {}, {"data": [{"model_id": "open/model", "rank": 1}]}),
        (200, {}, {"data": [{"model_id": "new/model"}]}),
        (200, {}, {"data": [{"benchmark": "coding", "score": 0.9}]}),
    ]
    client = LLMStatsClient(base_url=fake_server)

    assert client.fetch_model("open/model")["model_id"] == "open/model"
    assert client.fetch_rankings("coding")[0]["rank"] == 1
    assert client.fetch_recent()[0]["model_id"] == "new/model"
    assert client.fetch_benchmarks("open/model")[0]["score"] == 0.9
    assert [call["path"] for call in FakeStatsHandler.calls] == [
        "/api/v1/models/open%2Fmodel",
        "/api/v1/rankings/coding",
        "/api/v1/models/recent",
        "/api/v1/models/open%2Fmodel/benchmarks",
    ]
