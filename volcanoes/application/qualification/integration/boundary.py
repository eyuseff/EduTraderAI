"""Runtime-facing, non-executing Paper qualification boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from volcanoes.application.qualification.contracts import (
    CommandId,
    CorrelationId,
    IdempotencyKey,
    QualificationRunId,
    StateRevision,
)
from volcanoes.application.qualification.integration.contracts import (
    MetadataValue,
    PaperIntegrationEnvironment,
    RuntimeActionKind,
    SafeMetadata,
    require_paper_environment,
)
from volcanoes.application.qualification.integration.errors import (
    BoundaryIdentityContinuityError,
    BoundaryInputValidationError,
    BoundaryModeError,
    BoundaryResultValidationError,
    BoundaryShadowInvocationError,
    PaperQualificationShadowError,
)
from volcanoes.application.qualification.integration.shadow import (
    PaperQualificationShadowRequest,
    PaperQualificationShadowResult,
    PaperQualificationShadowRunner,
    ShadowComparisonStatus,
    ShadowMismatchClassification,
)
from volcanoes.application.qualification.integration.translation import (
    derive_integration_identity,
)


class QualificationRuntimeBoundaryMode(StrEnum):
    """Only supported runtime boundary mode for this slice."""

    SHADOW_ONLY = "SHADOW_ONLY"


class QualificationRuntimeBoundaryStatus(StrEnum):
    """Safe non-executing runtime-boundary statuses."""

    SHADOW_EVALUATED = "SHADOW_EVALUATED"
    SHADOW_MATCH = "SHADOW_MATCH"
    SHADOW_MISMATCH = "SHADOW_MISMATCH"
    SHADOW_INCOMPARABLE = "SHADOW_INCOMPARABLE"
    SHADOW_QUALIFICATION_ERROR = "SHADOW_QUALIFICATION_ERROR"
    REJECTED_INVALID_INPUT = "REJECTED_INVALID_INPUT"


_SECRET_MARKERS = (
    "sentinel_boundary_secret_do_not_expose",
    "sentinel_boundary_token_do_not_expose",
    "sentinel_boundary_password_do_not_expose",
    "api_key",
    "secret",
    "token",
    "password",
    "authorization",
    "cookie",
)


@dataclass(frozen=True, slots=True)
class QualificationRuntimeBoundaryRequest:
    """Immutable request accepted by the future runtime-facing seam."""

    shadow_request: PaperQualificationShadowRequest
    mode: QualificationRuntimeBoundaryMode = (
        QualificationRuntimeBoundaryMode.SHADOW_ONLY
    )
    boundary_invocation_id: str = ""
    source_identifier: str = "paper-runtime-shadow-boundary"
    legacy_behavior_authoritative: bool = True
    execution_authorized: bool = False
    metadata: SafeMetadata = ()

    def __post_init__(self) -> None:
        if not isinstance(self.shadow_request, PaperQualificationShadowRequest):
            raise BoundaryInputValidationError(
                reason_code="INVALID_BOUNDARY_SHADOW_REQUEST",
                safe_message="Boundary shadow request is invalid.",
            )
        _validate_shadow_mode(self.mode)
        if self.legacy_behavior_authoritative is not True:
            raise BoundaryInputValidationError(
                reason_code="LEGACY_AUTHORITY_REQUIRED",
                safe_message="Legacy Paper behavior must remain authoritative.",
            )
        if self.execution_authorized is not False:
            raise BoundaryInputValidationError(
                reason_code="EXECUTION_NOT_AUTHORIZED",
                safe_message="Runtime boundary accepts shadow-only requests.",
            )
        object.__setattr__(
            self,
            "source_identifier",
            _validate_identifier(self.source_identifier, "source_identifier"),
        )
        object.__setattr__(self, "metadata", _safe_metadata(self.metadata))
        boundary_id = self.boundary_invocation_id or derive_boundary_invocation_id(
            self.shadow_request,
            self.source_identifier,
        )
        object.__setattr__(
            self,
            "boundary_invocation_id",
            _validate_identifier(boundary_id, "boundary_invocation_id"),
        )


@dataclass(frozen=True, slots=True)
class QualificationRuntimeBoundaryResult:
    """Immutable non-executing result returned by the runtime boundary."""

    boundary_invocation_id: str
    boundary_mode: QualificationRuntimeBoundaryMode
    boundary_status: QualificationRuntimeBoundaryStatus
    shadow_result: PaperQualificationShadowResult
    qualification_run_id: QualificationRunId
    runtime_request_id: str
    command_id: CommandId
    correlation_id: CorrelationId
    idempotency_key: IdempotencyKey
    comparison_status: ShadowComparisonStatus
    mismatch_classifications: tuple[ShadowMismatchClassification, ...]
    expected_revision: StateRevision
    previous_revision: StateRevision
    next_revision: StateRevision | None
    transition_id: str | None
    action_described: RuntimeActionKind | None
    safe_summary: str
    action_executed: Literal[False] = False
    legacy_behavior_authoritative: Literal[True] = True
    legacy_behavior_changed: Literal[False] = False
    runtime_connected: Literal[False] = False


class QualificationRuntimeIntegrationBoundary:
    """Single future runtime seam for Paper shadow qualification observation."""

    def __init__(self, shadow_runner: PaperQualificationShadowRunner) -> None:
        if not isinstance(shadow_runner, PaperQualificationShadowRunner):
            raise TypeError("shadow_runner must be a PaperQualificationShadowRunner.")
        self._shadow_runner = shadow_runner

    def evaluate_shadow(
        self,
        request: QualificationRuntimeBoundaryRequest,
    ) -> QualificationRuntimeBoundaryResult:
        """Evaluate one shadow request without controlling runtime behavior."""

        if not isinstance(request, QualificationRuntimeBoundaryRequest):
            raise BoundaryInputValidationError(
                reason_code="INVALID_BOUNDARY_REQUEST",
                safe_message="Runtime boundary request is invalid.",
            )
        self._validate_request(request)
        try:
            shadow_result = self._shadow_runner.evaluate(request.shadow_request)
        except PaperQualificationShadowError as error:
            raise BoundaryShadowInvocationError(
                reason_code=error.reason_code,
                safe_message=error.safe_message,
                context=error.context,
            ) from error
        self._validate_shadow_result(request, shadow_result)
        return _boundary_result_from_shadow(request, shadow_result)

    @staticmethod
    def _validate_request(request: QualificationRuntimeBoundaryRequest) -> None:
        _validate_shadow_mode(request.mode)
        shadow_request = request.shadow_request
        runtime_request = shadow_request.runtime_request
        legacy_decision = shadow_request.legacy_decision
        require_paper_environment(runtime_request.environment)
        require_paper_environment(legacy_decision.environment)
        if runtime_request.environment != legacy_decision.environment:
            raise BoundaryIdentityContinuityError(
                reason_code="BOUNDARY_ENVIRONMENT_MISMATCH",
                safe_message="Boundary request environments do not match.",
                context=(("field", "environment"),),
            )
        mismatches: list[str] = []
        if legacy_decision.runtime_request_id != runtime_request.runtime_request_id:
            mismatches.append("runtime_request_id")
        if legacy_decision.qualification_run_id != runtime_request.qualification_run_id:
            mismatches.append("qualification_run_id")
        if legacy_decision.command_id != runtime_request.command_id:
            mismatches.append("command_id")
        if legacy_decision.correlation_id != runtime_request.correlation_id:
            mismatches.append("correlation_id")
        if legacy_decision.idempotency_key != runtime_request.idempotency_key:
            mismatches.append("idempotency_key")
        if legacy_decision.expected_revision != runtime_request.expected_revision:
            mismatches.append("expected_revision")
        if mismatches:
            raise BoundaryIdentityContinuityError(
                reason_code="BOUNDARY_IDENTITY_CONTINUITY_FAILED",
                safe_message="Boundary request identity does not match.",
                context=tuple(("field", field) for field in mismatches),
            )
        if request.legacy_behavior_authoritative is not True:
            raise BoundaryInputValidationError(
                reason_code="LEGACY_AUTHORITY_REQUIRED",
                safe_message="Legacy Paper behavior must remain authoritative.",
            )
        if request.execution_authorized is not False:
            raise BoundaryInputValidationError(
                reason_code="EXECUTION_NOT_AUTHORIZED",
                safe_message="Runtime boundary accepts shadow-only requests.",
            )

    @staticmethod
    def _validate_shadow_result(
        request: QualificationRuntimeBoundaryRequest,
        result: PaperQualificationShadowResult,
    ) -> None:
        shadow_request = request.shadow_request
        runtime_request = shadow_request.runtime_request
        mismatches: list[str] = []
        if result.shadow_invocation_id != shadow_request.shadow_invocation_id:
            mismatches.append("shadow_invocation_id")
        if result.qualification_run_id != runtime_request.qualification_run_id:
            mismatches.append("qualification_run_id")
        if result.command_id != runtime_request.command_id:
            mismatches.append("command_id")
        if result.correlation_id != runtime_request.correlation_id:
            mismatches.append("correlation_id")
        if result.idempotency_key != runtime_request.idempotency_key:
            mismatches.append("idempotency_key")
        if result.previous_revision != runtime_request.expected_revision:
            mismatches.append("previous_revision")
        if (
            result.legacy_decision.runtime_request_id
            != runtime_request.runtime_request_id
        ):
            mismatches.append("runtime_request_id")
        if result.action_executed is not False:
            mismatches.append("action_executed")
        if result.legacy_behavior_changed is not False:
            mismatches.append("legacy_behavior_changed")
        if mismatches:
            raise BoundaryResultValidationError(
                reason_code="BOUNDARY_RESULT_IDENTITY_CONTINUITY_FAILED",
                safe_message="Shadow result identity does not match boundary request.",
                context=tuple(("field", field) for field in mismatches),
            )


def derive_boundary_invocation_id(
    shadow_request: PaperQualificationShadowRequest,
    source_identifier: str,
) -> str:
    """Derive a stable safe boundary identity from canonical shadow fields."""

    runtime_request = shadow_request.runtime_request
    return derive_integration_identity(
        "qib",
        (
            "boundary",
            "shadow-only",
            _environment_identity(runtime_request.environment),
            shadow_request.shadow_invocation_id,
            runtime_request.runtime_request_id,
            runtime_request.qualification_run_id,
            runtime_request.command_id,
            runtime_request.correlation_id,
            runtime_request.idempotency_key,
            str(runtime_request.expected_revision),
            source_identifier,
        ),
    )


def boundary_status_from_shadow(
    status: ShadowComparisonStatus,
) -> QualificationRuntimeBoundaryStatus:
    """Map shadow comparison status into the runtime boundary status model."""

    if status is ShadowComparisonStatus.MATCH:
        return QualificationRuntimeBoundaryStatus.SHADOW_MATCH
    if status is ShadowComparisonStatus.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE:
        return QualificationRuntimeBoundaryStatus.SHADOW_MATCH
    if status is ShadowComparisonStatus.MISMATCH:
        return QualificationRuntimeBoundaryStatus.SHADOW_MISMATCH
    if status is ShadowComparisonStatus.INCOMPARABLE:
        return QualificationRuntimeBoundaryStatus.SHADOW_INCOMPARABLE
    if status is ShadowComparisonStatus.QUALIFICATION_ERROR:
        return QualificationRuntimeBoundaryStatus.SHADOW_QUALIFICATION_ERROR
    return QualificationRuntimeBoundaryStatus.REJECTED_INVALID_INPUT


def _boundary_result_from_shadow(
    request: QualificationRuntimeBoundaryRequest,
    shadow_result: PaperQualificationShadowResult,
) -> QualificationRuntimeBoundaryResult:
    return QualificationRuntimeBoundaryResult(
        boundary_invocation_id=request.boundary_invocation_id,
        boundary_mode=request.mode,
        boundary_status=boundary_status_from_shadow(shadow_result.comparison_status),
        shadow_result=shadow_result,
        qualification_run_id=shadow_result.qualification_run_id,
        runtime_request_id=shadow_result.legacy_decision.runtime_request_id,
        command_id=shadow_result.command_id,
        correlation_id=shadow_result.correlation_id,
        idempotency_key=shadow_result.idempotency_key,
        comparison_status=shadow_result.comparison_status,
        mismatch_classifications=shadow_result.classifications,
        expected_revision=request.shadow_request.runtime_request.expected_revision,
        previous_revision=shadow_result.previous_revision,
        next_revision=shadow_result.next_revision,
        transition_id=shadow_result.transition_id,
        action_described=shadow_result.qualification_action_type,
        safe_summary=(
            "Qualification boundary completed shadow evaluation; "
            "legacy Paper behavior remains authoritative."
        ),
        action_executed=False,
        legacy_behavior_authoritative=True,
        legacy_behavior_changed=False,
        runtime_connected=False,
    )


def _validate_shadow_mode(mode: object) -> QualificationRuntimeBoundaryMode:
    if mode is QualificationRuntimeBoundaryMode.SHADOW_ONLY:
        return mode
    raise BoundaryModeError(
        reason_code="SHADOW_ONLY_MODE_REQUIRED",
        safe_message="Runtime boundary supports only shadow-only mode.",
    )


def _validate_identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BoundaryInputValidationError(
            reason_code="INVALID_BOUNDARY_IDENTIFIER",
            safe_message=f"{name} is invalid.",
        )
    normalized = value.strip()
    _ensure_safe_text(normalized)
    return normalized


def _safe_metadata(metadata: SafeMetadata) -> SafeMetadata:
    safe: list[tuple[str, MetadataValue]] = []
    for key, value in metadata:
        _ensure_safe_text(str(key))
        if isinstance(value, tuple):
            for item in value:
                _ensure_safe_text(str(item))
        else:
            _ensure_safe_text(str(value))
        safe.append((str(key), value))
    return tuple(safe)


def _environment_identity(value: object) -> str:
    if isinstance(value, PaperIntegrationEnvironment):
        return value.value
    if value is None:
        return ""
    return str(value)


def _ensure_safe_text(value: str) -> None:
    lowered = value.lower()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        raise BoundaryInputValidationError(
            reason_code="UNSAFE_BOUNDARY_METADATA",
            safe_message="Boundary input contains unsafe metadata.",
        )
