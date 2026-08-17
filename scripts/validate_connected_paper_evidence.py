"""Offline validator for redacted Connected Paper qualification evidence.

The validator is intentionally broker-neutral and has no credential, network,
order-submission, persistence, or runtime dependency. It validates evidence
created by a separately authorized Paper session and emits a deterministic
SHA-256 fingerprint for immutable review records.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "connected-paper-qualification-evidence-v1"
_SECRET_TERMS = (
    "api_key",
    "apikey",
    "secret",
    "token",
    "password",
    "passwd",
    "authorization",
    "cookie",
    "private_key",
    "connection_string",
)
_SECRET_VALUE_MARKERS = (
    "sentinel_integration_secret_do_not_expose",
    "sentinel_broker_token_do_not_expose",
    "sentinel_password_do_not_expose",
    "api_key=",
    "secret=",
    "token=",
    "password=",
    "authorization:",
    "bearer ",
)
_REQUIRED_TRUE = (
    "submitted",
    "acknowledged",
    "status_observed",
    "cancel_requested",
    "cancel_confirmed",
    "cleanup_verified",
)
_TOP_LEVEL_FIELDS = frozenset(
    {
        "schema_version",
        "environment",
        "live_trading",
        "credentials_embedded",
        "consequential_action_confirmed",
        "reference_best_ask",
        "observed_at",
        "order",
        "lifecycle",
    }
)
_ORDER_FIELDS = frozenset(
    {
        "symbol",
        "side",
        "quantity",
        "order_type",
        "time_in_force",
        "limit_price",
    }
)
_LIFECYCLE_FIELDS = frozenset(_REQUIRED_TRUE)


class EvidenceValidationError(ValueError):
    """Fail-closed validation error containing only a safe reason code."""

    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


def _decimal(value: object, field: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise EvidenceValidationError(f"INVALID_{field.upper()}") from exc
    if not parsed.is_finite() or parsed <= 0:
        raise EvidenceValidationError(f"INVALID_{field.upper()}")
    return parsed


def _utc_timestamp(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceValidationError(f"INVALID_{field.upper()}")
    rendered = value.strip()
    try:
        parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceValidationError(f"INVALID_{field.upper()}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise EvidenceValidationError(f"INVALID_{field.upper()}")
    return parsed.isoformat().replace("+00:00", "Z")


def _walk_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, nested in value.items():
            rendered = str(key).lower()
            if any(term in rendered for term in _SECRET_TERMS):
                raise EvidenceValidationError("SECRET_SHAPED_FIELD_REJECTED")
            _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            _walk_keys(nested)


def _reject_unknown_fields(
    value: Mapping[object, object], allowed: frozenset[str]
) -> None:
    if any(not isinstance(key, str) or key not in allowed for key in value):
        raise EvidenceValidationError("UNEXPECTED_FIELD_REJECTED")


def _unsafe_symbol(value: str) -> bool:
    lowered = value.lower()
    if "/" in value or "\\" in value:
        return True
    return any(term in lowered for term in _SECRET_TERMS) or any(
        marker in lowered for marker in _SECRET_VALUE_MARKERS
    )


def validate_evidence(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a redacted Paper evidence payload and return safe normalized facts."""

    _walk_keys(payload)
    _reject_unknown_fields(payload, _TOP_LEVEL_FIELDS)
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise EvidenceValidationError("UNSUPPORTED_SCHEMA_VERSION")
    if payload.get("environment") != "PAPER":
        raise EvidenceValidationError("PAPER_ENVIRONMENT_REQUIRED")
    if payload.get("live_trading") is not False:
        raise EvidenceValidationError("LIVE_TRADING_MUST_BE_FALSE")
    if payload.get("credentials_embedded") is not False:
        raise EvidenceValidationError("CREDENTIALS_MUST_NOT_BE_EMBEDDED")
    if payload.get("consequential_action_confirmed") is not True:
        raise EvidenceValidationError("CONSEQUENTIAL_ACTION_CONFIRMATION_REQUIRED")
    observed_at = _utc_timestamp(payload.get("observed_at"), "observed_at")

    order = payload.get("order")
    if not isinstance(order, Mapping):
        raise EvidenceValidationError("ORDER_EVIDENCE_REQUIRED")
    _reject_unknown_fields(order, _ORDER_FIELDS)
    raw_symbol = order.get("symbol")
    if not isinstance(raw_symbol, str):
        raise EvidenceValidationError("SYMBOL_REQUIRED")
    symbol = raw_symbol.strip()
    if not symbol:
        raise EvidenceValidationError("SYMBOL_REQUIRED")
    if _unsafe_symbol(symbol):
        raise EvidenceValidationError("UNSAFE_SYMBOL")
    symbol = symbol.upper()
    if order.get("side") != "BUY":
        raise EvidenceValidationError("BUY_SIDE_REQUIRED")
    quantity = order.get("quantity")
    if type(quantity) is not int or quantity != 1:
        raise EvidenceValidationError("ONE_SHARE_REQUIRED")
    if order.get("order_type") != "LIMIT":
        raise EvidenceValidationError("LIMIT_ORDER_REQUIRED")
    if order.get("time_in_force") != "DAY":
        raise EvidenceValidationError("DAY_TIME_IN_FORCE_REQUIRED")

    limit_price = _decimal(order.get("limit_price"), "limit_price")
    reference_best_ask = _decimal(
        payload.get("reference_best_ask"), "reference_best_ask"
    )
    if limit_price >= reference_best_ask:
        raise EvidenceValidationError("MARKETABLE_LIMIT_REJECTED")

    lifecycle = payload.get("lifecycle")
    if not isinstance(lifecycle, Mapping):
        raise EvidenceValidationError("LIFECYCLE_EVIDENCE_REQUIRED")
    _reject_unknown_fields(lifecycle, _LIFECYCLE_FIELDS)
    for field in _REQUIRED_TRUE:
        if lifecycle.get(field) is not True:
            raise EvidenceValidationError(f"{field.upper()}_EVIDENCE_REQUIRED")

    return {
        "schema_version": SCHEMA_VERSION,
        "environment": "PAPER",
        "consequential_action_confirmed": True,
        "observed_at": observed_at,
        "symbol": symbol,
        "side": "BUY",
        "quantity": 1,
        "order_type": "LIMIT",
        "time_in_force": "DAY",
        "limit_price": str(limit_price),
        "reference_best_ask": str(reference_best_ask),
        "non_marketable": True,
        "submitted": True,
        "acknowledged": True,
        "status_observed": True,
        "cancel_requested": True,
        "cancel_confirmed": True,
        "cleanup_verified": True,
        "live_trading": False,
        "credentials_embedded": False,
    }


def evidence_fingerprint(payload: Mapping[str, Any]) -> str:
    """Return a deterministic digest of the complete redacted evidence payload."""

    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_validation_report(payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized = validate_evidence(payload)
    return {
        "validation": "PASS",
        "evidence_sha256": evidence_fingerprint(payload),
        "normalized": normalized,
        "broker_accessed_by_validator": False,
        "credentials_loaded_by_validator": False,
        "network_used_by_validator": False,
        "order_submitted_by_validator": False,
        "runtime_changed_by_validator": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate redacted Connected Paper qualification evidence offline."
    )
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args(argv)
    payload = json.loads(args.evidence.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise EvidenceValidationError("OBJECT_PAYLOAD_REQUIRED")
    print(json.dumps(build_validation_report(payload), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
