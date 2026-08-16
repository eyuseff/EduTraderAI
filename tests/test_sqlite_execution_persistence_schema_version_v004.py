from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from volcanoes.infrastructure.execution_persistence.sqlite import (
    CURRENT_SCHEMA_VERSION,
    DURABLE_DISPATCH_CLAIM_MIGRATION,
    KNOWN_MIGRATIONS,
    apply_pending_migrations,
    open_sqlite_execution_connection,
)

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def migrated(tmp_path):
    connection = open_sqlite_execution_connection(tmp_path / "claims.sqlite")
    apply_pending_migrations(
        connection,
        KNOWN_MIGRATIONS,
        applied_at=NOW,
        application_version="f6a-v004-test",
    )
    return connection


def test_v004_record_schema_remains_current_while_v005_migration_is_registered() -> None:
    assert CURRENT_SCHEMA_VERSION == 4
    assert tuple(item.migration_id for item in KNOWN_MIGRATIONS) == (
        "v001",
        "v002",
        "v003",
        "v004",
        "v005",
    )
    assert DURABLE_DISPATCH_CLAIM_MIGRATION.previous_version == 3
    assert DURABLE_DISPATCH_CLAIM_MIGRATION.resulting_version == 4


def test_v004_creates_fail_closed_control_and_exact_objects(tmp_path) -> None:
    connection = migrated(tmp_path)
    try:
        row = connection.execute("SELECT * FROM execution_dispatch_controls").fetchone()
        assert (
            row["enabled"],
            row["paper_mode"],
            row["emergency_stop_active"],
            row["legacy_authority_active"],
            row["generation"],
        ) == (0, 1, 1, 1, 1)
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {
            "execution_dispatch_controls",
            "execution_dispatch_claims",
            "execution_dispatch_authorizations",
            "execution_dispatch_resolutions",
        }.issubset(names)
        owner_index = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='index' "
            "AND name='idx_execution_broker_references_exact_owner'"
        ).fetchone()
        assert owner_index is not None
        assert tuple(
            row["name"]
            for row in connection.execute(
                "PRAGMA index_info(idx_execution_broker_references_exact_owner)"
            )
        ) == (
            "broker_reference",
            "aggregate_id",
            "command_id",
            "record_fingerprint",
        )
        owner_foreign_key = sorted(
            (row["seq"], row["from"], row["to"])
            for row in connection.execute(
                "PRAGMA foreign_key_list(execution_dispatch_resolutions)"
            )
            if row["table"] == "execution_broker_references"
        )
        assert owner_foreign_key == [
            (0, "broker_reference", "broker_reference"),
            (1, "conflicting_owner_aggregate_id", "aggregate_id"),
            (2, "conflicting_owner_command_id", "command_id"),
            (3, "conflicting_owner_record_fingerprint", "record_fingerprint"),
        ]
    finally:
        connection.close()


def test_two_connections_have_one_immutable_claim_winner(tmp_path) -> None:
    first = migrated(tmp_path)
    first.execute(
        "INSERT INTO execution_aggregates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "aggregate-1",
            "correlation-1",
            "DISPATCH_PENDING",
            5,
            "0",
            "1",
            None,
            0,
            0,
            0,
            0,
            "PX-TRN-008",
            "command-1",
            "idempotency-1",
            None,
            None,
            "PAPER",
            "2026-08-14T00:00:00.000000Z",
            "2026-08-14T00:00:00.000000Z",
            "4",
            "aggregate-fp",
        ),
    )
    first.execute(
        "INSERT INTO execution_commands VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "command-1",
            "aggregate-1",
            "correlation-1",
            "idempotency-1",
            "SUBMIT",
            0,
            "pcf-" + "1" * 64,
            "{}",
            "pap-" + "2" * 64,
            "pps-" + "3" * 64,
            "2026-08-14T00:00:00.000000Z",
            "ACCEPTED",
            "PAPER",
            "4",
            "pcm-" + "4" * 64,
        ),
    )
    first.execute(
        "INSERT INTO execution_idempotency VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "idempotency-1",
            "pli-" + "5" * 64,
            "command-1",
            "aggregate-1",
            "RESERVED",
            None,
            "2026-08-14T00:00:00.000000Z",
            None,
            0,
            "PAPER",
            "4",
            "pir-" + "6" * 64,
        ),
    )
    first.commit()
    second = open_sqlite_execution_connection(tmp_path / "claims.sqlite")
    values = (
        "claim-1",
        "submission-1",
        "command-1",
        "aggregate-1",
        "correlation-1",
        "idempotency-1",
        5,
        "psq-" + "7" * 64,
        "pcm-" + "4" * 64,
        "pcf-" + "1" * 64,
        "pap-" + "2" * 64,
        "pps-" + "3" * 64,
        "c" * 48,
        "pcv-" + "9" * 64,
        "{}",
        1,
        "2026-08-14T00:00:00.000000Z",
        "PAPER",
        "4",
        "pcl-" + "8" * 64,
    )
    try:
        first.execute("BEGIN IMMEDIATE")
        first.execute(
            "INSERT INTO execution_dispatch_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            values,
        )
        first.commit()
        second.execute("BEGIN IMMEDIATE")
        try:
            second.execute(
                "INSERT INTO execution_dispatch_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                ("claim-2",) + values[1:],
            )
        except sqlite3.IntegrityError:
            second.rollback()
        assert (
            first.execute("SELECT count(*) FROM execution_dispatch_claims").fetchone()[
                0
            ]
            == 1
        )
    finally:
        first.close()
        second.close()


def test_unresolved_claim_has_no_expiry_or_takeover_columns(tmp_path) -> None:
    connection = migrated(tmp_path)
    try:
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(execution_dispatch_claims)"
            )
        }
        assert columns.isdisjoint(
            {"expires_at", "lease_until", "released_at", "retry_at"}
        )
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("verifier", "valid"),
    (
        ("pcv-" + "a" * 64, True),
        ("pcv-", False),
        ("pcv-" + "a" * 63, False),
        ("pcv-" + "a" * 65, False),
        ("pcv-" + "A" * 64, False),
        ("pcv-" + "a" * 63 + "!", False),
        ("pcv-" + "a" * 63 + "g", False),
    ),
)
def test_capability_verifier_sql_validation_is_exact(tmp_path, verifier, valid) -> None:
    connection = migrated(tmp_path)
    try:
        connection.execute("PRAGMA foreign_keys=OFF")
        values = (
            "claim-1",
            "submission-1",
            "command-1",
            "aggregate-1",
            "correlation-1",
            "idempotency-1",
            5,
            "request",
            "command-fp",
            "payload-fp",
            "approval-fp",
            "policy-fp",
            "c" * 48,
            verifier,
            "{}",
            1,
            "2026-08-14T00:00:00.000000Z",
            "PAPER",
            "4",
            "claim-fp",
        )
        if valid:
            connection.execute(
                "INSERT INTO execution_dispatch_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                values,
            )
        else:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "INSERT INTO execution_dispatch_claims VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    values,
                )
    finally:
        connection.close()


def test_control_generation_trigger_rejects_same_skipped_and_decreasing_values(
    tmp_path,
) -> None:
    connection = migrated(tmp_path)
    try:
        for generation in (1, 3, 0):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE execution_dispatch_controls SET generation=? WHERE control_id='PAPER_DISPATCH'",
                    (generation,),
                )
        connection.execute(
            "UPDATE execution_dispatch_controls SET emergency_stop_active=0, generation=2 WHERE control_id='PAPER_DISPATCH'"
        )
        connection.execute(
            "UPDATE execution_dispatch_controls SET emergency_stop_active=1, generation=3 WHERE control_id='PAPER_DISPATCH'"
        )
        assert (
            connection.execute(
                "SELECT generation FROM execution_dispatch_controls"
            ).fetchone()[0]
            == 3
        )
    finally:
        connection.close()
