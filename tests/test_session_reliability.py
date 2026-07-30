from __future__ import annotations

import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from types import ModuleType
from typing import ClassVar

import pytest

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load_helper() -> ModuleType:
    path = ROOT / "skills/routing-plan/scripts/llm_stats.py"
    spec = importlib.util.spec_from_file_location("aps_skill_llm_stats", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class StatsHandler(BaseHTTPRequestHandler):
    calls: ClassVar[list[dict[str, str]]] = []

    def do_GET(self) -> None:
        self.__class__.calls.append(
            {"path": self.path, "authorization": self.headers.get("Authorization", "")}
        )
        payload = {"data": [{"model_id": "open/test-model"}], "next": None}
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture()
def stats_server() -> str:
    StatsHandler.calls = []
    server = HTTPServer(("127.0.0.1", 0), StatsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/api/v1"
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_rehearsal_requires_complete_persisted_independent_reports() -> None:
    text = read("skills/plan-rehearsal/SKILL.md")
    for required in (
        "complete persisted report artifact",
        "truncated",
        "superseded",
        "different model families or providers",
        "exact producer artifact",
        "every affected consumer rehearsal is rerun",
        "After a server reload",
    ):
        assert required in text


def test_execution_monitoring_is_uncapped_truthful_and_reload_safe() -> None:
    text = read("skills/execution-manager/SKILL.md")
    for required in (
        "30 seconds",
        "cancel, continue, or fallback",
        "more than 30",
        "Never emit a `+N more`",
        "exact provider and model route",
        "`not exposed`",
        "ETA only when",
        "After a server reload",
        "every metered service",
    ):
        assert required in text


def test_routing_enforces_user_constraints_and_whole_service_budget() -> None:
    text = read("skills/routing-plan/SKILL.md")
    for required in (
        "user's provider, model, subscription, budget, and diversity constraints",
        "exhausted or excluded provider",
        "already eligible through the user's direct subscription",
        "all metered services",
        "scripts/llm_stats.py",
    ):
        assert required in text


def test_llm_stats_skill_helper_fetches_json_without_persisting_secret(
    stats_server: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    helper = load_helper()
    monkeypatch.setenv("LLM_STATS_API_KEY", "test-secret")
    cache = tmp_path / "llm-stats.json"

    result = helper.main(
        ["--base-url", stats_server, "--cache", str(cache), "models", "--param", "limit=1"]
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "network"
    assert payload["stale"] is False
    assert payload["records"] == [{"model_id": "open/test-model"}]
    assert StatsHandler.calls == [
        {"path": "/api/v1/models?limit=1", "authorization": "Bearer test-secret"}
    ]
    assert "test-secret" not in cache.read_text(encoding="utf-8")


def test_llm_stats_skill_helper_rejects_bad_parameter(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    helper = load_helper()
    monkeypatch.setenv("LLM_STATS_API_KEY", "unused")

    assert helper.main(["models", "--param", "invalid"]) == 2
    assert "expected KEY=VALUE" in capsys.readouterr().err
