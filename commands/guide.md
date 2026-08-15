---
name: "speckit.keel.guide"
description: "State-aware entry point: figures out where you are in discovery and guides you to the next action, without requiring you to know Keel's individual commands or IDs."
argument-hint: "(optional) describe your idea, paste new interview notes, or leave blank for a status check and a recommendation"
compatibility: "Works with or without existing keel/ state; safe to run at any point in the workflow"
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

This may be empty (just check status and recommend), a product idea or
hypothesis (if nothing exists yet), pasted interview/survey/data (if
evidence collection is the live phase), or a choice among options this
command itself just offered (e.g. "let's narrow it" or "gather more
evidence"). Read it in light of the phase you detect below before deciding
what it means.

## Pre-flight

```bash
bash .specify/extensions/keel/scripts/bash/keel-gate.sh guide
```

This phase never blocks — it only reports state. Read its output before
doing anything else; don't re-derive these numbers by hand, the script's
parsing of `keel/assumptions.md` and `keel/evidence/` is the source of
truth the gate itself uses for `brief`.

## Presentation convention (applies to everything below, and to every other
Keel command's output)

Never lead with a bare ID. Refer to an assumption by its Statement text
("the assumption that small-business owners will pay $20/month") and to a
piece of evidence by its source ("feedback from EM-2, an engineering
manager" or "the pricing survey" — whatever `participant_id`/`participant_role`
or evidence method makes it recognizable). `A-00X` / `E-00X` may still
appear, but only afterward, in parentheses, as secondary metadata for
whoever wants to open the underlying file. Once you've picked how to
describe a given assumption or evidence item, keep describing it the same
way for the rest of this conversation — don't rephrase it differently each
time it comes up.

## Outline

1. **Open with a progress summary, not a blank slate**, whenever any
   `keel/` state already exists: one line on the hypothesis, the evidence
   count and role diversity, how many high-risk assumptions are validated
   vs. still open (from the gate output), and the most recent entry in
   `keel/decisions.md` if one exists. A returning user should never have to
   re-explain where they left off.

2. **Detect the phase from the gate output and file presence, in this
   order**, and act on the first one that applies:

   - **No `keel/hypothesis.md`.** Phase: *Hypothesis*. If `$ARGUMENTS`
     describes an idea, do the work of `commands/init.md`'s Outline right
     now, inline, using `$ARGUMENTS` as its input — do not ask the user to
     separately invoke `/speckit.keel.init`. If `$ARGUMENTS` is empty, ask
     what they're trying to validate before doing anything else.

   - **Hypothesis exists, `keel/evidence-plan.md` missing.** Phase:
     *Evidence planning*. Run `commands/init.md`'s evidence-plan step
     (writing `keel/evidence-plan.md`) now if it wasn't already produced.

   - **Evidence plan exists, evidence below the gate's thresholds.** Phase:
     *Evidence collection*. If `$ARGUMENTS` looks like pasted interview
     notes, a survey response, or other raw material, treat it as one piece
     of evidence and do the work of `commands/add-evidence.md`'s Outline on
     it inline. Otherwise, read `keel/evidence-plan.md` and present the
     single highest-priority stakeholder/question still uncovered, and
     invite the user to paste evidence now or go gather it.

   - **Evidence at or above thresholds.** Phase: *Check*. Do the work of
     `commands/check.md`'s Outline inline, ending in its five-option
     decision menu (pivot / gather more evidence / reduce risk / narrow the
     hypothesis / proceed to brief).

   - **The user is responding to a decision menu this command (or
     `/speckit.keel.check`) already presented.** Route into the chosen
     option immediately, in this same turn:
     - *Gather more evidence* → back into the evidence-collection behavior
       above, using the specific stakeholder/questions the check named.
     - *Narrow* or *pivot* → draft the revised hypothesis/assumption(s) and
       show them to the user for confirmation before writing anything;
       once confirmed, update `keel/hypothesis.md`/`assumptions.md` and
       append a dated entry to `keel/decisions.md` describing what changed
       and why, so the reasoning survives even though the old wording
       doesn't. Prefer adding a new assumption over silently rewriting an
       old one that already has evidence attached to it, per
       `commands/add-evidence.md`'s guidance on this. If the assumption
       being replaced was high-risk, that same `keel/decisions.md` entry
       must include `superseded: A-00X` (the old ID) — otherwise it blocks
       `/speckit.keel.brief` indefinitely with no way to resolve it, since
       a contradicted assumption can never become validated. If the narrow
       itself introduces a new mechanism or claim (per
       `commands/check.md`'s Option 4), derive a new assumption for that
       too — don't let it ride through unvalidated just because it
       replaced something that was.
     - *Reduce/downgrade risk* → help the user record the downgrade and
       its justification in `keel/decisions.md`, and update the
       assumption's `Risk` field accordingly.
     - *Proceed* → do the work of `commands/brief.md`'s Outline inline
       (its own gate re-check still applies; relay a block verbatim if it
       happens, exactly as `commands/brief.md` requires).

   - **`keel/brief.md` exists.** Phase: *Post-brief*. Remind the user of
     the manual hand-off to `/speckit.specify` (Keel has no automatic
     hand-off — see `commands/brief.md`), and if an active `spec.md` now
     exists, offer `/speckit.keel.audit`.

3. **Always state the current phase and one recommended next action up
   front**, in plain language, before the detail — mirroring
   `commands/check.md`'s rule that a status report is never the end of the
   response by itself.

4. **Close by naming the direct command** that corresponds to whatever you
   just did or recommended (e.g. "this is what `/speckit.keel.add-evidence`
   does — you can also invoke it directly next time with a transcript
   ready to go"). Guide is a router around the other five commands, not a
   replacement for them; say so explicitly so experienced users know they
   can skip straight to any of them.
