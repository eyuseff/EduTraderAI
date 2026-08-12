"""Immutable orchestration policies used by ExecutionSupervisor."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from volcanoes.application.supervisor.contracts import ExecutionRequest
from volcanoes.events import PolicyConfiguration


@dataclass(frozen=True, slots=True)
class SupervisorPolicyDecision:
    approved: bool
    code: str
    policy: str
    explanation: str
    configuration: PolicyConfiguration = ()


@dataclass(frozen=True, slots=True)
class CooldownPolicy:
    """Prevent rapid successive executions for one symbol."""

    window: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        if self.window < timedelta(0):
            raise ValueError("cooldown window cannot be negative.")

    def evaluate(
        self,
        request: ExecutionRequest,
        *,
        last_execution_at: datetime | None,
        now: datetime,
    ) -> SupervisorPolicyDecision:
        remaining = timedelta(0)
        if last_execution_at is not None:
            remaining = self.window - (now - last_execution_at)
        approved = remaining <= timedelta(0)
        return SupervisorPolicyDecision(
            approved=approved,
            code="COOLDOWN_CLEAR" if approved else "COOLDOWN_ACTIVE",
            policy=type(self).__name__,
            explanation=(
                "No execution cooldown is active for this symbol."
                if approved
                else "Execution skipped because the symbol cooldown is active."
            ),
            configuration=(
                ("window_seconds", str(self.window.total_seconds())),
                ("remaining_seconds", str(max(0.0, remaining.total_seconds()))),
            ),
        )


@dataclass(frozen=True, slots=True)
class DuplicateExecutionPolicy:
    """Reject an identical successful or currently active trade request."""

    def evaluate(
        self,
        request: ExecutionRequest,
        *,
        fingerprints: frozenset[tuple[str, ...]],
    ) -> SupervisorPolicyDecision:
        duplicate = request.fingerprint in fingerprints
        return SupervisorPolicyDecision(
            approved=not duplicate,
            code="UNIQUE_EXECUTION" if not duplicate else "DUPLICATE_EXECUTION",
            policy=type(self).__name__,
            explanation=(
                "No identical execution is active or already submitted."
                if not duplicate
                else "An identical execution is active or already submitted."
            ),
            configuration=(("fingerprint", "|".join(request.fingerprint)),),
        )


@dataclass(frozen=True, slots=True)
class ConcurrentSymbolPolicy:
    """Allow at most one active execution workflow per symbol."""

    def evaluate(
        self,
        request: ExecutionRequest,
        *,
        active_symbols: frozenset[str],
    ) -> SupervisorPolicyDecision:
        active = request.symbol in active_symbols
        return SupervisorPolicyDecision(
            approved=not active,
            code="SYMBOL_AVAILABLE" if not active else "SYMBOL_BUSY",
            policy=type(self).__name__,
            explanation=(
                "No execution workflow is active for this symbol."
                if not active
                else "Another execution workflow is active for this symbol."
            ),
            configuration=(("symbol", request.symbol),),
        )


@dataclass(frozen=True, slots=True)
class MarketStatePolicy:
    """Stub orchestration gate for a future authoritative market-state port."""

    require_open: bool = False

    def evaluate(self, request: ExecutionRequest) -> SupervisorPolicyDecision:
        observed_state = request.market_state or "UNAVAILABLE"
        approved = not self.require_open or observed_state == "OPEN"
        return SupervisorPolicyDecision(
            approved=approved,
            code="MARKET_STATE_CLEAR" if approved else "MARKET_STATE_BLOCKED",
            policy=type(self).__name__,
            explanation=(
                "Market-state enforcement is disabled or the market is open."
                if approved
                else "Execution skipped because market state is not OPEN."
            ),
            configuration=(
                ("observed_state", observed_state),
                ("require_open", str(self.require_open).lower()),
            ),
        )
