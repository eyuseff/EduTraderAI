"""
EduTrader AI
Configuration
"""

# Stocks to analyze
WATCHLIST = [
    "AAPL",
    "MSFT",
    "NVDA",
    "META",
    "AMZN",
    "GOOGL",
]

# Historical data period
PERIOD = "6mo"

# Candle interval
INTERVAL = "1d"

# Risk management
STOP_LOSS_PERCENT = 0.05
TARGET_PERCENT = 0.10

# Indicator settings
RSI_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
SMA_LONG = 200

# Display
DECIMALS = 2