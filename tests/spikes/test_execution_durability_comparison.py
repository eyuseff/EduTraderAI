from __future__ import annotations

from spikes.execution_durability.reports.comparison import (
    ASSESSMENTS,
    FINAL_DECISION,
    NEXT_RECOMMENDED_SLICE,
    POSTGRESQL_MIGRATION_TRIGGERS,
    SQLITE_DEPLOYMENT_CONDITIONS,
    total_scores,
)


def test_comparison_matrix_scores_all_required_criteria() -> None:
    assert len(ASSESSMENTS) == 20
    sqlite_total, postgresql_total = total_scores()
    assert sqlite_total > 0
    assert postgresql_total > 0
    assert postgresql_total > sqlite_total


def test_final_decision_selects_sqlite_with_mandatory_postgresql_triggers() -> None:
    assert FINAL_DECISION == "SELECT_SQLITE_WITH_MANDATORY_POSTGRESQL_MIGRATION_TRIGGER"
    assert "single machine" in SQLITE_DEPLOYMENT_CONDITIONS
    assert "multiple active execution workers" in POSTGRESQL_MIGRATION_TRIGGERS
    assert NEXT_RECOMMENDED_SLICE == "V41-PQ-001F5E2A — SQLITE DURABLE ADAPTER DESIGN"
