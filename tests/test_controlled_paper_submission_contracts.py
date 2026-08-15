from datetime import UTC, datetime
from dataclasses import asdict, fields, replace
from decimal import Decimal

import pytest

from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.fingerprints import command_payload_fingerprint
from volcanoes.application.execution.persistence import (
    DispatchClaimResult,
    DispatchClaimStatus,
)
from volcanoes.application.execution.persistence.contracts import (
    DispatchWinnerGrant,
    ExecutionDispatchClaimRecord,
    dispatch_capability_verifier,
)
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
)
from volcanoes.application.execution.submission import (
    ControlledPaperOrder,
    ControlledSubmissionRequest,
    ControlledSubmissionResult,
    ControlledSubmissionStatus,
    deterministic_client_order_id,
)

NOW = datetime(2026, 8, 14, tzinfo=UTC)
COMMAND_ID = PaperExecutionCommandId("pec-" + "1" * 64)
IDEMPOTENCY_KEY = PaperExecutionIdempotencyKey("pik-" + "2" * 64)
BROKER_REFERENCE = PaperBrokerOrderReference("pbr-" + "3" * 64)
AGGREGATE_ID = PaperExecutionAggregateId("pea-" + "4" * 64)
CORRELATION_ID = PaperExecutionCorrelationId("pcr-" + "5" * 64)


def claim(json_text: str | None = None) -> ExecutionDispatchClaimRecord:
    payload = {
        "asset_class": "equity",
        "currency": "USD",
        "mode": "PAPER",
        "operation": "SUBMIT",
        "order_type": "LIMIT",
        "quantity": "1.25",
        "side": "BUY",
        "symbol": "AAPL",
        "time_in_force": "DAY",
        "limit_price": "10.50",
    }
    text = canonical_json_text(payload) if json_text is None else json_text
    record = ExecutionDispatchClaimRecord(
        "claim-1",
        "submission-1",
        COMMAND_ID,
        AGGREGATE_ID,
        CORRELATION_ID,
        IDEMPOTENCY_KEY,
        5,
        "psq-" + "1" * 64,
        "pcm-" + "2" * 64,
        command_payload_fingerprint(payload),
        "pap-" + "3" * 64,
        "pps-" + "4" * 64,
        "paper-" + "a" * 42,
        dispatch_capability_verifier(b"x" * 32),
        text,
        2,
        NOW,
        4,
    )
    return replace(record, client_order_id=deterministic_client_order_id(record))


def test_public_request_contains_identity_only() -> None:
    request = ControlledSubmissionRequest("submission-1", COMMAND_ID, IDEMPOTENCY_KEY)
    assert set(request._primitive()) == {
        "submission_id",
        "command_id",
        "idempotency_key",
    }


def test_winner_capability_is_absent_from_broad_persistence_surface() -> None:
    import volcanoes.application.execution.persistence as persistence

    assert "DispatchWinnerGrant" not in persistence.__all__
    assert not hasattr(persistence, "DispatchWinnerGrant")
    assert "ExecutionDispatchClaimRecord" not in persistence.__all__
    assert not hasattr(persistence, "ExecutionDispatchClaimRecord")
    assert "winner_grant" not in ControlledSubmissionResult.__dataclass_fields__


def test_durable_verifier_cannot_reconstruct_winner_capability() -> None:
    durable = claim()
    forged = DispatchWinnerGrant(
        durable.claim_token, b"y" * 32, durable.record_fingerprint
    )
    assert not forged.authenticates(durable)


def test_public_claim_result_has_no_raw_capability_or_grant_surface() -> None:
    result = DispatchClaimResult(
        DispatchClaimStatus.EXACT_REPLAY, claim().to_public(), 4, "EXACT_CLAIM_REPLAY"
    )
    assert "winner_grant" not in {item.name for item in fields(result)}
    assert not _contains_bytes(asdict(result))
    assert "_capability" not in repr(result)
    assert "capability_verifier" not in repr(result)
    assert "capability_verifier" not in asdict(result)["claim"]
    assert "pcv-" not in repr(result)


def test_private_grant_repr_suppresses_raw_capability() -> None:
    durable = claim()
    capability = b"x" * 32
    grant = DispatchWinnerGrant(
        durable.claim_token, capability, durable.record_fingerprint
    )
    assert repr(capability) not in repr(grant)


def _contains_bytes(value: object) -> bool:
    if isinstance(value, bytes):
        return True
    if isinstance(value, dict):
        return any(_contains_bytes(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_contains_bytes(item) for item in value)
    return False


def test_order_is_derived_exactly_from_durable_canonical_command() -> None:
    durable = claim()
    order = ControlledPaperOrder.from_claim(durable.to_public())
    assert order.quantity == Decimal("1.25")
    assert order.limit_price == Decimal("10.50")
    assert order.client_order_id == deterministic_client_order_id(durable)
    assert len(order.client_order_id) == 48


def test_changed_durable_client_order_identity_fails_closed() -> None:
    durable = claim()
    with pytest.raises(Exception):
        ControlledPaperOrder.from_claim(
            replace(durable.to_public(), client_order_id="paper-" + "f" * 42)
        )


def test_duplicate_keys_and_noncanonical_json_are_rejected() -> None:
    with pytest.raises(Exception):
        ControlledPaperOrder.from_claim(
            claim('{"operation":"SUBMIT","operation":"SUBMIT"}').to_public()
        )
    with pytest.raises(Exception):
        ControlledPaperOrder.from_claim(claim('{ "operation": "SUBMIT" }').to_public())


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("side", "HOLD"),
        ("order_type", "PEGGED"),
        ("time_in_force", "IOC"),
        ("mode", "LIVE"),
        ("asset_class", "crypto"),
        ("currency", "EUR"),
        ("venue", "NASDAQ"),
    ),
)
def test_unsupported_order_variants_fail_closed(field: str, value: str) -> None:
    order = ControlledPaperOrder.from_claim(claim().to_public())
    with pytest.raises(Exception):
        replace(order, **{field: value})


def test_invalid_price_combinations_fail_closed() -> None:
    order = ControlledPaperOrder.from_claim(claim().to_public())
    with pytest.raises(Exception):
        replace(order, order_type="MARKET", limit_price=Decimal("10"))
    with pytest.raises(Exception):
        replace(order, order_type="LIMIT", limit_price=None)


def test_impossible_known_result_ambiguity_is_rejected() -> None:
    request = ControlledSubmissionRequest("submission-1", COMMAND_ID, IDEMPOTENCY_KEY)
    with pytest.raises(Exception):
        ControlledSubmissionResult(
            request.submission_id,
            request.request_fingerprint,
            ControlledSubmissionStatus.ACKNOWLEDGED,
            "ACK",
            broker_reference=BROKER_REFERENCE,
            dispatch_invoked=True,
            outcome_unknown=True,
            reconciliation_required=True,
            operator_action_required=True,
        )


def test_broker_conflict_result_binds_complete_owner_evidence() -> None:
    request = ControlledSubmissionRequest("submission-1", COMMAND_ID, IDEMPOTENCY_KEY)
    result = ControlledSubmissionResult(
        request.submission_id,
        request.request_fingerprint,
        ControlledSubmissionStatus.OUTCOME_UNKNOWN,
        "BROKER_REFERENCE_OWNERSHIP_CONFLICT",
        broker_reference=BROKER_REFERENCE,
        dispatch_invoked=True,
        outcome_unknown=True,
        reconciliation_required=True,
        operator_action_required=True,
        conflicting_owner_aggregate_id=AGGREGATE_ID,
        conflicting_owner_command_id=COMMAND_ID,
        conflicting_owner_record_fingerprint="pbf-" + "6" * 64,
    )
    assert result.conflicting_owner_aggregate_id == AGGREGATE_ID
    assert result.conflicting_owner_command_id == COMMAND_ID
    altered = replace(result, conflicting_owner_record_fingerprint="pbf-" + "7" * 64)
    assert altered.result_fingerprint != result.result_fingerprint


def test_partial_broker_conflict_owner_evidence_is_rejected() -> None:
    request = ControlledSubmissionRequest("submission-1", COMMAND_ID, IDEMPOTENCY_KEY)
    with pytest.raises(Exception):
        ControlledSubmissionResult(
            request.submission_id,
            request.request_fingerprint,
            ControlledSubmissionStatus.OUTCOME_UNKNOWN,
            "BROKER_REFERENCE_OWNERSHIP_CONFLICT",
            broker_reference=BROKER_REFERENCE,
            dispatch_invoked=True,
            outcome_unknown=True,
            reconciliation_required=True,
            operator_action_required=True,
            conflicting_owner_aggregate_id=AGGREGATE_ID,
        )
