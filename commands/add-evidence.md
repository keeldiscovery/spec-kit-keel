---
name: "speckit.keel.add-evidence"
description: "Ingest one interview, extract claims with provenance, and update assumption confidence."
argument-hint: "Paste or describe the interview notes/transcript, and who it was with"
compatibility: "Requires keel/hypothesis.md and keel/assumptions.md (run speckit.keel.init first)"
metadata:
  author: "Keel Discovery"
  extension: "keel"
user-invocable: true
disable-model-invocation: false
---

## User Input

```text
$ARGUMENTS
```

This should contain, or point to, raw interview notes or a transcript, plus
who the participant was (their role relative to the product, not their
name). If it's missing either, ask for it before proceeding — this command
processes one real interview, it does not simulate one.

## Pre-flight

```bash
bash .specify/extensions/keel/scripts/bash/keel-gate.sh add-evidence
```

If this blocks, `keel/hypothesis.md` or `keel/assumptions.md` is missing.
Stop and tell the user to run `/speckit.keel.init` first.

## Presentation convention

Never lead with a bare ID when talking to the user. Refer to an assumption
by its Statement text and to evidence by its source (participant name/role,
or whatever `keel/evidence-plan.md` called that stakeholder). IDs may still
appear afterward, in parentheses, as secondary metadata.

## Outline

1. **Determine the next evidence ID.** List `keel/evidence/E-*.md`, take the
   highest number, and use the next one (`E-001` if none exist).

2. **Extract claims**, each one a distinct, attributable statement from the
   interview — not a paraphrase of the whole conversation. For each claim:
   - Which assumption ID(s) it bears on (an interview can produce claims
     relevant to more than one, or none).
   - Whether it **supports** or **contradicts** that assumption. If a claim
     doesn't cleanly do either, say so rather than forcing a direction.
   - A short direct quote as provenance. If the source material has no
     quotable text (e.g. a summary was pasted instead of a transcript),
     note that explicitly — it's weaker evidence than a direct quote and
     the audit should be able to tell the difference later.
   - A confidence note when the claim is a stated preference rather than
     observed behavior (e.g. "I'd probably use that" is weaker evidence
     than a description of something they already do).

3. **Write `keel/evidence/E-00N.md`** with this structure:

   ```markdown
   # E-00N

   - participant_role: <role, e.g. engineering_manager>
   - participant_id: <anonymized identifier + one line of context>
   - date: <YYYY-MM-DD>
   - method: <interview format>

   ## Claims

   - **C1** (→ A-00X): "<quote>" — <supports|contradicts> A-00X, <confidence note>.

   ## Provenance

   <how this was collected, consent status, where the raw material lives>
   ```

   The `- participant_role:` line is load-bearing — the gate script counts
   distinct values across all evidence files verbatim. Keep role naming
   consistent across interviews (`engineering_manager`, not sometimes
   `EM` and sometimes `manager`), or the source-diversity check will
   undercount.

4. **Update `keel/assumptions.md`** for every assumption this evidence
   touches:
   - Append the new evidence ID to that row's `Evidence` column.
   - Update `Status` only when the claims justify it:
     - `contradicted` if this evidence, alone or combined with prior
       evidence, credibly disproves the assumption. Do not soften this to
       avoid triggering a gate — a contradicted assumption is useful
       information, not a failure.
     - `supported` once independent evidence (different participant roles
       ideally) points the same direction with reasonable confidence.
     - `validated` only for a high bar — direct, repeated, low-ambiguity
       confirmation. Most assumptions should sit at `supported`, not
       `validated`, until there's real weight of evidence.
     - Otherwise leave it `open`. **Never mark an assumption
       `validated`/`supported` just because the evidence count went up** —
       the gate script cannot tell the difference between real evidence and
       rubber-stamping; that judgment is this command's job.
   - If evidence contradicts an assumption in a way that implies a design
     change (not just "this is false" but "here's what's true instead"),
     consider adding a **new** assumption capturing the revised belief
     rather than stretching the old one's wording to fit.

5. **Summarize your interpretation in plain language** — who this was with,
   what it was recorded as supporting or contradicting, and at what
   confidence — and explicitly invite a correction if any of that reading
   feels uncertain (e.g. an ambiguous claim you had to force one way).
   Don't move on while the user is still correcting your read of the last
   piece of evidence.

6. **If new evidence changes the picture** — reveals a stakeholder gap,
   shifts which assumption is highest-priority, or makes a planned question
   moot — update `keel/evidence-plan.md` to match rather than leaving it
   stale.

7. **Offer next actions, and keep going in this same conversation** rather
   than requiring the slash command to be re-invoked per item:
   - **Add another piece of evidence** — if the user pastes more material,
     repeat steps 1–6 on it immediately.
   - **Review evidence collected so far** — list each item with its
     human-readable summary (source, what it supports/contradicts).
   - **Edit or remove an evidence item** — to remove, delete the `E-00N.md`
     file, strip its ID from every assumption row's `Evidence` column it
     touched, and re-evaluate those rows' `Status`: if no other evidence
     remains for a row, it goes back to `open`. If removing evidence
     invalidates a documented override or downgrade in `keel/decisions.md`,
     say so explicitly rather than leaving a stale justification in place.
     To edit, rewrite the claims/quote in place and redo step 4's status
     logic for every assumption affected — an edit can change a claim's
     direction (supports → contradicts) just as a new piece of evidence
     could.
   - **Run a check now** — do the work of `commands/check.md`'s Outline
     inline.

   If coverage is still clearly too thin for a meaningful check (e.g. one
   evidence file, one participant role), say so plainly and suggest
   gathering more before running one, rather than running a check that can
   only say "not enough evidence yet."
