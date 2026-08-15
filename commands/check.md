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

## Presentation convention

Never lead with a bare ID. Refer to an assumption by its Statement text
("the assumption that small-business owners will pay $20/month") and to a
piece of evidence by its source ("feedback from EM-2, an engineering
manager"). IDs may still appear, but only afterward, in parentheses, as
secondary metadata — and keep using the same phrasing for a given
assumption/evidence item for the rest of the report, don't reword it each
time it's mentioned.

## Outline

Read `keel/assumptions.md` and every file in `keel/evidence/`, then report:

1. **Coverage** — for each assumption, how many evidence files touch it and
   from how many distinct `participant_role` values. Call out by statement
   (especially high-risk ones) any assumption with zero evidence.

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

5. **Decision menu.** A check never ends on a score, a table, or a status
   summary by itself — it always ends here, with concrete options the user
   can act on immediately. Present all five, in this order:

   - **Option 1 — Pivot.** Only surface this as live (not just listed for
     completeness) when the evidence actually points away from the current
     shape of the idea. Explain: why a pivot may be appropriate given what
     the evidence showed; what to pivot toward (change the customer, the
     problem, the solution, the market, or the business model — say which);
     which existing evidence supports that direction; what questions would
     still need answering after the pivot; and whether current evidence is
     already sufficient to make the call or is just suggestive.

   - **Option 2 — Gather more evidence.** Explain: what's missing
     specifically (by assumption statement, not ID); why it matters; from
     whom it should come (a stakeholder role not yet represented, or more
     depth on one that is); the actual questions to ask; and what kind of
     answer would move the assumption's status in either direction.

   - **Option 3 — Reduce or downgrade a risk.** Explain: which single
     assumption carries the most risk right now and why; how the user could
     reduce that risk (a smaller experiment, a scoped mitigation, a design
     change); what evidence or test would resolve it; and whether, given
     everything gathered so far, downgrading its stated risk level (with a
     documented reason) is honestly warranted or would just be gaming the
     gate.

   - **Option 4 — Narrow the hypothesis.** Suggest a concrete alternative:
     a narrower customer segment, a more specific problem, a smaller use
     case, or a reduced solution scope — and write it out as a revised,
     testable hypothesis statement, not just an instruction to narrow.

   - **Option 5 — Proceed to the brief.** Recommend this when evidence is
     genuinely strong enough, and say plainly why (which assumptions
     cleared the gate and how).

   Then **recommend exactly one** of these five as the preferred next step,
   with your reasoning, prioritizing whatever is actually blocking
   `/speckit.keel.brief` right now over something merely nice to have. Make
   clear the other four remain available if the user prefers a different
   one — this is a menu, not a single verdict. If the user is continuing in
   this same conversation (e.g. via `/speckit.keel.guide`), act on whichever
   option they pick immediately rather than ending the turn.
