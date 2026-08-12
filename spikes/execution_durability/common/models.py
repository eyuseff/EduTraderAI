"""Immutable shared result models for the storage comparison spike."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class EnvironmentStatus(StrEnum):
    """Execution availability for a backend scenario."""

    EXECUTED = "EXECUTED"
    NOT_EXECUTED_ENVIRONMENT_UNAVAILABLE = "NOT_EXECUTED_ENVIRONMENT_UNAVAILABLE"
    STATIC_ASSESSMENT = "STATIC_ASSESSMENT"


@dataclass(frozen=True, slots=True)
class SpikeScenario:
    """Backend-neutral scenario definition."""

    scenario_id: str
    title: str
    expected_outcome: str
    restart_relevance: bool = False
    concurrency_relevance: bool = False
    migration_relevance: bool = False
    backup_relevance: bool = False


@dataclass(frozen=True, slots=True)
class SpikeResult:
    """Normalized immutable scenario result with safe notes only."""

    backend: str
    scenario_id: str
    environment_status: EnvironmentStatus
    executed: bool
    passed: bool | None
    expected_outcome: str
    observed_normalized_outcome: str
    conflict_classification: str | None = None
    transaction_atomicity_result: str | None = None
    restart_relevance: bool = False
    measurement_metadata: Mapping[str, object] = field(default_factory=dict)
    safe_notes: str = ""
    evidence_limitation: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "measurement_metadata",
            MappingProxyType(dict(self.measurement_metadata)),
        )
        if any(token in self.safe_notes.lower() for token in ("secret", "password")):
            raise ValueError("SpikeResult safe_notes cannot contain sensitive terms.")

    def to_primitive(self) -> dict[str, object]:
        return {
            "backend": self.backend,
            "scenario_id": self.scenario_id,
            "environment_status": self.environment_status.value,
            "executed": self.executed,
            "passed": self.passed,
            "expected_outcome": self.expected_outcome,
            "observed_normalized_outcome": self.observed_normalized_outcome,
            "conflict_classification": self.conflict_classification,
            "transaction_atomicity_result": self.transaction_atomicity_result,
            "restart_relevance": self.restart_relevance,
            "measurement_metadata": dict(self.measurement_metadata),
            "safe_notes": self.safe_notes,
            "evidence_limitation": self.evidence_limitation,
        }


@dataclass(frozen=True, slots=True)
class BackendAssessment:
    """Static backend score with evidence classification."""

    criterion: str
    sqlite_score: int
    postgresql_score: int
    evidence_basis: str
    notes: str

    def __post_init__(self) -> None:
        for score in (self.sqlite_score, self.postgresql_score):
            if score < 0 or score > 4:
                raise ValueError("Backend scores must be between 0 and 4.")


__all__ = [
    "BackendAssessment",
    "EnvironmentStatus",
    "SpikeResult",
    "SpikeScenario",
]
