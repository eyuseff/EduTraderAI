from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.fingerprints import (
    command_payload_fingerprint,
)
from volcanoes.application.execution.persistence import (
    DispatchClaimResult,
    DispatchClaimStatus,
    ExecutionDispatchAuthorizationRecord,
    ExecutionDispatchControlRecord,
    ExecutionAggregateRecord,
    ExecutionPersistenceResultStatus,
    RecordLoadResult,
    UnitOfWorkCommitResult,
)
from volcanoes.application.execution.persistence.contracts import (
    ExecutionDispatchClaimRecord,
    dispatch_capability_verifier,
)
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionCorrelationId,
    PaperExecutionRevision,
    PaperBrokerOrderReference,
    PaperExecutionCommandId,
    PaperExecutionIdempotencyKey,
)
from volcanoes.application.execution.lifecycle import PaperExecutionLifecycleState
from volcanoes.application.execution.submission import (
    ControlledPaperSubmissionService,
    ControlledSubmissionRequest,
    ControlledSubmissionStatus,
    deterministic_client_order_id,
    PaperDispatchObservation,
)

NOW = datetime(2026, 8, 14, tzinfo=UTC)
COMMAND_ID = PaperExecutionCommandId("pec-" + "1" * 64)
IDEMPOTENCY_KEY = PaperExecutionIdempotencyKey("pik-" + "2" * 64)
BROKER_REFERENCE = PaperBrokerOrderReference("pbr-" + "3" * 64)
AGGREGATE_ID = PaperExecutionAggregateId("pea-" + "4" * 64)
CORRELATION_ID = PaperExecutionCorrelationId("pcr-" + "5" * 64)


def durable_claim(request):
    payload = {
        "asset_class": "equity",
        "currency": "USD",
        "mode": "PAPER",
        "operation": "SUBMIT",
        "order_type": "MARKET",
        "quantity": "1",
        "side": "BUY",
        "symbol": "AAPL",
        "time_in_force": "DAY",
    }
    record = ExecutionDispatchClaimRecord(
        "claim-1",
        request.submission_id,
        request.command_id,
        AGGREGATE_ID,
        CORRELATION_ID,
        request.idempotency_key,
        PaperExecutionRevision(5),
        request.request_fingerprint,
        "pcm-" + "2" * 64,
        command_payload_fingerprint(payload),
        "pap-" + "3" * 64,
        "pps-" + "4" * 64,
        "paper-" + "a" * 42,
        dispatch_capability_verifier(b"x" * 32),
        canonical_json_text(payload),
        1,
        NOW,
        4,
    )
    return replace(record, client_order_id=deterministic_client_order_id(record))


class Repo:
    def __init__(self):
        self.claim = None
        self.auth = None
        self.resolution = None
        self.stop = False
        self.references = {}
        self.write_set = None
        self.aggregate = ExecutionAggregateRecord(
            AGGREGATE_ID,
            CORRELATION_ID,
            PaperExecutionLifecycleState.DISPATCH_PENDING,
            PaperExecutionRevision(5),
            Decimal("0"),
            False,
            False,
            False,
            False,
            "PX-TRN-008",
            NOW,
            NOW,
            4,
            requested_quantity=Decimal("1"),
            last_command_id=COMMAND_ID,
            last_idempotency_key=IDEMPOTENCY_KEY,
        )

    def unit_of_work(self):
        return Unit(self)

    def acquire_and_authorize_dispatch(self, attempt, *, claimed_at, authorized_at):
        with self.unit_of_work() as first:
            result = first.acquire(attempt, claimed_at=claimed_at)
            if result.status is not DispatchClaimStatus.ACQUIRED:
                first.rollback()
                return result
            if not first.commit().committed:
                return DispatchClaimResult(
                    DispatchClaimStatus.BLOCKED, None, 4, "CLAIM_COMMIT_FAILED"
                )
        with self.unit_of_work() as second:
            control = second.get()
            if not control.permits_dispatch:
                second.rollback()
                return DispatchClaimResult(
                    DispatchClaimStatus.BLOCKED,
                    result.claim,
                    4,
                    "FINAL_GUARD_BLOCKED",
                )
            authorization = ExecutionDispatchAuthorizationRecord(
                result.claim.claim_token,
                result.claim.control_generation,
                authorized_at,
                4,
            )
            self.auth = authorization
            if not second.commit().committed:
                return DispatchClaimResult(
                    DispatchClaimStatus.BLOCKED,
                    result.claim,
                    4,
                    "FINAL_GUARD_BLOCKED",
                )
            return replace(
                result,
                reason_code="AUTHORIZED_WINNER",
                authorized=True,
                authorization=authorization,
                aggregate=self.aggregate,
            )


class Unit:
    def __init__(self, owner):
        self.owner = owner
        self.dispatch_claims = self
        self.dispatch_control = self
        self.dispatch_authorizations = Auth(owner)
        self.dispatch_resolutions = Resolution(owner)
        self.broker_references = References(owner)
        self.aggregates = self
        self.receipts = Evidence()
        self.failures = Evidence()
        self.transitions = Evidence()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def acquire(self, attempt, *, claimed_at):
        if self.owner.claim is not None:
            return DispatchClaimResult(
                DispatchClaimStatus.EXACT_REPLAY,
                self.owner.claim.to_public(),
                4,
                "EXACT_CLAIM_REPLAY",
            )
        claim = durable_claim(
            ControlledSubmissionRequest(
                attempt.submission_id,
                attempt.command_id,
                attempt.idempotency_key,
            )
        )
        self.owner.claim = claim
        return DispatchClaimResult(
            DispatchClaimStatus.ACQUIRED, claim.to_public(), 4, "CLAIM_ACQUIRED"
        )

    def get(self, key=None):
        if key is not None:
            return self.owner.claim
        return ExecutionDispatchControlRecord(True, self.owner.stop, False, 1, NOW, 4)

    def load_record(self, key):
        return self.owner.aggregate

    def save(self, record, *, expected_revision):
        self.owner.aggregate = record
        return SimpleNamespace(status=ExecutionPersistenceResultStatus.SAVED)

    def commit(self):
        return UnitOfWorkCommitResult(ExecutionPersistenceResultStatus.SAVED, True, 4)

    def rollback(self):
        pass

    def record_dispatch_outcome(self, write_set):
        self.owner.write_set = write_set
        self.owner.aggregate = write_set.aggregate
        self.owner.resolution = write_set.resolution
        if write_set.broker_reference is not None:
            self.owner.references[str(write_set.broker_reference.broker_reference)] = (
                write_set.broker_reference
            )
        return RecordLoadResult(ExecutionPersistenceResultStatus.CREATED, 4)


class Auth:
    def __init__(self, o):
        self.o = o

    def get(self, key):
        return self.o.auth

    def record(self, r):
        self.o.auth = r
        return RecordLoadResult(
            ExecutionPersistenceResultStatus.CREATED, 4, r.record_fingerprint
        )


class Resolution:
    def __init__(self, o):
        self.o = o

    def get(self, key):
        return self.o.resolution

    def record(self, r):
        self.o.resolution = r
        return RecordLoadResult(
            ExecutionPersistenceResultStatus.CREATED, 4, r.record_fingerprint
        )


class References:
    def __init__(self, o):
        self.o = o

    def register(self, r):
        self.o.references[str(r.broker_reference)] = r
        return RecordLoadResult(
            ExecutionPersistenceResultStatus.CREATED, 4, r.record_fingerprint
        )


class Evidence:
    def record(self, record):
        return SimpleNamespace(status=ExecutionPersistenceResultStatus.CREATED)

    def append(self, record):
        return SimpleNamespace(status=ExecutionPersistenceResultStatus.APPENDED)


def test_one_winner_invokes_exact_durable_order_and_replay_never_dispatches() -> None:
    repo = Repo()
    seen = []
    request = ControlledSubmissionRequest("submission-1", COMMAND_ID, IDEMPOTENCY_KEY)

    def dispatch(order):
        seen.append(order)
        return PaperDispatchObservation("submission-1", BROKER_REFERENCE, True, "ACK")

    first = ControlledPaperSubmissionService(
        repo, dispatch, clock=lambda: NOW
    ).apply_once(request)
    second = ControlledPaperSubmissionService(
        repo, dispatch, clock=lambda: NOW
    ).apply_once(request)
    assert first.status is ControlledSubmissionStatus.ACKNOWLEDGED
    assert first.broker_reference == BROKER_REFERENCE
    assert second.status is ControlledSubmissionStatus.ACKNOWLEDGED
    assert (
        len(seen) == 1
        and seen[0].symbol == "AAPL"
        and seen[0].quantity.as_tuple().digits == (1,)
    )


def test_stop_between_claim_and_authorization_blocks_effect_and_keeps_claim() -> None:
    repo = Repo()
    seen = []
    request = ControlledSubmissionRequest("submission-1", COMMAND_ID, IDEMPOTENCY_KEY)
    original = repo.unit_of_work
    calls = 0

    def units():
        nonlocal calls
        calls += 1
        if calls == 2:
            repo.stop = True
        return original()

    repo.unit_of_work = units
    result = ControlledPaperSubmissionService(
        repo, lambda order: seen.append(order), clock=lambda: NOW
    ).apply_once(request)
    assert (
        result.status is ControlledSubmissionStatus.BLOCKED
        and seen == []
        and repo.claim is not None
        and repo.aggregate.lifecycle_state
        is PaperExecutionLifecycleState.DISPATCH_PENDING
        and repo.resolution is None
    )


def _valid_acknowledged_write_set():
    repo = Repo()
    request = ControlledSubmissionRequest("submission-1", COMMAND_ID, IDEMPOTENCY_KEY)
    result = ControlledPaperSubmissionService(
        repo,
        lambda order: PaperDispatchObservation(
            "submission-1", BROKER_REFERENCE, True, "ACK"
        ),
        clock=lambda: NOW,
    ).apply_once(request)
    assert result.status is ControlledSubmissionStatus.ACKNOWLEDGED
    assert repo.write_set is not None
    return repo.write_set


def test_outcome_contract_rejects_missing_reordered_duplicated_and_surplus_edges() -> (
    None
):
    write_set = _valid_acknowledged_write_set()
    first, final = write_set.transitions
    for transitions in (
        (final,),
        (final, first),
        (first, first),
        (first, final, final),
    ):
        with pytest.raises(Exception):
            replace(write_set, transitions=transitions)


def test_outcome_contract_rejects_wrong_start_identity_and_evidence_placement() -> None:
    write_set = _valid_acknowledged_write_set()
    first, final = write_set.transitions
    mutations = (
        replace(first, command_id=PaperExecutionCommandId("pec-" + "9" * 64)),
        replace(first, transition_id="PX-TRN-010"),
        replace(first, receipt_fingerprint=write_set.resolution.evidence_fingerprint),
        replace(final, transition_record_id="forged-transition-record"),
    )
    for changed in mutations:
        with pytest.raises(Exception):
            replace(write_set, transitions=(changed, final))


def test_outcome_contract_binds_claim_revision_and_dispatch_pending_start() -> None:
    write_set = _valid_acknowledged_write_set()
    first, final = write_set.transitions
    with pytest.raises(Exception):
        replace(write_set, expected_revision=PaperExecutionRevision(4))
    with pytest.raises(Exception):
        replace(
            write_set,
            transitions=(
                replace(
                    first, source_state=PaperExecutionLifecycleState.READY_FOR_DISPATCH
                ),
                final,
            ),
        )
