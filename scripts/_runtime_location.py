"""Where the runtime is, and how to invoke it -- shared by every script in this skill.

keel-cloud `canon/designs/keel-skill-design.md` §3.2 is the whole of this file. Both
`keel_connect_check.py` and (spec `002-keel-disconnect`) `keel_disconnect.py` import it and use
it *whole*: there is one resolution order in this skill, and one place it is written down.

The order, and why:

1. **a checkout** -- `--runtime-path` / `KEEL_RUNTIME_PATH`. A developer, or keel-e2e-eval. It wins
   outright so that a founder debugging the runtime is not silently testing a release. It is a
   development override and no founder-facing message names it (invariant X-4).
2. **the runtime that travelled with this skill** -- `<skill root>/keel_runtime/`, put there by
   `make runtime`. This is the normal case and the one a founder is on.
3. **a `keel` already on `PATH`** -- someone pip-installed it, or packaged it.

**The bundled copy beats a `keel` on `PATH`**, reversing spec 001's order. `PATH` came first when
the alternative was asking a founder to install something; nothing is installed now, and the
bundled copy *is* the skill -- the version this skill's own tests ran against. A stranger's `keel`
must not shadow it silently.

**One mechanism for both Python branches** (§3.2): the directory is prepended to `PYTHONPATH` in
the child's environment. `sys.executable` -- the interpreter that ran the script, already
guaranteed >= 3.9 by the caller's version gate -- is what runs it.

**One documented deviation from §3.2, forced by the floor.** The design also says `cwd` is left
alone. It cannot be, on Python 3.9: `python3 -m <pkg>` *prepends the working directory* to
`sys.path`, ahead of `PYTHONPATH`, so a caller whose `cwd` happens to hold an unrelated
`keel_runtime/` would silently run that one instead of the one this file resolved -- which is the
whole failure the resolution order exists to prevent. `PYTHONSAFEPATH=1` fixes it exactly and is
set here, but it is 3.11+ and the floor is 3.9 (§4.1), so the module branch also runs with `cwd`
set to the directory it resolved. `PYTHONPATH` is still the mechanism that carries the location;
`cwd` is a shadow guard and nothing else. Measured on 2026-09-08: without it, `/usr/bin/python3`
3.9.6 run from a directory containing a `keel_runtime/` ignores `PYTHONPATH` entirely.

Standard library only, and no syntax newer than the floor: this module is imported by a script
that must stay runnable on Python 3.9 (design §4).
"""

import os
import shutil
import subprocess
import sys

# Where a resolution came from, reported so a founder and a referee can both see *why*, not only
# *what* -- the same vocabulary the runtime's own `KEEL_EXECUTOR=` line uses (design §5.3).
SOURCE_CHECKOUT = "checkout"
SOURCE_BUNDLED = "bundled"
SOURCE_PATH = "path"

ENV_RUNTIME_PATH = "KEEL_RUNTIME_PATH"


class RuntimeLocation(object):
    """A resolved runtime: the argv prefix that runs it, the directory (if any) that must be on
    the child's `PYTHONPATH`, and which of the three rules found it."""

    def __init__(self, argv_prefix, pythonpath=None, source=None):
        self.argv_prefix = list(argv_prefix)
        self.pythonpath = pythonpath
        self.source = source

    def child_env(self, base_env=None):
        """The environment a `status`/`connect` child is launched with: the caller's, plus this
        location's directory prepended to `PYTHONPATH` when it has one.

        Prepended, not replaced -- a caller who set `PYTHONPATH` for their own reasons keeps it,
        and the runtime we resolved still wins the import. `PYTHONSAFEPATH` goes with it: on 3.11+
        it removes the working directory from `sys.path` outright, which is the exact fix for the
        shadowing this module's docstring describes. It is ignored by older interpreters, which is
        why `child_cwd` exists as well.
        """
        env = dict(os.environ if base_env is None else base_env)
        if self.pythonpath is not None:
            existing = env.get("PYTHONPATH")
            entry = str(self.pythonpath)
            if existing:
                env["PYTHONPATH"] = entry + os.pathsep + existing
            else:
                env["PYTHONPATH"] = entry
            env["PYTHONSAFEPATH"] = "1"
        return env

    def child_cwd(self):
        """Where a child is rooted: the resolved directory for the module branch (the shadow
        guard), and the caller's own working directory -- `None` -- for a `keel` on `PATH`, which
        has no directory to be shadowed by."""
        return self.pythonpath

    def __repr__(self):  # pragma: no cover -- debugging aid only
        return "RuntimeLocation(argv_prefix=%r, pythonpath=%r, source=%r)" % (
            self.argv_prefix, self.pythonpath, self.source)


def skill_root():
    """This skill's own directory: the parent of the `scripts/` directory this file sits in.

    Every path in this skill is resolved relative to it rather than to a working directory, which
    is what makes the skill relocatable: a plugin cache, a personal skills directory and a
    repository's own committed one are several different absolute paths and one relative one
    (design §3.1).
    """
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _is_runtime_package_dir(directory):
    """A directory usable as a `PYTHONPATH` entry for `python3 -m keel_runtime`."""
    return os.path.isfile(os.path.join(directory, "keel_runtime", "__main__.py"))


def _module_location(directory, source):
    return RuntimeLocation(
        argv_prefix=[sys.executable, "-m", "keel_runtime"],
        pythonpath=os.path.abspath(directory),
        source=source,
    )


def resolve_runtime(runtime_path=None, environ=None, which=None):
    """Design §3.2, in order. Returns a `RuntimeLocation`, or `None` -- which the caller reports
    as `runtime_unavailable`, never as an exception.

    `environ` and `which` are injectable for the tests; production passes neither.
    """
    env = os.environ if environ is None else environ
    lookup = shutil.which if which is None else which

    # 1. a checkout -- a developer, or keel-e2e-eval (X-4: a development override).
    candidate = runtime_path or env.get(ENV_RUNTIME_PATH)
    if candidate:
        expanded = os.path.expanduser(candidate)
        if _is_runtime_package_dir(expanded):
            return _module_location(expanded, SOURCE_CHECKOUT)

    # 2. the runtime that travels with this skill -- the normal case (D2: put here by
    #    `make runtime`, never committed, never hand-edited).
    here = skill_root()
    if _is_runtime_package_dir(here):
        return _module_location(here, SOURCE_BUNDLED)

    # 3. a `keel` already on PATH -- someone installed or packaged it themselves.
    keel_on_path = lookup("keel", path=env.get("PATH"))
    if keel_on_path:
        return RuntimeLocation(argv_prefix=[keel_on_path], pythonpath=None, source=SOURCE_PATH)

    return None


def run_capturing(location, argv, timeout=None, environ=None):
    """`subprocess.run` for a resolved runtime: this location's argv prefix, environment and
    working directory (§3.2 and this module's one documented deviation from it)."""
    return subprocess.run(
        location.argv_prefix + list(argv),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=location.child_env(environ),
        cwd=location.child_cwd(),
    )
