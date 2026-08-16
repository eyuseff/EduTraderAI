from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from volcanoes.application.execution.fingerprints import fingerprint_payload
from volcanoes.application.execution.identities import (
    PaperExecutionAggregateId,
    PaperExecutionCommandId,
    PaperExecutionCorrelationId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle.enums import (
    PaperExecutionLifecycleState as State,
    PaperExecutionReconciliationOutcome as Outcome,
)
from volcanoes.application.execution.persistence.contracts import ExecutionAggregateRecord
from volcanoes.application.execution.persistence.enums import (
    ExecutionPersistenceResultStatus,
)
from volcanoes.application.execution.reconciliation import (
    ReconciliationDecision,
    ReconciliationFacts,
    build_operator_recovery_command_record,
    build_reconciliation_history_record,
)
from volcanoes.infrastructure.execution_persistence.sqlite import (
    CURRENT_SCHEMA_VERSION,
    KNOWN_MIGRATIONS,
    SqliteExecutionPersistence,
    apply_pending_migrations,
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionMigrationError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.migration import (
    RECONCILE_COMMAND_MIGRATION,
    SqliteExecutionMigration,
)

NOW = datetime(2026, 8, 15, 22, 30, tzinfo=UTC)


def _v004_connection(tmp_path):
    connection = open_sqlite_execution_connection(tmp_path / "v005.sqlite")
    apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS[:-1],
        applied_at=NOW,
        application_version="f6b-v005-precondition",
    )
    return connection


def _insert_parent_and_child(connection) -> None:
    connection.execute(
        "INSERT INTO execution_aggregates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "aggregate-v005",
            "correlation-v005",
            "DISPATCH_PENDING",
            5,
            "0",
            "1",
            None,
            0,
            0,
            0,
            0,
            "PX-TRN-008",
            "command-v005",
            "idempotency-v005",
            None,
            None,
            "PAPER",
            "2026-08-15T22:30:00.000000Z",
            "2026-08-15T22:30:00.000000Z",
            "4",
            "par-" + "1" * 64,
        ),
    )
    connection.execute(
        "INSERT INTO execution_commands VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "command-v005",
            "aggregate-v005",
            "correlation-v005",
            "idempotency-v005",
            "SUBMIT",
            0,
            "pcf-" + "2" * 64,
            "{}",
            "pap-" + "3" * 64,
            "pps-" + "4" * 64,
            "2026-08-15T22:30:00.000000Z",
            "ACCEPTED",
            "PAPER",
            "4",
            "pcm-" + "5" * 64,
        ),
    )
    connection.execute(
        "INSERT INTO execution_idempotency VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "idempotency-v005",
            "plo-" + "6" * 64,
            "command-v005",
            "aggregate-v005",
            "RESERVED",
            None,
            "2026-08-15T22:30:00.000000Z",
            None,
            0,
            "PAPER",
            "4",
            "pir-" + "7" * 64,
        ),
    )
    connection.commit()


def test_v005_is_current_database_migration_and_broadens_only_command_operation_vocabulary(
    tmp_path,
) -> None:
    assert CURRENT_SCHEMA_VERSION == 4
    assert RECONCILE_COMMAND_MIGRATION.previous_version == 4
    assert RECONCILE_COMMAND_MIGRATION.resulting_version == 5
    assert RECONCILE_COMMAND_MIGRATION.requires_foreign_keys_off is True

    connection = _v004_connection(tmp_path)
    try:
        _insert_parent_and_child(connection)
        result = apply_pending_migrations(
            connection,
            KNOWN_MIGRATIONS,
            applied_at=NOW,
            application_version="f6b-v005",
        )

        assert result.applied_migration_ids == ("v005",)
        assert result.schema_state.current_version == 5
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT operation FROM execution_commands WHERE command_id='command-v005'"
        ).fetchone()[0] == "SUBMIT"
        assert connection.execute(
            "SELECT command_id FROM execution_idempotency WHERE idempotency_key='idempotency-v005'"
        ).fetchone()[0] == "command-v005"
        table_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='execution_commands'"
        ).fetchone()[0]
        assert "'RECONCILE'" in table_sql
        assert connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='trigger' AND name IN "
            "('trg_execution_commands_no_update','trg_execution_commands_no_delete')"
        ).fetchone()[0] == 2
    finally:
        connection.close()


def test_v005_runner_restores_foreign_keys_and_rolls_back_broken_rebuild(tmp_path) -> None:
    connection = _v004_connection(tmp_path)
    try:
        _insert_parent_and_child(connection)
        broken = SqliteExecutionMigration.create(
            migration_id="v005-broken",
            name="broken controlled parent rebuild",
            previous_version=4,
            resulting_version=5,
            sql_text=(
                "DROP TRIGGER trg_execution_commands_no_update;\n"
                "DROP TRIGGER trg_execution_commands_no_delete;\n"
                "DROP TABLE execution_commands;\n"
                "CREATE TABLE execution_commands (command_id TEXT PRIMARY KEY);\n"
            ),
            irreversible=True,
            safe_description="Test-only broken rebuild.",
            requires_foreign_keys_off=True,
        )

        with pytest.raises(
            SqliteExecutionMigrationError,
            match="foreign-key violation",
        ):
            apply_pending_migrations(
                connection,
                KNOWN_MIGRATIONS[:-1] + (broken,),
                applied_at=NOW,
                application_version="f6b-v005-broken",
            )

        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert connection.execute(
            "SELECT operation FROM execution_commands WHERE command_id='command-v005'"
        ).fetchone()[0] == "SUBMIT"
        assert connection.execute(
            "SELECT command_id FROM execution_idempotency WHERE idempotency_key='idempotency-v005'"
        ).fetchone()[0] == "command-v005"
    finally:
        connection.close()


def test_operator_recovery_command_persists_through_authoritative_sqlite_repository(
    tmp_path,
) -> None:
    connection = open_sqlite_execution_connection(tmp_path / "recovery.sqlite")
    apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS,
        applied_at=NOW,
        application_version="f6b-v005-recovery",
    )
    persistence = SqliteExecutionPersistence(connection)
    aggregate_id = PaperExecutionAggregateId.from_seed("f6b", "v005-recovery")
    correlation_id = PaperExecutionCorrelationId.from_seed("f6b", "v005-recovery")
    command_id = PaperExecutionCommandId.from_seed("f6b", "v005-recovery")
    idempotency_key = PaperExecutionIdempotencyKey.from_seed("f6b", "v005-recovery")
    revision = PaperExecutionRevision(0)
    aggregate = ExecutionAggregateRecord(
        aggregate_id=aggregate_id,
        correlation_id=correlation_id,
        lifecycle_state=State.RECONCILIATION_REQUIRED,
        execution_revision=revision,
        cumulative_filled_quantity=Decimal("0"),
        outcome_unknown=False,
        reconciliation_required=True,
        command_terminal=False,
        aggregate_terminal=False,
        last_transition_id="PX-TRN-025",
        created_at=NOW,
        updated_at=NOW,
        schema_version=4,
    )
    history = build_reconciliation_history_record(
        aggregate_id=aggregate_id,
        starting_revision=revision,
        starting_state=State.RECONCILIATION_REQUIRED,
        facts=ReconciliationFacts(
            local_present=True,
            broker_present=True,
            local_state=State.RECONCILIATION_REQUIRED,
            broker_state=State.FILLED,
            observation_conflict=True,
        ),
        decision=ReconciliationDecision(
            outcome=Outcome.OPERATOR_ACTION_REQUIRED,
            reason="CONFLICTING_EVIDENCE",
            proposed_state=State.RECONCILIATION_REQUIRED,
            operator_action_required=True,
        ),
        recorded_at=NOW,
        schema_version=4,
    )
    recovery = build_operator_recovery_command_record(
        reconciliation=history,
        destination=State.FILLED,
        command_id=command_id,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        approval_fingerprint=fingerprint_payload("pap", {"operator": "approved"}),
        policy_fingerprint=fingerprint_payload("pps", {"policy": "f6b-v005"}),
        received_at=NOW,
        schema_version=4,
    )

    try:
        with persistence.unit_of_work() as unit:
            assert unit.aggregates.save(
                aggregate,
                expected_revision=revision,
            ).status is ExecutionPersistenceResultStatus.CREATED
            assert unit.reconciliations.record(
                history
            ).status is ExecutionPersistenceResultStatus.CREATED
            assert unit.commands.register(
                recovery
            ).status is ExecutionPersistenceResultStatus.CREATED
            assert unit.commit().committed is True

        row = connection.execute(
            "SELECT operation, canonical_command_json FROM execution_commands WHERE command_id=?",
            (str(command_id),),
        ).fetchone()
        assert row["operation"] == "RECONCILE"
        assert history.reconciliation_id in row["canonical_command_json"]
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()
