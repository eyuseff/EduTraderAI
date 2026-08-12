"""Immutable Paper execution context."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from volcanoes.application.execution.contracts._validation import (
    SafeMetadata,
    normalize_alias,
    normalize_metadata,
    require_datetime,
)
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionCorrelationId,
)


@dataclass(frozen=True, slots=True)
class PaperExecutionContext:
    """Safe request context with no runtime handles or credentials."""

    aggregate_id: PaperExecutionAggregateId
    correlation_id: PaperExecutionCorrelationId
    source_component: str
    requested_at: datetime
    strategy_reference: str | None = None
    portfolio_reference: str | None = None
    account_alias: str | None = None
    trace_reference: str | None = None
    qualification_reference: str | None = None
    metadata: SafeMetadata = ()

    def __post_init__(self) -> None:
        if not isinstance(self.aggregate_id, PaperExecutionAggregateId):
            raise TypeError("aggregate_id must be a PaperExecutionAggregateId.")
        if not isinstance(self.correlation_id, PaperExecutionCorrelationId):
            raise TypeError("correlation_id must be a PaperExecutionCorrelationId.")
        object.__setattr__(
            self,
            "source_component",
            normalize_alias(self.source_component, "source_component"),
        )
        object.__setattr__(
            self,
            "requested_at",
            require_datetime(self.requested_at, "requested_at"),
        )
        for field_name in (
            "strategy_reference",
            "portfolio_reference",
            "account_alias",
            "trace_reference",
            "qualification_reference",
        ):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, normalize_alias(value, field_name))
        object.__setattr__(self, "metadata", normalize_metadata(self.metadata))

    def to_primitive(self) -> dict[str, object]:
        return {
            "account_alias": self.account_alias,
            "aggregate_id": self.aggregate_id,
            "correlation_id": self.correlation_id,
            "metadata": self.metadata,
            "portfolio_reference": self.portfolio_reference,
            "qualification_reference": self.qualification_reference,
            "requested_at": self.requested_at,
            "source_component": self.source_component,
            "strategy_reference": self.strategy_reference,
            "trace_reference": self.trace_reference,
        }
