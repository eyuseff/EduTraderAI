from __future__ import annotations

from decimal import Decimal
import inspect

import pytest

from volcanoes.application.execution.certification import (
    CertificationFailurePhase,
    CertificationObservationKind,
    CertificationResultKind,
    MappedRequest,
    NormalizedFailure,
    NormalizedObservation,
    OfflinePaperCertificationHarness,
    SyntheticOrderFixture,
    SyntheticResponseFixture,
)


def request_fixture(
    fixture_id: str = "fixture-001", quantity: str = "2"
) -> SyntheticOrderFixture:
    return SyntheticOrderFixture(
        fixture_id=fixture_id,
        client_order_id=f"client-{fixture_id}",
        symbol="AAPL",
        side="BUY",
        quantity=Decimal(quantity),
        order_type="LIMIT",
        time_in_force="DAY",
        limit_price=Decimal("100.50"),
    )


def response_fixture(
    kind: CertificationObservationKind = CertificationObservationKind.ACCEPTED,
    *,
    fixture_id: str = "fixture-001",
    broker_reference: str = "paper-ref-001",
) -> SyntheticResponseFixture:
    return SyntheticResponseFixture(
        fixture_id=fixture_id,
        broker_reference=broker_reference,
        observation_kind=kind,
        message_code=f"SYNTHETIC_{kind.value}",
    )


def mapper(fixture: SyntheticOrderFixture) -> MappedRequest:
    return MappedRequest(
        fixture_id=fixture.fixture_id,
        client_order_id=fixture.client_order_id,
        fields=fixture.expected_mapped_fields(),
    )


def normalizer(
    fixture: SyntheticResponseFixture,
) -> NormalizedObservation | NormalizedFailure:
    if fixture.failure_phase is not None:
        return NormalizedFailure(
            fixture_id=fixture.fixture_id,
            phase=fixture.failure_phase,
            reason_code=fixture.message_code,
            safe_message=fixture.expected_safe_message or "unreachable",
            broker_reference=fixture.broker_reference,
            fields=fixture.fields,
        )
    assert fixture.broker_reference is not None
    assert fixture.observation_kind is not None
    return NormalizedObservation(
        fixture_id=fixture.fixture_id,
        broker_reference=fixture.broker_reference,
        kind=fixture.observation_kind,
        message_code=fixture.message_code,
        fields=fixture.fields,
    )


@pytest.mark.parametrize("kind", tuple(CertificationObservationKind))
def test_every_observation_category_is_normalized(
    kind: CertificationObservationKind,
) -> None:
    result = OfflinePaperCertificationHarness(mapper, normalizer).certify(
        request_fixture(), response_fixture(kind)
    )

    assert result.kind is CertificationResultKind.OBSERVATION
    assert result.observation is not None
    assert result.observation.kind is kind
    assert result.observation.broker_reference == "paper-ref-001"


def test_identical_input_replay_returns_identical_evidence_without_reinvocation() -> (
    None
):
    calls = {"mapped": 0, "normalized": 0}

    def counting_mapper(fixture: SyntheticOrderFixture) -> MappedRequest:
        calls["mapped"] += 1
        return mapper(fixture)

    def counting_normalizer(
        fixture: SyntheticResponseFixture,
    ) -> NormalizedObservation | NormalizedFailure:
        calls["normalized"] += 1
        return normalizer(fixture)

    harness = OfflinePaperCertificationHarness(counting_mapper, counting_normalizer)
    request = request_fixture()
    response = response_fixture()

    first = harness.certify(request, response)
    second = harness.certify(request, response)

    assert second is first
    assert calls == {"mapped": 1, "normalized": 1}


def test_same_fixture_identity_with_different_content_is_conflict() -> None:
    harness = OfflinePaperCertificationHarness(mapper, normalizer)
    harness.certify(request_fixture(quantity="2"), response_fixture())

    conflict = harness.certify(request_fixture(quantity="3"), response_fixture())

    assert conflict.kind is CertificationResultKind.IDENTITY_CONFLICT
    assert conflict.reason_code == "FIXTURE_IDENTITY_CONFLICT"


def test_changed_response_identity_or_content_uses_conflict_precedence() -> None:
    harness = OfflinePaperCertificationHarness(mapper, normalizer)
    original = harness.certify(request_fixture(), response_fixture())

    changed_identity = harness.certify(
        request_fixture(), response_fixture(fixture_id="fixture-002")
    )
    changed_content = harness.certify(
        request_fixture(), response_fixture(CertificationObservationKind.FILLED)
    )
    original_replay = harness.certify(request_fixture(), response_fixture())

    assert changed_identity.kind is CertificationResultKind.IDENTITY_CONFLICT
    assert changed_content.kind is CertificationResultKind.IDENTITY_CONFLICT
    assert original_replay is original


def test_broker_reference_has_one_fixture_owner() -> None:
    harness = OfflinePaperCertificationHarness(mapper, normalizer)
    harness.certify(request_fixture("fixture-001"), response_fixture())

    conflict = harness.certify(
        request_fixture("fixture-002"),
        response_fixture(fixture_id="fixture-002", broker_reference="paper-ref-001"),
    )

    assert conflict.kind is CertificationResultKind.OWNERSHIP_CONFLICT


@pytest.mark.parametrize(
    ("phase", "expected_kind", "unknown"),
    (
        (
            CertificationFailurePhase.PRE_DISPATCH,
            CertificationResultKind.PRE_DISPATCH_FAILURE,
            False,
        ),
        (
            CertificationFailurePhase.POSSIBLE_POST_DISPATCH,
            CertificationResultKind.OUTCOME_UNKNOWN,
            True,
        ),
    ),
)
def test_failure_phase_controls_ambiguity_without_resubmission(
    phase: CertificationFailurePhase,
    expected_kind: CertificationResultKind,
    unknown: bool,
) -> None:
    response = SyntheticResponseFixture(
        fixture_id="fixture-001",
        failure_phase=phase,
        message_code="SYNTHETIC_FAILURE",
    )

    result = OfflinePaperCertificationHarness(mapper, normalizer).certify(
        request_fixture(), response
    )

    assert result.kind is expected_kind
    assert result.failure is not None
    assert result.failure.outcome_unknown is unknown
    assert result.failure.automatic_resubmission is False


def test_fixture_identity_mismatch_is_rejected_before_normalization() -> None:
    called = False

    def forbidden_normalizer(
        fixture: SyntheticResponseFixture,
    ) -> NormalizedObservation | NormalizedFailure:
        nonlocal called
        called = True
        return normalizer(fixture)

    result = OfflinePaperCertificationHarness(mapper, forbidden_normalizer).certify(
        request_fixture(), response_fixture(fixture_id="fixture-002")
    )

    assert result.kind is CertificationResultKind.MALFORMED
    assert called is False


def test_mapper_cannot_change_client_identity() -> None:
    def wrong_identity(fixture: SyntheticOrderFixture) -> MappedRequest:
        return MappedRequest(
            fixture_id=fixture.fixture_id,
            client_order_id="different-client-id",
            fields=(),
        )

    result = OfflinePaperCertificationHarness(wrong_identity, normalizer).certify(
        request_fixture(), response_fixture()
    )

    assert result.kind is CertificationResultKind.MALFORMED


@pytest.mark.parametrize(
    "field_name",
    (
        "limit_price",
        "order_type",
        "quantity",
        "side",
        "stop_price",
        "symbol",
        "time_in_force",
    ),
)
@pytest.mark.parametrize("mutation", ("missing", "empty", "changed"))
def test_mapper_must_preserve_every_required_canonical_field(
    field_name: str, mutation: str
) -> None:
    calls = {"normalized": 0}

    def altered_mapper(fixture: SyntheticOrderFixture) -> MappedRequest:
        fields = dict(fixture.expected_mapped_fields())
        if mutation == "missing":
            del fields[field_name]
        elif mutation == "empty":
            fields[field_name] = ""
        else:
            fields[field_name] = "CHANGED"
        return MappedRequest(
            fixture_id=fixture.fixture_id,
            client_order_id=fixture.client_order_id,
            fields=tuple(fields.items()),
        )

    def counting_normalizer(
        fixture: SyntheticResponseFixture,
    ) -> NormalizedObservation | NormalizedFailure:
        calls["normalized"] += 1
        return normalizer(fixture)

    result = OfflinePaperCertificationHarness(
        altered_mapper, counting_normalizer
    ).certify(request_fixture(), response_fixture())

    assert result.kind is CertificationResultKind.MALFORMED
    assert calls["normalized"] == 0


@pytest.mark.parametrize("boundary", ("mapper", "normalizer"))
def test_boundary_exceptions_are_contained_and_sanitized(boundary: str) -> None:
    def raises(_: object) -> object:
        raise RuntimeError("authorization: bearer highly-sensitive")

    harness = OfflinePaperCertificationHarness(
        raises if boundary == "mapper" else mapper,  # type: ignore[arg-type]
        raises if boundary == "normalizer" else normalizer,  # type: ignore[arg-type]
    )

    result = harness.certify(request_fixture(), response_fixture())

    expected_kind = (
        CertificationResultKind.PRE_DISPATCH_FAILURE
        if boundary == "mapper"
        else CertificationResultKind.OUTCOME_UNKNOWN
    )
    assert result.kind is expected_kind
    assert result.failure is not None
    assert result.failure.outcome_unknown is (boundary == "normalizer")
    assert result.failure.automatic_resubmission is False
    assert result.failure.safe_message == "Certification boundary failed safely."
    assert "bearer" not in str(result.to_primitive()).lower()


def test_malformed_normalizer_output_is_rejected() -> None:
    def incomplete(_: SyntheticResponseFixture) -> object:
        return {"status": "accepted"}

    result = OfflinePaperCertificationHarness(mapper, incomplete).certify(  # type: ignore[arg-type]
        request_fixture(), response_fixture()
    )

    assert result.kind is CertificationResultKind.MALFORMED


def test_semantically_mismatched_normalizer_output_is_rejected() -> None:
    def wrong_category(fixture: SyntheticResponseFixture) -> NormalizedObservation:
        assert fixture.broker_reference is not None
        return NormalizedObservation(
            fixture_id=fixture.fixture_id,
            broker_reference=fixture.broker_reference,
            kind=CertificationObservationKind.FILLED,
            message_code="WRONG_CATEGORY",
        )

    result = OfflinePaperCertificationHarness(mapper, wrong_category).certify(
        request_fixture(), response_fixture(CertificationObservationKind.ACCEPTED)
    )

    assert result.kind is CertificationResultKind.MALFORMED


@pytest.mark.parametrize(
    "changed_field",
    ("fixture_id", "broker_reference", "kind", "message_code", "fields"),
)
def test_normalized_observation_must_preserve_all_response_evidence(
    changed_field: str,
) -> None:
    response = SyntheticResponseFixture(
        fixture_id="fixture-001",
        broker_reference="paper-ref-001",
        observation_kind=CertificationObservationKind.PARTIALLY_FILLED,
        message_code="PARTIAL_OBSERVED",
        fields=(("filled_quantity", "1"), ("status", "PARTIAL")),
    )

    def altered(fixture: SyntheticResponseFixture) -> NormalizedObservation:
        values = {
            "fixture_id": fixture.fixture_id,
            "broker_reference": fixture.broker_reference,
            "kind": fixture.observation_kind,
            "message_code": fixture.message_code,
            "fields": fixture.fields,
        }
        replacements = {
            "fixture_id": "fixture-other",
            "broker_reference": "paper-ref-other",
            "kind": CertificationObservationKind.FILLED,
            "message_code": "CHANGED_CODE",
            "fields": (("status", "CHANGED"),),
        }
        values[changed_field] = replacements[changed_field]
        assert isinstance(values["fixture_id"], str)
        assert isinstance(values["broker_reference"], str)
        assert isinstance(values["kind"], CertificationObservationKind)
        assert isinstance(values["message_code"], str)
        assert isinstance(values["fields"], tuple)
        return NormalizedObservation(**values)  # type: ignore[arg-type]

    result = OfflinePaperCertificationHarness(mapper, altered).certify(
        request_fixture(), response
    )

    assert result.kind is CertificationResultKind.MALFORMED


@pytest.mark.parametrize(
    "changed_field",
    (
        "fixture_id",
        "phase",
        "reason_code",
        "safe_message",
        "broker_reference",
        "fields",
    ),
)
def test_normalized_failure_must_preserve_all_response_evidence(
    changed_field: str,
) -> None:
    response = SyntheticResponseFixture(
        fixture_id="fixture-001",
        failure_phase=CertificationFailurePhase.PRE_DISPATCH,
        broker_reference="paper-ref-001",
        message_code="SYNTHETIC_REJECTION",
        expected_safe_message="Synthetic rejection normalized safely.",
        fields=(("status", "REJECTED"),),
    )

    def altered(fixture: SyntheticResponseFixture) -> NormalizedFailure:
        values = {
            "fixture_id": fixture.fixture_id,
            "phase": fixture.failure_phase,
            "reason_code": fixture.message_code,
            "safe_message": fixture.expected_safe_message,
            "broker_reference": fixture.broker_reference,
            "fields": fixture.fields,
        }
        replacements = {
            "fixture_id": "fixture-other",
            "phase": CertificationFailurePhase.POSSIBLE_POST_DISPATCH,
            "reason_code": "CHANGED_REASON",
            "safe_message": "Changed safe message.",
            "broker_reference": "paper-ref-other",
            "fields": (("status", "CHANGED"),),
        }
        values[changed_field] = replacements[changed_field]
        return NormalizedFailure(**values)  # type: ignore[arg-type]

    result = OfflinePaperCertificationHarness(mapper, altered).certify(
        request_fixture(), response
    )

    assert result.kind is CertificationResultKind.MALFORMED


@pytest.mark.parametrize(
    "terminal",
    (
        "observation",
        "pre_dispatch_failure",
        "outcome_unknown",
        "mapper_exception",
        "normalizer_exception",
        "malformed_mapper",
        "malformed_normalizer",
        "ownership_conflict",
        "identity_conflict",
        "fixture_identity_mismatch",
    ),
)
def test_every_terminal_result_replays_without_reinvoking_boundaries(
    terminal: str,
) -> None:
    calls = {"mapped": 0, "normalized": 0}

    def configured_mapper(fixture: SyntheticOrderFixture) -> object:
        calls["mapped"] += 1
        if terminal == "mapper_exception":
            raise RuntimeError("access_token must not escape")
        if terminal == "malformed_mapper":
            return MappedRequest(fixture.fixture_id, fixture.client_order_id, ())
        return mapper(fixture)

    def configured_normalizer(fixture: SyntheticResponseFixture) -> object:
        calls["normalized"] += 1
        if terminal == "normalizer_exception":
            raise RuntimeError("access_token must not escape")
        if terminal == "malformed_normalizer":
            return object()
        return normalizer(fixture)

    harness = OfflinePaperCertificationHarness(  # type: ignore[arg-type]
        configured_mapper, configured_normalizer
    )
    request = request_fixture()
    if terminal in ("pre_dispatch_failure", "outcome_unknown"):
        response = SyntheticResponseFixture(
            fixture_id=request.fixture_id,
            failure_phase=(
                CertificationFailurePhase.PRE_DISPATCH
                if terminal == "pre_dispatch_failure"
                else CertificationFailurePhase.POSSIBLE_POST_DISPATCH
            ),
            message_code="SYNTHETIC_FAILURE",
        )
    elif terminal == "fixture_identity_mismatch":
        response = response_fixture(fixture_id="fixture-other")
    else:
        response = response_fixture()

    if terminal == "ownership_conflict":
        harness.certify(
            request_fixture("fixture-owner"),
            response_fixture(fixture_id="fixture-owner"),
        )
        request = request_fixture("fixture-001")
    elif terminal == "identity_conflict":
        harness.certify(request, response)
        response = response_fixture(CertificationObservationKind.FILLED)

    first = harness.certify(request, response)
    calls_after_first = calls.copy()
    second = harness.certify(request, response)

    assert second is first
    assert calls == calls_after_first
    assert second.result_fingerprint == first.result_fingerprint


def test_harness_has_no_retry_or_storage_provider_inputs() -> None:
    signature = inspect.signature(OfflinePaperCertificationHarness)
    source = inspect.getsource(OfflinePaperCertificationHarness)

    assert tuple(signature.parameters) == ("mapper", "normalizer")
    assert "while " not in source
    assert "retry" not in source.lower()
    assert "transaction" not in source.lower()
    assert "persistence" not in source.lower()
