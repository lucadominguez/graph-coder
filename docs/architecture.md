# Architecture

Graph Coder separates subjective reasoning from deterministic control.

- The root JCode session is the **Director**. It owns intent, approval, the canonical plan, and coordinator-gated graph mutations.
- Agent Skills conduct the concept grill, planning, specialist review, cold rehearsal, graph compilation, routing, and execution management.
- Python owns persisted lifecycle state, schemas, hashes, snapshots, budgets, deterministic route selection, graph validation, and recovery.
- JCode owns worker execution. Graph Coder v1 emits Director-mediated task-graph operation bundles and does not use JCode's private local socket protocol.

## Compatibility decisions

1. `/aps-plan` is the orchestration command because JCode v0.55.0 dispatches built-ins before skill lookup, so `/plan` cannot be safely overridden.
2. The execution manager is advisory. The Director applies graph changes that JCode reserves for the root coordinator.
3. Routing uses environment-only LLM Stats authentication and records source data, freshness, calculations, and eliminations.
4. Expected passing cost uses a bounded geometric primary-attempt model plus failure-weighted fallback cost.
5. YAML and JSON Schema are handled by small audited runtime dependencies.
6. JCode's installed LLM Stats client is provisional schema evidence until live API validation succeeds.

## State ownership

Authoritative project state lives in `.graph-coder/state.db`. Human-readable projections, snapshots, caches, context packets, and artifacts are derived from that database or content-addressed source files. SQLite uses WAL mode, foreign keys, explicit migrations, short transactions, and a busy timeout.
