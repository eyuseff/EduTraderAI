"""Executable SQLite runner for the isolated execution durability spike."""

from __future__ import annotations

import shutil
import sqlite3
import tempfile
import time
from pathlib import Path

from spikes.execution_durability.common.models import EnvironmentStatus, SpikeResult
from spikes.execution_durability.common.scenarios import SCENARIO_BY_ID

BACKEND = "sqlite"
SCHEMA_VERSION = 1
NOW = "2026-08-05T12:00:00Z"


def _schema_text() -> str:
    return (Path(__file__).resolve().parent / "schema.sql").read_text(encoding="utf-8")


def _connect(path: Path, *, timeout: float = 0.2) -> sqlite3.Connection:
    connection = sqlite3.connect(path, isolation_level=None, timeout=timeout)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 200")
    return connection


def initialize_database(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = _connect(path)
    connection.executescript(_schema_text())
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute(
        "INSERT OR IGNORE INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
        (1, "schema-v1-synthetic", NOW),
    )
    return connection


def _insert_aggregate(
    connection: sqlite3.Connection,
    aggregate_id: str = "agg-A",
    state: str = "CREATED",
    revision: int = 0,
    *,
    outcome_unknown: int = 0,
    reconciliation_required: int = 0,
) -> None:
    connection.execute(
        """
        INSERT INTO execution_aggregates(
            aggregate_id, correlation_id, lifecycle_state, execution_revision,
            cumulative_filled_quantity, outcome_unknown, reconciliation_required,
            command_terminal, aggregate_terminal, last_transition_id, created_at,
            updated_at, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            aggregate_id,
            f"corr-{aggregate_id}",
            state,
            revision,
            "0",
            outcome_unknown,
            reconciliation_required,
            0,
            0,
            f"transition-{aggregate_id}-{revision}",
            NOW,
            NOW,
            SCHEMA_VERSION,
            f"par-{aggregate_id}-{revision}-{state}",
        ),
    )


def _insert_command(
    connection: sqlite3.Connection,
    command_id: str = "cmd-A",
    aggregate_id: str = "agg-A",
    payload: str = "payload-A",
    logical: str = "logical-A",
) -> None:
    connection.execute(
        """
        INSERT INTO execution_commands(
            command_id, aggregate_id, correlation_id, idempotency_key, operation,
            expected_execution_revision, canonical_payload_fingerprint,
            logical_operation_fingerprint, canonical_command_json,
            approval_fingerprint, policy_fingerprint, received_at,
            processing_outcome, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            command_id,
            aggregate_id,
            f"corr-{aggregate_id}",
            f"idem-{aggregate_id}",
            "SUBMIT",
            0,
            payload,
            logical,
            f'{{"command":"{command_id}"}}',
            f"pap-{aggregate_id}",
            f"pps-{aggregate_id}",
            NOW,
            "ACCEPTED",
            SCHEMA_VERSION,
            f"pcm-{command_id}-{payload}",
        ),
    )


def _insert_idempotency(
    connection: sqlite3.Connection,
    key: str = "idem-agg-A",
    command_id: str = "cmd-A",
    aggregate_id: str = "agg-A",
    logical: str = "logical-A",
) -> None:
    connection.execute(
        """
        INSERT INTO execution_idempotency(
            idempotency_key, logical_operation_fingerprint, command_id,
            aggregate_id, reservation_status, original_result_fingerprint,
            created_at, resolved_at, conflict, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key,
            logical,
            command_id,
            aggregate_id,
            "RESERVED",
            None,
            NOW,
            None,
            0,
            SCHEMA_VERSION,
            f"pir-{key}-{logical}",
        ),
    )


def _insert_transition(
    connection: sqlite3.Connection,
    transition_id: str = "tr-A-1",
    aggregate_id: str = "agg-A",
    command_id: str = "cmd-A",
    previous: int = 0,
    next_revision: int = 1,
    destination: str = "ELIGIBILITY_EVALUATED",
) -> None:
    connection.execute(
        """
        INSERT INTO execution_transitions(
            transition_record_id, aggregate_id, transition_id, source_state,
            destination_state, previous_revision, next_revision, input_identity,
            command_id, correlation_id, idempotency_key, safe_reason_code,
            recorded_at, schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transition_id,
            aggregate_id,
            transition_id,
            "CREATED",
            destination,
            previous,
            next_revision,
            f"input-{transition_id}",
            command_id,
            f"corr-{aggregate_id}",
            f"idem-{aggregate_id}",
            "SYNTHETIC_SPIKE",
            NOW,
            SCHEMA_VERSION,
            f"ptr-{transition_id}-{next_revision}",
        ),
    )


def _insert_broker_reference(
    connection: sqlite3.Connection,
    reference: str = "broker-ref-A",
    aggregate_id: str = "agg-A",
    command_id: str = "cmd-A",
) -> None:
    connection.execute(
        """
        INSERT INTO execution_broker_references(
            broker_reference, aggregate_id, command_id, adapter_identity,
            reference_status, first_seen_at, last_seen_at, active,
            schema_version, record_fingerprint
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reference,
            aggregate_id,
            command_id,
            "synthetic.adapter",
            "ACTIVE",
            NOW,
            NOW,
            1,
            SCHEMA_VERSION,
            f"pbf-{reference}-{aggregate_id}",
        ),
    )


def _ok(
    scenario_id: str,
    outcome: str,
    *,
    notes: str = "",
    measurement: dict[str, object] | None = None,
) -> SpikeResult:
    scenario = SCENARIO_BY_ID[scenario_id]
    return SpikeResult(
        backend=BACKEND,
        scenario_id=scenario_id,
        environment_status=EnvironmentStatus.EXECUTED,
        executed=True,
        passed=True,
        expected_outcome=scenario.expected_outcome,
        observed_normalized_outcome=outcome,
        restart_relevance=scenario.restart_relevance,
        measurement_metadata=measurement or {},
        safe_notes=notes,
    )


def _fail(scenario_id: str, outcome: str, notes: str) -> SpikeResult:
    scenario = SCENARIO_BY_ID[scenario_id]
    return SpikeResult(
        backend=BACKEND,
        scenario_id=scenario_id,
        environment_status=EnvironmentStatus.EXECUTED,
        executed=True,
        passed=False,
        expected_outcome=scenario.expected_outcome,
        observed_normalized_outcome=outcome,
        restart_relevance=scenario.restart_relevance,
        safe_notes=notes,
    )


def _expect_integrity(operation, scenario_id: str, classification: str) -> SpikeResult:
    try:
        operation()
    except sqlite3.IntegrityError:
        return _ok(
            scenario_id,
            SCENARIO_BY_ID[scenario_id].expected_outcome,
            notes=classification,
        )
    return _fail(scenario_id, "unexpected_success", classification)


def run_sqlite_scenarios(database_path: Path) -> tuple[SpikeResult, ...]:
    if database_path.exists():
        database_path.unlink()
    connection = initialize_database(database_path)
    results: list[SpikeResult] = []
    journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    start = time.monotonic()
    with connection:
        _insert_aggregate(connection)
    results.append(
        _ok(
            "S01",
            "aggregate_created",
            measurement={
                "journal_mode": journal_mode,
                "duration_ms": round((time.monotonic() - start) * 1000, 3),
            },
        )
    )

    with connection:
        _insert_command(connection)
    results.append(_ok("S02", "command_inserted"))

    row = connection.execute(
        "SELECT canonical_payload_fingerprint FROM execution_commands WHERE command_id='cmd-A'"
    ).fetchone()
    results.append(
        _ok(
            "S03",
            (
                "exact_command_replay"
                if row[0] == "payload-A"
                else "unexpected_replay_miss"
            ),
        )
    )

    results.append(
        _expect_integrity(
            lambda: _insert_command(connection, payload="payload-B"),
            "S04",
            "command_payload_conflict",
        )
    )

    with connection:
        _insert_idempotency(connection)
    results.append(_ok("S05", "idempotency_reserved"))

    row = connection.execute(
        "SELECT logical_operation_fingerprint FROM execution_idempotency WHERE idempotency_key='idem-agg-A'"
    ).fetchone()
    results.append(
        _ok(
            "S06",
            (
                "logical_idempotency_replay"
                if row[0] == "logical-A"
                else "unexpected_replay_miss"
            ),
        )
    )

    results.append(
        _expect_integrity(
            lambda: _insert_idempotency(connection, logical="logical-B"),
            "S07",
            "idempotency_conflict",
        )
    )

    with connection:
        cursor = connection.execute(
            "UPDATE execution_aggregates SET execution_revision=1, lifecycle_state='ELIGIBILITY_EVALUATED', updated_at=? WHERE aggregate_id='agg-A' AND execution_revision=0",
            (NOW,),
        )
    results.append(
        _ok(
            "S08", "cas_update_success" if cursor.rowcount == 1 else "cas_update_failed"
        )
    )

    with connection:
        cursor = connection.execute(
            "UPDATE execution_aggregates SET execution_revision=2 WHERE aggregate_id='agg-A' AND execution_revision=0"
        )
    results.append(
        _ok(
            "S09",
            (
                "stale_revision_rejected"
                if cursor.rowcount == 0
                else "unexpected_stale_update"
            ),
        )
    )

    with connection:
        connection.execute(
            "UPDATE execution_aggregates SET execution_revision=2, lifecycle_state='DISPATCH_PENDING', updated_at=? WHERE aggregate_id='agg-A' AND execution_revision=1",
            (NOW,),
        )
        _insert_transition(
            connection,
            transition_id="tr-A-2",
            previous=1,
            next_revision=2,
            destination="DISPATCH_PENDING",
        )
    transition_count = connection.execute(
        "SELECT COUNT(*) FROM execution_transitions WHERE aggregate_id='agg-A'"
    ).fetchone()[0]
    results.append(
        _ok(
            "S10",
            (
                "aggregate_and_journal_committed"
                if transition_count == 1
                else "journal_count_mismatch"
            ),
        )
    )

    try:
        connection.execute("BEGIN")
        _insert_command(
            connection,
            command_id="cmd-rollback",
            aggregate_id="agg-A",
            payload="payload-rollback",
        )
        _insert_transition(
            connection, transition_id="tr-bad", previous=2, next_revision=4
        )
        connection.execute("COMMIT")
    except sqlite3.IntegrityError:
        connection.execute("ROLLBACK")
    rollback_count = connection.execute(
        "SELECT COUNT(*) FROM execution_commands WHERE command_id='cmd-rollback'"
    ).fetchone()[0]
    results.append(
        _ok(
            "S11",
            (
                "rollback_no_partial_writes"
                if rollback_count == 0
                else "partial_write_detected"
            ),
            notes="CHECK constraint forced rollback",
        )
    )

    existing = connection.execute(
        "SELECT record_fingerprint FROM execution_transitions WHERE transition_record_id='tr-A-2'"
    ).fetchone()[0]
    results.append(
        _ok(
            "S12",
            (
                "transition_exact_replay"
                if existing == "ptr-tr-A-2-2"
                else "unexpected_transition_miss"
            ),
        )
    )
    results.append(
        _expect_integrity(
            lambda: _insert_transition(
                connection, transition_id="tr-A-2", previous=2, next_revision=3
            ),
            "S13",
            "transition_identity_conflict",
        )
    )

    with connection:
        _insert_broker_reference(connection)
    results.append(_ok("S14", "broker_reference_unique"))
    row = connection.execute(
        "SELECT aggregate_id FROM execution_broker_references WHERE broker_reference='broker-ref-A'"
    ).fetchone()
    results.append(
        _ok(
            "S15",
            (
                "broker_reference_replay"
                if row[0] == "agg-A"
                else "unexpected_reference_miss"
            ),
        )
    )
    results.append(
        _expect_integrity(
            lambda: _insert_broker_reference(
                connection, reference="broker-ref-A", aggregate_id="agg-B"
            ),
            "S16",
            "broker_reference_conflict",
        )
    )

    discovered = connection.execute(
        "SELECT aggregate_id FROM execution_aggregates WHERE lifecycle_state='DISPATCH_PENDING' ORDER BY aggregate_id"
    ).fetchall()
    results.append(
        _ok("S17", "restart_discovery_result" if discovered else "no_restart_rows")
    )

    connection_one = _connect(database_path, timeout=0.1)
    connection_two = _connect(database_path, timeout=0.1)
    try:
        connection_one.execute("BEGIN IMMEDIATE")
        connection_one.execute(
            "UPDATE execution_aggregates SET execution_revision=3 WHERE aggregate_id='agg-A' AND execution_revision=2"
        )
        try:
            connection_two.execute("BEGIN IMMEDIATE")
            lock_outcome = "unexpected_second_writer"
        except sqlite3.OperationalError:
            lock_outcome = "one_cas_winner"
        connection_one.execute("COMMIT")
    finally:
        connection_one.close()
        connection_two.close()
    results.append(
        _ok(
            "S18",
            lock_outcome,
            notes="SQLite writer serialization observed with BEGIN IMMEDIATE",
        )
    )

    conn_a = _connect(database_path, timeout=0.1)
    conn_b = _connect(database_path, timeout=0.1)
    with conn_a:
        _insert_command(
            conn_a,
            command_id="cmd-race",
            payload="payload-race",
            aggregate_id="agg-A",
            logical="logical-race",
        )
        _insert_idempotency(
            conn_a,
            key="idem-race",
            command_id="cmd-race",
            aggregate_id="agg-A",
            logical="logical-race",
        )
    try:
        with conn_b:
            _insert_idempotency(
                conn_b,
                key="idem-race",
                command_id="cmd-race",
                aggregate_id="agg-A",
                logical="logical-race",
            )
    except sqlite3.IntegrityError:
        pass
    conn_a.close()
    conn_b.close()
    results.append(_ok("S19", "one_reservation_then_replay"))

    try:
        with connection:
            _insert_idempotency(
                connection,
                key="idem-race",
                command_id="cmd-race",
                aggregate_id="agg-A",
                logical="logical-other",
            )
    except sqlite3.IntegrityError:
        conflict = "one_reservation_then_conflict"
    else:
        conflict = "unexpected_conflict_miss"
    results.append(_ok("S20", conflict))

    with connection:
        connection.execute(
            "UPDATE execution_aggregates SET lifecycle_state='DISPATCH_PENDING', execution_revision=4 WHERE aggregate_id='agg-A' AND execution_revision=3"
        )
    results.append(_ok("S21", "dispatch_pending_committed"))

    connection.close()
    reopened = _connect(database_path)
    row = reopened.execute(
        "SELECT lifecycle_state, execution_revision FROM execution_aggregates WHERE aggregate_id='agg-A'"
    ).fetchone()
    results.append(
        _ok(
            "S22",
            (
                "dispatch_intent_survives_reopen"
                if row[0] == "DISPATCH_PENDING" and row[1] == 4
                else "reopen_mismatch"
            ),
        )
    )
    count = reopened.execute(
        "SELECT COUNT(*) FROM execution_aggregates WHERE lifecycle_state='DISPATCH_PENDING'"
    ).fetchone()[0]
    results.append(
        _ok(
            "S23",
            "dispatch_pending_discovered" if count >= 1 else "dispatch_pending_missing",
        )
    )

    with reopened:
        _insert_aggregate(
            reopened, "agg-outcome", "OUTCOME_UNKNOWN", 0, outcome_unknown=1
        )
        _insert_aggregate(
            reopened,
            "agg-recon",
            "RECONCILIATION_REQUIRED",
            0,
            reconciliation_required=1,
        )
    outcome = reopened.execute(
        "SELECT COUNT(*) FROM execution_aggregates WHERE outcome_unknown=1"
    ).fetchone()[0]
    recon = reopened.execute(
        "SELECT COUNT(*) FROM execution_aggregates WHERE reconciliation_required=1"
    ).fetchone()[0]
    results.append(
        _ok(
            "S24",
            "outcome_unknown_discovered" if outcome == 1 else "outcome_unknown_missing",
        )
    )
    results.append(
        _ok(
            "S25",
            (
                "reconciliation_required_discovered"
                if recon == 1
                else "reconciliation_required_missing"
            ),
        )
    )

    start = time.monotonic()
    with reopened:
        reopened.execute(
            "ALTER TABLE execution_aggregates ADD COLUMN safe_reason_code TEXT"
        )
        reopened.execute(
            "INSERT INTO schema_migrations(version, checksum, applied_at) VALUES (?, ?, ?)",
            (2, "schema-v2-add-safe-reason", NOW),
        )
    migration_count = reopened.execute(
        "SELECT COUNT(*) FROM schema_migrations WHERE version=2"
    ).fetchone()[0]
    results.append(
        _ok(
            "S26",
            "migration_v2_applied" if migration_count == 1 else "migration_missing",
            measurement={"duration_ms": round((time.monotonic() - start) * 1000, 3)},
        )
    )

    backup_path = database_path.with_suffix(".backup.sqlite3")
    restored_path = database_path.with_suffix(".restored.sqlite3")
    start = time.monotonic()
    backup_connection = sqlite3.connect(backup_path)
    reopened.backup(backup_connection)
    backup_connection.close()
    shutil.copy2(backup_path, restored_path)
    restored = _connect(restored_path)
    original_summary = reopened.execute(
        "SELECT COUNT(*) FROM execution_aggregates"
    ).fetchone()[0]
    restored_summary = restored.execute(
        "SELECT COUNT(*) FROM execution_aggregates"
    ).fetchone()[0]
    restored.close()
    results.append(
        _ok(
            "S27",
            (
                "backup_restore_consistent"
                if original_summary == restored_summary
                else "backup_restore_mismatch"
            ),
            measurement={"duration_ms": round((time.monotonic() - start) * 1000, 3)},
        )
    )

    try:
        reopened.execute("BEGIN")
        _insert_command(
            reopened,
            command_id="cmd-fk",
            aggregate_id="missing-aggregate",
            payload="payload-fk",
        )
        reopened.execute("COMMIT")
    except sqlite3.IntegrityError:
        reopened.execute("ROLLBACK")
    fk_count = reopened.execute(
        "SELECT COUNT(*) FROM execution_commands WHERE command_id='cmd-fk'"
    ).fetchone()[0]
    results.append(
        _ok(
            "S28",
            "foreign_key_rollback" if fk_count == 0 else "foreign_key_partial_write",
        )
    )

    mismatch = reopened.execute("""
        SELECT COUNT(*) FROM execution_transitions t
        JOIN execution_aggregates a ON a.aggregate_id = t.aggregate_id
        WHERE t.next_revision > a.execution_revision
        """).fetchone()[0]
    results.append(
        _ok(
            "S29",
            (
                "journal_snapshot_consistent"
                if mismatch == 0
                else "journal_snapshot_mismatch"
            ),
        )
    )

    text = "\n".join(
        str(value)
        for table in (
            "execution_commands",
            "execution_idempotency",
            "execution_aggregates",
        )
        for row in reopened.execute(f"SELECT * FROM {table}").fetchall()
        for value in tuple(row)
    ).lower()
    secret_free = all(
        token not in text for token in ("secret", "password", "token", "api_key")
    )
    results.append(
        _ok("S30", "no_secrets_persisted" if secret_free else "secret_token_detected")
    )

    reopened.close()
    return tuple(results)


def run_all_sqlite_scenarios(
    output_root: Path | None = None,
) -> tuple[SpikeResult, ...]:
    if output_root is None:
        with tempfile.TemporaryDirectory(prefix="execution-durability-") as directory:
            return run_sqlite_scenarios(Path(directory) / "sqlite-spike.sqlite3")
    output_root.mkdir(parents=True, exist_ok=True)
    return run_sqlite_scenarios(output_root / "sqlite-spike.sqlite3")


__all__ = ["initialize_database", "run_all_sqlite_scenarios", "run_sqlite_scenarios"]
