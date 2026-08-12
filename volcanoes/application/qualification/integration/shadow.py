"""Read-only shadow comparison for Paper qualification integration."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Literal

from volcanoes.application.qualification.contracts import (
    CommandId,
    CorrelationId,
    IdempotencyKey,
    QualificationResult,
    QualificationRunId,
    QualificationState,
    StateRevision,
)
from volcanoes.application.qualification.integration.contracts import (
    PaperIntegrationEnvironment,
    PaperRuntimeRequest,
    RuntimeActionKind,
    MetadataValue,
    SafeMetadata,
    SafeOrderIntent,
    require_paper_environment,
)
from volcanoes.application.qualification.integration.errors import (
    PaperQualificationFacadeError,
    ShadowIdentityContinuityError,
    ShadowInputValidationError,
)
from volcanoes.application.qualification.integration.facade import (
    PaperQualificationFacade,
    PaperQualificationFacadeResult,
)
from volcanoes.application.qualification.integration.translation import (
    derive_integration_identity,
)


class LegacyPaperDecisionType(StrEnum):
    """Safe categories describing what the current Paper path decided."""

    NO_ACTION = "NO_ACTION"
    PROCEED = "PROCEED"
    BLOCK = "BLOCK"
    REQUEST_SUBMISSION = "REQUEST_SUBMISSION"
    REQUEST_CANCELLATION = "REQUEST_CANCELLATION"
    REQUEST_RECONCILIATION = "REQUEST_RECONCILIATION"
    ABORT = "ABORT"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class LegacyPaperActionType(StrEnum):
    """Safe categories describing what the current Paper path requested."""

    NONE = "NONE"
    SUBMIT_ORDER = "SUBMIT_ORDER"
    CANCEL_ORDER = "CANCEL_ORDER"
    RECONCILE = "RECONCILE"
    BLOCK_CONSEQUENTIAL_ACTION = "BLOCK_CONSEQUENTIAL_ACTION"
    ABORT = "ABORT"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class ShadowComparisonStatus(StrEnum):
    """High-level deterministic shadow comparison outcome."""

    MATCH = "MATCH"
    MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE = "MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE"
    MISMATCH = "MISMATCH"
    INCOMPARABLE = "INCOMPARABLE"
    QUALIFICATION_ERROR = "QUALIFICATION_ERROR"
    INVALID_SHADOW_INPUT = "INVALID_SHADOW_INPUT"


class ShadowMismatchClassification(StrEnum):
    """Stable safe mismatch categories for shadow comparison."""

    ENVIRONMENT_MISMATCH = "ENVIRONMENT_MISMATCH"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"
    LEGACY_PROCEEDS_QUALIFICATION_BLOCKS = "LEGACY_PROCEEDS_QUALIFICATION_BLOCKS"
    LEGACY_BLOCKS_QUALIFICATION_PROCEEDS = "LEGACY_BLOCKS_QUALIFICATION_PROCEEDS"
    ACTION_KIND_MISMATCH = "ACTION_KIND_MISMATCH"
    ORDER_INTENT_MISMATCH = "ORDER_INTENT_MISMATCH"
    APPROVAL_MISMATCH = "APPROVAL_MISMATCH"
    CANCELLATION_MISMATCH = "CANCELLATION_MISMATCH"
    RECONCILIATION_MISMATCH = "RECONCILIATION_MISMATCH"
    EMERGENCY_STOP_MISMATCH = "EMERGENCY_STOP_MISMATCH"
    REVISION_MISMATCH = "REVISION_MISMATCH"
    REPLAY_MISMATCH = "REPLAY_MISMATCH"
    TERMINAL_RESULT_MISMATCH = "TERMINAL_RESULT_MISMATCH"
    UNSUPPORTED_LEGACY_DECISION = "UNSUPPORTED_LEGACY_DECISION"
    UNSUPPORTED_QUALIFICATION_ACTION = "UNSUPPORTED_QUALIFICATION_ACTION"
    INSUFFICIENT_COMPARISON_FACTS = "INSUFFICIENT_COMPARISON_FACTS"


_SECRET_MARKERS = (
    "sentinel_shadow_secret_do_not_expose",
    "sentinel_shadow_token_do_not_expose",
    "sentinel_shadow_password_do_not_expose",
    "api_key",
    "secret",
    "token",
    "password",
    "authorization",
    "cookie",
)


@dataclass(frozen=True, slots=True)
class LegacyPaperDecision:
    """Safe immutable representation of an existing Paper workflow decision."""

    environment: PaperIntegrationEnvironment
    legacy_decision_id: str
    runtime_request_id: str
    qualification_run_id: QualificationRunId
    command_id: CommandId
    correlation_id: CorrelationId
    idempotency_key: IdempotencyKey
    expected_revision: StateRevision
    decision_type: LegacyPaperDecisionType
    action_type: LegacyPaperActionType
    order_intent: SafeOrderIntent | None = None
    approved: bool | None = None
    cancellation_requested: bool = False
    reconciliation_requested: bool = False
    emergency_stop_active: bool = False
    reason_code: str | None = None
    metadata: SafeMetadata = ()

    def __post_init__(self) -> None:
        if not isinstance(self.environment, PaperIntegrationEnvironment):
            raise ShadowInputValidationError(
                reason_code="INVALID_LEGACY_ENVIRONMENT",
                safe_message="Legacy decision environment is invalid.",
            )
        _validate_identifier(self.legacy_decision_id, "legacy_decision_id")
        _validate_identifier(self.runtime_request_id, "runtime_request_id")
        for name in (
            "qualification_run_id",
            "command_id",
            "correlation_id",
            "idempotency_key",
        ):
            _validate_identifier(str(getattr(self, name)), name)
        if not isinstance(self.expected_revision, int) or self.expected_revision < 0:
            raise ShadowInputValidationError(
                reason_code="INVALID_LEGACY_REVISION",
                safe_message="Legacy expected revision is invalid.",
            )
        if not isinstance(self.decision_type, LegacyPaperDecisionType):
            raise ShadowInputValidationError(
                reason_code="UNSUPPORTED_LEGACY_DECISION",
                safe_message="Legacy decision type is unsupported.",
            )
        if not isinstance(self.action_type, LegacyPaperActionType):
            raise ShadowInputValidationError(
                reason_code="UNSUPPORTED_LEGACY_ACTION",
                safe_message="Legacy action type is unsupported.",
            )
        if self.reason_code is not None:
            _validate_identifier(self.reason_code, "reason_code")
        object.__setattr__(self, "metadata", _safe_metadata(self.metadata))


@dataclass(frozen=True, slots=True)
class ShadowMismatch:
    """One safe deterministic comparison mismatch."""

    classification: ShadowMismatchClassification
    field: str
    safe_reason: str


@dataclass(frozen=True, slots=True)
class PaperQualificationShadowRequest:
    """One read-only request to compare current Paper behavior with qualification."""

    runtime_request: PaperRuntimeRequest
    legacy_decision: LegacyPaperDecision
    shadow_invocation_id: str = ""
    metadata: SafeMetadata = ()

    def __post_init__(self) -> None:
        if not isinstance(self.runtime_request, PaperRuntimeRequest):
            raise ShadowInputValidationError(
                reason_code="INVALID_RUNTIME_REQUEST",
                safe_message="Shadow runtime request is invalid.",
            )
        if not isinstance(self.legacy_decision, LegacyPaperDecision):
            raise ShadowInputValidationError(
                reason_code="INVALID_LEGACY_DECISION",
                safe_message="Shadow legacy decision is invalid.",
            )
        object.__setattr__(self, "metadata", _safe_metadata(self.metadata))
        shadow_id = self.shadow_invocation_id or derive_shadow_invocation_id(
            self.runtime_request,
            self.legacy_decision,
        )
        object.__setattr__(
            self,
            "shadow_invocation_id",
            _validate_identifier(shadow_id, "shadow_invocation_id"),
        )


@dataclass(frozen=True, slots=True)
class PaperQualificationShadowResult:
    """Immutable result of a read-only shadow comparison."""

    shadow_invocation_id: str
    legacy_decision: LegacyPaperDecision
    qualification_facade_result: PaperQualificationFacadeResult | None
    comparison_status: ShadowComparisonStatus
    classifications: tuple[ShadowMismatchClassification, ...]
    matched_fields: tuple[str, ...]
    mismatches: tuple[ShadowMismatch, ...]
    qualification_run_id: QualificationRunId
    command_id: CommandId
    correlation_id: CorrelationId
    idempotency_key: IdempotencyKey
    transition_id: str | None
    previous_revision: StateRevision
    next_revision: StateRevision | None
    legacy_action_type: LegacyPaperActionType
    qualification_action_type: RuntimeActionKind | None
    qualification_state: QualificationState | None
    qualification_result: QualificationResult | None
    replayed: bool
    safe_operator_summary: str
    action_executed: Literal[False] = False
    legacy_behavior_changed: Literal[False] = False


class PaperQualificationShadowRunner:
    """Invoke the Paper facade once and compare without changing runtime behavior."""

    def __init__(self, facade: PaperQualificationFacade) -> None:
        if not isinstance(facade, PaperQualificationFacade):
            raise TypeError("facade must be a PaperQualificationFacade instance.")
        self._facade = facade

    def evaluate(
        self,
        request: PaperQualificationShadowRequest,
    ) -> PaperQualificationShadowResult:
        """Evaluate one Paper shadow request without executing returned actions."""

        self._validate_before_facade(request)
        try:
            facade_result = self._facade.handle(request.runtime_request)
        except PaperQualificationFacadeError as error:
            return self._qualification_error_result(request, error)
        self._validate_facade_result(request, facade_result)
        return compare_legacy_to_qualification(request, facade_result)

    @staticmethod
    def _validate_before_facade(request: PaperQualificationShadowRequest) -> None:
        require_paper_environment(request.runtime_request.environment)
        require_paper_environment(request.legacy_decision.environment)
        mismatches = _identity_mismatches(request)
        if mismatches:
            raise ShadowIdentityContinuityError(
                reason_code="SHADOW_IDENTITY_CONTINUITY_FAILED",
                safe_message="Shadow request identity does not match.",
                context=tuple(("field", field) for field in mismatches),
            )

    @staticmethod
    def _validate_facade_result(
        request: PaperQualificationShadowRequest,
        facade_result: PaperQualificationFacadeResult,
    ) -> None:
        require_paper_environment(facade_result.runtime_action.environment)
        mismatches: list[str] = []
        runtime = request.runtime_request
        if facade_result.qualification_run_id != runtime.qualification_run_id:
            mismatches.append("qualification_run_id")
        if facade_result.command_id != runtime.command_id:
            mismatches.append("command_id")
        if facade_result.correlation_id != runtime.correlation_id:
            mismatches.append("correlation_id")
        if facade_result.idempotency_key != runtime.idempotency_key:
            mismatches.append("idempotency_key")
        if facade_result.previous_revision != runtime.expected_revision:
            mismatches.append("previous_revision")
        if mismatches:
            raise ShadowIdentityContinuityError(
                reason_code="FACADE_RESULT_IDENTITY_CONTINUITY_FAILED",
                safe_message="Facade result identity does not match shadow request.",
                context=tuple(("field", field) for field in mismatches),
            )

    @staticmethod
    def _qualification_error_result(
        request: PaperQualificationShadowRequest,
        error: PaperQualificationFacadeError,
    ) -> PaperQualificationShadowResult:
        mismatch = ShadowMismatch(
            classification=ShadowMismatchClassification.IDENTITY_MISMATCH,
            field="qualification_facade",
            safe_reason=error.reason_code,
        )
        return PaperQualificationShadowResult(
            shadow_invocation_id=request.shadow_invocation_id,
            legacy_decision=request.legacy_decision,
            qualification_facade_result=None,
            comparison_status=ShadowComparisonStatus.QUALIFICATION_ERROR,
            classifications=(mismatch.classification,),
            matched_fields=(),
            mismatches=(mismatch,),
            qualification_run_id=request.runtime_request.qualification_run_id,
            command_id=request.runtime_request.command_id,
            correlation_id=request.runtime_request.correlation_id,
            idempotency_key=request.runtime_request.idempotency_key,
            transition_id=None,
            previous_revision=request.runtime_request.expected_revision,
            next_revision=None,
            legacy_action_type=request.legacy_decision.action_type,
            qualification_action_type=None,
            qualification_state=None,
            qualification_result=None,
            replayed=False,
            safe_operator_summary="Qualification facade failed before comparison.",
            action_executed=False,
            legacy_behavior_changed=False,
        )


def derive_shadow_invocation_id(
    runtime_request: PaperRuntimeRequest,
    legacy_decision: LegacyPaperDecision,
) -> str:
    """Derive a stable safe shadow identity from canonical fields."""

    order = legacy_decision.order_intent or runtime_request.order_intent
    return derive_integration_identity(
        "qis",
        (
            "shadow",
            _environment_identity(runtime_request.environment),
            runtime_request.runtime_request_id,
            legacy_decision.legacy_decision_id,
            runtime_request.qualification_run_id,
            runtime_request.command_id,
            runtime_request.correlation_id,
            runtime_request.idempotency_key,
            str(runtime_request.expected_revision),
            runtime_request.request_kind.value,
            legacy_decision.decision_type.value,
            legacy_decision.action_type.value,
            _order_identity(order),
        ),
    )


def compare_legacy_to_qualification(
    request: PaperQualificationShadowRequest,
    facade_result: PaperQualificationFacadeResult,
) -> PaperQualificationShadowResult:
    """Compare a legacy Paper decision with one facade result."""

    matched: list[str] = []
    mismatches: list[ShadowMismatch] = []
    legacy = request.legacy_decision
    action = facade_result.runtime_action

    _record_match_or_mismatch(
        legacy.environment == action.environment,
        matched,
        mismatches,
        field="environment",
        classification=ShadowMismatchClassification.ENVIRONMENT_MISMATCH,
        reason="Paper environment differs.",
    )
    _compare_action_kind(legacy, action.action_kind, matched, mismatches)
    _compare_order_intent(
        legacy, request.runtime_request, facade_result, matched, mismatches
    )
    _compare_approval(legacy, action.action_kind, matched, mismatches)
    _compare_revision(request, facade_result, matched, mismatches)
    _compare_replay(legacy, facade_result, matched, mismatches)
    _compare_terminal_result(legacy, facade_result, matched, mismatches)

    classifications = tuple(mismatch.classification for mismatch in mismatches)
    status = _status_for(mismatches, facade_result)
    return PaperQualificationShadowResult(
        shadow_invocation_id=request.shadow_invocation_id,
        legacy_decision=legacy,
        qualification_facade_result=facade_result,
        comparison_status=status,
        classifications=classifications,
        matched_fields=tuple(sorted(matched)),
        mismatches=tuple(
            sorted(mismatches, key=lambda item: (item.field, item.classification.value))
        ),
        qualification_run_id=facade_result.qualification_run_id,
        command_id=facade_result.command_id,
        correlation_id=facade_result.correlation_id,
        idempotency_key=facade_result.idempotency_key,
        transition_id=facade_result.transition_id,
        previous_revision=facade_result.previous_revision,
        next_revision=facade_result.next_revision,
        legacy_action_type=legacy.action_type,
        qualification_action_type=action.action_kind,
        qualification_state=facade_result.qualification_state,
        qualification_result=facade_result.qualification_result,
        replayed=facade_result.replayed,
        safe_operator_summary=_summary_for(status),
        action_executed=False,
        legacy_behavior_changed=False,
    )


def _identity_mismatches(request: PaperQualificationShadowRequest) -> list[str]:
    runtime = request.runtime_request
    legacy = request.legacy_decision
    mismatches: list[str] = []
    if legacy.environment != runtime.environment:
        mismatches.append("environment")
    if legacy.runtime_request_id != runtime.runtime_request_id:
        mismatches.append("runtime_request_id")
    if legacy.qualification_run_id != runtime.qualification_run_id:
        mismatches.append("qualification_run_id")
    if legacy.command_id != runtime.command_id:
        mismatches.append("command_id")
    if legacy.correlation_id != runtime.correlation_id:
        mismatches.append("correlation_id")
    if legacy.idempotency_key != runtime.idempotency_key:
        mismatches.append("idempotency_key")
    if legacy.expected_revision != runtime.expected_revision:
        mismatches.append("expected_revision")
    if legacy.order_intent is not None and runtime.order_intent is not None:
        if _order_identity(legacy.order_intent) != _order_identity(
            runtime.order_intent
        ):
            mismatches.append("order_intent")
    return mismatches


def _compare_action_kind(
    legacy: LegacyPaperDecision,
    qualification_action: RuntimeActionKind,
    matched: list[str],
    mismatches: list[ShadowMismatch],
) -> None:
    acceptable = _acceptable_qualification_actions(legacy.decision_type)
    if qualification_action in acceptable:
        matched.append("action_kind")
        return
    if not acceptable:
        mismatches.append(
            ShadowMismatch(
                ShadowMismatchClassification.UNSUPPORTED_LEGACY_DECISION,
                "legacy_decision_type",
                "Legacy decision type is not comparable.",
            )
        )
        return
    classification = ShadowMismatchClassification.ACTION_KIND_MISMATCH
    if (
        legacy.decision_type
        in {
            LegacyPaperDecisionType.PROCEED,
            LegacyPaperDecisionType.REQUEST_SUBMISSION,
        }
        and qualification_action is RuntimeActionKind.BLOCK_CONSEQUENTIAL_ACTION
    ):
        classification = (
            ShadowMismatchClassification.LEGACY_PROCEEDS_QUALIFICATION_BLOCKS
        )
    elif (
        legacy.decision_type is LegacyPaperDecisionType.BLOCK
        and qualification_action is not RuntimeActionKind.BLOCK_CONSEQUENTIAL_ACTION
    ):
        classification = (
            ShadowMismatchClassification.LEGACY_BLOCKS_QUALIFICATION_PROCEEDS
        )
    elif legacy.decision_type is LegacyPaperDecisionType.REQUEST_CANCELLATION:
        classification = ShadowMismatchClassification.CANCELLATION_MISMATCH
    elif legacy.decision_type is LegacyPaperDecisionType.REQUEST_RECONCILIATION:
        classification = ShadowMismatchClassification.RECONCILIATION_MISMATCH
    elif legacy.decision_type is LegacyPaperDecisionType.EMERGENCY_STOP:
        classification = ShadowMismatchClassification.EMERGENCY_STOP_MISMATCH
    mismatches.append(
        ShadowMismatch(
            classification,
            "action_kind",
            "Legacy action and qualification action differ.",
        )
    )


def _acceptable_qualification_actions(
    decision_type: LegacyPaperDecisionType,
) -> frozenset[RuntimeActionKind]:
    if decision_type is LegacyPaperDecisionType.NO_ACTION:
        return frozenset(
            {
                RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED,
                RuntimeActionKind.FINALIZE_WITHOUT_EXTERNAL_EFFECT,
            }
        )
    if decision_type is LegacyPaperDecisionType.PROCEED:
        return frozenset(
            {
                RuntimeActionKind.PREPARE_BROKER_SUBMISSION,
                RuntimeActionKind.REQUEST_BROKER_SUBMISSION,
                RuntimeActionKind.NO_RUNTIME_ACTION_REQUIRED,
            }
        )
    if decision_type is LegacyPaperDecisionType.REQUEST_SUBMISSION:
        return frozenset({RuntimeActionKind.REQUEST_BROKER_SUBMISSION})
    if decision_type is LegacyPaperDecisionType.REQUEST_CANCELLATION:
        return frozenset({RuntimeActionKind.REQUEST_BROKER_CANCELLATION})
    if decision_type is LegacyPaperDecisionType.REQUEST_RECONCILIATION:
        return frozenset({RuntimeActionKind.START_RECONCILIATION})
    if decision_type in {
        LegacyPaperDecisionType.BLOCK,
        LegacyPaperDecisionType.ABORT,
        LegacyPaperDecisionType.EMERGENCY_STOP,
    }:
        return frozenset({RuntimeActionKind.BLOCK_CONSEQUENTIAL_ACTION})
    return frozenset()


def _compare_order_intent(
    legacy: LegacyPaperDecision,
    runtime_request: PaperRuntimeRequest,
    facade_result: PaperQualificationFacadeResult,
    matched: list[str],
    mismatches: list[ShadowMismatch],
) -> None:
    if legacy.decision_type not in {
        LegacyPaperDecisionType.PROCEED,
        LegacyPaperDecisionType.REQUEST_SUBMISSION,
    }:
        return
    legacy_order = legacy.order_intent or runtime_request.order_intent
    qualification_order = facade_result.runtime_action.order_intent
    if legacy_order is None and qualification_order is None:
        mismatches.append(
            ShadowMismatch(
                ShadowMismatchClassification.INSUFFICIENT_COMPARISON_FACTS,
                "order_intent",
                "No safe order intent facts were supplied.",
            )
        )
        return
    if legacy_order is None or qualification_order is None:
        mismatches.append(
            ShadowMismatch(
                ShadowMismatchClassification.INSUFFICIENT_COMPARISON_FACTS,
                "order_intent",
                "Only one side supplied safe order intent facts.",
            )
        )
        return
    if _order_identity(legacy_order) == _order_identity(qualification_order):
        matched.append("order_intent")
        return
    mismatches.append(
        ShadowMismatch(
            ShadowMismatchClassification.ORDER_INTENT_MISMATCH,
            _order_mismatch_field(legacy_order, qualification_order),
            "Safe order intent facts differ.",
        )
    )


def _compare_approval(
    legacy: LegacyPaperDecision,
    qualification_action: RuntimeActionKind,
    matched: list[str],
    mismatches: list[ShadowMismatch],
) -> None:
    if legacy.approved is None:
        return
    qualification_allows = qualification_action not in {
        RuntimeActionKind.BLOCK_CONSEQUENTIAL_ACTION,
    }
    if legacy.approved == qualification_allows:
        matched.append("approval")
        return
    mismatches.append(
        ShadowMismatch(
            ShadowMismatchClassification.APPROVAL_MISMATCH,
            "approval",
            "Legacy approval and qualification allowance differ.",
        )
    )


def _compare_revision(
    request: PaperQualificationShadowRequest,
    facade_result: PaperQualificationFacadeResult,
    matched: list[str],
    mismatches: list[ShadowMismatch],
) -> None:
    if facade_result.previous_revision == request.runtime_request.expected_revision:
        matched.append("previous_revision")
    else:
        mismatches.append(
            ShadowMismatch(
                ShadowMismatchClassification.REVISION_MISMATCH,
                "previous_revision",
                "Qualification revision differs from expected revision.",
            )
        )


def _compare_replay(
    legacy: LegacyPaperDecision,
    facade_result: PaperQualificationFacadeResult,
    matched: list[str],
    mismatches: list[ShadowMismatch],
) -> None:
    legacy_replay = ("replay", True) in legacy.metadata
    if legacy_replay == facade_result.replayed:
        matched.append("replay")
        return
    mismatches.append(
        ShadowMismatch(
            ShadowMismatchClassification.REPLAY_MISMATCH,
            "replay",
            "Legacy replay marker and qualification replay flag differ.",
        )
    )


def _compare_terminal_result(
    legacy: LegacyPaperDecision,
    facade_result: PaperQualificationFacadeResult,
    matched: list[str],
    mismatches: list[ShadowMismatch],
) -> None:
    if facade_result.qualification_result is None:
        return
    if facade_result.qualification_result is QualificationResult.INCONCLUSIVE:
        mismatches.append(
            ShadowMismatch(
                ShadowMismatchClassification.INSUFFICIENT_COMPARISON_FACTS,
                "qualification_result",
                "Qualification result is inconclusive.",
            )
        )
        return
    if (
        legacy.decision_type is LegacyPaperDecisionType.BLOCK
        and facade_result.qualification_result is QualificationResult.PASSED
    ):
        mismatches.append(
            ShadowMismatch(
                ShadowMismatchClassification.TERMINAL_RESULT_MISMATCH,
                "qualification_result",
                "Legacy blocked while qualification terminal result passed.",
            )
        )
        return
    matched.append("qualification_result")


def _status_for(
    mismatches: list[ShadowMismatch],
    facade_result: PaperQualificationFacadeResult,
) -> ShadowComparisonStatus:
    if not mismatches:
        return ShadowComparisonStatus.MATCH
    classifications = {mismatch.classification for mismatch in mismatches}
    if classifications == {ShadowMismatchClassification.REPLAY_MISMATCH}:
        return ShadowComparisonStatus.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE
    if classifications <= {ShadowMismatchClassification.INSUFFICIENT_COMPARISON_FACTS}:
        return ShadowComparisonStatus.INCOMPARABLE
    if facade_result.qualification_result is QualificationResult.INCONCLUSIVE:
        return ShadowComparisonStatus.INCOMPARABLE
    return ShadowComparisonStatus.MISMATCH


def _summary_for(status: ShadowComparisonStatus) -> str:
    if status is ShadowComparisonStatus.MATCH:
        return "Shadow comparison matched without changing runtime behavior."
    if status is ShadowComparisonStatus.MATCH_WITH_NONCONSEQUENTIAL_DIFFERENCE:
        return "Shadow comparison matched with a nonconsequential difference."
    if status is ShadowComparisonStatus.INCOMPARABLE:
        return "Shadow comparison lacked enough safe facts to compare."
    if status is ShadowComparisonStatus.QUALIFICATION_ERROR:
        return "Qualification facade failed before comparison."
    if status is ShadowComparisonStatus.INVALID_SHADOW_INPUT:
        return "Shadow input was invalid."
    return "Shadow comparison found a consequential mismatch."


def _record_match_or_mismatch(
    condition: bool,
    matched: list[str],
    mismatches: list[ShadowMismatch],
    *,
    field: str,
    classification: ShadowMismatchClassification,
    reason: str,
) -> None:
    if condition:
        matched.append(field)
    else:
        mismatches.append(ShadowMismatch(classification, field, reason))


def _order_identity(order: SafeOrderIntent | None) -> str:
    if order is None:
        return ""
    return "|".join(
        (
            order.symbol,
            str(order.quantity),
            order.order_type.value,
            _decimal_identity(order.limit_price),
            order.time_in_force.value if order.time_in_force is not None else "",
        )
    )


def _order_mismatch_field(left: SafeOrderIntent, right: SafeOrderIntent) -> str:
    if left.symbol != right.symbol:
        return "symbol"
    if left.quantity != right.quantity:
        return "quantity"
    if left.order_type != right.order_type:
        return "order_type"
    if left.limit_price != right.limit_price:
        return "limit_price"
    if left.time_in_force != right.time_in_force:
        return "time_in_force"
    return "order_intent"


def _decimal_identity(value: Decimal | None) -> str:
    return "" if value is None else format(value, "f")


def _environment_identity(value: object) -> str:
    if isinstance(value, PaperIntegrationEnvironment):
        return value.value
    if value is None:
        return ""
    return str(value)


def _validate_identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ShadowInputValidationError(
            reason_code="INVALID_SHADOW_IDENTIFIER",
            safe_message=f"{name} is invalid.",
        )
    _ensure_safe_text(value)
    return value


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


def _ensure_safe_text(value: str) -> None:
    lowered = value.lower()
    if any(marker in lowered for marker in _SECRET_MARKERS):
        raise ShadowInputValidationError(
            reason_code="UNSAFE_SHADOW_METADATA",
            safe_message="Shadow input contains unsafe metadata.",
        )
