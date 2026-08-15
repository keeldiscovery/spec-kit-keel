# Changelog

All notable changes to this extension are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-08-15

### Added
- `speckit.keel.guide` — state-aware entry point. Detects the current
  discovery phase from `keel/` state (via the gate script's new `guide`
  phase) and does that phase's work inline, routing through
  `init`/`add-evidence`/`check`/`brief` by reference rather than requiring
  them to be invoked and sequenced manually. Never blocks; purely advisory
  and routing.
- `scripts/bash/keel-gate.sh`: new `guide` phase plus `assumption_count`,
  `high_risk_ids`, and `high_risk_count` helpers, reused by `guide` to
  report a full state snapshot (hypothesis/evidence-plan/brief presence,
  evidence and role counts, high-risk validated/unvalidated split,
  contradictions, and whether `brief` would currently pass) without
  duplicating the arithmetic `brief` already gates on.
- `speckit.keel.init` now also writes `keel/evidence-plan.md` — a
  stakeholder/question/priority table generated from the derived
  assumptions, so a new project gets a concrete "who to talk to and what to
  ask" plan instead of just an interview guide.
- `speckit.keel.check`'s report now always ends in a five-option decision
  menu (pivot / gather more evidence / reduce or downgrade a risk / narrow
  the hypothesis / proceed to the brief) with one recommended option and
  reasoning, instead of a single free-text "next action" line. A check can
  no longer end on just a score or table.
- `speckit.keel.add-evidence` now runs conversationally: after logging one
  piece of evidence it offers to add another, review what's collected,
  edit/remove an item, or run a check — without requiring the command to be
  re-invoked per item — and keeps `keel/evidence-plan.md` in sync when new
  evidence changes priorities.
- A shared "presentation convention" across `check`, `brief`, `audit`,
  `add-evidence`, and `guide`: assumptions and evidence are referred to by
  their statement/source in prose, with `A-00X`/`E-00X` kept only as
  parenthetical secondary metadata. The underlying file formats and IDs are
  unchanged — `keel-gate.sh`'s parsing and existing tests still depend on
  them exactly as before.
- `tests/test-install.sh`: new "guide phase" section simulating several
  `keel/` states (empty, hypothesis-only, fully passing, overridden
  high-risk assumption) against the real gate script.

## [0.1.1] - 2026-08-09

Initial public release.

### Added
- `speckit.keel.init` — captures the hypothesis, derives assumptions, writes
  a non-leading interview guide.
- `speckit.keel.add-evidence` — ingests one interview, extracts claims with
  provenance, updates assumption confidence.
- `speckit.keel.check` — reports coverage, saturation, contradictions, and
  one recommended next action.
- `speckit.keel.brief` — writes constitution input and an evidence-backed
  brief for `/speckit.specify`.
- `speckit.keel.audit` — scores spec quality; with `keel/` present, diffs
  the shipped build against the original evidence.
- `scripts/bash/keel-gate.sh` — phase-precondition enforcement run at the
  top of every Keel command; blocks `/speckit.keel.brief` while any
  high-risk assumption is unvalidated, evidence is thin, or all evidence
  comes from a single participant role.
- `.extensionignore` so dev-only files (`tests/`, `.claude/`) aren't copied
  into consumer installs.
- `tests/test-install.sh` — static manifest/gate checks (no network) plus
  an optional `--full` mode that performs a real `specify` install.

### Fixed
- `keel-gate.sh`'s assumption-table parser now reads `Risk`/`Status`
  right-anchored instead of by fixed left position, so a literal `|`
  inside an assumption's free-text `Statement` can no longer shift
  columns and silently defeat the high-risk gate.
- A high-risk assumption marked `supported`/`validated` with a completely
  empty `Evidence` column is now caught and still counted as unvalidated,
  rather than passing on the Status label alone.
- README install instructions corrected to the command that actually
  resolves today (`specify extension add keel --from <archive-url>`),
  since this extension isn't yet in Spec Kit's bundled catalog.
