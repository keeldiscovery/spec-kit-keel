"""Command-line entry point: `python3 -m keel_runtime connect` / installed `keel connect`.

`main()` is also the `[project.scripts]` target (`keel = "keel_runtime.cli:main"`), but
this module never assumes it has been installed -- `keel_runtime/__main__.py` calls the
same `main()` so the package runs uninstalled from this directory, which is how the
E2E test launches it (spec FR-024, SC-002).
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys

from . import COPYRIGHT, LICENSE_URL, __license__, __version__
from . import agent_session as agent_session_module
from . import auth as auth_module
from . import config as config_module
from . import disconnect as disconnect_module
from . import heartbeat as heartbeat_module
from .cloud_client import AgentSessionSuperseded, AuthenticationExpired, CloudClient
from .credential_store import CredentialStore
from .executor import get_executor
from .poller import run_loop


# Which CLI a named executor needs on `PATH` now lives in `config` beside the selection order
# that chooses between them (spec `005-copilot-executor`), because `status` and `connect` must
# agree about both. `claude_on_path` is never built, because it reads `false` on a healthy
# runtime that is not using Claude, which is a lie about health (C-10).


def version_line() -> str:
    """One line, and the whole of `--version` (FR-005). It names `CLOUD_BASE_URL`, set since
    design §13 step 8 to keel-cloud's real address.
    """
    line = f"keel-runtime {__version__}"
    if config_module.CLOUD_BASE_URL:
        line += f" (Keel Cloud {config_module.CLOUD_BASE_URL})"
    return line


def license_text() -> str:
    return (
        f"keel-runtime {__version__}\n"
        f"{COPYRIGHT}\n"
        f"Licensed under the Apache License, Version 2.0 (SPDX: {__license__}); "
        f"the full text ships as this repository's own LICENSE file and is also at "
        f"{LICENSE_URL}\n"
        "This runtime bundles no third-party code: it runs on the Python standard library alone. "
        "`keyring` and `jsonschema` are optional accelerators, used only if you install them "
        "yourself."
    )


class _PrintAndExit(argparse.Action):
    """A `--version`-style flag: print one thing, exit 0, ask for no subcommand.

    argparse runs an optional's action as it consumes the argument, so this fires before the
    `required=True` subparser check at the end of `parse_args` -- which is what lets
    `python3 -m keel_runtime --version` work with no command at all (§10.3 assertion 3).
    """

    def __init__(self, option_strings, dest, text=None, **kwargs):
        super().__init__(option_strings, dest, nargs=0, default=argparse.SUPPRESS, **kwargs)
        self._text = text

    def __call__(self, parser, namespace, values, option_string=None):
        print(self._text() if callable(self._text) else self._text)
        parser.exit(0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="keel", description="Keel local runtime")
    parser.add_argument(
        "--version",
        action=_PrintAndExit,
        text=version_line,
        help="print this runtime's version and exit",
    )
    parser.add_argument(
        "--license",
        action=_PrintAndExit,
        text=license_text,
        help="print this runtime's licence notice and exit",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    connect = subparsers.add_parser(
        "connect", help="authorize this device against Keel Cloud and run the local runtime"
    )
    connect.add_argument("--base-url", dest="base_url", help="Keel Cloud base URL")
    connect.add_argument(
        "--executor",
        dest="executor",
        choices=["claude", "claude-code", "copilot", "codex", "scripted", "stub"],
        help="executor to run jobs with: claude (default; claude-code is a permanent alias), "
        "copilot, codex, or stub/scripted (test-only). Named explicitly it wins outright -- even if "
        "its CLI is missing, which is reported per job rather than second-guessed here.",
    )
    # design §5.3: **the skill passes the host through.** `keel_connect_check.py` runs the
    # host-detection table itself and passes `--host <host>` to the `connect` it launches --
    # only when the founder did not pass `--executor` themselves, and nothing at all when the
    # table is silent or ambiguous. It is a host signal, never an instruction from the founder,
    # so it sits at step 2 of the selection order and below every explicit term.
    connect.add_argument(
        "--host",
        dest="host",
        choices=["claude", "copilot", "codex", "auto"],
        default="auto",
        help="the host this runtime was launched under, when the caller knows (the skill does); "
        "'auto' reads the environment's own host markers instead",
    )
    # spec 009-model-routing: no `--<host>-model` flag. The model a job runs on comes with the
    # job, from the cloud's routing table, and from nowhere else (design §6).
    connect.add_argument(
        "--script",
        dest="script",
        help="path to a scripted-executor script (only meaningful with --executor scripted; "
        "falls back to KEEL_SCRIPT, then to the bundled countly-problem script)",
    )
    connect.add_argument(
        "--context-keys",
        dest="context_keys",
        help="path to keel-cloud's exported context-keys.json, the scripted executor's "
        "screen-inference table (only meaningful with --executor scripted; falls back to "
        "KEEL_CONTEXT_KEYS, then to the bundled copy)",
    )
    connect.add_argument("--home", dest="home", help="overrides KEEL_HOME for this run")
    connect.add_argument(
        "--launcher-version",
        dest="launcher_version",
        help="the version of the skill (or other launcher) starting this runtime, recorded in "
             "the heartbeat and reported by `status` as launcher_version (spec 007); "
             "KEEL_LAUNCHER_VERSION is the environment form",
    )
    connect.add_argument(
        "--credential-backend",
        dest="credential_backend",
        choices=["auto", "file", "keyring"],
        help="where to store the issued credential",
    )
    connect.add_argument(
        "--no-browser",
        dest="no_browser",
        action="store_true",
        help="do not open a browser for device authorization; print the URL instead",
    )
    connect.add_argument(
        "--log-level",
        dest="log_level",
        default="INFO",
        help="log verbosity (informational only in this pass)",
    )

    status = subparsers.add_parser(
        "status",
        help="report whether a keel-runtime process is currently connected (spec 021)",
    )
    status.add_argument("--home", dest="home", help="overrides KEEL_HOME for this run")

    disconnect = subparsers.add_parser(
        "disconnect",
        help="stop the keel-runtime process running on this home (spec 003-keel-disconnect)",
    )
    disconnect.add_argument("--home", dest="home", help="overrides KEEL_HOME for this run")
    # Since spec `004-shipped-runtime` the home **follows the address**, so naming the Keel is a
    # way of naming the home: a caller that knows which Keel it means should not have to compute a
    # host slug to say which directory it means. It is never used to reach the network (D9).
    disconnect.add_argument(
        "--base-url",
        dest="base_url",
        help="the Keel whose derived home to act on, when no --home/KEEL_HOME is set",
    )

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "connect":
        return _run_connect(args)
    if args.command == "status":
        return _run_status(args)
    if args.command == "disconnect":
        return _run_disconnect(args)

    parser.print_help()  # pragma: no cover -- argparse's `required=True` makes this dead
    return 1


# One call, a one-second timeout: a version string is worth a line in the log and worth
# nothing at all if it delays a connect.
_VERSION_PROBE_TIMEOUT_SECONDS = 1.0


def _binary_version(binary_path: str):
    """`<binary> --version`'s first line, or `None` if it cannot be had. Best-effort by
    design: the founder gets a version when one is cheap and the line without one when it is
    not, and a connect is never held up for a decoration.
    """
    try:
        completed = subprocess.run(
            [binary_path, "--version"],
            capture_output=True,
            text=True,
            timeout=_VERSION_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    output = (completed.stdout or completed.stderr or "").strip()
    return output.splitlines()[0].strip() if output else None


def probe_host_cli(config):
    """`(binary, binary_path, version)` for the executor's CLI: the name `EXECUTOR_BINARIES`
    gives, where `PATH` has it (or `None`), and its `--version` line (or `None`). One probe per
    connect, shared by the startup line and by the executor's `host_version` (spec 009)."""
    binary = config_module.EXECUTOR_BINARIES.get(config.executor)
    binary_path = shutil.which(binary) if binary else None
    version = _binary_version(binary_path) if binary_path else None
    return binary, binary_path, version


def executor_startup_lines(config, probe=None) -> list:
    """design §5.3 / C-9: the `KEEL_EXECUTOR=` line, and the `KEEL_EXECUTOR_UNAVAILABLE=` line
    beneath it when the CLI that executor needs is not on `PATH`.

    ```
    KEEL_EXECUTOR=copilot source=host binary=/opt/homebrew/bin/copilot version=1.0.83
    KEEL_EXECUTOR=claude source=ambiguous-path  # both CLIs on PATH; pass --executor to choose
    KEEL_EXECUTOR_UNAVAILABLE=copilot           # not on PATH; jobs report EXECUTOR_UNAVAILABLE
    ```

    `source` says **why**, not only what. The runtime still connects when the CLI is missing:
    the founder's device is authorized either way, and each job reports `EXECUTOR_UNAVAILABLE`
    on its own -- which is a far better failure than refusing to connect at all.

    No `model=` word since spec 009: there is no session-wide model any more. The model is per
    job, named by the cloud, and recorded per job in `$KEEL_HOME/jobs/<id>/execution.json`.
    """
    name = config.executor
    source = config.executor_source
    parts = [f"KEEL_EXECUTOR={name}", f"source={source}"]

    binary, binary_path, version = probe if probe is not None else probe_host_cli(config)
    if binary_path:
        parts.append(f"binary={binary_path}")
        if version:
            parts.append(f"version={version}")

    line = " ".join(parts)
    if source == "ambiguous-path":
        line += "  # more than one host CLI on PATH; pass --executor to choose"

    lines = [line]
    if binary is not None and binary_path is None:
        lines.append(
            f"KEEL_EXECUTOR_UNAVAILABLE={name}"
            "  # not on PATH; jobs report EXECUTOR_UNAVAILABLE"
        )
    return lines


def _run_connect(args) -> int:
    config = config_module.load(args)
    config.home.mkdir(parents=True, exist_ok=True)
    # The first line of the log the skill is already reading, in the same machine-readable family
    # as `KEEL_USER_CODE=` (spec 004-shipped-runtime FR-010, design §6.3): which Keel this is, and
    # its address. The skill carries no address of its own (X-5) and reports what it is handed.
    print(
        f"KEEL_ENVIRONMENT={config.environment} base_url={config.base_url}",
        flush=True,
    )
    # C-9: **the runtime says which, always** -- one line at startup, into the log the skill is
    # already reading, in the same machine-readable family as `KEEL_USER_CODE=`.
    probe = probe_host_cli(config)
    for line in executor_startup_lines(config, probe):
        print(line, flush=True)
    _install_heartbeat_shutdown_handlers(config)
    # keel-cloud DRIFT #51 / canon/designs/keel-disconnect-design.md §6(g): a launch record,
    # naming this pid, written before the device code is even requested -- so a runtime that is
    # alive and waiting for approval is not invisible to `status` and `disconnect`. Overwritten
    # with the real heartbeat the moment an agent session exists, by `create_agent_session`
    # (stored-credential path) or by `auth.authorize_device`'s own per-tick refresh followed by
    # `create_agent_session` (fresh device authorization).
    heartbeat_module.write_awaiting_approval(config.home, os.getpid(), config.base_url,
                                             launcher_version=config.launcher_version)

    if config.script_path and config.executor != "scripted":
        print(
            f"keel connect: --script is ignored because --executor is '{config.executor}', "
            "not 'scripted'",
            file=sys.stderr,
        )

    if config.context_keys_path and config.executor != "scripted":
        print(
            f"keel connect: --context-keys is ignored because --executor is "
            f"'{config.executor}', not 'scripted'",
            file=sys.stderr,
        )

    executor = get_executor(
        config.executor,
        config.script_path,
        home=config.home,
        context_keys_path=config.context_keys_path,
        budget_usd=config.job_budget_usd,
        max_turns=config.job_max_turns,
        timeout_seconds=config.job_timeout_seconds,
    )
    if getattr(executor, "host_key", None):
        # spec 009: the CLI's own `--version` line, reported on every completion as
        # `execution.host_version` -- the same probe the startup line printed.
        executor.host_version = probe[2]
    store = CredentialStore(config.home, backend=config.credential_backend)
    client = CloudClient(base_url=config.base_url)

    # A SIGTERM/Ctrl-C anywhere from here through the end of `run_loop` -- most of all while
    # blocked in device authorization, waiting on a founder who never clicks approve -- used to
    # propagate out of this function uncaught whenever it landed before `state` existed: a
    # traceback, not a clean exit (the pre-existing quirk the goodbye pass noted). One try now
    # covers the stored-credential reconnect, a fresh device authorization, and the poll loop
    # alike, so all three are a clean exit the same way. The shutdown handler has already removed
    # the launch record by the time we get here; `state` staying `None` is exactly what
    # `_say_goodbye`'s G6 already treats as nothing to end.
    state = None
    try:
        credential = store.load()
        if credential is not None:
            try:
                state = agent_session_module.create_agent_session(client, credential, config)
            except AuthenticationExpired:
                # A stored credential the server no longer accepts is exactly "none or
                # refused" (spec FR-026) -- fall through to a fresh device authorization.
                store.clear()
                credential = None

        if state is None:
            credential = auth_module.authorize_device(client, config)
            store.save(credential)
            state = agent_session_module.create_agent_session(client, credential, config)

        print(f"keel-runtime connected: agent_session_id={state.agent_session_id}")
        print("Polling for work. Press Ctrl+C to stop.")

        # FR-011: `run_loop` rebinds `state` when a credential expires mid-run (`_reauthorize`),
        # so the state to say goodbye with is the one it *finished* with, not the one it started
        # with. It returns None only if it never entered the loop.
        final_state = run_loop(client, state, executor, store, config)
        if final_state is not None:
            state = final_state
    except AgentSessionSuperseded as exc:
        # keel-cloud spec 035-one-runtime-per-founder: a newer runtime already took this
        # account's agent session over. Report it, remove the heartbeat ourselves (there is no
        # signal here to make the shutdown handler do it), leave the credential exactly as it
        # is, and return without even trying the goodbye -- the session it would address is
        # already gone, and a 404 for it would just be swallowed anyway.
        _report_superseded(exc, config)
        return 0
    except KeyboardInterrupt:
        pass

    try:
        _say_goodbye(client, state, config)
    except KeyboardInterrupt:
        # A second Ctrl+C/SIGTERM while the goodbye is in flight is still a clean exit (G1).
        pass
    return 0


def _report_superseded(exc: AgentSessionSuperseded, config) -> None:
    """keel-cloud spec `035-one-runtime-per-founder` (`003-keel-disconnect`'s amendment): a
    runtime-authenticated route answered `410 AGENT_SESSION_SUPERSEDED` -- another runtime
    connected to this founder account and took this one's agent session over.

    One line, in the same machine-readable `KEEL_*` signal-line family as `KEEL_USER_CODE=` and
    `KEEL_ENVIRONMENT=`, naming the server's own founder-facing message verbatim. The heartbeat is
    removed directly, exactly as the SIGINT/SIGTERM handler would (`_install_heartbeat_shutdown_
    handlers`) -- there is no signal here to make it do that for us, and a founder running `keel
    status` right after must read `not_running`, not a stale record of a session that is already
    dead. The credential is left untouched: it is what lets `keel connect` here issue a fresh
    agent session and take the account back.
    """
    print(f"KEEL_SUPERSEDED=1 message={exc.message}", flush=True)
    heartbeat_module.remove(config.home)


# One call, a two-second timeout, no retry, no backoff -- the opposite of the poll loop, which
# retries forever because it has forever (G2).
GOODBYE_TIMEOUT_SECONDS = 2.0


def _say_goodbye(client, state, config) -> bool:
    """The runtime's last act (FR-010; design §4.2, invariants G1-G3, G6). Returns whether a
    goodbye was attempted.

    **The call**, since `CloudClient.end_agent_session` (keel-cloud spec
    `033-agent-session-goodbye`): `POST /v2/agent-sessions/{id}/disconnect`, this session's own
    bearer, a body of `{}`, expecting `204`. The `getattr` lookup below is kept rather than called
    directly so a client without the method -- a stub in a test, or an older `CloudClient` --
    still makes this a clean no-op instead of an `AttributeError`.

    **Where it is, and where it must not be.** Not in the signal handler: that runs on the main
    thread's own stack, wherever that thread happens to be -- nine times in ten inside the
    long-poll's `urlopen` -- and opening a second socket from inside the first one's stack frame,
    in a handler that may be re-entered by a second SIGTERM, is the kind of code that works until
    the day it does not. The handler keeps doing exactly what spec 021 FR-003 gave it, and the
    goodbye goes here, after the stack has unwound. That placement also gets the ordering right
    for free (G3): the heartbeat is already gone, so a founder who runs `keel status` half a second
    later reads "not running" whether or not the network cooperated. **Local truth first, always.**

    **Best-effort.** Every exception is swallowed: a refused call, a 404 from an older Keel Cloud,
    a laptop already off the wifi, the call itself timing out. None of them delays the exit,
    changes the exit code, or changes `keel disconnect`'s outcome (G1). The goodbye is an
    accelerator, never a requirement (G5) -- when it does not arrive, keel-cloud's existing
    staleness rule turns the founder's screen off exactly as it does today. Success or failure,
    the attempt is one line in the log a founder can read afterwards; it is never why `connect`
    exits non-zero, because it is never why `connect` exits at all.
    """
    if state is None or not getattr(state, "agent_session_id", None):
        return False  # G6 -- a run interrupted during device authorization has nothing to end.

    end_agent_session = getattr(client, "end_agent_session", None)
    if end_agent_session is None:
        return False  # this client carries no goodbye -- a stub in a test, or an older client.

    try:
        end_agent_session(
            state.agent_session_id,
            state.access_token,
            timeout=GOODBYE_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # noqa: BLE001 -- G1: everything, without exception, is swallowed.
        print(
            f"keel-runtime: goodbye to agent_session_id={state.agent_session_id} failed "
            f"({exc.__class__.__name__}: {exc}) -- disconnecting anyway",
            flush=True,
        )
    else:
        print(
            f"keel-runtime: said goodbye to agent_session_id={state.agent_session_id}",
            flush=True,
        )
    return True


def _install_heartbeat_shutdown_handlers(config) -> None:
    """spec 021 FR-003 / research.md §6: on SIGINT (Ctrl+C) or SIGTERM, remove the
    heartbeat file before the existing shutdown path (spec 020 FR-026) runs its course,
    so `status` sees "not running" immediately rather than waiting out the staleness
    window. Re-raising as `KeyboardInterrupt` keeps `run_loop`'s and `_run_connect`'s
    existing `except KeyboardInterrupt` handling -- and therefore `connect`'s existing
    exit behavior/messages -- unchanged for both signals.
    """

    def _handle_shutdown_signal(signum, frame):  # noqa: ARG001 -- signal handler signature
        heartbeat_module.remove(config.home)
        raise KeyboardInterrupt()

    signal.signal(signal.SIGINT, _handle_shutdown_signal)
    signal.signal(signal.SIGTERM, _handle_shutdown_signal)


def _run_status(args) -> int:
    """spec 021 FR-004/FR-005: no network call, always exits 0, exactly one line of
    JSON on stdout (contracts/status-cli-output.md).

    **`connected: false`** (keel-cloud DRIFT #51): the running shape's `connected` key was
    reserved for exactly this by the contract's own guarantee 4 -- "a future revision ... could
    distinguish 'running but not yet connected' from 'running and connected' without breaking
    existing callers who only check `running`". A runtime that wrote a launch record
    (`heartbeat.write_awaiting_approval`) and is still waiting on device approval is alive and
    pid-checkable, so `running` is `true`; it has no agent session yet, so `agent_session_id` is
    `null` and `connected` is `false`, never `true`. No key is added to the shape -- `pid`,
    `agent_session_id`, `base_url`, `last_heartbeat_at` and `connected` are the same five keys
    the running shape always carried -- only `agent_session_id`'s value may now be `null` and
    `connected`'s may now be `false`. Both are value-set changes the status contract
    (`keel-cloud specs/021-keel-runtime-status/contracts/status-cli-output.md`) still needs to
    describe; see this fix's own writeup for the exact amendment.
    """
    status_config = config_module.load_status_config(args)
    hb = heartbeat_module.read(status_config.home)

    if hb is None:
        result = {"running": False}
    elif not heartbeat_module.pid_alive(hb.pid):
        # A dead pid is definitive, regardless of the heartbeat's age (Acceptance
        # Scenario 5).
        result = {"running": False, "stale_pid": hb.pid}
    elif heartbeat_module.is_stale(hb, status_config.heartbeat_stale_after):
        result = {"running": False, "stale_pid": hb.pid}
    else:
        result = {
            "running": True,
            "pid": hb.pid,
            "agent_session_id": hb.agent_session_id,
            "base_url": hb.base_url,
            "last_heartbeat_at": hb.last_heartbeat_at,
            "connected": hb.state != heartbeat_module.STATE_AWAITING_APPROVAL,
            # spec `007-launcher-version`: who launched it (null for a runtime that was not
            # told), and whether it is working on a job right now -- the two facts a newer
            # skill needs before it may replace this process.
            "launcher_version": hb.launcher_version,
            "busy": hb.job_id is not None,
        }

    result.update(_environment_keys(status_config, hb))
    print(json.dumps(result))
    return 0


def _run_disconnect(args) -> int:
    """spec `003-keel-disconnect` FR-001/FR-005/FR-008: one line of JSON on stdout, exit 0 always,
    no network call (contracts/disconnect-cli-output.md).

    The wiring is four lines because the flow is `disconnect.py`'s: read the heartbeat once for
    the address it records, run the flow, and say what happened and which Keel it happened to.
    """
    status_config = config_module.load_status_config(args)
    # Read before the flow runs, because a `stopped` run removes the file the address comes from.
    hb = heartbeat_module.read(status_config.home)

    result = disconnect_module.disconnect(status_config.home)
    result.update(_address_keys(status_config, hb))
    print(json.dumps(result))
    return 0


def _address_keys(status_config, heartbeat_record) -> dict:
    """`home`, `base_url`, `environment` -- *which home, and which Keel* (spec 004 FR-009, spec 003
    FR-008). One helper, so exactly one place decides the address for both `status` and
    `disconnect`.

    When a heartbeat was readable the address is the *heartbeat's*: it describes the Keel the live
    (or just-stopped) process actually connected to, which is not necessarily the one a fresh
    resolution would pick now.
    """
    base_url = status_config.base_url
    if heartbeat_record is not None and getattr(heartbeat_record, "base_url", None):
        base_url = heartbeat_record.base_url

    return {
        "home": str(status_config.home),
        "base_url": base_url,
        "environment": config_module.environment_for(base_url),
    }


def _environment_keys(status_config, heartbeat_record) -> dict:
    """`home`, `base_url`, `environment`, `executor`, `executor_on_path` -- the four keys spec
    004-shipped-runtime FR-009 adds and the promotion of `base_url` to always-present. Every one
    of them is in **both** shapes (design C-10), which is why this is one helper and not two
    branches.

    In the running shape the address is the *heartbeat's*: it describes the Keel the live process
    actually connected to, which is not necessarily the one a fresh resolution would pick now.
    That part is `_address_keys`, shared with `disconnect`; the two executor keys are `status`'s
    alone, since no executor takes part in a disconnect.
    """
    keys = _address_keys(status_config, heartbeat_record)

    # Both keys reflect the executor the **selection order** resolved (C-10), which since spec
    # `005-copilot-executor` may be `copilot` -- on a Copilot-hosted machine `executor_on_path`
    # is then about `copilot`, and reads `true` on a healthy runtime with no `claude` anywhere.
    keys["executor"] = status_config.executor
    keys["executor_on_path"] = config_module.executor_on_path(status_config.executor)
    return keys


if __name__ == "__main__":  # pragma: no cover -- exercised via __main__.py instead
    sys.exit(main())
