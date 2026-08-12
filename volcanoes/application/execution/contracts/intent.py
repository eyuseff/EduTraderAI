"""Immutable Paper execution intent."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from volcanoes.application.execution.contracts._validation import (
    normalize_alias,
    require_positive_decimal,
)
from volcanoes.application.execution.contracts.instrument import (
    PaperExecutionInstrument,
)
from volcanoes.application.execution.enums import (
    PaperExecutionOrderType,
    PaperExecutionSide,
    PaperExecutionTimeInForce,
)
from volcanoes.application.execution.errors import PaperExecutionInvariantError


@dataclass(frozen=True, slots=True)
class PaperExecutionIntent:
    """What the caller wants represented as inert broker-neutral data."""

    instrument: PaperExecutionInstrument
    side: PaperExecutionSide
    order_type: PaperExecutionOrderType
    quantity: Decimal
    time_in_force: PaperExecutionTimeInForce = PaperExecutionTimeInForce.DAY
    limit_price: Decimal | None = None
    stop_price: Decimal | None = None
    strategy_reference: str | None = None
    portfolio_reference: str | None = None
    qualification_reference: str | None = None
    qualification_revision_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.instrument, PaperExecutionInstrument):
            raise PaperExecutionInvariantError(
                "INVALID_INSTRUMENT",
                "Intent requires a PaperExecutionInstrument.",
            )
        if not isinstance(self.side, PaperExecutionSide):
            raise PaperExecutionInvariantError("INVALID_SIDE", "Unsupported side.")
        if not isinstance(self.order_type, PaperExecutionOrderType):
            raise PaperExecutionInvariantError(
                "INVALID_ORDER_TYPE",
                "Unsupported order type.",
            )
        if not isinstance(self.time_in_force, PaperExecutionTimeInForce):
            raise PaperExecutionInvariantError(
                "INVALID_TIME_IN_FORCE",
                "Unsupported time in force.",
            )
        object.__setattr__(
            self,
            "quantity",
            require_positive_decimal(self.quantity, "quantity"),
        )
        if self.limit_price is not None:
            object.__setattr__(
                self,
                "limit_price",
                require_positive_decimal(self.limit_price, "limit_price"),
            )
        if self.stop_price is not None:
            object.__setattr__(
                self,
                "stop_price",
                require_positive_decimal(self.stop_price, "stop_price"),
            )
        self._validate_price_shape()
        for field in (
            "strategy_reference",
            "portfolio_reference",
            "qualification_reference",
            "qualification_revision_reference",
        ):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, normalize_alias(value, field))

    def to_primitive(self) -> dict[str, object]:
        return {
            "instrument": self.instrument.to_primitive(),
            "limit_price": self.limit_price,
            "order_type": self.order_type,
            "portfolio_reference": self.portfolio_reference,
            "qualification_reference": self.qualification_reference,
            "qualification_revision_reference": self.qualification_revision_reference,
            "quantity": self.quantity,
            "side": self.side,
            "stop_price": self.stop_price,
            "strategy_reference": self.strategy_reference,
            "time_in_force": self.time_in_force,
        }

    def _validate_price_shape(self) -> None:
        if self.order_type is PaperExecutionOrderType.MARKET:
            if self.limit_price is not None or self.stop_price is not None:
                raise PaperExecutionInvariantError(
                    "INVALID_MARKET_PRICE_FIELDS",
                    "Market orders cannot carry limit or stop prices.",
                )
            return
        if self.order_type is PaperExecutionOrderType.LIMIT:
            if self.limit_price is None or self.stop_price is not None:
                raise PaperExecutionInvariantError(
                    "INVALID_LIMIT_PRICE_FIELDS",
                    "Limit orders require limit price and no stop price.",
                )
            return
        if self.order_type is PaperExecutionOrderType.STOP:
            if self.stop_price is None or self.limit_price is not None:
                raise PaperExecutionInvariantError(
                    "INVALID_STOP_PRICE_FIELDS",
                    "Stop orders require stop price and no limit price.",
                )
            return
        if self.order_type is PaperExecutionOrderType.STOP_LIMIT and (
            self.stop_price is None or self.limit_price is None
        ):
            raise PaperExecutionInvariantError(
                "INVALID_STOP_LIMIT_PRICE_FIELDS",
                "Stop-limit orders require stop and limit prices.",
            )


def require_intent(value: PaperExecutionIntent | None) -> PaperExecutionIntent:
    if not isinstance(value, PaperExecutionIntent):
        raise PaperExecutionInvariantError(
            "INTENT_REQUIRED",
            "This command requires a PaperExecutionIntent.",
        )
    return value
