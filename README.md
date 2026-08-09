# Keel Discovery

A Spec Kit extension that puts customer evidence upstream of `/speckit.specify`, and audits what you shipped against it afterwards.

Spec Kit turns a specification into working software. Keel is about whether the specification deserved to exist. It brackets the core workflow rather than inserting into it.

```
keel.init → keel.add-evidence → keel.check → keel.brief
                                                  ↓
   /speckit.constitution → specify → clarify → plan → checklist → tasks → analyze → implement → converge
                                                                                                    ↓
                                                                                              keel.audit
```

## Install

`keeldiscovery/spec-kit-keel` isn't in Spec Kit's bundled extension catalog
yet, so the bare `specify extension add keel` won't resolve it — install
straight from this repo instead:

```bash
specify extension add keel --from https://github.com/keeldiscovery/spec-kit-keel/archive/refs/heads/main.zip
```

Spec Kit will ask you to confirm installing from an external, non-catalog
source (`y` at the prompt) — that's expected for any `--from` install, not
specific to Keel.

Developing locally instead?

```bash
specify extension add --dev /path/to/spec-kit-keel
```

Requires Spec Kit >= 0.15.0 and Python 3.11+.

## Commands

| Command | What it does |
|---|---|
| `/speckit.keel.init` | Captures the hypothesis, derives assumptions, writes a non-leading interview guide |
| `/speckit.keel.add-evidence` | Ingests one interview, extracts claims with provenance, updates assumption confidence |
| `/speckit.keel.check` | Coverage, saturation, contradictions, and one recommended next action |
| `/speckit.keel.brief` | Writes constitution input and an evidence-backed brief for `/speckit.specify` |
| `/speckit.keel.audit` | Scores spec quality; with `keel/` present, diffs the build against the evidence |

## Why not just use `/speckit.clarify`?

`clarify` resolves ambiguity by asking you. Your assumptions become the spec. Keel resolves it against interviews.

And `/speckit.analyze` checks whether the artifacts agree with **each other**. `keel.audit` checks whether they agree with the **evidence** — a check Spec Kit cannot make, because it has no evidence layer.

## Phase enforcement

`scripts/bash/keel-gate.sh` runs at the top of every Keel command and exits non-zero when preconditions fail. `/speckit.keel.brief` is blocked while any high-risk assumption is unvalidated, evidence is thin, or all evidence comes from a single participant role.

Thresholds live in `keel-config.yml`. You can lower them, and overrides are recorded so `keel.audit` can surface them later.

Note that Spec Kit hooks surface prompts to your agent rather than halting execution — the gate script is the layer that actually enforces.

## Testing

```bash
./tests/test-install.sh          # static + gate behaviour, no network
./tests/test-install.sh --full   # also performs a real specify install
```

## License

Apache-2.0. The Keel name and logo are not covered by the licence — forks are welcome and must rename.
