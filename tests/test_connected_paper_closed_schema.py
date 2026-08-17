from __future__ import annotations

import pytest

from scripts.validate_connected_paper_evidence import (
    EvidenceValidationError,
    validate_evidence,
)


def evidence() -> dict[str, object]:
    return {
        "schema_version": "connected-paper-qualification-evidence-v1",
        "environment": "PAPER",
        "live_trading": False,
        "credentials_embedded": False,
        "consequential_action_confirmed": True,
        "reference_best_ask": "100.50",
        "observed_at": "2026-08-17T00:00:00Z",
        "order": {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 1,
            "order_type": "LIMIT",
            "time_in_force": "DAY",
            "limit_price": "100.49",
        },
        "lifecycle": {
            "submitted": True,
            "acknowledged": True,
            "status_observed": True,
            "cancel_requested": True,
            "cancel_confirmed": True,
            "cleanup_verified": True,
        },
    }


def test_unexpected_top_level_field_is_rejected() -> None:
    payload = evidence()
    payload["notes"] = "operator-reviewed"

    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(payload)

    assert error_info.value.reason_code == "UNEXPECTED_FIELD_REJECTED"


def test_unexpected_order_field_is_rejected() -> None:
    payload = evidence()
    order = dict(payload["order"])  # type: ignore[arg-type]
    order["broker_order_id"] = "redacted-id"
    payload["order"] = order

    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(payload)

    assert error_info.value.reason_code == "UNEXPECTED_FIELD_REJECTED"


def test_unexpected_lifecycle_field_is_rejected() -> None:
    payload = evidence()
    lifecycle = dict(payload["lifecycle"])  # type: ignore[arg-type]
    lifecycle["raw_response"] = "redacted"
    payload["lifecycle"] = lifecycle

    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(payload)

    assert error_info.value.reason_code == "UNEXPECTED_FIELD_REJECTED"


def test_non_string_mapping_key_is_rejected() -> None:
    payload = evidence()
    payload[7] = "unexpected"  # type: ignore[index]

    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(payload)

    assert error_info.value.reason_code == "UNEXPECTED_FIELD_REJECTED"
