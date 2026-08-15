"""Focused v003 schema-version migration specifications.

Every database path is derived from pytest's ``tmp_path``.  This module exercises
only the SQLite schema and explicit migration runner; it has no runtime, broker,
network, credential, or production-state dependency.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from volcanoes.infrastructure.execution_persistence.sqlite import (
    CONTRACT_ALIGNMENT_MIGRATION,
    INITIAL_MIGRATION,
    KNOWN_MIGRATIONS,
    SCHEMA_VERSION_TEXT_MIGRATION,
    SqliteExecutionMigration,
    apply_pending_migrations,
    inspect_schema_state,
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionMigrationError,
    SqliteExecutionSchemaError,
)

NOW = datetime(2026, 8, 14, 12, 0, tzinfo=UTC)
TIMESTAMP = "2026-08-14T12:00:00.000000Z"
EXECUTION_TABLES = (
    "execution_aggregates",
    "execution_commands",
    "execution_idempotency",
    "execution_transitions",
    "execution_broker_references",
    "execution_receipts",
    "execution_failures",
    "execution_approvals",
    "execution_reconciliations",
)
PRIMARY_KEYS = {
    "execution_aggregates": "aggregate_id",
    "execution_commands": "command_id",
    "execution_idempotency": "idempotency_key",
    "execution_transitions": "transition_record_id",
    "execution_broker_references": "broker_reference",
    "execution_receipts": "receipt_fingerprint",
    "execution_failures": "failure_fingerprint",
    "execution_approvals": "approval_fingerprint",
    "execution_reconciliations": "reconciliation_id",
}
IDENTITY_PREFIXES = {
    "execution_aggregates": "agg",
    "execution_commands": "cmd",
    "execution_idempotency": "idem",
    "execution_transitions": "transition",
    "execution_broker_references": "broker",
    "execution_receipts": "receipt",
    "execution_failures": "failure",
    "execution_approvals": "approval",
    "execution_reconciliations": "reconciliation",
}
EXPECTED_FOREIGN_KEYS = {
    "execution_aggregates": set(),
    "execution_commands": {("aggregate_id", "execution_aggregates")},
    "execution_idempotency": {
        ("aggregate_id", "execution_aggregates"),
        ("command_id", "execution_commands"),
    },
    "execution_transitions": {
        ("aggregate_id", "execution_aggregates"),
        ("command_id", "execution_commands"),
        ("idempotency_key", "execution_idempotency"),
    },
    "execution_broker_references": {
        ("aggregate_id", "execution_aggregates"),
        ("command_id", "execution_commands"),
    },
    "execution_receipts": {
        ("aggregate_id", "execution_aggregates"),
        ("command_id", "execution_commands"),
    },
    "execution_failures": {
        ("aggregate_id", "execution_aggregates"),
        ("command_id", "execution_commands"),
    },
    "execution_approvals": set(),
    "execution_reconciliations": {("aggregate_id", "execution_aggregates")},
}
EXPECTED_INDEX_ATTACHMENTS = {
    "idx_execution_aggregates_lifecycle_state": "execution_aggregates",
    "idx_execution_aggregates_consequential_state": "execution_aggregates",
    "idx_execution_aggregates_updated_at": "execution_aggregates",
    "idx_execution_commands_aggregate_received": "execution_commands",
    "idx_execution_commands_idempotency_key": "execution_commands",
    "idx_execution_idempotency_aggregate": "execution_idempotency",
    "idx_execution_transitions_command": "execution_transitions",
    "ux_execution_broker_references_active_aggregate": "execution_broker_references",
    "idx_execution_broker_references_aggregate_active": "execution_broker_references",
    "idx_execution_receipts_command_aggregate": "execution_receipts",
    "idx_execution_failures_command_aggregate": "execution_failures",
    "idx_execution_reconciliations_aggregate_unresolved": "execution_reconciliations",
}
SCHEMA_MIGRATION_INDEX_ATTACHMENT = {
    "idx_schema_migrations_resulting_version": "schema_migrations",
}
EXPECTED_TRIGGER_ATTACHMENTS = {
    "trg_execution_commands_no_update": "execution_commands",
    "trg_execution_commands_no_delete": "execution_commands",
    "trg_execution_transitions_no_update": "execution_transitions",
    "trg_execution_transitions_no_delete": "execution_transitions",
    "trg_execution_receipts_no_update": "execution_receipts",
    "trg_execution_receipts_no_delete": "execution_receipts",
    "trg_execution_failures_no_update": "execution_failures",
    "trg_execution_failures_no_delete": "execution_failures",
    "trg_execution_approvals_no_update": "execution_approvals",
    "trg_execution_approvals_no_delete": "execution_approvals",
    "trg_execution_reconciliations_no_update": "execution_reconciliations",
    "trg_execution_reconciliations_no_delete": "execution_reconciliations",
}
SCHEMA_MIGRATION_TRIGGER_ATTACHMENTS = {
    "trg_schema_migrations_no_update": "schema_migrations",
    "trg_schema_migrations_no_delete": "schema_migrations",
}
CANONICAL_VERSIONS = (
    "1",
    "2",
    "9223372036854775808",
    "12345678901234567890123456789012345678901234567890",
)


def _connection(tmp_path: Path, name: str) -> sqlite3.Connection:
    return open_sqlite_execution_connection(tmp_path / name)


def _apply_through_v002(connection: sqlite3.Connection) -> None:
    result = apply_pending_migrations(
        connection,
        (INITIAL_MIGRATION, CONTRACT_ALIGNMENT_MIGRATION),
        applied_at=NOW,
        application_version="f5e2c-v003-test",
    )
    assert result.applied_migration_ids == ("v001", "v002")
    assert result.schema_state.current_version == 2
    migration_ids = tuple(
        row["migration_id"]
        for row in connection.execute(
            "SELECT migration_id FROM schema_migrations "
            "ORDER BY resulting_schema_version"
        ).fetchall()
    )
    assert migration_ids == ("v001", "v002")
    assert (
        connection.execute(
            "SELECT count(*) FROM schema_migrations WHERE migration_id = 'v003'"
        ).fetchone()[0]
        == 0
    )


def _apply_current(connection: sqlite3.Connection) -> None:
    result = apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS[:3],
        applied_at=NOW,
        application_version="f5e2c-v003-test",
    )
    assert result.schema_state.current_version == 3


def _row_snapshot(
    connection: sqlite3.Connection,
) -> dict[str, tuple[tuple[object, ...], ...]]:
    return {
        table: tuple(
            tuple(row)
            for row in connection.execute(
                f"SELECT * FROM {table} ORDER BY {PRIMARY_KEYS[table]}"
            ).fetchall()
        )
        for table in EXECUTION_TABLES
    }


def _schema_snapshot(connection: sqlite3.Connection) -> dict[str, object]:
    return {
        "columns": {
            table: tuple(
                tuple(row)
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            )
            for table in EXECUTION_TABLES
        },
        "foreign_keys": {
            table: tuple(
                tuple(row)
                for row in connection.execute(
                    f"PRAGMA foreign_key_list({table})"
                ).fetchall()
            )
            for table in EXECUTION_TABLES
        },
        "indexes": tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT name, tbl_name FROM sqlite_master "
                "WHERE type = 'index' AND name NOT LIKE 'sqlite_%' ORDER BY name"
            ).fetchall()
        ),
        "triggers": tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT name, tbl_name, sql FROM sqlite_master "
                "WHERE type = 'trigger' ORDER BY name"
            ).fetchall()
        ),
        "migrations": tuple(
            tuple(row)
            for row in connection.execute(
                "SELECT migration_id, checksum, previous_schema_version, "
                "resulting_schema_version FROM schema_migrations "
                "ORDER BY resulting_schema_version"
            ).fetchall()
        ),
    }


def _insert_all_rows(
    connection: sqlite3.Connection,
    suffix: str,
    schema_versions: dict[str, object],
) -> None:
    """Insert a valid representative row in every execution table."""

    aggregate = f"agg-{suffix}"
    command = f"cmd-{suffix}"
    idempotency = f"idem-{suffix}"
    transition = f"transition-{suffix}"
    broker_reference = f"broker-{suffix}"
    receipt = f"receipt-{suffix}"
    failure = f"failure-{suffix}"
    approval = f"approval-{suffix}"
    reconciliation = f"reconciliation-{suffix}"
    connection.execute(
        """
        INSERT INTO execution_aggregates (
            aggregate_id, correlation_id, lifecycle_state, execution_revision,
            cumulative_filled_quantity, requested_quantity, active_broker_reference,
            outcome_unknown, reconciliation_required, command_terminal,
            aggregate_terminal,
            last_transition_id, last_command_id, last_idempotency_key,
            last_receipt_fingerprint, last_failure_fingerprint, mode, created_at,
            updated_at, schema_version, record_fingerprint
        ) VALUES (?, ?, 'CREATED', 0, '0', '1', NULL, 0, 0, 0, 0, 'PX-TRN-000',
                  NULL, NULL, NULL, NULL, 'PAPER', ?, ?, ?, ?)
        """,
        (
            aggregate,
            f"corr-{suffix}",
            TIMESTAMP,
            TIMESTAMP,
            schema_versions["execution_aggregates"],
            f"aggregate-fp-{suffix}",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_commands (
            command_id, aggregate_id, correlation_id, idempotency_key, operation,
            expected_execution_revision, canonical_payload_fingerprint,
            canonical_command_json, approval_fingerprint, policy_fingerprint,
            received_at, processing_outcome, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, 'SUBMIT', 0, ?, '{}', ?, ?, ?, 'PENDING', 'PAPER', ?, ?)
        """,
        (
            command,
            aggregate,
            f"corr-{suffix}",
            idempotency,
            f"payload-{suffix}",
            approval,
            f"policy-{suffix}",
            TIMESTAMP,
            schema_versions["execution_commands"],
            f"command-fp-{suffix}",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_idempotency (
            idempotency_key, logical_operation_fingerprint, command_id, aggregate_id,
            reservation_status, original_result_fingerprint, created_at, resolved_at,
            conflict, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, 'RESERVED', NULL, ?, NULL, 0, 'PAPER', ?, ?)
        """,
        (
            idempotency,
            f"logical-{suffix}",
            command,
            aggregate,
            TIMESTAMP,
            schema_versions["execution_idempotency"],
            f"idempotency-fp-{suffix}",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_transitions (
            transition_record_id, aggregate_id, transition_id, source_state,
            destination_state, previous_revision, next_revision, lifecycle_input_kind,
            input_identity, command_id, correlation_id, idempotency_key,
            broker_observation_identity, receipt_fingerprint, failure_fingerprint,
            replay_indicator, side_effect_intent_kinds_json, evidence_intent_kinds_json,
            safe_reason_code, mode, recorded_at, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, 'CREATED', 'READY_FOR_DISPATCH', 0, 1, 'COMMAND', ?, ?, ?, ?,
                  NULL, NULL, NULL, 'NONE', '[]', '[]', 'OK', 'PAPER', ?, ?, ?)
        """,
        (
            transition,
            aggregate,
            f"PX-TRN-{suffix}",
            f"input-{suffix}",
            command,
            f"corr-{suffix}",
            idempotency,
            TIMESTAMP,
            schema_versions["execution_transitions"],
            f"transition-fp-{suffix}",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_broker_references (
            broker_reference, aggregate_id, command_id, adapter_identity,
            reference_status,
            first_seen_at, last_seen_at, active, replaced_by_reference, mode,
            schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, 'ACTIVE', ?, ?, 1, NULL, 'PAPER', ?, ?)
        """,
        (
            broker_reference,
            aggregate,
            command,
            f"adapter-{suffix}",
            TIMESTAMP,
            TIMESTAMP,
            schema_versions["execution_broker_references"],
            f"broker-fp-{suffix}",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_receipts (
            receipt_fingerprint, aggregate_id, command_id, correlation_id, operation,
            receipt_kind, status, observed_execution_revision, observed_at,
            message_code, broker_reference, outcome_known, reconciliation_required,
            recorded_at, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, 'SUBMIT', 'COMMAND_ACCEPTED_LOCALLY', 'CREATED', 1, ?,
                  'OK', ?, 1, 0, ?, 'PAPER', ?, ?)
        """,
        (
            receipt,
            aggregate,
            command,
            f"corr-{suffix}",
            TIMESTAMP,
            broker_reference,
            TIMESTAMP,
            schema_versions["execution_receipts"],
            f"receipt-fp-{suffix}",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_failures (
            failure_fingerprint, aggregate_id, command_id, correlation_id, failure_kind,
            severity, code, safe_message, retryable, terminal, reconciliation_required,
            operator_action_required, authority_impacting, recorded_at, mode,
            schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, 'CONTRACT_VALIDATION', 'INFO', 'SAFE', 'safe message',
                  0, 0, 0, 0, 0, ?, 'PAPER', ?, ?)
        """,
        (
            failure,
            aggregate,
            command,
            f"corr-{suffix}",
            TIMESTAMP,
            schema_versions["execution_failures"],
            f"failure-fp-{suffix}",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_approvals (
            approval_fingerprint, bound_fingerprint, approval_kind,
            approver_safe_reference, approved_at, expires_at, revocation_reference,
            recorded_at, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, 'OPERATOR', ?, ?, ?, NULL, ?, 'PAPER', ?, ?)
        """,
        (
            approval,
            f"bound-{suffix}",
            f"operator-{suffix}",
            TIMESTAMP,
            TIMESTAMP,
            TIMESTAMP,
            schema_versions["execution_approvals"],
            f"approval-fp-{suffix}",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_reconciliations (
            reconciliation_id, aggregate_id, starting_local_revision,
            starting_lifecycle_state, broker_observation_references_json,
            result_classification, resulting_transition_id, resulting_revision,
            operator_action_required, unresolved, safe_reason_code, recorded_at, mode,
            schema_version, record_fingerprint
        ) VALUES (?, ?, 1, 'READY_FOR_DISPATCH', '[]', 'UNRESOLVED', ?, 1, 1, 1,
                  'SAFE', ?, 'PAPER', ?, ?)
        """,
        (
            reconciliation,
            aggregate,
            f"PX-TRN-{suffix}",
            TIMESTAMP,
            schema_versions["execution_reconciliations"],
            f"reconciliation-fp-{suffix}",
        ),
    )


def _insert_v003_rows(
    connection: sqlite3.Connection,
    suffix: str,
    value: object,
) -> None:
    _insert_all_rows(connection, suffix, {table: value for table in EXECUTION_TABLES})


def _object_map(connection: sqlite3.Connection, object_type: str) -> dict[str, str]:
    return {
        str(row["name"]): str(row["tbl_name"])
        for row in connection.execute(
            "SELECT name, tbl_name FROM sqlite_master "
            "WHERE type = ? AND name NOT LIKE 'sqlite_%'",
            (object_type,),
        )
    }


def _migration_rows(connection: sqlite3.Connection) -> tuple[sqlite3.Row, ...]:
    return tuple(
        connection.execute(
            "SELECT migration_id, checksum, previous_schema_version, "
            "resulting_schema_version FROM schema_migrations "
            "ORDER BY resulting_schema_version"
        ).fetchall()
    )


def _insert_transition_for_uniqueness_case(
    connection: sqlite3.Connection,
    *,
    transition_record_id: str,
    aggregate_id: str,
    transition_id: str,
    previous_revision: int,
    next_revision: int,
    input_identity: str,
    command_id: str,
    correlation_id: str,
    idempotency_key: str,
    record_fingerprint: str,
) -> None:
    connection.execute(
        """
        INSERT INTO execution_transitions (
            transition_record_id, aggregate_id, transition_id, source_state,
            destination_state, previous_revision, next_revision, lifecycle_input_kind,
            input_identity, command_id, correlation_id, idempotency_key,
            broker_observation_identity, receipt_fingerprint, failure_fingerprint,
            replay_indicator, side_effect_intent_kinds_json, evidence_intent_kinds_json,
            safe_reason_code, mode, recorded_at, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, 'READY_FOR_DISPATCH', 'DISPATCHED', ?, ?, 'COMMAND', ?,
                  ?, ?, ?, NULL, NULL, NULL, 'NONE', '[]', '[]', 'OK', 'PAPER',
                  ?, '1', ?)
        """,
        (
            transition_record_id,
            aggregate_id,
            transition_id,
            previous_revision,
            next_revision,
            input_identity,
            command_id,
            correlation_id,
            idempotency_key,
            TIMESTAMP,
            record_fingerprint,
        ),
    )


def test_fresh_database_applies_v001_v002_and_v003(tmp_path: Path) -> None:
    connection = _connection(tmp_path, "fresh.sqlite")
    try:
        _apply_current(connection)
        assert (
            inspect_schema_state(
                connection,
                known_migrations=KNOWN_MIGRATIONS,
            ).current_version
            == 3
        )
        assert tuple(row["migration_id"] for row in _migration_rows(connection)) == (
            "v001",
            "v002",
            "v003",
        )
        assert (
            _migration_rows(connection)[2]["checksum"]
            == SCHEMA_VERSION_TEXT_MIGRATION.checksum
        )
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert set(EXECUTION_TABLES).issubset(tables)
        assert not any(name.startswith("_v002_") for name in tables)
        assert "_v003_guard" not in tables
        assert (
            connection.execute(
                "SELECT name FROM sqlite_temp_master "
                "WHERE type = 'table' AND name = '_v003_guard'"
            ).fetchall()
            == []
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_populated_v002_migrates_all_rows_without_non_version_data_change(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path, "preservation.sqlite")
    try:
        _apply_through_v002(connection)
        _insert_all_rows(
            connection,
            "preserved",
            {table: 1 for table in EXECUTION_TABLES},
        )
        before = _row_snapshot(connection)
        before_schema = _schema_snapshot(connection)
        _apply_current(connection)
        after = _row_snapshot(connection)
        after_schema = _schema_snapshot(connection)
        assert {table: len(rows) for table, rows in before.items()} == {
            table: len(rows) for table, rows in after.items()
        }
        for table in EXECUTION_TABLES:
            version_index = tuple(
                row["name"] for row in connection.execute(f"PRAGMA table_info({table})")
            ).index("schema_version")
            for old, new in zip(before[table], after[table], strict=True):
                assert old[:version_index] == new[:version_index]
                assert old[version_index] == 1
                assert new[version_index] == "1"
                assert old[version_index + 1 :] == new[version_index + 1 :]
            assert [
                tuple(row)
                for row in connection.execute(
                    f"SELECT DISTINCT typeof(schema_version) FROM {table}"
                ).fetchall()
            ] == [("text",)]
        assert set(EXPECTED_INDEX_ATTACHMENTS).issubset(
            _object_map(connection, "index")
        )
        assert set(EXPECTED_TRIGGER_ATTACHMENTS).issubset(
            _object_map(connection, "trigger")
        )
        objects = tuple(
            connection.execute(
                "SELECT name FROM sqlite_master ORDER BY name"
            ).fetchall()
        )
        assert not any(str(row[0]).startswith("_v002_") for row in objects)
        assert (
            connection.execute(
                "SELECT name FROM sqlite_temp_master "
                "WHERE type = 'table' AND name = '_v003_guard'"
            ).fetchall()
            == []
        )
        assert len(before_schema["migrations"]) == 2
        assert tuple(
            row
            for row in before_schema["triggers"]
            if row[0] in EXPECTED_TRIGGER_ATTACHMENTS
        ) == tuple(
            row
            for row in after_schema["triggers"]
            if row[0] in EXPECTED_TRIGGER_ATTACHMENTS
        )
        assert tuple(
            row
            for row in before_schema["triggers"]
            if row[0] in SCHEMA_MIGRATION_TRIGGER_ATTACHMENTS
        ) == tuple(
            row
            for row in after_schema["triggers"]
            if row[0] in SCHEMA_MIGRATION_TRIGGER_ATTACHMENTS
        )
        assert tuple(row["migration_id"] for row in _migration_rows(connection)) == (
            "v001",
            "v002",
            "v003",
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_schema_version_columns_are_text_not_null_and_store_canonical_text(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path, "declarations.sqlite")
    try:
        _apply_current(connection)
        _insert_v003_rows(connection, "declared", "1")
        for table in EXECUTION_TABLES:
            column = next(
                row
                for row in connection.execute(f"PRAGMA table_info({table})")
                if row["name"] == "schema_version"
            )
            assert column["type"] == "TEXT"
            assert column["notnull"] == 1
            assert [
                tuple(row)
                for row in connection.execute(
                    f"SELECT schema_version, typeof(schema_version) FROM {table}"
                ).fetchall()
            ] == [("1", "text")]
    finally:
        connection.close()


@pytest.mark.parametrize("table_name", EXECUTION_TABLES)
@pytest.mark.parametrize("invalid_value", ("0", "01", "1.0", "version"))
def test_every_schema_version_column_rejects_noncanonical_text(
    tmp_path: Path, table_name: str, invalid_value: str
) -> None:
    connection = _connection(
        tmp_path,
        f"invalid-{table_name}-{invalid_value}.sqlite",
    )
    try:
        _apply_current(connection)
        versions = {table: "1" for table in EXECUTION_TABLES}
        versions[table_name] = invalid_value
        with pytest.raises(sqlite3.IntegrityError):
            _insert_all_rows(
                connection,
                f"invalid-{table_name}-{invalid_value}",
                versions,
            )
    finally:
        connection.close()


@pytest.mark.parametrize("table_name", EXECUTION_TABLES)
@pytest.mark.parametrize("schema_version", CANONICAL_VERSIONS)
def test_every_table_accepts_arbitrary_size_canonical_text_schema_versions(
    tmp_path: Path, table_name: str, schema_version: str
) -> None:
    connection = _connection(
        tmp_path,
        f"domain-{table_name}-{schema_version[:4]}.sqlite",
    )
    try:
        _apply_current(connection)
        _insert_v003_rows(connection, f"{table_name}-{schema_version}", schema_version)
        row = connection.execute(
            f"SELECT schema_version, typeof(schema_version) FROM {table_name} "
            f"WHERE {PRIMARY_KEYS[table_name]} = ?",
            (f"{IDENTITY_PREFIXES[table_name]}-{table_name}-{schema_version}",),
        ).fetchone()
        assert row is not None
        assert tuple(row) == (schema_version, "text")
        assert int(str(row[0])) == int(schema_version)
    finally:
        connection.close()


def test_text_affinity_stores_small_integer_as_canonical_text_for_future_adapter_intent(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path, "affinity.sqlite")
    try:
        _apply_current(connection)
        _insert_v003_rows(connection, "affinity", 1)
        row = connection.execute(
            "SELECT schema_version, typeof(schema_version) FROM execution_aggregates"
        ).fetchone()
        assert row is not None
        assert tuple(row) == ("1", "text")
    finally:
        connection.close()


def test_v003_recreates_exact_named_index_and_trigger_inventory(tmp_path: Path) -> None:
    connection = _connection(tmp_path, "objects.sqlite")
    try:
        _apply_current(connection)
        indexes = _object_map(connection, "index")
        triggers = _object_map(connection, "trigger")
        assert indexes == {
            **EXPECTED_INDEX_ATTACHMENTS,
            **SCHEMA_MIGRATION_INDEX_ATTACHMENT,
        }
        assert triggers == {
            **EXPECTED_TRIGGER_ATTACHMENTS,
            **SCHEMA_MIGRATION_TRIGGER_ATTACHMENTS,
        }
        objects = tuple(
            connection.execute(
                "SELECT name FROM sqlite_master ORDER BY name"
            ).fetchall()
        )
        assert not any(str(row[0]).startswith("_v002_") for row in objects)
    finally:
        connection.close()


def test_v003_preserves_foreign_keys_transition_uniqueness_and_deferrability(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path, "foreign-keys.sqlite")
    try:
        _apply_current(connection)
        _insert_v003_rows(connection, "constraints", "1")
        for table_name, expected_edges in EXPECTED_FOREIGN_KEYS.items():
            actual_edges = {
                (row["from"], row["table"])
                for row in connection.execute(
                    f"PRAGMA foreign_key_list({table_name})"
                ).fetchall()
            }
            assert actual_edges == expected_edges
        command_sql = str(
            connection.execute(
                "SELECT sql FROM sqlite_master "
                "WHERE type = 'table' AND name = 'execution_commands'"
            ).fetchone()[0]
        )
        assert "DEFERRABLE INITIALLY DEFERRED" in command_sql
        baseline_count = connection.execute(
            "SELECT count(*) FROM execution_transitions"
        ).fetchone()[0]
        baseline_transition = tuple(
            connection.execute(
                "SELECT * FROM execution_transitions "
                "WHERE transition_record_id = 'transition-constraints'"
            ).fetchone()
        )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="execution_transitions.transition_record_id",
        ):
            _insert_transition_for_uniqueness_case(
                connection,
                transition_record_id="transition-constraints",
                aggregate_id="agg-constraints",
                transition_id="PX-TRN-RECORD-ID",
                previous_revision=1,
                next_revision=2,
                input_identity="record-id-only",
                command_id="cmd-constraints",
                correlation_id="corr-constraints",
                idempotency_key="idem-constraints",
                record_fingerprint="transition-record-id-only-fp",
            )
        assert (
            connection.execute("SELECT count(*) FROM execution_transitions").fetchone()[
                0
            ]
            == baseline_count
        )
        assert (
            tuple(
                connection.execute(
                    "SELECT * FROM execution_transitions "
                    "WHERE transition_record_id = 'transition-constraints'"
                ).fetchone()
            )
            == baseline_transition
        )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="execution_transitions.aggregate_id, "
            "execution_transitions.next_revision",
        ):
            _insert_transition_for_uniqueness_case(
                connection,
                transition_record_id="transition-next-revision-only",
                aggregate_id="agg-constraints",
                transition_id="PX-TRN-NEXT-REVISION",
                previous_revision=0,
                next_revision=1,
                input_identity="next-revision-only",
                command_id="cmd-constraints",
                correlation_id="corr-constraints",
                idempotency_key="idem-constraints",
                record_fingerprint="transition-next-revision-only-fp",
            )
        assert (
            connection.execute("SELECT count(*) FROM execution_transitions").fetchone()[
                0
            ]
            == baseline_count
        )
        assert (
            tuple(
                connection.execute(
                    "SELECT * FROM execution_transitions "
                    "WHERE transition_record_id = 'transition-constraints'"
                ).fetchone()
            )
            == baseline_transition
        )
        with pytest.raises(
            sqlite3.IntegrityError,
            match="execution_transitions.aggregate_id, "
            "execution_transitions.transition_id",
        ):
            _insert_transition_for_uniqueness_case(
                connection,
                transition_record_id="transition-transition-id-only",
                aggregate_id="agg-constraints",
                transition_id="PX-TRN-constraints",
                previous_revision=1,
                next_revision=2,
                input_identity="transition-id-only",
                command_id="cmd-constraints",
                correlation_id="corr-constraints",
                idempotency_key="idem-constraints",
                record_fingerprint="transition-transition-id-only-fp",
            )
        assert (
            connection.execute("SELECT count(*) FROM execution_transitions").fetchone()[
                0
            ]
            == baseline_count
        )
        assert (
            tuple(
                connection.execute(
                    "SELECT * FROM execution_transitions "
                    "WHERE transition_record_id = 'transition-constraints'"
                ).fetchone()
            )
            == baseline_transition
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO execution_commands SELECT * FROM execution_commands"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO execution_idempotency SELECT * FROM execution_idempotency"
            )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_v003_preserves_all_append_only_table_triggers(tmp_path: Path) -> None:
    connection = _connection(tmp_path, "append-only.sqlite")
    try:
        _apply_current(connection)
        _insert_v003_rows(connection, "append", "1")
        for trigger_name, table_name in EXPECTED_TRIGGER_ATTACHMENTS.items():
            primary_key = PRIMARY_KEYS[table_name]
            operation = "UPDATE" if trigger_name.endswith("no_update") else "DELETE"
            statement = (
                f"UPDATE {table_name} SET {primary_key} = {primary_key}"
                if operation == "UPDATE"
                else f"DELETE FROM {table_name}"
            )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
    finally:
        connection.close()


def test_v003_rerun_is_idempotent_for_metadata_rows_and_schema_objects(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path, "rerun.sqlite")
    try:
        _apply_current(connection)
        _insert_v003_rows(connection, "rerun", "2")
        before_rows = _row_snapshot(connection)
        before_schema = _schema_snapshot(connection)
        result = apply_pending_migrations(
            connection,
            KNOWN_MIGRATIONS[:3],
            applied_at=NOW,
            application_version="f5e2c-v003-test",
        )
        assert result.changed is False
        assert result.applied_migration_ids == ()
        assert _row_snapshot(connection) == before_rows
        assert _schema_snapshot(connection) == before_schema
        assert (
            connection.execute(
                "SELECT count(*) FROM schema_migrations WHERE migration_id = 'v003'"
            ).fetchone()[0]
            == 1
        )
    finally:
        connection.close()


def test_v003_checksum_mismatch_rejects_without_schema_or_metadata_mutation(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path, "checksum.sqlite")
    try:
        _apply_through_v002(connection)
        _insert_all_rows(
            connection,
            "checksum",
            {table: 1 for table in EXECUTION_TABLES},
        )
        _apply_current(connection)
        before_rows = _row_snapshot(connection)
        before_schema = _schema_snapshot(connection)
        assert (
            inspect_schema_state(
                connection,
                known_migrations=KNOWN_MIGRATIONS,
            ).current_version
            == 3
        )
        altered = SqliteExecutionMigration.create(
            migration_id="v003",
            name=SCHEMA_VERSION_TEXT_MIGRATION.name,
            previous_version=2,
            resulting_version=3,
            sql_text=SCHEMA_VERSION_TEXT_MIGRATION.sql_text + "\n-- altered\n",
            irreversible=True,
            safe_description=SCHEMA_VERSION_TEXT_MIGRATION.safe_description,
        )
        with pytest.raises(SqliteExecutionMigrationError, match="checksum mismatch"):
            apply_pending_migrations(
                connection,
                (INITIAL_MIGRATION, CONTRACT_ALIGNMENT_MIGRATION, altered),
                applied_at=NOW,
                application_version="f5e2c-v003-test",
            )
        assert _row_snapshot(connection) == before_rows
        assert _schema_snapshot(connection) == before_schema
        objects = tuple(
            connection.execute(
                "SELECT name FROM sqlite_master ORDER BY name"
            ).fetchall()
        )
        assert not any(str(row[0]).startswith("_v002_") for row in objects)
        assert (
            connection.execute(
                "SELECT name FROM sqlite_temp_master "
                "WHERE type = 'table' AND name = '_v003_guard'"
            ).fetchall()
            == []
        )
        assert (
            inspect_schema_state(
                connection,
                known_migrations=KNOWN_MIGRATIONS,
            ).current_version
            == 3
        )
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_v003_state_rejects_unknown_future_migration_without_weakening_schema_checks(
    tmp_path: Path,
) -> None:
    connection = _connection(tmp_path, "future.sqlite")
    try:
        _apply_current(connection)
        connection.execute(
            "INSERT INTO schema_migrations ("
            "migration_id, migration_name, checksum, applied_at, application_version, "
            "previous_schema_version, resulting_schema_version, safe_notes"
            ") VALUES ('v999', 'future', 'checksum', ?, 'future', 3, 999, 'future')",
            (TIMESTAMP,),
        )
        state = inspect_schema_state(connection, known_migrations=KNOWN_MIGRATIONS)
        assert state.incompatible_reason == "unknown newer schema"
        with pytest.raises(SqliteExecutionSchemaError, match="unknown newer schema"):
            _apply_current(connection)
    finally:
        connection.close()
