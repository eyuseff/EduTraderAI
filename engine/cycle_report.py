"""Stable reporting contract shared by scanner execution paths."""

from __future__ import annotations

from dataclasses import dataclass, field

from scanner_engine.automated_scanner import ScanResult


@dataclass
class TradingCycleReport:
    """UI-compatible result of one automated scanner cycle."""

    scan: ScanResult
    submitted: list[dict[str, object]] = field(default_factory=list)
    rejected_by_risk: list[dict[str, object]] = field(default_factory=list)
