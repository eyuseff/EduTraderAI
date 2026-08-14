"""Immutable contracts for brokerless transactional execution intake."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
from typing import Any

from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.fingerprints import (
    command_payload_fingerprint,
    fingerprint_payload,
)
from volcanoes.application.execution.identities import PaperExecutionRevision
from volcanoes.application.execution.lifecycle import (
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionLifecycleState,
)
from volcanoes.application.execution.persistence import (
    ExecutionAggregateRecord,
    ExecutionApprovalRecord,
    ExecutionCommandRecord,
    ExecutionIdempotencyRecord,
    ExecutionTransitionRecord,
)

_INITIAL_CHAIN = (
    (
        "PX-TRN-002",
        PaperExecutionLifecycleState.CREATED,
        PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
        "RECORD_ELIGIBILITY",
    ),
    (
        "PX-TRN-005",
        PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
        PaperExecutionLifecycleState.APPROVAL_CONFIRMED,
        "RECORD_APPROVAL",
    ),
    (
        "PX-TRN-006",
        PaperExecutionLifecycleState.APPROVAL_CONFIRMED,
        PaperExecutionLifecycleState.IDEMPOTENCY_RESERVED,
        "RECORD_IDEMPOTENCY_RESERVATION",
    ),
    (
        "PX-TRN-007",
        PaperExecutionLifecycleState.IDEMPOTENCY_RESERVED,
        PaperExecutionLifecycleState.READY_FOR_DISPATCH,
        "PREPARE_DISPATCH",
    ),
    (
        "PX-TRN-008",
        PaperExecutionLifecycleState.READY_FOR_DISPATCH,
        PaperExecutionLifecycleState.DISPATCH_PENDING,
        "RECORD_DISPATCH_PENDING",
    ),
)


class TransactionalIntakeStatus(StrEnum):
    """Bounded outcomes returned by transactional intake."""

    ACCEPTED_FOR_DISPATCH = "ACCEPTED_FOR_DISPATCH"
    EXACT_REPLAY = "EXACT_REPLAY"
    LOGICAL_REPLAY = "LOGICAL_REPLAY"
    COMMAND_CONFLICT = "COMMAND_CONFLICT"
    IDEMPOTENCY_CONFLICT = "IDEMPOTENCY_CONFLICT"
    STALE_REVISION = "STALE_REVISION"
    TRANSACTION_ABORTED = "TRANSACTION_ABORTED"


@dataclass(frozen=True, slots=True)
class TransactionalIntakeRequest:
    """A complete inert write set for one atomic dispatch handoff."""

    command: ExecutionCommandRecord
    idempotency: ExecutionIdempotencyRecord
    approval: ExecutionApprovalRecord
    aggregate: ExecutionAggregateRecord
    transitions: tuple[ExecutionTransitionRecord, ...]
    expected_revision: PaperExecutionRevision

    def __post_init__(self) -> None:
        if int(self.expected_revision) != 0:
            raise ValueError("Transactional intake requires expected revision zero.")
        if self.command.expected_execution_revision != self.expected_revision:
            raise ValueError("Command and request expected revisions must match zero.")
        if not isinstance(self.transitions, tuple) or len(self.transitions) != len(
            _INITIAL_CHAIN
        ):
            raise ValueError("Transactional intake requires the exact initial chain.")
        if self.command.aggregate_id != self.aggregate.aggregate_id:
            raise ValueError("Command and aggregate identities must match.")
        if self.command.correlation_id != self.aggregate.correlation_id:
            raise ValueError("Command and aggregate correlations must match.")
        if self.command.command_id != self.idempotency.command_id:
            raise ValueError("Command and idempotency command identities must match.")
        if self.command.idempotency_key != self.idempotency.idempotency_key:
            raise ValueError("Command and idempotency keys must match.")
        if self.command.aggregate_id != self.idempotency.aggregate_id:
            raise ValueError("Idempotency and aggregate identities must match.")
        if self.command.operation.value != "SUBMIT":
            raise ValueError(
                "Transactional intake accepts initial submit commands only."
            )
        canonical_payload = _strict_canonical_payload(
            self.command.canonical_command_json
        )
        if (
            command_payload_fingerprint(canonical_payload)
            != self.command.canonical_payload_fingerprint
        ):
            raise ValueError(
                "Command payload fingerprint does not match canonical JSON."
            )
        if (
            fingerprint_payload("plo", canonical_payload)
            != self.idempotency.logical_operation_fingerprint
        ):
            raise ValueError(
                "Idempotency logical-operation fingerprint does not match canonical JSON."
            )
        if self.approval.approval_fingerprint != self.command.approval_fingerprint:
            raise ValueError("Approval fingerprint must match the command.")
        if (
            self.approval.bound_fingerprint
            != self.command.canonical_payload_fingerprint
        ):
            raise ValueError("Approval evidence must bind to the command payload.")
        if self.approval.mode is not self.command.mode:
            raise ValueError("Approval and command modes must match.")
        if self.approval.schema_version != self.command.schema_version:
            raise ValueError("Approval and command schema versions must match.")
        schema_version = self.command.schema_version
        if (
            self.idempotency.schema_version != schema_version
            or self.aggregate.schema_version != schema_version
            or any(
                transition.schema_version != schema_version
                for transition in self.transitions
            )
        ):
            raise ValueError("Every intake record must share one schema version.")
        if self.aggregate.cumulative_filled_quantity != 0:
            raise ValueError("Initial intake requires zero cumulative filled quantity.")

        previous = self.expected_revision
        previous_destination = PaperExecutionLifecycleState.CREATED
        for transition, expected_edge in zip(
            self.transitions, _INITIAL_CHAIN, strict=True
        ):
            if (
                transition.aggregate_id != self.command.aggregate_id
                or transition.command_id != self.command.command_id
                or transition.correlation_id != self.command.correlation_id
                or transition.idempotency_key != self.command.idempotency_key
            ):
                raise ValueError("Every transition must bind to the intake command.")
            if transition.previous_revision != previous:
                raise ValueError("Transition revisions must form one contiguous chain.")
            if int(transition.next_revision) != int(transition.previous_revision) + 1:
                raise ValueError("Every transition must advance exactly one revision.")
            expected_id, expected_source, expected_destination, expected_input = (
                expected_edge
            )
            if transition.source_state is not previous_destination:
                raise ValueError(
                    "Transition source must equal the preceding destination."
                )
            if (
                transition.source_state is not expected_source
                or transition.destination_state is not expected_destination
                or transition.lifecycle_input_kind.value != expected_input
                or transition.transition_id != expected_id
            ):
                raise ValueError(
                    "Transactional intake contains a noncanonical lifecycle edge."
                )
            previous = transition.next_revision
            previous_destination = transition.destination_state

        if int(previous) != 5:
            raise ValueError("The initial intake chain must finish at revision five.")

        for transition in self.transitions[:-1]:
            if transition.side_effect_intent_kinds != (
                PaperExecutionLifecycleSideEffectIntentKind.NONE,
            ):
                raise ValueError(
                    "Only the final transition may contain dispatch side-effect intent."
                )

        final = self.transitions[-1]
        if final.destination_state is not PaperExecutionLifecycleState.DISPATCH_PENDING:
            raise ValueError("Transactional intake must end at DISPATCH_PENDING.")
        if final.side_effect_intent_kinds != (
            PaperExecutionLifecycleSideEffectIntentKind.WOULD_DISPATCH,
        ):
            raise ValueError(
                "The final transition must durably describe dispatch intent."
            )
        if self.aggregate.lifecycle_state is not final.destination_state:
            raise ValueError("Aggregate state must match the final transition.")
        if self.aggregate.execution_revision != final.next_revision:
            raise ValueError("Aggregate revision must match the final transition.")
        if self.aggregate.last_command_id != self.command.command_id:
            raise ValueError("Aggregate must retain the intake command identity.")
        if self.aggregate.last_idempotency_key != self.command.idempotency_key:
            raise ValueError("Aggregate must retain the intake idempotency key.")


def _strict_canonical_payload(value: str) -> Any:
    def reject_constant(constant: str) -> None:
        raise ValueError(f"Non-finite JSON constant is forbidden: {constant}.")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("Canonical command JSON contains a duplicate key.")
            result[key] = item
        return result

    try:
        payload = json.loads(
            value,
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("Canonical command JSON is malformed.") from error
    if not isinstance(payload, dict):
        raise ValueError("Canonical command JSON must contain an object payload.")
    try:
        canonical = canonical_json_text(payload)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Canonical command JSON contains unsupported values."
        ) from error
    if canonical != value:
        raise ValueError("Canonical command JSON is not in canonical form.")
    return payload


@dataclass(frozen=True, slots=True)
class TransactionalIntakeResult:
    """Deterministic brokerless intake outcome."""

    status: TransactionalIntakeStatus
    committed: bool
    command_id: str
    aggregate_id: str
    final_revision: int | None
    durable_dispatch_intent: bool
    source_result_fingerprint: str
    result_fingerprint: str = field(init=False)

    def __post_init__(self) -> None:
        accepted = self.status is TransactionalIntakeStatus.ACCEPTED_FOR_DISPATCH
        if accepted:
            if not self.committed or not self.durable_dispatch_intent:
                raise ValueError(
                    "Accepted intake must be committed with durable intent."
                )
            if self.final_revision is None:
                raise ValueError("Accepted intake requires a final revision.")
        elif (
            self.committed
            or self.durable_dispatch_intent
            or self.final_revision is not None
        ):
            raise ValueError("Nonaccepted intake cannot claim committed durable state.")
        object.__setattr__(
            self,
            "result_fingerprint",
            fingerprint_payload(
                "pti",
                (
                    self.status,
                    self.committed,
                    self.command_id,
                    self.aggregate_id,
                    self.final_revision,
                    self.durable_dispatch_intent,
                    self.source_result_fingerprint,
                ),
            ),
        )
