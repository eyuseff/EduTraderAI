"""Collect immutable portfolio snapshots."""

from __future__ import annotations

from datetime import datetime

from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot


class SnapshotRecorder:
    """Records immutable portfolio snapshots."""

    def __init__(self) -> None:
        self._snapshots: list[PortfolioSnapshot] = []

    def record(self, snapshot: PortfolioSnapshot) -> None:
        """Record a portfolio snapshot."""
        self._snapshots.append(snapshot)

    @property
    def snapshots(self) -> tuple[PortfolioSnapshot, ...]:
        """Return recorded snapshots as an immutable sequence."""
        return tuple(self._snapshots)

    def __len__(self) -> int:
        return len(self._snapshots)

    def clear(self) -> None:
        """Remove all recorded snapshots."""
        self._snapshots.clear()
