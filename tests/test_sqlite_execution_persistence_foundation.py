from __future__ import annotations

import ast
import hashlib
import importlib
import sqlite3
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

import pytest

from volcanoes.infrastructure.execution_persistence.sqlite import (
    CURRENT_SCHEMA_VERSION,
    CONTRACT_ALIGNMENT_MIGRATION,
    DEFAULT_BUSY_TIMEOUT_MS,
    INITIAL_MIGRATION,
    KNOWN_MIGRATIONS,
    MAXIMUM_SUPPORTED_SCHEMA_VERSION,
    MINIMUM_SUPPORTED_SCHEMA_VERSION,
    SqliteExecutionMigration,
    SCHEMA_VERSION_TEXT_MIGRATION,
    apply_pending_migrations,
    inspect_schema_state,
    open_sqlite_execution_connection,
    run_integrity_check,
    run_quick_check,
    validate_sqlite_execution_path,
    validate_sqlite_execution_schema,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionConfigurationError,
    SqliteExecutionMigrationError,
    SqliteExecutionPathError,
    SqliteExecutionSchemaError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.integrity import (
    check_aggregate_transition_revisions,
    check_broker_reference_ownership,
    check_foreign_keys,
    check_idempotency_bindings,
)

UTC_NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
UTC_TEXT = "2026-08-10T12:00:00.000000Z"
UTC_LATER_TEXT = "2026-08-10T12:01:00.000000Z"

EXPECTED_PUBLIC_EXPORTS = {
    "CURRENT_SCHEMA_VERSION",
    "CONTRACT_ALIGNMENT_MIGRATION",
    "DEFAULT_BUSY_TIMEOUT_MS",
    "INITIAL_MIGRATION",
    "KNOWN_MIGRATIONS",
    "SCHEMA_VERSION_TEXT_MIGRATION",
    "IntegrityCheckResult",
    "InvariantCheckResult",
    "MAXIMUM_SUPPORTED_SCHEMA_VERSION",
    "MINIMUM_SUPPORTED_SCHEMA_VERSION",
    "MigrationApplicationResult",
    "SchemaState",
    "SchemaValidationResult",
    "SqliteExecutionMigration",
    "apply_pending_migrations",
    "check_aggregate_transition_revisions",
    "check_broker_reference_ownership",
    "check_foreign_keys",
    "check_idempotency_bindings",
    "inspect_schema_state",
    "open_sqlite_execution_connection",
    "run_integrity_check",
    "run_quick_check",
    "validate_sqlite_execution_path",
    "validate_sqlite_execution_schema",
}

AUTHORIZED_PHASE2_SLICE2_CLASSES = {
    ("unit_of_work.py", "_SqliteExecutionTransaction"),
    ("repositories.py", "_RepositoryBase"),
    ("repositories.py", "SqliteExecutionAggregateRepository"),
    ("repositories.py", "SqliteExecutionCommandRepository"),
    ("repositories.py", "SqliteExecutionIdempotencyRepository"),
    ("repositories.py", "SqliteExecutionTransitionJournal"),
    ("repositories.py", "SqliteExecutionBrokerReferenceRepository"),
    ("repositories.py", "SqliteExecutionReceiptRepository"),
    ("repositories.py", "SqliteExecutionFailureRepository"),
    ("repositories.py", "SqliteExecutionApprovalRepository"),
    ("repositories.py", "SqliteExecutionReconciliationRepository"),
    ("repositories.py", "SqliteExecutionRestartDiscoveryRepository"),
}

EXPECTED_TABLES = {
    "execution_aggregates",
    "execution_commands",
    "execution_idempotency",
    "execution_transitions",
    "execution_broker_references",
    "execution_receipts",
    "execution_failures",
    "execution_approvals",
    "execution_reconciliations",
    "schema_migrations",
}

EXPECTED_INDEXES = {
    "idx_execution_aggregates_lifecycle_state",
    "idx_execution_aggregates_consequential_state",
    "idx_execution_aggregates_updated_at",
    "idx_execution_commands_aggregate_received",
    "idx_execution_commands_idempotency_key",
    "idx_execution_idempotency_aggregate",
    "idx_execution_transitions_command",
    "idx_execution_broker_references_aggregate_active",
    "idx_execution_receipts_command_aggregate",
    "idx_execution_failures_command_aggregate",
    "idx_execution_reconciliations_aggregate_unresolved",
    "idx_schema_migrations_resulting_version",
}

EXPECTED_TRIGGERS = {
    "trg_execution_commands_no_update",
    "trg_execution_commands_no_delete",
    "trg_execution_transitions_no_update",
    "trg_execution_transitions_no_delete",
    "trg_execution_receipts_no_update",
    "trg_execution_receipts_no_delete",
    "trg_execution_failures_no_update",
    "trg_execution_failures_no_delete",
    "trg_execution_approvals_no_update",
    "trg_execution_approvals_no_delete",
    "trg_execution_reconciliations_no_update",
    "trg_execution_reconciliations_no_delete",
    "trg_schema_migrations_no_update",
    "trg_schema_migrations_no_delete",
}

EXPECTED_COLUMNS = {
    "execution_aggregates": (
        "aggregate_id",
        "correlation_id",
        "lifecycle_state",
        "execution_revision",
        "cumulative_filled_quantity",
        "requested_quantity",
        "active_broker_reference",
        "outcome_unknown",
        "reconciliation_required",
        "command_terminal",
        "aggregate_terminal",
        "last_transition_id",
        "last_command_id",
        "last_idempotency_key",
        "last_receipt_fingerprint",
        "last_failure_fingerprint",
        "mode",
        "created_at",
        "updated_at",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_commands": (
        "command_id",
        "aggregate_id",
        "correlation_id",
        "idempotency_key",
        "operation",
        "expected_execution_revision",
        "canonical_payload_fingerprint",
        "canonical_command_json",
        "approval_fingerprint",
        "policy_fingerprint",
        "received_at",
        "processing_outcome",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_idempotency": (
        "idempotency_key",
        "logical_operation_fingerprint",
        "command_id",
        "aggregate_id",
        "reservation_status",
        "original_result_fingerprint",
        "created_at",
        "resolved_at",
        "conflict",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_transitions": (
        "transition_record_id",
        "aggregate_id",
        "transition_id",
        "source_state",
        "destination_state",
        "previous_revision",
        "next_revision",
        "lifecycle_input_kind",
        "input_identity",
        "command_id",
        "correlation_id",
        "idempotency_key",
        "broker_observation_identity",
        "receipt_fingerprint",
        "failure_fingerprint",
        "replay_indicator",
        "side_effect_intent_kinds_json",
        "evidence_intent_kinds_json",
        "safe_reason_code",
        "mode",
        "recorded_at",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_broker_references": (
        "broker_reference",
        "aggregate_id",
        "command_id",
        "adapter_identity",
        "reference_status",
        "first_seen_at",
        "last_seen_at",
        "active",
        "replaced_by_reference",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_receipts": (
        "receipt_fingerprint",
        "aggregate_id",
        "command_id",
        "correlation_id",
        "operation",
        "receipt_kind",
        "status",
        "observed_execution_revision",
        "observed_at",
        "message_code",
        "broker_reference",
        "outcome_known",
        "reconciliation_required",
        "recorded_at",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_failures": (
        "failure_fingerprint",
        "aggregate_id",
        "command_id",
        "correlation_id",
        "failure_kind",
        "severity",
        "code",
        "safe_message",
        "retryable",
        "terminal",
        "reconciliation_required",
        "operator_action_required",
        "authority_impacting",
        "recorded_at",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_approvals": (
        "approval_fingerprint",
        "bound_fingerprint",
        "approval_kind",
        "approver_safe_reference",
        "approved_at",
        "expires_at",
        "revocation_reference",
        "recorded_at",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_reconciliations": (
        "reconciliation_id",
        "aggregate_id",
        "starting_local_revision",
        "starting_lifecycle_state",
        "broker_observation_references_json",
        "result_classification",
        "resulting_transition_id",
        "resulting_revision",
        "operator_action_required",
        "unresolved",
        "safe_reason_code",
        "recorded_at",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "schema_migrations": (
        "migration_id",
        "migration_name",
        "checksum",
        "applied_at",
        "application_version",
        "previous_schema_version",
        "resulting_schema_version",
        "safe_notes",
    ),
}


def open_database(tmp_path: Path, name: str = "execution.sqlite") -> sqlite3.Connection:
    return open_sqlite_execution_connection(tmp_path / name)


def apply_initial_schema(connection: sqlite3.Connection):
    return apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS,
        applied_at=UTC_NOW,
        application_version="f5e2b-durable-test",
    )


def sqlite_objects(connection: sqlite3.Connection, object_type: str) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = ?",
        (object_type,),
    )
    return {str(row[0]) for row in rows if not str(row[0]).startswith("sqlite_")}


def table_columns(
    connection: sqlite3.Connection, table_name: str
) -> dict[str, sqlite3.Row]:
    return {
        str(row["name"]): row
        for row in connection.execute(f"PRAGMA table_info({table_name})")
    }


def foreign_key_edges(
    connection: sqlite3.Connection, table_name: str
) -> set[tuple[str, str]]:
    return {
        (str(row["from"]), str(row["table"]))
        for row in connection.execute(f"PRAGMA foreign_key_list({table_name})")
    }


def insert_minimum_aggregate_command_and_idempotency(
    connection: sqlite3.Connection,
) -> None:
    connection.execute(
        """
        INSERT INTO execution_aggregates (
            aggregate_id, correlation_id, lifecycle_state, execution_revision,
            cumulative_filled_quantity, requested_quantity, active_broker_reference,
            outcome_unknown, reconciliation_required, command_terminal, aggregate_terminal,
            last_transition_id, last_command_id, last_idempotency_key,
            last_receipt_fingerprint, last_failure_fingerprint, mode, created_at,
            updated_at, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "agg-1",
            "corr-1",
            "CREATED",
            0,
            "0",
            "1",
            None,
            0,
            0,
            0,
            0,
            "PX-TRN-000",
            None,
            None,
            None,
            None,
            "PAPER",
            UTC_TEXT,
            UTC_TEXT,
            1,
            "agg-fp",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_commands (
            command_id, aggregate_id, correlation_id, idempotency_key, operation,
            expected_execution_revision, canonical_payload_fingerprint,
            canonical_command_json, approval_fingerprint, policy_fingerprint,
            received_at, processing_outcome, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "cmd-1",
            "agg-1",
            "corr-1",
            "idem-1",
            "SUBMIT",
            0,
            "payload-fp",
            "{}",
            "approval-fp",
            "policy-fp",
            UTC_TEXT,
            "PENDING",
            "PAPER",
            1,
            "cmd-fp",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_idempotency (
            idempotency_key, logical_operation_fingerprint, command_id,
            aggregate_id, reservation_status, original_result_fingerprint,
            created_at, resolved_at, conflict, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "idem-1",
            "logical-fp",
            "cmd-1",
            "agg-1",
            "RESERVED",
            None,
            UTC_TEXT,
            None,
            0,
            "PAPER",
            1,
            "idem-fp",
        ),
    )


def insert_trigger_exercise_rows(connection: sqlite3.Connection) -> None:
    insert_minimum_aggregate_command_and_idempotency(connection)
    connection.execute(
        """
        INSERT INTO execution_transitions (
            transition_record_id, aggregate_id, transition_id, source_state,
            destination_state, previous_revision, next_revision, lifecycle_input_kind,
            input_identity, command_id, correlation_id, idempotency_key,
            broker_observation_identity, receipt_fingerprint, failure_fingerprint,
            replay_indicator, side_effect_intent_kinds_json, evidence_intent_kinds_json,
            safe_reason_code, mode, recorded_at, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "transition-1",
            "agg-1",
            "PX-TRN-001",
            "CREATED",
            "READY_FOR_DISPATCH",
            0,
            1,
            "COMMAND",
            "input-1",
            "cmd-1",
            "corr-1",
            "idem-1",
            None,
            None,
            None,
            "NONE",
            "[]",
            "[]",
            "OK",
            "PAPER",
            UTC_LATER_TEXT,
            1,
            "transition-fp",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_receipts (
            receipt_fingerprint, aggregate_id, command_id, correlation_id, operation,
            receipt_kind, status, observed_execution_revision, observed_at,
            message_code, broker_reference, outcome_known, reconciliation_required,
            recorded_at, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "receipt-fp",
            "agg-1",
            "cmd-1",
            "corr-1",
            "SUBMIT",
            "COMMAND_ACCEPTED_LOCALLY",
            "CREATED",
            1,
            UTC_LATER_TEXT,
            "OK",
            None,
            1,
            0,
            UTC_LATER_TEXT,
            "PAPER",
            1,
            "receipt-record-fp",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_failures (
            failure_fingerprint, aggregate_id, command_id, correlation_id,
            failure_kind, severity, code, safe_message, retryable, terminal,
            reconciliation_required, operator_action_required, authority_impacting,
            recorded_at, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "failure-fp",
            "agg-1",
            "cmd-1",
            "corr-1",
            "CONTRACT_VALIDATION",
            "INFO",
            "SAFE",
            "safe failure",
            0,
            1,
            0,
            0,
            0,
            UTC_LATER_TEXT,
            "PAPER",
            1,
            "failure-record-fp",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_approvals (
            approval_fingerprint, bound_fingerprint, approval_kind,
            approver_safe_reference, approved_at, recorded_at, mode, schema_version,
            record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "approval-1",
            "bound-fp",
            "OPERATOR",
            "operator",
            UTC_LATER_TEXT,
            UTC_LATER_TEXT,
            "PAPER",
            1,
            "approval-record-fp",
        ),
    )
    connection.execute(
        """
        INSERT INTO execution_reconciliations (
            reconciliation_id, aggregate_id, starting_local_revision,
            starting_lifecycle_state, broker_observation_references_json,
            result_classification, operator_action_required, unresolved,
            safe_reason_code, recorded_at, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "reconciliation-1",
            "agg-1",
            1,
            "READY_FOR_DISPATCH",
            "[]",
            "UNRESOLVED",
            1,
            1,
            "SAFE",
            UTC_LATER_TEXT,
            "PAPER",
            1,
            "reconciliation-record-fp",
        ),
    )


def test_public_exports_versions_and_import_have_no_filesystem_side_effects(tmp_path):
    before = sorted(
        path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")
    )
    module = importlib.import_module(
        "volcanoes.infrastructure.execution_persistence.sqlite"
    )
    after = sorted(
        path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*")
    )

    assert EXPECTED_PUBLIC_EXPORTS.issubset(set(module.__all__))
    assert CURRENT_SCHEMA_VERSION == 3
    assert MINIMUM_SUPPORTED_SCHEMA_VERSION == 1
    assert MAXIMUM_SUPPORTED_SCHEMA_VERSION == 3
    assert INITIAL_MIGRATION.migration_id == "v001"
    assert INITIAL_MIGRATION.previous_version == 0
    assert INITIAL_MIGRATION.resulting_version == 1
    assert CONTRACT_ALIGNMENT_MIGRATION.migration_id == "v002"
    assert CONTRACT_ALIGNMENT_MIGRATION.previous_version == 1
    assert CONTRACT_ALIGNMENT_MIGRATION.resulting_version == 2
    assert SCHEMA_VERSION_TEXT_MIGRATION.migration_id == "v003"
    assert SCHEMA_VERSION_TEXT_MIGRATION.previous_version == 2
    assert SCHEMA_VERSION_TEXT_MIGRATION.resulting_version == 3
    assert tuple(item.migration_id for item in KNOWN_MIGRATIONS) == (
        "v001",
        "v002",
        "v003",
    )
    assert after == before


def test_initial_migration_bootstraps_exact_schema_metadata_and_pragmas(tmp_path):
    connection = open_database(tmp_path)
    try:
        result = apply_initial_schema(connection)

        assert result.changed is True
        assert result.applied_migration_ids == ("v001", "v002", "v003")
        assert result.schema_state.current_version == 3
        assert sqlite_objects(connection, "table") == EXPECTED_TABLES
        assert EXPECTED_INDEXES.issubset(sqlite_objects(connection, "index"))
        assert sqlite_objects(connection, "trigger") == EXPECTED_TRIGGERS
        for table_name, expected_column_names in EXPECTED_COLUMNS.items():
            assert tuple(table_columns(connection, table_name)) == expected_column_names

        migration_rows = connection.execute("""
            SELECT migration_id, migration_name, checksum, application_version,
                   previous_schema_version, resulting_schema_version, safe_notes
            FROM schema_migrations
            """).fetchall()
        expected_sql = (
            resources.files(
                "volcanoes.infrastructure.execution_persistence.sqlite.migrations"
            )
            .joinpath("v001_initial_schema.sql")
            .read_text(encoding="utf-8")
            .replace("\r\n", "\n")
            .strip()
            + "\n"
        )
        independent_checksum = hashlib.sha256(expected_sql.encode("utf-8")).hexdigest()

        assert dict(migration_rows[0]) == {
            "migration_id": "v001",
            "migration_name": "initial execution persistence schema",
            "checksum": independent_checksum,
            "application_version": "f5e2b-durable-test",
            "previous_schema_version": 0,
            "resulting_schema_version": 1,
            "safe_notes": "Initial SQLite execution persistence schema.",
        }
        assert dict(migration_rows[1])["migration_id"] == "v002"
        assert dict(migration_rows[1])["previous_schema_version"] == 1
        assert dict(migration_rows[1])["resulting_schema_version"] == 2
        assert dict(migration_rows[2])["migration_id"] == "v003"
        assert dict(migration_rows[2])["previous_schema_version"] == 2
        assert dict(migration_rows[2])["resulting_schema_version"] == 3
        assert int(connection.execute("PRAGMA foreign_keys").fetchone()[0]) == 1
        assert (
            str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
            == "wal"
        )
        assert int(connection.execute("PRAGMA synchronous").fetchone()[0]) == 2
        assert int(connection.execute("PRAGMA busy_timeout").fetchone()[0]) == (
            DEFAULT_BUSY_TIMEOUT_MS
        )
        assert validate_sqlite_execution_schema(
            connection,
            expected_busy_timeout_ms=DEFAULT_BUSY_TIMEOUT_MS,
        ).passed
    finally:
        connection.close()


def test_schema_constraints_foreign_keys_and_uniqueness_are_enforced(tmp_path):
    connection = open_database(tmp_path)
    try:
        apply_initial_schema(connection)
        aggregate_columns = table_columns(connection, "execution_aggregates")
        assert aggregate_columns["aggregate_id"]["type"] == "TEXT"
        assert aggregate_columns["aggregate_id"]["pk"] == 1
        assert aggregate_columns["execution_revision"]["type"] == "INTEGER"
        assert aggregate_columns["record_fingerprint"]["notnull"] == 1
        assert ("aggregate_id", "execution_aggregates") in foreign_key_edges(
            connection,
            "execution_commands",
        )
        assert ("command_id", "execution_commands") in foreign_key_edges(
            connection,
            "execution_idempotency",
        )
        assert ("idempotency_key", "execution_idempotency") in foreign_key_edges(
            connection,
            "execution_transitions",
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO execution_aggregates (
                    aggregate_id, correlation_id, lifecycle_state, execution_revision,
                    cumulative_filled_quantity, outcome_unknown,
                    reconciliation_required, command_terminal, aggregate_terminal,
                    last_transition_id, mode, created_at, updated_at, schema_version,
                    record_fingerprint
                ) VALUES ('bad-revision', 'corr', 'CREATED', -1, '0', 0, 0, 0, 0,
                          'PX-TRN-000', 'PAPER', ?, ?, 1, 'fp')
                """,
                (UTC_TEXT, UTC_TEXT),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO execution_aggregates (
                    aggregate_id, correlation_id, lifecycle_state, execution_revision,
                    cumulative_filled_quantity, outcome_unknown,
                    reconciliation_required, command_terminal, aggregate_terminal,
                    last_transition_id, mode, created_at, updated_at, schema_version,
                    record_fingerprint
                ) VALUES ('live-mode', 'corr', 'CREATED', 0, '0', 0, 0, 0, 0,
                          'PX-TRN-000', 'LIVE', ?, ?, 1, 'fp')
                """,
                (UTC_TEXT, UTC_TEXT),
            )
    finally:
        connection.close()


def test_append_only_and_immutable_triggers_reject_update_and_delete(tmp_path):
    connection = open_database(tmp_path)
    try:
        apply_initial_schema(connection)
        insert_trigger_exercise_rows(connection)

        guarded_tables = {
            "execution_commands": "command_id",
            "execution_transitions": "transition_record_id",
            "execution_receipts": "receipt_fingerprint",
            "execution_failures": "failure_fingerprint",
            "execution_approvals": "approval_fingerprint",
            "execution_reconciliations": "reconciliation_id",
            "schema_migrations": "migration_id",
        }
        for table_name, primary_key in guarded_tables.items():
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    f"UPDATE {table_name} SET {primary_key} = {primary_key}"
                )
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"DELETE FROM {table_name}")
    finally:
        connection.close()


def test_migration_replay_checksum_mismatch_and_future_schema_rejection(tmp_path):
    connection = open_database(tmp_path)
    try:
        first = apply_initial_schema(connection)
        second = apply_initial_schema(connection)
        assert first.changed is True
        assert second.changed is False
        assert second.applied_migration_ids == ()

        tampered = SqliteExecutionMigration.create(
            migration_id="v001",
            name="initial execution persistence schema",
            previous_version=0,
            resulting_version=1,
            sql_text=INITIAL_MIGRATION.sql_text + "\n-- tampered\n",
            irreversible=True,
            safe_description="tampered",
        )
        with pytest.raises(SqliteExecutionMigrationError):
            apply_pending_migrations(
                connection,
                (tampered, CONTRACT_ALIGNMENT_MIGRATION, SCHEMA_VERSION_TEXT_MIGRATION),
                applied_at=UTC_NOW,
                application_version="f5e2b-durable-test",
            )

        connection.execute(
            """
            INSERT INTO schema_migrations (
                migration_id, migration_name, checksum, applied_at,
                application_version, previous_schema_version,
                resulting_schema_version, safe_notes
            ) VALUES ('v999', 'future', 'future-checksum', ?, 'future', 1, 999, 'future')
            """,
            (UTC_TEXT,),
        )
        future_state = inspect_schema_state(
            connection, known_migrations=KNOWN_MIGRATIONS
        )
        assert future_state.incompatible_reason == "unknown newer schema"
        with pytest.raises(SqliteExecutionSchemaError):
            apply_initial_schema(connection)
    finally:
        connection.close()


def test_partial_tampered_and_missing_schema_objects_fail_validation(tmp_path):
    partial = open_database(tmp_path, "partial.sqlite")
    try:
        partial.execute("CREATE TABLE unexpected_existing_table (id TEXT PRIMARY KEY)")
        state = inspect_schema_state(partial, known_migrations=KNOWN_MIGRATIONS)
        assert state.incompatible_reason == "missing migrations table"
        with pytest.raises(SqliteExecutionSchemaError):
            apply_initial_schema(partial)
    finally:
        partial.close()

    tampered = open_database(tmp_path, "tampered.sqlite")
    try:
        apply_initial_schema(tampered)
        tampered.execute("DROP INDEX idx_execution_commands_idempotency_key")
        tampered.execute("DROP TRIGGER trg_execution_commands_no_update")
        validation_one = validate_sqlite_execution_schema(
            tampered,
            expected_busy_timeout_ms=DEFAULT_BUSY_TIMEOUT_MS,
        )
        validation_two = validate_sqlite_execution_schema(
            tampered,
            expected_busy_timeout_ms=DEFAULT_BUSY_TIMEOUT_MS,
        )
        assert validation_one.passed is False
        assert validation_one.failures == validation_two.failures
        assert "missing index: idx_execution_commands_idempotency_key" in (
            validation_one.failures
        )
        assert "missing trigger: trg_execution_commands_no_update" in (
            validation_one.failures
        )
    finally:
        tampered.close()


def test_migration_atomicity_rolls_back_after_controlled_failure(tmp_path):
    connection = open_database(tmp_path)
    try:
        broken = SqliteExecutionMigration.create(
            migration_id="v001",
            name="broken initial execution persistence schema",
            previous_version=0,
            resulting_version=1,
            sql_text=(
                "CREATE TABLE should_roll_back (id TEXT PRIMARY KEY);\n"
                "CREATE TABLE broken SQL;"
            ),
            irreversible=True,
            safe_description="controlled failure",
        )
        with pytest.raises(SqliteExecutionMigrationError):
            apply_pending_migrations(
                connection,
                (broken,),
                applied_at=UTC_NOW,
                application_version="f5e2b-durable-test",
            )
        assert "should_roll_back" not in sqlite_objects(connection, "table")
        assert "schema_migrations" not in sqlite_objects(connection, "table")
    finally:
        connection.close()


def test_lock_busy_timeout_surfaces_without_hidden_retry(tmp_path):
    database_path = tmp_path / "locked.sqlite"
    first = open_sqlite_execution_connection(database_path, busy_timeout_ms=50)
    second = open_sqlite_execution_connection(database_path, busy_timeout_ms=50)
    try:
        apply_initial_schema(first)
        first.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError):
            second.execute("BEGIN IMMEDIATE")
    finally:
        first.rollback()
        first.close()
        second.close()


def test_quick_integrity_foreign_key_and_invariant_checks(tmp_path):
    connection = open_database(tmp_path)
    try:
        apply_initial_schema(connection)
        insert_minimum_aggregate_command_and_idempotency(connection)
        assert run_quick_check(connection).passed is True
        assert run_integrity_check(connection).passed is True
        assert check_foreign_keys(connection).passed is True
        assert check_idempotency_bindings(connection).passed is True
        assert check_broker_reference_ownership(connection).passed is True
        assert check_aggregate_transition_revisions(connection).passed is True

        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            """
            INSERT INTO execution_commands (
                command_id, aggregate_id, correlation_id, idempotency_key, operation,
                expected_execution_revision, canonical_payload_fingerprint,
                canonical_command_json, approval_fingerprint, policy_fingerprint,
                received_at, processing_outcome, mode, schema_version, record_fingerprint
            ) VALUES ('orphan', 'missing-agg', 'corr', 'idem', 'SUBMIT', 0,
                      'payload', '{}', 'approval', 'policy', ?, 'PENDING',
                      'PAPER', 1, 'orphan-fp')
            """,
            (UTC_TEXT,),
        )
        foreign_key_result = check_foreign_keys(connection)
        assert foreign_key_result.passed is False
        assert foreign_key_result.blocks_execution is True
    finally:
        connection.close()


def test_reopen_repeated_startup_and_read_only_compatibility(tmp_path):
    database_path = tmp_path / "reopen.sqlite"
    connection = open_sqlite_execution_connection(database_path)
    try:
        apply_initial_schema(connection)
    finally:
        connection.close()

    writable = open_sqlite_execution_connection(database_path)
    try:
        replay = apply_initial_schema(writable)
        assert replay.changed is False
    finally:
        writable.close()

    read_only = open_sqlite_execution_connection(database_path, read_only=True)
    try:
        result = validate_sqlite_execution_schema(
            read_only,
            expected_busy_timeout_ms=DEFAULT_BUSY_TIMEOUT_MS,
            require_wal=False,
        )
        assert result.passed is True
        with pytest.raises(sqlite3.OperationalError):
            read_only.execute("CREATE TABLE forbidden_write (id TEXT)")
    finally:
        read_only.close()


def test_path_rejection_happens_before_sqlite_connection(monkeypatch, tmp_path):
    state_like_directory = tmp_path / "state"
    state_like_directory.mkdir()

    def fail_if_called(*_args: object, **_kwargs: object) -> sqlite3.Connection:
        raise AssertionError("sqlite3.connect should not be called")

    monkeypatch.setattr(sqlite3, "connect", fail_if_called)

    with pytest.raises(SqliteExecutionPathError):
        open_sqlite_execution_connection(state_like_directory / "execution.sqlite")
    with pytest.raises(SqliteExecutionPathError):
        open_sqlite_execution_connection(tmp_path / "simulated_broker.json")
    with pytest.raises(SqliteExecutionPathError):
        validate_sqlite_execution_path(tmp_path / "not-a-sqlite-file.txt")


def test_pragma_verification_failure_and_stable_error_contracts(tmp_path):
    connection = open_database(tmp_path)
    try:
        apply_initial_schema(connection)
        validation = validate_sqlite_execution_schema(
            connection,
            expected_busy_timeout_ms=DEFAULT_BUSY_TIMEOUT_MS + 1,
        )
        assert validation.passed is False
        assert (
            "busy_timeout pragma does not match expected value" in validation.failures
        )
    finally:
        connection.close()

    assert SqliteExecutionPathError.safe_code == "SQLITE_EXECUTION_PATH_ERROR"
    assert (
        SqliteExecutionConfigurationError.safe_code
        == "SQLITE_EXECUTION_CONFIGURATION_ERROR"
    )
    assert SqliteExecutionMigrationError.safe_code == "SQLITE_EXECUTION_MIGRATION_ERROR"
    assert SqliteExecutionSchemaError.safe_code == "SQLITE_EXECUTION_SCHEMA_ERROR"


def test_sqlite_infrastructure_allows_only_private_phase2_slice1_behavior():
    root = Path("volcanoes/infrastructure/execution_persistence/sqlite")
    prohibited_tokens = (
        "state/simulated_broker.json",
        "TradingClient",
        "submit_order",
        "submit_bracket_order",
        "cancel_order",
        "replace_order",
        "PaperBroker",
        "Alpaca",
        "streamlit",
        "requests",
        "urllib",
        "socket",
        "subprocess",
        "os.environ",
        "getenv",
        "PreviewTradeService",
        "SubmitTradeService",
        "ExecutionSupervisor",
        "PaperExecutionEngine",
        "FastAPI",
        "flask",
    )
    offenders: list[str] = []
    discovered_phase2_classes: set[tuple[str, str]] = set()
    for path in sorted(root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        relative_path = path.relative_to(root).as_posix()
        tree = ast.parse(source)
        source_for_token_scan = source
        if relative_path == "repositories.py":
            broker_reference_imports = {
                (node.module, alias.name, alias.asname)
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module == "volcanoes.application.execution.identities"
                for alias in node.names
                if alias.name == "PaperBrokerOrderReference"
            }
            broker_reference_names = {
                node.id
                for node in ast.walk(tree)
                if isinstance(node, ast.Name) and "PaperBroker" in node.id
            }
            runtime_broker_imports = {
                node.module
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom)
                and node.module is not None
                and "broker" in node.module.lower()
            }
            assert broker_reference_imports == {
                (
                    "volcanoes.application.execution.identities",
                    "PaperBrokerOrderReference",
                    None,
                )
            }
            assert broker_reference_names == {"PaperBrokerOrderReference"}
            assert runtime_broker_imports == set()
            source_for_token_scan = source.replace("PaperBrokerOrderReference", "")
        offenders.extend(
            f"{path} contains {token}"
            for token in prohibited_tokens
            if token in source_for_token_scan
        )
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            class_identity = (relative_path, node.name)
            if relative_path in {"repositories.py", "unit_of_work.py"}:
                discovered_phase2_classes.add(class_identity)
            if (
                any(
                    fragment in node.name
                    for fragment in ("Repository", "UnitOfWork", "Service")
                )
                and class_identity not in AUTHORIZED_PHASE2_SLICE2_CLASSES
            ):
                offenders.append(f"{path} defines {node.name}")

    assert discovered_phase2_classes == AUTHORIZED_PHASE2_SLICE2_CLASSES
    assert ("repositories.py", "_RepositoryBase") in AUTHORIZED_PHASE2_SLICE2_CLASSES
    assert "_RepositoryBase".startswith("_")
    import volcanoes.infrastructure.execution_persistence.sqlite as sqlite_package

    assert all(
        "Repository" not in name and "UnitOfWork" not in name
        for name in sqlite_package.__all__
    )
    assert "PaperBrokerOrderReference" not in sqlite_package.__all__
    assert offenders == []
