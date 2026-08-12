"""Financial ledger."""

from __future__ import annotations

from volcanoes.domain.ledger_entry import LedgerEntry


class Ledger:
    """Immutable financial journal."""

    def __init__(self) -> None:
        self._entries: list[LedgerEntry] = []

    def record(
        self,
        entry: LedgerEntry,
    ) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[LedgerEntry]:
        return list(self._entries)

    def count(self) -> int:
        return len(self._entries)
