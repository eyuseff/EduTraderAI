from __future__ import annotations

from datetime import UTC, datetime, timezone, timedelta
from decimal import Decimal

import pytest

from volcanoes.application.execution._canonical import (
    canonical_json_bytes,
    canonical_json_text,
    canonicalize,
    normalize_decimal,
    normalize_datetime,
)
from volcanoes.application.execution.enums import PaperExecutionMode
from volcanoes.application.execution.errors import PaperExecutionSerializationError


def test_canonical_json_is_mapping_order_independent_and_compact() -> None:
    left = {"b": Decimal("1.00"), "a": [PaperExecutionMode.PAPER, None, True, 1]}
    right = {"a": [PaperExecutionMode.PAPER, None, True, 1], "b": Decimal("1")}

    assert canonical_json_text(left) == canonical_json_text(right)
    assert canonical_json_text(left) == '{"a":["PAPER",null,true,1],"b":"1"}'
    assert canonical_json_bytes(left) == canonical_json_text(left).encode()


@pytest.mark.parametrize(
    "value",
    (Decimal("1"), Decimal("1.0"), Decimal("1.00"), Decimal("1.000")),
)
def test_decimal_equivalent_values_canonicalize_identically(value: Decimal) -> None:
    assert normalize_decimal(value) == "1"


@pytest.mark.parametrize(
    "value", (Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity"))
)
def test_decimal_rejects_non_finite_values(value: Decimal) -> None:
    with pytest.raises(PaperExecutionSerializationError):
        normalize_decimal(value)


def test_datetime_requires_timezone_and_normalizes_to_utc() -> None:
    source = datetime(2026, 7, 30, 12, 30, tzinfo=timezone(timedelta(hours=-4)))

    assert normalize_datetime(source) == "2026-07-30T16:30:00.000000Z"
    assert normalize_datetime(datetime(2026, 7, 30, tzinfo=UTC)).endswith("Z")
    with pytest.raises(PaperExecutionSerializationError):
        normalize_datetime(datetime(2026, 7, 30))


def test_unicode_normalization_is_stable() -> None:
    assert canonical_json_text({"name": "é"}) == canonical_json_text(
        {"name": "e\u0301"}
    )


@pytest.mark.parametrize(
    "value",
    (
        1.0,
        {1: "not text"},
        {"items": {"nondeterministic"}},
        object(),
    ),
)
def test_canonicalization_rejects_unsupported_or_nondeterministic_values(
    value: object,
) -> None:
    with pytest.raises(PaperExecutionSerializationError):
        canonicalize(value)


def test_fixed_golden_canonical_json_vector() -> None:
    payload = {
        "decimal": Decimal("10.5000"),
        "mode": PaperExecutionMode.PAPER,
        "none": None,
        "timestamp": datetime(2026, 7, 30, 1, 2, 3, 4000, tzinfo=UTC),
    }

    assert canonical_json_text(payload) == (
        '{"decimal":"10.5","mode":"PAPER","none":null,'
        '"timestamp":"2026-07-30T01:02:03.004000Z"}'
    )
