"""Shared domain enums for Volcanes."""

from enum import Enum


class LedgerEntryType(str, Enum):
    """Supported financial ledger entry types."""

    BUY = "BUY"
    SELL = "SELL"
    COMMISSION = "COMMISSION"
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    DIVIDEND = "DIVIDEND"


class TradeSide(str, Enum):
    """Supported trading directions."""

    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    """Lifecycle states for broker orders."""

    PENDING = "PENDING"
    FILLED = "FILLED"
    REJECTED = "REJECTED"


class TradeStatus(str, Enum):
    """Lifecycle states for persisted trades."""

    PENDING = "PENDING"
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class CandidateStatus(str, Enum):
    """Lifecycle states for trade candidates."""

    NEW = "NEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
