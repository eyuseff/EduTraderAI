from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from spikes.execution_durability.common.models import EnvironmentStatus, SpikeResult
from spikes.execution_durability.common.scenarios import SCENARIOS


def test_shared_scenario_catalog_has_required_30_scenarios() -> None:
    assert len(SCENARIOS) == 30
    assert [scenario.scenario_id for scenario in SCENARIOS] == [
        f"S{index:02d}" for index in range(1, 31)
    ]


def test_spike_result_is_immutable_and_safe() -> None:
    result = SpikeResult(
        backend="sqlite",
        scenario_id="S01",
        environment_status=EnvironmentStatus.EXECUTED,
        executed=True,
        passed=True,
        expected_outcome="aggregate_created",
        observed_normalized_outcome="aggregate_created",
    )

    with pytest.raises(FrozenInstanceError):
        result.backend = "postgresql"

    assert result.to_primitive()["backend"] == "sqlite"


def test_spike_result_rejects_sensitive_notes() -> None:
    with pytest.raises(ValueError):
        SpikeResult(
            backend="sqlite",
            scenario_id="S30",
            environment_status=EnvironmentStatus.EXECUTED,
            executed=True,
            passed=False,
            expected_outcome="no_secrets_persisted",
            observed_normalized_outcome="secret_detected",
            safe_notes="secret appeared",
        )
