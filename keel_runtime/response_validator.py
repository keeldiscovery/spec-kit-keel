"""Validates a job's response against its `response_contract` (mirrors spec FR-019).

`outcome` must be one of `response_contract.allowed_outcomes`; `NEEDS_INPUT` requires a
non-empty `questions[]` each shaped `{id, question, input_type, required}`; `COMPLETED`
requires a `result` conforming to `completed_result_schema`. Schema conformance uses
`jsonschema.validate` when that package is importable, else `_subset_validate`, which
implements exactly the server's own subset (spec FR-019, extended by spec
002-words-are-words FR-006): `type`, `required`, `properties`, `enum`, `items`,
`additionalProperties: false`, `maxLength`, `minLength`, `maxItems`, `pattern`
(`re.search`, matching keel-cloud's own `ResultSchemaValidator` so the runtime's local
check agrees with Cloud's); every other keyword is ignored.
"""
from __future__ import annotations

import re
from typing import Any

try:
    import jsonschema  # type: ignore

    _JSONSCHEMA_AVAILABLE = True
except ImportError:  # pragma: no cover -- exercised only where jsonschema is installed
    jsonschema = None  # type: ignore
    _JSONSCHEMA_AVAILABLE = False


class InvalidResponse(Exception):
    """Raised when a response does not conform to its response_contract."""


_REQUIRED_QUESTION_FIELDS = ("id", "question", "input_type", "required")


def validate_response(response: dict, response_contract: dict) -> None:
    if not isinstance(response, dict):
        raise InvalidResponse("response must be an object")

    outcome = response.get("outcome")
    allowed_outcomes = response_contract.get("allowed_outcomes") or []
    if outcome not in allowed_outcomes:
        raise InvalidResponse(
            f"outcome '{outcome}' is not in allowed_outcomes {allowed_outcomes}"
        )

    if outcome == "NEEDS_INPUT":
        _validate_questions(response.get("questions"))
    elif outcome == "COMPLETED":
        if "result" not in response:
            raise InvalidResponse("COMPLETED requires a 'result'")
        schema = response_contract.get("completed_result_schema")
        if schema is not None:
            _validate_against_schema(response["result"], schema)


def _validate_questions(questions: Any) -> None:
    if not isinstance(questions, list) or not questions:
        raise InvalidResponse("NEEDS_INPUT requires a non-empty questions[] array")
    for index, question in enumerate(questions):
        if not isinstance(question, dict):
            raise InvalidResponse(f"questions[{index}] must be an object")
        for field_name in _REQUIRED_QUESTION_FIELDS:
            if field_name not in question:
                raise InvalidResponse(f"questions[{index}] missing '{field_name}'")


def _validate_against_schema(value: Any, schema: dict) -> None:
    if _JSONSCHEMA_AVAILABLE:
        try:
            jsonschema.validate(value, schema)  # type: ignore[union-attr]
        except jsonschema.exceptions.ValidationError as exc:  # type: ignore[union-attr]
            path = ".".join(str(part) for part in exc.absolute_path) or "result"
            raise InvalidResponse(f"{path}: {exc.message}") from exc
        return
    _subset_validate(value, schema, "result")


def _subset_validate(value: Any, schema: dict, path: str) -> None:
    """The stdlib fallback: exactly the server's ResultSchemaValidator subset (spec
    FR-019, extended by spec 002-words-are-words FR-006).
    """
    expected_type = schema.get("type")
    if expected_type is not None and not _matches_type(value, expected_type):
        raise InvalidResponse(f"{path}: expected type '{expected_type}'")

    if "enum" in schema and value not in schema["enum"]:
        raise InvalidResponse(f"{path}: value not in enum {schema['enum']}")

    if isinstance(value, str):
        max_length = schema.get("maxLength")
        if max_length is not None and len(value) > max_length:
            raise InvalidResponse(f"{path}: longer than maxLength {max_length}")
        min_length = schema.get("minLength")
        if min_length is not None and len(value) < min_length:
            raise InvalidResponse(f"{path}: shorter than minLength {min_length}")
        pattern = schema.get("pattern")
        if pattern is not None and not re.search(pattern, value):
            raise InvalidResponse(f"{path}: does not match pattern {pattern!r}")

    if isinstance(value, dict) and expected_type in (None, "object"):
        for required_field in schema.get("required") or []:
            if required_field not in value:
                raise InvalidResponse(f"{path}.{required_field}: required field missing")
        properties = schema.get("properties") or {}
        for key, subschema in properties.items():
            if key in value:
                _subset_validate(value[key], subschema, f"{path}.{key}")
        if schema.get("additionalProperties") is False:
            allowed_keys = set(properties.keys())
            for key in value.keys():
                if key not in allowed_keys:
                    raise InvalidResponse(f"{path}.{key}: additional property not allowed")

    if isinstance(value, list) and expected_type in (None, "array"):
        max_items = schema.get("maxItems")
        if max_items is not None and len(value) > max_items:
            raise InvalidResponse(f"{path}: more items than maxItems {max_items}")
        items_schema = schema.get("items")
        if items_schema is not None:
            for index, item in enumerate(value):
                _subset_validate(item, items_schema, f"{path}[{index}]")


def _matches_type(value: Any, expected_type: str) -> bool:
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "null":
        return value is None
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "object":
        return isinstance(value, dict)
    if expected_type == "array":
        return isinstance(value, list)
    return True  # unknown type keyword value -- the subset posture ignores it
