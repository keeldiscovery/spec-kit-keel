---
name: "speckit.keel.brief"
description: "Write constitution input and an evidence-backed brief for /speckit.specify."
argument-hint: "(no input needed — synthesizes keel/hypothesis.md, keel/assumptions.md, keel/evidence/)"
compatibility: "Requires evidence past the configured thresholds (see keel-config.yml)"
metadata:
  author: "Keel Discovery"
  extension: "keel"
user-invocable: true
disable-model-invocation: false
---

## Pre-flight

```bash
bash .specify/extensions/keel/scripts/bash/keel-gate.sh brief
```

**This gate can actually block.** If it exits non-zero, stop and relay its
output verbatim to the user along with the concrete next action it names
(more evidence, a risk downgrade with a documented reason in
`keel/decisions.md`, or — as a last resort, and only if the user explicitly
chooses it — disabling the gate project-wide in `keel-config.local.yml`).
Do not attempt to write `keel/brief.md` anyway, and do not talk the user
into a downgrade or override just to get past the gate — the point of
discovery is that some ideas should change shape or stop here.

## Outline (only once the gate passes)

1. **Write `keel/brief.md`** with these sections:

   - **Evidence-backed problem statement** — what the evidence actually
     showed, citing evidence IDs, not the original hypothesis restated.
   - **What the evidence ruled out** — every `contradicted` assumption,
     stated as "do not build this" / "do not assume this," with the
     evidence IDs that killed it. This section is not optional: the gate
     script warns when open contradictions exist specifically so they
     survive into the brief instead of getting quietly dropped.
   - **What to build** — scoped to what's actually supported, citing the
     assumption IDs and evidence behind each piece.
   - **Residual risk carried into build** — for every assumption that
     cleared the gate on thin evidence (a single participant, a concept
     test rather than real usage, a risk downgrade rather than a
     validation), say so here. Clearing the gate is not the same as being
     risk-free, and this is the one place that distinction is recorded for
     whoever plans the build.
   - **Traceability** — instruct that every functional requirement in the
     resulting spec should carry a `keel: A-00X` marker back to the
     assumption/evidence it's grounded in. Note explicitly that
     `/speckit.specify` has no native concept of this — it has to be
     requested inline in the feature description, and kept up through
     `/speckit.clarify` and `/speckit.plan` by whoever is driving, or the
     markers silently stop propagating.

2. **Write `keel/constitution-input.md`** — principles for
   `/speckit.constitution`, but only ones grounded in a specific finding
   (cite the assumption/evidence ID). Do not include generic best-practice
   advice here; if it would apply to any project regardless of what the
   evidence showed, it doesn't belong in this file.

3. **Hand off explicitly.** Tell the user: paste the contents of
   `keel/brief.md` (or a faithful summary of it) as the feature description
   when they run `/speckit.specify`, and carry the `keel:` markers through
   manually at each downstream step. There is no automatic hand-off — Spec
   Kit's spec template has no field for any of this.
