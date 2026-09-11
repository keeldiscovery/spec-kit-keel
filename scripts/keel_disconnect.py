#!/usr/bin/env python3
"""Stops the local keel-runtime on this home, and proves it is gone.

The second of this skill's two scripts (`../SKILL.md`), and the door out that
`keel_connect_check.py` is the door in for. It never talks to Keel Cloud, never touches a
credential, and -- guarantee 3 of its contract -- **cannot start a `keel connect` under any
outcome**. All it does is locate the runtime the way its sibling does, run that runtime's own
`disconnect`, and translate the four outcomes of keel-runtime's
`specs/003-keel-disconnect/contracts/disconnect-cli-output.md` into the six a founder's agent is
told about.

A second script rather than a `--disconnect` mode of the first one (keel-cloud
`canon/designs/keel-disconnect-design.md` §5.1): the connect contract is titled for one script,
two other repositories read it, and every flag it has left exists to launch something. The one
thing the two scripts share is where the runtime is, and that is
`scripts/_runtime_location.py` -- imported and used **whole**, since there is no branch this
script must skip (keel-skill-design.md §11).

Standard library only, and no syntax newer than the 3.9 floor (design §4.1), matching its
sibling: a host invokes this as a plain subprocess with whatever `python3` it has.

Stable output contract: `../specs/002-keel-disconnect/contracts/skill-disconnect-output.md`, six
outcomes. Every shape documented there is produced from exactly one place in this file (`_emit`),
so the contract and the implementation cannot drift apart silently.
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _runtime_location  # noqa: E402 -- must follow the path insert above

# The command is bounded at 15 seconds by its own contract -- SIGTERM, ten seconds of grace,
# SIGKILL, five more -- so anything past that is a runtime that is not honouring the contract at
# all, which is `internal_error` rather than something to keep waiting for.
DISCONNECT_SUBPROCESS_TIMEOUT_SECONDS = 45.0

# The runtime's four outcome names, and the founder-facing name each becomes (design §5.2).
# `not_running` and `stale_pid_cleared` mean the same thing at both levels and keep their names;
# `stopped` becomes `disconnected` and `timeout` becomes `did_not_stop` because the skill layer
# speaks the founder's vocabulary, not the process's -- and because "timeout" at this level is
# ambiguous between the runtime's grace bound and this script's own subprocess timeout.
OUTCOME_NAMES = {
    "stopped": "disconnected",
    "not_running": "not_running",
    "stale_pid_cleared": "stale_pid_cleared",
    "timeout": "did_not_stop",
}

DID_NOT_STOP_MESSAGE = (
    "the keel-runtime process did not exit after SIGTERM and SIGKILL; it is stuck in a call the "
    "operating system will not interrupt."
)


# -------------------------------------------------------------------------------- argument parsing


def build_parser():
    parser = argparse.ArgumentParser(
        prog="keel_disconnect",
        description=(
            "Stop the local keel-runtime on this home. See specs/002-keel-disconnect/contracts/"
            "skill-disconnect-output.md for this script's stable JSON output contract."
        ),
    )
    parser.add_argument(
        "--runtime-path",
        dest="runtime_path",
        default=None,
        help=argparse.SUPPRESS,  # X-4: a development override; no founder-facing text names it
    )
    parser.add_argument(
        "--home",
        dest="home",
        default=None,
        help="overrides KEEL_HOME for this run. When neither is given, the runtime resolves its "
        "own home from the Keel it resolves -- the same home its own `status` and `connect` "
        "resolve, so this script does not guess one.",
    )
    return parser


def resolve_given_home(args, environ=None):
    """The home this script was *given*, or `None` -- resolved exactly as `keel_connect_check.py`
    resolves it (that script's `resolve_given_home`, design §6.3).

    `None` means "let the runtime decide". The disconnect design's §5.2 wrote this rule as
    "flag > `KEEL_HOME` > `~/.keel`, resolved by this script"; since spec `004-shipped-runtime`
    the runtime derives `~/.keel/<host-slug>/` from the Keel it resolved, so a script that passed
    a guessed `~/.keel` would act on a *different* home from the one its sibling connected. The
    two scripts must resolve one home from one set of inputs or the door out does not open on the
    door in -- so this one, like that one, passes `--home` only when it was given one.
    """
    env = os.environ if environ is None else environ
    if args.home:
        return os.path.expanduser(args.home)
    env_home = env.get("KEEL_HOME")
    if env_home:
        return os.path.expanduser(env_home)
    return None


# --------------------------------------------------------------------------- running the disconnect


def run_disconnect(location, home):
    """Invokes `<runtime> disconnect [--home <home>]` and parses its documented contract
    (keel-runtime `specs/003-keel-disconnect/contracts/disconnect-cli-output.md`).

    Returns `(data, None)` when the runtime honoured that contract, and `(None, reason)` when it
    did not -- a crash, a non-zero exit, output that is not exactly one JSON line, or JSON short
    the required `outcome` key. The caller reports `internal_error` with that reason; no exception
    ever escapes this function.
    """
    argv = ["disconnect"]
    if home:
        argv += ["--home", str(home)]
    try:
        completed = _runtime_location.run_capturing(
            location, argv, timeout=DISCONNECT_SUBPROCESS_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return None, ("the Keel runtime's 'disconnect' did not return within %d seconds, well "
                      "past the 15 seconds its own contract bounds it to."
                      % DISCONNECT_SUBPROCESS_TIMEOUT_SECONDS)
    except OSError as exc:
        return None, "the Keel runtime's 'disconnect' could not be run: %s" % exc

    if completed.returncode != 0:
        # The likeliest cause in practice, and the one worth naming: a keel-runtime old enough to
        # have no `disconnect` subcommand at all, in which case argparse exits 2 with a usage line
        # on stderr. "Update your keel-runtime" is a remedy; "something went wrong" is not.
        return None, ("the Keel runtime's 'disconnect' exited %d. If it reports an invalid or "
                      "unrecognized command, this keel-runtime predates the disconnect command "
                      "and needs updating. It said: %s"
                      % (completed.returncode, _first_line(completed.stderr or completed.stdout)))

    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        return None, ("the Keel runtime's 'disconnect' printed %d lines of output where its "
                      "contract promises exactly one line of JSON." % len(lines))

    try:
        data = json.loads(lines[0])
    except ValueError:
        return None, ("the Keel runtime's 'disconnect' printed something that is not JSON where "
                      "its contract promises one JSON line: %s" % _first_line(lines[0]))

    if not isinstance(data, dict) or "outcome" not in data:
        return None, ("the Keel runtime's 'disconnect' answered without the required 'outcome' "
                      "key its contract promises.")

    if data["outcome"] not in OUTCOME_NAMES:
        return None, ("the Keel runtime's 'disconnect' reported an outcome this skill does not "
                      "know: %s. It may be newer than this skill." % _first_line(str(data["outcome"])))

    return data, None


def _first_line(text, limit=200):
    """One short line of someone else's output, safe to put inside a JSON message."""
    if not text:
        return "(nothing)"
    line = text.strip().splitlines()[0].strip()
    if len(line) > limit:
        line = line[:limit] + "..."
    return line


# ------------------------------------------------------------------------------------------ output


def _emit(payload, exit_code):
    """The one place every one of the six shapes is printed: exactly one line of JSON on stdout,
    always, and exit 0 for every outcome except `internal_error` -- the same rule the connect
    script follows (invariant X-1)."""
    sys.stdout.write(json.dumps(payload) + "\n")
    return exit_code


def _runtime_unavailable():
    """No checkout, no bundled runtime, no `keel` on `PATH`. Same shape, same message discipline
    and the same meaning as the connect script's: the message names neither `--runtime-path` nor
    `KEEL_RUNTIME_PATH` (X-4), and does not offer an install, because nothing is installed --
    a skill with no `keel_runtime/` beside it was copied wrong. `environment` is null because no
    runtime answered."""
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


def translate(data):
    """The runtime's four outcomes into four of this script's six, and nothing else.

    Only the keys the contract names for each shape are carried across: `home` and `base_url`,
    which the runtime's own contract puts on all four of its shapes, are deliberately dropped --
    `environment` is the one key for *which Keel* (design §7), and guarantee 2 forbids a key
    outside a documented shape.
    """
    runtime_outcome = data["outcome"]
    payload = {"outcome": OUTCOME_NAMES[runtime_outcome]}

    if runtime_outcome in ("stopped", "stale_pid_cleared", "timeout"):
        payload["pid"] = data.get("pid")
    if runtime_outcome in ("stopped", "timeout"):
        payload["waited_ms"] = data.get("waited_ms")
    if runtime_outcome == "stopped":
        payload["signal"] = data.get("signal")
    if runtime_outcome == "timeout":
        payload["message"] = DID_NOT_STOP_MESSAGE

    payload["environment"] = data.get("environment")
    return payload


# -------------------------------------------------------------------------------------------- main


def main(argv=None):
    args = build_parser().parse_args(argv)

    location = _runtime_location.resolve_runtime(runtime_path=args.runtime_path)
    if location is None:
        return _runtime_unavailable()

    data, failure = run_disconnect(location, resolve_given_home(args))
    if data is None:
        # Nothing came back that honours the contract, so no runtime named a Keel: `environment`
        # is null (X-5 -- say nothing rather than guess one).
        return _internal_error(failure)

    return _emit(translate(data), 0)


if __name__ == "__main__":
    sys.exit(main())
