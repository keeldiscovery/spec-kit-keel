# Changelog

All notable changes to this extension are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

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
