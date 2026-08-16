from __future__ import annotations

import pytest

from adapters.paper_execution_persistence_runtime import PaperExecutionPersistenceRuntime
from test_f6b_paper_e2e_acceptance import _intake_request
from test_f6b_paper_e2e_prepared_recovery_runtime_restart import (
    test_prepared_recovery_survives_runtime_restart_without_auto_execution as run_prepared_recovery_runtime_restart,
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


def test_runtime_startup_blocks_tampered_reconcile_idempotency_binding(tmp_path) -> None:
    run_prepared_recovery_runtime_restart(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart.sqlite").resolve()
    request = _intake_request()
    connection = open_sqlite_execution_connection(database_path)
    try:
        before = check_reconcile_authority_bindings(connection)
        assert before.passed is True
        assert before.blocks_execution is False
        assert before.violations == ()

        command = connection.execute(
            "SELECT idempotency_key FROM execution_commands "
            "WHERE aggregate_id=? AND operation='RECONCILE'",
            (str(request.aggregate.aggregate_id),),
        ).fetchone()
        assert command is not None

        # Simulate isolated offline corruption of the logical reservation
        # binding. The dedicated checker must reject a fingerprint that no
        # longer represents the RECONCILE destination/reconciliation tuple.
        updated = connection.execute(
            "UPDATE execution_idempotency SET logical_operation_fingerprint=? "
            "WHERE idempotency_key=?",
            ("plo-" + "0" * 64, command[0]),
        )
        assert updated.rowcount == 1
        connection.commit()

        after = check_reconcile_authority_bindings(connection)
        assert after.passed is False
        assert after.blocks_execution is True
        assert len(after.violations) == 1
        assert "idempotency bindings" in after.violations[0]
    finally:
        connection.close()

    configuration = PaperExecutionPersistenceRuntimeConfiguration(
        database_path=database_path,
        application_version="f6b-reconcile-idempotency-binding-startup-integrity",
        busy_timeout_ms=5_000,
    )
    with pytest.raises(SqliteExecutionIntegrityError):
        PaperExecutionPersistenceRuntime(configuration).start()
