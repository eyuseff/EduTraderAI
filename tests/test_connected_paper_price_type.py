from __future__ import annotations

import pytest

from scripts.validate_connected_paper_evidence import (
    EvidenceValidationError,
    validate_evidence,
)


def evidence(
    *, limit_price: object = "100.49", reference_best_ask: object = "100.50"
) -> dict[str, object]:
    return {
        "schema_version": "connected-paper-qualification-evidence-v1",
        "environment": "PAPER",
        "live_trading": False,
        "credentials_embedded": False,
        "consequential_action_confirmed": True,
        "reference_best_ask": reference_best_ask,
        "observed_at": "2026-08-17T00:00:00Z",
        "order": {
            "symbol": "AAPL",
            "side": "BUY",
            "quantity": 1,
            "order_type": "LIMIT",
            "time_in_force": "DAY",
            "limit_price": limit_price,
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


@pytest.mark.parametrize("value", (None, True, 100, 100.49, ["100.49"], {"value": "100.49"}))
def test_limit_price_requires_textual_decimal_evidence(value: object) -> None:
    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(evidence(limit_price=value))

    assert error_info.value.reason_code == "INVALID_LIMIT_PRICE"


@pytest.mark.parametrize("value", (None, True, 101, 100.50, ["100.50"], {"value": "100.50"}))
def test_reference_best_ask_requires_textual_decimal_evidence(value: object) -> None:
    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(evidence(reference_best_ask=value))

    assert error_info.value.reason_code == "INVALID_REFERENCE_BEST_ASK"


def test_decimal_strings_are_trimmed_and_normalized() -> None:
    normalized = validate_evidence(
        evidence(limit_price=" 100.49 ", reference_best_ask=" 100.50 ")
    )

    assert normalized["limit_price"] == "100.49"
    assert normalized["reference_best_ask"] == "100.50"
