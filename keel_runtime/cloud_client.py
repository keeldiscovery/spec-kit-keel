"""HTTP client for Keel Cloud's `/v2` connect surface (spec FR-005..018; plan §Key
mechanics 8).

Standard library only: `urllib.request`. Every non-2xx response is parsed into an
`ApiError(status, code, message)` when the body carries the dictated envelope
(`{"error": {"code": ..., "message": ...}}`), else `ApiError(status, "HTTP_<status>",
<raw text>)`. A `401` status is always raised as `AuthenticationExpired`, regardless of
body shape (spec edge case: "the runtime treats any 401 as credential no longer
accepted regardless of body"). A request that never reaches Cloud at all (DNS,
connection refused, timeout) raises `NetworkError`.

A `410` carrying `{"error": {"code": "AGENT_SESSION_SUPERSEDED", ...}}` is raised as
`AgentSessionSuperseded` (keel-cloud spec `035-one-runtime-per-founder`: a second runtime
connected to this founder account and took over, ending this one's agent session) -- deliberately
*not* folded into `AuthenticationExpired`, because the two demand opposite responses: a 401 means
"re-authenticate", a 410-superseded means "this runtime is done; re-authenticating would only
fight the new runtime for the account". A `410` carrying any other code -- or no parseable code at
all -- is still an `ApiError`, exactly as any other non-2xx, non-401 status.
"""
from __future__ import annotations

import json
import socket
import urllib.error
import urllib.request
from typing import Optional

DEFAULT_TIMEOUT_SECONDS = 10.0

# The long-poll window the client asks for by default, and the extra margin it waits
# beyond that window before treating the connection as dead (plan §Key mechanics 8).
# Named (rather than inline literals) so other modules -- e.g. config.py's
# `heartbeat_stale_after` default, spec 021 research.md §4 -- can derive from the same
# numbers instead of duplicating them.
DEFAULT_POLL_WINDOW_SECONDS = 25.0
POLL_TIMEOUT_MARGIN_SECONDS = 10.0


class ApiError(Exception):
    """A parsed, non-2xx, non-401 response from Cloud."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{status} {code}: {message}")
        self.status = status
        self.code = code
        self.message = message


class AuthenticationExpired(Exception):
    """Raised for any 401 response -- the stored credential is no longer accepted."""


class AgentSessionSuperseded(Exception):
    """Raised for a 410 whose body's error code is `AGENT_SESSION_SUPERSEDED` (keel-cloud spec
    `035-one-runtime-per-founder`): another runtime connected to this founder account and took
    this one's agent session over. Unlike `AuthenticationExpired`, catching this must never
    re-authorize -- the new runtime already holds the account, and racing it for the credential
    is exactly the failure this exception exists to let callers avoid. A 410 carrying any other
    code stays an `ApiError`, as it always has.

    Carries the server's own `message` -- the one meant for a founder to read (e.g. "another
    runtime connected to this account and took over ... run keel connect here again to take it
    back") -- verbatim, so a caller can print it rather than invent its own wording.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NetworkError(Exception):
    """Raised when the request could not reach Cloud at all."""


class CloudClient:
    """Thin JSON HTTP client for the keel-connect wire surface (spec FR-005..018)."""

    def __init__(self, base_url: str, poll_window_seconds: float = DEFAULT_POLL_WINDOW_SECONDS):
        self.base_url = base_url.rstrip("/")
        self.poll_window_seconds = poll_window_seconds

    # -- device authorization (open) -------------------------------------------------

    def create_device_authorization(self) -> dict:
        return self._request("POST", "/v2/device-authorizations", body={})

    def get_agent_token(self, device_code: str) -> dict:
        return self._request(
            "POST",
            "/v2/device-authorizations/token",
            body={"device_code": device_code},
        )

    # -- agent session / jobs (bearer) -------------------------------------------------

    def create_agent_session(self, access_token: str) -> dict:
        return self._request(
            "POST", "/v2/agent-sessions", body={}, access_token=access_token
        )

    def poll(self, agent_session_id: str, access_token: str) -> dict:
        # The long-poll's window is server-configured; the client waits a little longer
        # than the server is allowed to hold the request (plan §Key mechanics 8).
        return self._request(
            "POST",
            f"/v2/agent-sessions/{agent_session_id}/poll",
            body={},
            access_token=access_token,
            timeout=self.poll_window_seconds + POLL_TIMEOUT_MARGIN_SECONDS,
        )

    def complete_job(self, job_id: str, access_token: str, response: dict,
                     execution: dict = None) -> dict:
        # spec 009: `execution` -- `{host, host_version, model_requested, model_used,
        # retried_unpinned}` -- is optional and additive (design §6); omitted when the executor
        # has no host to report, so a scripted run's body is byte-identical to before.
        body = {"response": response}
        if execution is not None:
            body["execution"] = execution
        return self._request(
            "POST",
            f"/v2/inference-jobs/{job_id}/complete",
            body=body,
            access_token=access_token,
        )

    def fail_job(self, job_id: str, access_token: str, code: str, message: str,
                 execution: dict = None) -> dict:
        body = {"error_code": code, "error_message": message}
        if execution is not None:
            body["execution"] = execution
        return self._request(
            "POST",
            f"/v2/inference-jobs/{job_id}/fail",
            body=body,
            access_token=access_token,
        )

    def end_agent_session(
        self,
        agent_session_id: str,
        access_token: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        """The goodbye (keel-cloud spec `033-agent-session-goodbye`; `003-keel-disconnect`
        design §4.2, §4.3): `POST /v2/agent-sessions/{id}/disconnect`, body `{}`, expecting
        `204 No Content` -- the runtime's own last act on a clean shutdown, called once with
        this session's own bearer and a short, caller-supplied timeout.

        This is `create_agent_session`'s counterpart, not a variant of `poll`/`complete_job`/
        `fail_job`: it carries no response to interpret, only a refusal to raise if one comes
        back. A `404 AGENT_SESSION_NOT_FOUND` (an older Keel Cloud, or a session this bearer
        does not own) and a `403 INSUFFICIENT_SCOPE` both surface as the same `ApiError` every
        other call raises; a network error, a connection refused, or the timeout expiring
        surfaces as `NetworkError`. **This method swallows nothing itself** -- `cli._say_goodbye`
        is the one seam that does (G1), and it is the one that supplies the bound.
        """
        self._request(
            "POST",
            f"/v2/agent-sessions/{agent_session_id}/disconnect",
            body={},
            access_token=access_token,
            timeout=timeout,
        )

    # -- transport ---------------------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        body: Optional[dict] = None,
        access_token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> dict:
        url = f"{self.base_url}{path}"
        data = json.dumps(body if body is not None else {}).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            status = exc.code
            if status == 401:
                raise AuthenticationExpired(
                    f"401 from {method} {path}"
                ) from exc
            code, message = self._parse_error_body(raw, status)
            if status == 410 and code == "AGENT_SESSION_SUPERSEDED":
                raise AgentSessionSuperseded(message) from exc
            raise ApiError(status, code, message) from exc
        except urllib.error.URLError as exc:
            raise NetworkError(str(exc.reason)) from exc
        except (socket.timeout, TimeoutError) as exc:
            # A timeout reading the response (rather than connecting) reaches here unwrapped --
            # `http.client.HTTPConnection.getresponse()` raises it directly, not through
            # `URLError`. On Python 3.9 `socket.timeout` is its own class, not `TimeoutError`
            # (they are the same class from 3.10 on); listing both keeps this one clause correct
            # on every supported interpreter, which is what makes a hung server's `NetworkError`
            # -- not a bare, unswallowed `socket.timeout` -- a promise `end_agent_session` can
            # make on 3.9 too.
            raise NetworkError(str(exc)) from exc

    @staticmethod
    def _parse_error_body(raw: bytes, status: int) -> tuple:
        try:
            parsed = json.loads(raw) if raw else {}
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            error = parsed.get("error")
            if isinstance(error, dict) and "code" in error:
                return error.get("code", f"HTTP_{status}"), error.get("message", "")
        text = raw.decode("utf-8", errors="replace") if raw else ""
        return f"HTTP_{status}", text
