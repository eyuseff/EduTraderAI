"""Result helpers for isolated spike outputs."""

from __future__ import annotations

import json
from pathlib import Path

from spikes.execution_durability.common.models import SpikeResult


def write_results(path: Path, results: tuple[SpikeResult, ...]) -> None:
    """Write normalized spike results under an ignored build path."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [result.to_primitive() for result in results], indent=2, sort_keys=True
        ),
        encoding="utf-8",
    )


__all__ = ["write_results"]
