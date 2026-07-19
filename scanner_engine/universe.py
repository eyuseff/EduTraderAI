from __future__ import annotations

CORE_UNIVERSE: tuple[str, ...] = (
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "AVGO", "TSLA",
    "JPM", "V", "MA", "LLY", "UNH", "XOM", "COST", "HD", "WMT", "ORCL",
    "NFLX", "AMD", "CRM", "ADBE", "QCOM", "INTC", "TXN", "AMAT", "MU",
    "BAC", "GS", "MS", "SCHW", "KO", "PEP", "MCD", "NKE", "DIS",
    "CAT", "GE", "HON", "UPS", "LOW", "TMO", "ABT", "MRK", "ABBV",
    "SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "XLV", "XLI",
)


def normalize_universe(symbols: list[str] | tuple[str, ...] | None = None) -> list[str]:
    source = symbols or CORE_UNIVERSE
    seen: set[str] = set()
    clean: list[str] = []
    for raw in source:
        symbol = raw.strip().upper()
        if symbol and symbol not in seen:
            seen.add(symbol)
            clean.append(symbol)
    return clean
