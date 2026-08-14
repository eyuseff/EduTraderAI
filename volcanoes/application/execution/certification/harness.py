"""Deterministic, entirely offline Paper boundary certification harness."""

from __future__ import annotations

from volcanoes.application.execution.certification.contracts import (
    CertificationFailurePhase,
    CertificationResult,
    CertificationResultKind,
    MappedRequest,
    NormalizedFailure,
    NormalizedObservation,
    SyntheticOrderFixture,
    SyntheticResponseFixture,
)
from volcanoes.application.execution.certification.ports import (
    CertificationRequestMapper,
    CertificationResponseNormalizer,
)

InputFingerprint = tuple[str, str]
EvidenceKey = tuple[str, str, str]


class OfflinePaperCertificationHarness:
    """Certify pure mapping and normalization using synthetic fixtures only."""

    __slots__ = ("_evidence", "_inputs", "_mapper", "_normalizer", "_owners")

    def __init__(
        self,
        mapper: CertificationRequestMapper,
        normalizer: CertificationResponseNormalizer,
    ) -> None:
        if not callable(mapper) or not callable(normalizer):
            raise TypeError("Certification boundaries must be callable.")
        self._mapper = mapper
        self._normalizer = normalizer
        self._inputs: dict[str, InputFingerprint] = {}
        self._evidence: dict[EvidenceKey, CertificationResult] = {}
        self._owners: dict[str, str] = {}

    def certify(
        self,
        request_fixture: SyntheticOrderFixture,
        response_fixture: SyntheticResponseFixture,
    ) -> CertificationResult:
        """Return deterministic evidence; never repeat or perform an external effect."""

        if not isinstance(request_fixture, SyntheticOrderFixture) or not isinstance(
            response_fixture, SyntheticResponseFixture
        ):
            raise TypeError("Certification requires synthetic immutable fixtures.")

        current_input = (
            request_fixture.fixture_fingerprint,
            response_fixture.response_fingerprint,
        )
        evidence_key = (request_fixture.fixture_id, *current_input)
        prior_evidence = self._evidence.get(evidence_key)
        if prior_evidence is not None:
            return prior_evidence
        if request_fixture.fixture_id in self._inputs:
            return self._record_evidence(
                evidence_key,
                CertificationResult(
                    fixture_id=request_fixture.fixture_id,
                    request_fingerprint=request_fixture.fixture_fingerprint,
                    response_fingerprint=response_fixture.response_fingerprint,
                    kind=CertificationResultKind.IDENTITY_CONFLICT,
                    reason_code="FIXTURE_IDENTITY_CONFLICT",
                ),
            )
        if request_fixture.fixture_id != response_fixture.fixture_id:
            return self._record_primary(
                evidence_key,
                current_input,
                self._malformed(
                    request_fixture, response_fixture, "FIXTURE_ID_MISMATCH"
                ),
            )

        try:
            mapped = self._mapper(request_fixture)
        except Exception:
            return self._record_primary(
                evidence_key,
                current_input,
                self._contained_failure(
                    request_fixture,
                    response_fixture,
                    "MAPPER_EXCEPTION",
                    CertificationFailurePhase.PRE_DISPATCH,
                ),
            )
        if (
            not isinstance(mapped, MappedRequest)
            or mapped.fixture_id != request_fixture.fixture_id
            or mapped.client_order_id != request_fixture.client_order_id
            or mapped.fields != request_fixture.expected_mapped_fields()
        ):
            return self._record_primary(
                evidence_key,
                current_input,
                self._malformed(
                    request_fixture, response_fixture, "MALFORMED_MAPPED_REQUEST"
                ),
            )

        try:
            normalized = self._normalizer(response_fixture)
        except Exception:
            return self._record_primary(
                evidence_key,
                current_input,
                self._contained_failure(
                    request_fixture,
                    response_fixture,
                    "NORMALIZER_EXCEPTION",
                    CertificationFailurePhase.POSSIBLE_POST_DISPATCH,
                ),
            )

        result = self._result_from_normalized(mapped, response_fixture, normalized)
        if result.kind is CertificationResultKind.OBSERVATION:
            assert result.observation is not None
            observation_reference = result.observation.broker_reference
            owner = self._owners.get(observation_reference)
            if owner is not None and owner != mapped.fixture_id:
                result = CertificationResult(
                    fixture_id=mapped.fixture_id,
                    request_fingerprint=mapped.request_fingerprint,
                    response_fingerprint=response_fixture.response_fingerprint,
                    kind=CertificationResultKind.OWNERSHIP_CONFLICT,
                    reason_code="BROKER_REFERENCE_OWNERSHIP_CONFLICT",
                )
            else:
                self._owners[observation_reference] = mapped.fixture_id
        return self._record_primary(evidence_key, current_input, result)

    def _result_from_normalized(
        self,
        mapped: MappedRequest,
        response_fixture: SyntheticResponseFixture,
        normalized: object,
    ) -> CertificationResult:
        if isinstance(normalized, NormalizedObservation):
            if (
                normalized.fixture_id != mapped.fixture_id
                or normalized.broker_reference != response_fixture.broker_reference
                or normalized.kind is not response_fixture.observation_kind
                or normalized.message_code != response_fixture.message_code
                or normalized.fields != response_fixture.fields
            ):
                return self._malformed_mapped(
                    mapped, response_fixture, "MALFORMED_NORMALIZED_OBSERVATION"
                )
            return CertificationResult(
                fixture_id=mapped.fixture_id,
                request_fingerprint=mapped.request_fingerprint,
                response_fingerprint=response_fixture.response_fingerprint,
                kind=CertificationResultKind.OBSERVATION,
                observation=normalized,
            )
        if isinstance(normalized, NormalizedFailure):
            if (
                normalized.fixture_id != mapped.fixture_id
                or normalized.phase is not response_fixture.failure_phase
                or normalized.reason_code != response_fixture.message_code
                or normalized.safe_message != response_fixture.expected_safe_message
                or normalized.broker_reference != response_fixture.broker_reference
                or normalized.fields != response_fixture.fields
            ):
                return self._malformed_mapped(
                    mapped, response_fixture, "MALFORMED_NORMALIZED_FAILURE"
                )
            kind = (
                CertificationResultKind.OUTCOME_UNKNOWN
                if normalized.outcome_unknown
                else CertificationResultKind.PRE_DISPATCH_FAILURE
            )
            return CertificationResult(
                fixture_id=mapped.fixture_id,
                request_fingerprint=mapped.request_fingerprint,
                response_fingerprint=response_fixture.response_fingerprint,
                kind=kind,
                failure=normalized,
                reason_code=normalized.reason_code,
            )
        return self._malformed_mapped(
            mapped, response_fixture, "MALFORMED_NORMALIZED_RESPONSE"
        )

    def _record_primary(
        self,
        evidence_key: EvidenceKey,
        current_input: InputFingerprint,
        result: CertificationResult,
    ) -> CertificationResult:
        self._inputs[evidence_key[0]] = current_input
        return self._record_evidence(evidence_key, result)

    def _record_evidence(
        self, evidence_key: EvidenceKey, result: CertificationResult
    ) -> CertificationResult:
        self._evidence[evidence_key] = result
        return result

    def _contained_failure(
        self,
        request_fixture: SyntheticOrderFixture,
        response_fixture: SyntheticResponseFixture,
        reason_code: str,
        phase: CertificationFailurePhase,
    ) -> CertificationResult:
        failure = NormalizedFailure(
            fixture_id=request_fixture.fixture_id,
            phase=phase,
            reason_code=reason_code,
            safe_message="Certification boundary failed safely.",
        )
        return CertificationResult(
            fixture_id=request_fixture.fixture_id,
            request_fingerprint=request_fixture.fixture_fingerprint,
            response_fingerprint=response_fixture.response_fingerprint,
            kind=(
                CertificationResultKind.OUTCOME_UNKNOWN
                if failure.outcome_unknown
                else CertificationResultKind.PRE_DISPATCH_FAILURE
            ),
            failure=failure,
            reason_code=reason_code,
        )

    def _malformed(
        self,
        request_fixture: SyntheticOrderFixture,
        response_fixture: SyntheticResponseFixture,
        reason_code: str,
    ) -> CertificationResult:
        return CertificationResult(
            fixture_id=request_fixture.fixture_id,
            request_fingerprint=request_fixture.fixture_fingerprint,
            response_fingerprint=response_fixture.response_fingerprint,
            kind=CertificationResultKind.MALFORMED,
            reason_code=reason_code,
        )

    def _malformed_mapped(
        self,
        mapped: MappedRequest,
        response_fixture: SyntheticResponseFixture,
        reason_code: str,
    ) -> CertificationResult:
        return CertificationResult(
            fixture_id=mapped.fixture_id,
            request_fingerprint=mapped.request_fingerprint,
            response_fingerprint=response_fixture.response_fingerprint,
            kind=CertificationResultKind.MALFORMED,
            reason_code=reason_code,
        )
