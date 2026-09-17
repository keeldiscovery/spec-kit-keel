"""The runtime's main loop (design §10.12): long-poll, execute, validate, complete/fail.

On ``NO_WORK`` it re-polls immediately -- the long-poll itself is the liveness signal,
so there is no additional short-interval polling (spec FR-027). Executor exceptions map
to `/fail` error codes; a ``422 INVALID_RESULT`` from `/complete` is treated the same as
the executor's own ``InvalidResponse``. A ``401`` anywhere discards the stored
credential and re-authorizes from scratch. A network error retries with capped
exponential backoff. ``KeyboardInterrupt`` exits cleanly.

A ``410 AGENT_SESSION_SUPERSEDED`` anywhere (keel-cloud spec `035-one-runtime-per-founder`) is the
opposite of a `401`: it means another runtime already holds this founder account, so
re-authorizing here would only fight it for the credential. `run_loop` does not catch
`AgentSessionSuperseded` -- it is let through deliberately, past this module's own
`except AuthenticationExpired`/`except NetworkError`, straight out to `cli._run_connect`, which is
where it is reported, the heartbeat is removed, the goodbye is skipped (the session is already
ended -- calling it would just 404), and `connect` exits 0.

spec 002-words-are-words FR-005: every job's `envelope.json` (the CLI's own envelope,
verbatim) and `request.json` (the prompt sections that were sent, for the referee's
canary check) are written to `$KEEL_HOME/jobs/<job_id>/` -- read off the executor's
`last_envelope`/`last_request_sections` attributes when present, so this stays a no-op
for the scripted and stub executors, which have neither. A `/fail` message is always
`<code>: <=200 chars of diagnostic text>`, never model output (the executor's own
exception messages are the CLI's stderr or the envelope's own error text, not
`structured_output`). Job directories under `$KEEL_HOME/jobs/` are pruned to the newest
50 once, at the start of `run_loop`.

spec 009-model-routing (keel-cloud `canon/designs/model-routing-design.md` §5/§6): the job's
`request_payload["model"]` is a per-host map; `_model_for` reads the entry for the executor's own
`host_key` and hands it to the executor on the request -- the one rule, no other source. After
the job, `_execution_report` reads the executor's five report attributes into the `execution`
object `/complete` and `/fail` carry (and `execution.json` beside the other job logs), so the
cloud learns which host answered, on which model, and whether the named one was refused. A
executor without a `host_key` (scripted, stub) carries no report and the bodies are unchanged.
"""
from __future__ import annotations

import json
import os
import shutil
import time

from . import agent_session as agent_session_module
from . import auth as auth_module
from . import heartbeat as heartbeat_module
from .cloud_client import (
    AgentSessionSuperseded,
    ApiError,
    AuthenticationExpired,
    CloudClient,
    NetworkError,
)
from .executor import (
    Executor,
    ExecutorAuthFailure,
    ExecutorTimeout,
    ExecutorUnavailable,
    InferenceRequest,
)
from .response_validator import InvalidResponse, validate_response

INITIAL_BACKOFF_SECONDS = 1.0
MAX_BACKOFF_SECONDS = 30.0

# spec FR-005 Edge Cases: the per-job directory holds the envelope log the referee
# reads -- kept, not deleted on completion -- but pruned to the newest 50 so it never
# grows without bound over a long-running `connect`.
JOB_DIR_RETENTION = 50

# spec FR-005: the `/fail` message is "<code>: <=200 chars of stderr>".
_FAIL_MESSAGE_DETAIL_LIMIT = 200


def run_loop(client: CloudClient, state, executor: Executor, store, config):
    """Returns the `RuntimeState` it finished with (spec `003-keel-disconnect` FR-011).

    `_reauthorize` rebinds `state` when a credential expires mid-run, so the caller's own local
    variable can name an agent session that is already dead -- which is the session the goodbye
    would otherwise be addressed to. One `return` is the whole fix.
    """
    _prune_job_dirs(config.home)
    backoff = INITIAL_BACKOFF_SECONDS
    try:
        while True:
            try:
                answer = client.poll(state.agent_session_id, state.access_token)
                backoff = INITIAL_BACKOFF_SECONDS
                if answer.get("type") == "NO_WORK":
                    _write_heartbeat(state, config)
                    continue
                # spec `007-launcher-version`: the heartbeat names the job for as long as it is
                # being worked, so a newer skill's "keel connect" waits rather than replacing a
                # runtime mid-job; the write after the job clears it again.
                _write_heartbeat(state, config, job_id=answer["job"]["job_id"])
                _handle_job(client, state, executor, answer["job"], config)
                _write_heartbeat(state, config)
            except AgentSessionSuperseded:
                # Deliberately not handled here -- re-authorizing (what `AuthenticationExpired`
                # does, just below) is exactly wrong for this one: a newer runtime already holds
                # the account, and reconnecting here would fight it for the credential. Left to
                # propagate out of `run_loop` whole, straight to `cli._run_connect`.
                raise
            except AuthenticationExpired:
                state = _reauthorize(client, store, config)
                continue
            except NetworkError:
                time.sleep(backoff)
                backoff = min(backoff * 2, MAX_BACKOFF_SECONDS)
                continue
    except KeyboardInterrupt:
        return state


def _prune_job_dirs(home, keep: int = JOB_DIR_RETENTION) -> None:
    jobs_dir = home / "jobs"
    if not jobs_dir.is_dir():
        return
    entries = [entry for entry in jobs_dir.iterdir() if entry.is_dir()]
    entries.sort(key=lambda entry: entry.stat().st_mtime, reverse=True)
    for stale in entries[keep:]:
        shutil.rmtree(stale, ignore_errors=True)


def _write_heartbeat(state, config, job_id=None) -> None:
    # spec 021 FR-001: written after every poll cycle -- NO_WORK and a delivered job
    # alike -- so a runtime that is merely idle still reads as alive, not only one that
    # just completed a job. `job_id` names the job in hand (spec 007), `None` when idle.
    heartbeat_module.write(
        config.home,
        heartbeat_module.Heartbeat(
            pid=os.getpid(),
            agent_session_id=state.agent_session_id,
            base_url=config.base_url,
            last_heartbeat_at=heartbeat_module.now_iso8601(),
            launcher_version=getattr(config, "launcher_version", None),
            job_id=job_id,
        ),
    )


def _model_for(executor: Executor, request_payload: dict):
    """`request_payload["model"][<host_key>]` when it is a non-empty string; otherwise `None`.
    A payload without the key (an older cloud), a map without this host's entry (an unmeasured
    host, an absent tier), or anything that is not a string all mean the same thing: no flag."""
    host = getattr(executor, "host_key", None)
    if not host:
        return None
    models = request_payload.get("model") if isinstance(request_payload, dict) else None
    if not isinstance(models, dict):
        return None
    model = models.get(host)
    if isinstance(model, str) and model.strip():
        return model.strip()
    return None


def _execution_report(executor: Executor):
    """The `execution` object for `/complete` and `/fail`; `None` for an executor with no host."""
    host = getattr(executor, "host_key", None)
    if not host:
        return None
    return {
        "host": host,
        "host_version": getattr(executor, "host_version", None),
        "model_requested": getattr(executor, "last_model_requested", None),
        "model_used": getattr(executor, "last_model_used", None),
        "retried_unpinned": bool(getattr(executor, "last_retried_unpinned", False)),
    }


def _write_job_logs(config, executor: Executor, job_id: str) -> None:
    # spec FR-005, extended by FR-010 (amendment): written for whichever executor
    # exposes them -- ClaudeCodeExecutor does, the scripted and stub executors don't,
    # and this is a no-op for those (they are untouched by this spec). `events.jsonl`
    # holds the raw `stream-json` events (both passes' when FR-011's recovery pass ran)
    # for the referee, beside `envelope.json`'s final `result` event.
    envelope = getattr(executor, "last_envelope", None)
    sections = getattr(executor, "last_request_sections", None)
    events = getattr(executor, "last_events", None)
    if envelope is None and sections is None and events is None:
        return
    job_dir = config.home / "jobs" / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    if envelope is not None:
        (job_dir / "envelope.json").write_text(json.dumps(envelope, indent=2))
    if sections is not None:
        (job_dir / "request.json").write_text(json.dumps(sections, indent=2, default=str))
    if events is not None:
        lines = [json.dumps(event) for event in events]
        content = "\n".join(lines)
        if lines:
            content += "\n"
        (job_dir / "events.jsonl").write_text(content)
    execution = _execution_report(executor)
    if execution is not None:
        (job_dir / "execution.json").write_text(json.dumps(execution, indent=2))


def _handle_job(client: CloudClient, state, executor: Executor, job: dict, config) -> None:
    request = InferenceRequest(
        job_id=job["job_id"],
        interaction_id=job["interaction_id"],
        turn_number=job["turn_number"],
        request_payload=job["request_payload"],
        model=_model_for(executor, job["request_payload"]),
    )

    try:
        response = executor.execute(request)
        validate_response(response, job["request_payload"]["response_contract"])
    except ExecutorUnavailable as exc:
        _write_job_logs(config, executor, job["job_id"])
        _fail(client, state, job["job_id"], "LLM_UNAVAILABLE", str(exc), executor)
        return
    except ExecutorAuthFailure as exc:
        _write_job_logs(config, executor, job["job_id"])
        _fail(client, state, job["job_id"], "EXECUTOR_AUTH_FAILED", str(exc), executor)
        return
    except ExecutorTimeout as exc:
        _write_job_logs(config, executor, job["job_id"])
        _fail(client, state, job["job_id"], "EXECUTOR_TIMEOUT", str(exc), executor)
        return
    except InvalidResponse as exc:
        _write_job_logs(config, executor, job["job_id"])
        _fail(client, state, job["job_id"], "INVALID_LLM_RESPONSE", str(exc), executor)
        return
    except Exception as exc:  # noqa: BLE001 -- anything else maps to INTERNAL_ERROR (FR-027)
        _write_job_logs(config, executor, job["job_id"])
        _fail(client, state, job["job_id"], "INTERNAL_ERROR", str(exc), executor)
        return

    _write_job_logs(config, executor, job["job_id"])

    try:
        execution = _execution_report(executor)
        if execution is None:
            client.complete_job(job["job_id"], state.access_token, response)
        else:
            client.complete_job(job["job_id"], state.access_token, response, execution=execution)
    except ApiError as exc:
        if exc.status == 422:
            # A 422 INVALID_RESULT from /complete is treated as InvalidResponse (FR-027):
            # the runtime's own validator agreed, but the server's disagreed (or the
            # runtime has no jsonschema/subset gap) -- fail it honestly rather than retry.
            _fail(client, state, job["job_id"], "INVALID_LLM_RESPONSE", exc.message, executor)
        else:
            raise


def _fail(client: CloudClient, state, job_id: str, code: str, message: str,
          executor: Executor = None) -> None:
    # spec FR-005: "<code>: <=200 chars of stderr>" -- never model output. `message`
    # here is always the executor's own exception text (the CLI's stderr, the
    # envelope's own error string, or the validator's diagnostic), never
    # `structured_output`.
    detail = message[:_FAIL_MESSAGE_DETAIL_LIMIT]
    execution = _execution_report(executor) if executor is not None else None
    if execution is None:
        client.fail_job(job_id, state.access_token, code, f"{code}: {detail}")
    else:
        client.fail_job(job_id, state.access_token, code, f"{code}: {detail}", execution=execution)


def _reauthorize(client: CloudClient, store, config):
    store.clear()
    credential = auth_module.authorize_device(client, config)
    store.save(credential)
    return agent_session_module.create_agent_session(client, credential, config)
