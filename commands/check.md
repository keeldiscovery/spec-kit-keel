---
name: "speckit.keel.check"
description: "Report coverage, saturation, contradictions, and one recommended next action."
argument-hint: "(no input needed — reads keel/hypothesis.md, keel/assumptions.md, keel/evidence/)"
compatibility: "Requires keel/hypothesis.md and keel/assumptions.md (run speckit.keel.init first)"
metadata:
  author: "Keel Discovery"
  extension: "keel"
user-invocable: true
disable-model-invocation: false
---

## Pre-flight

```bash
bash .specify/extensions/keel/scripts/bash/keel-gate.sh check
```

If this blocks, stop and tell the user to run `/speckit.keel.init` first.
This command is read-only otherwise — it never writes to `keel/`.

## Outline

Read `keel/assumptions.md` and every file in `keel/evidence/`, then report:

1. **Coverage** — for each assumption, how many evidence files touch it and
   from how many distinct `participant_role` values. Call out by ID any
   assumption (especially high-risk ones) with zero evidence.

2. **Saturation** — a qualitative read, not just a count: are the most
   recent 1–2 interviews mostly restating claims already captured, or still
   surfacing new claims? If you can't tell (e.g. only one interview exists
   so far), say that plainly rather than guessing.

3. **Contradictions** — list every assumption whose `Status` is
   `contradicted`, with the evidence IDs involved. Note whether each has
   already been addressed (risk downgraded with a documented reason, or
   spun off into a new assumption) or is still an open loose end.

4. **Gate status** — run the numbers `keel-gate.sh brief` would use
   (evidence count, distinct roles, unvalidated high-risk count) and state
   plainly whether `/speckit.keel.brief` would currently pass or block, and
   why.

5. **One recommended next action.** Not a list — pick the single highest-
   leverage next step given everything above, e.g.:
   - "Interview one more participant in a role not yet represented —
     currently all evidence is from `engineering_manager`."
   - "A-003 is high-risk with zero evidence; prioritize it before anything
     else."
   - "Coverage and saturation both look solid — run `/speckit.keel.brief`."

   If more than one thing is true, pick the one that's actually blocking
   `/speckit.keel.brief` right now over one that merely would be nice to
   have.
