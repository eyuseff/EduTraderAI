from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.validate_connected_paper_evidence import EvidenceValidationError, main


def valid_evidence_json() -> str:
    payload = {
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
    return json.dumps(payload, separators=(",", ":"))


@pytest.mark.parametrize(
    ("needle", "duplicate"),
    (
        (
            '"environment":"PAPER"',
            '"environment":"PAPER","environment":"PAPER"',
        ),
        ('"symbol":"AAPL"', '"symbol":"AAPL","symbol":"AAPL"'),
        (
            '"cleanup_verified":true',
            '"cleanup_verified":true,"cleanup_verified":true',
        ),
    ),
)
def test_cli_rejects_duplicate_fields_at_any_object_depth(
    tmp_path: Path, needle: str, duplicate: str
) -> None:
    raw = valid_evidence_json().replace(needle, duplicate, 1)
    evidence_path = tmp_path / "evidence.json"
    evidence_path.write_text(raw, encoding="utf-8")

    with pytest.raises(EvidenceValidationError) as error_info:
        main([str(evidence_path)])

    assert error_info.value.reason_code == "DUPLICATE_FIELD_REJECTED"
