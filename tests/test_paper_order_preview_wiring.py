"""Tests for the Streamlit Paper Order preview composition boundary."""

from __future__ import annotations

import ast
import logging
from decimal import Decimal
from pathlib import Path

import pytest

from adapters.paper_order_preview import (
    ParityClassification,
    compare_preview_decisions,
    preview_paper_order,
)
from adapters.paper_order_presentation import (
    REJECTED_APPROVED_QUANTITY,
    approved_quantity_display,
)
from broker.base import (
    AccountSnapshot,
    BrokerOrder,
    BrokerPosition,
)
from trading.execution import PaperExecutionEngine
from trading.risk_manager import (
    RiskDecision,
    RiskLimits,
    RiskManager,
    TradeProposal,
)
from volcanoes.application.services import PreviewTradeResult

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class RecordingBroker:
    """Paper broker fake that rejects every mutation method."""

    name = "Recording broker"
    is_paper = True

    def __init__(
        self,
        *,
        account: AccountSnapshot | None = None,
        positions: list[BrokerPosition] | None = None,
        orders: list[BrokerOrder] | None = None,
    ) -> None:
        self.account = account or AccountSnapshot(
            equity=100_000.0,
            cash=100_000.0,
            buying_power=100_000.0,
            daily_pnl=0.0,
            paper=True,
        )
        self.positions = positions or []
        self.orders = orders or []
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
        raise AssertionError("preview submitted a broker order")

    def cancel_all_orders(self) -> int:
        self.calls.append("cancel_all_orders")
        raise AssertionError("preview cancelled broker orders")

    def close_all_positions(self) -> int:
        self.calls.append("close_all_positions")
        raise AssertionError("preview closed broker positions")


def proposal(
    *,
    symbol: str = "AAPL",
    entry: float = 100.0,
    stop: float = 97.5,
    target: float = 105.0,
    side: str = "buy",
) -> TradeProposal:
    return TradeProposal(
        symbol=symbol,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        side=side,
    )


def preview_stack(
    broker: RecordingBroker,
    *,
    limits: RiskLimits | None = None,
) -> tuple[RiskLimits, PaperExecutionEngine]:
    configured_limits = limits or RiskLimits()
    return (
        configured_limits,
        PaperExecutionEngine(
            broker,
            RiskManager(configured_limits),
        ),
    )


def run_preview(
    broker: RecordingBroker,
    *,
    trade: TradeProposal | None = None,
    limits: RiskLimits | None = None,
    enabled: bool = True,
    development_mode: bool = False,
    logger: logging.Logger | None = None,
) -> RiskDecision:
    configured_limits, engine = preview_stack(broker, limits=limits)
    return preview_paper_order(
        broker=broker,
        proposal=trade or proposal(),
        limits=configured_limits,
        legacy_preview=engine.preview,
        use_deterministic_preview=enabled,
        development_mode=development_mode,
        logger=logger,
    )


def test_deterministic_preview_wires_broker_view_to_service() -> None:
    broker = RecordingBroker()

    decision = run_preview(broker)

    assert decision.approved is True
    assert decision.quantity == 100
    assert decision.maximum_loss == 250.0
    assert decision.capital_required == 10_000.0
    assert decision.reward_risk == 2.0
    assert broker.calls == [
        "get_account",
        "get_positions",
        "get_open_orders",
    ]


def test_disabled_feature_flag_uses_only_legacy_preview() -> None:
    broker = RecordingBroker()

    decision = run_preview(broker, enabled=False)

    assert decision.approved is True
    assert broker.calls == [
        "get_account",
        "get_positions",
        "get_open_orders",
    ]


def test_enabled_feature_flag_avoids_legacy_preview_outside_development() -> None:
    broker = RecordingBroker()

    run_preview(broker, enabled=True, development_mode=False)

    assert broker.calls == [
        "get_account",
        "get_positions",
        "get_open_orders",
    ]


def test_development_mode_computes_both_previews() -> None:
    broker = RecordingBroker()

    run_preview(broker, enabled=True, development_mode=True)

    assert broker.calls == [
        "get_account",
        "get_positions",
        "get_open_orders",
        "get_account",
        "get_positions",
        "get_open_orders",
    ]


def test_diagnostic_failure_does_not_change_deterministic_preview(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broker = RecordingBroker()
    limits, _ = preview_stack(broker)

    def failing_legacy_preview(_: TradeProposal) -> RiskDecision:
        raise RuntimeError("legacy diagnostic failed")

    with caplog.at_level(logging.ERROR):
        decision = preview_paper_order(
            broker=broker,
            proposal=proposal(),
            limits=limits,
            legacy_preview=failing_legacy_preview,
            use_deterministic_preview=True,
            development_mode=True,
        )

    assert decision.approved is True
    assert "deterministic preview remains active" in caplog.text


def test_preview_parity_when_policies_match(caplog: pytest.LogCaptureFixture) -> None:
    broker = RecordingBroker()

    with caplog.at_level(logging.WARNING):
        deterministic = run_preview(
            broker,
            enabled=True,
            development_mode=True,
        )

    comparison_broker = RecordingBroker()
    legacy = run_preview(comparison_broker, enabled=False)

    assert deterministic == legacy
    assert "Preview parity difference" not in caplog.text


def test_non_default_risk_percentage_has_parity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broker = RecordingBroker()
    limits = RiskLimits(risk_per_trade_pct=0.5)
    trade = proposal(stop=90.0, target=120.0)

    with caplog.at_level(logging.WARNING):
        deterministic = run_preview(
            broker,
            trade=trade,
            limits=limits,
            enabled=True,
            development_mode=True,
        )

    legacy = run_preview(
        RecordingBroker(),
        trade=trade,
        limits=limits,
        enabled=False,
    )

    assert deterministic == legacy
    assert deterministic.quantity == 50
    assert "Preview parity difference" not in caplog.text


@pytest.mark.parametrize(
    ("trade", "broker"),
    [
        (
            proposal(entry=5.0, stop=4.0, target=7.0),
            RecordingBroker(),
        ),
        (
            proposal(target=101.0),
            RecordingBroker(),
        ),
        (
            proposal(),
            RecordingBroker(
                positions=[
                    BrokerPosition(
                        symbol="AAPL",
                        quantity=10,
                        average_entry_price=90.0,
                        current_price=100.0,
                    )
                ]
            ),
        ),
        (
            proposal(),
            RecordingBroker(
                orders=[
                    BrokerOrder(
                        order_id="order-1",
                        symbol="AAPL",
                        quantity=1,
                        side="buy",
                        status="open",
                        order_type="limit",
                        submitted_price=100.0,
                    )
                ]
            ),
        ),
    ],
)
def test_previously_mismatched_buy_policies_now_have_parity(
    trade: TradeProposal,
    broker: RecordingBroker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING):
        decision = run_preview(
            broker,
            trade=trade,
            enabled=True,
            development_mode=True,
        )

    assert decision.approved is False
    assert "Preview parity difference" not in caplog.text


def test_non_buy_long_only_difference_remains_classified(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broker = RecordingBroker()

    with caplog.at_level(logging.WARNING):
        run_preview(
            broker,
            trade=proposal(stop=105.0, target=90.0, side="sell"),
            enabled=True,
            development_mode=True,
        )

    assert "[POLICY_DIFFERENCE]" in caplog.text
    assert "explicit long-only policy" in caplog.text
    assert "[IMPLEMENTATION_DEFECT]" not in caplog.text


def test_position_size_cap_reaches_legacy_parity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broker = RecordingBroker()
    limits = RiskLimits(risk_per_trade_pct=5.0)

    with caplog.at_level(logging.WARNING):
        decision = run_preview(
            broker,
            trade=proposal(stop=95.0, target=110.0),
            limits=limits,
            enabled=True,
            development_mode=True,
        )

    assert decision.approved is True
    assert decision.quantity == 120
    assert "Preview parity difference" not in caplog.text


def test_zero_buying_power_reaches_legacy_parity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broker = RecordingBroker(
        account=AccountSnapshot(
            equity=100_000.0,
            cash=0.0,
            buying_power=0.0,
            daily_pnl=0.0,
            paper=True,
        )
    )

    with caplog.at_level(logging.WARNING):
        decision = run_preview(
            broker,
            enabled=True,
            development_mode=True,
        )

    assert decision.approved is False
    assert decision.quantity == 0
    assert decision.reasons == [
        "Risk and exposure limits produce a zero-share position."
    ]
    assert "Preview parity difference" not in caplog.text


def test_daily_loss_current_equity_basis_reaches_legacy_parity(
    caplog: pytest.LogCaptureFixture,
) -> None:
    broker = RecordingBroker(
        account=AccountSnapshot(
            equity=99_005.0,
            cash=99_005.0,
            buying_power=99_005.0,
            daily_pnl=-995.0,
            paper=True,
        )
    )

    with caplog.at_level(logging.WARNING):
        decision = run_preview(
            broker,
            enabled=True,
            development_mode=True,
        )

    assert decision.approved is False
    assert decision.reasons == ["Daily loss lock is active."]
    assert "Preview parity difference" not in caplog.text


def test_unexpected_numeric_difference_is_classified_as_defect() -> None:
    deterministic_result = PreviewTradeResult(
        approved=True,
        quantity=100,
        dollar_risk=Decimal("250"),
        position_value=Decimal("10000"),
        reward_risk=Decimal("2"),
        reasons=(),
    )
    deterministic = RiskDecision(
        approved=True,
        quantity=100,
        maximum_loss=250.0,
        capital_required=10_000.0,
        reward_risk=2.0,
    )
    legacy = RiskDecision(
        approved=True,
        quantity=99,
        maximum_loss=250.0,
        capital_required=10_000.0,
        reward_risk=2.0,
    )

    differences = compare_preview_decisions(
        proposal=proposal(),
        limits=RiskLimits(),
        legacy=legacy,
        deterministic=deterministic,
        deterministic_result=deterministic_result,
    )

    assert len(differences) == 1
    assert differences[0].field == "quantity"
    assert differences[0].classification is ParityClassification.IMPLEMENTATION_DEFECT


def test_zero_equity_returns_safe_rejection() -> None:
    broker = RecordingBroker(
        account=AccountSnapshot(
            equity=0.0,
            cash=0.0,
            buying_power=0.0,
            daily_pnl=0.0,
            paper=True,
        )
    )

    decision = run_preview(broker)

    assert decision.approved is False
    assert decision.quantity == 0
    assert decision.reasons == ["Account equity is unavailable or zero."]
    assert broker.calls == ["get_account", "get_positions"]


def test_invalid_side_is_rejected_instead_of_becoming_a_buy() -> None:
    broker = RecordingBroker()

    decision = run_preview(broker, trade=proposal(side="hold"))

    assert decision.approved is False
    assert decision.quantity == 0
    assert "Unsupported trade side" in decision.reasons[0]


def test_preview_never_submits_or_mutates_broker() -> None:
    broker = RecordingBroker()

    run_preview(broker, enabled=True, development_mode=True)

    assert "submit_bracket_order" not in broker.calls
    assert "cancel_all_orders" not in broker.calls
    assert "close_all_positions" not in broker.calls


def test_rejected_plan_never_displays_a_nonzero_approved_quantity() -> None:
    rejected = RiskDecision(
        approved=False,
        quantity=250,
        maximum_loss=250.0,
        capital_required=2_250.0,
        reward_risk=2.0,
        reasons=["Price is below the $10.00 minimum."],
    )

    rendered = approved_quantity_display(rejected)

    assert rendered == REJECTED_APPROVED_QUANTITY
    assert rendered not in (250, "250")


def test_approved_plan_displays_its_existing_quantity_unchanged() -> None:
    approved = RiskDecision(
        approved=True,
        quantity=100,
        maximum_loss=250.0,
        capital_required=10_000.0,
        reward_risk=2.0,
    )

    assert approved_quantity_display(approved) == approved.quantity


def test_app_feature_flag_defaults_to_deterministic_preview() -> None:
    tree = ast.parse((PROJECT_ROOT / "app.py").read_text(encoding="utf-8"))
    assignments = {
        target.id: node.value.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance((target := node.targets[0]), ast.Name)
        and isinstance(node.value, ast.Constant)
    }

    assert assignments["USE_DETERMINISTIC_PREVIEW"] is True


def test_app_wires_paper_order_preview_through_feature_flag() -> None:
    tree = ast.parse((PROJECT_ROOT / "app.py").read_text(encoding="utf-8"))
    preview_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "preview_paper_order"
    ]

    assert len(preview_calls) == 1
    keywords = {
        keyword.arg: keyword.value
        for keyword in preview_calls[0].keywords
        if keyword.arg is not None
    }
    assert isinstance(keywords["broker"], ast.Name)
    assert keywords["broker"].id == "broker"
    assert isinstance(keywords["legacy_preview"], ast.Attribute)
    assert isinstance(keywords["legacy_preview"].value, ast.Name)
    assert keywords["legacy_preview"].value.id == "engine"
    assert keywords["legacy_preview"].attr == "preview"
    assert isinstance(keywords["use_deterministic_preview"], ast.Name)
    assert keywords["use_deterministic_preview"].id == "USE_DETERMINISTIC_PREVIEW"


def test_app_uses_rejection_aware_approved_quantity_presentation() -> None:
    tree = ast.parse((PROJECT_ROOT / "app.py").read_text(encoding="utf-8"))
    metric_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
        and node.func.attr == "metric"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "Approved quantity"
    ]

    assert len(metric_calls) == 1
    rendered_value = metric_calls[0].args[1]
    assert isinstance(rendered_value, ast.Call)
    assert isinstance(rendered_value.func, ast.Name)
    assert rendered_value.func.id == "approved_quantity_display"
    assert len(rendered_value.args) == 1
    assert isinstance(rendered_value.args[0], ast.Name)
    assert rendered_value.args[0].id == "decision"


def test_app_submission_retains_legacy_execution_engine_as_rollback() -> None:
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    assert "legacy_submit=engine.submit" in source
    assert "use_deterministic_submission=USE_DETERMINISTIC_SUBMISSION" in source
