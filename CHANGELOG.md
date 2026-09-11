# Changelog

All notable changes to this extension are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## [2.0.0]

Upgrades in place. "keel connect" now replaces a runtime that an older version of this extension
started, as long as it is idle -- and says so. A runtime working on a job is left to finish, and
the next "keel connect" replaces it. A runtime started by a newer version is never downgraded.
The outcome contract gains two shapes (`upgraded`, `upgrade_waiting`), which is what makes this a
major version. The runtime inside is keel-runtime 0.2.0, which records who launched it.

## [1.0.0]

Keel Discovery becomes Keel Connect, and replaces 0.2.0 outright.

### Added
- `speckit.keel.connect` — checks whether the Keel runtime on this machine is connected to Keel
  Cloud, starts it if it isn't, and hands back the code and the URL to approve the device. It
  also says which Keel it is talking to.
- The runtime ships inside the extension. Nothing to install, nothing to download; Python 3.9 or
  newer is the one prerequisite.
- `speckit.keel.brief` — tells you how to bring what Keel has learned into the spec: download
  the brief from keel-web and paste it in. It fetches nothing itself and holds no token.

### Removed
- `speckit.keel.init`, `speckit.keel.add-evidence`, `speckit.keel.check` and `speckit.keel.guide`.
  They did discovery in prompts, on your machine, over a `keel/` directory the same agent wrote
  and then graded. Keel does that work in Keel Cloud now: your idea becomes three claims, you
  approve every card before anyone sees it, and the people you invite answer for themselves. An
  agent scoring its own notes was never a measurement.
- `speckit.keel.audit`. Diffing a build against the evidence needs evidence with stable ids in
  your repository, and Keel's standings do not have them yet. It returns when they do.
- The `before_plan` and `after_implement` hooks, `keel-config.yml` and `keel-gate.sh`. What used
  to be a threshold in a local file is now what people actually said, and nothing in your
  repository can turn that off.

### Changed
- Requires Spec Kit 1.0.0 or newer.

## [0.2.0] - 2026-08-15

Superseded in full by 1.0.0. See that entry for what left and why.
