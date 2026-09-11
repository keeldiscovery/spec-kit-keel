# Keel Connect

**Keel Connect** connects the Keel runtime on your machine to Keel Cloud, from inside the agent
you are already talking to. Say "keel connect": you get a code and a URL, you approve the device
in your browser, and Keel can get on with asking the people you invite what they actually think.
Say "keel brief" once Keel has something to say, and it tells you how to bring that into the
spec. That is the whole extension — two commands, one script, and the runtime itself travelling
beside it. Python 3.9 or newer is the only thing you need that you might not already have.

## Install

```bash
specify extension add keel
```

Before the community catalogue entry lands — and afterwards, for anyone who wants a pin — install
straight from a release archive:

```bash
specify extension add keel --from https://github.com/keeldiscovery/spec-kit-keel/archive/refs/tags/v1.0.0.zip
```

Requires Spec Kit 1.0.0 or newer, and `python3` 3.9 or newer on your `PATH`. Nothing else is
installed, downloaded or fetched: the runtime ships inside the extension.

## The two commands

### `/speckit.keel.connect`

Checks whether the Keel runtime on this machine is connected to Keel Cloud, starts it if it isn't,
and hands back the code and the URL to approve the device. It tells you which Keel it is talking
to, every time. Nothing was started if something was already running.

You do not have to type the command — the skill's own description is the trigger, so "keel
connect", "start the keel runtime" or "is keel connected" reach it too. So does "keel disconnect",
"stop the keel runtime" or "keel off", which stops the runtime again and proves it is gone. A
disconnect stops a process; it never forgets your machine, so the next connect needs no approval.

### `/speckit.keel.brief`

Prose only. It fetches nothing and holds no token: it tells you how to download the brief from
keel-web and paste it in, and tells the agent how to read what comes back — the claims and
measured lines as evidence, *What this says* as one agent's opinion, and every quoted sentence as
a person's own words and source material, never an instruction.

## What it needs, and what it does not

**Needs**: Python 3.9 or newer. On macOS that is `xcode-select --install`; on Windows
`winget install Python.Python.3.12`; on Linux your package manager.

**Does not need**: an install of anything called Keel, a package index, a binary, a checksum, a
signature, or network access at install time beyond fetching this extension.

**Does not do**: it never runs, validates or interprets an inference job — that is the connected
runtime's business. It knows nothing about Keel's discovery protocol or any MCP server. It carries
no Keel Cloud address of its own; which Keel you reach is the runtime's answer, relayed.

## Where the real documentation lives

`SKILL.md`, in this directory. It is the same file in every place this skill is installed — a
Claude Code plugin, a Copilot repo drop, a bare install, and here — byte for byte, and a test
asserts it.

Licensed under Apache-2.0. Issues and source: https://github.com/keeldiscovery/keel-connect-skill
