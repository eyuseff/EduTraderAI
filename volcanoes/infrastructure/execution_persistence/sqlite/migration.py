"""SQLite migration descriptors and explicit migration runner."""

from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionMigrationError,
    SqliteExecutionSchemaError,
)
from volcanoes.infrastructure.execution_persistence.sqlite.schema import (
    load_initial_schema_sql,
)

CURRENT_SCHEMA_VERSION = 1
MINIMUM_SUPPORTED_SCHEMA_VERSION = 1
MAXIMUM_SUPPORTED_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SqliteExecutionMigration:
    """Immutable SQLite execution persistence migration descriptor."""

    migration_id: str
    name: str
    previous_version: int
    resulting_version: int
    sql_text: str
    checksum: str
    irreversible: bool
    safe_description: str

    @classmethod
    def create(
        cls,
        *,
        migration_id: str,
        name: str,
        previous_version: int,
        resulting_version: int,
        sql_text: str,
        irreversible: bool,
        safe_description: str,
    ) -> "SqliteExecutionMigration":
        return cls(
            migration_id=migration_id,
            name=name,
            previous_version=previous_version,
            resulting_version=resulting_version,
            sql_text=_canonical_sql(sql_text),
            checksum=checksum_sql(sql_text),
            irreversible=irreversible,
            safe_description=safe_description,
        )


@dataclass(frozen=True, slots=True)
class AppliedMigration:
    """One applied SQLite execution persistence migration."""

    migration_id: str
    migration_name: str
    checksum: str
    application_version: str
    previous_schema_version: int
    resulting_schema_version: int


@dataclass(frozen=True, slots=True)
class SchemaState:
    """Observed SQLite execution schema state."""

    schema_table_exists: bool
    applied_migrations: tuple[AppliedMigration, ...]
    current_version: int | None
    empty_database: bool
    unknown_migration_ids: tuple[str, ...]
    incompatible_reason: str | None = None


@dataclass(frozen=True, slots=True)
class MigrationApplicationResult:
    """Result of an explicit migration application."""

    applied_migration_ids: tuple[str, ...]
    schema_state: SchemaState
    changed: bool


def checksum_sql(sql_text: str) -> str:
    """Return a deterministic SHA-256 checksum for canonical SQL text."""

    return hashlib.sha256(_canonical_sql(sql_text).encode("utf-8")).hexdigest()


def inspect_schema_state(
    connection: sqlite3.Connection,
    *,
    known_migrations: tuple[SqliteExecutionMigration, ...] = (),
) -> SchemaState:
    """Inspect applied schema migrations without mutating the database."""

    table_count = int(
        connection.execute(
            "SELECT count(*) FROM sqlite_master WHERE type = 'table'"
        ).fetchone()[0]
    )
    schema_table_exists = _object_exists(connection, "table", "schema_migrations")
    if not schema_table_exists:
        return SchemaState(
            schema_table_exists=False,
            applied_migrations=(),
            current_version=None,
            empty_database=table_count == 0,
            unknown_migration_ids=(),
            incompatible_reason=(
                None if table_count == 0 else "missing migrations table"
            ),
        )

    rows = connection.execute("""
        SELECT migration_id,
               migration_name,
               checksum,
               application_version,
               previous_schema_version,
               resulting_schema_version
        FROM schema_migrations
        ORDER BY resulting_schema_version, migration_id
        """).fetchall()
    applied = tuple(
        AppliedMigration(
            migration_id=str(row["migration_id"]),
            migration_name=str(row["migration_name"]),
            checksum=str(row["checksum"]),
            application_version=str(row["application_version"]),
            previous_schema_version=int(row["previous_schema_version"]),
            resulting_schema_version=int(row["resulting_schema_version"]),
        )
        for row in rows
    )
    known_ids = {migration.migration_id for migration in known_migrations}
    unknown_ids = tuple(
        migration.migration_id
        for migration in applied
        if known_ids and migration.migration_id not in known_ids
    )
    current_version = (
        max(migration.resulting_schema_version for migration in applied)
        if applied
        else None
    )
    incompatible_reason = None
    if (
        current_version is not None
        and current_version > MAXIMUM_SUPPORTED_SCHEMA_VERSION
    ):
        incompatible_reason = "unknown newer schema"
    elif unknown_ids:
        incompatible_reason = "unknown migration id"

    return SchemaState(
        schema_table_exists=True,
        applied_migrations=applied,
        current_version=current_version,
        empty_database=False,
        unknown_migration_ids=unknown_ids,
        incompatible_reason=incompatible_reason,
    )


def apply_pending_migrations(
    connection: sqlite3.Connection,
    migrations: tuple[SqliteExecutionMigration, ...],
    *,
    applied_at: datetime,
    application_version: str,
) -> MigrationApplicationResult:
    """Explicitly apply pending migrations to the supplied connection."""

    if not migrations:
        raise SqliteExecutionMigrationError("No migrations were supplied.")
    if applied_at.tzinfo is None:
        raise SqliteExecutionMigrationError(
            "Migration timestamp must be timezone-aware."
        )
    if not application_version:
        raise SqliteExecutionMigrationError("Application version is required.")

    ordered = tuple(sorted(migrations, key=lambda item: item.resulting_version))
    _validate_migration_descriptors(ordered)
    state = inspect_schema_state(connection, known_migrations=ordered)
    if state.incompatible_reason:
        raise SqliteExecutionSchemaError(state.incompatible_reason)

    applied_by_id = {item.migration_id: item for item in state.applied_migrations}
    applied_ids: list[str] = []
    for migration in ordered:
        existing = applied_by_id.get(migration.migration_id)
        if existing is not None:
            if existing.checksum != migration.checksum:
                raise SqliteExecutionMigrationError(
                    "Migration checksum mismatch for applied migration."
                )
            continue
        if state.current_version is None:
            expected_previous = 0
        else:
            expected_previous = state.current_version
        if migration.previous_version != expected_previous:
            raise SqliteExecutionMigrationError("Migration ordering is invalid.")

        _apply_one_migration(
            connection,
            migration,
            applied_at=applied_at,
            application_version=application_version,
        )
        applied_ids.append(migration.migration_id)
        state = inspect_schema_state(connection, known_migrations=ordered)
        if state.incompatible_reason:
            raise SqliteExecutionSchemaError(state.incompatible_reason)

    final_state = inspect_schema_state(connection, known_migrations=ordered)
    return MigrationApplicationResult(
        applied_migration_ids=tuple(applied_ids),
        schema_state=final_state,
        changed=bool(applied_ids),
    )


def format_utc_timestamp(value: datetime) -> str:
    """Format a timezone-aware datetime as canonical UTC text."""

    if value.tzinfo is None:
        raise SqliteExecutionMigrationError("Timestamp must be timezone-aware.")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _apply_one_migration(
    connection: sqlite3.Connection,
    migration: SqliteExecutionMigration,
    *,
    applied_at: datetime,
    application_version: str,
) -> None:
    script = "\n".join(
        (
            "BEGIN IMMEDIATE;",
            migration.sql_text,
            "INSERT INTO schema_migrations (",
            "migration_id, migration_name, checksum, applied_at, application_version,",
            "previous_schema_version, resulting_schema_version, safe_notes",
            ") VALUES (",
            ", ".join(
                (
                    _sql_literal(migration.migration_id),
                    _sql_literal(migration.name),
                    _sql_literal(migration.checksum),
                    _sql_literal(format_utc_timestamp(applied_at)),
                    _sql_literal(application_version),
                    str(migration.previous_version),
                    str(migration.resulting_version),
                    _sql_literal(migration.safe_description),
                )
            ),
            ");",
            "COMMIT;",
        )
    )
    try:
        connection.executescript(script)
    except sqlite3.Error as exc:
        try:
            connection.rollback()
        except sqlite3.Error:
            pass
        raise SqliteExecutionMigrationError("SQLite migration failed.") from exc


def _validate_migration_descriptors(
    migrations: tuple[SqliteExecutionMigration, ...],
) -> None:
    ids = [migration.migration_id for migration in migrations]
    if len(ids) != len(set(ids)):
        raise SqliteExecutionMigrationError("Migration IDs must be unique.")
    versions = [migration.resulting_version for migration in migrations]
    if versions != sorted(versions):
        raise SqliteExecutionMigrationError("Migrations must be ordered.")
    expected_previous = 0
    for migration in sorted(migrations, key=lambda item: item.resulting_version):
        if migration.previous_version != expected_previous:
            raise SqliteExecutionMigrationError(
                "Migration versions are not contiguous."
            )
        expected_previous = migration.resulting_version
        if checksum_sql(migration.sql_text) != migration.checksum:
            raise SqliteExecutionMigrationError("Migration checksum is not canonical.")


def _canonical_sql(sql_text: str) -> str:
    return sql_text.replace("\r\n", "\n").strip() + "\n"


def _object_exists(connection: sqlite3.Connection, object_type: str, name: str) -> bool:
    return (
        int(
            connection.execute(
                """
                SELECT count(*)
                FROM sqlite_master
                WHERE type = ? AND name = ?
                """,
                (object_type, name),
            ).fetchone()[0]
        )
        > 0
    )


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


INITIAL_MIGRATION = SqliteExecutionMigration.create(
    migration_id="v001",
    name="initial execution persistence schema",
    previous_version=0,
    resulting_version=1,
    sql_text=load_initial_schema_sql(),
    irreversible=True,
    safe_description="Initial SQLite execution persistence schema.",
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "INITIAL_MIGRATION",
    "MAXIMUM_SUPPORTED_SCHEMA_VERSION",
    "MINIMUM_SUPPORTED_SCHEMA_VERSION",
    "AppliedMigration",
    "MigrationApplicationResult",
    "SchemaState",
    "SqliteExecutionMigration",
    "apply_pending_migrations",
    "checksum_sql",
    "format_utc_timestamp",
    "inspect_schema_state",
]
