"""Proof that configured deterministic buy previews have full legacy parity."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pytest

from adapters.paper_order_preview import preview_paper_order
from broker.base import AccountSnapshot, BrokerOrder, BrokerPosition
from trading.execution import PaperExecutionEngine
from trading.risk_manager import RiskLimits, RiskManager, TradeProposal


@dataclass(frozen=True, slots=True)
class ParityCase:
    trade: TradeProposal
    account: AccountSnapshot = AccountSnapshot(
        equity=100_000.0,
        cash=100_000.0,
        buying_power=100_000.0,
        daily_pnl=0.0,
        paper=True,
    )
    positions: tuple[BrokerPosition, ...] = ()
    orders: tuple[BrokerOrder, ...] = ()
    limits: RiskLimits = RiskLimits()


class SnapshotBroker:
    """Stable read-only broker fake for cross-engine parity tests."""

    name = "Parity snapshot"
    is_paper = True

    def __init__(self, case: ParityCase) -> None:
        self._case = case
        self.mutations: list[str] = []

    def get_account(self) -> AccountSnapshot:
        return self._case.account

    def get_positions(self) -> list[BrokerPosition]:
        return list(self._case.positions)

    def get_open_orders(self) -> list[BrokerOrder]:
        return list(self._case.orders)

    def submit_bracket_order(
        self,
        *,
        symbol: str,
        quantity: int,
        entry_price: float,
        stop_price: float,
        target_price: float,
    ) -> BrokerOrder:
        self.mutations.append("submit_bracket_order")
        raise AssertionError("preview submitted an order")

    def cancel_all_orders(self) -> int:
        self.mutations.append("cancel_all_orders")
        raise AssertionError("preview cancelled orders")

    def close_all_positions(self) -> int:
        self.mutations.append("close_all_positions")
        raise AssertionError("preview closed positions")


def trade(
    *,
    symbol: str = "AAPL",
    entry: float = 100.0,
    stop: float = 97.5,
    target: float = 105.0,
) -> TradeProposal:
    return TradeProposal(
        symbol=symbol,
        entry_price=entry,
        stop_price=stop,
        target_price=target,
        side="buy",
    )


def order(symbol: str = "AAPL") -> BrokerOrder:
    return BrokerOrder(
        order_id=f"order-{symbol}",
        symbol=symbol,
        quantity=1,
        side="buy",
        status="open",
        order_type="limit",
        submitted_price=100.0,
    )


PARITY_CASES = (
    pytest.param(ParityCase(trade()), id="approved"),
    pytest.param(
        ParityCase(trade(entry=5.0, stop=4.0, target=7.0)),
        id="minimum-price",
    ),
    pytest.param(
        ParityCase(trade(target=101.0)),
        id="reward-risk",
    ),
    pytest.param(
        ParityCase(
            trade(),
            positions=(BrokerPosition("aapl", 10, 90.0, 100.0),),
        ),
        id="duplicate-position",
    ),
    pytest.param(
        ParityCase(trade(), orders=(order("aapl"),)),
        id="duplicate-order",
    ),
    pytest.param(
        ParityCase(
            trade(),
            account=AccountSnapshot(
                equity=100_000.0,
                cash=5_000.0,
                buying_power=5_000.0,
            ),
        ),
        id="buying-power-cap",
    ),
    pytest.param(
        ParityCase(
            trade(),
            account=AccountSnapshot(
                equity=100_000.0,
                cash=0.0,
                buying_power=0.0,
            ),
        ),
        id="zero-buying-power",
    ),
    pytest.param(
        ParityCase(
            trade(),
            account=AccountSnapshot(
                equity=99_005.0,
                cash=99_005.0,
                buying_power=99_005.0,
                daily_pnl=-995.0,
            ),
        ),
        id="daily-loss-current-equity",
    ),
    pytest.param(
        ParityCase(
            trade(stop=95.0, target=110.0),
            limits=RiskLimits(risk_per_trade_pct=5.0),
        ),
        id="single-position-cap",
    ),
    pytest.param(
        ParityCase(
            trade(),
            positions=(BrokerPosition("MSFT", 49, 1_000.0, 1_000.0),),
            limits=RiskLimits(risk_per_trade_pct=1.0),
        ),
        id="portfolio-exposure-cap",
    ),
    pytest.param(
        ParityCase(
            trade(),
            positions=tuple(
                BrokerPosition(f"SYM{index}", 1, 1.0, 1.0) for index in range(5)
            ),
        ),
        id="maximum-open-positions",
    ),
    pytest.param(
        ParityCase(
            trade(entry=5.0, stop=4.0, target=5.5),
            account=AccountSnapshot(
                equity=99_005.0,
                cash=99_005.0,
                buying_power=99_005.0,
                daily_pnl=-1_000.0,
            ),
            positions=(BrokerPosition("AAPL", 1, 5.0, 5.0),),
            orders=(order(),),
            limits=RiskLimits(max_open_positions=1),
        ),
        id="combined-rejections",
    ),
    pytest.param(
        ParityCase(
            trade(entry=50.0, stop=45.0, target=57.5),
            limits=RiskLimits(
                risk_per_trade_pct=0.5,
                max_daily_loss_pct=2.0,
                max_open_positions=10,
                max_total_exposure_pct=75.0,
                max_single_position_pct=20.0,
                minimum_reward_risk=1.5,
                minimum_price=1.0,
            ),
        ),
        id="non-default-configuration",
    ),
    pytest.param(
        ParityCase(
            trade(),
            limits=RiskLimits(
                max_daily_loss_pct=0.0,
                max_total_exposure_pct=0.0,
                minimum_reward_risk=0.0,
                minimum_price=0.0,
            ),
        ),
        id="zero-policy-thresholds",
    ),
    pytest.param(
        ParityCase(
            trade(entry=1_000.0, stop=500.0, target=2_000.0),
            account=AccountSnapshot(
                equity=100.0,
                cash=100.0,
                buying_power=100.0,
            ),
        ),
        id="risk-sized-zero-quantity",
    ),
)


@pytest.mark.parametrize("case", PARITY_CASES)
def test_deterministic_preview_has_full_buy_trade_parity(
    case: ParityCase,
    caplog: pytest.LogCaptureFixture,
) -> None:
    legacy_broker = SnapshotBroker(case)
    legacy_engine = PaperExecutionEngine(
        legacy_broker,
        RiskManager(case.limits),
    )
    legacy = legacy_engine.preview(case.trade)

    deterministic_broker = SnapshotBroker(case)
    deterministic_engine = PaperExecutionEngine(
        deterministic_broker,
        RiskManager(case.limits),
    )
    with caplog.at_level(logging.WARNING):
        deterministic = preview_paper_order(
            broker=deterministic_broker,
            proposal=case.trade,
            limits=case.limits,
            legacy_preview=deterministic_engine.preview,
            use_deterministic_preview=True,
            development_mode=True,
        )

    assert deterministic == legacy
    assert "Preview parity difference" not in caplog.text
    assert legacy_broker.mutations == []
    assert deterministic_broker.mutations == []
