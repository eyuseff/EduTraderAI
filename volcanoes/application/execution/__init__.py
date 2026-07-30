"""Immutable Paper execution contract vocabulary.

This package defines inert values only. It contains no executor, broker
adapter, persistence, runtime wiring, or approval decision logic.
"""

from volcanoes.application.execution.contracts import (
    PaperExecutionApproval,
    PaperExecutionCommand,
    PaperExecutionContext,
    PaperExecutionFailure,
    PaperExecutionInstrument,
    PaperExecutionIntent,
    PaperExecutionPolicySnapshot,
    PaperExecutionReceipt,
)
from volcanoes.application.execution.enums import (
    PaperExecutionApprovalKind,
    PaperExecutionFailureKind,
    PaperExecutionFailureSeverity,
    PaperExecutionMode,
    PaperExecutionOperation,
    PaperExecutionOrderType,
    PaperExecutionReceiptKind,
    PaperExecutionSide,
    PaperExecutionStatus,
    PaperExecutionTimeInForce,
)
from volcanoes.application.execution.eligibility import (
    PaperExecutionEligibilityCriterion,
    PaperExecutionEligibilityCriterionOutcome,
    PaperExecutionEligibilityCriterionResult,
    PaperExecutionEligibilityDecision,
    PaperExecutionEligibilityError,
    PaperExecutionEligibilityFailureCode,
    PaperExecutionEligibilityPolicy,
    PaperExecutionEligibilityResult,
    PaperExecutionEligibilityService,
    PaperExecutionEligibilitySeverity,
)
from volcanoes.application.execution.errors import (
    PaperExecutionContractError,
    PaperExecutionIdentityError,
    PaperExecutionInvariantError,
    PaperExecutionRevisionError,
    PaperExecutionSerializationError,
)
from volcanoes.application.execution.identities import (
    PaperBrokerOrderReference,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)

__all__ = [
    "PaperBrokerOrderReference",
    "PaperExecutionAggregateId",
    "PaperExecutionApproval",
    "PaperExecutionApprovalKind",
    "PaperExecutionCommand",
    "PaperExecutionCommandId",
    "PaperExecutionContext",
    "PaperExecutionContractError",
    "PaperExecutionCorrelationId",
    "PaperExecutionEligibilityCriterion",
    "PaperExecutionEligibilityCriterionOutcome",
    "PaperExecutionEligibilityCriterionResult",
    "PaperExecutionEligibilityDecision",
    "PaperExecutionEligibilityError",
    "PaperExecutionEligibilityFailureCode",
    "PaperExecutionEligibilityPolicy",
    "PaperExecutionEligibilityResult",
    "PaperExecutionEligibilityService",
    "PaperExecutionEligibilitySeverity",
    "PaperExecutionFailure",
    "PaperExecutionFailureKind",
    "PaperExecutionFailureSeverity",
    "PaperExecutionIdentityError",
    "PaperExecutionIdempotencyKey",
    "PaperExecutionInstrument",
    "PaperExecutionIntent",
    "PaperExecutionInvariantError",
    "PaperExecutionMode",
    "PaperExecutionOperation",
    "PaperExecutionOrderType",
    "PaperExecutionPolicySnapshot",
    "PaperExecutionReceipt",
    "PaperExecutionReceiptKind",
    "PaperExecutionRevision",
    "PaperExecutionRevisionError",
    "PaperExecutionSerializationError",
    "PaperExecutionSide",
    "PaperExecutionStatus",
    "PaperExecutionTimeInForce",
]
