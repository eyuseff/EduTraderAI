from __future__ import annotations

import pytest

from scripts.validate_connected_paper_evidence import (
    EvidenceValidationError,
    validate_evidence,
)


def evidence(symbol: object) -> dict[str, object]:
    return {
        "schema_version": "connected-paper-qualification-evidence-v1",
        "environment": "PAPER",
        "live_trading": False,
        "credentials_embedded": False,
        "consequential_action_confirmed": True,
        "reference_best_ask": "100.50",
        "observed_at": "2026-08-17T00:00:00Z",
        "order": {
            "symbol": symbol,
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


@pytest.mark.parametrize("symbol", (None, True, 123, ["AAPL"], {"value": "AAPL"}))
def test_symbol_requires_textual_evidence(symbol: object) -> None:
    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(evidence(symbol))

    assert error_info.value.reason_code == "SYMBOL_REQUIRED"


@pytest.mark.parametrize(
    "symbol",
    (
        "AAPL/../../state",
        r"AAPL\state",
        "api_key",
        "Bearer dummy-token",
        "token=dummy",
        "sentinel_integration_secret_do_not_expose",
    ),
)
def test_symbol_rejects_unsafe_or_secret_shaped_text(symbol: str) -> None:
    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(evidence(symbol))

    assert error_info.value.reason_code == "UNSAFE_SYMBOL"


def test_textual_symbol_is_trimmed_and_normalized() -> None:
    normalized = validate_evidence(evidence(" aapl "))

    assert normalized["symbol"] == "AAPL"
