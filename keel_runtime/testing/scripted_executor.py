"""ScriptedExecutor -- deterministic, test-only Executor driven by a script file (spec
`001-scripted-executor` FR-001, as amended by its `AMENDMENT-measured-beliefs.md`).

Selected with `--executor scripted`, never a default. The script is a JSON object
`{screen: [entries...]}`; each screen's entries are consumed in order, one per call to
`execute`, repeating the last entry once exhausted -- per screen, per process (a
restarted runtime starts the script over).

The screen is never LLM-derived: it is inferred from the request payload's own `context`
keys, by **exact key-set match**, against a table that is **loaded, not written**.
keel-cloud's own `ScreenContextBuilder` writes every key for its screen, filling an absent
value with `null` rather than omitting it, so a key set is fixed and complete per screen --
which is what makes an exact match the right rule rather than a fragile one. The table comes
from keel-cloud's own export (`./gradlew -q screenContracts --args="export <dir>"`, its
`context-keys.json`), reached by `--context-keys` / `KEEL_CONTEXT_KEYS` /
`$KEEL_HOME/config.json`, with a bundled copy as the fallback.

That is the whole point of the amendment. The previous version transcribed keel-cloud spec
022 FR-010's prose table by hand, and every row of it was stale: `market` had joined every
framing, assumptions and reframe context, `founder_name` had joined the three assumption
contexts, `INTERPRET` carried `{invitation_id, anchors}` where it had carried
`{invitation_id, assumptions}`, `BRIEF` carried `{project_name, market, claims}` where it had
carried `deal_breakers`, and three `<SCREEN>.correction` key sets had appeared that the table
had never heard of. A hand-copied table is a claim about another repository that nothing
checks; a loaded one is that repository's own answer.

**Strictness is kept.** An unknown key set still raises `ExecutorUnavailable` naming the keys.
A loose executor would have answered the wrong screen silently, and this drift would never
have been found at all.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from ..executor import Executor, ExecutorUnavailable, InferenceRequest

#: The bundled copy of keel-cloud's `context-keys.json`, used when nothing else is given.
#: Regenerated from keel-cloud's own exporter -- never hand-edited.
DEFAULT_CONTEXT_KEYS_PATH = Path(__file__).parent / "contracts" / "context-keys.json"


def load_screen_table(path: str | Path | None = None) -> dict[frozenset, str]:
    """Reads keel-cloud's `context-keys.json` into `{frozenset(keys): screen}`.

    `path` is the operator's (`--context-keys`, `KEEL_CONTEXT_KEYS`, or the config file);
    `None` means the bundled copy. A file that names two screens with the same key set is a
    refusal rather than a coin toss -- exact-match inference is only honest while the sets
    are distinct, and keel-cloud's own builder is what keeps them so.
    """
    source = Path(path) if path else DEFAULT_CONTEXT_KEYS_PATH
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExecutorUnavailable(
            f"scripted executor cannot read its screen table from {source}: {exc}"
        ) from exc
    except ValueError as exc:
        raise ExecutorUnavailable(f"{source} is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or not raw:
        raise ExecutorUnavailable(
            f"{source} is not a context-keys export (expected a non-empty object of "
            "screen -> [key, ...])"
        )

    table: dict[frozenset, str] = {}
    for screen, keys in raw.items():
        if screen.startswith("_"):  # metadata, not a screen
            continue
        if not isinstance(keys, list) or not all(isinstance(k, str) for k in keys):
            raise ExecutorUnavailable(
                f"{source}: screen {screen} does not carry a list of key names"
            )
        key_set = frozenset(keys)
        clash = table.get(key_set)
        if clash is not None:
            raise ExecutorUnavailable(
                f"{source}: {screen} and {clash} have the same context key set "
                f"{sorted(key_set)} -- a screen cannot be inferred from keys two screens share"
            )
        table[key_set] = screen
    if not table:
        raise ExecutorUnavailable(f"{source} names no screens")
    return table


def infer_screen(context: dict, table: dict[frozenset, str] | None = None) -> str:
    """keel-cloud's current context-key table, by exact match and nothing looser.

    `table` defaults to the bundled export. Every key set keel-cloud writes is fixed and
    complete for its screen, so an exact match is the whole rule -- there is no longer any
    "this one key is present" fallback, and there does not need to be.
    """
    if table is None:
        table = load_screen_table()

    screen = table.get(frozenset(context.keys()))
    if screen is not None:
        return screen

    raise ExecutorUnavailable(
        f"scripted executor cannot infer a screen from context keys {sorted(context.keys())}"
    )


class ScriptedExecutor(Executor):
    def __init__(self, script: dict, context_keys_path: str | Path | None = None):
        if not isinstance(script, dict):
            raise ExecutorUnavailable("scripted executor script must be a JSON object")
        # `_source` (and any other underscore-prefixed key) is metadata, not a screen.
        self._script = {
            screen: entries for screen, entries in script.items() if not screen.startswith("_")
        }
        self._table = load_screen_table(context_keys_path)
        self._cursors: dict[str, int] = {}

    def execute(self, request: InferenceRequest) -> dict:
        context = request.request_payload.get("context", {})
        screen = infer_screen(context, self._table)

        entries = self._script.get(screen)
        if not entries:
            raise ExecutorUnavailable(f"scripted executor has no entry for {screen}")

        index = self._cursors.get(screen, 0)
        entry = entries[min(index, len(entries) - 1)]
        self._cursors[screen] = index + 1

        response = copy.deepcopy(entry)
        if screen == "INTERPRET" and response.get("outcome") == "COMPLETED":
            response["result"] = _resolve_interpret_result(response["result"], context)
        return response


def _resolve_interpret_result(result: dict, context: dict) -> dict:
    """Fills `invitationId` from the context (keel-cloud refuses otherwise) and checks every
    `anchorings[]` entry against the context's own `anchors[]`, by the `(stage, id)` pair.

    The heading-to-id resolution the old reading contract needed is gone with the shape that
    needed it: an `INTERPRET` context is `{invitation_id, anchors[]}` where an anchor is
    `{stage, anchor_id, prompt, text, tap}`, and an anchor id is already an id -- so the
    script's `anchorId` passes through **unchanged**. What is new is that an anchor id is
    unique only within its own stage (keel-cloud design decision 18 / rule Q7, DRIFT #37): a
    link can carry occasions from more than one approved stage, and every stage's
    questionnaire numbers its first anchor `A1`. So identity is the pair, not the bare id --
    the script names `{stage, anchorId}` and both travel onto the anchoring the executor
    returns, unchanged. What survives is the honesty the heading rule had: a `(stage, id)`
    pair the context does not carry is a refusal, never a value invented to keep a run green.
    A blank answer is never written into the context at all, so a script that answers one is
    answering something the reader was never shown, and that is exactly what this refuses.
    """
    result["invitationId"] = context.get("invitation_id")

    offered = {
        (anchor.get("stage"), anchor.get("anchor_id"))
        for anchor in context.get("anchors") or []
        if isinstance(anchor, dict)
    }
    for anchoring in result.get("anchorings", []):
        stage = anchoring.get("stage")
        anchor_id = anchoring.get("anchorId")
        if (stage, anchor_id) not in offered:
            raise ExecutorUnavailable(
                f"scripted executor was scripted to answer anchor '{anchor_id}' in stage "
                f"'{stage}', which this invitation's context does not carry (it offers "
                f"{sorted((s, a) for s, a in offered if a)})"
            )

    return result
