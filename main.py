"""
EduTrader AI 2.3
Typed Application Entry Point
"""

from logger import setup_logger
from position_sizing import PositionSizingEngine
from report import ConsoleReport
from reports.ranking import RankingEngine
from risk import RiskEngine
from scanner import MarketScanner
from stock_analysis import StockAnalysis
from strategy import StrategyEngine


logger = setup_logger()

ACCOUNT_BALANCE = 10_000.0
RISK_PER_TRADE = 1.0

TRADEABLE_RECOMMENDATIONS = {
    "BUY",
    "STRONG BUY",
}


def process_stock(
    scanner_stock: dict,
    strategy: StrategyEngine,
    risk: RiskEngine,
    position_sizing: PositionSizingEngine,
) -> StockAnalysis:
    """
    Convert scanner data into a typed StockAnalysis model
    and apply strategy, risk, and position-sizing calculations.
    """

    stock = StockAnalysis.from_scanner_dict(scanner_stock)

    # Existing engines still expect the old dictionary format.
    engine_data = stock.to_engine_dict()

    strategy_result = strategy.evaluate(engine_data)
    risk_result = risk.calculate(engine_data)

    stock.score = strategy_result.score
    stock.recommendation = strategy_result.recommendation
    stock.confidence = strategy_result.confidence
    stock.stars = strategy_result.stars
    stock.reasons = list(strategy_result.reasons)

    stock.entry = risk_result.entry
    stock.stop_loss = risk_result.stop_loss
    stock.target = risk_result.target
    stock.risk_amount = risk_result.risk_amount
    stock.reward_amount = risk_result.reward_amount
    stock.risk_percent = risk_result.risk_percent
    stock.reward_percent = risk_result.reward_percent
    stock.risk_reward = risk_result.risk_reward

    stock.account_balance = ACCOUNT_BALANCE
    stock.portfolio_risk_percent = RISK_PER_TRADE
    stock.maximum_loss = (
        ACCOUNT_BALANCE * RISK_PER_TRADE / 100
    )

    recommendation = stock.recommendation.upper()

    if recommendation in TRADEABLE_RECOMMENDATIONS:
        position_result = position_sizing.calculate(
            entry_price=stock.entry,
            stop_loss=stock.stop_loss,
            target_price=stock.target,
        )

        stock.account_balance = position_result.account_balance
        stock.portfolio_risk_percent = (
            position_result.risk_percentage
        )
        stock.maximum_loss = position_result.maximum_loss
        stock.risk_per_share = position_result.risk_per_share
        stock.shares = position_result.shares
        stock.capital_required = (
            position_result.capital_required
        )
        stock.estimated_profit = (
            position_result.estimated_profit
        )
        stock.actual_loss = position_result.actual_loss
        stock.actual_risk_percent = (
            position_result.actual_risk_percentage
        )
        stock.trade_eligible = True
        stock.trade_status = "TRADE"

    else:
        stock.risk_per_share = 0.0
        stock.shares = 0
        stock.capital_required = 0.0
        stock.estimated_profit = 0.0
        stock.actual_loss = 0.0
        stock.actual_risk_percent = 0.0
        stock.trade_eligible = False
        stock.trade_status = "NO TRADE"

    return stock


def main() -> None:
    """Run the complete EduTrader AI workflow."""

    logger.info("EduTrader AI 2.3 starting.")

    scanner = MarketScanner()
    strategy = StrategyEngine()
    risk = RiskEngine()

    position_sizing = PositionSizingEngine(
        account_balance=ACCOUNT_BALANCE,
        risk_percentage=RISK_PER_TRADE,
    )

    ranking = RankingEngine()
    report = ConsoleReport()

    try:
        scanned_market = scanner.scan()

        if not scanned_market:
            logger.warning("Scanner returned no valid stocks.")
            report.print_full_report([])
            return

        analyzed_models: list[StockAnalysis] = []

        for scanner_stock in scanned_market:
            symbol = scanner_stock.get("Symbol", "UNKNOWN")

            try:
                analyzed_stock = process_stock(
                    scanner_stock=scanner_stock,
                    strategy=strategy,
                    risk=risk,
                    position_sizing=position_sizing,
                )

                analyzed_models.append(analyzed_stock)

                logger.info(
                    "%s processed: score=%s, "
                    "recommendation=%s, status=%s, shares=%s.",
                    analyzed_stock.symbol,
                    analyzed_stock.score,
                    analyzed_stock.recommendation,
                    analyzed_stock.trade_status,
                    analyzed_stock.shares,
                )

            except (KeyError, TypeError, ValueError) as error:
                logger.error(
                    "Unable to process %s: %s",
                    symbol,
                    error,
                )

            except Exception:
                logger.exception(
                    "Unexpected error while processing %s.",
                    symbol,
                )

        # Temporary compatibility layer.
        # Ranking and reporting still receive dictionaries.
        analyzed_market = [
            stock.to_engine_dict()
            for stock in analyzed_models
        ]

        ranked_market = ranking.rank(analyzed_market)

        report.print_full_report(ranked_market)

        logger.info(
            "EduTrader AI completed with %d analyzed stocks.",
            len(ranked_market),
        )

    except KeyboardInterrupt:
        logger.warning(
            "Application interrupted by the user."
        )

    except Exception:
        logger.exception(
            "EduTrader AI terminated unexpectedly."
        )
        raise


if __name__ == "__main__":
    main()