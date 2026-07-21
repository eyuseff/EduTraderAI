"""Sanitized, operator-triggered operational validation exports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from volcanoes.application.operations.dashboard import OperationalDashboardSnapshot


@dataclass(frozen=True, slots=True)
class VerificationMetadata:
    """Secret-free metadata written by the local release verification gate."""

    status: str
    command: str
    test_count: int | None = None
    line_coverage_percent: float | None = None
    branch_coverage_percent: float | None = None
    combined_coverage_percent: float | None = None
    verified_at: str | None = None

    def __post_init__(self) -> None:
        if self.status not in {"PASS", "FAIL"}:
            raise ValueError("verification status must be PASS or FAIL.")
        if self.command != "make verify":
            raise ValueError("verification command must be 'make verify'.")

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "command": self.command,
            "test_count": self.test_count,
            "line_coverage_percent": self.line_coverage_percent,
            "branch_coverage_percent": self.branch_coverage_percent,
            "combined_coverage_percent": self.combined_coverage_percent,
            "verified_at": self.verified_at,
        }


@dataclass(frozen=True, slots=True)
class ValidationSnapshot:
    """Immutable sanitized snapshot suitable for a local JSON export."""

    application_version: str
    timestamp: str
    dashboard: OperationalDashboardSnapshot

    def to_dict(self) -> dict[str, object]:
        health = self.dashboard.health.to_dict()
        return {
            "application_version": self.application_version,
            "timestamp": self.timestamp,
            "configuration_health": health,
            "active_feature_flags": health["deterministic_flags"],
            "metrics": self.dashboard.metrics.to_dict(),
            "verification": (
                self.dashboard.verification.to_dict()
                if self.dashboard.verification is not None
                else None
            ),
            "known_limitations": health["known_operational_limitations"],
        }


def build_validation_snapshot(
    application_version: str,
    dashboard: OperationalDashboardSnapshot,
    *,
    timestamp: datetime | None = None,
) -> ValidationSnapshot:
    """Build a controlled payload containing no broker or credential objects."""

    if not application_version.strip():
        raise ValueError("application_version cannot be empty.")
    observed_at = timestamp or datetime.now(UTC)
    if observed_at.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware.")
    return ValidationSnapshot(
        application_version=application_version.strip(),
        timestamp=observed_at.astimezone(UTC).isoformat(),
        dashboard=dashboard,
    )


def serialize_validation_snapshot(snapshot: ValidationSnapshot) -> str:
    """Return stable, sanitized JSON for local operator review."""

    if not isinstance(snapshot, ValidationSnapshot):
        raise TypeError("snapshot must be a ValidationSnapshot instance.")
    payload = snapshot.to_dict()
    _assert_sanitized(payload)
    return json.dumps(payload, indent=2, sort_keys=True) + "\n"


def export_validation_snapshot(
    path: Path,
    snapshot: ValidationSnapshot,
) -> Path:
    """Write one explicitly requested local JSON snapshot."""

    if path.suffix.lower() != ".json":
        raise ValueError("validation export path must end in .json.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(serialize_validation_snapshot(snapshot), encoding="utf-8")
    return path


def load_verification_metadata(path: Path) -> VerificationMetadata | None:
    """Load optional output from the trusted local release verification script."""

    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return VerificationMetadata(
        status=str(payload["status"]),
        command=str(payload["command"]),
        test_count=_optional_int(payload.get("test_count")),
        line_coverage_percent=_optional_float(payload.get("line_coverage_percent")),
        branch_coverage_percent=_optional_float(payload.get("branch_coverage_percent")),
        combined_coverage_percent=_optional_float(
            payload.get("combined_coverage_percent")
        ),
        verified_at=(
            str(payload["verified_at"])
            if payload.get("verified_at") is not None
            else None
        ),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("verification integer metadata is invalid.")
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("verification numeric metadata is invalid.")
    return float(value)


def _assert_sanitized(value: object, *, key: str = "") -> None:
    forbidden_keys = ("api_key", "secret", "password", "account_id", "token")
    forbidden_values = ("api_key=", "secret_key=", "password=", "bearer ", "sk-")
    normalized_key = key.lower()
    if any(fragment in normalized_key for fragment in forbidden_keys):
        raise ValueError(f"validation export contains forbidden key: {key}")
    if isinstance(value, str):
        normalized_value = value.lower()
        if any(fragment in normalized_value for fragment in forbidden_values):
            raise ValueError("validation export contains sensitive-looking content.")
        return
    if isinstance(value, dict):
        for child_key, child_value in value.items():
            _assert_sanitized(child_value, key=str(child_key))
        return
    if isinstance(value, (list, tuple)):
        for child_value in value:
            _assert_sanitized(child_value)
