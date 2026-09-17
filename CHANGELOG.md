# Changelog

All notable changes to this extension are documented here. Versions follow
[Semantic Versioning](https://semver.org/).

## [2.3.1]

The runtime inside is keel-runtime 0.5.1: the two rule sentences (use the listed word exactly;
never the word "proxy") now sit under CONTRACT in the Claude-shaped prompt as well, after Claude's
own run of record missed one brief on that word. The skill itself is unchanged. Codex is
**supported** (README, *Tested against*).

## [2.3.0]

The runtime inside is keel-runtime 0.5.0. The model a job runs on is now named by the cloud, per
job, from one table kept there (keel-cloud spec 042, `canon/designs/model-routing-design.md`): the
runtime reads the job's `model` entry for its own host and passes it to the CLI, retries once
unpinned when the CLI refuses that model by name, and reports which model answered. The 2.2.0
model knobs (`KEEL_CLAUDE_MODEL`, `KEEL_COPILOT_MODEL`, `KEEL_CODEX_MODEL` and their flags) are
gone -- nothing in the product ever let a person set them. The Copilot- and Codex-shaped prompt
names the allowed units and forbids the word "proxy" where those hosts read it best. The skill
itself is unchanged.

## [2.2.0]

The runtime inside is keel-runtime 0.4.0. Every executor can be pinned to a model now -- Claude
Code joins Copilot and Codex (`KEEL_CLAUDE_MODEL`, an alias such as `sonnet`) -- and Copilot's
answer is read whether or not the model marks it with a phase, which is what let Anthropic-vendored
models on Copilot fail every job. The skill itself is unchanged.

## [2.1.2]

The plugin tree carries `plugin.json` at its root, in the Agent Plugins 1.0 shape, beside the
`.claude-plugin/` manifest it already had -- what GitHub's Copilot marketplace and Codex read.
Nothing inside the skill changed.

## [2.1.1]

The runtime inside is keel-runtime 0.3.1: a Codex session that keeps its login in an isolated
home can name it as `KEEL_CODEX_HOME`, because Codex strips `CODEX_HOME` from the shells it runs
commands in. Nothing else changed.

## [2.1.0]

Codex is a host the skill recognises. The check script's host table names `codex` when a command
runs inside a Codex session (`CODEX_THREAD_ID` / `CODEX_SESSION_ID`), and the runtime inside is
keel-runtime 0.3.0, which carries a Codex executor: `codex exec` in a closed shape (thirteen
feature flags off, read-only sandbox, no session file), the schema in the prompt, tokens as the
unit. Codex is not a measured host yet -- it installs, loads and runs; say so, and do not bet a
project on it until the gate is green. Nothing changes for Claude Code or Copilot.

## [2.0.1]

Keel's address is `https://keeldiscovery.com`. The runtime inside is keel-runtime 0.2.1, whose
built-in Keel Cloud address moved from `app.keeldiscovery.com` to the apex; nothing else changed.
A runtime started by 2.0.0 keeps working (the old name still answers the API) and is replaced in
place the next time "keel connect" finds it idle. The credential home on this machine is derived
from the address, so the first connect after the upgrade approves the device once more.

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
