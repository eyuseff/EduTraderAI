"""
EduTrader AI
Console Reporting

Displays ranked opportunities, trade plans,
trade eligibility, and position-sizing calculations.
"""

from analysis import MarketAnalysis


class ConsoleReport:
    """Renders EduTrader AI results in the terminal."""

    WIDTH = 82

    def __init__(self) -> None:
        self.analysis = MarketAnalysis()

    def print_header(self) -> None:
        print()
        print("=" * self.WIDTH)
        print("EDUTRADER AI 2.2".center(self.WIDTH))
        print("=" * self.WIDTH)

    def print_portfolio_settings(
        self,
        market: list[dict],
    ) -> None:
        """Display account-level risk settings."""

        if not market:
            return

        first_stock = market[0]

        print("\nPORTFOLIO SETTINGS")
        print("-" * self.WIDTH)
        print(
            f"Account Balance    : "
            f"${first_stock['AccountBalance']:,.2f}"
        )
        print(
            f"Risk per Trade     : "
            f"{first_stock['PortfolioRiskPercent']:.2f}%"
        )
        print(
            f"Maximum Loss       : "
            f"${first_stock['MaximumLoss']:,.2f}"
        )
        print(
            "Eligible Signals   : BUY, STRONG BUY"
        )

    def print_ranking(
        self,
        market: list[dict],
    ) -> None:
        """Print the ranked market summary."""

        print("\nRANKED OPPORTUNITIES")
        print("-" * self.WIDTH)

        header = (
            f"{'Rank':<6}"
            f"{'Symbol':<9}"
            f"{'Score':<8}"
            f"{'Rating':<10}"
            f"{'Recommendation':<17}"
            f"{'Status':<12}"
            f"{'Shares':>8}"
            f"{'R/R':>8}"
        )

        print(header)
        print("-" * self.WIDTH)

        for rank, stock in enumerate(
            market,
            start=1,
        ):
            print(
                f"{rank:<6}"
                f"{stock['Symbol']:<9}"
                f"{stock['Score']:<8}"
                f"{stock['Stars']:<10}"
                f"{stock['Recommendation']:<17}"
                f"{stock['TradeStatus']:<12}"
                f"{stock['Shares']:>8}"
                f"{stock['RiskReward']:>8.2f}"
            )

    def print_stock_details(
        self,
        stock: dict,
    ) -> None:
        """Print a detailed report for one stock."""

        technical = self.analysis.describe(stock)

        print()
        print("=" * self.WIDTH)
        print(stock["Symbol"].center(self.WIDTH))
        print("=" * self.WIDTH)

        print(
            f"Current Price      : "
            f"${stock['Price']:,.2f}"
        )
        print(
            f"AI Score           : "
            f"{stock['Score']} / 100"
        )
        print(
            f"Recommendation     : "
            f"{stock['Stars']} "
            f"{stock['Recommendation']}"
        )
        print(
            f"Confidence         : "
            f"{stock['Confidence']}%"
        )
        print(
            f"Trade Status       : "
            f"{stock['TradeStatus']}"
        )

        print("\nTechnical Analysis")
        print("-" * 40)
        print(
            f"RSI Momentum       : "
            f"{technical['Momentum']}"
        )
        print(
            f"Medium-Term Trend  : "
            f"{technical['Trend']}"
        )
        print(
            f"Long-Term Trend    : "
            f"{technical['LongTerm']}"
        )
        print(
            f"MACD Momentum      : "
            f"{technical['MACDState']}"
        )
        print(
            f"Volatility         : "
            f"{technical['Volatility']} "
            f"({technical['ATRPercent']})"
        )
        print(
            f"ATR                : "
            f"{stock['ATR']:.2f}"
        )

        print("\nTrade Plan")
        print("-" * 40)
        print(
            f"Entry Price        : "
            f"${stock['Entry']:,.2f}"
        )
        print(
            f"Stop Loss          : "
            f"${stock['StopLoss']:,.2f}"
        )
        print(
            f"Target Price       : "
            f"${stock['Target']:,.2f}"
        )
        print(
            f"Trade Risk         : "
            f"{stock['RiskPercent']:.2f}%"
        )
        print(
            f"Potential Reward   : "
            f"{stock['RewardPercent']:.2f}%"
        )
        print(
            f"Risk/Reward        : "
            f"1 : {stock['RiskReward']:.2f}"
        )

        print("\nPosition Sizing")
        print("-" * 40)

        if stock["TradeEligible"]:
            print(
                f"Account Balance    : "
                f"${stock['AccountBalance']:,.2f}"
            )
            print(
                f"Risk Limit         : "
                f"{stock['PortfolioRiskPercent']:.2f}%"
            )
            print(
                f"Maximum Loss       : "
                f"${stock['MaximumLoss']:,.2f}"
            )
            print(
                f"Risk per Share     : "
                f"${stock['RiskPerShare']:,.2f}"
            )
            print(
                f"Position Size      : "
                f"{stock['Shares']} shares"
            )
            print(
                f"Capital Required   : "
                f"${stock['CapitalRequired']:,.2f}"
            )
            print(
                f"Actual Maximum Loss: "
                f"${stock['ActualLoss']:,.2f}"
            )
            print(
                f"Actual Account Risk: "
                f"{stock['ActualRiskPercent']:.2f}%"
            )
            print(
                f"Estimated Profit   : "
                f"${stock['EstimatedProfit']:,.2f}"
            )
        else:
            print(
                "No long position calculated."
            )
            print(
                f"Reason              : "
                f"{stock['Recommendation']} is not "
                f"an eligible entry signal."
            )
            print(
                "Position Size       : 0 shares"
            )
            print(
                "Capital Required    : $0.00"
            )
            print(
                "Account Risk        : 0.00%"
            )

        print("\nScoring Explanation")
        print("-" * 40)

        for reason in stock["Reasons"]:
            print(f"✓ {reason}")

    def print_full_report(
        self,
        market: list[dict],
    ) -> None:
        """Display the complete ranked report."""

        self.print_header()

        if not market:
            print(
                "\nNo valid stocks were available "
                "for analysis."
            )
            return

        self.print_portfolio_settings(market)
        self.print_ranking(market)

        for stock in market:
            self.print_stock_details(stock)

        print()
        print("=" * self.WIDTH)
        print(
            "Analysis completed successfully.".center(
                self.WIDTH
            )
        )
        print("=" * self.WIDTH)
        print(
            "Educational analysis only — "
            "not financial advice."
        )