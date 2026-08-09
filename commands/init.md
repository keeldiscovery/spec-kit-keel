---
name: "speckit.keel.init"
description: "Capture the hypothesis, derive assumptions, and write a non-leading interview guide before any spec exists."
argument-hint: "Describe the product idea or hypothesis in your own words"
compatibility: "Requires a Spec Kit project with the Keel extension installed"
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

You **MUST** consider the user input before proceeding. If it is empty, ask
the user for the idea or hypothesis before doing anything else — do not
invent one.

## Pre-flight

Run the gate script and stop if it fails:

```bash
bash .specify/extensions/keel/scripts/bash/keel-gate.sh init
```

`init` never blocks, but if `keel/hypothesis.md` already exists it will
print a note that existing assumption IDs (`A-001`, `A-002`, ...) must be
preserved on re-run — evidence files reference them by ID, so renumbering
silently breaks traceability. If the note appears, read the existing
`keel/assumptions.md` first and keep every ID that already has evidence
attached.

## Outline

1. **Write `keel/hypothesis.md`** in your own words, not the user's pitch.
   Cover, as prose: the product idea, the underlying belief (what problem
   this solves and for whom), who you think it's for, and why now. If "why
   now" is nothing more than founder intuition, say so explicitly — that's
   the honest starting point Keel discovery exists to pressure-test, not a
   gap to paper over.

2. **Derive 3–7 assumptions** the hypothesis depends on and write them to
   `keel/assumptions.md` as a table with this exact header (the gate script
   parses columns by position — do not reorder or rename them):

   ```markdown
   | ID | Statement | Type | Risk | Evidence | Status |
   |----|-----------|------|------|----------|--------|
   | A-001 | ... | belief | high | | open |
   ```

   - IDs are `A-001`, `A-002`, ... in the order derived.
   - `Type` is usually `belief`; use `fact` only for something independently
     verifiable without an interview (rare at this stage).
   - `Risk` is **high** if the hypothesis mostly falls apart when this
     assumption is false, **medium** if it forces a redesign but not a
     restart, **low** if it's a detail. Be honest — a brief full of
     high-risk assumptions that are all still "open" is a working brief;
     a brief with everything marked "low" to avoid the evidence bar is not.
   - `Evidence` starts empty. `Status` starts `open` for every row.

3. **Write a non-leading interview guide**, appended to the bottom of
   `keel/assumptions.md` under a `## Interview guide (non-leading)` heading.
   Rules for good questions here:
   - Ask about what the participant currently does, not what they'd think
     of your idea. "Walk me through the last time you..." beats "Would you
     use a tool that...".
   - Never name the product, the mechanism, or the solution shape in a
     question. If a question can only be answered by imagining your
     product, rewrite it.
   - Include at least one question that could produce evidence
     *contradicting* the hypothesis, not just confirming it.

4. **Report back**: hypothesis captured, N assumptions derived (call out
   how many are high-risk), interview guide ready. Tell the user the next
   step is `/speckit.keel.add-evidence` once they have a real interview to
   log — do not fabricate evidence at this stage under any circumstances.
