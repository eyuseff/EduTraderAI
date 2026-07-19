"""Candidate domain model for Volcanes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from volcanoes.domain.enums import CandidateStatus


@dataclass
class Candidate:
    """A market opportunity produced by Explorer."""

    symbol: str
    strategy_name: str
    score: int

    entry_price: float | None = None
    stop_price: float | None = None
    target_price: float | None = None
    explanation: str = ""

    status: CandidateStatus = CandidateStatus.NEW
    scanner_run_id: int | None = None
    id: int | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )

    def __post_init__(self) -> None:
        self.symbol = self.symbol.strip().upper()
        self.strategy_name = self.strategy_name.strip()

        if not self.symbol:
            raise ValueError("Candidate symbol cannot be empty.")

        if not self.strategy_name:
            raise ValueError("Strategy name cannot be empty.")

        if not 0 <= self.score <= 100:
            raise ValueError("Candidate score must be between 0 and 100.")

        for name, value in (
            ("entry_price", self.entry_price),
            ("stop_price", self.stop_price),
            ("target_price", self.target_price),
        ):
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be greater than zero.")
