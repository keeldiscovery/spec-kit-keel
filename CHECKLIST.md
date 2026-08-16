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
- [ ] The hand-authored hero diagram SVG uses `style="fill:var(--x)"` /
      `style="stroke:var(--x)"` for every color, never a hardcoded hex. This
      already broke once: after the site's visual redesign made the hero
      follow the normal light/dark tokens (it's no longer fixed-dark — that
      was an earlier, now-superseded design), the diagram's own colors were
      still hardcoded hex tuned for one background. Its container correctly
      re-themed; the SVG's text didn't, and "Spec Kit builds it" went
      unreadable in dark mode. Plain `fill="#hex"` / `stroke="#hex"`
      attributes do **not** parse `var()` — only `style="fill:var(--x)"` does.

### Interactivity

- [ ] Install toggle: each pill correctly shows/hides its panel, updates
      `aria-selected`, and its own copy buttons grab the right text — two
      near-identical panels sharing similar step content is exactly where a
      `data-target`/`id` mismatch sneaks in unnoticed
- [ ] "How it works" `<details>` disclosure opens/closes and the chevron
      rotates, using native `<details>` behavior — verify no JS regression
      accidentally makes it JS-dependent
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

### The hero diagram (hand-authored SVG — the most fragile piece on the page)

- [ ] Desktop and mobile SVGs render with **no visual overlap or clipping** —
      this has to be checked visually; misaligned `x`/`y` coordinates are
      syntactically valid SVG and will never throw an error
- [ ] Diagram text (box labels, connector labels) still matches the current
      real command names and behavior — this diagram has gone stale before
      (it used to show four sequential Keel commands as the primary flow,
      which stopped being true the moment `/speckit.keel.guide` shipped)
- [ ] `aria-label` on both SVGs still accurately describes current content

### Copy accuracy — the site makes specific factual claims

- [ ] Command list in the Install section matches what `extension.yml`
      actually provides
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
