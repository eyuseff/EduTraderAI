from __future__ import annotations

import sqlite3

from spikes.execution_durability.common.scenarios import SCENARIOS
from spikes.execution_durability.sqlite.runner import (
    initialize_database,
    run_sqlite_scenarios,
)


def test_sqlite_schema_creation_enables_required_tables(tmp_path) -> None:
    db_path = tmp_path / "spike.sqlite3"
    connection = initialize_database(db_path)
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    connection.close()

    assert "execution_aggregates" in tables
    assert "execution_commands" in tables
    assert "execution_idempotency" in tables
    assert "execution_transitions" in tables
    assert "execution_broker_references" in tables
    assert "schema_migrations" in tables


def test_sqlite_scenarios_all_execute_and_pass(tmp_path) -> None:
    results = run_sqlite_scenarios(tmp_path / "scenario.sqlite3")

    assert len(results) == len(SCENARIOS)
    assert all(result.executed for result in results)
    assert all(result.passed is True for result in results)


def test_sqlite_command_and_idempotency_conflicts_are_normalized(tmp_path) -> None:
    results = {
        result.scenario_id: result
        for result in run_sqlite_scenarios(tmp_path / "conflicts.sqlite3")
    }

    assert results["S04"].observed_normalized_outcome == "command_payload_conflict"
    assert results["S07"].observed_normalized_outcome == "idempotency_conflict"
    assert results["S16"].observed_normalized_outcome == "broker_reference_conflict"


def test_sqlite_restart_migration_and_backup_scenarios_pass(tmp_path) -> None:
    results = {
        result.scenario_id: result
        for result in run_sqlite_scenarios(tmp_path / "restart.sqlite3")
    }

    assert (
        results["S22"].observed_normalized_outcome == "dispatch_intent_survives_reopen"
    )
    assert results["S26"].observed_normalized_outcome == "migration_v2_applied"
    assert results["S27"].observed_normalized_outcome == "backup_restore_consistent"


def test_sqlite_schema_rejects_foreign_key_violations(tmp_path) -> None:
    connection = initialize_database(tmp_path / "fk.sqlite3")
    try:
        connection.execute("""
            INSERT INTO execution_commands(
                command_id, aggregate_id, correlation_id, idempotency_key,
                operation, expected_execution_revision,
                canonical_payload_fingerprint, logical_operation_fingerprint,
                canonical_command_json, approval_fingerprint, policy_fingerprint,
                received_at, processing_outcome, schema_version, record_fingerprint
            ) VALUES ('cmd-missing', 'missing', 'corr', 'idem', 'SUBMIT', 0,
                'payload', 'logical', '{}', 'approval', 'policy',
                '2026-08-05T12:00:00Z', 'ACCEPTED', 1, 'pcm-missing')
            """)
    except sqlite3.IntegrityError:
        violated = True
    else:
        violated = False
    finally:
        connection.close()

    assert violated is True
