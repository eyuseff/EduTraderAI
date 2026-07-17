import yfinance as yf
import pandas as pd

from indicators import calculate_indicators

WATCHLIST = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL"
]


def get_stock_data(symbol):

    stock = yf.Ticker(symbol)

    df = stock.history(period="1y")

    if df.empty:
        return None

    df = calculate_indicators(df)

    latest = df.iloc[-1]

    return {
        "Symbol": symbol,
        "Price": latest["Close"],
        "RSI": latest["RSI"],
        "EMA20": latest["EMA20"],
        "EMA50": latest["EMA50"],
        "SMA200": latest["SMA200"],
        "MACD": latest["MACD"],
        "Signal": latest["MACD_SIGNAL"],
    }


def scan_market():

    print("\n🚀 EduTrader AI")
    print("=" * 70)
    print(f'{"Symbol":<10}{"Price":>12}{"RSI":>10}')
    print("-" * 70)

    for symbol in WATCHLIST:

        data = get_stock_data(symbol)

        if data:

            print(
                f'{data["Symbol"]:<10}'
                f'${data["Price"]:>10.2f}'
                f'{data["RSI"]:>10.1f}'
            )


if __name__ == "__main__":
    scan_market()