PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_aggregates (
    aggregate_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    execution_revision INTEGER NOT NULL CHECK (execution_revision >= 0),
    cumulative_filled_quantity TEXT NOT NULL,
    outcome_unknown INTEGER NOT NULL CHECK (outcome_unknown IN (0, 1)),
    reconciliation_required INTEGER NOT NULL CHECK (reconciliation_required IN (0, 1)),
    command_terminal INTEGER NOT NULL CHECK (command_terminal IN (0, 1)),
    aggregate_terminal INTEGER NOT NULL CHECK (aggregate_terminal IN (0, 1)),
    last_transition_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    record_fingerprint TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS execution_commands (
    command_id TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    operation TEXT NOT NULL,
    expected_execution_revision INTEGER NOT NULL CHECK (expected_execution_revision >= 0),
    canonical_payload_fingerprint TEXT NOT NULL,
    logical_operation_fingerprint TEXT NOT NULL,
    canonical_command_json TEXT NOT NULL,
    approval_fingerprint TEXT NOT NULL,
    policy_fingerprint TEXT NOT NULL,
    received_at TEXT NOT NULL,
    processing_outcome TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    record_fingerprint TEXT NOT NULL UNIQUE,
    FOREIGN KEY (aggregate_id) REFERENCES execution_aggregates(aggregate_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS execution_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    logical_operation_fingerprint TEXT NOT NULL,
    command_id TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    reservation_status TEXT NOT NULL,
    original_result_fingerprint TEXT,
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    conflict INTEGER NOT NULL CHECK (conflict IN (0, 1)),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    record_fingerprint TEXT NOT NULL UNIQUE,
    FOREIGN KEY (aggregate_id) REFERENCES execution_aggregates(aggregate_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (command_id) REFERENCES execution_commands(command_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS execution_transitions (
    transition_record_id TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    transition_id TEXT NOT NULL,
    source_state TEXT NOT NULL,
    destination_state TEXT NOT NULL,
    previous_revision INTEGER NOT NULL CHECK (previous_revision >= 0),
    next_revision INTEGER NOT NULL CHECK (next_revision = previous_revision + 1),
    input_identity TEXT NOT NULL,
    command_id TEXT NOT NULL,
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    safe_reason_code TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    record_fingerprint TEXT NOT NULL UNIQUE,
    FOREIGN KEY (aggregate_id) REFERENCES execution_aggregates(aggregate_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (command_id) REFERENCES execution_commands(command_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS execution_broker_references (
    broker_reference TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    adapter_identity TEXT NOT NULL,
    reference_status TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    record_fingerprint TEXT NOT NULL UNIQUE,
    FOREIGN KEY (aggregate_id) REFERENCES execution_aggregates(aggregate_id) DEFERRABLE INITIALLY DEFERRED,
    FOREIGN KEY (command_id) REFERENCES execution_commands(command_id) DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE IF NOT EXISTS execution_receipts (
    receipt_fingerprint TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0)
);

CREATE TABLE IF NOT EXISTS execution_failures (
    failure_fingerprint TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    command_id TEXT NOT NULL,
    safe_code TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0)
);

CREATE TABLE IF NOT EXISTS execution_approvals (
    approval_fingerprint TEXT PRIMARY KEY,
    bound_fingerprint TEXT NOT NULL,
    approval_kind TEXT NOT NULL,
    approver_safe_reference TEXT NOT NULL,
    approved_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0)
);

CREATE TABLE IF NOT EXISTS execution_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    starting_local_revision INTEGER NOT NULL,
    starting_lifecycle_state TEXT NOT NULL,
    result_classification TEXT NOT NULL,
    operator_action_required INTEGER NOT NULL CHECK (operator_action_required IN (0, 1)),
    unresolved INTEGER NOT NULL CHECK (unresolved IN (0, 1)),
    safe_reason_code TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK (schema_version > 0),
    record_fingerprint TEXT NOT NULL UNIQUE,
    FOREIGN KEY (aggregate_id) REFERENCES execution_aggregates(aggregate_id) DEFERRABLE INITIALLY DEFERRED
);
