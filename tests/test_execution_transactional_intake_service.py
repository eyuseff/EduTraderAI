from __future__ import annotations

from copy import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from volcanoes.application.execution import (
    ExecutionAggregateRecord,
    ExecutionApprovalRecord,
    ExecutionCommandProcessingOutcome,
    ExecutionCommandRecord,
    ExecutionIdempotencyRecord,
    ExecutionIdempotencyReservationStatus,
    ExecutionPersistenceResultStatus,
    ExecutionReplayKind,
    ExecutionTransitionRecord,
    InMemoryExecutionPersistence,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionLifecycleState,
    PaperExecutionOperation,
    PaperExecutionRevision,
    TransactionalExecutionIntakeService,
    TransactionalIntakeRequest,
    TransactionalIntakeResult,
    TransactionalIntakeStatus,
)
from volcanoes.application.execution.fingerprints import (
    approval_fingerprint,
    command_payload_fingerprint,
    fingerprint_payload,
    policy_fingerprint,
)

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
SCHEMA_VERSION = 1


def _request(seed: str = "AAPL", *, payload_seed: str | None = None):
    aggregate_id = PaperExecutionAggregateId.from_seed("aggregate", seed)
    command_id = PaperExecutionCommandId.from_seed("command", seed)
    correlation_id = PaperExecutionCorrelationId.from_seed("correlation", seed)
    idempotency_key = PaperExecutionIdempotencyKey.from_seed("idempotency", seed)
    payload = {"operation": "SUBMIT", "quantity": "1", "symbol": payload_seed or seed}
    command = ExecutionCommandRecord(
        command_id=command_id,
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        operation=PaperExecutionOperation.SUBMIT,
        expected_execution_revision=PaperExecutionRevision.initial(),
        canonical_payload_fingerprint=command_payload_fingerprint(payload),
        canonical_command_json=(
            '{"operation":"SUBMIT","quantity":"1","symbol":"%s"}'
            % (payload_seed or seed)
        ),
        approval_fingerprint=approval_fingerprint(("approval", seed)),
        policy_fingerprint=policy_fingerprint(("policy", seed)),
        received_at=NOW,
        processing_outcome=ExecutionCommandProcessingOutcome.PENDING,
        schema_version=SCHEMA_VERSION,
    )
    reservation = ExecutionIdempotencyRecord(
        idempotency_key=idempotency_key,
        logical_operation_fingerprint=fingerprint_payload("plo", payload),
        command_id=command_id,
        aggregate_id=aggregate_id,
        reservation_status=ExecutionIdempotencyReservationStatus.RESERVED,
        created_at=NOW,
        schema_version=SCHEMA_VERSION,
    )
    approval = ExecutionApprovalRecord(
        approval_fingerprint=command.approval_fingerprint,
        bound_fingerprint=command.canonical_payload_fingerprint,
        approval_kind="OPERATOR_CONFIRMED",
        approver_safe_reference=f"operator-{seed}",
        approved_at=NOW,
        recorded_at=NOW,
        schema_version=SCHEMA_VERSION,
    )
    states = (
        (
            "PX-TRN-002",
            PaperExecutionLifecycleState.CREATED,
            PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
            PaperExecutionLifecycleInputType.RECORD_ELIGIBILITY,
        ),
        (
            "PX-TRN-005",
            PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
            PaperExecutionLifecycleState.APPROVAL_CONFIRMED,
            PaperExecutionLifecycleInputType.RECORD_APPROVAL,
        ),
        (
            "PX-TRN-006",
            PaperExecutionLifecycleState.APPROVAL_CONFIRMED,
            PaperExecutionLifecycleState.IDEMPOTENCY_RESERVED,
            PaperExecutionLifecycleInputType.RECORD_IDEMPOTENCY_RESERVATION,
        ),
        (
            "PX-TRN-007",
            PaperExecutionLifecycleState.IDEMPOTENCY_RESERVED,
            PaperExecutionLifecycleState.READY_FOR_DISPATCH,
            PaperExecutionLifecycleInputType.PREPARE_DISPATCH,
        ),
        (
            "PX-TRN-008",
            PaperExecutionLifecycleState.READY_FOR_DISPATCH,
            PaperExecutionLifecycleState.DISPATCH_PENDING,
            PaperExecutionLifecycleInputType.RECORD_DISPATCH_PENDING,
        ),
    )
    transitions = tuple(
        ExecutionTransitionRecord(
            transition_record_id=f"intake-{seed}-{number}",
            aggregate_id=aggregate_id,
            transition_id=transition_id,
            source_state=source,
            destination_state=destination,
            previous_revision=PaperExecutionRevision(number - 1),
            next_revision=PaperExecutionRevision(number),
            lifecycle_input_kind=input_kind,
            input_identity=f"input-{seed}-{number}",
            command_id=command_id,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            replay_indicator=ExecutionReplayKind.NONE,
            side_effect_intent_kinds=(
                (
                    PaperExecutionLifecycleSideEffectIntentKind.WOULD_DISPATCH
                    if destination is PaperExecutionLifecycleState.DISPATCH_PENDING
                    else PaperExecutionLifecycleSideEffectIntentKind.NONE
                ),
            ),
            evidence_intent_kinds=(
                PaperExecutionLifecycleEvidenceIntentKind.LIFECYCLE_TRANSITION_ACCEPTED,
            ),
            safe_reason_code=input_kind.value,
            recorded_at=NOW + timedelta(seconds=number),
            schema_version=SCHEMA_VERSION,
        )
        for number, (transition_id, source, destination, input_kind) in enumerate(
            states, 1
        )
    )
    aggregate = ExecutionAggregateRecord(
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        lifecycle_state=PaperExecutionLifecycleState.DISPATCH_PENDING,
        execution_revision=PaperExecutionRevision(5),
        cumulative_filled_quantity=Decimal("0"),
        outcome_unknown=False,
        reconciliation_required=False,
        command_terminal=False,
        aggregate_terminal=False,
        last_transition_id="PX-TRN-008",
        created_at=NOW,
        updated_at=NOW + timedelta(seconds=5),
        schema_version=SCHEMA_VERSION,
        requested_quantity=Decimal("1"),
        last_command_id=command_id,
        last_idempotency_key=idempotency_key,
    )
    return TransactionalIntakeRequest(
        command=command,
        idempotency=reservation,
        approval=approval,
        aggregate=aggregate,
        transitions=transitions,
        expected_revision=PaperExecutionRevision.initial(),
    )


def test_intake_atomically_commits_durable_dispatch_handoff() -> None:
    persistence = InMemoryExecutionPersistence()
    result = TransactionalExecutionIntakeService(persistence).intake(_request())

    assert result.status is TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH
    assert result.committed is True
    assert result.durable_dispatch_intent is True
    snapshot = persistence.snapshot()
    assert len(snapshot.command_records()) == 1
    assert len(snapshot.idempotency_records()) == 1
    assert len(snapshot.approval_records()) == 1
    assert len(snapshot.transition_records()) == 5
    assert (
        snapshot.aggregate_records()[0].lifecycle_state
        is PaperExecutionLifecycleState.DISPATCH_PENDING
    )


def test_exact_replay_does_not_create_new_transitions() -> None:
    persistence = InMemoryExecutionPersistence()
    service = TransactionalExecutionIntakeService(persistence)
    request = _request()
    service.intake(request)

    replay = service.intake(request)

    assert replay.status is TransactionalIntakeStatus.EXACT_REPLAY
    assert replay.committed is False
    assert replay.durable_dispatch_intent is False
    assert len(persistence.snapshot().transition_records()) == 5


def test_command_payload_conflict_rolls_back_without_residue() -> None:
    persistence = InMemoryExecutionPersistence()
    service = TransactionalExecutionIntakeService(persistence)
    service.intake(_request())

    conflict = service.intake(_request(payload_seed="MSFT"))

    assert conflict.status is TransactionalIntakeStatus.COMMAND_CONFLICT
    snapshot = persistence.snapshot()
    assert len(snapshot.command_records()) == 1
    assert len(snapshot.idempotency_records()) == 1
    assert len(snapshot.transition_records()) == 5


def test_same_logical_operation_with_new_command_is_a_non_mutating_replay() -> None:
    persistence = InMemoryExecutionPersistence()
    service = TransactionalExecutionIntakeService(persistence)
    original = _request()
    service.intake(original)
    new_command_id = PaperExecutionCommandId.from_seed("command", "AAPL-retry")
    replay = TransactionalIntakeRequest(
        command=replace(original.command, command_id=new_command_id),
        idempotency=replace(original.idempotency, command_id=new_command_id),
        approval=original.approval,
        aggregate=replace(original.aggregate, last_command_id=new_command_id),
        transitions=tuple(
            replace(transition, command_id=new_command_id)
            for transition in original.transitions
        ),
        expected_revision=original.expected_revision,
    )

    result = service.intake(replay)

    assert result.status is TransactionalIntakeStatus.LOGICAL_REPLAY
    snapshot = persistence.snapshot()
    assert len(snapshot.command_records()) == 1
    assert len(snapshot.transition_records()) == 5


def test_request_requires_a_durable_dispatch_pending_transition() -> None:
    request = _request()
    with pytest.raises(ValueError, match="dispatch intent"):
        TransactionalIntakeRequest(
            command=request.command,
            idempotency=request.idempotency,
            approval=request.approval,
            aggregate=request.aggregate,
            transitions=(
                *request.transitions[:-1],
                __import__("dataclasses").replace(
                    request.transitions[-1],
                    side_effect_intent_kinds=(
                        PaperExecutionLifecycleSideEffectIntentKind.NONE,
                    ),
                ),
            ),
            expected_revision=request.expected_revision,
        )


def _rebuild(request, **changes):
    values = {
        "command": request.command,
        "idempotency": request.idempotency,
        "approval": request.approval,
        "aggregate": request.aggregate,
        "transitions": request.transitions,
        "expected_revision": request.expected_revision,
    }
    values.update(changes)
    return TransactionalIntakeRequest(**values)


def test_approval_exact_replay_is_accepted_without_duplication() -> None:
    persistence = InMemoryExecutionPersistence()
    request = _request()
    with persistence.unit_of_work() as unit:
        assert (
            unit.approvals.record(request.approval).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        unit.commit()

    result = TransactionalExecutionIntakeService(persistence).intake(request)

    assert result.status is TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH
    assert len(persistence.snapshot().approval_records()) == 1


def test_approval_content_conflict_rolls_back_every_staged_record() -> None:
    persistence = InMemoryExecutionPersistence()
    request = _request()
    conflicting = replace(request.approval, approver_safe_reference="other-operator")
    with persistence.unit_of_work() as unit:
        unit.approvals.record(conflicting)
        unit.commit()

    result = TransactionalExecutionIntakeService(persistence).intake(request)

    assert result.status is TransactionalIntakeStatus.COMMAND_CONFLICT
    snapshot = persistence.snapshot()
    assert len(snapshot.command_records()) == 0
    assert len(snapshot.idempotency_records()) == 0
    assert len(snapshot.aggregate_records()) == 0
    assert len(snapshot.transition_records()) == 0
    assert snapshot.approval_records() == (conflicting,)


@pytest.mark.parametrize(
    "approval_change, message",
    (
        ({"approval_fingerprint": approval_fingerprint(("other",))}, "fingerprint"),
        ({"bound_fingerprint": command_payload_fingerprint(("other",))}, "bind"),
    ),
)
def test_missing_or_mismatched_approval_evidence_is_rejected(
    approval_change, message
) -> None:
    request = _request()
    with pytest.raises(ValueError, match=message):
        _rebuild(request, approval=replace(request.approval, **approval_change))


@pytest.mark.parametrize(
    "mutator, message",
    (
        (
            lambda r: (
                replace(
                    r.transitions[0],
                    source_state=PaperExecutionLifecycleState.APPROVAL_CONFIRMED,
                ),
                *r.transitions[1:],
            ),
            "source",
        ),
        (
            lambda r: (
                replace(
                    r.transitions[0],
                    destination_state=PaperExecutionLifecycleState.APPROVAL_CONFIRMED,
                ),
                *r.transitions[1:],
            ),
            "noncanonical",
        ),
        (
            lambda r: (
                replace(
                    r.transitions[0],
                    lifecycle_input_kind=PaperExecutionLifecycleInputType.RECORD_APPROVAL,
                ),
                *r.transitions[1:],
            ),
            "noncanonical",
        ),
        (
            lambda r: (r.transitions[1], r.transitions[0], *r.transitions[2:]),
            "source|noncanonical|revisions",
        ),
        (lambda r: r.transitions[:-1], "exact initial chain"),
        (lambda r: (*r.transitions, r.transitions[-1]), "exact initial chain"),
        (
            lambda r: (
                r.transitions[0],
                replace(
                    r.transitions[1],
                    previous_revision=PaperExecutionRevision(3),
                    next_revision=PaperExecutionRevision(4),
                ),
                *r.transitions[2:],
            ),
            "revisions",
        ),
    ),
)
def test_malformed_initial_chains_are_rejected(mutator, message) -> None:
    request = _request()
    with pytest.raises(ValueError, match=message):
        _rebuild(request, transitions=tuple(mutator(request)))


def test_nonzero_expected_revision_is_rejected() -> None:
    request = _request()
    with pytest.raises(ValueError, match="revision zero"):
        _rebuild(request, expected_revision=PaperExecutionRevision(1))


@pytest.mark.parametrize(
    "state, revision",
    (
        (PaperExecutionLifecycleState.CREATED, PaperExecutionRevision.initial()),
        (
            PaperExecutionLifecycleState.APPROVAL_CONFIRMED,
            PaperExecutionRevision.initial(),
        ),
    ),
)
def test_preexisting_aggregate_blocks_intake_and_rolls_back_staged_records(
    state, revision
) -> None:
    persistence = InMemoryExecutionPersistence()
    request = _request()
    existing = replace(
        request.aggregate,
        lifecycle_state=state,
        execution_revision=revision,
        last_transition_id="existing-state",
    )
    with persistence.unit_of_work() as unit:
        unit.aggregates.save(
            existing, expected_revision=PaperExecutionRevision.initial()
        )
        unit.commit()

    result = TransactionalExecutionIntakeService(persistence).intake(request)

    assert result.status is TransactionalIntakeStatus.STALE_REVISION
    snapshot = persistence.snapshot()
    assert snapshot.aggregate_records() == (existing,)
    assert snapshot.command_records() == ()
    assert snapshot.idempotency_records() == ()
    assert snapshot.transition_records() == ()


@pytest.mark.parametrize(
    "changes",
    (
        {"committed": False},
        {"durable_dispatch_intent": False},
        {"final_revision": None},
        {"status": TransactionalIntakeStatus.STALE_REVISION, "committed": True},
        {
            "status": TransactionalIntakeStatus.STALE_REVISION,
            "durable_dispatch_intent": True,
        },
        {"status": TransactionalIntakeStatus.STALE_REVISION, "final_revision": 5},
    ),
)
def test_result_rejects_impossible_combinations(changes) -> None:
    values = {
        "status": TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH,
        "committed": True,
        "command_id": "command",
        "aggregate_id": "aggregate",
        "final_revision": 5,
        "durable_dispatch_intent": True,
        "source_result_fingerprint": "source",
    }
    values.update(changes)
    with pytest.raises(ValueError):
        TransactionalIntakeResult(**values)


@pytest.mark.parametrize(
    "canonical_json",
    (
        "{",
        "[]",
        '{"symbol":"AAPL","symbol":"MSFT"}',
        '{"quantity":NaN}',
        '{ "operation": "SUBMIT" }',
    ),
)
def test_malformed_or_noncanonical_command_json_is_rejected(canonical_json) -> None:
    request = _request()
    with pytest.raises(ValueError, match="JSON|canonical"):
        _rebuild(
            request,
            command=replace(request.command, canonical_command_json=canonical_json),
        )


def test_command_payload_fingerprint_mismatch_is_rejected() -> None:
    request = _request()
    with pytest.raises(ValueError, match="Command payload fingerprint"):
        _rebuild(
            request,
            command=replace(
                request.command,
                canonical_payload_fingerprint=command_payload_fingerprint(
                    {"operation": "SUBMIT", "quantity": "2", "symbol": "AAPL"}
                ),
            ),
        )


def test_idempotency_logical_fingerprint_mismatch_is_rejected() -> None:
    request = _request()
    with pytest.raises(ValueError, match="Idempotency logical-operation"):
        _rebuild(
            request,
            idempotency=replace(
                request.idempotency,
                logical_operation_fingerprint=fingerprint_payload(
                    "plo", {"different": True}
                ),
            ),
        )


def test_coordinated_revision_jump_chain_is_rejected() -> None:
    request = _request()
    shifted = (
        *request.transitions[:2],
        replace(
            request.transitions[2],
            previous_revision=PaperExecutionRevision(3),
            next_revision=PaperExecutionRevision(4),
        ),
        replace(
            request.transitions[3],
            previous_revision=PaperExecutionRevision(4),
            next_revision=PaperExecutionRevision(5),
        ),
        replace(
            request.transitions[4],
            previous_revision=PaperExecutionRevision(5),
            next_revision=PaperExecutionRevision(6),
        ),
    )
    with pytest.raises(ValueError, match="revisions"):
        _rebuild(
            request,
            transitions=shifted,
            aggregate=replace(
                request.aggregate, execution_revision=PaperExecutionRevision(6)
            ),
        )


def test_final_revision_other_than_five_is_rejected() -> None:
    request = _request()
    final = copy(request.transitions[-1])
    object.__setattr__(final, "next_revision", PaperExecutionRevision(6))
    with pytest.raises(ValueError, match="exactly one|revision five"):
        _rebuild(
            request,
            transitions=(*request.transitions[:-1], final),
            aggregate=replace(
                request.aggregate, execution_revision=PaperExecutionRevision(6)
            ),
        )


@pytest.mark.parametrize("transition_index", (0, 1, 2, 3))
def test_misplaced_side_effect_intent_is_rejected(transition_index) -> None:
    request = _request()
    transitions = list(request.transitions)
    transitions[transition_index] = replace(
        transitions[transition_index],
        side_effect_intent_kinds=(
            PaperExecutionLifecycleSideEffectIntentKind.WOULD_DISPATCH,
        ),
    )
    with pytest.raises(ValueError, match="Only the final"):
        _rebuild(request, transitions=tuple(transitions))


def test_additional_final_side_effect_intent_is_rejected() -> None:
    request = _request()
    transitions = (
        *request.transitions[:-1],
        replace(
            request.transitions[-1],
            side_effect_intent_kinds=(
                PaperExecutionLifecycleSideEffectIntentKind.WOULD_DISPATCH,
                PaperExecutionLifecycleSideEffectIntentKind.WOULD_NOTIFY_OPERATOR,
            ),
        ),
    )
    with pytest.raises(ValueError, match="dispatch intent"):
        _rebuild(request, transitions=transitions)


def test_command_and_request_revision_mismatch_is_rejected() -> None:
    request = _request()
    with pytest.raises(ValueError, match="expected revisions"):
        _rebuild(
            request,
            command=replace(
                request.command,
                expected_execution_revision=PaperExecutionRevision(1),
            ),
        )


@pytest.mark.parametrize(
    "category",
    ("command", "idempotency", "approval", "aggregate", "transition"),
)
def test_schema_mismatch_for_every_record_category_is_rejected(category) -> None:
    request = _request()
    changes = {}
    if category == "command":
        changes["command"] = replace(request.command, schema_version=2)
    elif category == "idempotency":
        changes["idempotency"] = replace(request.idempotency, schema_version=2)
    elif category == "approval":
        changes["approval"] = replace(request.approval, schema_version=2)
    elif category == "aggregate":
        changes["aggregate"] = replace(request.aggregate, schema_version=2)
    else:
        changes["transitions"] = (
            replace(request.transitions[0], schema_version=2),
            *request.transitions[1:],
        )
    with pytest.raises(ValueError, match="schema version"):
        _rebuild(request, **changes)


def test_nonzero_initial_cumulative_fill_is_rejected() -> None:
    request = _request()
    with pytest.raises(ValueError, match="zero cumulative"):
        _rebuild(
            request,
            aggregate=replace(
                request.aggregate, cumulative_filled_quantity=Decimal("1")
            ),
        )
