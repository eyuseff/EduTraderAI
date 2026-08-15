from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from volcanoes.infrastructure.execution_persistence.sqlite import (
    KNOWN_MIGRATIONS,
    apply_pending_migrations,
    open_sqlite_execution_connection,
)
from volcanoes.infrastructure.execution_persistence.sqlite.integrity import (
    check_dispatch_outcome_bindings,
)
from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionSchemaError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    SqliteExecutionPersistence,
)
from volcanoes.infrastructure.execution_persistence.sqlite.repositories import (
    _broker_reference_from_row,
    _transition_from_row,
)
from volcanoes.application.execution import PaperBrokerOrderReference
from volcanoes.application.execution.persistence import (
    ExecutionBrokerReferenceRecord,
    ExecutionBrokerReferenceStatus,
    ExecutionPersistenceResultStatus,
)
from volcanoes.application.execution.submission import (
    ControlledPaperSubmissionService,
    PaperDispatchObservation,
)
from test_sqlite_execution_persistence_unit_of_work import (
    DISPATCH_NOW,
    _aggregate,
    _command,
    _connection,
    _seed_dispatch_authority,
)

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def test_claim_evidence_tables_are_append_only(tmp_path) -> None:
    connection = open_sqlite_execution_connection(tmp_path / "immutable.sqlite")
    try:
        apply_pending_migrations(
            connection,
            KNOWN_MIGRATIONS,
            applied_at=NOW,
            application_version="f6a-v004-test",
        )
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "INSERT INTO execution_dispatch_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "claim-1",
                "submission-1",
                "command-1",
                "aggregate-1",
                "correlation-1",
                "idempotency-1",
                5,
                "psq-" + "1" * 64,
                "pcm-" + "2" * 64,
                "pcf-" + "3" * 64,
                "pap-" + "4" * 64,
                "pps-" + "5" * 64,
                "c" * 48,
                "pcv-" + "7" * 64,
                "{}",
                1,
                "2026-08-14T00:00:00.000000Z",
                "PAPER",
                "4",
                "pcl-" + "6" * 64,
            ),
        )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE execution_dispatch_claims SET submission_id='changed'"
            )
        connection.rollback()
    finally:
        connection.close()


def test_ambiguous_resolution_requires_reconciliation(tmp_path) -> None:
    connection = open_sqlite_execution_connection(tmp_path / "resolution.sqlite")
    try:
        apply_pending_migrations(
            connection,
            KNOWN_MIGRATIONS,
            applied_at=NOW,
            application_version="f6a-v004-test",
        )
        connection.execute("PRAGMA foreign_keys=OFF")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO execution_dispatch_resolutions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "claim-1",
                    "OUTCOME_UNKNOWN",
                    "POSSIBLE_POST_EFFECT",
                    "2026-08-14T00:00:00.000000Z",
                    None,
                    None,
                    None,
                    None,
                    None,
                    "result",
                    "prc-" + "1" * 64,
                    "prr-" + "2" * 64,
                    "UNKNOWN",
                    0,
                    1,
                    0,
                    "4",
                    "record",
                ),
            )
    finally:
        connection.close()


def _resolved_chain_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript("""
        CREATE TABLE execution_dispatch_claims (
          claim_token TEXT, aggregate_id TEXT, command_id TEXT, correlation_id TEXT,
          idempotency_key TEXT, expected_execution_revision INTEGER,
          control_generation INTEGER);
        CREATE TABLE execution_dispatch_authorizations (
          claim_token TEXT, control_generation INTEGER);
        CREATE TABLE execution_dispatch_resolutions (
          claim_token TEXT, resolution_status TEXT, broker_reference TEXT,
          evidence_fingerprint TEXT, evidence_record_fingerprint TEXT,
          conflicting_owner_aggregate_id TEXT,
          conflicting_owner_command_id TEXT,
          conflicting_owner_record_fingerprint TEXT);
        CREATE TABLE execution_aggregates (
          aggregate_id TEXT, lifecycle_state TEXT, execution_revision INTEGER,
          last_transition_id TEXT);
        CREATE TABLE execution_broker_references (
          broker_reference TEXT, aggregate_id TEXT, command_id TEXT,
          record_fingerprint TEXT);
        CREATE TABLE execution_failures (
          failure_fingerprint TEXT, record_fingerprint TEXT, aggregate_id TEXT,
          command_id TEXT, correlation_id TEXT);
        CREATE TABLE execution_receipts (
          receipt_fingerprint TEXT, record_fingerprint TEXT, aggregate_id TEXT,
          command_id TEXT, correlation_id TEXT);
        CREATE TABLE execution_transitions (
          transition_record_id TEXT, aggregate_id TEXT, transition_id TEXT,
          source_state TEXT, destination_state TEXT, previous_revision INTEGER,
          next_revision INTEGER, lifecycle_input_kind TEXT, command_id TEXT,
          correlation_id TEXT, idempotency_key TEXT, receipt_fingerprint TEXT,
          failure_fingerprint TEXT, broker_observation_identity TEXT,
          recorded_at TEXT);
        INSERT INTO execution_dispatch_claims VALUES
          ('claim-1','aggregate-1','command-1','correlation-1','idempotency-1',5,1);
        INSERT INTO execution_dispatch_authorizations VALUES ('claim-1',1);
        INSERT INTO execution_dispatch_resolutions VALUES
          ('claim-1','ACKNOWLEDGED','broker-1','receipt-1','receipt-record-1',
           NULL,NULL,NULL);
        INSERT INTO execution_aggregates VALUES
          ('aggregate-1','BROKER_ACKNOWLEDGED',7,'PX-TRN-010');
        INSERT INTO execution_broker_references VALUES
          ('broker-1','aggregate-1','command-1','owner-record-1');
        INSERT INTO execution_receipts VALUES
          ('receipt-1','receipt-record-1','aggregate-1','command-1','correlation-1');
        INSERT INTO execution_transitions VALUES
          ('claim-1-PX-TRN-009','aggregate-1','PX-TRN-009','DISPATCH_PENDING',
           'DISPATCHED',5,6,'RECORD_DISPATCH','command-1','correlation-1',
           'idempotency-1',NULL,NULL,NULL,'2026-08-14T00:00:00.000000Z'),
          ('claim-1-PX-TRN-010','aggregate-1','PX-TRN-010','DISPATCHED',
           'BROKER_ACKNOWLEDGED',6,7,'OBSERVE_BROKER_ACKNOWLEDGEMENT','command-1',
           'correlation-1','idempotency-1','receipt-1',NULL,'observation-1',
           '2026-08-14T00:00:01.000000Z');
        """)
    return connection


def test_complete_resolved_transition_chain_integrity_check() -> None:
    connection = _resolved_chain_connection()
    assert check_dispatch_outcome_bindings(connection).passed
    for transition_id in ("PX-TRN-009", "PX-TRN-010"):
        candidate = _resolved_chain_connection()
        candidate.execute(
            "DELETE FROM execution_transitions WHERE transition_id = ?",
            (transition_id,),
        )
        assert not check_dispatch_outcome_bindings(candidate).passed


@pytest.mark.parametrize(
    ("column", "value"),
    (
        ("source_state", "READY_FOR_DISPATCH"),
        ("destination_state", "OUTCOME_UNKNOWN"),
        ("previous_revision", 4),
        ("next_revision", 8),
        ("transition_id", "PX-TRN-011"),
        ("lifecycle_input_kind", "OBSERVE_BROKER_REJECTION"),
        ("command_id", "other-command"),
        ("correlation_id", "other-correlation"),
        ("idempotency_key", "other-idempotency"),
        ("receipt_fingerprint", None),
    ),
)
def test_altered_resolved_transition_chain_integrity_check(column, value) -> None:
    connection = _resolved_chain_connection()
    connection.execute(
        f"UPDATE execution_transitions SET {column} = ? WHERE transition_id = 'PX-TRN-010'",
        (value,),
    )
    assert not check_dispatch_outcome_bindings(connection).passed


def test_reordered_or_surplus_resolved_transition_chain_integrity_check() -> None:
    reordered = _resolved_chain_connection()
    reordered.execute(
        "UPDATE execution_transitions SET recorded_at = '2026-08-13T00:00:00.000000Z' "
        "WHERE transition_id = 'PX-TRN-010'"
    )
    assert not check_dispatch_outcome_bindings(reordered).passed

    surplus = _resolved_chain_connection()
    surplus.execute("UPDATE execution_aggregates SET execution_revision = 8")
    assert not check_dispatch_outcome_bindings(surplus).passed


@pytest.mark.parametrize(
    ("owner", "passed"),
    (
        (None, False),
        (("aggregate-1", "command-1"), False),
        (("aggregate-1", "other-command"), False),
        (("other-aggregate", "other-command"), True),
    ),
)
def test_broker_reference_conflict_requires_authentic_different_owner(
    owner, passed
) -> None:
    connection = _resolved_chain_connection()
    connection.execute(
        "UPDATE execution_dispatch_resolutions "
        "SET resolution_status = 'BROKER_REFERENCE_CONFLICT'"
    )
    connection.execute("DELETE FROM execution_broker_references")
    connection.execute(
        "UPDATE execution_aggregates SET lifecycle_state = 'OUTCOME_UNKNOWN', "
        "last_transition_id = 'PX-TRN-012'"
    )
    connection.execute(
        "UPDATE execution_transitions SET transition_record_id = 'claim-1-PX-TRN-012', "
        "transition_id = 'PX-TRN-012', destination_state = 'OUTCOME_UNKNOWN', "
        "lifecycle_input_kind = 'MARK_OUTCOME_UNKNOWN' "
        "WHERE next_revision = 7"
    )
    if owner is not None:
        owner_fingerprint = "owner-record-1"
        connection.execute(
            "INSERT INTO execution_broker_references VALUES ('broker-1', ?, ?, ?)",
            (*owner, owner_fingerprint),
        )
        connection.execute(
            "UPDATE execution_dispatch_resolutions "
            "SET conflicting_owner_aggregate_id = ?, "
            "conflicting_owner_command_id = ?, "
            "conflicting_owner_record_fingerprint = ?",
            (*owner, owner_fingerprint),
        )
    result = check_dispatch_outcome_bindings(connection)
    assert result.passed is passed


def _drop_integrity_guards(connection: sqlite3.Connection) -> list[tuple[str, str]]:
    triggers = connection.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type = 'trigger' AND sql IS NOT NULL"
    ).fetchall()
    for name, _ in triggers:
        connection.execute(f'DROP TRIGGER "{name}"')
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("PRAGMA ignore_check_constraints = ON")
    return [(str(name), str(sql)) for name, sql in triggers]


def _restore_integrity_guards(
    connection: sqlite3.Connection, triggers: list[tuple[str, str]]
) -> None:
    connection.execute("PRAGMA ignore_check_constraints = OFF")
    connection.execute("PRAGMA foreign_keys = ON")
    for _, sql in triggers:
        connection.execute(sql)


def _refresh_transition_fingerprints(connection: sqlite3.Connection) -> None:
    for row in connection.execute("SELECT * FROM execution_transitions").fetchall():
        record = _transition_from_row(row)
        connection.execute(
            "UPDATE execution_transitions SET record_fingerprint = ? "
            "WHERE transition_record_id = ?",
            (record.record_fingerprint, record.transition_record_id),
        )


def _assert_public_startup_rejects(tmp_path) -> None:
    reopened = _connection(tmp_path)
    with pytest.raises(SqliteExecutionSchemaError):
        SqliteExecutionPersistence(reopened)
    reopened.close()


def test_logically_reordered_acknowledgement_chain_fails_public_startup(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)
    result = ControlledPaperSubmissionService(
        persistence,
        lambda order: PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        ),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    assert result.reason_code == "ACK"
    triggers = _drop_integrity_guards(connection)
    connection.executescript("""
        UPDATE execution_transitions
           SET transition_record_id = 'temporary-transition-record',
               transition_id = 'TEMPORARY-TRANSITION',
               previous_revision = 98,
               next_revision = 99
         WHERE transition_id = 'PX-TRN-009';
        UPDATE execution_transitions
           SET transition_record_id = (
                   SELECT claim_token || '-PX-TRN-009'
                     FROM execution_dispatch_claims
               ),
               transition_id = 'PX-TRN-009',
               lifecycle_input_kind = 'RECORD_DISPATCH',
               source_state = 'DISPATCH_PENDING',
               destination_state = 'DISPATCHED',
               previous_revision = 1,
               next_revision = 2
         WHERE transition_id = 'PX-TRN-010';
        UPDATE execution_transitions
           SET transition_record_id = (
                   SELECT claim_token || '-PX-TRN-010'
                     FROM execution_dispatch_claims
               ),
               transition_id = 'PX-TRN-010',
               lifecycle_input_kind = 'OBSERVE_BROKER_ACKNOWLEDGEMENT',
               source_state = 'DISPATCHED',
               destination_state = 'BROKER_ACKNOWLEDGED',
               previous_revision = 0,
               next_revision = 1
         WHERE transition_id = 'TEMPORARY-TRANSITION';
        """)
    _refresh_transition_fingerprints(connection)
    _restore_integrity_guards(connection, triggers)
    connection.close()
    _assert_public_startup_rejects(tmp_path)


def test_canonical_schema_rejects_duplicate_transition_record_identity(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)
    ControlledPaperSubmissionService(
        persistence,
        lambda order: PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        ),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    with pytest.raises(
        sqlite3.IntegrityError,
        match="execution_transitions.transition_record_id",
    ):
        connection.execute("""
            INSERT INTO execution_transitions
            SELECT transition_record_id, aggregate_id,
                   'PX-TRN-DUPLICATE-RECORD-ID', source_state,
                   destination_state, 2, 3, lifecycle_input_kind,
                   input_identity || '-duplicate-record', command_id,
                   correlation_id, idempotency_key,
                   broker_observation_identity, receipt_fingerprint,
                   failure_fingerprint, replay_indicator,
                   side_effect_intent_kinds_json, evidence_intent_kinds_json,
                   safe_reason_code, mode, recorded_at, schema_version,
                   record_fingerprint
              FROM execution_transitions WHERE next_revision = 1
            """)
    connection.close()


def test_canonical_schema_rejects_duplicate_aggregate_revision_identity(
    tmp_path,
) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)
    ControlledPaperSubmissionService(
        persistence,
        lambda order: PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        ),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    with pytest.raises(
        sqlite3.IntegrityError,
        match="execution_transitions.aggregate_id, execution_transitions.next_revision",
    ):
        connection.execute("""
            INSERT INTO execution_transitions
            SELECT transition_record_id || '-duplicate-revision', aggregate_id,
                   'PX-TRN-DUPLICATE-REVISION', source_state, destination_state,
                   previous_revision, next_revision, lifecycle_input_kind,
                   input_identity, command_id, correlation_id, idempotency_key,
                   broker_observation_identity, receipt_fingerprint,
                   failure_fingerprint, replay_indicator,
                   side_effect_intent_kinds_json, evidence_intent_kinds_json,
                   safe_reason_code, mode, recorded_at, schema_version,
                   record_fingerprint
              FROM execution_transitions WHERE next_revision = 1
            """)
    connection.close()


def test_logically_duplicated_protocol_edge_fails_public_startup(tmp_path) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)
    ControlledPaperSubmissionService(
        persistence,
        lambda order: PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        ),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    triggers = _drop_integrity_guards(connection)
    connection.executescript("""
        INSERT INTO execution_transitions
        SELECT transition_record_id || '-duplicate-protocol', aggregate_id,
               'PX-TRN-DUPLICATE-PROTOCOL', source_state, destination_state,
               next_revision, next_revision + 1, lifecycle_input_kind,
               input_identity || '-duplicate', command_id, correlation_id,
               idempotency_key, broker_observation_identity,
               receipt_fingerprint, failure_fingerprint, replay_indicator,
               side_effect_intent_kinds_json, evidence_intent_kinds_json,
               safe_reason_code, mode, recorded_at, schema_version,
               record_fingerprint
          FROM execution_transitions WHERE next_revision = 2;
        UPDATE execution_aggregates
           SET execution_revision = 3,
               last_transition_id = 'PX-TRN-DUPLICATE-PROTOCOL';
        """)
    _refresh_transition_fingerprints(connection)
    _restore_integrity_guards(connection, triggers)
    connection.close()
    _assert_public_startup_rejects(tmp_path)


def _seed_broker_reference_conflict(connection: sqlite3.Connection):
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)
    reference = PaperBrokerOrderReference("pbr-" + "5" * 64)
    owner_aggregate = _aggregate("MSFT")
    owner_command = _command("MSFT")
    forged_aggregate = _aggregate("NVDA")
    forged_command = _command("NVDA")
    owner = ExecutionBrokerReferenceRecord(
        reference,
        owner_aggregate.aggregate_id,
        owner_command.command_id,
        "pre-existing-owner",
        ExecutionBrokerReferenceStatus.ACTIVE,
        DISPATCH_NOW,
        DISPATCH_NOW,
        True,
        4,
    )
    with persistence.unit_of_work() as unit:
        for aggregate, command in (
            (owner_aggregate, owner_command),
            (forged_aggregate, forged_command),
        ):
            unit.aggregates.save(
                aggregate, expected_revision=aggregate.execution_revision
            )
            unit.commands.register(command)
        assert (
            unit.broker_references.register(owner).status
            is ExecutionPersistenceResultStatus.CREATED
        )
        assert unit.commit().committed
    result = ControlledPaperSubmissionService(
        persistence,
        lambda order: PaperDispatchObservation(
            request.submission_id, reference, True, "ACK"
        ),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    assert result.reason_code == "BROKER_REFERENCE_OWNERSHIP_CONFLICT"
    return request, owner_aggregate, owner_command, forged_aggregate, forged_command


def _refresh_broker_reference_fingerprint(connection: sqlite3.Connection) -> None:
    row = connection.execute("SELECT * FROM execution_broker_references").fetchone()
    record = _broker_reference_from_row(row)
    connection.execute(
        "UPDATE execution_broker_references SET record_fingerprint = ?",
        (record.record_fingerprint,),
    )


@pytest.mark.parametrize(
    "mutation",
    (
        """UPDATE execution_dispatch_resolutions
              SET conflicting_owner_aggregate_id = NULL,
                  conflicting_owner_command_id = NULL,
                  conflicting_owner_record_fingerprint = NULL""",
        """UPDATE execution_dispatch_resolutions
              SET conflicting_owner_command_id = NULL""",
        """UPDATE execution_dispatch_resolutions
              SET conflicting_owner_aggregate_id = (
                      SELECT aggregate_id FROM execution_aggregates
                       WHERE aggregate_id <> conflicting_owner_aggregate_id
                       ORDER BY aggregate_id LIMIT 1
                  ),
                  conflicting_owner_command_id = (
                      SELECT command_id FROM execution_commands
                       WHERE command_id <> conflicting_owner_command_id
                       ORDER BY command_id LIMIT 1
                  )""",
        """UPDATE execution_dispatch_resolutions
              SET conflicting_owner_record_fingerprint = 'pbf-' || printf('%064d', 9)""",
    ),
)
def test_relational_owner_binding_rejects_invalid_conflict_tuple(
    tmp_path, mutation
) -> None:
    connection = _connection(tmp_path)
    _seed_broker_reference_conflict(connection)
    stored = connection.execute(
        "SELECT r.broker_reference, r.conflicting_owner_aggregate_id, "
        "r.conflicting_owner_command_id, r.conflicting_owner_record_fingerprint "
        "FROM execution_dispatch_resolutions AS r "
        "JOIN execution_broker_references AS b "
        "ON (b.broker_reference, b.aggregate_id, b.command_id, b.record_fingerprint) "
        "= (r.broker_reference, r.conflicting_owner_aggregate_id, "
        "r.conflicting_owner_command_id, r.conflicting_owner_record_fingerprint)"
    ).fetchone()
    assert stored is not None
    connection.execute("DROP TRIGGER trg_execution_dispatch_resolutions_no_update")
    with pytest.raises(sqlite3.IntegrityError):
        connection.executescript(mutation)
    connection.close()


@pytest.mark.parametrize(
    "ownership_case",
    (
        "missing",
        "same-owner",
        "aggregate-only-mismatch",
        "command-only-mismatch",
        "altered-owner-record-fingerprint",
        "fully-forged-different-owner",
    ),
)
def test_corrupt_broker_reference_ownership_fails_public_startup(
    tmp_path, ownership_case
) -> None:
    connection = _connection(tmp_path)
    (
        request,
        owner_aggregate,
        owner_command,
        forged_aggregate,
        forged_command,
    ) = _seed_broker_reference_conflict(connection)
    claimant = connection.execute(
        "SELECT aggregate_id, command_id FROM execution_dispatch_claims"
    ).fetchone()
    claimant_aggregate_id, claimant_command_id = tuple(claimant)
    triggers = _drop_integrity_guards(connection)
    if ownership_case == "missing":
        connection.execute("DELETE FROM execution_broker_references")
    else:
        if ownership_case == "altered-owner-record-fingerprint":
            connection.execute(
                "UPDATE execution_broker_references "
                "SET adapter_identity = 'corrupted-owner-adapter'"
            )
            _refresh_broker_reference_fingerprint(connection)
            aggregate_id = command_id = None
        elif ownership_case == "same-owner":
            aggregate_id, command_id = claimant_aggregate_id, claimant_command_id
        elif ownership_case == "aggregate-only-mismatch":
            aggregate_id, command_id = owner_aggregate.aggregate_id, claimant_command_id
        elif ownership_case == "command-only-mismatch":
            aggregate_id, command_id = claimant_aggregate_id, owner_command.command_id
        else:
            aggregate_id, command_id = (
                forged_aggregate.aggregate_id,
                forged_command.command_id,
            )
        if aggregate_id is not None and command_id is not None:
            connection.execute(
                "UPDATE execution_broker_references "
                "SET aggregate_id = ?, command_id = ?",
                (str(aggregate_id), str(command_id)),
            )
            _refresh_broker_reference_fingerprint(connection)
    _restore_integrity_guards(connection, triggers)
    connection.close()
    _assert_public_startup_rejects(tmp_path)


@pytest.mark.parametrize(
    "mutation",
    (
        "DELETE FROM execution_transitions WHERE next_revision = 1",
        "DELETE FROM execution_transitions WHERE next_revision = 2",
        "UPDATE execution_transitions SET recorded_at = '2026-08-13T00:00:00.000000Z' WHERE next_revision = 2",
        """UPDATE execution_transitions
              SET transition_record_id = transition_record_id || '-duplicate',
                  record_fingerprint = (
                      SELECT record_fingerprint FROM execution_transitions
                       WHERE next_revision = 1
                  )
            WHERE next_revision = 2""",
        "UPDATE execution_transitions SET previous_revision = 2, next_revision = 3 WHERE next_revision = 2",
        """INSERT INTO execution_transitions
               SELECT transition_record_id || '-surplus', aggregate_id, 'PX-TRN-011',
                      destination_state, destination_state, next_revision,
                      next_revision + 1, lifecycle_input_kind, input_identity,
                      command_id, correlation_id, idempotency_key,
                      broker_observation_identity, receipt_fingerprint,
                      failure_fingerprint, replay_indicator,
                      side_effect_intent_kinds_json, evidence_intent_kinds_json,
                      safe_reason_code, mode, recorded_at, schema_version,
                      record_fingerprint || '-surplus'
                 FROM execution_transitions WHERE next_revision = 2;
           UPDATE execution_aggregates
              SET execution_revision = 3, last_transition_id = 'PX-TRN-011'""",
        "UPDATE execution_transitions SET source_state = 'READY_FOR_DISPATCH' WHERE next_revision = 1",
        "UPDATE execution_transitions SET destination_state = 'OUTCOME_UNKNOWN' WHERE next_revision = 2",
        "UPDATE execution_transitions SET previous_revision = 7 WHERE next_revision = 2",
        "UPDATE execution_transitions SET lifecycle_input_kind = 'OBSERVE_BROKER_REJECTION' WHERE next_revision = 2",
        "UPDATE execution_transitions SET command_id = 'pec-' || printf('%064d', 9) WHERE next_revision = 2",
        "UPDATE execution_transitions SET correlation_id = 'pcr-' || printf('%064d', 9) WHERE next_revision = 2",
        "UPDATE execution_transitions SET idempotency_key = 'pik-' || printf('%064d', 9) WHERE next_revision = 2",
        "UPDATE execution_transitions SET receipt_fingerprint = NULL WHERE next_revision = 2",
        "UPDATE execution_aggregates SET execution_revision = 3",
        "UPDATE execution_aggregates SET lifecycle_state = 'OUTCOME_UNKNOWN'",
        "UPDATE execution_aggregates SET last_transition_id = 'PX-TRN-009'",
        "DELETE FROM execution_dispatch_authorizations",
        "UPDATE execution_dispatch_authorizations SET control_generation = 99",
        "UPDATE execution_dispatch_claims SET client_order_id = 'paper-' || printf('%042d', 8)",
        "DELETE FROM execution_receipts",
        "UPDATE execution_receipts SET aggregate_id = 'pea-' || printf('%064d', 8)",
        "UPDATE execution_dispatch_resolutions SET resolution_status = 'BROKER_REJECTED'",
        "UPDATE execution_dispatch_resolutions SET resolution_status = 'PRE_EFFECT_BLOCKED'",
        "DELETE FROM execution_dispatch_resolutions",
        """UPDATE execution_dispatch_resolutions
              SET resolution_status = 'BROKER_REFERENCE_CONFLICT';
           DELETE FROM execution_broker_references""",
        """UPDATE execution_dispatch_resolutions
              SET resolution_status = 'BROKER_REFERENCE_CONFLICT';
           UPDATE execution_broker_references
              SET aggregate_id = (SELECT aggregate_id FROM execution_dispatch_claims)""",
        """UPDATE execution_dispatch_resolutions
              SET resolution_status = 'BROKER_REFERENCE_CONFLICT';
           UPDATE execution_broker_references
              SET command_id = 'pec-' || printf('%064d', 9)""",
    ),
)
def test_real_startup_rejects_resolved_outcome_corruption_matrix(
    tmp_path, mutation
) -> None:
    connection = _connection(tmp_path)
    persistence = SqliteExecutionPersistence(connection)
    request = _seed_dispatch_authority(persistence)
    result = ControlledPaperSubmissionService(
        persistence,
        lambda order: PaperDispatchObservation(
            request.submission_id,
            PaperBrokerOrderReference("pbr-" + "5" * 64),
            True,
            "ACK",
        ),
        clock=lambda: DISPATCH_NOW,
    ).apply_once(request)
    assert result.reason_code == "ACK"
    triggers = connection.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type = 'trigger' AND sql IS NOT NULL"
    ).fetchall()
    for name, _ in triggers:
        connection.execute(f'DROP TRIGGER "{name}"')
    connection.execute("PRAGMA foreign_keys = OFF")
    connection.execute("PRAGMA ignore_check_constraints = ON")
    connection.executescript(mutation)
    connection.execute("PRAGMA ignore_check_constraints = OFF")
    connection.execute("PRAGMA foreign_keys = ON")
    for _, sql in triggers:
        connection.execute(sql)
    connection.close()
    reopened = _connection(tmp_path)
    with pytest.raises(SqliteExecutionSchemaError):
        SqliteExecutionPersistence(reopened)
    reopened.close()
