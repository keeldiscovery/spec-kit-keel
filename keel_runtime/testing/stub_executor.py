"""StubExecutor -- deterministic, test-only Executor (spec FR-028).

Selected with `--executor stub`, never a default. Driven entirely by
`request_payload["input"]["content"]`; this is the executor `KeelConnectJourneyTest`
(spec SC-002) drives directly, so its behavior must match the spec exactly:

- ``"ask"``     -> ``{outcome: NEEDS_INPUT, questions: [{id: "q1", ...}]}``
- ``"crash"``   -> raises ``ExecutorUnavailable``
- ``"garbage"`` -> ``{outcome: COMPLETED, result: {unexpected: true}}`` (deliberately
  invalid, so the runtime's own response_validator refuses it and the runtime fails the
  job with ``INVALID_LLM_RESPONSE``)
- anything else -> ``{outcome: COMPLETED, result: {echo: <content>, turn_number: <job's
  turn_number>}}``
"""
from __future__ import annotations

from ..executor import Executor, ExecutorUnavailable, InferenceRequest


class StubExecutor(Executor):
    def execute(self, request: InferenceRequest) -> dict:
        content = request.request_payload["input"]["content"]

        if content == "ask":
            return {
                "outcome": "NEEDS_INPUT",
                "questions": [
                    {
                        "id": "q1",
                        "question": "What would you like echoed?",
                        "input_type": "text",
                        "required": True,
                    }
                ],
            }

        if content == "crash":
            raise ExecutorUnavailable("stub executor simulating LLM unavailability")

        if content == "garbage":
            return {"outcome": "COMPLETED", "result": {"unexpected": True}}

        return {
            "outcome": "COMPLETED",
            "result": {"echo": content, "turn_number": request.turn_number},
        }
