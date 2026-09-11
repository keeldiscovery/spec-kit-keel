"""Local liveness heartbeat for a running `keel connect` process (spec 021).

One file per `$KEEL_HOME`, `runtime.heartbeat.json` (sibling of `credentials.json`/
`config.json`), holding only the current state -- no history, overwritten in place on
every write. Written atomically (temp file in the same directory, then `os.replace`,
research.md §2) so a reader never observes a partial write. `read()` never raises to
its caller: a missing file, unreadable/malformed JSON, or a file missing a required
key is all treated identically to "no heartbeat" (data-model.md's validation rule,
spec Acceptance Scenario 6) -- this module only ever answers with a `Heartbeat` or
`None`.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

HEARTBEAT_FILENAME = "runtime.heartbeat.json"

_REQUIRED_FIELDS = ("pid", "agent_session_id", "base_url", "last_heartbeat_at")

# `state` (keel-cloud DRIFT #51 / `canon/designs/keel-disconnect-design.md` §6, edge case (g)):
# a runtime blocked in device authorization has a pid and a home but no agent session yet. It is
# written by `write_awaiting_approval` and overwritten with `STATE_CONNECTED` the moment the real
# heartbeat exists (`agent_session.create_agent_session`, `poller._write_heartbeat`). A file with
# no `state` key at all -- every heartbeat this runtime ever wrote before this change -- is
# `STATE_CONNECTED`: it could only have been written *after* an agent session existed.
STATE_CONNECTED = "connected"
STATE_AWAITING_APPROVAL = "awaiting_approval"


@dataclass
class Heartbeat:
    pid: int
    agent_session_id: Optional[str]
    base_url: str
    last_heartbeat_at: str
    state: str = STATE_CONNECTED
    # spec `007-launcher-version` (keel-cloud `canon/designs/upgrade-in-place-design.md`): the
    # version of the skill that launched this process, as it told us (`connect
    # --launcher-version`), so a newer skill can tell an older running runtime from its own; and
    # the job this process is working on right now, so that skill never replaces a runtime
    # mid-job. Both absent from any heartbeat written before this spec, which `read` treats as
    # "unknown launcher, idle" -- the shape an older runtime would have reported had it known to.
    launcher_version: Optional[str] = None
    job_id: Optional[str] = None


def path(home: Path) -> Path:
    return Path(home) / HEARTBEAT_FILENAME


def write(home: Path, heartbeat: Heartbeat) -> None:
    """Atomic write: a `.tmp` file in the same directory, then `os.replace` (research.md
    §2) -- keeps the rename on the same filesystem, which is what makes it atomic.
    """
    target = path(home)
    tmp_path = target.with_name(target.name + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(heartbeat)))
    os.replace(tmp_path, target)


def write_awaiting_approval(home: Path, pid: int, base_url: str,
                            launcher_version: Optional[str] = None) -> None:
    """Written the moment `connect` has a pid and a home -- before the device code is even
    requested, let alone redeemed (keel-cloud DRIFT #51: a runtime alive and waiting for device
    approval was invisible to both `status` and `disconnect`, because the only heartbeat write
    used to happen after the agent session existed).

    Carries no `agent_session_id` -- none exists yet -- and `state=STATE_AWAITING_APPROVAL`, so
    `disconnect` (which only ever reads `pid`) finds and stops this process at any point in its
    life, and `status` can say "running, not yet connected" without claiming `connected: true`
    of a session that does not exist. `agent_session.create_agent_session` overwrites this same
    file with the real heartbeat -- `state=STATE_CONNECTED` -- the moment the agent session is
    created, exactly as it already overwrites whatever the previous run left behind.

    The caller (`auth.authorize_device`) also calls this once per poll tick while it waits, so a
    founder who takes minutes to click approve does not watch this record go stale.
    """
    write(
        home,
        Heartbeat(
            pid=pid,
            agent_session_id=None,
            base_url=base_url,
            last_heartbeat_at=now_iso8601(),
            state=STATE_AWAITING_APPROVAL,
            launcher_version=launcher_version,
        ),
    )


def read(home: Path) -> Optional[Heartbeat]:
    """Returns `None` on a missing file, unreadable/malformed JSON, or JSON missing any
    required field -- never raises (data-model.md's validation rule).
    """
    try:
        with open(path(home), "r", encoding="utf-8") as handle:
            raw = handle.read()
    except OSError:
        return None

    try:
        data = json.loads(raw)
    except ValueError:
        return None

    if not isinstance(data, dict) or any(field not in data for field in _REQUIRED_FIELDS):
        return None

    raw_agent_session_id = data["agent_session_id"]
    raw_state = data.get("state")
    try:
        return Heartbeat(
            pid=int(data["pid"]),
            agent_session_id=(
                None if raw_agent_session_id is None else str(raw_agent_session_id)
            ),
            base_url=str(data["base_url"]),
            last_heartbeat_at=str(data["last_heartbeat_at"]),
            state=str(raw_state) if raw_state is not None else STATE_CONNECTED,
            launcher_version=(
                None if data.get("launcher_version") is None else str(data["launcher_version"])
            ),
            job_id=None if data.get("job_id") is None else str(data["job_id"]),
        )
    except (TypeError, ValueError):
        return None


def remove(home: Path) -> None:
    """Deletes the heartbeat file; idempotent -- swallows `FileNotFoundError`."""
    try:
        path(home).unlink()
    except FileNotFoundError:
        pass


def pid_alive(pid: int) -> bool:
    """POSIX (macOS/Linux): `os.kill(pid, 0)` -- `ProcessLookupError` => False,
    `PermissionError` => True (a pid we can't signal still exists) -- **except** a pid
    that is `os.kill`-alive but a zombie, which is not alive (keel-e2e-eval DRIFT #57):
    a process that has already exited keeps its process-table entry, and therefore keeps
    answering `os.kill(pid, 0)`, until whatever its *real* parent is calls `wait()` on it.
    On the founder's own macOS, or any systemd Linux, that reaping happens within a poll
    interval and this was never visibly wrong -- but inside a container whose PID 1 is an
    ordinary process (a devcontainer, a CI job, `docker run python3` with no `--init`),
    nothing ever reaps it, and a runtime that died on the very first `SIGTERM` was reported
    `disconnect: timeout` (the skill layer's `did_not_stop`) for the full 15-second bound,
    about a process that was already gone. `is_zombie` below is the correction; a pid this
    process cannot signal (`PermissionError`) is left as "alive" unchanged -- it belongs to
    another user, and there is no remedy for that case regardless.

    Windows: `ctypes`/`OpenProcess`, since `os.kill(pid, 0)` is not the same signal-0 probe
    there (research.md §3; no `psutil` dependency, matching spec 020 FR-025's stdlib-only
    posture). Windows has no zombie state in this sense -- a terminated process's handle
    simply stops being valid -- so no equivalent check is needed there.
    """
    if sys.platform == "win32":
        return _pid_alive_windows(pid)  # pragma: no cover -- exercised on Windows only
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return not is_zombie(pid)


def is_zombie(pid: int) -> bool:
    """True when `pid` exists (answers `os.kill(pid, 0)`) but has already exited and not
    been reaped by its real parent -- state `Z`, "zombie" or "defunct" depending on the
    tool that prints it. Exported (not `_`-prefixed) so `disconnect` can log the distinction
    without this module's liveness seam (`pid_alive`, which stays a plain bool) needing to
    change shape.

    Linux has `/proc/<pid>/stat`, whose third field is the state letter -- read directly,
    no subprocess, no shell. macOS/BSD have no `/proc`; `ps -o stat= -p <pid>` is the
    portable stand-in there (an argv list passed straight to `subprocess.run`, never a
    shell string). Either read failing -- the pid vanished between the caller's `os.kill`
    probe and this check, `ps` is missing, anything -- answers "not a zombie": this
    function only ever narrows an already-`os.kill`-alive pid from "alive" to "gone", never
    the reverse, so an inconclusive read must side with the caller's cheaper probe rather
    than manufacture a new way to say "dead" that `pid_alive`'s docstring doesn't promise.
    """
    if sys.platform == "win32":
        return False  # pragma: no cover -- exercised on Windows only; no zombie state there
    if Path("/proc").is_dir():
        state = _proc_stat_state(pid)
    else:
        state = _ps_stat_state(pid)
    return state == "Z"


def _proc_stat_state(pid: int) -> Optional[str]:
    """The state letter from `/proc/<pid>/stat`, or `None` if it can't be read/parsed."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    return _parse_proc_stat_state(raw)


def _parse_proc_stat_state(raw: str) -> Optional[str]:
    """Parses one `/proc/<pid>/stat` line into its state field (man proc(5), field 3).

    The line is `pid (comm) state ...`, and `comm` -- the process's own name, which it
    controls (`prctl(PR_SET_NAME, ...)`, or just `argv[0]`) -- is the one field that isn't
    whitespace-delimited: it is wrapped in parentheses specifically because it may itself
    contain spaces, or even parentheses of its own. The only field guaranteed not to appear
    inside `comm` is the *matching close* of the *opening* paren right after the pid -- but
    finding that would need a real parser, and proc(5) gives a cheaper guarantee instead:
    nothing after `comm` ever contains a `)`, so the **last** `)` in the whole line is always
    `comm`'s close paren, whatever `comm` contains. Split there, then take the first
    whitespace-delimited token after it.
    """
    close_paren = raw.rfind(")")
    if close_paren == -1:
        return None
    fields = raw[close_paren + 1 :].split()
    if not fields:
        return None
    return fields[0]


def _ps_stat_state(pid: int) -> Optional[str]:
    """The leading state letter from `ps -o stat= -p <pid>` (e.g. `Z`, `Z+`, `S`, `R+`) --
    macOS/BSD's answer where there is no `/proc` to read directly. `capture_output`/`text`
    keep this stdlib-only (research.md §3's posture); the argv list form never touches a
    shell. `ps` printing nothing (pid already gone) or failing to run at all both answer
    `None` -- inconclusive, not "zombie".
    """
    try:
        result = subprocess.run(
            ["ps", "-o", "stat=", "-p", str(pid)],
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    stat = result.stdout.strip()
    return stat[:1] or None


def _pid_alive_windows(pid: int) -> bool:  # pragma: no cover -- exercised on Windows only
    """`OpenProcess` alone is not enough: a Windows process object -- and therefore its pid --
    stays valid for as long as *any* handle to it is still open, which very much includes the
    handle a caller's own `subprocess.Popen` keeps until it is waited on (or garbage-collected).
    A test (or a founder's own shell) that spawned the runtime and has not yet reaped it makes
    `OpenProcess` succeed for a pid that has already exited -- Windows' nearest equivalent to a
    POSIX zombie (module docstring, DRIFT #57's Windows counterpart). `GetExitCodeProcess` is the
    second half of the probe: `STILL_ACTIVE` (259) means genuinely running, anything else means
    the process has already terminated, whatever else still points at it.
    """
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    STILL_ACTIVE = 259
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.c_ulong()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False  # could not be read at all -- no stronger claim than "not alive"
        return exit_code.value == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def is_stale(
    heartbeat: Heartbeat, stale_after_seconds: float, now: Optional[datetime] = None
) -> bool:
    """True when `heartbeat.last_heartbeat_at`'s age exceeds `stale_after_seconds`.

    An unparseable timestamp is treated as stale -- there is no fresher answer to give.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    try:
        written_at = _parse_iso8601(heartbeat.last_heartbeat_at)
    except ValueError:
        return True
    age_seconds = (now - written_at).total_seconds()
    return age_seconds > stale_after_seconds


def now_iso8601() -> str:
    """The current UTC time in the format this module writes/reads: millisecond
    precision, `Z` suffix (e.g. `2026-09-02T13:04:11.482Z`).
    """
    now = datetime.now(timezone.utc)
    return now.strftime("%Y-%m-%dT%H:%M:%S.") + f"{now.microsecond // 1000:03d}Z"


def _parse_iso8601(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed
