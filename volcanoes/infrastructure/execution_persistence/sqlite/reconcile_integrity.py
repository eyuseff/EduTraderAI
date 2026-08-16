"""Fail-closed integrity checks for durable Paper reconciliation authority."""

from __future__ import annotations

import json
import sqlite3

from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.fingerprints import (
    command_payload_fingerprint,
    fingerprint_payload,
)
from volcanoes.infrastructure.execution_persistence.sqlite.integrity import (
    InvariantCheckResult,
)
from volcanoes.infrastructure.execution_persistence.sqlite.repositories import (
    _approval_from_row,
    _command_from_row,
    _reconciliation_from_row,
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
    """Validate immutable RECONCILE command, history, idempotency, and approval bindings."""

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
            OR p.approval_kind <> 'OPERATOR_CONFIRMED'
            OR p.revocation_reference IS NOT NULL
            OR p.approved_at > m.received_at
            OR (p.expires_at IS NOT NULL AND p.expires_at < m.received_at)
          )
        """).fetchall()
    violations = [
        f"{row[0]} has invalid reconcile authority bindings" for row in rows
    ]
    for row in connection.execute("""
        SELECT command_id, aggregate_id, expected_execution_revision,
               canonical_payload_fingerprint, canonical_command_json,
               idempotency_key, approval_fingerprint
        FROM execution_commands
        WHERE operation = 'RECONCILE'
        """):
        payload: dict[str, object] | None = None
        try:
            parsed = json.loads(
                row[4], object_pairs_hook=_reject_duplicate_json_keys
            )
            valid = (
                isinstance(parsed, dict)
                and canonical_json_text(parsed) == row[4]
                and command_payload_fingerprint(parsed) == row[3]
            )
            if valid:
                payload = parsed
        except (TypeError, ValueError, json.JSONDecodeError):
            valid = False
        if not valid or payload is None:
            violations.append(
                f"{row[0]} has invalid reconcile canonical command bindings"
            )
            continue

        command = connection.execute(
            "SELECT * FROM execution_commands WHERE command_id = ?",
            (row[0],),
        ).fetchone()
        command_record_valid = False
        if command is not None:
            try:
                reconstructed_command = _command_from_row(command)
                command_record_valid = (
                    reconstructed_command.record_fingerprint
                    == command["record_fingerprint"]
                )
            except (TypeError, ValueError):
                command_record_valid = False
        if not command_record_valid:
            violations.append(
                f"{row[0]} has invalid reconcile command record fingerprint"
            )

        reconciliation_id = payload.get("reconciliation_id")
        reconciliation_fingerprint = payload.get("reconciliation_record_fingerprint")
        payload_aggregate_id = payload.get("aggregate_id")
        starting_revision = payload.get("starting_local_revision")
        destination = payload.get("destination")
        history = None
        if isinstance(reconciliation_id, str):
            history = connection.execute(
                "SELECT * FROM execution_reconciliations WHERE reconciliation_id = ?",
                (reconciliation_id,),
            ).fetchone()
        history_valid = bool(
            history is not None
            and payload_aggregate_id == row[1]
            and starting_revision == row[2]
            and history["aggregate_id"] == row[1]
            and history["starting_local_revision"] == row[2]
            and reconciliation_fingerprint == history["record_fingerprint"]
            and history["operator_action_required"] == 1
            and history["unresolved"] == 1
            and history["resulting_transition_id"] is None
            and history["resulting_revision"] is None
            and history["mode"] == "PAPER"
        )
        if not history_valid:
            violations.append(
                f"{row[0]} has invalid reconcile history bindings"
            )
        history_record_valid = False
        if history is not None:
            try:
                reconstructed_history = _reconciliation_from_row(history)
                history_record_valid = (
                    reconstructed_history.record_fingerprint
                    == history["record_fingerprint"]
                )
            except (TypeError, ValueError):
                history_record_valid = False
        if not history_record_valid:
            violations.append(
                f"{row[0]} has invalid reconcile history record fingerprint"
            )

        idempotency = connection.execute(
            """
            SELECT logical_operation_fingerprint, command_id, aggregate_id, mode
            FROM execution_idempotency
            WHERE idempotency_key = ?
            """,
            (row[5],),
        ).fetchone()
        idempotency_valid = False
        if (
            idempotency is not None
            and isinstance(reconciliation_id, str)
            and isinstance(destination, str)
        ):
            expected_logical_fingerprint = fingerprint_payload(
                "plo",
                {
                    "destination": destination,
                    "reconciliation_id": reconciliation_id,
                },
            )
            idempotency_valid = bool(
                idempotency[0] == expected_logical_fingerprint
                and idempotency[1] == row[0]
                and idempotency[2] == row[1]
                and idempotency[3] == "PAPER"
            )
        if not idempotency_valid:
            violations.append(
                f"{row[0]} has invalid reconcile idempotency bindings"
            )

        approval = connection.execute(
            "SELECT * FROM execution_approvals WHERE approval_fingerprint = ?",
            (row[6],),
        ).fetchone()
        approval_valid = False
        if approval is not None:
            try:
                reconstructed = _approval_from_row(approval)
                approval_valid = (
                    reconstructed.record_fingerprint == approval["record_fingerprint"]
                )
            except (TypeError, ValueError):
                approval_valid = False
        if not approval_valid:
            violations.append(
                f"{row[0]} has invalid reconcile approval record fingerprint"
            )
    normalized = tuple(dict.fromkeys(violations))
    return InvariantCheckResult(
        invariant_name="reconcile_authority_bindings",
        passed=not normalized,
        violations=normalized,
        blocks_execution=bool(normalized),
    )


__all__ = ["check_reconcile_authority_bindings"]
