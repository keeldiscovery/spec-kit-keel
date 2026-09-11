"""keel-runtime: Keel Connect's local runtime (spec 020-keel-connect, FR-024..028)."""

# The single source of truth for the version, deliberately (spec 004-shipped-runtime FR-004).
# The shipped runtime travels inside the skill and is run from a directory on `PYTHONPATH`, never
# installed (design §3.2), so `importlib.metadata.version("keel-runtime")` would raise for exactly
# the founder this design exists for. `pyproject.toml`'s `version` mirrors this constant and a
# test asserts they agree.
__version__ = "0.2.0"

# The identifier the design's own packaging declares for the tree that carries this runtime
# (design §8.4's Spec Kit manifest), and the SPDX id of the `LICENSE` file at the repository
# root (spec 004-shipped-runtime, Assumptions -- once an open item, closed by adding the file).
__license__ = "Apache-2.0"

LICENSE_URL = "https://www.apache.org/licenses/LICENSE-2.0"
COPYRIGHT = "Copyright 2026 Keel Discovery"
