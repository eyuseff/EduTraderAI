"""
EduTrader AI
Configuration

Central configuration file for the application.
Modify values here instead of changing source code.
"""

# ======================================================
# Application
# ======================================================

APP_NAME = "EduTrader AI"
APP_VERSION = "4.0.0-rc1"

# ======================================================
# Market
# ======================================================

WATCHLIST = [
    "AAPL",
    "MSFT",
    "NVDA",
    "META",
    "AMZN",
    "GOOGL",
]

# Historical data downloaded from Yahoo Finance
HISTORY_PERIOD = "1y"
INTERVAL = "1d"

# ======================================================
# Technical Indicators
# ======================================================

RSI_PERIOD = 14

EMA_FAST = 20
EMA_SLOW = 50

SMA_LONG = 200

MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

ATR_PERIOD = 14

# ======================================================
# Scoring Weights
# ======================================================

TREND_WEIGHT = 30
EMA_WEIGHT = 25
MACD_WEIGHT = 20
RSI_WEIGHT = 15
ATR_WEIGHT = 10

# ======================================================
# Recommendation Thresholds
# ======================================================

STRONG_BUY_THRESHOLD = 85
BUY_THRESHOLD = 70
HOLD_THRESHOLD = 50
SELL_THRESHOLD = 30

# ======================================================
# RSI Thresholds
# ======================================================

RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70

# ======================================================
# Volatility Thresholds
# ATR expressed as percentage of price
# ======================================================

LOW_VOLATILITY = 2.5
MEDIUM_VOLATILITY = 5.0

# ======================================================
# Risk Management
# ======================================================

STOP_LOSS_PERCENT = 0.05
TARGET_PERCENT = 0.10

# ======================================================
# Logging
# ======================================================

LOG_LEVEL = "INFO"
LOG_FILE = "logs/edutrader.log"

# ======================================================
# Display
# ======================================================

DECIMALS = 2
