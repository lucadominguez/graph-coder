# Dispatch

How phase 10 actually puts work into subagents. The orchestrator skill states the
rule; this file is the mechanism, so there is no step left for the Director to
invent.

The rule it serves: **every dispatchable node runs in its own spawned subagent,
and the Director never implements one itself.**

## Preflight

Do these three before spawning anything. Each one corresponds to a way a real run
has already failed.

Checks 2 and 3 are machine-checkable, so do not eyeball them. `graph-coder jcode
emit` returns a `preflight` block:

```json
"preflight": {
  "ready_to_dispatch": false,
  "dispatchable_nodes": 4,
  "unrouted_nodes": ["IU-ENDPOINT", "IU-MIGRATION", "IU-SCHEMA", "IU-STORE"],
  "non_visible_nodes": [],
  "warnings": ["4 nodes carry a placeholder route instead of a routed model, which means MODEL_ROUTING was skipped. ..."]
}
```

`ready_to_dispatch: false` means the graph will run, but not the run that was
approved. Fix what the warnings name and re-emit. Do not dispatch past it.

1. **Clear stale swarm state.** `swarm cleanup --force`. Plan nodes from an earlier
   session survive in the swarm and merge into yours: one run emitted a 3-node
   graph and got a 55-node plan. If a task graph comes back with more nodes than
   your graph has, that is what happened. Clean and re-emit; do not try to pick
   your nodes out of the merged plan.
2. **Confirm routing actually ran.** Every node's `model` must name a real routed
   model. `local` is the example plan's compile placeholder, not a route. If you
   see `model: "local"` in the emitted packets, phase 8 was skipped and the workers
   will silently run on whatever default the harness hands them, which is the exact
   outcome the cost model exists to prevent. Go back and run `route refresh` then
   `route assign`.
3. **Confirm spawn visibility.** Every emitted task carries `spawn_mode`. It must be
   `visible`. A worker spawned inline or headless does the work but never appears in
   `swarm list`, so the Director cannot see it start, stall, or finish, and the
   status roster becomes fiction.

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
  "id": "IU-STORE",
  "content": "Graph Coder node IU-STORE: ...\nSubmit your report to manager M-STORAGE for review. Only its passing review completes this node; you do not mark yourself complete.\nRead scopes: [...]\nWrite scopes: [...]\nAcceptance: [...]\n<unit prompt>\n<report template>",
  "kind": "implement",
  "depends_on": ["IU-MIGRATION"],
  "priority": "high",
  "model": "<routed model>",
  "spawn_mode": "visible",
  "metadata": {"review_owner": "M-STORAGE", "write_scopes": [...], "max_attempts": 2, ...}
}
```

`content` is the whole worker packet: objective, scopes, procedure, verification
commands, acceptance, review contract, and the report template. It is already
bounded by the context contract. Send it verbatim. Rewriting it in your own words
is how scope leaks in and how a worker ends up reviewing itself.

## Spawning

One subagent per ready node, one round per frontier.

**Preferred: one `swarm spawn` per node.** This is the path that works. Take the
node's `content` as the prompt and its `id` as the label:

```text
swarm spawn --label "IU-STORE" --prompt "<content, verbatim>" \
  --working_dir "<project root>" --spawn_mode visible --model "<routed model>"
```

Issue every ready node's spawn in a single message so the round is genuinely
parallel. Nothing about `swarm spawn` requires the agent to join the swarm; a
spawned worker does its job either way, so do not chase swarm membership as if it
were a precondition.

**`run_plan` is the batch path, and it is brittle.** It has failed on stale plan
pollution and on `Only the coordinator can assign tasks.` Try it if you want the
whole graph registered at once, but the moment it errors, drop to per-node
`swarm spawn` calls instead of debugging the batch path. The per-node route
produces the same agents with the same packets.

**Any other harness with a subagent tool**, Claude Code included: skip both swarm
actions and make one subagent call per entry in `task_graph.arguments.nodes`.
Prompt is that entry's `content`, model is its `model`.

**No subagent tool at all.** Then this harness cannot run a Graph Coder graph.
Say that plainly and stop. Do not silently degrade into implementing the plan
yourself in the root session, which produces a plausible diff with none of the
isolation, review, or cost properties the plan was approved on.

## Parallel rounds and linear chains

Spawn width is set by the dependency DAG, not by preference.

```text
independent nodes    spawn together, in one message, up to max_active_workers (8)
linear chain         spawn one, verify, then spawn the next
```

A chain like `IU-STORE -> IU-BACKEND -> IU-FRONTEND` cannot be spawned at once,
because each worker needs its predecessor's artifacts to exist before it starts.
Spawn `IU-STORE`, wait for its output to appear, verify it, review it, and only
then spawn `IU-BACKEND`. Spawning all three immediately gives the second and third
workers a repository that does not yet contain what their packets told them to
build on.

The reverse mistake costs just as much: serializing nodes that share no dependency
edge, because watching one at a time felt easier. Recompute the frontier after each
round of verdicts and spawn everything it contains.

## Verifying a worker finished

Do not sit waiting for a swarm report. A worker writes to its write scope, so the
Director confirms completion from the filesystem and from commands:

1. The files named in the node's `write_scopes` exist and have changed.
2. The unit's verification commands run and pass, with the real output quoted.
3. The acceptance criteria in the packet are met by that output.

That evidence is what goes to the `review_owner`. A worker's own claim that it
finished is not evidence, and neither is its absence from `swarm list`.

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
- [ ] Every spawn used `spawn_mode: visible` and a real routed model, never `local`.
- [ ] Every completed node has a manager review artifact with acceptance results,
      backed by filesystem evidence and fresh command output.
- [ ] Every spawn used its emitted packet, not a summary of it.
- [ ] Rounds were parallel where the frontier allowed it, and sequential only where
      a dependency edge required it.

Any unchecked box means the graph was not executed. Report that instead of
reporting success.
