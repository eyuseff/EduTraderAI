from __future__ import annotations

import pytest

from test_f6b_paper_e2e_acceptance import _intake_request
from test_f6b_paper_e2e_restart_recovery_acceptance import (
    test_approved_recovery_completes_after_outcome_unknown_restart as run_restart_recovery,
)
from volcanoes.application.execution.identities import (
    PaperExecutionCommandId,
    PaperExecutionIdempotencyKey,
    PaperExecutionRevision,
)
from volcanoes.application.execution.lifecycle import PaperExecutionLifecycleState
from volcanoes.infrastructure.execution_persistence.sqlite import (
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.repositories import (
    SqliteExecutionAggregateRepository,
)


def test_late_recovery_failure_rolls_back_entire_bundle_after_restart(
    tmp_path, monkeypatch
) -> None:
    original_save = SqliteExecutionAggregateRepository.save

    def injected_save(self, record, *, expected_revision):
        if (
            record.execution_revision == PaperExecutionRevision(9)
            and record.lifecycle_state is PaperExecutionLifecycleState.FILLED
        ):
            raise RuntimeError("injected late recovery aggregate failure")
        return original_save(self, record, expected_revision=expected_revision)

    monkeypatch.setattr(SqliteExecutionAggregateRepository, "save", injected_save)

    with pytest.raises(RuntimeError, match="injected late recovery aggregate failure"):
        run_restart_recovery(tmp_path)

    database_path = tmp_path / "paper-e2e-restart-recovery.sqlite"
    reopened = open_sqlite_execution_connection(database_path)
    try:
        request = _intake_request()
        recovery_command_id = PaperExecutionCommandId.from_seed(
            "f6b-e2e", "restart-recovery"
        )
        recovery_idempotency_key = PaperExecutionIdempotencyKey.from_seed(
            "f6b-e2e", "restart-recovery"
        )

        aggregate = reopened.execute(
            "SELECT lifecycle_state, execution_revision, reconciliation_required "
            "FROM execution_aggregates WHERE aggregate_id=?",
            (str(request.aggregate.aggregate_id),),
        ).fetchone()
        assert aggregate is not None
        assert tuple(aggregate) == ("RECONCILIATION_REQUIRED", 8, 1)

        assert reopened.execute(
            "SELECT count(*) FROM execution_commands WHERE command_id=?",
            (str(recovery_command_id),),
        ).fetchone()[0] == 0
        assert reopened.execute(
            "SELECT count(*) FROM execution_idempotency WHERE idempotency_key=?",
            (str(recovery_idempotency_key),),
        ).fetchone()[0] == 0
        assert reopened.execute("SELECT count(*) FROM execution_commands").fetchone()[0] == 1
        assert reopened.execute("SELECT count(*) FROM execution_idempotency").fetchone()[0] == 1
        assert reopened.execute("SELECT count(*) FROM execution_approvals").fetchone()[0] == 1
        assert reopened.execute("SELECT count(*) FROM execution_transitions").fetchone()[0] == 8
        assert reopened.execute(
            "SELECT count(*) FROM execution_reconciliations"
        ).fetchone()[0] == 1
        assert reopened.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        reopened.close()
