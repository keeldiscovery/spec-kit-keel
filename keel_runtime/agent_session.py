"""Creates the runtime's agent session and prints its id for harnesses (spec FR-026)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from . import heartbeat as heartbeat_module
from .cloud_client import CloudClient
from .credential_store import Credential


@dataclass
class RuntimeState:
    agent_session_id: str
    access_token: str
    running: bool = True


def create_agent_session(client: CloudClient, credential: Credential, config) -> RuntimeState:
    created = client.create_agent_session(credential.access_token)
    agent_session_id = created["agent_session_id"]
    print(f"KEEL_AGENT_SESSION_ID={agent_session_id}", flush=True)
    # spec 021 research.md §5: write the first heartbeat as soon as the agent session
    # (and therefore its id) exists, before the poll loop's own per-cycle writes begin
    # -- otherwise a runtime that is connected but hasn't yet completed one poll cycle
    # would read back as "not running" (the false-negative window Acceptance Scenario 2
    # rules out).
    heartbeat_module.write(
        config.home,
        heartbeat_module.Heartbeat(
            pid=os.getpid(),
            agent_session_id=agent_session_id,
            base_url=config.base_url,
            last_heartbeat_at=heartbeat_module.now_iso8601(),
            launcher_version=getattr(config, "launcher_version", None),
        ),
    )
    return RuntimeState(agent_session_id=agent_session_id, access_token=credential.access_token)
