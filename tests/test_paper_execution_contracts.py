from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from volcanoes.application.execution import (
    PaperExecutionAggregateId,
    PaperExecutionApproval,
    PaperExecutionApprovalKind,
    PaperExecutionCommand,
    PaperExecutionCommandId,
    PaperExecutionContext,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionInstrument,
    PaperExecutionIntent,
    PaperExecutionInvariantError,
    PaperExecutionMode,
    PaperExecutionOperation,
    PaperExecutionOrderType,
    PaperExecutionPolicySnapshot,
    PaperExecutionRevision,
    PaperExecutionSide,
)


def ids() -> tuple[
    PaperExecutionAggregateId,
    PaperExecutionCorrelationId,
    PaperExecutionCommandId,
    PaperExecutionIdempotencyKey,
]:
    aggregate = PaperExecutionAggregateId.from_seed("aggregate", "AAPL")
    correlation = PaperExecutionCorrelationId.from_seed("correlation", "AAPL")
    command = PaperExecutionCommandId.from_seed("command", "AAPL")
    key = PaperExecutionIdempotencyKey.from_seed(
        aggregate,
        PaperExecutionOperation.SUBMIT,
        PaperExecutionRevision.initial(),
        {"symbol": "AAPL"},
    )
    return aggregate, correlation, command, key


def instrument(symbol: str = "aapl") -> PaperExecutionInstrument:
    return PaperExecutionInstrument(symbol)


def intent(
    order_type: PaperExecutionOrderType = PaperExecutionOrderType.LIMIT,
) -> PaperExecutionIntent:
    kwargs: dict[str, object] = {}
    if order_type is PaperExecutionOrderType.LIMIT:
        kwargs["limit_price"] = Decimal("100")
    if order_type is PaperExecutionOrderType.STOP:
        kwargs["stop_price"] = Decimal("90")
    if order_type is PaperExecutionOrderType.STOP_LIMIT:
        kwargs["limit_price"] = Decimal("100")
        kwargs["stop_price"] = Decimal("90")
    return PaperExecutionIntent(
        instrument=instrument(),
        side=PaperExecutionSide.BUY,
        order_type=order_type,
        quantity=Decimal("1.00"),
        **kwargs,
    )


def approval(bound: str = "pcf-" + ("1" * 64)) -> PaperExecutionApproval:
    return PaperExecutionApproval(
        approval_kind=PaperExecutionApprovalKind.OPERATOR,
        approver_reference="operator.primary",
        approval_reference="approval-1",
        bound_fingerprint=bound,
        approved_at=datetime(2026, 7, 30, tzinfo=UTC),
        expires_at=datetime(2026, 7, 31, tzinfo=UTC),
    )


def policy() -> PaperExecutionPolicySnapshot:
    return PaperExecutionPolicySnapshot(
        policy_version="paper-v1",
        allowed_operations=(
            PaperExecutionOperation.REPLACE,
            PaperExecutionOperation.SUBMIT,
            PaperExecutionOperation.SUBMIT,
            PaperExecutionOperation.CANCEL,
        ),
    )


def context() -> PaperExecutionContext:
    aggregate, correlation, _, _ = ids()
    return PaperExecutionContext(
        aggregate_id=aggregate,
        correlation_id=correlation,
        source_component="manual.paper",
        requested_at=datetime(2026, 7, 30, tzinfo=UTC),
        metadata=(("trace", "safe"),),
    )


def command(
    operation: PaperExecutionOperation = PaperExecutionOperation.SUBMIT,
) -> PaperExecutionCommand:
    aggregate, correlation, command_id, key = ids()
    ctx = PaperExecutionContext(
        aggregate_id=aggregate,
        correlation_id=correlation,
        source_component="manual.paper",
        requested_at=datetime(2026, 7, 30, tzinfo=UTC),
    )
    return PaperExecutionCommand(
        command_id=command_id,
        aggregate_id=aggregate,
        correlation_id=correlation,
        idempotency_key=key,
        operation=operation,
        expected_execution_revision=PaperExecutionRevision.initial(),
        approval=approval(),
        policy_snapshot=policy(),
        context=ctx,
        intent=(intent() if operation is PaperExecutionOperation.SUBMIT else None),
        replacement_intent=(
            intent() if operation is PaperExecutionOperation.REPLACE else None
        ),
    )


def test_paper_only_mode_has_no_live_or_production_member() -> None:
    assert PaperExecutionMode.PAPER.value == "PAPER"
    assert "LIVE" not in PaperExecutionMode.__members__
    assert "PRODUCTION" not in PaperExecutionMode.__members__
    with pytest.raises(ValueError):
        PaperExecutionMode("LIVE")


def test_instrument_normalization_invariants_and_immutability() -> None:
    item = PaperExecutionInstrument(" aapl ", venue="NASDAQ")

    assert item.symbol == "AAPL"
    assert item.asset_class == "equity"
    assert item.currency == "USD"
    assert item.to_primitive()["symbol"] == "AAPL"
    with pytest.raises(FrozenInstanceError):
        item.symbol = "MSFT"  # type: ignore[misc]


@pytest.mark.parametrize("symbol", ("", " ", "AAPL$", "x" * 17))
def test_instrument_rejects_unsafe_symbols(symbol: str) -> None:
    with pytest.raises(PaperExecutionInvariantError):
        PaperExecutionInstrument(symbol)


@pytest.mark.parametrize(
    "order_type",
    (
        PaperExecutionOrderType.MARKET,
        PaperExecutionOrderType.LIMIT,
        PaperExecutionOrderType.STOP,
        PaperExecutionOrderType.STOP_LIMIT,
    ),
)
def test_intent_accepts_supported_order_shapes(
    order_type: PaperExecutionOrderType,
) -> None:
    result = intent(order_type)

    assert result.order_type is order_type
    assert result.quantity == Decimal("1.00")
    assert result.to_primitive()["instrument"]["symbol"] == "AAPL"


@pytest.mark.parametrize("quantity", (Decimal("0"), Decimal("-1"), Decimal("NaN")))
def test_intent_rejects_invalid_quantity(quantity: Decimal) -> None:
    with pytest.raises(PaperExecutionInvariantError):
        PaperExecutionIntent(
            instrument=instrument(),
            side=PaperExecutionSide.BUY,
            order_type=PaperExecutionOrderType.MARKET,
            quantity=quantity,
        )


def test_intent_rejects_floats_and_invalid_price_combinations() -> None:
    with pytest.raises(PaperExecutionInvariantError):
        PaperExecutionIntent(
            instrument=instrument(),
            side=PaperExecutionSide.BUY,
            order_type=PaperExecutionOrderType.MARKET,
            quantity=1.0,  # type: ignore[arg-type]
        )
    with pytest.raises(PaperExecutionInvariantError):
        PaperExecutionIntent(
            instrument=instrument(),
            side=PaperExecutionSide.BUY,
            order_type=PaperExecutionOrderType.MARKET,
            quantity=Decimal("1"),
            limit_price=Decimal("100"),
        )


def test_approval_is_evidence_only_with_stable_fingerprint_and_safe_repr() -> None:
    first = approval()
    second = approval()

    assert first == second
    assert first.approval_fingerprint.startswith("pap-")
    assert "secret" not in repr(first).lower()
    with pytest.raises(FrozenInstanceError):
        first.approver_reference = "other"  # type: ignore[misc]


def test_approval_rejects_readiness_objects_naive_datetimes_and_bad_expiry() -> None:
    with pytest.raises(PaperExecutionInvariantError):
        PaperExecutionApproval(
            approval_kind=PaperExecutionApprovalKind.OPERATOR,
            approver_reference="operator",
            approval_reference="approval",
            bound_fingerprint=object(),  # type: ignore[arg-type]
            approved_at=datetime(2026, 7, 30, tzinfo=UTC),
        )
    with pytest.raises(Exception):
        PaperExecutionApproval(
            approval_kind=PaperExecutionApprovalKind.OPERATOR,
            approver_reference="operator",
            approval_reference="approval",
            bound_fingerprint="pcf-" + ("1" * 64),
            approved_at=datetime(2026, 7, 30),
        )
    with pytest.raises(PaperExecutionInvariantError):
        PaperExecutionApproval(
            approval_kind=PaperExecutionApprovalKind.OPERATOR,
            approver_reference="operator",
            approval_reference="approval",
            bound_fingerprint="pcf-" + ("1" * 64),
            approved_at=datetime(2026, 7, 30, tzinfo=UTC),
            expires_at=datetime(2026, 7, 29, tzinfo=UTC),
        )


def test_policy_snapshot_is_descriptive_sorted_and_fingerprinted() -> None:
    result = policy()

    assert result.allowed_operations == (
        PaperExecutionOperation.CANCEL,
        PaperExecutionOperation.REPLACE,
        PaperExecutionOperation.SUBMIT,
    )
    assert result.policy_fingerprint.startswith("pps-")
    assert not hasattr(result, "evaluate")


def test_context_normalizes_metadata_rejects_sensitive_terms_and_requires_aware_time() -> (
    None
):
    ctx = context()

    assert ctx.metadata == (("trace", "safe"),)
    with pytest.raises(PaperExecutionInvariantError):
        PaperExecutionContext(
            aggregate_id=ctx.aggregate_id,
            correlation_id=ctx.correlation_id,
            source_component="manual.paper",
            requested_at=datetime(2026, 7, 30, tzinfo=UTC),
            metadata=(("api_key", "sentinel"),),
        )
    with pytest.raises(Exception):
        PaperExecutionContext(
            aggregate_id=ctx.aggregate_id,
            correlation_id=ctx.correlation_id,
            source_component="manual.paper",
            requested_at=datetime(2026, 7, 30),
        )


@pytest.mark.parametrize(
    "operation",
    (
        PaperExecutionOperation.SUBMIT,
        PaperExecutionOperation.CANCEL,
        PaperExecutionOperation.REPLACE,
    ),
)
def test_command_accepts_supported_operations(
    operation: PaperExecutionOperation,
) -> None:
    result = command(operation)

    assert result.mode is PaperExecutionMode.PAPER
    assert result.payload_fingerprint.startswith("pcf-")
    assert result.command_id.to_primitive().startswith("pec-")
    assert result.command_id.to_primitive() != result.payload_fingerprint
    assert result.fingerprint() == result.payload_fingerprint


def test_command_payload_fingerprint_is_deterministic_and_changes_with_payload() -> (
    None
):
    first = command()
    second = command()
    changed = PaperExecutionCommand(
        command_id=first.command_id,
        aggregate_id=first.aggregate_id,
        correlation_id=first.correlation_id,
        idempotency_key=first.idempotency_key,
        operation=PaperExecutionOperation.SUBMIT,
        expected_execution_revision=PaperExecutionRevision(1),
        approval=first.approval,
        policy_snapshot=first.policy_snapshot,
        context=first.context,
        intent=first.intent,
    )

    assert first.payload_fingerprint == second.payload_fingerprint
    assert first.payload_fingerprint != changed.payload_fingerprint


def test_command_invariants_and_no_behavior_methods() -> None:
    with pytest.raises(PaperExecutionInvariantError):
        PaperExecutionCommand(
            command_id=ids()[2],
            aggregate_id=ids()[0],
            correlation_id=ids()[1],
            idempotency_key=ids()[3],
            operation=PaperExecutionOperation.SUBMIT,
            expected_execution_revision=PaperExecutionRevision.initial(),
            approval=approval(),
            policy_snapshot=policy(),
            context=context(),
            intent=None,
        )

    prohibited = {
        "execute",
        "submit",
        "dispatch",
        "cancel_order",
        "replace_order",
        "retry",
        "reconcile",
        "persist",
        "approve",
        "authorize",
        "connect",
        "send",
        "call_broker",
    }
    assert prohibited.isdisjoint(dir(PaperExecutionCommand))
