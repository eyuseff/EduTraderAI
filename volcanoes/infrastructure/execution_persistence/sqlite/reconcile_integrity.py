"""Fail-closed integrity checks for durable Paper reconciliation authority."""

from __future__ import annotations

import json
import sqlite3

from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.fingerprints import command_payload_fingerprint
from volcanoes.infrastructure.execution_persistence.sqlite.integrity import (
    InvariantCheckResult,
)


def _reject_duplicate_json_keys(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


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
    violations = [
        f"{row[0]} has invalid reconcile authority bindings" for row in rows
    ]
    for row in connection.execute("""
        SELECT command_id, canonical_payload_fingerprint, canonical_command_json
        FROM execution_commands
        WHERE operation = 'RECONCILE'
        """):
        try:
            payload = json.loads(
                row[2], object_pairs_hook=_reject_duplicate_json_keys
            )
            valid = (
                isinstance(payload, dict)
                and canonical_json_text(payload) == row[2]
                and command_payload_fingerprint(payload) == row[1]
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            valid = False
        if not valid:
            violations.append(
                f"{row[0]} has invalid reconcile canonical command bindings"
            )
    normalized = tuple(dict.fromkeys(violations))
    return InvariantCheckResult(
        invariant_name="reconcile_authority_bindings",
        passed=not normalized,
        violations=normalized,
        blocks_execution=bool(normalized),
    )


__all__ = ["check_reconcile_authority_bindings"]
