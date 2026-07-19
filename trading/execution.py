from __future__ import annotations

from broker.base import BrokerOrder, PaperBroker
from .risk_manager import RiskDecision, RiskManager, TradeProposal


class PaperExecutionEngine:
    """Coordinates risk approval and paper-only order submission."""

    def __init__(self, broker: PaperBroker, risk_manager: RiskManager) -> None:
        if not broker.is_paper:
            raise ValueError("EduTrader v3.1 refuses non-paper broker connections.")
        self.broker = broker
        self.risk_manager = risk_manager

    def preview(self, proposal: TradeProposal) -> RiskDecision:
        account = self.broker.get_account()
        positions = self.broker.get_positions()
        open_orders = self.broker.get_open_orders()
        return self.risk_manager.evaluate(
            proposal=proposal,
            account=account,
            positions=positions,
            open_order_symbols={order.symbol for order in open_orders},
        )

    def submit(self, proposal: TradeProposal, confirmation: str) -> BrokerOrder:
        if confirmation.strip().upper() != "PAPER TRADE":
            raise PermissionError('Type "PAPER TRADE" to authorize submission.')

        decision = self.preview(proposal)
        if not decision.approved:
            raise ValueError("Risk checks failed: " + "; ".join(decision.reasons))

        return self.broker.submit_bracket_order(
            symbol=proposal.symbol,
            quantity=decision.quantity,
            entry_price=proposal.entry_price,
            stop_price=proposal.stop_price,
            target_price=proposal.target_price,
        )
