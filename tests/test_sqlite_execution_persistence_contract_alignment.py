"""Focused F5E2C contract-alignment migration specifications.

Every database used here is rooted in pytest's supplied temporary directory.
The production simulator-state path is never named or opened by this module.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from volcanoes.application.execution import (
    ExecutionPersistenceResultStatus,
    ExecutionReplayKind,
    ExecutionTransitionRecord,
    InMemoryExecutionPersistence,
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionLifecycleEvidenceIntentKind,
    PaperExecutionLifecycleInputType,
    PaperExecutionLifecycleSideEffectIntentKind,
    PaperExecutionLifecycleState,
    PaperExecutionRevision,
)
from volcanoes.infrastructure.execution_persistence.sqlite import (
    CONTRACT_ALIGNMENT_MIGRATION,
    INITIAL_MIGRATION,
    KNOWN_MIGRATIONS,
    apply_pending_migrations,
    check_foreign_keys,
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionMigrationError,
)

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
TEXT = "2026-08-13T12:00:00.000000Z"


def _connection(tmp_path, name: str) -> sqlite3.Connection:
    return open_sqlite_execution_connection(tmp_path / name)


def _apply(
    connection: sqlite3.Connection,
    migrations=KNOWN_MIGRATIONS,
) -> None:
    apply_pending_migrations(
        connection,
        migrations,
        applied_at=NOW,
        application_version="f5e2c-contract-alignment-test",
    )


def _insert_aggregate(
    connection: sqlite3.Connection, aggregate_id: str = "agg-1"
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
        ) VALUES (?, 'corr-1', 'CREATED', 0, '0', '1', NULL, 0, 0, 0, 0,
                  'PX-TRN-000', NULL, NULL, NULL, NULL, 'PAPER', ?, ?, 1, ?)
        """,
        (aggregate_id, TEXT, TEXT, f"aggregate-{aggregate_id}"),
    )


def _insert_command(
    connection: sqlite3.Connection,
    *,
    command_id: str = "cmd-1",
    aggregate_id: str = "agg-1",
    outcome: str = "REGISTERED",
    received_at: str = TEXT,
) -> None:
    connection.execute(
        """
        INSERT INTO execution_commands (
            command_id, aggregate_id, correlation_id, idempotency_key, operation,
            expected_execution_revision, canonical_payload_fingerprint,
            canonical_command_json, approval_fingerprint, policy_fingerprint,
            received_at, processing_outcome, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, 'corr-1', ?, 'SUBMIT', 0, ?, '{}', 'approval', 'policy',
                  ?, ?, 'PAPER', 1, ?)
        """,
        (
            command_id,
            aggregate_id,
            f"idem-{command_id}",
            f"payload-{command_id}",
            received_at,
            outcome,
            f"command-{command_id}",
        ),
    )


def _insert_idempotency(
    connection: sqlite3.Connection,
    *,
    command_id: str = "cmd-1",
    aggregate_id: str = "agg-1",
    status: str = "RESERVED",
) -> None:
    connection.execute(
        """
        INSERT INTO execution_idempotency (
            idempotency_key, logical_operation_fingerprint, command_id, aggregate_id,
            reservation_status, original_result_fingerprint, created_at, resolved_at,
            conflict, mode, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, NULL, ?, NULL, 0, 'PAPER', 1, ?)
        """,
        (
            f"idem-{command_id}",
            f"logical-{command_id}",
            command_id,
            aggregate_id,
            status,
            TEXT,
            f"idempotency-{command_id}",
        ),
    )


def _in_memory_transition(
    record_id: str,
    transition_id: str,
    previous_revision: int,
    next_revision: int,
) -> ExecutionTransitionRecord:
    return ExecutionTransitionRecord(
        transition_record_id=record_id,
        aggregate_id=PaperExecutionAggregateId.from_seed("aggregate", "alignment"),
        transition_id=transition_id,
        source_state=PaperExecutionLifecycleState.CREATED,
        destination_state=PaperExecutionLifecycleState.ELIGIBILITY_EVALUATED,
        previous_revision=PaperExecutionRevision(previous_revision),
        next_revision=PaperExecutionRevision(next_revision),
        lifecycle_input_kind=PaperExecutionLifecycleInputType.RECORD_ELIGIBILITY,
        input_identity=f"input-{record_id}",
        command_id=PaperExecutionCommandId.from_seed("command", "alignment"),
        correlation_id=PaperExecutionCorrelationId.from_seed(
            "correlation", "alignment"
        ),
        idempotency_key=PaperExecutionIdempotencyKey.from_seed(
            "idempotency", "alignment"
        ),
        replay_indicator=ExecutionReplayKind.NONE,
        side_effect_intent_kinds=(PaperExecutionLifecycleSideEffectIntentKind.NONE,),
        evidence_intent_kinds=(
            PaperExecutionLifecycleEvidenceIntentKind.LIFECYCLE_TRANSITION_ACCEPTED,
        ),
        safe_reason_code="ELIGIBILITY_RECORDED",
        recorded_at=NOW,
        schema_version=2,
    )


def _schema_shape(connection: sqlite3.Connection) -> tuple[tuple[object, ...], ...]:
    """Capture schema definitions without relying on implementation internals."""

    return tuple(connection.execute("""
            SELECT type, name, tbl_name, sql
            FROM sqlite_master
            WHERE name NOT LIKE 'sqlite_%'
            ORDER BY type, name
            """).fetchall())


def _v002_only_migrations():
    return (INITIAL_MIGRATION, CONTRACT_ALIGNMENT_MIGRATION)


def _insert_v002_transition(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO execution_transitions VALUES (
            'tr-1', 'agg-1', 'PX-TRN-001', 'CREATED', 'ELIGIBILITY_EVALUATED',
            0, 1, 'COMMAND', 'input-1', 'cmd-1', 'corr-1', 'idem-cmd-1',
            NULL, NULL, NULL, 'NONE', '[]', '[]', 'OK', 'PAPER', ?, 2, 'transition-1'
        )
        """,
        (TEXT,),
    )


def _insert_v002_broker_reference(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO execution_broker_references VALUES (
            'broker-1', 'agg-1', 'cmd-1', 'adapter', 'ACTIVE', ?, ?, 1, NULL,
            'PAPER', 2, 'broker-1'
        )
        """,
        (TEXT, TEXT),
    )


def _insert_v002_receipt(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO execution_receipts VALUES (
            'receipt-1', 'agg-1', 'cmd-1', 'corr-1', 'SUBMIT',
            'COMMAND_ACCEPTED_LOCALLY', 'CREATED', 0, ?, 'ACCEPTED', NULL, 1, 0,
            ?, 'PAPER', 2, 'receipt-1'
        )
        """,
        (TEXT, TEXT),
    )


def _insert_v002_failure(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        INSERT INTO execution_failures VALUES (
            'failure-1', 'agg-1', 'cmd-1', 'corr-1', 'CONTRACT_VALIDATION',
            'INFO', 'VALIDATION', 'safe message', 0, 0, 0, 0, 0, ?, 'PAPER', 2,
            'failure-1'
        )
        """,
        (TEXT,),
    )


def _insert_v002_timestamp_fixture(
    connection: sqlite3.Connection,
    table_name: str,
) -> None:
    _insert_aggregate(connection)
    _insert_command(connection, outcome="PENDING")
    if table_name == "execution_commands":
        return
    _insert_idempotency(connection, status="RESERVED")
    if table_name == "execution_idempotency":
        return
    if table_name == "execution_transitions":
        _insert_v002_transition(connection)
    elif table_name == "execution_broker_references":
        _insert_v002_broker_reference(connection)
    elif table_name == "execution_receipts":
        _insert_v002_receipt(connection)
    elif table_name == "execution_failures":
        _insert_v002_failure(connection)


def _insert_v002_immutable_timestamp_row(
    connection: sqlite3.Connection,
    table_name: str,
    column: str,
    timestamp: str,
    suffix: str,
) -> None:
    aggregate_id = f"agg-{suffix}"
    command_id = f"cmd-{suffix}"
    _insert_aggregate(connection, aggregate_id)
    _insert_command(
        connection,
        command_id=command_id,
        aggregate_id=aggregate_id,
        outcome="PENDING",
        received_at=timestamp if table_name == "execution_commands" else TEXT,
    )
    if table_name == "execution_commands":
        return
    _insert_idempotency(
        connection,
        command_id=command_id,
        aggregate_id=aggregate_id,
        status="RESERVED",
    )
    if table_name == "execution_transitions":
        connection.execute(
            """
            INSERT INTO execution_transitions VALUES (?, ?, ?, 'CREATED',
                'ELIGIBILITY_EVALUATED', 0, 1, 'COMMAND', ?, ?, 'corr-1', ?,
                NULL, NULL, NULL, 'NONE', '[]', '[]', 'OK', 'PAPER', ?, 2, ?)
            """,
            (
                f"tr-{suffix}",
                aggregate_id,
                f"PX-TRN-{suffix}",
                f"input-{suffix}",
                command_id,
                f"idem-{command_id}",
                timestamp,
                f"transition-{suffix}",
            ),
        )
    elif table_name == "execution_receipts":
        connection.execute(
            """
            INSERT INTO execution_receipts VALUES (?, ?, ?, 'corr-1', 'SUBMIT',
                'COMMAND_ACCEPTED_LOCALLY', 'CREATED', 0, ?, 'ACCEPTED', NULL, 1,
                0, ?, 'PAPER', 2, ?)
            """,
            (
                f"receipt-{suffix}",
                aggregate_id,
                command_id,
                timestamp if column == "observed_at" else TEXT,
                timestamp if column == "recorded_at" else TEXT,
                f"receipt-{suffix}",
            ),
        )
    elif table_name == "execution_failures":
        connection.execute(
            """
            INSERT INTO execution_failures VALUES (?, ?, ?, 'corr-1',
                'CONTRACT_VALIDATION', 'INFO', 'VALIDATION', 'safe message', 0, 0,
                0, 0, 0, ?, 'PAPER', 2, ?)
            """,
            (
                f"failure-{suffix}",
                aggregate_id,
                command_id,
                timestamp,
                f"failure-{suffix}",
            ),
        )


def _corrupt_v001_command(connection: sqlite3.Connection, statement: str) -> None:
    trigger_rows = connection.execute("""
        SELECT sql FROM sqlite_master
        WHERE type = 'trigger' AND name = 'trg_execution_commands_no_update'
        """).fetchall()
    assert len(trigger_rows) == 1
    trigger_sql = trigger_rows[0][0]
    assert isinstance(trigger_sql, str)
    trigger_dropped = False
    try:
        connection.execute("DROP TRIGGER trg_execution_commands_no_update")
        trigger_dropped = True
        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(statement)
    finally:
        connection.execute("PRAGMA ignore_check_constraints = OFF")
        if trigger_dropped:
            connection.execute(trigger_sql)
    assert connection.execute("""
            SELECT count(*) FROM sqlite_master
            WHERE type = 'trigger' AND name = 'trg_execution_commands_no_update'
            """).fetchone()[0] == 1


@pytest.mark.parametrize(
    (
        "legacy_outcome",
        "expected_outcome",
        "legacy_reservation",
        "expected_reservation",
    ),
    [
        ("REGISTERED", "PENDING", "RESERVED", "RESERVED"),
        ("REPLAY", "REPLAYED", "RESOLVED", "COMPLETED"),
        ("CONFLICT", "CONFLICTED", "CONFLICT", "CONFLICTED"),
        ("REJECTED", "REJECTED", "UNKNOWN", "RECONCILIATION_REQUIRED"),
    ],
)
def test_v002_maps_each_supported_legacy_outcome_losslessly(
    tmp_path,
    legacy_outcome: str,
    expected_outcome: str,
    legacy_reservation: str,
    expected_reservation: str,
) -> None:
    connection = _connection(tmp_path, "legacy-maps.sqlite")
    try:
        _apply(connection, (INITIAL_MIGRATION,))
        _insert_aggregate(connection)
        _insert_command(connection, outcome=legacy_outcome)
        _insert_idempotency(connection, status=legacy_reservation)
        _apply(connection, (INITIAL_MIGRATION, CONTRACT_ALIGNMENT_MIGRATION))
        assert (
            connection.execute(
                "SELECT processing_outcome FROM execution_commands"
            ).fetchone()[0]
            == expected_outcome
        )
        assert (
            connection.execute(
                "SELECT reservation_status FROM execution_idempotency"
            ).fetchone()[0]
            == expected_reservation
        )
        assert check_foreign_keys(connection).passed is True
    finally:
        connection.close()


def test_v002_keeps_v001_checksum_and_is_idempotent(tmp_path) -> None:
    connection = _connection(tmp_path, "idempotent.sqlite")
    try:
        _apply(connection)
        first = connection.execute(
            "SELECT checksum FROM schema_migrations WHERE migration_id = 'v001'"
        ).fetchone()[0]
        assert first == INITIAL_MIGRATION.checksum
        replay = apply_pending_migrations(
            connection,
            KNOWN_MIGRATIONS,
            applied_at=NOW,
            application_version="f5e2c-contract-alignment-test",
        )
        assert replay.changed is False
        assert replay.applied_migration_ids == ()
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_v002_checksum_mismatch_is_rejected_without_schema_mutation(tmp_path) -> None:
    connection = _connection(tmp_path, "checksum.sqlite")
    try:
        _apply(connection, _v002_only_migrations())
        before = _schema_shape(connection)
        tampered = type(CONTRACT_ALIGNMENT_MIGRATION).create(
            migration_id="v002",
            name=CONTRACT_ALIGNMENT_MIGRATION.name,
            previous_version=1,
            resulting_version=2,
            sql_text=CONTRACT_ALIGNMENT_MIGRATION.sql_text + "\n-- changed\n",
            irreversible=True,
            safe_description=CONTRACT_ALIGNMENT_MIGRATION.safe_description,
        )
        with pytest.raises(SqliteExecutionMigrationError):
            _apply(connection, (INITIAL_MIGRATION, tampered))
        assert _schema_shape(connection) == before
    finally:
        connection.close()


def test_migration_rejects_caller_transaction_without_implicit_commit(tmp_path) -> None:
    connection = _connection(tmp_path, "caller-transaction.sqlite")
    try:
        _apply(connection, (INITIAL_MIGRATION,))
        connection.execute("CREATE TABLE canary (value TEXT NOT NULL)")
        connection.execute("BEGIN")
        connection.execute("INSERT INTO canary VALUES ('uncommitted')")
        with pytest.raises(SqliteExecutionMigrationError):
            _apply(connection, _v002_only_migrations())
        assert connection.in_transaction is True
        assert (
            connection.execute("SELECT value FROM canary").fetchone()[0]
            == "uncommitted"
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM schema_migrations WHERE migration_id = 'v002'"
            ).fetchone()[0]
            == 0
        )
        connection.rollback()
        assert connection.execute("SELECT count(*) FROM canary").fetchone()[0] == 0
    finally:
        connection.close()


def test_incomplete_or_failing_v002_script_changes_nothing(tmp_path) -> None:
    connection = _connection(tmp_path, "invalid-script.sqlite")
    try:
        _apply(connection, (INITIAL_MIGRATION,))
        before = _schema_shape(connection)
        incomplete = type(CONTRACT_ALIGNMENT_MIGRATION).create(
            migration_id="v002",
            name="incomplete",
            previous_version=1,
            resulting_version=2,
            sql_text="CREATE TABLE incomplete (id TEXT PRIMARY KEY)",
            irreversible=True,
            safe_description="incomplete",
        )
        with pytest.raises(SqliteExecutionMigrationError):
            _apply(connection, (INITIAL_MIGRATION, incomplete))
        assert _schema_shape(connection) == before

        broken = type(CONTRACT_ALIGNMENT_MIGRATION).create(
            migration_id="v002",
            name="broken",
            previous_version=1,
            resulting_version=2,
            sql_text="CREATE TABLE should_rollback (id TEXT PRIMARY KEY); broken SQL;",
            irreversible=True,
            safe_description="broken",
        )
        with pytest.raises(SqliteExecutionMigrationError):
            _apply(connection, (INITIAL_MIGRATION, broken))
        assert _schema_shape(connection) == before
        assert (
            connection.execute(
                "SELECT count(*) FROM schema_migrations WHERE migration_id = 'v002'"
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()


@pytest.mark.parametrize("legacy_table", ["execution_receipts", "execution_failures"])
def test_v002_rejects_nonlossless_legacy_fact_tables_and_rolls_back(
    tmp_path, legacy_table: str
) -> None:
    connection = _connection(tmp_path, f"{legacy_table}.sqlite")
    try:
        _apply(connection, (INITIAL_MIGRATION,))
        _insert_aggregate(connection)
        _insert_command(connection)
        if legacy_table == "execution_receipts":
            connection.execute(
                """INSERT INTO execution_receipts VALUES
                ('receipt', 'agg-1', 'cmd-1', 'LEGACY', NULL, 'OK', 'OK', ?, 'PAPER', 1, 'r')""",
                (TEXT,),
            )
        else:
            connection.execute(
                """INSERT INTO execution_failures VALUES
                ('failure', 'agg-1', 'cmd-1', 'LEGACY', 'LOW', 0, 0, 0, 'OK', ?, 'PAPER', 1, 'f')""",
                (TEXT,),
            )
        with pytest.raises(SqliteExecutionMigrationError):
            _apply(connection)
        assert (
            connection.execute(
                "SELECT count(*) FROM schema_migrations WHERE migration_id = 'v002'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(f"SELECT count(*) FROM {legacy_table}").fetchone()[0]
            == 1
        )
    finally:
        connection.close()


def test_v002_rejects_replay_suppressed_transition_and_rolls_back(tmp_path) -> None:
    connection = _connection(tmp_path, "replay-suppressed.sqlite")
    try:
        _apply(connection, (INITIAL_MIGRATION,))
        _insert_aggregate(connection)
        _insert_command(connection)
        _insert_idempotency(connection)
        connection.execute(
            """INSERT INTO execution_transitions VALUES
            ('tr-1', 'agg-1', 'PX-TRN-001', 'CREATED', 'ELIGIBILITY_EVALUATED', 0, 1,
             'COMMAND', 'input-1', 'cmd-1', 'corr-1', 'idem-cmd-1', NULL, NULL, NULL,
             'REPLAY_SUPPRESSED', '[]', '[]', 'OK', 'PAPER', ?, 1, 'transition')""",
            (TEXT,),
        )
        with pytest.raises(SqliteExecutionMigrationError):
            _apply(connection)
        assert (
            connection.execute(
                "SELECT replay_indicator FROM execution_transitions"
            ).fetchone()[0]
            == "REPLAY_SUPPRESSED"
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM schema_migrations WHERE migration_id = 'v002'"
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("table_name", "statement"),
    [
        (
            "execution_commands",
            "UPDATE execution_commands SET processing_outcome = 'UNSUPPORTED'",
        ),
        (
            "execution_idempotency",
            "UPDATE execution_idempotency SET reservation_status = 'UNSUPPORTED'",
        ),
        (
            "execution_commands",
            "UPDATE execution_commands SET operation = 'RECONCILE'",
        ),
        (
            "execution_commands",
            "UPDATE execution_commands SET received_at = 'malformed'",
        ),
    ],
)
def test_v002_rejects_unsupported_or_malformed_legacy_rows_without_partial_rebuild(
    tmp_path, table_name: str, statement: str
) -> None:
    connection = _connection(tmp_path, f"{table_name}.sqlite")
    try:
        _apply(connection, (INITIAL_MIGRATION,))
        _insert_aggregate(connection)
        _insert_command(connection)
        _insert_idempotency(connection)
        if table_name == "execution_commands":
            _corrupt_v001_command(connection, statement)
        else:
            connection.execute("PRAGMA ignore_check_constraints = ON")
            try:
                connection.execute(statement)
            finally:
                connection.execute("PRAGMA ignore_check_constraints = OFF")
        before = _schema_shape(connection)
        with pytest.raises(SqliteExecutionMigrationError):
            _apply(connection, _v002_only_migrations())
        assert _schema_shape(connection) == before
        assert (
            connection.execute(
                "SELECT count(*) FROM schema_migrations WHERE migration_id = 'v002'"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(f"SELECT count(*) FROM {table_name}").fetchone()[0] == 1
        )
    finally:
        connection.close()


def test_v002_foreign_key_check_failure_restores_the_complete_legacy_shape(
    tmp_path,
) -> None:
    connection = _connection(tmp_path, "foreign-key-check.sqlite")
    try:
        _apply(connection, (INITIAL_MIGRATION,))
        _insert_aggregate(connection)
        _insert_command(connection)
        connection.execute("PRAGMA foreign_keys = OFF")
        connection.execute(
            "DELETE FROM execution_aggregates WHERE aggregate_id = 'agg-1'"
        )
        connection.execute("PRAGMA foreign_keys = ON")
        before = _schema_shape(connection)
        with pytest.raises(SqliteExecutionMigrationError):
            _apply(connection, _v002_only_migrations())
        assert _schema_shape(connection) == before
        assert (
            connection.execute(
                "SELECT aggregate_id FROM execution_commands"
            ).fetchone()[0]
            == "agg-1"
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM schema_migrations WHERE migration_id = 'v002'"
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()


def test_v002_duplicate_legacy_transition_identity_rolls_back_complete_shape(
    tmp_path,
) -> None:
    unique_clause = ",\n    UNIQUE (aggregate_id, transition_id)\n"
    assert unique_clause in INITIAL_MIGRATION.sql_text
    legacy_sql = INITIAL_MIGRATION.sql_text.replace(unique_clause, "")
    assert unique_clause not in legacy_sql
    legacy = type(INITIAL_MIGRATION).create(
        migration_id="v001",
        name=INITIAL_MIGRATION.name,
        previous_version=0,
        resulting_version=1,
        sql_text=legacy_sql,
        irreversible=True,
        safe_description=INITIAL_MIGRATION.safe_description,
    )
    connection = _connection(tmp_path, "duplicate-transition.sqlite")
    try:
        _apply(connection, (legacy,))
        _insert_aggregate(connection)
        _insert_command(connection)
        _insert_idempotency(connection)
        transition = (
            "tr-1",
            "agg-1",
            "PX-TRN-001",
            "CREATED",
            "ELIGIBILITY_EVALUATED",
            0,
            1,
            "COMMAND",
            "input-1",
            "cmd-1",
            "corr-1",
            "idem-cmd-1",
            None,
            None,
            None,
            "NOT_REPLAY",
            "[]",
            "[]",
            "OK",
            "PAPER",
            TEXT,
            1,
            "transition-1",
        )
        connection.execute(
            "INSERT INTO execution_transitions VALUES ("
            + ",".join("?" for _ in transition)
            + ")",
            transition,
        )
        duplicate = list(transition)
        duplicate[0] = "tr-2"
        duplicate[6] = 2
        duplicate[5] = 1
        duplicate[8] = "input-2"
        duplicate[22] = "transition-2"
        connection.execute(
            "INSERT INTO execution_transitions VALUES ("
            + ",".join("?" for _ in duplicate)
            + ")",
            duplicate,
        )
        before = _schema_shape(connection)
        with pytest.raises(SqliteExecutionMigrationError):
            _apply(connection, (legacy, CONTRACT_ALIGNMENT_MIGRATION))
        assert _schema_shape(connection) == before
        assert (
            connection.execute("SELECT count(*) FROM execution_transitions").fetchone()[
                0
            ]
            == 2
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM schema_migrations WHERE migration_id = 'v002'"
            ).fetchone()[0]
            == 0
        )
    finally:
        connection.close()


def test_v002_exposes_required_current_fact_columns_and_enum_constraints(
    tmp_path,
) -> None:
    connection = _connection(tmp_path, "contract.sqlite")
    try:
        _apply(connection)
        _insert_aggregate(connection)
        _insert_command(connection, outcome="PENDING")
        _insert_idempotency(connection, status="RESERVED")
        _insert_v002_receipt(connection)
        _insert_v002_failure(connection)
        receipt_columns = {
            row[1]: row
            for row in connection.execute("PRAGMA table_info(execution_receipts)")
        }
        failure_columns = {
            row[1]: row
            for row in connection.execute("PRAGMA table_info(execution_failures)")
        }
        for name in (
            "correlation_id",
            "operation",
            "status",
            "observed_execution_revision",
            "observed_at",
            "message_code",
            "outcome_known",
            "reconciliation_required",
        ):
            assert receipt_columns[name][3] == 1
        for name in (
            "code",
            "safe_message",
            "operator_action_required",
            "authority_impacting",
        ):
            assert failure_columns[name][3] == 1
        assert (
            tuple(
                connection.execute(
                    """SELECT aggregate_id, command_id, correlation_id, operation, receipt_kind,
                      status, observed_execution_revision, observed_at, message_code,
                      broker_reference, outcome_known, reconciliation_required
               FROM execution_receipts"""
                ).fetchone()
            )
            == (
                "agg-1",
                "cmd-1",
                "corr-1",
                "SUBMIT",
                "COMMAND_ACCEPTED_LOCALLY",
                "CREATED",
                0,
                TEXT,
                "ACCEPTED",
                None,
                1,
                0,
            )
        )
        assert (
            tuple(
                connection.execute(
                    """SELECT aggregate_id, command_id, correlation_id, failure_kind, severity,
                      code, safe_message, retryable, reconciliation_required,
                      operator_action_required, terminal, authority_impacting
               FROM execution_failures"""
                ).fetchone()
            )
            == (
                "agg-1",
                "cmd-1",
                "corr-1",
                "CONTRACT_VALIDATION",
                "INFO",
                "VALIDATION",
                "safe message",
                0,
                0,
                0,
                0,
                0,
            )
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE execution_receipts SET outcome_known = 2")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE execution_failures SET severity = 'INVALID'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE execution_receipts SET message_code = NULL")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """INSERT INTO execution_commands VALUES
                ('bad', 'missing', 'corr', 'key', 'SUBMIT', 0, 'payload', '{}', 'a', 'p',
                 ?, 'REGISTERED', 'PAPER', 2, 'bad')""",
                (TEXT,),
            )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("table_name", "column"),
    [
        ("execution_commands", "received_at"),
        ("execution_idempotency", "created_at"),
        ("execution_idempotency", "resolved_at"),
        ("execution_transitions", "recorded_at"),
        ("execution_broker_references", "first_seen_at"),
        ("execution_broker_references", "last_seen_at"),
        ("execution_receipts", "observed_at"),
        ("execution_receipts", "recorded_at"),
        ("execution_failures", "recorded_at"),
    ],
)
@pytest.mark.parametrize(
    "invalid", ["2026-08-13T12:00:00Z", "2026-08-13T12:00:00.000000+00:00", "malformed"]
)
def test_v002_timestamp_constraints_preserve_v001_canonical_utc_semantics(
    tmp_path, table_name: str, column: str, invalid: str
) -> None:
    connection = _connection(tmp_path, f"{table_name}-{column}.sqlite")
    try:
        _apply(connection)
        immutable_timestamp_tables = {
            "execution_commands",
            "execution_transitions",
            "execution_receipts",
            "execution_failures",
        }
        if table_name in immutable_timestamp_tables:
            _insert_v002_immutable_timestamp_row(
                connection, table_name, column, TEXT, "valid"
            )
            with pytest.raises(sqlite3.IntegrityError):
                _insert_v002_immutable_timestamp_row(
                    connection, table_name, column, invalid, "invalid"
                )
            assert (
                connection.execute(
                    f"SELECT count(*) FROM {table_name} WHERE record_fingerprint = ?",
                    (f"{table_name.split('_', 1)[1].rstrip('s')}-invalid",),
                ).fetchone()[0]
                == 0
            )
        else:
            _insert_v002_timestamp_fixture(connection, table_name)
            connection.execute(f"UPDATE {table_name} SET {column} = ?", (TEXT,))
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(f"UPDATE {table_name} SET {column} = ?", (invalid,))
    finally:
        connection.close()


def test_v002_defers_only_aggregate_foreign_key_for_documented_write_order(
    tmp_path,
) -> None:
    connection = _connection(tmp_path, "deferred.sqlite")
    try:
        _apply(connection)
        connection.execute("BEGIN")
        _insert_command(connection, outcome="PENDING")
        _insert_aggregate(connection)
        connection.commit()
        connection.execute("BEGIN")
        _insert_command(
            connection,
            command_id="cmd-missing",
            aggregate_id="missing",
            outcome="PENDING",
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.commit()
        connection.rollback()
    finally:
        connection.close()


def test_v002_enforces_all_three_transition_uniqueness_constraints(tmp_path) -> None:
    connection = _connection(tmp_path, "transitions.sqlite")
    try:
        _apply(connection)
        _insert_aggregate(connection)
        _insert_command(connection, outcome="PENDING")
        _insert_idempotency(connection, status="RESERVED")
        row = (
            "tr-1",
            "agg-1",
            "PX-TRN-001",
            "CREATED",
            "ELIGIBILITY_EVALUATED",
            0,
            1,
            "COMMAND",
            "input-1",
            "cmd-1",
            "corr-1",
            "idem-cmd-1",
            None,
            None,
            None,
            "NONE",
            "[]",
            "[]",
            "OK",
            "PAPER",
            TEXT,
            2,
            "transition-1",
        )
        connection.execute(
            "INSERT INTO execution_transitions VALUES ("
            + ",".join("?" for _ in row)
            + ")",
            row,
        )
        for replacement in (
            ("tr-1", 0, 1, "PX-TRN-002"),
            ("tr-2", 0, 1, "PX-TRN-002"),
            ("tr-2", 1, 2, "PX-TRN-001"),
        ):
            changed = list(row)
            changed[0], changed[5], changed[6], changed[2] = replacement
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO execution_transitions VALUES ("
                    + ",".join("?" for _ in changed)
                    + ")",
                    changed,
                )
    finally:
        connection.close()


def test_in_memory_reference_matches_sqlite_transition_identity_rules() -> None:
    store = InMemoryExecutionPersistence()
    unit_of_work = store.unit_of_work()
    first = _in_memory_transition("record-1", "PX-TRN-001", 0, 1)

    assert (
        unit_of_work.transitions.append(first).status
        is ExecutionPersistenceResultStatus.APPENDED
    )
    assert (
        unit_of_work.transitions.append(first).status
        is ExecutionPersistenceResultStatus.EXACT_REPLAY
    )
    assert (
        unit_of_work.transitions.append(
            _in_memory_transition("record-2", "PX-TRN-002", 0, 1)
        ).status
        is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    )
    assert (
        unit_of_work.transitions.append(
            _in_memory_transition("record-3", "PX-TRN-001", 1, 2)
        ).status
        is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    )


def test_in_memory_transition_indexes_are_transactional_and_rollback_safe() -> None:
    store = InMemoryExecutionPersistence()
    first = _in_memory_transition("record-1", "PX-TRN-001", 0, 1)
    first_unit_of_work = store.unit_of_work()
    assert (
        first_unit_of_work.transitions.append(first).status
        is ExecutionPersistenceResultStatus.APPENDED
    )
    assert first_unit_of_work.commit().committed is True

    conflicting = store.unit_of_work()
    assert (
        conflicting.transitions.append(
            _in_memory_transition("record-2", "PX-TRN-002", 0, 1)
        ).status
        is ExecutionPersistenceResultStatus.COMMAND_CONFLICT
    )
    conflicting.rollback()
    snapshot = store.snapshot()
    assert tuple(snapshot._transitions_by_id) == ("record-1",)
    assert len(snapshot._transitions_by_aggregate_revision) == 1
    assert len(snapshot._transitions_by_aggregate_transition_id) == 1

    valid = store.unit_of_work()
    second = _in_memory_transition("record-2", "PX-TRN-002", 1, 2)
    assert (
        valid.transitions.append(second).status
        is ExecutionPersistenceResultStatus.APPENDED
    )
    assert valid.commit().committed is True
    final = store.snapshot()
    assert len(final._transitions_by_id) == 2
    assert len(final._transitions_by_aggregate_revision) == 2
    assert len(final._transitions_by_aggregate_transition_id) == 2
