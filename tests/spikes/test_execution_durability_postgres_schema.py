from __future__ import annotations

from spikes.execution_durability.common.models import EnvironmentStatus
from spikes.execution_durability.common.scenarios import SCENARIOS
from spikes.execution_durability.postgres.runner import (
    postgres_runtime_available,
    run_postgres_scenarios,
    schema_text,
    static_assessment_notes,
)


def test_postgres_schema_contains_required_tables_and_cas_notes() -> None:
    sql = schema_text().lower()

    assert "execution_aggregates" in sql
    assert "execution_commands" in sql
    assert "execution_idempotency" in sql
    assert "execution_transitions" in sql
    assert "execution_broker_references" in sql
    assert "select aggregate_id, execution_revision" in sql
    assert "for update" in sql


def test_postgres_runtime_results_skip_when_environment_unavailable() -> None:
    results = run_postgres_scenarios()

    assert len(results) == len(SCENARIOS)
    if not postgres_runtime_available():
        assert all(result.executed is False for result in results)
        assert all(
            result.environment_status
            is EnvironmentStatus.NOT_EXECUTED_ENVIRONMENT_UNAVAILABLE
            for result in results
        )
        assert all(result.evidence_limitation for result in results)


def test_postgres_static_assessment_has_required_semantics() -> None:
    notes = static_assessment_notes()

    assert notes["schema_contains_required_tables"] == "True"
    assert "FOR UPDATE" in notes["row_level_locking"]
    assert "UPDATE" in notes["cas"]
