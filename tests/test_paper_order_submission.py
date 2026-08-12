"""Integration tests for deterministic manual Paper Order submission."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from adapters.paper_order_composition import build_paper_order_planner
from adapters.paper_order_preview import preview_paper_order
from adapters.paper_order_submission import submit_paper_order
from broker.base import AccountSnapshot, BrokerOrder, BrokerPosition
from trading.execution import PaperExecutionEngine
from trading.risk_manager import RiskDecision, RiskLimits, RiskManager, TradeProposal
from volcanoes.application.services import SubmitTradeResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class StatefulPaperBroker:
    name = "Stateful paper broker"
    is_paper = True

    def __init__(self) -> None:
        self.account = AccountSnapshot(
            equity=100_000.0,
            cash=100_000.0,
            buying_power=100_000.0,
        )
        self.positions: list[BrokerPosition] = []
        self.orders: list[BrokerOrder] = []
        self.calls: list[str] = []

    def get_account(self) -> AccountSnapshot:
        self.calls.append("get_account")
        return self.account

    def get_positions(self) -> list[BrokerPosition]:
        self.calls.append("get_positions")
        return list(self.positions)

    def get_open_orders(self) -> list[BrokerOrder]:
        self.calls.append("get_open_orders")
        return list(self.orders)

    def submit_bracket_order(
        self,
        *,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> BrokerOrder:
        self.calls.append("submit_bracket_order")
        order = BrokerOrder(
            order_id="manual-789",
            symbol=symbol,
            quantity=quantity,
            side="buy",
            status="accepted",
            order_type="bracket-limit",
            submitted_price=entry_price,
            stop_price=stop_price,
            target_price=target_price,
            message="Manual paper submission accepted.",
        )
        self.orders.append(order)
        return order

    def cancel_all_orders(self) -> int:
        raise AssertionError("submission cancelled orders")

    def close_all_positions(self) -> int:
        raise AssertionError("submission closed positions")


def trade() -> TradeProposal:
    return TradeProposal(
        symbol="AAPL",
        entry_price=100.0,
        stop_price=97.5,
        target_price=105.0,
    )


def preview(
    broker: StatefulPaperBroker,
    limits: RiskLimits,
) -> RiskDecision:
    legacy_engine = PaperExecutionEngine(broker, RiskManager(limits))
    return preview_paper_order(
        broker=broker,
        proposal=trade(),
        limits=limits,
        legacy_preview=legacy_engine.preview,
        use_deterministic_preview=True,
        development_mode=False,
    )


def test_deterministic_submission_uses_fresh_view_and_submits_exact_preview() -> None:
    broker = StatefulPaperBroker()
    limits = RiskLimits()
    displayed = preview(broker, limits)

    result = submit_paper_order(
        broker=broker,
        proposal=trade(),
        displayed_preview=displayed,
        limits=limits,
        confirmation="PAPER TRADE",
        legacy_submit=lambda proposal, confirmation: (_ for _ in ()).throw(
            AssertionError("legacy submit called")
        ),
        use_deterministic_submission=True,
    )

    assert isinstance(result, SubmitTradeResult)
    assert result.submitted is True
    assert result.symbol == "AAPL"
    assert result.quantity == displayed.quantity
    assert result.order_id == "manual-789"
    assert result.message == "Manual paper submission accepted."
    assert broker.calls.count("submit_bracket_order") == 1


def test_fresh_snapshot_drift_safely_rejects() -> None:
    broker = StatefulPaperBroker()
    limits = RiskLimits()
    displayed = preview(broker, limits)
    broker.account = AccountSnapshot(
        equity=100_000.0,
        cash=500.0,
        buying_power=500.0,
    )

    with pytest.raises(ValueError, match="fresh account snapshot"):
        submit_paper_order(
            broker=broker,
            proposal=trade(),
            displayed_preview=displayed,
            limits=limits,
            confirmation="PAPER TRADE",
            legacy_submit=lambda proposal, confirmation: (_ for _ in ()).throw(
                AssertionError("legacy submit called")
            ),
            use_deterministic_submission=True,
        )

    assert "submit_bracket_order" not in broker.calls


def test_second_confirmation_cannot_submit_same_symbol_again() -> None:
    broker = StatefulPaperBroker()
    limits = RiskLimits()
    displayed = preview(broker, limits)

    submit_paper_order(
        broker=broker,
        proposal=trade(),
        displayed_preview=displayed,
        limits=limits,
        confirmation="PAPER TRADE",
        legacy_submit=lambda proposal, confirmation: (_ for _ in ()).throw(
            AssertionError("legacy submit called")
        ),
        use_deterministic_submission=True,
    )

    with pytest.raises(ValueError, match="changed the previewed plan"):
        submit_paper_order(
            broker=broker,
            proposal=trade(),
            displayed_preview=displayed,
            limits=limits,
            confirmation="PAPER TRADE",
            legacy_submit=lambda proposal, confirmation: (_ for _ in ()).throw(
                AssertionError("legacy submit called")
            ),
            use_deterministic_submission=True,
        )

    assert broker.calls.count("submit_bracket_order") == 1


def test_rollback_flag_calls_legacy_submit_unchanged() -> None:
    broker = StatefulPaperBroker()
    expected = BrokerOrder(
        order_id="legacy-1",
        symbol="AAPL",
        quantity=11,
        side="buy",
        status="accepted",
        order_type="legacy",
        submitted_price=100.0,
        message="Legacy path.",
    )
    calls: list[tuple[TradeProposal, str]] = []

    def legacy_submit(proposal: TradeProposal, confirmation: str) -> BrokerOrder:
        calls.append((proposal, confirmation))
        return expected

    result = submit_paper_order(
        broker=broker,
        proposal=trade(),
        displayed_preview=RiskDecision(True, 11, 27.5, 1100.0, 2.0),
        limits=RiskLimits(),
        confirmation="as entered",
        legacy_submit=legacy_submit,
        use_deterministic_submission=False,
    )

    assert result is expected
    assert calls == [(trade(), "as entered")]
    assert broker.calls == []


def test_confirmation_guard_matches_legacy_behavior() -> None:
    broker = StatefulPaperBroker()

    with pytest.raises(PermissionError) as error:
        submit_paper_order(
            broker=broker,
            proposal=trade(),
            displayed_preview=RiskDecision(True, 100, 250.0, 10_000.0, 2.0),
            limits=RiskLimits(),
            confirmation="",
            legacy_submit=lambda proposal, confirmation: None,  # type: ignore[arg-type,return-value]
            use_deterministic_submission=True,
        )

    assert str(error.value) == 'Type "PAPER TRADE" to authorize submission.'
    assert broker.calls == []


def test_preview_and_submission_composition_build_equal_policy_profiles() -> None:
    limits = RiskLimits()
    preview_planner = build_paper_order_planner(limits)
    submission_planner = build_paper_order_planner(limits)

    assert preview_planner.policies == submission_planner.policies
    assert preview_planner.risk_manager.config == submission_planner.risk_manager.config


def test_manual_submission_adds_no_audit_or_persistence_dependency() -> None:
    source = (PROJECT_ROOT / "adapters/paper_order_submission.py").read_text(
        encoding="utf-8"
    )

    assert "audit" not in source
    assert "database" not in source
    assert "persistence" not in source


def test_app_defaults_to_deterministic_submission_and_keeps_legacy_fallback() -> None:
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    assignments = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance((target := node.targets[0]), ast.Name)
        and isinstance(node.value, ast.Constant)
    }

    assert assignments["USE_DETERMINISTIC_SUBMISSION"] is True
    assert "submit_paper_order(" in source
    assert "legacy_submit=engine.submit" in source
    assert "use_deterministic_submission=USE_DETERMINISTIC_SUBMISSION" in source
    assert "Paper order accepted: {order.symbol}, {order.quantity} shares." in source
    assert "st.info(order.message)" in source
