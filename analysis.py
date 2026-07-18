"""
EduTrader AI
Market Analysis

Provides human-readable interpretations of technical indicators.
"""


class MarketAnalysis:
    """Creates technical descriptions for individual stocks."""

    @staticmethod
    def describe(stock: dict) -> dict[str, str]:
        """
        Interpret the stock's technical indicators.

        Returns a dictionary of readable analysis labels.
        """

        rsi = float(stock["RSI"])
        price = float(stock["Price"])
        ema20 = float(stock["EMA20"])
        ema50 = float(stock["EMA50"])
        sma200 = float(stock["SMA200"])
        macd = float(stock["MACD"])
        signal = float(stock["Signal"])
        atr = float(stock["ATR"])

        if rsi < 30:
            momentum = "Oversold"
        elif rsi > 70:
            momentum = "Overbought"
        else:
            momentum = "Neutral"

        trend = "Bullish" if ema20 > ema50 else "Bearish"

        long_term = (
            "Above 200-day average"
            if price > sma200
            else "Below 200-day average"
        )

        macd_state = "Increasing" if macd > signal else "Weakening"

        atr_percent = atr / price * 100 if price > 0 else 0.0

        if atr_percent < 2.5:
            volatility = "Low"
        elif atr_percent < 5.0:
            volatility = "Moderate"
        else:
            volatility = "High"

        return {
            "Momentum": momentum,
            "Trend": trend,
            "LongTerm": long_term,
            "MACDState": macd_state,
            "Volatility": volatility,
            "ATRPercent": f"{atr_percent:.2f}%",
        }

    def analyze(self, market: list[dict]) -> None:
        """
        Print a compact technical analysis.

        Retained for compatibility with earlier versions.
        """

        print()
        print("=" * 60)
        print("AI MARKET ANALYSIS")
        print("=" * 60)

        for stock in market:
            analysis = self.describe(stock)

            print()
            print("-" * 60)
            print(stock["Symbol"])
            print("-" * 60)
            print(f"Momentum  : {analysis['Momentum']}")
            print(f"Trend     : {analysis['Trend']}")
            print(f"Long Term : {analysis['LongTerm']}")
            print(f"MACD      : {analysis['MACDState']}")
            print(
                f"Volatility: {analysis['Volatility']} "
                f"({analysis['ATRPercent']})"
            )
            print(f"ATR       : {stock['ATR']:.2f}")