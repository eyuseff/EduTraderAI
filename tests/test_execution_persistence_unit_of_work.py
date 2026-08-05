from __future__ import annotations

import inspect
from typing import get_type_hints

from volcanoes.application.execution import (
    AggregateSaveResult,
    CommandRegistrationResult,
    ExecutionAggregateRecord,
    ExecutionAggregateRepository,
    ExecutionCommandRecord,
    ExecutionCommandRepository,
    ExecutionFailureRecord,
    ExecutionIdempotencyRecord,
    ExecutionIdempotencyRepository,
    ExecutionPersistenceSession,
    ExecutionReceiptRecord,
    ExecutionTransitionRecord,
    ExecutionTransitionJournal,
    ExecutionUnitOfWork,
    IdempotencyReservationResult,
    PaperExecutionRevision,
    RecordLoadResult,
    TransitionAppendResult,
    UnitOfWorkCommitResult,
)


def test_unit_of_work_is_protocol_with_explicit_transaction_methods() -> None:
    assert getattr(ExecutionUnitOfWork, "_is_protocol", False)
    assert get_type_hints(ExecutionUnitOfWork.commit)["return"] is (
        UnitOfWorkCommitResult
    )
    assert get_type_hints(ExecutionUnitOfWork.rollback)["return"] is type(None)


def test_unit_of_work_exposes_expected_repositories() -> None:
    annotations = get_type_hints(ExecutionUnitOfWork)

    assert annotations["aggregates"] is ExecutionAggregateRepository
    assert annotations["commands"] is ExecutionCommandRepository
    assert annotations["idempotency"] is ExecutionIdempotencyRepository
    assert annotations["transitions"] is ExecutionTransitionJournal
    assert "broker_references" in annotations
    assert "receipts" in annotations
    assert "failures" in annotations
    assert "approvals" in annotations
    assert "reconciliations" in annotations
    assert "restart_discovery" in annotations


def test_unit_of_work_context_manager_does_not_define_auto_commit_contract() -> None:
    exit_hints = get_type_hints(ExecutionUnitOfWork.__exit__)

    assert exit_hints["return"] is type(None)
    assert "commit" in vars(ExecutionUnitOfWork)
    assert "rollback" in vars(ExecutionUnitOfWork)


def test_persistence_session_is_atomic_boundary_protocol() -> None:
    assert getattr(ExecutionPersistenceSession, "_is_protocol", False)

    expected_methods = {
        "register_command",
        "reserve_idempotency",
        "load_aggregate",
        "append_transition",
        "save_aggregate",
        "record_receipt",
        "record_failure",
    }

    assert expected_methods.issubset(vars(ExecutionPersistenceSession))


def test_session_register_command_signature() -> None:
    hints = get_type_hints(ExecutionPersistenceSession.register_command)

    assert hints["command"] is ExecutionCommandRecord
    assert hints["return"] is CommandRegistrationResult


def test_session_reserve_idempotency_signature() -> None:
    hints = get_type_hints(ExecutionPersistenceSession.reserve_idempotency)

    assert hints["reservation"] is ExecutionIdempotencyRecord
    assert hints["return"] is IdempotencyReservationResult


def test_session_save_aggregate_signature_requires_expected_revision() -> None:
    signature = inspect.signature(ExecutionPersistenceSession.save_aggregate)
    hints = get_type_hints(ExecutionPersistenceSession.save_aggregate)

    assert signature.parameters["expected_revision"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    assert hints["aggregate"] is ExecutionAggregateRecord
    assert hints["expected_revision"] is PaperExecutionRevision
    assert hints["return"] is AggregateSaveResult


def test_session_transition_receipt_failure_signatures() -> None:
    append_hints = get_type_hints(ExecutionPersistenceSession.append_transition)
    receipt_hints = get_type_hints(ExecutionPersistenceSession.record_receipt)
    failure_hints = get_type_hints(ExecutionPersistenceSession.record_failure)

    assert append_hints["transition"] is ExecutionTransitionRecord
    assert append_hints["return"] is TransitionAppendResult
    assert receipt_hints["receipt"] is ExecutionReceiptRecord
    assert receipt_hints["return"] is RecordLoadResult
    assert failure_hints["failure"] is ExecutionFailureRecord
    assert failure_hints["return"] is RecordLoadResult


def test_unit_of_work_defines_no_broker_or_event_methods() -> None:
    prohibited = {
        "submit",
        "cancel_order",
        "replace_order",
        "call_broker",
        "publish",
        "emit",
        "metric",
        "execute_sql",
        "migrate",
    }
    exposed = {
        name
        for name, value in vars(ExecutionUnitOfWork).items()
        if inspect.isfunction(value)
    } | {
        name
        for name, value in vars(ExecutionPersistenceSession).items()
        if inspect.isfunction(value)
    }

    assert prohibited.isdisjoint(exposed)
