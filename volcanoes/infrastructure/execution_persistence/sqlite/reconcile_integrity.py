"""Fail-closed integrity checks for durable Paper reconciliation authority."""

from __future__ import annotations

import sqlite3

from volcanoes.infrastructure.execution_persistence.sqlite.integrity import (
    InvariantCheckResult,
)


def check_reconcile_authority_bindings(
    connection: sqlite3.Connection,
) -> InvariantCheckResult:
    """Validate immutable RECONCILE command, idempotency, and approval bindings."""

    rows = connection.execute("""
        SELECT m.command_id
        FROM execution_commands AS m
        LEFT JOIN execution_idempotency AS i
          ON i.idempotency_key = m.idempotency_key
        LEFT JOIN execution_approvals AS p
          ON p.approval_fingerprint = m.approval_fingerprint
        WHERE m.operation = 'RECONCILE'
          AND (
            m.mode <> 'PAPER'
            OR i.idempotency_key IS NULL
            OR p.approval_fingerprint IS NULL
            OR i.command_id <> m.command_id
            OR i.aggregate_id <> m.aggregate_id
            OR i.mode <> m.mode
            OR p.mode <> m.mode
            OR p.bound_fingerprint <> m.canonical_payload_fingerprint
          )
        """).fetchall()
    violations = tuple(
        f"{row[0]} has invalid reconcile authority bindings" for row in rows
    )
    return InvariantCheckResult(
        invariant_name="reconcile_authority_bindings",
        passed=not violations,
        violations=violations,
        blocks_execution=bool(violations),
    )


__all__ = ["check_reconcile_authority_bindings"]
