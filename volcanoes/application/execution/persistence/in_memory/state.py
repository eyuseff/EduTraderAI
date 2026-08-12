"""Private process-local state for the in-memory execution persistence adapter.

The state held here is intentionally non-durable. It is lost when the adapter
instance is discarded and does not survive a process restart. It is a reference
implementation for validating contracts only, not a production execution source
of truth and not authority for broker execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionIdempotencyKey,
)
from volcanoes.application.execution.persistence.contracts import (
    ExecutionAggregateRecord,
    ExecutionApprovalRecord,
    ExecutionBrokerReferenceRecord,
    ExecutionCommandRecord,
    ExecutionFailureRecord,
    ExecutionIdempotencyRecord,
    ExecutionReceiptRecord,
    ExecutionReconciliationRecord,
    ExecutionTransitionRecord,
)


@dataclass(slots=True)
class InMemoryExecutionPersistenceState:
    """Private mutable state owned by one in-memory adapter instance."""

    _aggregates: dict[PaperExecutionAggregateId, ExecutionAggregateRecord] = field(
        default_factory=dict
    )
    _commands: dict[PaperExecutionCommandId, ExecutionCommandRecord] = field(
        default_factory=dict
    )
    _idempotency: dict[PaperExecutionIdempotencyKey, ExecutionIdempotencyRecord] = (
        field(default_factory=dict)
    )
    _transitions_by_id: dict[str, ExecutionTransitionRecord] = field(
        default_factory=dict
    )
    _transition_order: tuple[str, ...] = ()
    _broker_references: dict[
        PaperBrokerOrderReference, ExecutionBrokerReferenceRecord
    ] = field(default_factory=dict)
    _receipts: dict[str, ExecutionReceiptRecord] = field(default_factory=dict)
    _failures: dict[str, ExecutionFailureRecord] = field(default_factory=dict)
    _approvals: dict[str, ExecutionApprovalRecord] = field(default_factory=dict)
    _reconciliations: dict[str, ExecutionReconciliationRecord] = field(
        default_factory=dict
    )
    _sequence: int = 0

    def snapshot(self) -> "InMemoryExecutionPersistenceState":
        """Return an isolated mutable snapshot of this process-local state."""

        return InMemoryExecutionPersistenceState(
            _aggregates=dict(self._aggregates),
            _commands=dict(self._commands),
            _idempotency=dict(self._idempotency),
            _transitions_by_id=dict(self._transitions_by_id),
            _transition_order=tuple(self._transition_order),
            _broker_references=dict(self._broker_references),
            _receipts=dict(self._receipts),
            _failures=dict(self._failures),
            _approvals=dict(self._approvals),
            _reconciliations=dict(self._reconciliations),
            _sequence=self._sequence,
        )

    def replace_from(self, other: "InMemoryExecutionPersistenceState") -> None:
        """Atomically replace this state from a validated snapshot."""

        self._aggregates = dict(other._aggregates)
        self._commands = dict(other._commands)
        self._idempotency = dict(other._idempotency)
        self._transitions_by_id = dict(other._transitions_by_id)
        self._transition_order = tuple(other._transition_order)
        self._broker_references = dict(other._broker_references)
        self._receipts = dict(other._receipts)
        self._failures = dict(other._failures)
        self._approvals = dict(other._approvals)
        self._reconciliations = dict(other._reconciliations)
        self._sequence = other._sequence

    def aggregate_records(self) -> tuple[ExecutionAggregateRecord, ...]:
        """Return aggregate records in deterministic identity order."""

        return tuple(
            self._aggregates[key]
            for key in sorted(self._aggregates, key=lambda identity: identity.value)
        )

    def command_records(self) -> tuple[ExecutionCommandRecord, ...]:
        """Return command records in deterministic identity order."""

        return tuple(
            self._commands[key]
            for key in sorted(self._commands, key=lambda identity: identity.value)
        )

    def idempotency_records(self) -> tuple[ExecutionIdempotencyRecord, ...]:
        """Return idempotency records in deterministic identity order."""

        return tuple(
            self._idempotency[key]
            for key in sorted(self._idempotency, key=lambda identity: identity.value)
        )

    def transition_records(self) -> tuple[ExecutionTransitionRecord, ...]:
        """Return transition journal records in append order."""

        return tuple(self._transitions_by_id[key] for key in self._transition_order)

    def broker_reference_records(self) -> tuple[ExecutionBrokerReferenceRecord, ...]:
        """Return broker-reference records in deterministic reference order."""

        return tuple(
            self._broker_references[key]
            for key in sorted(
                self._broker_references,
                key=lambda reference: reference.value,
            )
        )

    def receipt_records(self) -> tuple[ExecutionReceiptRecord, ...]:
        """Return receipt records in deterministic fingerprint order."""

        return tuple(self._receipts[key] for key in sorted(self._receipts))

    def failure_records(self) -> tuple[ExecutionFailureRecord, ...]:
        """Return failure records in deterministic fingerprint order."""

        return tuple(self._failures[key] for key in sorted(self._failures))

    def approval_records(self) -> tuple[ExecutionApprovalRecord, ...]:
        """Return approval records in deterministic fingerprint order."""

        return tuple(self._approvals[key] for key in sorted(self._approvals))

    def reconciliation_records(self) -> tuple[ExecutionReconciliationRecord, ...]:
        """Return reconciliation records in deterministic identity order."""

        return tuple(
            self._reconciliations[key] for key in sorted(self._reconciliations)
        )

    def next_sequence(self) -> int:
        """Advance and return deterministic local insertion sequence."""

        self._sequence += 1
        return self._sequence


__all__ = ["InMemoryExecutionPersistenceState"]
