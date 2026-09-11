#!/usr/bin/env python3
"""Checks whether a local keel-runtime is connected to Keel Cloud, and launches `keel connect` in
the background if not.

This is the entire implementation behind the `keel-connect` skill (`../SKILL.md`). It never talks
to Keel Cloud itself -- it shells out to the runtime's own `status` (a fast, offline, local check)
and, when nothing is running, launches a detached `connect` and watches its log for the
human-facing signal lines the runtime already prints.

Since spec `003-bundled-runtime` (keel-cloud `canon/designs/keel-skill-design.md`) **the runtime
travels inside this skill**: `<skill root>/keel_runtime/`, put there by `make runtime`, resolved by
`_runtime_location.py` and run with the interpreter that ran this file. Nothing is downloaded and
nothing has to be installed. The one prerequisite is a Python 3.9, which is what the version gate
below is for.

Standard library only -- no dependency beyond what a bare `python3` provides, since a host invokes
this as a plain subprocess.

Stable output contract: `../specs/001-keel-connect-check/contracts/skill-script-output.md`, seven
outcomes. Every shape documented there is produced from exactly one place in this file (`_emit`),
so the contract and the implementation cannot drift apart silently (invariants X-1, X-2).
"""
import sys

# ------------------------------------------------------------------------------- the version gate
#
# Invariant X-3: the first executable statement, above every import but `sys`, in syntax every
# Python 3 parses -- no f-strings, no annotations, no walrus, no `pathlib`. A founder on 3.8 must
# get a sentence, not a `SyntaxError`, so nothing below this block may use newer syntax either:
# a module is compiled whole before its first line runs.
#
# The named platform is an **operating system**, which is neither a host nor an ecosystem, so this
# is not an exception to invariant D4 or D5 (design §3.3).
#
# `python_missing` is not an outcome and cannot be: a script that cannot start cannot emit one.
# With no `python3` at all the host gets *command not found*, so that answer lives in the
# instruction layer -- `SKILL.md`'s *Running the check* and `README.md`.
if sys.version_info < (3, 9):
    _HOW = {
        "darwin": "run `xcode-select --install`, or get it from https://www.python.org/downloads/",
        "win32": "run `winget install Python.Python.3.12`, or install Python from the Microsoft Store",
    }.get(sys.platform, "use your package manager, e.g. `sudo apt install python3`")
    sys.stdout.write('{"outcome": "python_too_old", "found": "%d.%d", "required": "3.9", '
                     '"environment": null, "message": "Keel needs Python 3.9 or newer; this is '
                     'Python %d.%d. Install it once and say \\"keel connect\\" again: %s"}\n'
                     % (sys.version_info[0], sys.version_info[1],
                        sys.version_info[0], sys.version_info[1], _HOW))
    raise SystemExit(0)

import argparse
import json
import os
import subprocess
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _runtime_location  # noqa: E402 -- must follow the gate and the path insert above

DEFAULT_WAIT_SECONDS = 8.0
STATUS_SUBPROCESS_TIMEOUT_SECONDS = 15.0
LAUNCH_SIGNAL_POLL_INTERVAL_SECONDS = 0.25
LAUNCH_LOG_FILENAME = "keel-connect-check.launch.log"

USER_CODE_PREFIX = "KEEL_USER_CODE="
VERIFICATION_URI_PREFIX = "KEEL_VERIFICATION_URI="
AGENT_SESSION_ID_PREFIX = "KEEL_AGENT_SESSION_ID="

HOST_CLAUDE = "claude"
HOST_COPILOT = "copilot"
HOST_AUTO = "auto"

# Which executor name each detected host asks the runtime for (design §5.3). `claude-code` is a
# permanent accepted alias of the canonical `claude` (invariant C-12) and is the name today's
# runtime knows, so it is the one sent: an alias promised never to be removed is safe to send, and
# a canonical name the runtime does not yet accept is not. `copilot` is spec
# `005-copilot-executor`'s and is sent as written.
HOST_EXECUTORS = {HOST_CLAUDE: "claude-code", HOST_COPILOT: "copilot"}


# -------------------------------------------------------------------------------- argument parsing


def build_parser():
    parser = argparse.ArgumentParser(
        prog="keel_connect_check",
        description=(
            "Check whether a keel-runtime is connected to Keel Cloud; launch `keel connect` "
            "in the background if not. See specs/001-keel-connect-check/contracts/"
            "skill-script-output.md for this script's stable JSON output contract."
        ),
    )
    parser.add_argument(
        "--runtime-path",
        dest="runtime_path",
        default=None,
        help=argparse.SUPPRESS,  # X-4: a development override; no founder-facing text names it
    )
    parser.add_argument(
        "--host",
        dest="host",
        choices=[HOST_CLAUDE, HOST_COPILOT, HOST_AUTO],
        default=HOST_AUTO,
        help="which agent host is running this check; 'auto' reads the environment it was "
        "launched into and says nothing when that is silent or contradictory",
    )
    parser.add_argument("--base-url", dest="base_url", default=None,
                        help="passed through to 'keel connect' if a launch is needed")
    parser.add_argument("--executor", dest="executor", default=None,
                        help="passed through to 'keel connect' if a launch is needed; when given, "
                        "it wins over --host outright")
    parser.add_argument(
        "--credential-backend",
        dest="credential_backend",
        choices=["auto", "file", "keyring"],
        default=None,
        help="passed through to 'keel connect' if a launch is needed",
    )
    parser.add_argument(
        "--no-browser",
        dest="no_browser",
        action="store_true",
        help="passed through to 'keel connect' if a launch is needed",
    )
    parser.add_argument(
        "--home",
        dest="home",
        default=None,
        help="overrides KEEL_HOME for both the status check and any launch. When neither is "
        "given, the runtime derives its own home from the Keel it resolves and reports it back "
        "-- this script does not guess one.",
    )
    parser.add_argument(
        "--wait-seconds",
        dest="wait_seconds",
        type=float,
        default=DEFAULT_WAIT_SECONDS,
        help="how long to watch a launched connect's log for a signal before reporting "
        "authorization_pending_timeout (default: %s)" % DEFAULT_WAIT_SECONDS,
    )
    return parser


def resolve_given_home(args, environ=None):
    """The home this script was *given*, or `None` (design §6.3).

    `None` means "let the runtime decide": since spec `004-shipped-runtime` the runtime derives
    `~/.keel/<host-slug>/` from the Keel it resolved, so a credential issued by one Keel is never
    presented to another. This script stops guessing a default of its own -- it passes `--home`
    only when it was given one, and otherwise reports back the `home` that `status` named, which
    is also where the launch log goes.
    """
    env = os.environ if environ is None else environ
    if args.home:
        return os.path.expanduser(args.home)
    env_home = env.get("KEEL_HOME")
    if env_home:
        return os.path.expanduser(env_home)
    return None


# --------------------------------------------------------------------------------- host detection


def detect_host(environ=None):
    """Design §5.3 step 2: the environment this process was launched into, or `None`.

    D5 grep exemption, explicitly: this table reads environment *variable names*, which is not a
    host name in a founder-facing reply. No outcome shape changes and no message mentions a host
    -- which executor was chosen is visible in the runtime's own log and in `keel status`.

    **Two different answers means no answer.** That is not hypothetical: the environment that
    taught this table those names was one host's CLI running *inside* the other, carrying both
    markers at once. `COPILOT_AGENT_SESSION_ID` leaks arbitrarily deep down a process tree -- it
    means "somewhere in my ancestry", never "my parent".
    """
    env = os.environ if environ is None else environ
    answers = set()

    if (env.get("COPILOT_AGENT_SESSION_ID") or "").strip():
        answers.add(HOST_COPILOT)
    if env.get("COPILOT_CLI") == "1":
        answers.add(HOST_COPILOT)
    if env.get("CLAUDECODE") == "1":
        answers.add(HOST_CLAUDE)

    ai_agent = (env.get("AI_AGENT") or "").strip()
    if ai_agent.startswith("github_copilot"):
        answers.add(HOST_COPILOT)
    if ai_agent.startswith("claude-code"):
        answers.add(HOST_CLAUDE)

    if len(answers) == 1:
        return answers.pop()
    return None


def executor_for(args, environ=None):
    """The `--executor` value to pass to `connect`, or `None` to pass none at all.

    Explicit beats detected: a founder who named an executor gets it, always. `--host claude` /
    `--host copilot` name the host outright; `auto` runs the detection table, which answers `None`
    when the environment is silent or contradictory -- and `None` means this script says nothing
    and leaves the runtime's own chain (`KEEL_EXECUTOR`, config, default) untouched.

    Never consulted on a `status` call: `--executor` is passed on `connect` only (design §5.3).
    """
    if args.executor:
        return args.executor
    host = args.host
    if host == HOST_AUTO:
        host = detect_host(environ)
    if host is None:
        return None
    return HOST_EXECUTORS.get(host)


# --------------------------------------------------------------------------- the bundle's version


def bundle_version():
    """The version of the skill this script travels in: the `VERSION` file at the skill's root,
    one number for every packaging (design D7). `None` when the file is not there -- a tree copied
    by hand, or a test's relocated copy -- in which case no upgrade is ever attempted, because a
    skill that cannot name its own version cannot claim to be newer than anything.
    """
    root = _runtime_location.skill_root()
    try:
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as handle:
            text = handle.read().strip()
    except OSError:
        return None
    return text or None


def _semver(text):
    """`(major, minor, patch)` for a bare semver string, else `None`. Anything that is not three
    integers joined by dots -- a `null`, a sha suffix, a word -- is `None`, and `None` compares as
    older than any number: a runtime that could not say who launched it predates the launchers
    that can (keel-runtime spec 007)."""
    if not isinstance(text, str):
        return None
    parts = text.strip().split(".")
    if len(parts) != 3 or not all(part.isdigit() for part in parts):
        return None
    return tuple(int(part) for part in parts)


def bundle_is_newer_than(running_version):
    """Whether this skill's own version is strictly newer than the version that launched the
    running runtime (keel-cloud `canon/designs/upgrade-in-place-design.md` §3). An unknown
    running version counts as older; an unknown bundle version never counts as newer."""
    mine = _semver(bundle_version())
    if mine is None:
        return False
    theirs = _semver(running_version)
    return theirs is None or theirs < mine


# ------------------------------------------------------------------------------------ status check


def run_status(location, home):
    """Invokes `<runtime> status [--home <home>]` and parses its documented contract (keel-cloud
    `specs/021-keel-runtime-status/contracts/status-cli-output.md`). Returns None on any failure to
    honour it -- a crash, non-zero exit, output that isn't exactly one JSON line, or JSON missing
    the required `running` key -- so the caller reports `internal_error` rather than letting an
    exception escape.
    """
    argv = ["status"]
    if home:
        argv += ["--home", str(home)]
    try:
        completed = _runtime_location.run_capturing(
            location, argv, timeout=STATUS_SUBPROCESS_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired):
        return None

    if completed.returncode != 0:
        return None

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        return None

    try:
        data = json.loads(lines[0])
    except ValueError:
        return None

    if not isinstance(data, dict) or "running" not in data:
        return None

    return data


# ------------------------------------------------------------------------------ launching connect


def launch_connect(location, log_home, args, executor):
    """Launches `connect` detached, with its combined output redirected to a log file under the
    runtime's home. Returns the launched process's pid and the log path.

    `--home` is passed to the child only when this script was *given* one (§6.3); `log_home` is
    where the log goes, which is the home `status` just named. Raises OSError if the subprocess
    cannot even be started (surfaced by the caller as `internal_error`).

    Nothing is written outside the runtime's home, and no `PATH` or shell profile is ever touched
    (invariant X-6).
    """
    if not os.path.isdir(log_home):
        os.makedirs(log_home)
    log_path = os.path.join(log_home, LAUNCH_LOG_FILENAME)

    argv = ["connect"]
    given_home = resolve_given_home(args)
    if given_home:
        argv += ["--home", given_home]
    if args.base_url:
        argv += ["--base-url", args.base_url]
    if executor:
        argv += ["--executor", executor]
    if args.credential_backend:
        argv += ["--credential-backend", args.credential_backend]
    if args.no_browser:
        argv += ["--no-browser"]
    # keel-runtime spec 007: the runtime records who launched it, so a newer skill can tell an
    # older running runtime from its own (design upgrade-in-place §3).
    version = bundle_version()
    if version:
        argv += ["--launcher-version", version]

    popen_kwargs = {}
    if os.name == "posix":
        popen_kwargs["start_new_session"] = True
    else:  # pragma: no cover -- exercised on Windows only
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    log_handle = open(log_path, "w")
    try:
        process = subprocess.Popen(
            location.argv_prefix + argv,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            env=location.child_env(),
            cwd=location.child_cwd(),
            **popen_kwargs
        )
    finally:
        # The child has already duplicated the fd -- closing ours does not stop it writing.
        log_handle.close()
    return process.pid, log_path


def _extract_value(content, prefix):
    for line in content.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):]
    return None


PENDING_TIMEOUT_MESSAGE = (
    "keel connect did not report an authorization code or a connection within "
    "the wait window; it may still be starting -- check the log file or try "
    "again shortly."
)


def _read_log(log_path):
    """The launched process's log, or `""` if it is not there yet or not readable. Shared by
    `await_launch_signal` (a launch this call just made) and `_resume_pending_authorization` (a
    launch an earlier call made, or the runtime itself before any script ran)."""
    if not os.path.exists(log_path):
        return ""
    try:
        handle = open(log_path, "r", errors="replace")
        try:
            return handle.read()
        finally:
            handle.close()
    except OSError:
        return ""


def await_launch_signal(log_path, wait_seconds):
    """Poll the launched process's log for a bounded time for either signal the runtime's own
    `cli.py`/`auth.py` already print. Returns an outcome dict without `pid`/`log_file`/
    `environment` -- the caller fills those in, since this function only knows about the log.
    """
    deadline = time.monotonic() + wait_seconds
    while True:
        content = _read_log(log_path)

        user_code = _extract_value(content, USER_CODE_PREFIX)
        verification_uri = _extract_value(content, VERIFICATION_URI_PREFIX)
        if user_code and verification_uri:
            return {
                "outcome": "authorization_started",
                "user_code": user_code,
                "verification_uri": verification_uri,
            }

        agent_session_id = _extract_value(content, AGENT_SESSION_ID_PREFIX)
        if agent_session_id:
            return {"outcome": "connected", "agent_session_id": agent_session_id}

        if time.monotonic() >= deadline:
            return {
                "outcome": "authorization_pending_timeout",
                "message": PENDING_TIMEOUT_MESSAGE,
            }

        time.sleep(LAUNCH_SIGNAL_POLL_INTERVAL_SECONDS)


def _resume_pending_authorization(log_home, status_result, environment):
    """`status` said `running: true` and `connected: false` (keel-runtime commit `bfc0ad6`,
    status contract guarantee 4): a `connect` this founder already started is alive and
    pid-checkable but has not completed device approval -- either still waiting on the code it
    already printed, or (no code ever printed) reusing a stored credential that has not finished
    reconnecting yet. Neither is a fresh event, and nothing here launches a second `connect` against
    a runtime that is already running (guarantee 5): the log the earlier launch already wrote
    (this script's own from a prior call, or the runtime's own if a human started it directly) is
    re-read for the same two signals `await_launch_signal` looks for fresh off a launch.

    A founder who says "keel connect" again while approval is still pending must see the code
    again, not `already_connected` -- `already_connected` is reserved for `connected: true`. The
    contract (`specs/001-keel-connect-check/contracts/skill-script-output.md`) closes over exactly
    seven shapes and says a key is never added to one without the contract changing first, so this
    adds none: no `resumed` field marks a repeat, the reply is the identical `authorization_started`
    or `authorization_pending_timeout` shape a fresh launch would have produced. `pid` is `status`'s
    own answer -- the process this call did not launch -- not a launch this call never made.
    """
    log_path = os.path.join(log_home, LAUNCH_LOG_FILENAME)
    content = _read_log(log_path)
    pid = status_result.get("pid")

    user_code = _extract_value(content, USER_CODE_PREFIX)
    verification_uri = _extract_value(content, VERIFICATION_URI_PREFIX)
    if user_code and verification_uri:
        return _emit({
            "outcome": "authorization_started",
            "user_code": user_code,
            "verification_uri": verification_uri,
            "pid": pid,
            "log_file": log_path,
            "environment": environment,
        }, 0)

    # No code in the log: a stored-credential reconnect in progress (or a launch too new to have
    # written anything yet), not a device approval waiting on this founder.
    return _emit({
        "outcome": "authorization_pending_timeout",
        "message": PENDING_TIMEOUT_MESSAGE,
        "pid": pid,
        "log_file": log_path,
        "environment": environment,
    }, 0)


# ------------------------------------------------------------------------------------------ output


def _emit(payload, exit_code):
    """The one place every one of the seven shapes is printed (X-1): exactly one line of JSON on
    stdout, always, and exit 0 for every outcome except `internal_error`."""
    sys.stdout.write(json.dumps(payload) + "\n")
    return exit_code


def _runtime_unavailable():
    """No checkout, no bundled runtime, no `keel` on PATH.

    The message names neither `--runtime-path` nor `KEEL_RUNTIME_PATH` (X-4: they are development
    overrides) and no longer names `pip install keel-runtime`: nothing is installed any more, so a
    skill with no `keel_runtime/` beside it is a skill that was copied wrong, not a founder who
    skipped a step. `environment` is null because no runtime answered (guarantee 4).
    """
    return _emit({
        "outcome": "runtime_unavailable",
        "message": (
            "this skill did not find the Keel runtime that is supposed to travel inside it "
            "(a keel_runtime/ package beside the skill's own scripts/ directory), and no keel "
            "command was found either. The skill directory looks incomplete -- reinstall it, or "
            "copy it again in full."
        ),
        "environment": None,
    }, 0)


def _internal_error(message, environment=None):
    return _emit({"outcome": "internal_error", "message": message,
                  "environment": environment}, 1)


# ------------------------------------------------------------------------- upgrade in place (005)


def _upgrade_in_place(location, log_home, given_home, args, running_version, environment):
    """Stops the older running runtime through the runtime's own `disconnect` (the goodbye, the
    process, the proof it is gone -- keel-runtime spec 003, as `keel_disconnect.py` already
    drives it), then launches this bundle's `connect`, which reconnects on the saved credential.
    One outcome, `upgraded`, carrying what the relaunch then said (`then`) and its keys."""
    import keel_disconnect  # a sibling in scripts/; imported here so a status-only run never loads it
    data, reason = keel_disconnect.run_disconnect(location, given_home)
    if data is None:
        return _internal_error("could not stop the older runtime before replacing it: %s" % reason,
                               environment)
    if data.get("outcome") not in ("stopped", "not_running", "stale_pid_cleared"):
        return _internal_error("the older runtime did not stop (its disconnect answered %r), so it "
                               "was not replaced" % data.get("outcome"), environment)
    try:
        pid, log_path = launch_connect(location, log_home, args, executor_for(args))
    except OSError as exc:
        return _internal_error("stopped the older runtime but failed to launch the new one: %s"
                               % exc, environment)
    then = await_launch_signal(log_path, args.wait_seconds)
    outcome = {"outcome": "upgraded", "then": then.pop("outcome"),
               "previous_version": running_version, "bundle_version": bundle_version()}
    outcome.update(then)
    outcome["pid"] = pid
    outcome["log_file"] = log_path
    outcome["environment"] = environment
    return _emit(outcome, 0)


# -------------------------------------------------------------------------------------------- main


def main(argv=None):
    args = build_parser().parse_args(argv)

    location = _runtime_location.resolve_runtime(runtime_path=args.runtime_path)
    if location is None:
        return _runtime_unavailable()

    given_home = resolve_given_home(args)
    status_result = run_status(location, given_home)
    if status_result is None:
        # Raised before `status` returned, so no runtime named a Keel: `environment` is null.
        return _internal_error(
            "the Keel runtime's 'status' did not return a well-formed answer (see keel-cloud "
            "specs/021-keel-runtime-status/contracts/status-cli-output.md) -- it may have "
            "crashed, printed something other than one JSON line, or omitted the required "
            "'running' key."
        )

    # Which Keel this is, straight from the runtime. The skill carries no base URL and no
    # environment table of its own, and says nothing rather than guessing (invariant X-5).
    environment = status_result.get("environment")
    # The home the runtime *reported*, which is where its log lives. The `~/.keel` fallback covers
    # only a runtime older than spec `004-shipped-runtime`, which does not report one.
    log_home = given_home or status_result.get("home") or os.path.join(
        os.path.expanduser("~"), ".keel")

    if status_result.get("running") is True:
        if status_result.get("connected") is True:
            running_version = status_result.get("launcher_version")
            # Upgrade in place (keel-cloud `canon/designs/upgrade-in-place-design.md`; the
            # founder, 2026-09-11): a running runtime is replaced by this bundle's only when the
            # bundle is strictly newer AND the runtime is idle. Same or newer running: nothing
            # happens, as before. Busy: the founder is told to ask again in a minute; a job is
            # never cancelled behind their back.
            if bundle_is_newer_than(running_version):
                if status_result.get("busy") is True:
                    return _emit({
                        "outcome": "upgrade_waiting",
                        "running_version": running_version,
                        "bundle_version": bundle_version(),
                        "agent_session_id": status_result.get("agent_session_id"),
                        "environment": environment,
                    }, 0)
                return _upgrade_in_place(location, log_home, given_home, args, running_version,
                                         environment)
            # `base_url` is gone from this shape and `environment` replaces it: one key for
            # *which Keel*, never two (design §7). `launcher_version` names who launched the
            # running runtime, `null` when it could not say (spec 005).
            return _emit({
                "outcome": "already_connected",
                "agent_session_id": status_result.get("agent_session_id"),
                "last_heartbeat_at": status_result.get("last_heartbeat_at"),
                "launcher_version": running_version,
                "environment": environment,
            }, 0)
        # Running, but not yet connected: a `connect` is alive and pid-checkable but still
        # waiting on device approval (or reconnecting a stored credential). Not a fresh event,
        # so nothing is launched a second time -- the founder is told the same thing a first
        # "keel connect" would have said (status contract guarantee 4).
        return _resume_pending_authorization(log_home, status_result, environment)

    try:
        pid, log_path = launch_connect(location, log_home, args, executor_for(args))
    except OSError as exc:
        return _internal_error("failed to launch 'keel connect': %s" % exc, environment)

    outcome = await_launch_signal(log_path, args.wait_seconds)
    outcome["pid"] = pid
    outcome["log_file"] = log_path
    outcome["environment"] = environment
    return _emit(outcome, 0)


if __name__ == "__main__":
    sys.exit(main())
