import yfinance as yf
import pandas as pd

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
    hist = stock.history(period="5d")

    if hist.empty:
        return None

    current = hist["Close"].iloc[-1]
    previous = hist["Close"].iloc[-2]

    change = ((current - previous) / previous) * 100

    return {
        "Symbol": symbol,
        "Price": current,
        "Change": change
    }


def scan_market():
    print("\n🚀 EduTrader AI")
    print("=" * 60)
    print(f'{"Symbol":<10}{"Price":>12}{"Change":>12}')
    print("-" * 60)

    results = []

    for symbol in WATCHLIST:

        data = get_stock_data(symbol)

        if data:

            results.append(data)

            print(
                f'{data["Symbol"]:<10}'
                f'${data["Price"]:>10.2f}'
                f'{data["Change"]:>11.2f}%'
            )

    return pd.DataFrame(results)


if __name__ == "__main__":
    scan_market()