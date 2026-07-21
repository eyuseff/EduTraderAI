"""Immutable contracts for supervised execution orchestration."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum

from volcanoes.application.services.preview_trade import PreviewTradeResult
from volcanoes.application.services.submit_trade import SubmitTradeResult
from volcanoes.domain import TradeSide
from volcanoes.events import PolicyConfiguration, new_correlation_id
from volcanoes.risk.portfolio_view import RiskPortfolioView


class ExecutionSource(StrEnum):
    """Origin of an execution request."""

    HUMAN = "HUMAN"
    AUTOMATION = "AUTOMATION"


class ExecutionMode(StrEnum):
    """Whether an admitted request previews or submits a trade."""

    PREVIEW_ONLY = "PREVIEW_ONLY"
    SUBMIT = "SUBMIT"


@dataclass(frozen=True, slots=True)
class ExecutionSnapshot:
    """Immutable application input containing one execution-state snapshot."""

    portfolio: RiskPortfolioView
    open_order_symbols: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        if not isinstance(self.portfolio, RiskPortfolioView):
            raise TypeError("portfolio must satisfy RiskPortfolioView.")
        object.__setattr__(
            self,
            "open_order_symbols",
            frozenset(
                symbol.strip().upper()
                for symbol in self.open_order_symbols
                if symbol.strip()
            ),
        )


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """Canonical immutable request accepted by the execution supervisor."""

    symbol: str
    side: TradeSide
    entry_price: Decimal
    stop_price: Decimal
    target_price: Decimal
    idempotency_key: str
    source: ExecutionSource
    correlation_id: str = field(default_factory=new_correlation_id)
    market_state: str | None = None
    mode: ExecutionMode = ExecutionMode.SUBMIT

    def __post_init__(self) -> None:
        normalized_symbol = self.symbol.strip().upper()
        if not normalized_symbol:
            raise ValueError("symbol cannot be empty.")
        if not isinstance(self.side, TradeSide):
            raise TypeError("side must be a TradeSide value.")
        for name in ("entry_price", "stop_price", "target_price"):
            if not isinstance(getattr(self, name), Decimal):
                raise TypeError(f"{name} must be a Decimal.")
        if not self.idempotency_key.strip():
            raise ValueError("idempotency_key cannot be empty.")
        if not isinstance(self.source, ExecutionSource):
            raise TypeError("source must be an ExecutionSource value.")
        if not isinstance(self.mode, ExecutionMode):
            raise TypeError("mode must be an ExecutionMode value.")
        if not self.correlation_id.strip():
            raise ValueError("correlation_id cannot be empty.")

        object.__setattr__(self, "symbol", normalized_symbol)
        if self.market_state is not None:
            object.__setattr__(
                self,
                "market_state",
                self.market_state.strip().upper(),
            )

    @property
    def fingerprint(self) -> tuple[str, ...]:
        """Return the deterministic identity of the requested trade."""

        return (
            self.symbol,
            self.side.value,
            format(self.entry_price, "f"),
            format(self.stop_price, "f"),
            format(self.target_price, "f"),
            self.mode.value,
        )


@dataclass(frozen=True, slots=True)
class ExecutionDecision:
    """Explain whether supervisor orchestration may proceed."""

    approved: bool
    code: str
    policy: str
    explanation: str
    correlation_id: str
    configuration: PolicyConfiguration = ()


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Immutable outcome of one supervised execution request."""

    request: ExecutionRequest
    decision: ExecutionDecision
    preview: PreviewTradeResult | None = None
    submission: SubmitTradeResult | None = None
    replayed: bool = False

    @property
    def correlation_id(self) -> str:
        return self.decision.correlation_id

    @property
    def submitted(self) -> bool:
        return self.submission is not None and self.submission.submitted
