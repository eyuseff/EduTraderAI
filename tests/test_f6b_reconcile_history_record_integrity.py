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


_RECONCILIATION_IMMUTABILITY_TRIGGER = """
CREATE TRIGGER trg_execution_reconciliations_no_update
BEFORE UPDATE ON execution_reconciliations
BEGIN
    SELECT RAISE(ABORT, 'execution_reconciliations is immutable');
END
"""


def test_runtime_startup_blocks_tampered_reconcile_history_record(tmp_path) -> None:
    run_prepared_recovery_runtime_restart(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart.sqlite").resolve()
    request = _intake_request()
    connection = open_sqlite_execution_connection(database_path)
    try:
        before = check_reconcile_authority_bindings(connection)
        assert before.passed is True
        assert before.blocks_execution is False
        assert before.violations == ()

        connection.execute("DROP TRIGGER trg_execution_reconciliations_no_update")
        updated = connection.execute(
            "UPDATE execution_reconciliations SET safe_reason_code=? "
            "WHERE aggregate_id=? AND operator_action_required=1 AND unresolved=1",
            (
                "TAMPERED_HISTORY_REASON",
                str(request.aggregate.aggregate_id),
            ),
        )
        assert updated.rowcount == 1
        connection.execute(_RECONCILIATION_IMMUTABILITY_TRIGGER)
        connection.commit()

        after = check_reconcile_authority_bindings(connection)
        assert after.passed is False
        assert after.blocks_execution is True
        assert len(after.violations) == 1
        assert "history record fingerprint" in after.violations[0]
    finally:
        connection.close()

    configuration = PaperExecutionPersistenceRuntimeConfiguration(
        database_path=database_path,
        application_version="f6b-reconcile-history-record-integrity",
        busy_timeout_ms=5_000,
    )
    with pytest.raises(SqliteExecutionIntegrityError):
        PaperExecutionPersistenceRuntime(configuration).start()
