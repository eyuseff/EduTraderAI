from broker.base import AccountSnapshot
from trading.risk_manager import RiskLimits, RiskManager, TradeProposal


def test_conservative_position_size():
    manager = RiskManager(RiskLimits(risk_per_trade_pct=0.25))
    decision = manager.evaluate(
        TradeProposal("AAPL", entry_price=100, stop_price=97.5, target_price=105),
        AccountSnapshot(equity=100_000, cash=100_000, buying_power=100_000),
        positions=[],
    )
    assert decision.approved
    assert decision.quantity == 100
    assert decision.maximum_loss == 250


def test_rejects_bad_reward_risk():
    manager = RiskManager()
    decision = manager.evaluate(
        TradeProposal("AAPL", entry_price=100, stop_price=98, target_price=102),
        AccountSnapshot(equity=100_000, cash=100_000, buying_power=100_000),
        positions=[],
    )
    assert not decision.approved
