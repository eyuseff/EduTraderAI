from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from volcanoes.application.execution import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionIdentityError,
    PaperExecutionRevision,
    PaperExecutionRevisionError,
)

IDENTITY_TYPES = (
    (PaperExecutionCommandId, "pec"),
    (PaperExecutionCorrelationId, "pcr"),
    (PaperExecutionIdempotencyKey, "pik"),
    (PaperExecutionAggregateId, "pea"),
    (PaperBrokerOrderReference, "pbr"),
)


@pytest.mark.parametrize(("identity_type", "prefix"), IDENTITY_TYPES)
def test_identity_valid_construction_round_trip_and_repr(identity_type, prefix) -> None:
    value = f"{prefix}-" + ("a" * 64)
    identity = identity_type(value)

    assert str(identity) == value
    assert identity.to_primitive() == value
    assert repr(identity) == f"{identity_type.__name__}({value!r})"
    assert hash(identity) == hash(identity_type(value))


@pytest.mark.parametrize(("identity_type", "prefix"), IDENTITY_TYPES)
@pytest.mark.parametrize(
    "value",
    (
        "",
        " ",
        "wrong-" + ("a" * 64),
        "PEC-" + ("a" * 64),
        "pec-" + ("a" * 63),
        "pec-" + ("a" * 65),
        "pec-" + ("g" * 64),
        " pec-" + ("a" * 64),
        "pec-" + ("a" * 64) + " ",
    ),
)
def test_identity_rejects_ambiguous_or_invalid_values(
    identity_type,
    prefix,
    value,
) -> None:
    if value.startswith("pec-") and prefix != "pec":
        value = value.replace("pec-", f"{prefix}-", 1)
    with pytest.raises(PaperExecutionIdentityError):
        identity_type(value)


def test_identity_classes_never_compare_equal_across_types() -> None:
    command = PaperExecutionCommandId("pec-" + ("1" * 64))
    correlation = PaperExecutionCorrelationId("pcr-" + ("1" * 64))

    assert command != correlation
    assert command.to_primitive() != correlation.to_primitive()


def test_identity_factories_are_deterministic_mapping_order_independent_and_unicode() -> (
    None
):
    left = PaperExecutionCommandId.from_seed({"b": "é", "a": "1.00"})
    right = PaperExecutionCommandId.from_seed({"a": "1.00", "b": "e\u0301"})
    changed = PaperExecutionCommandId.from_seed({"a": "1.00", "b": "different"})

    assert left == right
    assert left != changed
    assert str(left).startswith("pec-")
    assert len(str(left)) == 68


def test_identity_fixed_golden_vectors() -> None:
    assert (
        str(PaperExecutionAggregateId.from_seed("paper", "AAPL", 1))
        == "pea-4436d8f3509807cb26e768513ef667fe781449faa205057156ac686647e7b1bd"
    )


def test_revision_rules_and_immutability() -> None:
    initial = PaperExecutionRevision.initial()

    assert initial == PaperExecutionRevision(0)
    assert initial.next() == PaperExecutionRevision(1)
    assert initial.next() is not initial
    assert int(initial) == 0
    assert repr(initial) == "PaperExecutionRevision(0)"
    assert hash(initial) == hash(PaperExecutionRevision(0))
    with pytest.raises(FrozenInstanceError):
        initial.value = 3  # type: ignore[misc]


@pytest.mark.parametrize("value", (-1, True, False, 1.0, "1"))
def test_revision_rejects_invalid_values(value: object) -> None:
    with pytest.raises(PaperExecutionRevisionError):
        PaperExecutionRevision(value)  # type: ignore[arg-type]
