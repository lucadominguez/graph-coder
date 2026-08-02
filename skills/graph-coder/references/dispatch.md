# Dispatch

How phase 10 actually puts work into subagents. The orchestrator skill states the
rule; this file is the mechanism, so there is no step left for the Director to
invent.

The rule it serves: **every dispatchable node runs in its own spawned subagent,
and the Director never implements one itself.**

## The emitted bundle

`graph-coder jcode emit --graph <graph>` returns two operations plus the worker
report schema.

```json
{
  "ok": true,
  "compatibility": {"adapter": "jcode", "detected_version": "...", "compatible": true},
  "operations": [
    {"tool": "swarm", "action": "task_graph", "arguments": {...}},
    {"tool": "swarm", "action": "run_plan", "arguments": {...}}
  ],
  "report_schema": {...}
}
```

`task_graph.arguments.nodes` is the spawn list. One entry per dispatchable node,
already excluding the Director and every manager, because those are control-plane
agents rather than work:

```json
{
  "id": "IU-MIGRATION",
  "content": "Graph Coder node IU-MIGRATION: Revocation columns and audit table\nSubmit your report to manager M-STORAGE for review. Only its passing review completes this node; you do not mark yourself complete.\nPortable kind: implement; native kind: implement.\nRead scopes: [...]\nWrite scopes: [...]\nAcceptance: [...]\nReview checklist: [...]\n<unit prompt>\n<report template>",
  "kind": "implement",
  "depends_on": [],
  "priority": "high",
  "model": "<routed model>",
  "metadata": {"review_owner": "M-STORAGE", "read_scopes": [...], "write_scopes": [...], "max_attempts": 2, ...}
}
```

`content` is the whole worker packet: objective, scopes, procedure, verification
commands, acceptance, review contract, and the report template. It is already
bounded by the context contract. Send it verbatim. Rewriting it in your own words
is how scope leaks in and how a worker ends up reviewing itself.

`task_graph.arguments.metadata.managers` lists the advisory managers with their
review assignments and their empty `write_scopes`. `run_plan.arguments` carries
the Director prompt, the background and notify flags, and `concurrency_limit`.

## Spawning

One subagent per ready node, one parallel round per frontier.

**JCode.** Issue the two emitted operations through the public `swarm` tool:
`task_graph` to register the graph, then `run_plan` with `background: true` to
run it under Director control. The adapter targets JCode 0.55 and depends on no
private socket. Check `compatibility.compatible` first; if it is false, say so
and stop rather than dispatching into a version that will not honor the contract.

**Any other harness with a subagent tool**, Claude Code included: skip `run_plan`
and make one subagent call per entry in `task_graph.arguments.nodes`. Prompt is
that entry's `content`. Model is its `model` when present, otherwise the routed
model from the route receipt. Issue every ready node's call in a single message so
the round is genuinely parallel.

**No subagent tool at all.** Then this harness cannot run a Graph Coder graph.
Say that plainly and stop. Do not silently degrade into implementing the plan
yourself in the root session, which produces a plausible diff with none of the
isolation, review, or cost properties the plan was approved on.

## Round discipline

```text
frontier = nodes whose dependencies all reached completed through a passing review
spawn    = one subagent per frontier node, capped at max_active_workers (8)
overflow = queued, not dropped, not serialized by preference
```

- Record a dispatch event per spawn before relying on it.
- A worker returns a report. A report is not a completion. Route it to its
  `review_owner`.
- Recompute the frontier only after review verdicts land, because only a `pass`
  makes dependents eligible.
- Repairs are spawns too: a bounded repair goes to a worker subagent, never to the
  manager and never to the Director.

## Self-check

Before reporting execution finished, confirm all of these:

- [ ] The number of subagents spawned is at least the number of dispatchable nodes.
- [ ] No implementation file was written by the root session during phase 10.
- [ ] Every completed node has a manager review artifact with acceptance results.
- [ ] Every spawn used its emitted packet, not a summary of it.
- [ ] Rounds were parallel where the frontier allowed it.

Any unchecked box means the graph was not executed. Report that instead of
reporting success.
