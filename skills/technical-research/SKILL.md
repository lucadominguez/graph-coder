---
name: technical-research
description: Turn open technical decisions into a question inventory, dispatch only the research capabilities those questions need, and convert sourced claims into plan decisions.
---
# Technical Research

Bounded authority: build the question inventory, route each question to the right research capability, normalize answers into an evidence ledger, and write decisions into the canonical plan. Manager-advisory boundary: the Director synthesizes evidence into technical decisions and decides when research stops. This skill never authors implementation units and never writes application code.

This is a question router and an evidence normalizer. It does not encode general research knowledge, and it does not reimplement researcher prompts that already exist. Available capabilities and their licenses are in `../graph-coder/references/third-party-skills.md`.

Research begins with questions, not with agents. Dispatching a fixed swarm before knowing what is unknown is how a research phase becomes expensive and shallow at the same time.

## 1. Build the question inventory

Derive questions from the plan's open decisions, the concept phase's research queue, and grounding assumptions that are load-bearing. Each question is explicit:

```yaml
question_id: RQ-001
decision_required: the exact plan decision blocked by this question
repository_context: what this codebase already does about it
exact_question: one answerable question, not a topic
source_priority: [official_documentation, primary_repository, standard, community]
freshness_requirement: version or date the answer must be current to
alternatives_required: bool
evidence_required: [string]
confidence_threshold: high | medium
escalation_condition: what makes this a user decision instead
```

A question that does not block a decision is not a research question. Delete it. Curiosity is not free.

## 2. Dispatch selectively

Route each question by its shape. Do not launch every capability.

| Question shape | Capability | Never use for |
| --- | --- | --- |
| What does this codebase already do? | Repository research | External API behavior |
| Have we decided this before? | Learnings research | First-time decisions |
| What does the API actually support, at which version? | Framework documentation research | Opinions about approach |
| What is the established way to do this? | Best-practices research | Establishing API facts |
| What exists outside the repo and the official docs? | Web research | Anything the docs answer |
| How does this behave end to end across components? | Specification-flow analysis | Single-file questions |

A repository-only question must not trigger web research. A version-sensitive framework question must trigger official documentation research. Best-practices research checks curated skills first, then deprecations and breaking changes, then official documentation, and converts findings into plan constraints.

Batch independent questions into one dispatch round. Sequence only where one answer changes another question.

## 3. Normalize every answer into a claim

```yaml
claim_id: RC-001
question_id: RQ-001
claim: the exact technical conclusion the plan will rely on
source_url: https://...
source_type: official_documentation | primary_repository | standard | vendor_blog | community
version_or_date: the version or publication date the claim is true for
retrieved_at: iso8601
confidence: high | medium | low
alternatives: [{option, tradeoff}]
decision_impact: the plan decision this changes, in one sentence
affected_unit_ids: [IU-id]
conflicts_with: [RC-id]
unresolved_uncertainty: what is still not known
```

A claim states a conclusion, not a summary of a page. If the claim cannot be written as something the plan will do or rely on, it is not a claim.

## Source hierarchy

1. Official documentation, standards, source repositories, and release notes establish facts.
2. Vendor blogs and changelogs date facts and reveal intent.
3. Community sources identify practical problems and gotchas. They never establish API behavior.

Rules:

- Pin every version-sensitive claim to an exact version or a retrieval date.
- Always check deprecations and breaking changes for external APIs and dependencies.
- Cross-check critical or conflicting claims. Do not mechanically double-source everything; that doubles cost without raising confidence.
- Prefer the primary source over anything that describes it. A quote from the changelog beats a summary of the changelog.
- Record what you could not find. An absent answer is a finding.

## 4. Convert evidence into decisions

Every retained claim must change something in the plan: a technical decision, a risk, a constraint, an acceptance criterion, or an implementation unit. Write the change, then reference the claim from it.

A claim that changes nothing is omitted from the final evidence ledger. Keeping it is not thoroughness, it is noise that later readers must re-evaluate.

Conflicting claims are either resolved with a documented reason, or surfaced in the plan as an explicit open risk with both positions. They never silently coexist.

## Stop conditions

Research stops when all of these hold:

- every material question is answered or explicitly marked unresolved;
- critical claims use authoritative sources where those exist;
- version-sensitive claims carry a version or retrieval date;
- conflicting claims are resolved or exposed in the plan;
- every retained claim affects a decision, risk, acceptance criterion, or unit.

Research does not stop because it has been running a while, and it does not continue because more could theoretically be learned.

## Decision surfaces

Question necessity, question phrasing, source priority, capability selection, dispatch batching, freshness sufficiency, confidence floor, alternative comparison, conflict resolution, claim retention, decision impact, and the stop condition.

## Evidence rules

Every claim cites a resolvable source with a version or date. Never cite a source you did not retrieve, never paraphrase an API contract you did not read, and never present a community answer as documented behavior. Mark inference as inference and give the check that would falsify it. Absence of evidence is recorded as absence, never as a negative result.

## Schemas

```yaml
defect_schema: {defect_id: string, severity: P0|P1|P2|P3, question_id: RQ-id, claim_id: RC-id|null, evidence: [string], consequence: string, proposed_resolution: string}
rehearsal_schema: {question_id: RQ-id, answerable: boolean, source_available: boolean, freshness_met: boolean, blocking: boolean}
task_schema: {question_id: RQ-id, capability: string, exact_question: string, source_priority: [string], freshness_requirement: string, evidence_required: [string], confidence_threshold: string}
report_schema: {questions_total: int, questions_answered: int, questions_unresolved: [RQ-id], claims: [RC-id], conflicts: [object], claims_omitted_as_unused: int, plan_sections_changed: [string], capabilities_dispatched: [string]}
```

## STOP/escalation rules

Stop on: a critical claim with no authoritative source and a decision that cannot be deferred; two authoritative sources conflicting on a load-bearing fact; a required capability that is not installed; a version-sensitive dependency whose deprecation status cannot be determined; a question that is actually a product decision for the user; or research that would need credentials or paid access the user has not provided.
