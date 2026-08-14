from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from volcanoes.application.execution.certification import (
    CertificationFailurePhase,
    CertificationObservationKind,
    CertificationResult,
    CertificationResultKind,
    MappedRequest,
    NormalizedFailure,
    NormalizedObservation,
    SyntheticOrderFixture,
    SyntheticResponseFixture,
)
from volcanoes.application.execution.errors import PaperExecutionInvariantError


def order_fixture(fixture_id: str = "fixture-001") -> SyntheticOrderFixture:
    return SyntheticOrderFixture(
        fixture_id=fixture_id,
        client_order_id="client-001",
        symbol="aapl",
        side="buy",
        quantity=Decimal("2.00"),
        order_type="limit",
        time_in_force="day",
        limit_price=Decimal("100.50"),
    )


def test_contracts_are_immutable_and_normalized() -> None:
    fixture = order_fixture()

    assert fixture.symbol == "AAPL"
    assert fixture.side == "BUY"
    with pytest.raises(FrozenInstanceError):
        fixture.symbol = "MSFT"  # type: ignore[misc]


@pytest.mark.parametrize("field_name", ("side", "order_type", "time_in_force"))
@pytest.mark.parametrize("sensitive_value", ("ACCESS_TOKEN", "AUTHORIZATION"))
def test_order_fixture_rejects_sensitive_public_codes_during_construction(
    field_name: str, sensitive_value: str
) -> None:
    values = {
        "fixture_id": "fixture-001",
        "client_order_id": "client-001",
        "symbol": "AAPL",
        "side": "BUY",
        "quantity": Decimal("2"),
        "order_type": "LIMIT",
        "time_in_force": "DAY",
    }
    values[field_name] = sensitive_value

    with pytest.raises(PaperExecutionInvariantError, match="sensitive"):
        SyntheticOrderFixture(**values)  # type: ignore[arg-type]


def test_valid_public_codes_retain_deterministic_fixture_fingerprint() -> None:
    first = order_fixture()
    second = order_fixture()

    assert (first.side, first.order_type, first.time_in_force) == (
        "BUY",
        "LIMIT",
        "DAY",
    )
    assert first.fixture_fingerprint == second.fixture_fingerprint


def test_fingerprints_are_deterministic_and_content_sensitive() -> None:
    first = order_fixture()
    same = order_fixture()
    changed = SyntheticOrderFixture(
        fixture_id="fixture-001",
        client_order_id="client-001",
        symbol="AAPL",
        side="BUY",
        quantity=Decimal("3"),
        order_type="LIMIT",
        time_in_force="DAY",
        limit_price=Decimal("100.5"),
    )

    assert first.fixture_fingerprint == same.fixture_fingerprint
    assert first.fixture_fingerprint != changed.fixture_fingerprint


def test_fixture_defines_one_complete_canonical_mapping() -> None:
    fixture = order_fixture()

    assert fixture.expected_mapped_fields() == (
        ("limit_price", "100.5"),
        ("order_type", "LIMIT"),
        ("quantity", "2"),
        ("side", "BUY"),
        ("stop_price", None),
        ("symbol", "AAPL"),
        ("time_in_force", "DAY"),
    )


def test_mapped_fields_are_sorted_and_require_immutable_safe_values() -> None:
    mapped = MappedRequest(
        fixture_id="fixture-001",
        client_order_id="client-001",
        fields=(("symbol", "AAPL"), ("quantity", 2)),
    )

    assert mapped.fields == (("quantity", 2), ("symbol", "AAPL"))
    with pytest.raises(PaperExecutionInvariantError):
        MappedRequest("fixture-001", "client-001", [("symbol", "AAPL")])  # type: ignore[arg-type]
    with pytest.raises(PaperExecutionInvariantError):
        MappedRequest("fixture-001", "client-001", (("access_token", "redacted"),))
    with pytest.raises(PaperExecutionInvariantError):
        MappedRequest("fixture-001", "client-001", (("note", "bearer abc"),))


def test_response_fixture_rejects_malformed_or_incomplete_content() -> None:
    with pytest.raises(PaperExecutionInvariantError, match="Exactly one"):
        SyntheticResponseFixture(fixture_id="fixture-001")
    with pytest.raises(PaperExecutionInvariantError, match="Exactly one"):
        SyntheticResponseFixture(
            fixture_id="fixture-001",
            broker_reference="paper-ref-1",
            observation_kind=CertificationObservationKind.ACCEPTED,
            failure_phase=CertificationFailurePhase.PRE_DISPATCH,
        )
    with pytest.raises(PaperExecutionInvariantError, match="broker reference"):
        SyntheticResponseFixture(
            fixture_id="fixture-001",
            observation_kind=CertificationObservationKind.ACCEPTED,
        )


def test_failure_enforces_outcome_unknown_and_disables_automatic_resubmission() -> None:
    before = NormalizedFailure(
        fixture_id="fixture-001",
        phase=CertificationFailurePhase.PRE_DISPATCH,
        reason_code="LOCAL_MAPPING_FAILED",
        safe_message="Synthetic mapping was rejected.",
    )
    ambiguous = NormalizedFailure(
        fixture_id="fixture-001",
        phase=CertificationFailurePhase.POSSIBLE_POST_DISPATCH,
        reason_code="ACK_AMBIGUOUS",
        safe_message="Synthetic acknowledgement was ambiguous.",
    )

    assert before.outcome_unknown is False
    assert ambiguous.outcome_unknown is True
    assert before.automatic_resubmission is False
    assert ambiguous.automatic_resubmission is False


def test_result_rejects_incomplete_observation_and_failure_variants() -> None:
    with pytest.raises(PaperExecutionInvariantError, match="Observation"):
        CertificationResult(
            fixture_id="fixture-001",
            request_fingerprint="cmr-" + "0" * 64,
            response_fingerprint="crf-" + "0" * 64,
            kind=CertificationResultKind.OBSERVATION,
        )
    with pytest.raises(PaperExecutionInvariantError, match="Failure"):
        CertificationResult(
            fixture_id="fixture-001",
            request_fingerprint="cmr-" + "0" * 64,
            response_fingerprint="crf-" + "0" * 64,
            kind=CertificationResultKind.OUTCOME_UNKNOWN,
        )


def test_result_rejects_ambiguous_payload_variants() -> None:
    observation = NormalizedObservation(
        fixture_id="fixture-001",
        broker_reference="paper-ref-1",
        kind=CertificationObservationKind.ACCEPTED,
        message_code="ACCEPTED",
    )
    failure = NormalizedFailure(
        fixture_id="fixture-001",
        phase=CertificationFailurePhase.PRE_DISPATCH,
        reason_code="FAILED",
        safe_message="Synthetic failure.",
    )
    with pytest.raises(PaperExecutionInvariantError, match="cannot carry failure"):
        CertificationResult(
            fixture_id="fixture-001",
            request_fingerprint="cmr-" + "0" * 64,
            response_fingerprint="crf-" + "0" * 64,
            kind=CertificationResultKind.OBSERVATION,
            observation=observation,
            failure=failure,
        )


@pytest.mark.parametrize(
    ("kind", "phase"),
    (
        (
            CertificationResultKind.PRE_DISPATCH_FAILURE,
            CertificationFailurePhase.POSSIBLE_POST_DISPATCH,
        ),
        (
            CertificationResultKind.OUTCOME_UNKNOWN,
            CertificationFailurePhase.PRE_DISPATCH,
        ),
    ),
)
def test_result_rejects_inverse_failure_variants(
    kind: CertificationResultKind, phase: CertificationFailurePhase
) -> None:
    failure = NormalizedFailure(
        fixture_id="fixture-001",
        phase=phase,
        reason_code="FAILED",
        safe_message="Synthetic failure.",
    )

    with pytest.raises(PaperExecutionInvariantError, match="require"):
        CertificationResult(
            fixture_id="fixture-001",
            request_fingerprint="cmr-" + "0" * 64,
            response_fingerprint="crf-" + "0" * 64,
            kind=kind,
            failure=failure,
            reason_code=failure.reason_code,
        )


def test_failure_result_reason_must_match_failure_evidence() -> None:
    failure = NormalizedFailure(
        fixture_id="fixture-001",
        phase=CertificationFailurePhase.PRE_DISPATCH,
        reason_code="EXPECTED_REASON",
        safe_message="Synthetic failure.",
    )

    with pytest.raises(PaperExecutionInvariantError, match="reason"):
        CertificationResult(
            fixture_id="fixture-001",
            request_fingerprint="cmr-" + "0" * 64,
            response_fingerprint="crf-" + "0" * 64,
            kind=CertificationResultKind.PRE_DISPATCH_FAILURE,
            failure=failure,
            reason_code="DIFFERENT_REASON",
        )


def test_payload_free_result_variants_reject_observations_and_failures() -> None:
    observation = NormalizedObservation(
        fixture_id="fixture-001",
        broker_reference="paper-ref-1",
        kind=CertificationObservationKind.ACCEPTED,
        message_code="ACCEPTED",
    )
    failure = NormalizedFailure(
        fixture_id="fixture-001",
        phase=CertificationFailurePhase.PRE_DISPATCH,
        reason_code="FAILED",
        safe_message="Synthetic failure.",
    )
    for kind in (
        CertificationResultKind.IDENTITY_CONFLICT,
        CertificationResultKind.OWNERSHIP_CONFLICT,
        CertificationResultKind.MALFORMED,
    ):
        with pytest.raises(PaperExecutionInvariantError):
            CertificationResult(
                fixture_id="fixture-001",
                request_fingerprint="cmr-" + "0" * 64,
                response_fingerprint="crf-" + "0" * 64,
                kind=kind,
                observation=observation,
            )
        with pytest.raises(PaperExecutionInvariantError):
            CertificationResult(
                fixture_id="fixture-001",
                request_fingerprint="cmr-" + "0" * 64,
                response_fingerprint="crf-" + "0" * 64,
                kind=kind,
                failure=failure,
            )
    with pytest.raises(PaperExecutionInvariantError, match="specific safe reason"):
        CertificationResult(
            fixture_id="fixture-001",
            request_fingerprint="cmr-" + "0" * 64,
            response_fingerprint="crf-" + "0" * 64,
            kind=CertificationResultKind.MALFORMED,
        )


def test_normalized_outputs_reject_sensitive_text() -> None:
    with pytest.raises(PaperExecutionInvariantError):
        NormalizedObservation(
            fixture_id="fixture-001",
            broker_reference="paper-ref-1",
            kind=CertificationObservationKind.ACCEPTED,
            message_code="ACCESS_TOKEN_EXPOSED",
        )
    with pytest.raises(PaperExecutionInvariantError):
        NormalizedFailure(
            fixture_id="fixture-001",
            phase=CertificationFailurePhase.PRE_DISPATCH,
            reason_code="FAILED",
            safe_message="authorization: bearer value",
        )
    with pytest.raises(PaperExecutionInvariantError):
        NormalizedFailure(
            fixture_id="fixture-001",
            phase=CertificationFailurePhase.PRE_DISPATCH,
            reason_code="FAILED",
            safe_message="   ",
        )
    with pytest.raises(PaperExecutionInvariantError):
        CertificationResult(
            fixture_id="fixture-001",
            request_fingerprint="cmr-" + "0" * 64,
            response_fingerprint="crf-" + "0" * 64,
            kind=CertificationResultKind.MALFORMED,
            reason_code="ACCESS_TOKEN_EXPOSED",
        )
    with pytest.raises(PaperExecutionInvariantError):
        NormalizedObservation(
            fixture_id="fixture-001",
            broker_reference="access_token",
            kind=CertificationObservationKind.ACCEPTED,
            message_code="ACCEPTED",
        )
