from __future__ import annotations

import pytest

from adapters.paper_execution_persistence_runtime import PaperExecutionPersistenceRuntime
from test_f6b_paper_e2e_restart_recovery_acceptance import (
    test_approved_recovery_completes_after_outcome_unknown_restart as run_approved_recovery,
)
from volcanoes.application.platform.configuration import (
    PaperExecutionPersistenceRuntimeConfiguration,
)
from volcanoes.infrastructure.execution_persistence.sqlite import (
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionIntegrityError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.reconcile_integrity import (
    check_reconcile_authority_bindings,
)


_TRANSITION_IMMUTABILITY_TRIGGER = """
CREATE TRIGGER trg_execution_transitions_no_update
BEFORE UPDATE ON execution_transitions
BEGIN
    SELECT RAISE(ABORT, 'execution_transitions is immutable');
END
"""


def test_runtime_startup_blocks_tampered_reconcile_transition_record(tmp_path) -> None:
    run_approved_recovery(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart-recovery.sqlite").resolve()
    connection = open_sqlite_execution_connection(database_path)
    try:
        before = check_reconcile_authority_bindings(connection)
        assert before.passed is True
        assert before.blocks_execution is False
        assert before.violations == ()

        reconcile_command = connection.execute(
            "SELECT command_id FROM execution_commands WHERE operation='RECONCILE'"
        ).fetchone()
        assert reconcile_command is not None
        transition = connection.execute(
            "SELECT transition_record_id FROM execution_transitions WHERE command_id=?",
            (reconcile_command["command_id"],),
        ).fetchone()
        assert transition is not None

        connection.execute("DROP TRIGGER trg_execution_transitions_no_update")
        updated = connection.execute(
            "UPDATE execution_transitions "
            "SET recorded_at='2099-01-01T00:00:00.000000Z' "
            "WHERE transition_record_id=?",
            (transition["transition_record_id"],),
        )
        assert updated.rowcount == 1
        connection.execute(_TRANSITION_IMMUTABILITY_TRIGGER)
        connection.commit()

        after = check_reconcile_authority_bindings(connection)
        assert after.passed is False
        assert after.blocks_execution is True
        assert len(after.violations) == 1
        assert "transition record fingerprint" in after.violations[0]
    finally:
        connection.close()

    configuration = PaperExecutionPersistenceRuntimeConfiguration(
        database_path=database_path,
        application_version="f6b-reconcile-transition-record-integrity-v2",
        busy_timeout_ms=5_000,
    )
    with pytest.raises(SqliteExecutionIntegrityError):
        PaperExecutionPersistenceRuntime(configuration).start()
