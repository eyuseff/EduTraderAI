import ta


def calculate_indicators(df):

    df["RSI"] = ta.momentum.RSIIndicator(
        close=df["Close"],
        window=14
    ).rsi()

    macd = ta.trend.MACD(df["Close"])

    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()

    df["EMA20"] = ta.trend.EMAIndicator(
        df["Close"],
        window=20
    ).ema_indicator()

    df["EMA50"] = ta.trend.EMAIndicator(
        df["Close"],
        window=50
    ).ema_indicator()

    df["SMA200"] = ta.trend.SMAIndicator(
        df["Close"],
        window=200
    ).sma_indicator()

    return df