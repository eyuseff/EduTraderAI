"""Import-safe runtime composition helpers for paper broker selection."""

from __future__ import annotations

import os
from pathlib import Path

from broker.simulated import SimulatedPaperBroker

SIMULATED_BROKER_STATE_PATH_ENV = "EDUTRADER_SIMULATED_BROKER_STATE_PATH"
_PROJECT_ROOT = Path(__file__).resolve().parents[1]


def build_local_simulated_broker(starting_cash: float) -> SimulatedPaperBroker:
    """Build the local simulator, optionally using a validated external state path."""

    override = os.environ.get(SIMULATED_BROKER_STATE_PATH_ENV)
    if override is None:
        return SimulatedPaperBroker(starting_cash=starting_cash)

    state_path = _validated_external_state_path(override)
    return SimulatedPaperBroker(
        starting_cash=starting_cash,
        state_path=state_path,
    )


def _validated_external_state_path(raw_path: str) -> Path:
    candidate_text = raw_path.strip()
    if not candidate_text:
        raise ValueError(
            f"{SIMULATED_BROKER_STATE_PATH_ENV} must be a non-empty absolute path."
        )

    candidate = Path(candidate_text).expanduser()
    if not candidate.is_absolute():
        raise ValueError(f"{SIMULATED_BROKER_STATE_PATH_ENV} must be absolute.")

    repository_root = _PROJECT_ROOT.resolve()
    existing_parent = _nearest_existing_parent(candidate)
    resolved_parent = existing_parent.resolve()
    if _is_relative_to(resolved_parent, repository_root):
        raise ValueError(
            f"{SIMULATED_BROKER_STATE_PATH_ENV} must point outside the repository."
        )

    resolved_candidate = resolved_parent.joinpath(
        *candidate.parts[len(existing_parent.parts) :]
    )
    if resolved_candidate == repository_root or _is_relative_to(
        resolved_candidate,
        repository_root,
    ):
        raise ValueError(
            f"{SIMULATED_BROKER_STATE_PATH_ENV} must point outside the repository."
        )

    return resolved_candidate


def _nearest_existing_parent(path: Path) -> Path:
    current = path.parent
    while not current.exists():
        parent = current.parent
        if parent == current:
            break
        current = parent
    return current


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
