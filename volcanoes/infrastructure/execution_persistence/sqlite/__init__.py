"""SQLite execution persistence schema and migration foundation.

This package exposes the durable foundation and its explicit unit-of-work
factory. It does not compose runtime behavior or make broker calls.
"""

from volcanoes.infrastructure.execution_persistence.sqlite.connection import (
    DEFAULT_BUSY_TIMEOUT_MS,
    open_sqlite_execution_connection,
    validate_sqlite_execution_path,
)
from volcanoes.infrastructure.execution_persistence.sqlite.integrity import (
    IntegrityCheckResult,
    InvariantCheckResult,
    check_aggregate_transition_revisions,
    check_broker_reference_ownership,
    check_foreign_keys,
    check_idempotency_bindings,
    run_integrity_check,
    run_quick_check,
)
from volcanoes.infrastructure.execution_persistence.sqlite.migration import (
    CONTRACT_ALIGNMENT_MIGRATION,
    DURABLE_DISPATCH_CLAIM_MIGRATION,
    CURRENT_SCHEMA_VERSION,
    MAXIMUM_SUPPORTED_SCHEMA_VERSION,
    MINIMUM_SUPPORTED_SCHEMA_VERSION,
    INITIAL_MIGRATION,
    KNOWN_MIGRATIONS,
    MigrationApplicationResult,
    SchemaState,
    SqliteExecutionMigration,
    SCHEMA_VERSION_TEXT_MIGRATION,
    apply_pending_migrations,
    inspect_schema_state,
)
from volcanoes.infrastructure.execution_persistence.sqlite.validation import (
    SchemaValidationResult,
    validate_sqlite_execution_schema,
)
from volcanoes.infrastructure.execution_persistence.sqlite.unit_of_work import (
    SqliteExecutionPersistence,
    SqliteExecutionUnitOfWork,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "CONTRACT_ALIGNMENT_MIGRATION",
    "DURABLE_DISPATCH_CLAIM_MIGRATION",
    "DEFAULT_BUSY_TIMEOUT_MS",
    "INITIAL_MIGRATION",
    "KNOWN_MIGRATIONS",
    "IntegrityCheckResult",
    "InvariantCheckResult",
    "MAXIMUM_SUPPORTED_SCHEMA_VERSION",
    "MINIMUM_SUPPORTED_SCHEMA_VERSION",
    "SCHEMA_VERSION_TEXT_MIGRATION",
    "MigrationApplicationResult",
    "SchemaState",
    "SchemaValidationResult",
    "SqliteExecutionMigration",
    "SqliteExecutionPersistence",
    "SqliteExecutionUnitOfWork",
    "apply_pending_migrations",
    "check_aggregate_transition_revisions",
    "check_broker_reference_ownership",
    "check_foreign_keys",
    "check_idempotency_bindings",
    "inspect_schema_state",
    "open_sqlite_execution_connection",
    "run_integrity_check",
    "run_quick_check",
    "validate_sqlite_execution_path",
    "validate_sqlite_execution_schema",
]
