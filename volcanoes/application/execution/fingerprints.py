"""Central SHA-256 fingerprints for Paper execution contracts."""

from __future__ import annotations

from hashlib import sha256
import re
from typing import Any

from volcanoes.application.execution._canonical import canonical_json_bytes
from volcanoes.application.execution.errors import PaperExecutionIdentityError

_DIGEST_RE = re.compile(r"^[a-z]{3}-[0-9a-f]{64}$")


def fingerprint_payload(prefix: str, primitive: Any) -> str:
    """Return a prefixed SHA-256 fingerprint over canonical bytes."""

    _validate_prefix(prefix)
    digest = sha256(canonical_json_bytes(primitive)).hexdigest()
    return f"{prefix}-{digest}"


def validate_fingerprint(value: str, prefix: str) -> str:
    """Validate and return a lowercase prefixed SHA-256 fingerprint."""

    _validate_prefix(prefix)
    if not isinstance(value, str):
        raise PaperExecutionIdentityError(
            "INVALID_FINGERPRINT",
            "Fingerprint must be text.",
        )
    normalized = value.strip().lower()
    if normalized != value:
        raise PaperExecutionIdentityError(
            "AMBIGUOUS_FINGERPRINT",
            "Fingerprint cannot contain whitespace or uppercase characters.",
        )
    if not normalized.startswith(f"{prefix}-") or not _DIGEST_RE.fullmatch(normalized):
        raise PaperExecutionIdentityError(
            "INVALID_FINGERPRINT",
            f"Fingerprint must use {prefix}- followed by 64 lowercase hex characters.",
        )
    return normalized


def command_payload_fingerprint(primitive: Any) -> str:
    return fingerprint_payload("pcf", primitive)


def approval_fingerprint(primitive: Any) -> str:
    return fingerprint_payload("pap", primitive)


def policy_fingerprint(primitive: Any) -> str:
    return fingerprint_payload("pps", primitive)


def receipt_fingerprint(primitive: Any) -> str:
    return fingerprint_payload("prc", primitive)


def failure_fingerprint(primitive: Any) -> str:
    return fingerprint_payload("pfl", primitive)


def eligibility_policy_fingerprint(primitive: Any) -> str:
    return fingerprint_payload("pep", primitive)


def eligibility_result_fingerprint(primitive: Any) -> str:
    return fingerprint_payload("per", primitive)


def _validate_prefix(prefix: str) -> None:
    if not isinstance(prefix, str) or not re.fullmatch(r"[a-z]{3}", prefix):
        raise PaperExecutionIdentityError(
            "INVALID_FINGERPRINT_PREFIX",
            "Fingerprint prefix must be exactly three lowercase letters.",
        )
