"""SQLite connection bootstrap for execution persistence foundation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from volcanoes.infrastructure.execution_persistence.sqlite.errors import (
    SqliteExecutionConfigurationError,
    SqliteExecutionConnectionError,
    SqliteExecutionPathError,
)

DEFAULT_BUSY_TIMEOUT_MS = 200
MAX_BUSY_TIMEOUT_MS = 60_000
FULL_SYNCHRONOUS_VALUE = 2

_PROTECTED_PATH_PARTS = frozenset({".git", "state", "build"})
_PROHIBITED_FILENAMES = frozenset({"simulated_broker.json"})


def validate_sqlite_execution_path(database_path: Path) -> Path:
    """Validate a caller-supplied SQLite path and return its absolute path."""

    path = Path(database_path)
    if not path.name:
        raise SqliteExecutionPathError("Database path must include a file name.")
    if path.name in _PROHIBITED_FILENAMES:
        raise SqliteExecutionPathError("Protected simulator state path is rejected.")
    if path.suffix.lower() not in {".db", ".sqlite", ".sqlite3"}:
        raise SqliteExecutionPathError("Database path must use a SQLite file suffix.")

    absolute = path if path.is_absolute() else Path.cwd() / path
    absolute = absolute.resolve(strict=False)
    parent = absolute.parent
    if not parent.exists():
        raise SqliteExecutionPathError("Database parent directory does not exist.")
    if not parent.is_dir():
        raise SqliteExecutionPathError("Database parent path is not a directory.")

    for candidate in (absolute, *absolute.parents):
        if candidate.exists() and candidate.is_symlink():
            raise SqliteExecutionPathError(
                "SQLite execution path must not use symlinks."
            )

    parts = set(absolute.parts)
    if parts.intersection(_PROTECTED_PATH_PARTS):
        raise SqliteExecutionPathError(
            "SQLite execution path uses a protected directory."
        )

    return absolute


def open_sqlite_execution_connection(
    database_path: Path,
    *,
    busy_timeout_ms: int = DEFAULT_BUSY_TIMEOUT_MS,
    read_only: bool = False,
) -> sqlite3.Connection:
    """Open a configured SQLite execution persistence connection."""

    if busy_timeout_ms <= 0 or busy_timeout_ms > MAX_BUSY_TIMEOUT_MS:
        raise SqliteExecutionConfigurationError("Busy timeout is outside safe bounds.")

    path = validate_sqlite_execution_path(database_path)
    if read_only and not path.exists():
        raise SqliteExecutionPathError("Read-only SQLite database does not exist.")

    try:
        if read_only:
            connection = sqlite3.connect(
                f"file:{path.as_posix()}?mode=ro",
                uri=True,
                isolation_level=None,
            )
        else:
            connection = sqlite3.connect(path, isolation_level=None)
    except sqlite3.Error as exc:
        raise SqliteExecutionConnectionError("SQLite connection failed.") from exc

    try:
        _configure_connection(
            connection,
            busy_timeout_ms=busy_timeout_ms,
            read_only=read_only,
        )
    except Exception:
        connection.close()
        raise

    return connection


def _configure_connection(
    connection: sqlite3.Connection,
    *,
    busy_timeout_ms: int,
    read_only: bool,
) -> None:
    connection.row_factory = sqlite3.Row
    try:
        connection.enable_load_extension(False)
    except (AttributeError, sqlite3.Error):
        pass

    try:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {busy_timeout_ms}")
        connection.execute("PRAGMA synchronous = FULL")
        if not read_only:
            journal_mode = str(
                connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            ).lower()
            if journal_mode != "wal":
                raise SqliteExecutionConfigurationError("WAL mode was not enabled.")

        _verify_connection_configuration(
            connection,
            busy_timeout_ms=busy_timeout_ms,
            require_wal=not read_only,
        )
    except sqlite3.Error as exc:
        raise SqliteExecutionConfigurationError(
            "SQLite connection configuration failed."
        ) from exc


def _verify_connection_configuration(
    connection: sqlite3.Connection,
    *,
    busy_timeout_ms: int,
    require_wal: bool,
) -> None:
    foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
    if foreign_keys != 1:
        raise SqliteExecutionConfigurationError("Foreign keys are not enabled.")

    synchronous = int(connection.execute("PRAGMA synchronous").fetchone()[0])
    if synchronous != FULL_SYNCHRONOUS_VALUE:
        raise SqliteExecutionConfigurationError("Synchronous FULL is not active.")

    configured_timeout = int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
    if configured_timeout != busy_timeout_ms:
        raise SqliteExecutionConfigurationError("Busy timeout verification failed.")

    if require_wal:
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0])
        if journal_mode.lower() != "wal":
            raise SqliteExecutionConfigurationError("WAL mode verification failed.")


__all__ = [
    "DEFAULT_BUSY_TIMEOUT_MS",
    "MAX_BUSY_TIMEOUT_MS",
    "open_sqlite_execution_connection",
    "validate_sqlite_execution_path",
]
