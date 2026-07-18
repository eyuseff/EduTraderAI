import ta


def calculate_indicators(df):

    close = df["Close"]

    # RSI
    df["RSI"] = ta.momentum.RSIIndicator(close).rsi()

    # Moving Averages
    df["EMA20"] = ta.trend.EMAIndicator(close, window=20).ema_indicator()
    df["EMA50"] = ta.trend.EMAIndicator(close, window=50).ema_indicator()
    df["SMA200"] = ta.trend.SMAIndicator(close, window=200).sma_indicator()

    # MACD
    macd = ta.trend.MACD(close)
    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()

    # ATR
    atr = ta.volatility.AverageTrueRange(
        high=df["High"],
        low=df["Low"],
        close=df["Close"]
    )

    df["ATR"] = atr.average_true_range()

    return df