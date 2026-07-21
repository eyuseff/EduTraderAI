"""Presentation-neutral operational dashboard composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from volcanoes.application.operations.metrics import OperationalMetricsSnapshot
from volcanoes.application.platform import PlatformHealthReport

if TYPE_CHECKING:
    from volcanoes.application.operations.validation import VerificationMetadata


@dataclass(frozen=True, slots=True)
class OperationalDashboardSnapshot:
    """Immutable data model consumed by development presentation adapters."""

    health: PlatformHealthReport
    metrics: OperationalMetricsSnapshot
    verification: VerificationMetadata | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "health": self.health.to_dict(),
            "metrics": self.metrics.to_dict(),
            "verification": (
                self.verification.to_dict() if self.verification is not None else None
            ),
        }


def build_operational_dashboard_snapshot(
    health: PlatformHealthReport,
    metrics: OperationalMetricsSnapshot,
    verification: VerificationMetadata | None = None,
) -> OperationalDashboardSnapshot:
    """Compose already-sanitized application diagnostics for presentation."""

    if not isinstance(health, PlatformHealthReport):
        raise TypeError("health must be a PlatformHealthReport instance.")
    if not isinstance(metrics, OperationalMetricsSnapshot):
        raise TypeError("metrics must be an OperationalMetricsSnapshot instance.")
    return OperationalDashboardSnapshot(health, metrics, verification)
