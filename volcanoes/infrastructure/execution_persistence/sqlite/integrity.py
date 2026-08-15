"""Integrity and invariant helpers for SQLite execution persistence foundation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from volcanoes.application.execution._canonical import canonical_json_text
from volcanoes.application.execution.fingerprints import (
    command_payload_fingerprint,
    fingerprint_payload,
)


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


def check_dispatch_claim_bindings(
    connection: sqlite3.Connection,
) -> InvariantCheckResult:
    """Validate V004 claim envelopes against their immutable durable authorities."""

    rows = connection.execute("""
        SELECT c.claim_token
        FROM execution_dispatch_claims AS c
        LEFT JOIN execution_commands AS m ON m.command_id = c.command_id
        LEFT JOIN execution_aggregates AS a ON a.aggregate_id = c.aggregate_id
        LEFT JOIN execution_idempotency AS i ON i.idempotency_key = c.idempotency_key
        LEFT JOIN execution_approvals AS p ON p.approval_fingerprint = c.approval_fingerprint
        LEFT JOIN execution_dispatch_resolutions AS r ON r.claim_token = c.claim_token
        WHERE m.command_id IS NULL OR a.aggregate_id IS NULL OR i.idempotency_key IS NULL
           OR p.approval_fingerprint IS NULL OR m.aggregate_id <> c.aggregate_id
           OR m.correlation_id <> c.correlation_id OR m.idempotency_key <> c.idempotency_key
           OR m.record_fingerprint <> c.command_record_fingerprint
           OR m.canonical_payload_fingerprint <> c.canonical_payload_fingerprint
           OR m.canonical_command_json <> c.canonical_order_json
           OR m.approval_fingerprint <> c.approval_fingerprint
           OR m.policy_fingerprint <> c.policy_fingerprint OR m.mode <> 'PAPER'
           OR p.bound_fingerprint <> c.canonical_payload_fingerprint
           OR p.mode <> 'PAPER' OR p.revocation_reference IS NOT NULL
           OR (p.expires_at IS NOT NULL AND p.expires_at < c.claimed_at)
           OR (r.claim_token IS NULL AND (
                 a.lifecycle_state <> 'DISPATCH_PENDING'
                 OR a.execution_revision <> c.expected_execution_revision))
           OR i.command_id <> c.command_id OR i.aggregate_id <> c.aggregate_id
           OR length(c.capability_verifier) <> 68
           OR substr(c.capability_verifier,1,4) <> 'pcv-'
           OR substr(c.capability_verifier,5) GLOB '*[^0-9a-f]*'
           OR c.control_generation > (SELECT generation FROM execution_dispatch_controls WHERE control_id='PAPER_DISPATCH')
        """).fetchall()
    violations = [f"{row[0]} has invalid durable bindings" for row in rows]
    for row in connection.execute("""
        SELECT claim_token, submission_id, command_id, idempotency_key,
               canonical_payload_fingerprint, canonical_order_json, client_order_id
        FROM execution_dispatch_claims
        """):
        try:
            payload = json.loads(row[5], object_pairs_hook=_reject_duplicate_json_keys)
            digest = fingerprint_payload(
                "pci",
                {
                    "domain": "paper-client-order-v1",
                    "inputs": {
                        "canonical_payload_fingerprint": row[4],
                        "command_id": row[2],
                        "idempotency_key": row[3],
                        "submission_id": row[1],
                    },
                },
            ).rsplit("-", 1)[-1]
            valid = (
                isinstance(payload, dict)
                and canonical_json_text(payload) == row[5]
                and command_payload_fingerprint(payload) == row[4]
                and row[6] == "paper-" + digest[:42]
            )
        except (TypeError, ValueError):
            valid = False
        if not valid:
            violations.append(f"{row[0]} has invalid canonical order bindings")
    normalized = tuple(dict.fromkeys(violations))
    return InvariantCheckResult(
        "dispatch_claim_bindings", not normalized, normalized, bool(normalized)
    )


def check_dispatch_outcome_bindings(
    connection: sqlite3.Connection,
) -> InvariantCheckResult:
    """Validate authorization generations and atomic outcome evidence bindings."""

    rows = connection.execute("""
        SELECT c.claim_token
        FROM execution_dispatch_claims AS c
        LEFT JOIN execution_dispatch_authorizations AS z
          ON z.claim_token = c.claim_token
        LEFT JOIN execution_dispatch_resolutions AS r
          ON r.claim_token = c.claim_token
        LEFT JOIN execution_aggregates AS a ON a.aggregate_id = c.aggregate_id
        WHERE (z.claim_token IS NOT NULL AND z.control_generation <> c.control_generation)
           OR (r.claim_token IS NOT NULL AND z.claim_token IS NULL)
           OR (r.claim_token IS NOT NULL AND a.lifecycle_state = 'DISPATCH_PENDING')
           OR (r.broker_reference IS NOT NULL
               AND r.resolution_status <> 'BROKER_REFERENCE_CONFLICT'
               AND NOT EXISTS (
                 SELECT 1 FROM execution_broker_references AS b
                 WHERE b.broker_reference = r.broker_reference
                   AND b.aggregate_id = c.aggregate_id
                   AND b.command_id = c.command_id))
           OR (r.resolution_status = 'BROKER_REFERENCE_CONFLICT' AND NOT EXISTS (
                 SELECT 1 FROM execution_broker_references AS b
                 WHERE b.broker_reference = r.broker_reference
                   AND b.aggregate_id = r.conflicting_owner_aggregate_id
                   AND b.command_id = r.conflicting_owner_command_id
                   AND b.record_fingerprint = r.conflicting_owner_record_fingerprint
                   AND r.conflicting_owner_aggregate_id <> c.aggregate_id
                   AND r.conflicting_owner_command_id <> c.command_id))
           OR (r.claim_token IS NOT NULL AND r.resolution_status = 'PRE_EFFECT_BLOCKED'
               AND NOT EXISTS (
                 SELECT 1 FROM execution_failures AS f
                 WHERE f.failure_fingerprint = r.evidence_fingerprint
                   AND f.record_fingerprint = r.evidence_record_fingerprint
                   AND f.aggregate_id = c.aggregate_id AND f.command_id = c.command_id
                   AND f.correlation_id = c.correlation_id))
           OR (r.claim_token IS NOT NULL AND r.resolution_status <> 'PRE_EFFECT_BLOCKED'
               AND NOT EXISTS (
                 SELECT 1 FROM execution_receipts AS e
                 WHERE e.receipt_fingerprint = r.evidence_fingerprint
                   AND e.record_fingerprint = r.evidence_record_fingerprint
                   AND e.aggregate_id = c.aggregate_id AND e.command_id = c.command_id
                   AND e.correlation_id = c.correlation_id))
           OR (r.claim_token IS NOT NULL AND NOT EXISTS (
                 SELECT 1 FROM execution_transitions AS t
                 WHERE t.aggregate_id = c.aggregate_id
                   AND t.transition_id = a.last_transition_id
                   AND t.next_revision = a.execution_revision
                   AND t.destination_state = a.lifecycle_state
                   AND ((r.resolution_status = 'PRE_EFFECT_BLOCKED'
                         AND t.failure_fingerprint = r.evidence_fingerprint)
                        OR (r.resolution_status <> 'PRE_EFFECT_BLOCKED'
                            AND t.receipt_fingerprint = r.evidence_fingerprint))))
        """).fetchall()
    violations = [f"{row[0]} has invalid outcome bindings" for row in rows]
    expected_edges = {
        "PRE_EFFECT_BLOCKED": (
            (
                "PX-TRN-029",
                "ABORT_BEFORE_DISPATCH",
                "DISPATCH_PENDING",
                "ABORTED_BEFORE_DISPATCH",
            ),
        ),
        "ACKNOWLEDGED": (
            ("PX-TRN-009", "RECORD_DISPATCH", "DISPATCH_PENDING", "DISPATCHED"),
            (
                "PX-TRN-010",
                "OBSERVE_BROKER_ACKNOWLEDGEMENT",
                "DISPATCHED",
                "BROKER_ACKNOWLEDGED",
            ),
        ),
        "BROKER_REJECTED": (
            ("PX-TRN-009", "RECORD_DISPATCH", "DISPATCH_PENDING", "DISPATCHED"),
            ("PX-TRN-011", "OBSERVE_BROKER_REJECTION", "DISPATCHED", "BROKER_REJECTED"),
        ),
        "OUTCOME_UNKNOWN": (
            ("PX-TRN-009", "RECORD_DISPATCH", "DISPATCH_PENDING", "DISPATCHED"),
            ("PX-TRN-012", "MARK_OUTCOME_UNKNOWN", "DISPATCHED", "OUTCOME_UNKNOWN"),
        ),
        "BROKER_REFERENCE_CONFLICT": (
            ("PX-TRN-009", "RECORD_DISPATCH", "DISPATCH_PENDING", "DISPATCHED"),
            ("PX-TRN-012", "MARK_OUTCOME_UNKNOWN", "DISPATCHED", "OUTCOME_UNKNOWN"),
        ),
    }
    outcomes = connection.execute("""
        SELECT c.claim_token, c.aggregate_id, c.command_id, c.correlation_id,
               c.idempotency_key, c.expected_execution_revision,
               r.resolution_status, r.evidence_fingerprint,
               a.execution_revision, a.lifecycle_state, a.last_transition_id
        FROM execution_dispatch_claims AS c
        JOIN execution_dispatch_resolutions AS r ON r.claim_token = c.claim_token
        JOIN execution_aggregates AS a ON a.aggregate_id = c.aggregate_id
        """).fetchall()
    for outcome in outcomes:
        transitions = connection.execute(
            """
            SELECT transition_record_id, transition_id, source_state,
                   destination_state, previous_revision, next_revision,
                   lifecycle_input_kind, command_id, correlation_id,
                   idempotency_key, receipt_fingerprint, failure_fingerprint,
                   broker_observation_identity, recorded_at
            FROM execution_transitions
            WHERE aggregate_id = ? AND previous_revision >= ?
              AND next_revision <= ?
            ORDER BY next_revision
            """,
            (outcome[1], outcome[5], outcome[8]),
        ).fetchall()
        edges = expected_edges.get(outcome[6], ())
        valid = (
            outcome[9] == (edges[-1][3] if edges else None)
            and outcome[8] - outcome[5] == len(edges) == len(transitions)
            and bool(transitions)
        )
        prior_time = None
        for index, transition in enumerate(transitions):
            edge = edges[index] if index < len(edges) else None
            final = index == len(transitions) - 1
            evidence = (
                transition[10] if outcome[6] != "PRE_EFFECT_BLOCKED" else transition[11]
            )
            valid = valid and bool(
                edge is not None
                and (transition[1], transition[6], transition[2], transition[3]) == edge
                and transition[0] == f"{outcome[0]}-{transition[1]}"
                and transition[4] == outcome[5] + index
                and transition[5] == outcome[5] + index + 1
                and transition[7] == outcome[2]
                and transition[8] == outcome[3]
                and transition[9] == outcome[4]
                and (
                    (not final and evidence is None and transition[12] is None)
                    or (final and evidence == outcome[7])
                )
                and (prior_time is None or transition[13] >= prior_time)
            )
            prior_time = transition[13]
        if not transitions or transitions[-1][1] != outcome[10]:
            valid = False
        if not valid:
            violations.append(f"{outcome[0]} has invalid outcome transition chain")
    normalized = tuple(dict.fromkeys(violations))
    return InvariantCheckResult(
        "dispatch_outcome_bindings", not normalized, normalized, bool(normalized)
    )


def _reject_duplicate_json_keys(items: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


__all__ = [
    "IntegrityCheckResult",
    "InvariantCheckResult",
    "check_aggregate_transition_revisions",
    "check_broker_reference_ownership",
    "check_foreign_keys",
    "check_dispatch_claim_bindings",
    "check_dispatch_outcome_bindings",
    "check_idempotency_bindings",
    "run_integrity_check",
    "run_quick_check",
]
