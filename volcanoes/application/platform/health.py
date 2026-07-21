"""Immutable platform health diagnostics with no presentation dependency."""

from __future__ import annotations

from dataclasses import dataclass

from volcanoes.application.platform.configuration import (
    BrokerMode,
    PlatformConfiguration,
    validate_configuration,
)


@dataclass(frozen=True, slots=True)
class PlatformHealthReport:
    """Presentation-neutral description of active release behavior."""

    release: str
    active_execution_paths: tuple[str, ...]
    rollback_execution_paths: tuple[str, ...]
    broker_mode: str
    deterministic_flags: tuple[tuple[str, bool], ...]
    event_publisher_type: str
    persistence_mode: str
    supervisor_state_mode: str
    scanner_execution_mode: str
    known_operational_limitations: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible copy for any presentation adapter."""

        return {
            "release": self.release,
            "active_execution_paths": list(self.active_execution_paths),
            "rollback_execution_paths": list(self.rollback_execution_paths),
            "broker_mode": self.broker_mode,
            "deterministic_flags": dict(self.deterministic_flags),
            "event_publisher_type": self.event_publisher_type,
            "persistence_mode": self.persistence_mode,
            "supervisor_state_mode": self.supervisor_state_mode,
            "scanner_execution_mode": self.scanner_execution_mode,
            "known_operational_limitations": list(self.known_operational_limitations),
        }


def build_platform_health_report(
    configuration: PlatformConfiguration,
    *,
    event_publisher_type: str,
) -> PlatformHealthReport:
    """Build diagnostics only from validated, secret-free configuration."""

    validate_configuration(configuration)
    if not event_publisher_type.strip():
        raise ValueError("event_publisher_type cannot be empty.")

    flags = configuration.feature_flags
    active_paths: list[str] = []
    rollback_paths: list[str] = []
    if flags.preview:
        active_paths.extend(
            (
                "manual_deterministic_preview",
                "manual_deterministic_submission",
            )
        )
        rollback_paths.append("legacy_manual_preview_and_submission")
    else:
        active_paths.extend(("legacy_manual_preview", "legacy_manual_submission"))
        rollback_paths.append("manual_deterministic_preview_and_submission")

    if flags.scanner:
        active_paths.extend(
            (
                "supervised_scanner_preview_only",
                "supervised_scanner_submission",
            )
        )
        rollback_paths.append("legacy_scanner_preview_and_submission")
    else:
        active_paths.extend(
            ("legacy_scanner_preview_only", "legacy_scanner_submission")
        )
        rollback_paths.append("supervised_scanner_preview_and_submission")

    persistence_mode = (
        "LOCAL_JSON_BROKER_STATE"
        if configuration.broker_mode is BrokerMode.SIMULATED_PAPER
        else "ALPACA_PAPER_REMOTE_STATE"
    )
    return PlatformHealthReport(
        release="4.0.0-rc1",
        active_execution_paths=tuple(active_paths),
        rollback_execution_paths=tuple(rollback_paths),
        broker_mode=configuration.broker_mode.value,
        deterministic_flags=(
            ("preview", flags.preview),
            ("scanner", flags.scanner),
            ("submission", flags.submission),
        ),
        event_publisher_type=event_publisher_type.strip(),
        persistence_mode=persistence_mode,
        supervisor_state_mode="PROCESS_LOCAL_IN_MEMORY",
        scanner_execution_mode=configuration.scanner_execution_mode.value,
        known_operational_limitations=(
            "Operational events use a null publisher and are not durable.",
            "Operational metrics reset with the process and are not shared.",
            "Supervisor idempotency and symbol locks reset with the process.",
            "There is no distributed lock across application instances.",
            "Broker snapshots do not provide transactional versioning.",
            "The market-state supervisor policy has no authoritative adapter.",
            "Execution is paper-only and long-only.",
        ),
    )
