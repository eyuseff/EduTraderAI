"""Deterministic backtest orchestration for EduTraderAI."""

from __future__ import annotations

from decimal import Decimal

from volcanoes.analytics.analytics_engine import AnalyticsEngine
from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot
from volcanoes.analytics.snapshot_recorder import SnapshotRecorder
from volcanoes.backtest.backtest_result import BacktestResult
from volcanoes.execution import ExecutionPipeline
from volcanoes.market import MarketFeed
from volcanoes.portfolio import Portfolio
from volcanoes.risk import RiskViolation
from volcanoes.strategy import Strategy


class BacktestEngine:
    """Run a strategy against a sequential market-data feed.

    The engine performs orchestration only. It delegates trading decisions,
    position sizing, risk validation, order construction, execution,
    portfolio accounting, snapshot storage, and analytics calculations to
    their respective components.
    """

    def __init__(
        self,
        feed: MarketFeed,
        strategy: Strategy,
        pipeline: ExecutionPipeline,
        portfolio: Portfolio,
    ) -> None:
        if not isinstance(feed, MarketFeed):
            raise TypeError("feed must be a MarketFeed instance.")

        if not isinstance(strategy, Strategy):
            raise TypeError("strategy must be a Strategy instance.")

        if not isinstance(pipeline, ExecutionPipeline):
            raise TypeError(
                "pipeline must be an ExecutionPipeline instance."
            )

        if not isinstance(portfolio, Portfolio):
            raise TypeError("portfolio must be a Portfolio instance.")

        self._feed = feed
        self._strategy = strategy
        self._pipeline = pipeline
        self._portfolio = portfolio

    def run(self) -> BacktestResult:
        """Consume the feed and execute every generated trade intent.

        One immutable portfolio snapshot is recorded after each processed
        market bar. Risk violations and non-submitted zero-quantity results
        are counted as rejected trades. Unexpected programming errors are
        intentionally allowed to propagate.
        """
        total_bars = 0
        signals = 0
        executed_trades = 0
        rejected_trades = 0

        recorder = SnapshotRecorder()

        while self._feed.has_next():
            bar = self._feed.next_bar()
            total_bars += 1

            trade_intent = self._strategy.on_bar(bar)

            if trade_intent is not None:
                signals += 1

                try:
                    execution_result = self._pipeline.execute(
                        self._portfolio,
                        trade_intent,
                    )
                except RiskViolation:
                    rejected_trades += 1
                else:
                    if execution_result.submitted:
                        executed_trades += 1
                    else:
                        rejected_trades += 1

            recorder.record(
                self._create_snapshot(timestamp=bar.timestamp)
            )

        snapshots = recorder.snapshots
        performance_report = AnalyticsEngine().analyze(snapshots)

        return BacktestResult(
            total_bars=total_bars,
            signals=signals,
            executed_trades=executed_trades,
            rejected_trades=rejected_trades,
            portfolio=self._portfolio,
            snapshots=snapshots,
            performance_report=performance_report,
        )

    def _create_snapshot(self, timestamp: object) -> PortfolioSnapshot:
        """Create a snapshot from the portfolio's current accounting state."""
        market_value = self._portfolio.invested_value
        equity = self._portfolio.equity

        unrealized_pnl = (
            equity
            - self._portfolio.starting_cash
            - self._portfolio.realized_pnl
        )

        return PortfolioSnapshot(
            timestamp=timestamp,
            cash=self._portfolio.cash,
            market_value=market_value,
            equity=equity,
            realized_pnl=self._portfolio.realized_pnl,
            unrealized_pnl=unrealized_pnl,
            open_positions=self._portfolio.open_positions,
        )

    @property
    def feed(self) -> MarketFeed:
        """Return the market feed used by the engine."""
        return self._feed

    @property
    def strategy(self) -> Strategy:
        """Return the strategy used by the engine."""
        return self._strategy

    @property
    def pipeline(self) -> ExecutionPipeline:
        """Return the execution pipeline used by the engine."""
        return self._pipeline

    @property
    def portfolio(self) -> Portfolio:
        """Return the portfolio used by the engine."""
        return self._portfolio
