# Refactor / regression checklist

Run this before merging any change to either repo in the Keel project.
It's duplicated identically in `spec-kit-keel` and `keeldiscovery.github.io`
so it's on hand regardless of which one you're touching — if you update it,
update both copies.

Every item here exists because something like it actually broke, or
almost did, during real development — this isn't a generic template.

---

## Part 1 — `spec-kit-keel` (the extension)

### Automated tests (run these first — cheapest signal)

- [ ] `./tests/test-install.sh` passes (static checks + gate behaviour, no network)
- [ ] `./tests/test-install.sh --full` passes (real `specify init` + real extension
      install — confirms hooks registration, `.extensionignore` exclusions, and
      that the installed gate script actually runs from its real install path)

### `scripts/bash/keel-gate.sh` — the actual enforcement layer

- [ ] `bash -n scripts/bash/keel-gate.sh` parses cleanly
- [ ] The usage string's phase list matches the phases actually handled in the
      `case` statement (`init|add-evidence|check|brief|guide|plan|implement|audit`)
- [ ] Right-anchored table parsing still survives a literal `|` inside a
      `Statement` cell (a real historical bug — a naive left-to-right column
      split lets free-text prose shift `Risk`/`Status` out from under the parser
      and silently defeat the high-risk gate)
- [ ] A high-risk row marked `supported`/`validated` with an **empty** `Evidence`
      column is still caught as unbacked, not just counted as resolved because
      the status label says so
- [ ] `override: A-XXX` in `keel/decisions.md` still excludes that assumption
      from the unvalidated-high-risk count, and is still surfaced by name in
      `brief`/`guide` output (not silently absorbed into the count)
- [ ] `superseded: A-XXX` does the same, but is reported as a **distinct** note
      from `override:` — these mean opposite things (accepting an unresolved
      risk vs. an assumption that was actually disproven and replaced) and must
      not be merged into one message
- [ ] `guide` phase never exits non-zero, for any state, including a totally
      empty project — it's advisory-only; a regression here would silently
      start blocking a command that's supposed to never block
- [ ] `brief` phase's three blocking conditions (evidence count, distinct
      participant roles, unvalidated high-risk) are still independently
      AND-ed — a common refactor slip is accidentally OR-ing them or dropping
      one silently

### Command files (`commands/*.md`) — the actual behavior contract

- [ ] Every command's frontmatter `description:` matches what its Outline
      section actually instructs the agent to do. **This has already drifted
      once**: `check.md`'s description said "one recommended next action"
      for a full release after the Outline was rewritten to a five-option
      decision menu — nothing catches this automatically, it has to be
      read side by side.
- [ ] `extension.yml`'s `provides.commands[].description` matches each
      command's own frontmatter description (two places, no automated sync).
      "Matches" means describes the same behavior, not byte-identical text —
      `extension.yml`'s copies are meant to be short summaries, so trailing
      punctuation or minor rewording is fine. Diff them for meaning, not
      with a strict string-equality check, or every command will falsely
      flag as drifted.
- [ ] Any prose cross-reference to another command file (e.g. "do the work
      of `commands/init.md`'s Outline") still points at a step that actually
      exists there — these are plain prose links, nothing validates them
- [ ] The "presentation convention" block (human-readable framing, IDs as
      secondary metadata) is present and worded consistently across
      `check.md`, `brief.md`, `audit.md`, `add-evidence.md`, `guide.md`

### Manifest (`extension.yml`)

- [ ] `version:` is valid semver and was actually bumped if behavior changed
- [ ] Every command name is still prefixed `speckit.keel.`
- [ ] No hook has a `condition:` key (Spec Kit's command templates silently
      skip any hook that has one — this is enforced by test-install.sh, but
      worth knowing *why* if the check ever needs to change)

### Real install smoke test (do this before merging, not just before release)

- [ ] `specify extension add --dev /path/to/spec-kit-keel --force` succeeds
      in a fresh `specify init` project
- [ ] All six commands show up as skills for your agent
      (`speckit-keel-guide`, `-init`, `-add-evidence`, `-check`, `-brief`,
      `-audit`)
- [ ] Walk at least one full state transition by hand — empty → hypothesis →
      evidence → check → brief — through `/speckit.keel.guide` or the direct
      commands. **None of this is exercised by the automated test suite**; it
      only tests the gate script, never what an LLM actually does when it
      reads a command file.

---

## Part 1b — Publishing a new version (after merging to `main`, not before)

This is a different moment than everything above — Part 1's items gate the
merge itself; these gate what happens once `main` actually changes and a
release is meant to go out. Skipping any of these was how the catalog
listing went stale after the 0.2.0 release: the version was bumped, tagged,
and released correctly, but nothing updated the entry that actually points
users at it.

- [ ] `extension.yml`'s `version:` and `CHANGELOG.md`'s newest heading agree,
      and the changelog entry is dated the day of the actual merge, not
      written speculatively beforehand
- [ ] `./tests/test-install.sh` re-run **on the merged `main`**, not just on
      the feature branch pre-merge — a fast-forward merge makes this
      redundant in practice, but it's what actually catches a merge that
      wasn't the clean fast-forward it was assumed to be
- [ ] `git tag vX.Y.Z` at the new `main` HEAD, pushed, and a GitHub Release
      created from it with notes pulled from `CHANGELOG.md`'s matching
      section (not written fresh — the changelog is the source of truth)
- [ ] Real install smoke test against the **actual tagged release archive
      URL** (`.../archive/refs/tags/vX.Y.Z.zip`), not the branch or `main`
      zip — confirms the artifact users will actually download, not just
      the source tree it was cut from
- [ ] **File (or update) the extension catalog submission on
      `github/spec-kit`.** The community catalog
      (`extensions/catalog.community.json` upstream) is a static snapshot —
      it does not track this repo automatically. A version bump here does
      nothing to the catalog on its own; the listed `version`,
      `download_url`, and `provides.commands`/`provides.hooks` will silently
      go stale on every release until a new **Extension Submission** issue
      is filed on `github/spec-kit` with the updated fields, explicitly
      stating it's an update to the existing `keel` entry (not a fresh
      submission — see the [publishing guide](https://github.com/github/spec-kit/blob/main/extensions/EXTENSION-PUBLISHING-GUIDE.md#updating-an-existing-extension)).
      This needs doing **every version**, not just once.
- [ ] If `keeldiscovery.github.io` also has a pending merge for this release
      (site copy describing new behavior, updated command list, etc.):
      **merge and release `spec-kit-keel` first.** The site can describe a
      command before the extension that provides it is actually live on
      `spec-kit-keel`'s `main` — if the site ships first, the documented
      install command hands out a version that doesn't have the feature the
      page just described.

---

## Part 2 — `keeldiscovery.github.io` (the website)

There is **no automated test suite** for this site — it's hand-authored
static HTML, now two files (`index.html` and `showcase/index.html`, added
2026-08-15). Every item below is a manual/visual check, and applies to
**both** files unless a bullet says otherwise; this checklist *is* the
safety net.

### Structural validity (fast, catches the most common slip)

- [ ] Tag balance check (unclosed/mismatched tags) — a stray `</div>` won't
      throw any error, it'll just silently break layout somewhere downstream
- [ ] No duplicate `id` attributes anywhere on the page (breaks anchor links,
      `getElementById`, and copy buttons silently)
- [ ] Every `<button class="copybtn" data-target="cN">` has a matching
      `<pre id="cN">` somewhere on the page

### Both themes

- [ ] Every color token is defined once on bare `:root` (light), then
      redefined under **both** `@media (prefers-color-scheme: dark)`
      (guarded `:not([data-theme="light"])`) and `:root[data-theme="dark"]` —
      no color should exist inside only one of those blocks, or the
      un-stamped "system" state renders wrong
- [ ] `body` has an explicit background — never transparent, or it silently
      borrows the host page's theme
- [ ] `--ink-faint` is `#666862` (both `index.html` and `showcase/index.html`
      light `:root`), not `#8a8b86`. **2026-08-16**: the old value measured
      ~3.43:1 against white — below the 4.5:1 normal-text WCAG target — and
      it's used for real reading content (install explanations, trust
      statement, agent-format disclosures), not just decoration. The new
      value measures ~5.64:1. If this ever gets "restored" to the lighter,
      more subtle gray because someone likes the look better, that's a
      contrast regression, not a style preference — re-run the ratio check
      before changing it back. (Dark mode's `--ink-faint` was left alone;
      the complaint was specifically about the light-mode/white-background
      case.)
- [ ] **The hand-authored workflow SVG diagram no longer exists** (removed
      2026-08-16, not just relocated this time — first it moved
      hero→`#how` on 2026-08-15, then `#how` itself was dissolved into a
      compact `#install`-only subsection the next day). If a diagram like
      it ever comes back, re-apply the historical lesson that lived here:
      hardcoded hex on an SVG's `fill`/`stroke` attributes doesn't follow
      the site's light/dark tokens — only `style="fill:var(--x)"` /
      `style="stroke:var(--x)"` does, and this broke once in dark mode
      because of exactly that.

### Interactivity

- [ ] **Neither file uses CSS `scroll-behavior:smooth` anymore** (removed
      2026-08-16, both `index.html` and `showcase/index.html`). Native
      smooth scrolling's animation duration scales with distance and
      isn't capped — a deep link or long same-page jump could take 2-3
      real seconds, which is exactly what got reported. Same-page anchor
      clicks now go through a small JS-delegated handler
      (`a[href^="#"]` → `preventDefault()` → a fixed-duration
      `requestAnimationFrame` scroll, 450ms, respecting
      `prefers-reduced-motion`) defined near the top of each file's
      `<script>`. **Do not re-add `scroll-behavior:smooth` to `html`** —
      it would silently reintroduce the uncapped-duration bug alongside
      the new JS scroll, likely fighting it. A genuine deep link (page
      loads fresh with a `#hash` already in the URL — typed directly, or
      the cross-page `/?setup=1#install` link) is never a click, so it's
      never intercepted, and correctly falls back to the browser's
      default **instant** jump — that's intentional, not a gap to "fix"
      by adding animation there too.
- [ ] Install toggle: each pill correctly shows/hides its panel, updates
      `aria-selected`, and its own copy buttons grab the right text — two
      near-identical panels sharing similar step content is exactly where a
      `data-target`/`id` mismatch sneaks in unnoticed
- [ ] The three `<details class="phases-disclosure">` accordions in
      `#install` (as of 2026-08-16: "Advanced: Show individual Keel
      commands" ×2, one per install panel, and "Technical details: Five
      phases and enforcement gate" ×1, shared) open/close and the chevron
      rotates, using native `<details>` behavior — verify no JS regression
      accidentally makes it JS-dependent, and that **all three render
      collapsed by default** (no `open` attribute) — this was an explicit
      requirement, not a default that happened to be convenient.
- [ ] All copy buttons (index.html's install panels; showcase's "Run it
      yourself" clone command) show "copied" feedback and reset to "copy"
      afterward.
      **2026-08-15**: the old `#tryit` interactive demo (fixed assumptions
      table, gate terminal, brief-unlock animation) and its multi-command
      "copy all" block were removed in favor of a static teaser linking to
      `/showcase/` — there is currently no interactive element and no
      multi-command copy block on either page. If either comes back, restore
      a dedicated check for it here instead of assuming this bullet still
      covers it.
      **2026-08-16**: `index.html`'s copy-button handler is now **event
      delegation** on `document` (`e.target.closest('.copybtn')`), not a
      per-button `querySelectorAll(...).forEach(addEventListener)` — the
      agent selector below replaces `#start-keel-*`/`#advanced-commands-*`
      via `innerHTML` after page load, and a per-button binding done once
      at load would silently never attach to those buttons. If this ever
      gets "simplified" back to per-button binding, the agent-specific copy
      buttons will look fine visually but do nothing on click.

### Agent-specific Keel invocation (`#install`, added 2026-08-16)

- [ ] `KEEL_AGENTS` (in `index.html`'s script) is the **only** place
      dotted/dashed/`$`/skill-name command strings are defined for
      Install — the "Start Keel" step and "Advanced" accordion in both
      panels render from it via `startKeelHTML()`/`advancedHTML()`. If a
      command string ever gets hardcoded again in the install-panel
      markup directly (the way it was before this feature), that's a
      regression back to the pre-2026-08-16 "scattered across pages"
      problem this was built to fix.
- [ ] All five states render distinct, correct content — spot-check by
      clicking each `.agent-btn` and confirming: Claude Code shows
      `/speckit-keel-guide`; Codex CLI shows `$speckit-keel-guide`;
      GitHub Copilot shows the "ask Copilot to use the skill" explanation
      plus a copyable **prompt** (not a slash command); "Another Spec Kit
      integration" shows the three-rule table. None of these may describe
      another format as incorrect — this was an explicit requirement.
      **2026-08-16, fixed a real bug**: the **no-selection default** must
      show only "Choose your coding agent above to see how to start Keel."
      — it originally fell through to the same three-rule table as
      "Another Spec Kit integration," which meant every first-time visitor
      saw fallback rules before ever touching the selector. `key === null`
      and `key === 'other'` are handled as separate branches in
      `startKeelHTML()` now; don't collapse them back into one "no
      selection" case.
- [ ] Copy buttons in the agent-specific areas copy exactly what's
      currently rendered, not a stale value — this depends on the
      event-delegation copy-button fix above still being in place.
- [ ] Selection persists via `localStorage['keel-agent-integration']`
      across: a reload, leaving for `/showcase/` and coming back (same
      origin, same storage — nothing showcase-specific needed), switching
      the have/new install-toggle tabs (both panels re-render on every
      selection, not just the visible one), and opening/closing either
      accordion (content is set independently of the `<details>` `open`
      state, so it can't desync). No agent button shows `aria-pressed`
      `"true"` on first visit with empty storage — a saved/restored
      selection is the only thing allowed to preselect one.
      The always-visible agent-button row **is** the "change coding
      agent" control — there's no separate reset button; clicking a
      different pill changes the selection immediately.
      **2026-08-16, fixed a real bug**: the post-selection prompt text said
      "...above to change this," but the buttons render *below* the prompt
      paragraph in the DOM, not above it — backwards. Now reads "Select
      another coding agent to change these instructions," which doesn't
      make a position claim at all. If the buttons ever move above the
      prompt, this specific wording stops being wrong but should still be
      double-checked.
- [ ] `showcase/index.html`'s guide-chips still show the **unmodified**
      historical `/speckit.keel.guide` text (Change 7 requirement:
      historical examples must not be dynamically rewritten) — only the
      explanatory note right after the first chip should ever change, not
      the chip text itself. That note doesn't name a specific coding
      agent (there's no verified record of which one the real ShipLog run
      used) — it identifies the *form* shown (Spec Kit's dotted format)
      and links to `/#install` for the reader's own agent. Don't "fix"
      this into naming a specific agent without actually verifying it
      first.
      **2026-08-16**: shortened to one sentence ("Example shown using
      Spec Kit's dotted command format. Other agents may use dashes, $,
      or a named skill." + a "See invocation formats" link to `/#install`)
      — it used to be a much longer paragraph that visually dominated the
      first beat. Keep it this short; don't let it creep back into a full
      explanation, and don't repeat it after every guide-chip — one
      mention for the whole page is the point.

### The "how Keel fits" mini-flow and `#install` accordions (added 2026-08-16, replaced the removed diagram/`#how` section)

- [ ] `#install` opens with the compact `id="how"` subsection ("How Keel
      fits with Spec Kit" + the three-step `.mini-flow`) **before** the
      install-toggle tabs — this is the whole point of the restructure:
      whoever clicks "I use Spec Kit — install Keel" in the hero should
      see where Keel fits immediately, not scroll past tabs and steps
      first.
      **2026-08-16**: the mini-flow's Validate/Check-what-shipped steps
      show the neutral label "Keel Guide", not a specific command string —
      this section sits *before* the agent selector, so it must stay
      agent-neutral (see the agent-invocation entries above).
      `id="how"` is kept specifically so old `/#how` links (e.g. from
      `showcase/index.html`, or anyone's bookmark) still land somewhere
      sensible — if this id ever moves or gets removed, check for external
      references first.
- [ ] Each install panel's "Start Keel" step shows **only one** thing by
      default (a single command, or — for Copilot — one explanation plus
      one prompt), whichever the selected coding agent calls for; the
      other five commands live only in that panel's collapsed "Advanced:
      Show individual Keel commands" `<details>`. This was a specific
      reviewer requirement ("do not display all six commands by default"),
      not a space-saving choice — don't casually revert it while editing
      nearby.
- [ ] `.mini-flow` wraps sanely at narrow widths (stacks vertically under
      560px per its media query) — check visually, this is new and hasn't
      been eyeballed on a real mobile viewport yet.
      **2026-08-16**: switched from `flex` to a `grid` with
      `1fr auto 1fr auto 1fr` columns so the three steps stay equal-width
      across the panel instead of hugging the left edge with the rest of
      the gray `.how-fit` panel empty — this was flagged as looking
      unfinished. If it ever goes back to flex, re-check that the steps
      still span the full width rather than clumping left again.

### Hero (`.hero-grid`, added 2026-08-16 — desktop right-column output card)

- [ ] `.hero-grid` is a two-column grid (content left, `.hero-card` right)
      above 880px, collapsing to one column below it — check both. On
      mobile the card must render *after* the CTA buttons in reading
      order (it does, by DOM order, since collapsing a grid to one column
      just stacks items in source order — don't "fix" this with a CSS
      `order` property that could silently break if the breakpoint or
      markup order ever changes).
- [ ] `.hero-card` is founder-friendly example content (labeled "Current
      stage" / "Keel found" / "Recommended next step"), explicitly **not**
      styled as a terminal (no `.term`/dark monospace treatment) and
      **not** a resurrection of the removed technical diagram — this was
      an explicit distinction in the request that added it. If someone
      "improves" it toward looking more like real console output, that's
      drifting back toward the thing it was deliberately built to avoid.
- [ ] The hero's showcase link is `.hero-showcase-link` (not `.caveat` —
      that class no longer exists anywhere in `index.html`, checked
      2026-08-16), reads "View the end-to-end showcase→" with a non-italic
      weight, and the arrow is glued to "showcase" with `&nbsp;` so it
      can't wrap onto its own line. The trust statement
      ("Keel won't produce a build brief...") is also non-italic now, with
      a small shield-check `.trust-icon` SVG — both changes were explicit
      requirements (the italic styling and the wrapping arrow were flagged
      as looking like "an article citation," not a product action).
- [ ] `.hero-strip` ("Open source · Spec Kit extension · Apache-2.0") sits
      between the CTA buttons and the trust statement, inside
      `.hero-footnotes` — a dedicated wrapper with its own tight internal
      `gap`, not just more items dropped into `.hero-content`'s larger
      flex `gap`. If new hero footnote-style lines get added later, put
      them in `.hero-footnotes` too, not directly in `.hero-content`, or
      the spacing will look inconsistent with everything else in that
      group.

### Copy accuracy — the site makes specific factual claims

- [ ] `KEEL_AGENTS`' five-command lists (all four variants: dotted,
      Claude Code dashed, Codex `$`, Copilot bare skill names) each still
      match what `extension.yml` actually provides — same five commands,
      same order, just reformatted per integration. If a command gets
      added, renamed, or removed in `extension.yml`, all four lists need
      the same edit, not just the dotted one.
- [ ] Version tags (nav + footer) match `spec-kit-keel`'s `extension.yml`
      version
- [ ] Install commands (`specify extension add ...`, `uv tool install
      specify-cli`, `specify init ...`) still match Spec Kit's actual current
      CLI — this is an external project's syntax, not ours, and can change
      independently
- [ ] Any claim about "what running these commands produces" is checked
      against real command behavior, not assumed to match a hardcoded demo.
      **History**: `index.html` used to have a "Try it" section with a
      fixed JS-simulated demo, plus an "Or run it for real" block claiming
      pasting its commands was "exactly what" the demo produced — untrue,
      since `/speckit.keel.init` generates assumptions via LLM,
      non-deterministically. Both were removed 2026-08-15 in favor of a
      teaser linking to `/showcase/`, a real (not simulated) run. If a
      hardcoded demo of Keel's output is ever added back anywhere, re-apply
      this check — don't claim a script's exact wording matches an LLM's.
- [ ] `showcase/index.html`'s `.guide-chip` elements (the "detected: X →
      did Y" tags threaded through the timeline) describe behavior that
      still matches `commands/guide.md`'s actual documented phase-detection
      Outline — added 2026-08-15, grounded in that file's language at the
      time. If `guide.md`'s phase logic changes, these five chips drift
      out of sync silently; nothing checks them automatically.
- [ ] The founder help-discovery block, now wrapped in `id="continue"`
      (`#newfounder`, added 2026-08-15, `id="continue"` added 2026-08-16 —
      it's a linkable destination now: `showcase/index.html`'s "Back to my
      options" link and nav both point at `/#continue`) still holds up:
      the copy still says "not a sales form" / "no commitment" and never
      mentions pricing, consulting, or a support guarantee — this was an
      explicit requirement, not a style choice; Option 1 is titled "Set up
      Keel myself" (renamed 2026-08-16 from "Try it myself" — don't let it
      drift back); and its button still `.click()`s the real
      `.toggle-btn[data-panel="new"]` rather than duplicating the
      install-toggle's show/hide logic.
- [ ] `FOUNDER_HELP_SURVEY_URL` is **not** a single global source of truth
      anymore — as of 2026-08-16 there are **two** independent `const`
      declarations, one in `index.html`'s script and one in
      `showcase/index.html`'s script (separate documents can't share a JS
      variable without a shared external file, which wasn't worth adding
      for one constant). Each is still the only occurrence *within its own
      file* — grep each file separately for `surveymonkey.com` before
      adding a second reference in either — and both must resolve to the
      same URL. If they ever diverge, that's a real bug, not a stylistic
      difference.
- [ ] No link anywhere points at `/#tryit` or `/#how` as a **standalone
      destination** — `#tryit` hasn't existed since 2026-08-15, and `#how`
      moved *inside* `#install` on 2026-08-16 (still a valid anchor, just
      not a separate section — a nav item labeled "How it works" pointing
      there would now be confusing, which is why it was dropped rather
      than kept). `grep -rn '#tryit\|#how"' index.html showcase/index.html`
      before adding any new link — this exact class of bug (a showcase nav
      link surviving a homepage restructure) has already happened once.
- [ ] The cross-page "set up the beginner install path" links
      (`showcase/index.html`'s "← Back to my options" is `/#continue`; its
      bottom "Set up Keel myself" is `/?setup=1#install`) still work:
      `index.html`'s script checks `location.search` for `setup=1` on
      load and calls the **same** `selectBeginnerInstallTab()` function the
      in-page button uses — don't let a future edit fork these into two
      separate implementations that can drift. The `#install` anchor in
      the URL does the scrolling (native browser behavior); the JS only
      needs to handle the tab selection.
- [ ] `#newfounder, #continue, #why, #how, #install` all have
      `scroll-margin-top:88px` (added 2026-08-16) so the sticky nav
      doesn't cover the first line of content when you jump straight to
      one — `#continue` specifically was landing with "How would you like
      to continue?" hidden behind the nav bar before this. If a new
      anchor-linked section gets added (from outside, e.g. another
      cross-page link, or a nav item), add it to this same selector rather
      than styling it separately — one rule, one list of ids.
- [ ] The homepage's showcase-teaser paragraph no longer says "real
      evidence" / "Not simulated" (fixed 2026-08-16 — flagged as
      contradicting the Showcase page's own synthetic-interview
      disclosure, even though the disclosure itself was accurate). Current
      text: "A real execution of Keel and Spec Kit using a disclosed
      synthetic interview dataset. The gate, build, live verification and
      audit are real." If this section's copy changes again, keep the
      disclosure in the same breath as the "real" claim — that's the
      actual fix, not just different wording.
- [ ] `showcase/index.html`'s eyebrow reads "End-to-end showcase," not the
      old "A showcase — dogfooding feature/guided-validation-workflow"
      (changed 2026-08-16 — the branch name read as an internal detail
      too prominent for a page header). The branch name itself
      (`feature/guided-validation-workflow`) still appears, just
      downgraded to a `.stat.branch` metadata pill in the stat row instead
      of the headline eyebrow.
- [ ] `showcase/index.html` itself no longer says "four interviews" (dek)
      or "Not simulated — the actual script, against the actual evidence"
      (gate beat h3) — fixed 2026-08-16, a **separate** instance from the
      homepage teaser fix above (this one's on the Showcase page's own
      hero/gate-beat, not the homepage). Now: "four disclosed synthetic
      interview records" and "The actual gate, run against the disclosed
      test evidence." Same underlying issue as the homepage fix — don't
      let "real"/"actual" framing get ahead of the synthetic-data
      disclosure again on either page.
- [ ] The hero's `.hero-card` carries an explicit `.hero-card-tag` label
      ("Example Keel Guide output," added 2026-08-16) above its title —
      without it, "Interview billing administrators" reads as a real
      personalized result for whoever's currently viewing the page rather
      than illustrative example content. Don't remove this label as
      visual "cleanup"; it's load-bearing honesty, not decoration.
- [ ] The `data-panel="new"` (beginner) install panel has a `.beginner-help`
      line at its end ("Setup looks unfamiliar? Tell us where you're
      stuck.", added 2026-08-16) linking to the same founder-help survey
      as `#continue`'s Option 2 — this was flagged as a real gap: a
      founder hitting `uv`/Python/CLI commands for the first time had no
      nearby way out. Its href is set from the same
      `FOUNDER_HELP_SURVEY_URL` constant as `#founder-help-survey-link`
      (both ids are now in the `forEach` that sets survey hrefs on load —
      if a third survey link gets added anywhere, add its id to that same
      list rather than writing a new one-off assignment).
- [ ] Neither footer (`index.html`'s or `showcase/index.html`'s) states a
      bare `/speckit.specify` / `/speckit-specify` as if it were universal
      invocation syntax — both now read "...before Spec Kit's Specify
      step" (fixed 2026-08-16). This is distinct from the *other*
      `/speckit.specify` mentions still in `index.html` (in `#why`, the
      `#install` intro, and the Technical Details accordion) — those sit
      inside full explanatory paragraphs already establishing context (or,
      for the agent-selector's "Another Spec Kit integration" rule table,
      are the correct multi-format mapping the whole feature exists to
      provide) and were left alone. The footer instances were flagged
      specifically because they had **no** surrounding context — a bare
      tagline on every page.

### Responsive check

- [ ] Render at a real mobile width via an actual headless-browser tool
      (Playwright/Puppeteer viewport emulation), not just the raw
      `chrome --headless --window-size=W,H --screenshot` CLI flag. That flag
      produced a false-positive-looking text clipping in the hero during
      this project's own diagram work that did **not** reproduce under
      Playwright's proper viewport emulation, and
      `document.documentElement.scrollWidth` vs. `window.innerWidth`
      confirmed there was no real overflow. Trust the DOM measurement and a
      real browser engine's viewport handling, not a glance at a CLI
      screenshot.
