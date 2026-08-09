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

5. **Run `/speckit.keel.check` logic inline** (or tell the user to run it)
   and report the resulting coverage, saturation, and contradiction counts
   so they know whether another interview is needed before
   `/speckit.keel.brief` will pass.
