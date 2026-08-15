---
name: "speckit.keel.audit"
description: "Score spec quality; with keel/ present, diff the build against the evidence."
argument-hint: "(no input needed — reads the active spec, keel/brief.md if present, and the source tree)"
compatibility: "Requires an active spec.md; keel/ is optional (spec-quality-only mode without it)"
metadata:
  author: "Keel Discovery"
  extension: "keel"
user-invocable: true
disable-model-invocation: false
---

## Pre-flight

```bash
bash .specify/extensions/keel/scripts/bash/keel-gate.sh audit
```

This only blocks if there is no `spec.md` at all — audit needs something to
score. It runs in **spec-quality-only mode** when `keel/brief.md` is
missing (no evidence to diff the build against) and says so.

## Presentation convention

Never lead with a bare ID in prose findings. Refer to an assumption by its
Statement text and to evidence by its source; keep `A-00X`/`E-00X` as
parenthetical secondary metadata, and as the identifier used in the
`audit-report.md` table (a table column is where IDs belong — running prose
is where the human-readable form belongs).

## Outline

### Always: spec quality

Regardless of whether `keel/` exists, check the active spec for:
- Unresolved `[NEEDS CLARIFICATION: ...]` markers left in from
  `/speckit.specify`.
- Functional requirements that are actually testable (a reviewer could say
  yes/no whether the shipped product satisfies them) versus vague ones.
- Whether stated non-goals/exclusions are still honored by the current
  spec, if the spec was edited since they were written.

### With `keel/brief.md` present: round-trip drift

This is the part that actually requires reading code, not just text —
**do not** produce a compliance table by pattern-matching filenames or
function names against requirement text. For every `keel: A-00X` marker in
`spec.md` (and `plan.md`/`tasks.md` if markers are there too):

1. **Locate the assumption and evidence** it claims: read the row in
   `keel/assumptions.md` and the referenced files in `keel/evidence/`.
2. **Locate the actual implementation.** Use the plan/tasks to find the
   relevant source path, then read the real code — not just its presence,
   its logic. A function that exists but doesn't do the thing the
   requirement demands is a drift, not a pass.
3. **Judge, per marker**:
   - **OK** — behavior matches the requirement as evidenced.
   - **DRIFT** — code exists but contradicts or falls short of the
     requirement. State exactly what's missing or wrong, and whether the
     evidence behind the original assumption was about a real risk (e.g. a
     named trust/safety/liability concern from a participant) or a minor
     preference — that distinguishes a blocking finding from a nice-to-have.
   - **NOT FOUND** — no code addresses this marker at all. Say so; don't
     assume compliance because you didn't find evidence of the opposite.
4. If `spec.md` has **no** `keel:` markers at all, fall back to matching
   functional-requirement text against `keel/brief.md` sections directly.
   State explicitly that this is a lower-confidence fallback (structural
   comparison wasn't possible) rather than presenting it with the same
   confidence as marker-based results.

### Severity, specifically for downgraded risks

Cross-reference `keel/decisions.md`. If an assumption's risk was downgraded
from high to medium *because* of a specific mitigation (e.g. "a review step
bounds the blast radius of being wrong"), and the audit finds that
mitigation is **not actually implemented**, treat this as a high-severity
finding regardless of the assumption's current (downgraded) risk label —
the downgrade's justification no longer holds, so the original risk is
back in effect. Say this explicitly in the finding; don't just report the
label as-is.

### Overridden assumptions

Read `keel/decisions.md` for every line containing `override: A-XXX` —
`keel-gate.sh` lets `/speckit.keel.brief` proceed past an unvalidated
high-risk assumption when one is present, specifically so that `keel.audit`
surfaces it later. This step is that surfacing; do not skip it just because
the gate itself didn't block. For each overridden assumption:

- State plainly that it was **overridden, not validated or resolved** —
  carry that distinction into the audit output even though the build
  shipped.
- If the override text names a specific condition or scope limit (e.g. "X
  is out of scope for v1," "will do Y instead of guessing"), check whether
  the shipped code actually honors it — read the logic, not just whether a
  plausibly-named function or constant exists. An override whose named
  condition is **not** honored is a high-severity finding for the same
  reason an unimplemented downgrade mitigation is: the stated justification
  for accepting the risk no longer holds.
- If the override carries no specific condition — a plain "we're accepting
  this risk" call — still list the assumption and its original evidence so
  whoever reads the audit knows this risk was never resolved, only
  deferred.

### Output

Write `keel/audit-report.md`:

```markdown
# Keel Audit — <date>

| Marker | Requirement | Evidence | Code | Verdict |
|---|---|---|---|---|
| A-00X | ... | E-00X | `path/to/file.py::function` | OK / DRIFT / NOT FOUND |

## Findings

### <severity> — <one-line summary>
<what's wrong, why it matters given the evidence, what to do about it>
```

Rank findings most-severe first. If everything checks out, say so plainly
— an audit with zero findings is a valid, useful result, not a sign the
audit didn't try hard enough.
