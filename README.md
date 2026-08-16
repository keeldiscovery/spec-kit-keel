# Keel Discovery

A Spec Kit extension that puts customer evidence upstream of `/speckit.specify`, and audits what you shipped against it afterwards.

Spec Kit turns a specification into working software. Keel is about whether the specification deserved to exist. It brackets the core workflow rather than inserting into it.

```
             /speckit.keel.guide
     (state-aware — routes through all four below)
keel.init → keel.add-evidence → keel.check → keel.brief
                                                  ↓
   /speckit.constitution → specify → clarify → plan → checklist → tasks → analyze → implement → converge
                                                                                                    ↓
                                                                                              keel.audit
```

The fastest way to run Keel is to just run `/speckit.keel.guide` with no
arguments and follow what it says — it detects which phase you're in from
your project's `keel/` files and does that phase's work inline, so you
don't need to know the four commands below it exist, or track `A-00X` /
`E-00X` IDs yourself. Those four (plus `keel.audit`) remain fully usable
directly — `guide` is a router around them, not a replacement.

## Install

Keel is listed in Spec Kit's community catalog, but the entry is still
syncing to v0.2.0 — until that update lands, the bare
`specify extension add keel` will resolve the older v0.1.1. Install the
pinned v0.2.0 release directly instead:

```bash
specify extension add keel --from https://github.com/keeldiscovery/spec-kit-keel/archive/refs/tags/v0.2.0.zip
```

Spec Kit will ask you to confirm installing from an external, non-catalog-resolved
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
| `/speckit.keel.guide` | State-aware entry point — detects your current phase and does that phase's work, no memorized command order or IDs required |
| `/speckit.keel.init` | Captures the hypothesis, derives assumptions, writes a non-leading interview guide and an evidence-gathering plan |
| `/speckit.keel.add-evidence` | Ingests one interview, extracts claims with provenance, updates assumption confidence — stays conversational across multiple pieces of evidence |
| `/speckit.keel.check` | Coverage, saturation, contradictions, and a five-option decision menu (pivot, gather more evidence, reduce risk, narrow the hypothesis, or proceed to the brief) |
| `/speckit.keel.brief` | Writes constitution input and an evidence-backed brief for `/speckit.specify` |
| `/speckit.keel.audit` | Scores spec quality; with `keel/` present, diffs the build against the evidence |

Every command refers to assumptions and evidence by their actual statement or source ("the assumption that small-business owners will pay $20/month", "feedback from EM-2, an engineering manager") rather than leading with `A-00X` / `E-00X` — those IDs still exist as secondary metadata (and are what `keel-gate.sh` actually parses), you just shouldn't need to remember them.

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
