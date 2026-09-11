"""`keel disconnect`'s flow: stop the runtime this home is running, and prove it stopped.

spec `003-keel-disconnect` FR-002/FR-003/FR-009; keel-cloud
`canon/designs/keel-disconnect-design.md` §3.1, invariants D1-D10. There is a door into Keel --
a founder says "keel connect" and a runtime starts -- and this is the door out: read the heartbeat
that says which process is "the runtime on this home", send the signal that process's own shutdown
handler already honours (`cli._install_heartbeat_shutdown_handlers`, spec 021 FR-003), wait a
bounded time, **check that the pid is gone**, escalate once, and answer with one of four outcomes.

No new shutdown path is built: to the runtime, a `keel disconnect` is indistinguishable from the
founder pressing Ctrl+C in the terminal they started it in. This module is a caller of a path that
already exists, plus a wait and a proof.

It imports nothing that can reach a socket (D9), constructs no `CredentialStore` (D7), and knows
no wire vocabulary at all -- a job in flight is abandoned, never `/fail`ed, because "the AI could
not answer" is not what happened (D4). The only file it touches is `runtime.heartbeat.json`.

**Zombies (keel-e2e-eval DRIFT #57).** This module never forks or `Popen`s the runtime -- it only
ever signals a pid it read out of the heartbeat -- so it is never that pid's parent and has no
standing to `wait()` on it. When a signalled process dies but lands in state `Z` because *its*
real parent (typically the container's PID 1) never reaps it, `heartbeat.pid_alive` -- fixed for
exactly this -- already reports it as gone, so the outcome here is `stopped` like any other clean
exit; there is no fifth outcome and no extra key for it (the contract's own guarantees rule that
out -- see `contracts/disconnect-cli-output.md`'s "Stopped" shape). `_log_if_zombie` below writes
one line to stderr, outside the JSON contract, purely so a founder reading a container's log can
tell a zombie corpse from a real exit; reaping it is permanently someone else's job.
"""
from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

from . import heartbeat as heartbeat_module

# The two bounds (design decision 13; spec FR-003). Constants, not flags: a founder waiting on a
# cursor should not have to choose a number, and 15 seconds worst case is well inside any caller's
# patience. A caller that needs different ones is a test, and passes them as keyword arguments.
GRACE_SECONDS = 10.0
KILL_AFTER_SECONDS = 5.0

# How often the wait re-checks the pid. Small enough that the common path -- a runtime that leaves
# in tens of milliseconds -- reports a `waited_ms` that is about how long it really took.
POLL_INTERVAL_SECONDS = 0.05

# `SIGKILL` does not exist on Windows, where `os.kill` terminates the process unconditionally
# rather than delivering a catchable signal. There the first step has already stopped it and the
# escalation is unreachable in practice; the vocabulary of the outcome does not change.
TERM_SIGNAL = signal.SIGTERM
KILL_SIGNAL = getattr(signal, "SIGKILL", signal.SIGTERM)


def disconnect(
    home,
    *,
    grace: float = GRACE_SECONDS,
    kill_after: float = KILL_AFTER_SECONDS,
    kill=os.kill,
    alive=heartbeat_module.pid_alive,
    clock=time.monotonic,
    sleep=time.sleep,
) -> dict:
    """The design's §3.1, step for step. Returns the outcome dict; never raises, never blocks
    longer than `grace + kill_after`, never makes a network call.

    The four injected collaborators are the seam §8.1 names: two of the four outcomes cannot be
    produced by a real process on demand (nothing survives `SIGKILL` to order), and the escalation
    path would otherwise cost ten real seconds per test run.
    """
    home = Path(home)

    # 1 -- D1: a missing file, an unreadable one, malformed JSON, or JSON short a required field
    # are one answer. `heartbeat.read` already collapses all four to None; this adds no second
    # reading of its own.
    hb = heartbeat_module.read(home)
    if hb is None:
        return {"outcome": "not_running"}

    # 2 -- D2: a dead pid is removed and never signalled. This is the crash case (SIGKILL, a lost
    # power supply, an OOM kill): `status` has always reported it and left the file lying there,
    # and disconnect is the thing that finally cleans it up.
    if not alive(hb.pid):
        heartbeat_module.remove(home)
        _log_if_zombie(hb.pid)
        return {"outcome": "stale_pid_cleared", "pid": hb.pid}

    started_at = clock()

    # 3, 4 -- SIGTERM first, always (D5). The founder asked for a clean stop, and a SIGKILL first
    # would throw away the runtime's own heartbeat removal and, once it exists, its goodbye.
    if not _signal_and_wait(
        hb.pid, TERM_SIGNAL, started_at + grace, kill=kill, alive=alive, clock=clock, sleep=sleep
    ):
        # 5
        _remove_if_still_ours(home, hb.pid)
        _log_if_zombie(hb.pid)
        return {
            "outcome": "stopped",
            "pid": hb.pid,
            "waited_ms": _elapsed_ms(started_at, clock),
            "signal": "SIGTERM",
        }

    # 6 -- a process that did not take SIGTERM is either ignoring it outright or inside a call
    # that will not return. SIGKILL is the only remedy left, and it comes after the grace.
    if not _signal_and_wait(
        hb.pid,
        KILL_SIGNAL,
        started_at + grace + kill_after,
        kill=kill,
        alive=alive,
        clock=clock,
        sleep=sleep,
    ):
        # 7 -- the runtime never got the chance to remove its own heartbeat here, which is exactly
        # what `_remove_if_still_ours` exists for.
        _remove_if_still_ours(home, hb.pid)
        _log_if_zombie(hb.pid)
        return {
            "outcome": "stopped",
            "pid": hb.pid,
            "waited_ms": _elapsed_ms(started_at, clock),
            "signal": "SIGKILL",
        }

    # 8 -- D6: the heartbeat is LEFT IN PLACE. Removing it would tell `status`, and therefore the
    # skill, "not running" about a process that is still polling and still claiming jobs -- the
    # single worst lie this system can tell, and the one that produces two runtimes on one home.
    return {
        "outcome": "timeout",
        "pid": hb.pid,
        "waited_ms": _elapsed_ms(started_at, clock),
    }


def _signal_and_wait(pid, signal_number, deadline, *, kill, alive, clock, sleep) -> bool:
    """Sends one signal and waits for the pid to go. Returns whether it is **still alive** at the
    deadline -- i.e. `True` means "escalate or give up".

    A `ProcessLookupError` from the signal itself means the process left between the liveness
    check and the signal, which is a stop like any other. A `PermissionError` means this user may
    not signal that pid: there is no remedy in user space, so it falls through to the wait, whose
    verdict will be that the process is still there.
    """
    try:
        kill(pid, signal_number)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    while True:
        if not alive(pid):
            return False
        if clock() >= deadline:
            return True
        sleep(POLL_INTERVAL_SECONDS)


def _log_if_zombie(pid: int) -> None:
    """One line to stderr -- never stdout, which the contract reserves for exactly one line of
    JSON -- when the pid this disconnect just reported gone is, at this instant, a zombie rather
    than fully reaped. Purely diagnostic: `pid_alive` already decided `outcome`, this only tells a
    founder reading a container's log why `ps`/`docker top` may still show the pid for a while.
    `heartbeat_module.is_zombie` is called directly (not through the injected `alive` seam, which
    stays a plain bool) and any failure to read the process table here is swallowed -- a logging
    side-channel must never turn a successful disconnect into an error.
    """
    try:
        if heartbeat_module.is_zombie(pid):
            print(
                f"keel-runtime: pid {pid} is gone but still shows as a zombie (state Z) -- "
                "its parent process, not this command, is responsible for reaping it",
                file=sys.stderr,
                flush=True,
            )
    except Exception:  # noqa: BLE001 -- a diagnostic line must never fail the disconnect
        pass


def _remove_if_still_ours(home: Path, pid: int) -> None:
    """D3: re-read the heartbeat and unlink it only while it still names the pid that was
    signalled.

    On the common path there is nothing to do -- the runtime removes its own heartbeat inside its
    SIGTERM handler before it exits. The call exists for the `SIGKILL` path, where it never got
    the chance, and for a runtime old enough to predate spec 021's handler. Re-reading rather than
    unlinking blind is what stops a disconnect from deleting the record of a *different* runtime
    that has started on this home in the meantime.
    """
    current = heartbeat_module.read(home)
    if current is None or current.pid != pid:
        return
    heartbeat_module.remove(home)


def _elapsed_ms(started_at: float, clock) -> int:
    """Milliseconds since the **first signal**, not since process start -- so a caller can see the
    difference between a runtime that stopped in 80ms and one that took nine seconds to leave a
    job."""
    return int(round((clock() - started_at) * 1000))
