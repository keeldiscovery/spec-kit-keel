---
name: "keel-connect"
description: "Use when the user says or means \"keel connect\" -- including \"connect keel\", \"start the keel runtime\", \"launch keel connect\", \"is keel connected\", \"check keel's status\" -- or \"keel disconnect\", \"stop the keel runtime\", \"shut keel down\", \"keel off\"; or when a Keel action has just failed because no runtime is connected. Covers only the local keel-runtime process on this machine, not Keel's discovery protocol or any MCP server."
license: "Apache-2.0"
---

## What this skill does

Two jobs, one connection: decide whether a Keel runtime is already running and connected to Keel
Cloud on this machine and start it if it is not -- and **stop it again when the user asks**.
Nothing here understands what a connected runtime is *for* -- that is Keel Cloud's and the
runtime's own business, not this skill's.

## Two jobs, and which is which

**Starting or checking** -- anything that means "connect", "start", "is it running" -- runs
`scripts/keel_connect_check.py`.

**Stopping** -- anything that means "disconnect", "stop", "shut down", "stop polling" -- runs
`scripts/keel_disconnect.py`.

If the request is ambiguous, **ask which they meant; never run the connect check to find out.**
The connect check's whole job is to *start* a runtime when none is running -- running it on a
request that meant "stop" does the opposite of what was asked, silently. The disconnect script has
no such hazard: run against a home with nothing on it, it answers `not_running` and starts nothing.
Ambiguity therefore resolves toward disconnect, and toward asking.

**The runtime travels inside this skill.** `keel_runtime/` sits beside `scripts/`, and the script
runs it with the interpreter that ran the script. Nothing is downloaded and nothing has to be
installed. The one thing the user might not already have is a Python 3.9 or newer.

All of the actual logic lives in two deterministic scripts, `scripts/keel_connect_check.py` and
`scripts/keel_disconnect.py` (paths resolved relative to this `SKILL.md`'s own directory). Run the
one the request calls for, parse its one line of JSON, and follow the instructions below for the
`outcome` you get back. Their full, stable contracts are
`specs/001-keel-connect-check/contracts/skill-script-output.md` and
`specs/002-keel-disconnect/contracts/skill-disconnect-output.md` -- read those files if anything
below is ambiguous; they are the source of truth and this is a summary for quick use.

## Running the check

```bash
python3 <this skill's directory>/scripts/keel_connect_check.py
```

<!-- D5 exception, deliberate and the only one in this file: the line below names an agent host,
     which no *reply* to a user ever may. It is an instruction to the agent, not a sentence anyone
     reads. -->
If you are GitHub Copilot, add `--host copilot`.

No other flag is required, or wanted. Do not pass a base URL, an executor or a credential backend
unless the user has specifically told you theirs -- the script and the runtime already know
sensible defaults, and a flag you guessed will outrank the user's own configuration.

**If `python3` is not found at all**, the user has no Python, and no script can tell you so -- the
command simply fails. Tell them Keel needs Python 3.9 or newer, installed once: on macOS
`xcode-select --install`, or https://www.python.org/downloads/; on Windows
`winget install Python.Python.3.12`, or Python from the Microsoft Store; on Linux their package
manager, e.g. `sudo apt install python3`. Then ask them to say "keel connect" again.

## Interpreting each outcome

The script prints exactly one line of JSON with an `outcome` key. Match it against the seven values
below and reply in plain language -- **never show the raw JSON**.

Every outcome also carries `environment`: which Keel this is. **End your reply with one clause
naming it** -- "on Keel Cloud", or "on `localhost:18081`" written exactly as given. When it is
`null` no runtime answered, so say nothing about which Keel; do not guess one.

**`already_connected`** -- a runtime is already running **and has completed device approval**.
Nothing was started.
> Tell the user Keel is already connected. You may mention the `agent_session_id` as context, but
> it is rarely something a human needs to see.

**`connected`** -- nothing was running, so the check started the runtime, and it connected
immediately using a saved credential from a previous session -- no approval was needed.
> Tell the user Keel just reconnected on its own using a saved credential; no action needed from
> them.

**`authorization_started`** -- the runtime is waiting for the user to approve this device: either it
was just started, or it was already running and waiting when this check ran (a repeat "keel
connect" while approval is still pending gets this same outcome again, with the same code).
> Relay the `user_code` and `verification_uri` **verbatim** -- do not shorten, rewrite or rebuild
> the URL; the Keel that issued it is the only thing that knows where its own approval screen is.
> If this is a repeat check and the user has seen this code before, say so plainly -- something
> like "still waiting for you to approve -- here is the code again" -- rather than presenting it as
> if it were new. Otherwise tell them to open it and approve, and that they can just say "keel
> connect" again in a little while to confirm it went through.

**`authorization_pending_timeout`** -- the runtime was started, but it had not printed an
authorization code (or connected) by the time the check stopped waiting. The process is still
running in the background: not dead, not abandoned.
> Tell the user the runtime is starting but has not shown a code yet -- ask them to wait a few
> seconds and say "keel connect" again, which will either show the code now or confirm the
> connection if it completed in the meantime.

**`python_too_old`** -- the Python that ran the check is older than 3.9. Nothing was resolved and
nothing was started.
> Relay the `message` -- it already names the version they have, the version Keel needs, and the
> one install command for their operating system. Tell them it is a one-time install, and to say
> "keel connect" again afterwards. Do not offer a workaround; there isn't one.

**`runtime_unavailable`** -- the runtime that is supposed to travel inside this skill is not there,
and no `keel` command was found either.
> Relay the `message` in your own words: the skill directory looks incomplete, so they should
> reinstall or re-copy it in full. This is a broken installation, not something the user forgot to
> do -- do not tell them to install anything from a package index.

**`internal_error`** -- something broke that is not a normal "not connected" situation: the
runtime's `status` did not answer the way it is supposed to, or the runtime could not be started at
all. This is the only outcome that exits non-zero.
> Tell the user something unexpected happened, share the `message`, and suggest they check their
> Keel installation directly. Do not guess at a fix on their behalf.

## Running the disconnect

```bash
python3 <this skill's directory>/scripts/keel_disconnect.py
```

No flag is required, or wanted. This script starts nothing, contacts no server and never touches a
saved credential -- it stops the runtime on this machine and proves it is gone. Running it when
nothing is running is a normal, safe thing to do.

## Interpreting each disconnect outcome

One line of JSON with an `outcome` key, one of the six values below. Reply in plain language --
**never show the raw JSON** -- and end with the same one clause naming `environment` that every
connect reply ends with.

**`disconnected`** -- the runtime was running, was asked to stop, and has been seen to be gone.
> Tell the user Keel has stopped and is no longer polling for work. Mention that their saved
> credential is untouched, so saying "keel connect" later reconnects with no approval step.

**`not_running`** -- nothing was running on this machine; nothing was done.
> Tell them there was nothing to stop. This is not an error, and do not offer to start one unless
> they ask.

**`stale_pid_cleared`** -- no runtime was running, and a leftover file from one that had crashed or
been killed was cleaned up.
> Tell them exactly that: nothing was running, and the leftover was tidied away. Nothing else was
> needed.

**`did_not_stop`** -- the runtime would not stop and is still running.
> Relay the `pid` and say it is stuck in something the operating system will not interrupt. Suggest
> they look at that process themselves. **Do not offer to run "keel connect" now** -- the old
> runtime is still polling, and starting a second one against the same machine is worse than the
> problem.

**`runtime_unavailable`** -- the runtime that is supposed to travel inside this skill is not there,
and no `keel` command was found either.
> Relay the `message` in your own words: the skill directory looks incomplete, so they should
> reinstall or re-copy it in full. This is a broken installation, not something the user forgot.

**`internal_error`** -- the runtime's `disconnect` did not answer the way it is supposed to. This is
the only disconnect outcome that exits non-zero.
> Share the `message`. If it says their runtime predates the disconnect command, tell them their
> Keel installation needs updating. Otherwise suggest they check that installation directly.

## What "keel connect" says right after a disconnect

**After `disconnected`: nothing to worry about.** That outcome is reported only once the old process
has been seen to be gone, so "keel connect" straight afterwards is safe and starts exactly one
runtime. Say so if they ask.

**After `did_not_stop`: do not offer a connect at all.** The old runtime is still running and still
claiming work. A connect check now would truthfully report `already_connected`, which is unhelpful,
and any other attempt would put two runtimes on one machine. The next step is the stuck process,
not a new one.

**If they say "keel connect" while a disconnect is still in flight**, they may briefly get a code
for a second runtime while the first is on its way out. It resolves itself within a few seconds --
the old one exits, the new one takes over. If it happens, say so plainly rather than starting
another; do not run either script again to "fix" it.

## What this skill deliberately does not do

- It does not run, validate, or interpret any inference job -- that is the connected runtime's job,
  entirely out of this skill's view.
- It does not know anything about Keel's discovery protocol, MCP hosting, or any other Keel-branded
  skill. Do not reach for anything from one while handling a "keel connect" request.
- It never waits on human approval itself (that is an out-of-band step the user takes in their
  browser) -- it only reports whether that wait has a code to show yet.
- A disconnect stops a process; it does not forget a machine. It never clears a credential, never
  cancels or fails a job in flight, and never reaches Keel Cloud. If the user wants Keel to forget
  this machine, tell them this skill cannot do that.
- It carries no Keel Cloud address of its own. Which Keel a user reaches is the runtime's answer,
  relayed; never construct, complete or correct a URL it hands you.
