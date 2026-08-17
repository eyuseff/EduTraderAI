from __future__ import annotations

import json
import os
import socket
import subprocess
from decimal import Decimal

import pytest

from scripts.validate_connected_paper_evidence import (
    EvidenceValidationError,
    build_validation_report,
    evidence_fingerprint,
    validate_evidence,
)


def evidence(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": "connected-paper-qualification-evidence-v1",
        "environment": "PAPER",
        "live_trading": False,
        "credentials_embedded": False,
        "consequential_action_confirmed": True,
        "reference_best_ask": "100.50",
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
        "observed_at": "2026-08-17T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def test_valid_evidence_passes_with_one_non_marketable_share() -> None:
    normalized = validate_evidence(evidence())

    assert normalized["environment"] == "PAPER"
    assert normalized["consequential_action_confirmed"] is True
    assert normalized["observed_at"] == "2026-08-17T00:00:00Z"
    assert normalized["side"] == "BUY"
    assert normalized["quantity"] == 1
    assert normalized["order_type"] == "LIMIT"
    assert Decimal(normalized["limit_price"]) < Decimal(
        normalized["reference_best_ask"]
    )
    assert normalized["cleanup_verified"] is True


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    (
        ("environment", "LIVE", "PAPER_ENVIRONMENT_REQUIRED"),
        ("live_trading", True, "LIVE_TRADING_MUST_BE_FALSE"),
        ("credentials_embedded", True, "CREDENTIALS_MUST_NOT_BE_EMBEDDED"),
    ),
)
def test_top_level_safety_failures_are_rejected(
    field: str, value: object, reason: str
) -> None:
    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(evidence(**{field: value}))

    assert error_info.value.reason_code == reason


@pytest.mark.parametrize("confirmation", (None, False, 1, "true"))
def test_consequential_action_confirmation_requires_explicit_true(
    confirmation: object,
) -> None:
    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(evidence(consequential_action_confirmed=confirmation))

    assert (
        error_info.value.reason_code
        == "CONSEQUENTIAL_ACTION_CONFIRMATION_REQUIRED"
    )


@pytest.mark.parametrize(
    "observed_at",
    (
        None,
        "",
        "not-a-time",
        "2026-08-17T00:00:00",
        "2026-08-17T00:00:00-04:00",
    ),
)
def test_observed_at_requires_utc_timestamp(observed_at: object) -> None:
    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(evidence(observed_at=observed_at))

    assert error_info.value.reason_code == "INVALID_OBSERVED_AT"


@pytest.mark.parametrize(
    ("order_overrides", "reason"),
    (
        ({"side": "SELL"}, "BUY_SIDE_REQUIRED"),
        ({"quantity": 2}, "ONE_SHARE_REQUIRED"),
        ({"quantity": True}, "ONE_SHARE_REQUIRED"),
        ({"quantity": 1.0}, "ONE_SHARE_REQUIRED"),
        ({"order_type": "MARKET"}, "LIMIT_ORDER_REQUIRED"),
        ({"time_in_force": "GTC"}, "DAY_TIME_IN_FORCE_REQUIRED"),
        ({"limit_price": "100.50"}, "MARKETABLE_LIMIT_REJECTED"),
        ({"limit_price": "100.51"}, "MARKETABLE_LIMIT_REJECTED"),
    ),
)
def test_order_safety_failures_are_rejected(
    order_overrides: dict[str, object], reason: str
) -> None:
    payload = evidence()
    order = dict(payload["order"])  # type: ignore[arg-type]
    order.update(order_overrides)
    payload["order"] = order

    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(payload)

    assert error_info.value.reason_code == reason


@pytest.mark.parametrize(
    "field",
    (
        "submitted",
        "acknowledged",
        "status_observed",
        "cancel_requested",
        "cancel_confirmed",
        "cleanup_verified",
    ),
)
def test_missing_lifecycle_evidence_fails_closed(field: str) -> None:
    payload = evidence()
    lifecycle = dict(payload["lifecycle"])  # type: ignore[arg-type]
    lifecycle[field] = False
    payload["lifecycle"] = lifecycle

    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(payload)

    assert error_info.value.reason_code == f"{field.upper()}_EVIDENCE_REQUIRED"


def test_secret_shaped_fields_are_rejected_recursively() -> None:
    payload = evidence(extra={"api_key": "redacted"})

    with pytest.raises(EvidenceValidationError) as error_info:
        validate_evidence(payload)

    assert error_info.value.reason_code == "SECRET_SHAPED_FIELD_REJECTED"


def test_fingerprint_is_deterministic_and_sensitive() -> None:
    first = evidence()
    same = json.loads(json.dumps(first))
    changed = evidence(observed_at="2026-08-17T00:00:01Z")

    assert evidence_fingerprint(first) == evidence_fingerprint(same)
    assert evidence_fingerprint(first) != evidence_fingerprint(changed)


def test_validation_report_never_claims_external_effects() -> None:
    report = build_validation_report(evidence())

    assert report["validation"] == "PASS"
    assert len(report["evidence_sha256"]) == 64
    assert report["broker_accessed_by_validator"] is False
    assert report["credentials_loaded_by_validator"] is False
    assert report["network_used_by_validator"] is False
    assert report["order_submitted_by_validator"] is False
    assert report["runtime_changed_by_validator"] is False


def test_validator_has_no_network_subprocess_or_environment_dependency(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("external effect attempted")

    monkeypatch.setattr(socket, "socket", fail)
    monkeypatch.setattr(subprocess, "run", fail)
    monkeypatch.setattr(os, "getenv", fail)

    report = build_validation_report(evidence())

    assert report["validation"] == "PASS"
