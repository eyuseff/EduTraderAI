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
from volcanoes.infrastructure.execution_persistence.sqlite.reconcile_integrity import (
    check_reconcile_authority_bindings,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionIntegrityError,
)


_APPROVAL_IMMUTABILITY_TRIGGER = """
CREATE TRIGGER trg_execution_approvals_no_update
BEFORE UPDATE ON execution_approvals
BEGIN
    SELECT RAISE(ABORT, 'execution_approvals is immutable');
END
"""


def test_runtime_startup_blocks_tampered_prepared_reconcile_approval_binding(tmp_path) -> None:
    run_prepared_recovery_runtime_restart(tmp_path)

    database_path = (tmp_path / "paper-e2e-restart.sqlite").resolve()
    request = _intake_request()
    connection = open_sqlite_execution_connection(database_path)
    try:
        before = check_reconcile_authority_bindings(connection)
        assert before.passed is True
        assert before.blocks_execution is False
        assert before.violations == ()

        # Simulate offline file tampering in the isolated temporary database only.
        # Restore the canonical immutability trigger before exercising startup so
        # schema validation remains valid and the new authority invariant is the
        # reason startup fails closed.
        connection.execute("DROP TRIGGER trg_execution_approvals_no_update")
        updated = connection.execute(
            "UPDATE execution_approvals SET bound_fingerprint=? "
            "WHERE approval_fingerprint=("
            "SELECT approval_fingerprint FROM execution_commands "
            "WHERE aggregate_id=? AND operation='RECONCILE'"
            ")",
            (
                "tampered-reconcile-approval-binding",
                str(request.aggregate.aggregate_id),
            ),
        )
        assert updated.rowcount == 1
        connection.execute(_APPROVAL_IMMUTABILITY_TRIGGER)
        connection.commit()

        trigger = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name=?",
            ("trg_execution_approvals_no_update",),
        ).fetchone()
        assert trigger is not None

        after = check_reconcile_authority_bindings(connection)
        assert after.passed is False
        assert after.blocks_execution is True
        assert any("authority bindings" in value for value in after.violations)
        assert any(
            "approval record fingerprint" in value for value in after.violations
        )
    finally:
        connection.close()

    configuration = PaperExecutionPersistenceRuntimeConfiguration(
        database_path=database_path,
        application_version="f6b-reconcile-authority-startup-integrity",
        busy_timeout_ms=5_000,
    )
    with pytest.raises(
        SqliteExecutionIntegrityError,
        match="SQLite integrity or persistence invariants blocked startup",
    ):
        PaperExecutionPersistenceRuntime(configuration).start()
