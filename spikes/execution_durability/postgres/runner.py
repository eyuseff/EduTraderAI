"""PostgreSQL static assessment runner for the isolated durability spike."""

from __future__ import annotations

import shutil
from importlib.util import find_spec
from pathlib import Path

from spikes.execution_durability.common.models import EnvironmentStatus, SpikeResult
from spikes.execution_durability.common.scenarios import SCENARIOS

BACKEND = "postgresql"


def postgres_runtime_available() -> bool:
    """Return whether safe local PostgreSQL runtime execution is available."""

    has_driver = any(find_spec(name) is not None for name in ("psycopg", "psycopg2"))
    has_client = shutil.which("psql") is not None
    has_server = (
        shutil.which("postgres") is not None or shutil.which("pg_ctl") is not None
    )
    return has_driver and has_client and has_server


def schema_text() -> str:
    return (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")


def run_postgres_scenarios() -> tuple[SpikeResult, ...]:
    """Return explicit runtime skip results unless local PostgreSQL is safe."""

    if not postgres_runtime_available():
        return tuple(
            SpikeResult(
                backend=BACKEND,
                scenario_id=scenario.scenario_id,
                environment_status=EnvironmentStatus.NOT_EXECUTED_ENVIRONMENT_UNAVAILABLE,
                executed=False,
                passed=None,
                expected_outcome=scenario.expected_outcome,
                observed_normalized_outcome="not_executed",
                restart_relevance=scenario.restart_relevance,
                evidence_limitation=(
                    "No safe local PostgreSQL server/client and Python driver were "
                    "available without dependency installation or service changes."
                ),
                safe_notes="Static schema and transaction semantics assessed only.",
            )
            for scenario in SCENARIOS
        )
    return tuple(
        SpikeResult(
            backend=BACKEND,
            scenario_id=scenario.scenario_id,
            environment_status=EnvironmentStatus.STATIC_ASSESSMENT,
            executed=False,
            passed=None,
            expected_outcome=scenario.expected_outcome,
            observed_normalized_outcome="runtime_execution_not_implemented_in_spike",
            restart_relevance=scenario.restart_relevance,
            evidence_limitation="Runtime adapter intentionally not implemented without explicit disposable database configuration.",
            safe_notes="PostgreSQL runtime available but spike remains static until a disposable database is explicitly configured.",
        )
        for scenario in SCENARIOS
    )


def static_assessment_notes() -> dict[str, str]:
    """Return PostgreSQL semantic assessment notes without connecting anywhere."""

    sql = schema_text().lower()
    return {
        "unique_constraints": "Primary keys and unique fingerprints express command, idempotency, journal, and broker-reference uniqueness.",
        "row_level_locking": "PostgreSQL supports SELECT ... FOR UPDATE for aggregate command intake when runtime design reaches durable adapter work.",
        "cas": "Compare-and-swap can use UPDATE ... WHERE aggregate_id=$1 AND execution_revision=$2 and require rowcount=1.",
        "transactions": "Transactional DDL and DML support atomic aggregate plus journal updates and failed migration rollback.",
        "migration": "Schema migrations can be tracked in schema_migrations with checksum and transaction-wrapped additive changes.",
        "backup_restore": "pg_dump/restore and managed PITR are operationally stronger than SQLite but require service ownership.",
        "schema_contains_required_tables": str(
            all(
                name in sql
                for name in (
                    "execution_aggregates",
                    "execution_commands",
                    "execution_idempotency",
                    "execution_transitions",
                    "execution_broker_references",
                    "schema_migrations",
                )
            )
        ),
    }


__all__ = [
    "postgres_runtime_available",
    "run_postgres_scenarios",
    "schema_text",
    "static_assessment_notes",
]
