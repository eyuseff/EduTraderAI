"""Integrity and invariant helpers for SQLite execution persistence foundation."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class IntegrityCheckResult:
    """Normalized SQLite integrity check result."""

    check_name: str
    passed: bool
    findings: tuple[str, ...]
    blocks_execution: bool


@dataclass(frozen=True, slots=True)
class InvariantCheckResult:
    """Normalized execution invariant check result."""

    invariant_name: str
    passed: bool
    violations: tuple[str, ...]
    blocks_execution: bool


def run_quick_check(connection: sqlite3.Connection) -> IntegrityCheckResult:
    """Run PRAGMA quick_check without attempting repair."""

    rows = tuple(str(row[0]) for row in connection.execute("PRAGMA quick_check"))
    passed = rows == ("ok",)
    return IntegrityCheckResult(
        check_name="quick_check",
        passed=passed,
        findings=() if passed else rows,
        blocks_execution=not passed,
    )


def run_integrity_check(connection: sqlite3.Connection) -> IntegrityCheckResult:
    """Run PRAGMA integrity_check without attempting repair."""

    rows = tuple(str(row[0]) for row in connection.execute("PRAGMA integrity_check"))
    passed = rows == ("ok",)
    return IntegrityCheckResult(
        check_name="integrity_check",
        passed=passed,
        findings=() if passed else rows,
        blocks_execution=not passed,
    )


def check_foreign_keys(connection: sqlite3.Connection) -> IntegrityCheckResult:
    """Run PRAGMA foreign_key_check without attempting repair."""

    rows = tuple(
        ".".join(str(part) for part in row)
        for row in connection.execute("PRAGMA foreign_key_check")
    )
    return IntegrityCheckResult(
        check_name="foreign_key_check",
        passed=not rows,
        findings=rows,
        blocks_execution=bool(rows),
    )


def check_aggregate_transition_revisions(
    connection: sqlite3.Connection,
) -> InvariantCheckResult:
    """Validate aggregate revision does not trail transition history."""

    rows = connection.execute("""
        SELECT a.aggregate_id, a.execution_revision, max(t.next_revision)
        FROM execution_aggregates AS a
        LEFT JOIN execution_transitions AS t
          ON t.aggregate_id = a.aggregate_id
        GROUP BY a.aggregate_id, a.execution_revision
        HAVING max(t.next_revision) IS NOT NULL
           AND a.execution_revision < max(t.next_revision)
        """).fetchall()
    violations = tuple(
        f"{row[0]} revision {row[1]} trails journal {row[2]}" for row in rows
    )
    return InvariantCheckResult(
        invariant_name="aggregate_transition_revisions",
        passed=not violations,
        violations=violations,
        blocks_execution=bool(violations),
    )


def check_idempotency_bindings(connection: sqlite3.Connection) -> InvariantCheckResult:
    """Validate one idempotency key has one logical fingerprint."""

    rows = connection.execute("""
        SELECT idempotency_key, count(DISTINCT logical_operation_fingerprint)
        FROM execution_idempotency
        GROUP BY idempotency_key
        HAVING count(DISTINCT logical_operation_fingerprint) > 1
        """).fetchall()
    violations = tuple(f"{row[0]} has {row[1]} fingerprints" for row in rows)
    return InvariantCheckResult(
        invariant_name="idempotency_bindings",
        passed=not violations,
        violations=violations,
        blocks_execution=bool(violations),
    )


def check_broker_reference_ownership(
    connection: sqlite3.Connection,
) -> InvariantCheckResult:
    """Validate one broker reference cannot map to multiple aggregates."""

    rows = connection.execute("""
        SELECT broker_reference, count(DISTINCT aggregate_id)
        FROM execution_broker_references
        GROUP BY broker_reference
        HAVING count(DISTINCT aggregate_id) > 1
        """).fetchall()
    violations = tuple(f"{row[0]} has {row[1]} aggregate owners" for row in rows)
    return InvariantCheckResult(
        invariant_name="broker_reference_ownership",
        passed=not violations,
        violations=violations,
        blocks_execution=bool(violations),
    )


__all__ = [
    "IntegrityCheckResult",
    "InvariantCheckResult",
    "check_aggregate_transition_revisions",
    "check_broker_reference_ownership",
    "check_foreign_keys",
    "check_idempotency_bindings",
    "run_integrity_check",
    "run_quick_check",
]
