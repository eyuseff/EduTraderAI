"""Stable SQLite infrastructure errors for execution persistence foundation."""

from __future__ import annotations


class SqliteExecutionPersistenceError(RuntimeError):
    """Base class for SQLite execution persistence infrastructure errors."""

    safe_code = "SQLITE_EXECUTION_PERSISTENCE_ERROR"


class SqliteExecutionPathError(SqliteExecutionPersistenceError):
    """Database path is unsafe or unsupported."""

    safe_code = "SQLITE_EXECUTION_PATH_ERROR"


class SqliteExecutionConnectionError(SqliteExecutionPersistenceError):
    """SQLite connection could not be opened or configured safely."""

    safe_code = "SQLITE_EXECUTION_CONNECTION_ERROR"


class SqliteExecutionConfigurationError(SqliteExecutionPersistenceError):
    """SQLite connection configuration failed validation."""

    safe_code = "SQLITE_EXECUTION_CONFIGURATION_ERROR"


class SqliteExecutionSchemaError(SqliteExecutionPersistenceError):
    """SQLite schema state is missing, incompatible, or invalid."""

    safe_code = "SQLITE_EXECUTION_SCHEMA_ERROR"


class SqliteExecutionMigrationError(SqliteExecutionPersistenceError):
    """SQLite migration could not be applied safely."""

    safe_code = "SQLITE_EXECUTION_MIGRATION_ERROR"


class SqliteExecutionIntegrityError(SqliteExecutionPersistenceError):
    """SQLite integrity or invariant validation failed."""

    safe_code = "SQLITE_EXECUTION_INTEGRITY_ERROR"


class SqliteExecutionBusyError(SqliteExecutionPersistenceError):
    """SQLite lock or busy timeout prevented safe operation."""

    safe_code = "SQLITE_EXECUTION_BUSY"


class SqliteExecutionPermissionError(SqliteExecutionPersistenceError):
    """Filesystem permissions are insufficient for safe operation."""

    safe_code = "SQLITE_EXECUTION_PERMISSION_ERROR"


__all__ = [
    "SqliteExecutionBusyError",
    "SqliteExecutionConfigurationError",
    "SqliteExecutionConnectionError",
    "SqliteExecutionIntegrityError",
    "SqliteExecutionMigrationError",
    "SqliteExecutionPathError",
    "SqliteExecutionPermissionError",
    "SqliteExecutionPersistenceError",
    "SqliteExecutionSchemaError",
]
