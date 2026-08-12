from __future__ import annotations

import inspect
from typing import get_type_hints

from volcanoes.application.execution import (
    AggregateSaveResult,
    CommandRegistrationResult,
    ExecutionAggregateRecord,
    ExecutionAggregateRepository,
    ExecutionApprovalRecord,
    ExecutionApprovalRepository,
    ExecutionBrokerReferenceRecord,
    ExecutionBrokerReferenceRepository,
    ExecutionCommandRecord,
    ExecutionCommandRepository,
    ExecutionFailureRecord,
    ExecutionFailureRepository,
    ExecutionIdempotencyRecord,
    ExecutionIdempotencyRepository,
    ExecutionReceiptRecord,
    ExecutionReceiptRepository,
    ExecutionReconciliationRecord,
    ExecutionReconciliationRepository,
    ExecutionRestartDiscoveryQuery,
    ExecutionRestartDiscoveryRepository,
    ExecutionTransitionJournal,
    ExecutionTransitionRecord,
    IdempotencyReservationResult,
    PaperExecutionRevision,
    RecordLoadResult,
    ReplayLookupResult,
    RestartDiscoveryResult,
    TransitionAppendResult,
)


def test_repository_ports_are_protocols_not_concrete_adapters() -> None:
    ports = (
        ExecutionAggregateRepository,
        ExecutionCommandRepository,
        ExecutionIdempotencyRepository,
        ExecutionTransitionJournal,
        ExecutionBrokerReferenceRepository,
        ExecutionReceiptRepository,
        ExecutionFailureRepository,
        ExecutionApprovalRepository,
        ExecutionReconciliationRepository,
        ExecutionRestartDiscoveryRepository,
    )

    assert all(getattr(port, "_is_protocol", False) for port in ports)
    assert all(not hasattr(port, "__dataclass_fields__") for port in ports)


def test_aggregate_repository_save_requires_expected_revision() -> None:
    signature = inspect.signature(ExecutionAggregateRepository.save)

    assert "expected_revision" in signature.parameters
    assert signature.parameters["expected_revision"].kind is (
        inspect.Parameter.KEYWORD_ONLY
    )
    hints = get_type_hints(ExecutionAggregateRepository.save)
    assert hints["record"] is ExecutionAggregateRecord
    assert hints["expected_revision"] is PaperExecutionRevision
    assert hints["return"] is AggregateSaveResult


def test_command_repository_exposes_registration_and_replay_lookup() -> None:
    register_hints = get_type_hints(ExecutionCommandRepository.register)
    replay_hints = get_type_hints(ExecutionCommandRepository.lookup_replay)

    assert register_hints["record"] is ExecutionCommandRecord
    assert register_hints["return"] is CommandRegistrationResult
    assert replay_hints["return"] is ReplayLookupResult


def test_idempotency_repository_exposes_reservation_result() -> None:
    hints = get_type_hints(ExecutionIdempotencyRepository.reserve)

    assert hints["record"] is ExecutionIdempotencyRecord
    assert hints["return"] is IdempotencyReservationResult


def test_transition_journal_appends_transition_records() -> None:
    hints = get_type_hints(ExecutionTransitionJournal.append)

    assert hints["record"] is ExecutionTransitionRecord
    assert hints["return"] is TransitionAppendResult


def test_repository_ports_use_immutable_records_and_results() -> None:
    checked = {
        ExecutionBrokerReferenceRepository.register: ExecutionBrokerReferenceRecord,
        ExecutionReceiptRepository.record: ExecutionReceiptRecord,
        ExecutionFailureRepository.record: ExecutionFailureRecord,
        ExecutionApprovalRepository.record: ExecutionApprovalRecord,
        ExecutionReconciliationRepository.record: ExecutionReconciliationRecord,
    }

    for method, record_type in checked.items():
        hints = get_type_hints(method)
        assert record_type in hints.values()
        assert hints["return"] is RecordLoadResult


def test_restart_discovery_repository_is_query_only() -> None:
    hints = get_type_hints(ExecutionRestartDiscoveryRepository.discover)

    assert hints["query"] is ExecutionRestartDiscoveryQuery
    assert hints["return"] is RestartDiscoveryResult


def test_ports_do_not_expose_storage_or_broker_methods() -> None:
    prohibited = {
        "connect",
        "create_schema",
        "migrate",
        "execute_sql",
        "flush_to_disk",
        "acquire_lock",
        "publish",
        "call_broker",
        "recover_automatically",
        "retry",
    }
    ports = (
        ExecutionAggregateRepository,
        ExecutionCommandRepository,
        ExecutionIdempotencyRepository,
        ExecutionTransitionJournal,
        ExecutionBrokerReferenceRepository,
        ExecutionReceiptRepository,
        ExecutionFailureRepository,
        ExecutionApprovalRepository,
        ExecutionReconciliationRepository,
        ExecutionRestartDiscoveryRepository,
    )
    exposed = {
        name
        for port in ports
        for name, value in vars(port).items()
        if inspect.isfunction(value)
    }

    assert prohibited.isdisjoint(exposed)
