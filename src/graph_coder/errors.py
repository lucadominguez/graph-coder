"""Domain-specific exceptions used across Graph Coder."""

from __future__ import annotations


class GraphCoderError(Exception):
    """Base class for expected Graph Coder failures."""


class ConfigurationError(GraphCoderError):
    """Raised when configuration is missing or invalid."""


class ContractError(GraphCoderError):
    """Raised when an artifact violates a versioned contract."""


class IntegrityError(GraphCoderError):
    """Raised when persisted state or a hash chain fails verification."""


class RoutingError(GraphCoderError):
    """Raised when no safe deterministic route can be selected."""


class CompatibilityError(GraphCoderError):
    """Raised when an adapter cannot provide a required capability."""
