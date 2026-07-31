# Bringing work over from APS

Graph Coder ships **no automatic importer**. That is a deliberate scope decision,
not an omission: a mechanical conversion would have to invent the fields Graph
Coder added, and inventing a manager assignment or a context manifest is exactly
the kind of silent guess the design exists to prevent.

APS remains unchanged and available as a comparison baseline. The commit studied is
pinned in `upstream/aps.lock.json` and every ported file is mapped in
`docs/upstream-provenance.md`.

## What does not carry over

An APS plan cannot be executed by Graph Coder as-is, because these are missing or
mean something different:

| APS | Graph Coder | Why it cannot be inferred |
| --- | --- | --- |
| `reviewer` on a unit | `manager_id` | A reviewer was a peer of the worker. A manager owns a branch. Mapping one to the other requires deciding the branch shape. |
| `review` graph nodes | none | Review is a verdict and an artifact. Deleting the node loses whatever the node was actually doing. |
| Product Contract document | plan sections 2 and 3 | Requires deciding which statements are requirements and which are settled decisions. |
| 17 phases | 10 phases | Three phases were removed, not renamed. |
| `done` status | `completed` | `done` was self-declared. `completed` means a manager passed it. |
| no context manifest | `context_manifest` | Requires deciding what each unit actually needs to read. |
| no retry policy | `retry_policy` | Requires deciding where the escalation ladder ends. |

An imported plan's prior approval and completion state are void regardless,
because Graph Coder recompiles ownership, context, graph, and routing contracts,
and approval is bound to those hashes.

## Doing it by hand

Treat the APS plan as evidence, not as a plan.

1. Start a fresh `/graph-coder` run with the same goal.
2. In `REPOSITORY_GROUNDING`, cite the APS plan as a source. Its repository
   findings, technical decisions, and command lists are usually still good, and
   citing them is faster than rediscovering them.
3. Let `plan-forge` author the canonical plan. Reuse the APS unit objectives and
   acceptance criteria where they hold, and keep the original `R-`, `AE-`, `I-`,
   and `U-` identifiers so history stays traceable. Unit IDs accept both the
   canonical `IU-` prefix and the APS `U-` prefix for exactly this reason.
4. Decide the branch shape explicitly: which units share a manager, and why they
   share a context boundary. This is the part no importer could do for you.
5. Add the fields APS did not have: `manager_id`, `review_contract`,
   `context_manifest`, `retry_policy`, `failure_domain`, and explicit `interfaces`.
6. Run `COLD_REHEARSAL`. An APS plan that was implementation-ready under APS's
   gates will usually still have gaps against the fuller unit contract, and this
   is where they surface.
7. Compile, route, and take the whole plan back to the user for approval. The
   previous APS approval does not transfer.

## Reading APS artifacts

APS artifacts stay readable. They declare `agent-planning-system/v1`, and
byte-for-byte copies of the APS v1 schemas live under `schemas/import/aps-v1/` so
an old artifact can still be validated against the contract it was written for.

Graph Coder writes `graph-coder/v1` and reads only `graph-coder/v1`. The two
identifiers never mix: an APS artifact fed to a native reader is rejected on its
`artifact_contract`, which is the intended outcome, because the unit contract
underneath it lacks `manager_id`, `review_contract`, `context_manifest`,
`retry_policy`, and `failure_domain`. If you need to inspect an old plan,
validate it against the frozen schemas. To bring one forward, follow the
by-hand path above; the contract identifier is the last field you change, once
the content it promises is actually there.

## Upstream drift

`scripts/check_aps_upstream.py` reports whether APS has moved past the pinned
commit, and lists the changed source paths. It fetches into a throwaway directory
and never merges, rebases, imports code, or edits the lock. Porting an upstream
improvement is a deliberate act: read the diff, decide, port it, then update
`upstream/aps.lock.json` and `docs/upstream-provenance.md` by hand.

```shell
python scripts/check_aps_upstream.py --lock upstream/aps.lock.json
python scripts/check_aps_upstream.py --lock upstream/aps.lock.json --json
```

Exit `0` means unchanged. Exit `2` means APS moved and a human should look. Exit
`1` means the check could not run.
