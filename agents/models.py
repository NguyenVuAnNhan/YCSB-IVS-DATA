from __future__ import annotations

import json
from typing import Any


HYPOTHESIS_REQUIRED_FIELDS = [
    "hypothesis_name",
    "mechanism",
    "confidence",
    "supporting_evidence",
    "counter_evidence",
    "missing_evidence",
    "next_test",
    "expected_observation_if_true",
    "expected_observation_if_false",
]


def ensure_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def validate_hypothesis(raw: Any, index: int) -> tuple[dict[str, Any] | None, list[str]]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return None, [f"hypotheses[{index}] is not an object"]

    missing = [field for field in HYPOTHESIS_REQUIRED_FIELDS if field not in raw]
    if missing:
        errors.append(f"hypotheses[{index}] missing fields: {', '.join(missing)}")

    normalized: dict[str, Any] = {}
    for field in HYPOTHESIS_REQUIRED_FIELDS:
        if field in {"supporting_evidence", "counter_evidence", "missing_evidence"}:
            normalized[field] = ensure_list(raw.get(field))
        elif field == "confidence":
            try:
                confidence = float(raw.get(field))
            except (TypeError, ValueError):
                confidence = -1.0
                errors.append(f"hypotheses[{index}].confidence is not numeric")
            if not 0.0 <= confidence <= 1.0:
                errors.append(f"hypotheses[{index}].confidence is outside [0.0, 1.0]")
            normalized[field] = min(1.0, max(0.0, confidence))
        else:
            value = raw.get(field)
            if value is None or value == "":
                errors.append(f"hypotheses[{index}].{field} is empty")
                value = ""
            normalized[field] = str(value)

    return normalized, errors


def validate_agent_output(raw_output: str, expected_role: str, expected_round: int) -> dict[str, Any]:
    """Parse and validate an agent JSON payload without discarding bad output."""
    parsed: Any
    errors: list[str] = []
    try:
        parsed = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        return {
            "role": expected_role,
            "round": expected_round,
            "valid": False,
            "errors": [f"JSON parse error: {exc}"],
            "raw_output": raw_output,
            "payload": None,
        }

    if not isinstance(parsed, dict):
        errors.append("top-level output is not an object")
        parsed = {"raw": parsed}

    role = str(parsed.get("role", expected_role))
    if role != expected_role:
        errors.append(f"role mismatch: expected {expected_role}, got {role}")

    try:
        round_index = int(parsed.get("round", expected_round))
    except (TypeError, ValueError):
        round_index = expected_round
        errors.append("round is not an integer")
    if round_index != expected_round:
        errors.append(f"round mismatch: expected {expected_round}, got {round_index}")

    raw_hypotheses = parsed.get("hypotheses", [])
    if not isinstance(raw_hypotheses, list):
        errors.append("hypotheses is not a list")
        raw_hypotheses = []

    hypotheses: list[dict[str, Any]] = []
    for index, raw_hypothesis in enumerate(raw_hypotheses):
        normalized, hypothesis_errors = validate_hypothesis(raw_hypothesis, index)
        errors.extend(hypothesis_errors)
        if normalized is not None:
            hypotheses.append(normalized)

    payload = dict(parsed)
    payload["role"] = role
    payload["round"] = round_index
    payload["hypotheses"] = hypotheses
    payload["notes"] = ensure_list(parsed.get("notes"))
    payload["recommended_tests"] = ensure_list(parsed.get("recommended_tests"))
    taxonomy = parsed.get("taxonomy", [])
    payload["taxonomy"] = taxonomy if isinstance(taxonomy, list) else [str(taxonomy)]

    if not hypotheses:
        errors.append("no schema-valid hypotheses were produced")

    return {
        "role": expected_role,
        "round": expected_round,
        "valid": not errors,
        "errors": errors,
        "raw_output": raw_output,
        "payload": payload,
    }
