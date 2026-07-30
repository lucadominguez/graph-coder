#!/usr/bin/env python3
"""Secret-safe, noninteractive LLM Stats helper shipped with the routing skill."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from graph_coder.llm_stats import (
    DEFAULT_API_BASE,
    LLMStatsClient,
    LLMStatsError,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_API_BASE)
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--max-retries", type=int, default=2)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--cache-ttl", type=float, default=3600.0)
    subparsers = parser.add_subparsers(dest="command", required=True)

    models = subparsers.add_parser("models", help="Fetch paginated model records")
    models.add_argument("--endpoint", default="models")
    models.add_argument(
        "--param",
        action="append",
        default=[],
        metavar="KEY=VALUE",
        help="Repeatable model-list query parameter",
    )

    model = subparsers.add_parser("model", help="Fetch one model record")
    model.add_argument("model_id")

    rankings = subparsers.add_parser("rankings", help="Fetch one ranking category")
    rankings.add_argument("category")

    subparsers.add_parser("recent", help="Fetch recently added models")

    benchmarks = subparsers.add_parser("benchmarks", help="Fetch model benchmark records")
    benchmarks.add_argument("model_id")
    return parser


def _params(values: list[str]) -> dict[str, str]:
    params: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key:
            raise ValueError(f"invalid --param {value!r}; expected KEY=VALUE")
        params[key] = item
    return params


def _emit(payload: Any) -> None:
    json.dump(payload, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    client = LLMStatsClient(
        base_url=args.base_url,
        timeout=args.timeout,
        max_retries=args.max_retries,
        cache_path=args.cache,
        cache_ttl_seconds=args.cache_ttl,
    )
    try:
        if args.command == "models":
            result = client.fetch_models_with_cache(
                endpoint=args.endpoint,
                params=_params(args.param),
            )
            _emit(
                {
                    "records": result.records,
                    "source": result.source,
                    "stale": result.stale,
                    "fetched_at": result.fetched_at,
                    "expires_at": result.expires_at,
                }
            )
        elif args.command == "model":
            _emit(client.fetch_model(args.model_id))
        elif args.command == "rankings":
            _emit(client.fetch_rankings(args.category))
        elif args.command == "recent":
            _emit(client.fetch_recent())
        elif args.command == "benchmarks":
            _emit(client.fetch_benchmarks(args.model_id))
        else:  # pragma: no cover - argparse enforces the command choices
            raise AssertionError(f"unsupported command: {args.command}")
    except (LLMStatsError, ValueError) as exc:
        print(f"llm-stats: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
