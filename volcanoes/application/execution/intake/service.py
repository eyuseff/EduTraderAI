"""Brokerless application service for atomic durable execution intake."""

from __future__ import annotations

from dataclasses import replace

from volcanoes.application.execution.intake.contracts import (
    TransactionalIntakeRequest,
    TransactionalIntakeResult,
    TransactionalIntakeStatus,
)
from volcanoes.application.execution.intake.ports import ExecutionUnitOfWorkProvider
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycleState,
    is_aggregate_terminal,
    is_command_terminal,
)
from volcanoes.application.execution.persistence import ExecutionPersistenceResultStatus


class TransactionalExecutionIntakeService:
    """Atomically persist an inert command and its dispatch handoff."""

    def __init__(self, persistence: ExecutionUnitOfWorkProvider) -> None:
        if not isinstance(persistence, ExecutionUnitOfWorkProvider):
            raise TypeError("persistence must provide execution units of work.")
        self._persistence = persistence

    def intake(self, request: TransactionalIntakeRequest) -> TransactionalIntakeResult:
        if not isinstance(request, TransactionalIntakeRequest):
            raise TypeError("request must be a TransactionalIntakeRequest.")

        with self._persistence.unit_of_work() as unit:
            command = unit.commands.register(request.command)
            if command.status is ExecutionPersistenceResultStatus.EXACT_REPLAY:
                unit.rollback()
                return _result(
                    request,
                    TransactionalIntakeStatus.EXACT_REPLAY,
                    False,
                    command.result_fingerprint,
                )
            if command.status is ExecutionPersistenceResultStatus.COMMAND_CONFLICT:
                unit.rollback()
                return _result(
                    request,
                    TransactionalIntakeStatus.COMMAND_CONFLICT,
                    False,
                    command.result_fingerprint,
                )
            if command.status is not ExecutionPersistenceResultStatus.CREATED:
                unit.rollback()
                return _result(
                    request,
                    TransactionalIntakeStatus.TRANSACTION_ABORTED,
                    False,
                    command.result_fingerprint,
                )

            reservation = unit.idempotency.reserve(request.idempotency)
            if reservation.status is ExecutionPersistenceResultStatus.LOGICAL_REPLAY:
                unit.rollback()
                return _result(
                    request,
                    TransactionalIntakeStatus.LOGICAL_REPLAY,
                    False,
                    reservation.result_fingerprint,
                )
            if (
                reservation.status
                is ExecutionPersistenceResultStatus.IDEMPOTENCY_CONFLICT
            ):
                unit.rollback()
                return _result(
                    request,
                    TransactionalIntakeStatus.IDEMPOTENCY_CONFLICT,
                    False,
                    reservation.result_fingerprint,
                )
            if reservation.status is not ExecutionPersistenceResultStatus.CREATED:
                unit.rollback()
                return _result(
                    request,
                    TransactionalIntakeStatus.TRANSACTION_ABORTED,
                    False,
                    reservation.result_fingerprint,
                )

            loaded = unit.aggregates.get(request.aggregate.aggregate_id)
            if loaded.status is ExecutionPersistenceResultStatus.LOADED:
                unit.rollback()
                return _result(
                    request,
                    TransactionalIntakeStatus.STALE_REVISION,
                    False,
                    loaded.result_fingerprint,
                )
            if loaded.status is not ExecutionPersistenceResultStatus.NOT_FOUND:
                unit.rollback()
                return _result(
                    request,
                    TransactionalIntakeStatus.TRANSACTION_ABORTED,
                    False,
                    loaded.result_fingerprint,
                )

            initial = replace(
                request.aggregate,
                lifecycle_state=PaperExecutionLifecycleState.CREATED,
                execution_revision=request.expected_revision,
                outcome_unknown=False,
                reconciliation_required=False,
                command_terminal=False,
                aggregate_terminal=False,
                last_transition_id="PX-TRN-001",
                updated_at=request.aggregate.created_at,
            )
            created = unit.aggregates.save(
                initial, expected_revision=request.expected_revision
            )
            if created.status is ExecutionPersistenceResultStatus.STALE_REVISION:
                unit.rollback()
                return _result(
                    request,
                    TransactionalIntakeStatus.STALE_REVISION,
                    False,
                    created.result_fingerprint,
                )
            if created.status is not ExecutionPersistenceResultStatus.CREATED:
                unit.rollback()
                return _result(
                    request,
                    TransactionalIntakeStatus.TRANSACTION_ABORTED,
                    False,
                    created.result_fingerprint,
                )

            for transition in request.transitions:
                if (
                    transition.destination_state
                    is PaperExecutionLifecycleState.APPROVAL_CONFIRMED
                ):
                    approval = unit.approvals.record(request.approval)
                    if (
                        approval.status
                        is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
                    ):
                        unit.rollback()
                        return _result(
                            request,
                            TransactionalIntakeStatus.COMMAND_CONFLICT,
                            False,
                            approval.result_fingerprint,
                        )
                    if approval.status not in {
                        ExecutionPersistenceResultStatus.CREATED,
                        ExecutionPersistenceResultStatus.EXACT_REPLAY,
                    }:
                        unit.rollback()
                        return _result(
                            request,
                            TransactionalIntakeStatus.TRANSACTION_ABORTED,
                            False,
                            approval.result_fingerprint,
                        )
                appended = unit.transitions.append(transition)
                if appended.status is not ExecutionPersistenceResultStatus.APPENDED:
                    unit.rollback()
                    return _result(
                        request,
                        TransactionalIntakeStatus.TRANSACTION_ABORTED,
                        False,
                        appended.result_fingerprint,
                    )
                snapshot = replace(
                    request.aggregate,
                    lifecycle_state=transition.destination_state,
                    execution_revision=transition.next_revision,
                    outcome_unknown=transition.destination_state
                    is PaperExecutionLifecycleState.OUTCOME_UNKNOWN,
                    reconciliation_required=transition.destination_state
                    is PaperExecutionLifecycleState.RECONCILIATION_REQUIRED,
                    command_terminal=is_command_terminal(transition.destination_state),
                    aggregate_terminal=is_aggregate_terminal(
                        transition.destination_state
                    ),
                    last_transition_id=transition.transition_id,
                    updated_at=transition.recorded_at,
                )
                saved = unit.aggregates.save(
                    snapshot,
                    expected_revision=transition.previous_revision,
                )
                if saved.status is ExecutionPersistenceResultStatus.STALE_REVISION:
                    unit.rollback()
                    return _result(
                        request,
                        TransactionalIntakeStatus.STALE_REVISION,
                        False,
                        saved.result_fingerprint,
                    )
                if saved.status is not ExecutionPersistenceResultStatus.SAVED:
                    unit.rollback()
                    return _result(
                        request,
                        TransactionalIntakeStatus.TRANSACTION_ABORTED,
                        False,
                        saved.result_fingerprint,
                    )

            committed = unit.commit()
            if (
                not committed.committed
                or committed.status is not ExecutionPersistenceResultStatus.SAVED
            ):
                return _result(
                    request,
                    TransactionalIntakeStatus.TRANSACTION_ABORTED,
                    False,
                    committed.result_fingerprint,
                )
            return _result(
                request,
                TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH,
                True,
                committed.result_fingerprint,
            )


def _result(
    request: TransactionalIntakeRequest,
    status: TransactionalIntakeStatus,
    committed: bool,
    source_fingerprint: str,
) -> TransactionalIntakeResult:
    accepted = status is TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH and committed
    return TransactionalIntakeResult(
        status=status,
        committed=committed,
        command_id=str(request.command.command_id),
        aggregate_id=str(request.aggregate.aggregate_id),
        final_revision=int(request.aggregate.execution_revision) if accepted else None,
        durable_dispatch_intent=accepted,
        source_result_fingerprint=source_fingerprint,
    )
