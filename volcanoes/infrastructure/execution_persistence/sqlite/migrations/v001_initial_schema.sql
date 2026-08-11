CREATE TABLE execution_aggregates (
    aggregate_id TEXT PRIMARY KEY,
    correlation_id TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL,
    execution_revision INTEGER NOT NULL CHECK (execution_revision >= 0),
    cumulative_filled_quantity TEXT NOT NULL CHECK (
        length(cumulative_filled_quantity) > 0
        AND cumulative_filled_quantity NOT GLOB '*[^0-9.-]*'
    ),
    requested_quantity TEXT CHECK (
        requested_quantity IS NULL
        OR (
            length(requested_quantity) > 0
            AND requested_quantity NOT GLOB '*[^0-9.-]*'
        )
    ),
    active_broker_reference TEXT,
    outcome_unknown INTEGER NOT NULL CHECK (outcome_unknown IN (0, 1)),
    reconciliation_required INTEGER NOT NULL CHECK (reconciliation_required IN (0, 1)),
    command_terminal INTEGER NOT NULL CHECK (command_terminal IN (0, 1)),
    aggregate_terminal INTEGER NOT NULL CHECK (aggregate_terminal IN (0, 1)),
    last_transition_id TEXT NOT NULL,
    last_command_id TEXT,
    last_idempotency_key TEXT,
    last_receipt_fingerprint TEXT,
    last_failure_fingerprint TEXT,
    mode TEXT NOT NULL CHECK (mode = 'PAPER'),
    created_at TEXT NOT NULL CHECK (
        length(created_at) = 27
        AND substr(created_at, 5, 1) = '-'
        AND substr(created_at, 8, 1) = '-'
        AND substr(created_at, 11, 1) = 'T'
        AND substr(created_at, 14, 1) = ':'
        AND substr(created_at, 17, 1) = ':'
        AND substr(created_at, 20, 1) = '.'
        AND substr(created_at, 27, 1) = 'Z'
    ),
    updated_at TEXT NOT NULL CHECK (
        length(updated_at) = 27
        AND substr(updated_at, 5, 1) = '-'
        AND substr(updated_at, 8, 1) = '-'
        AND substr(updated_at, 11, 1) = 'T'
        AND substr(updated_at, 14, 1) = ':'
        AND substr(updated_at, 17, 1) = ':'
        AND substr(updated_at, 20, 1) = '.'
        AND substr(updated_at, 27, 1) = 'Z'
    ),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    record_fingerprint TEXT NOT NULL,
    CHECK (outcome_unknown = 0 OR reconciliation_required = 1)
);

CREATE TABLE execution_commands (
    command_id TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL REFERENCES execution_aggregates(aggregate_id),
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (
        operation IN ('SUBMIT', 'CANCEL', 'REPLACE', 'RECONCILE', 'FAIL')
    ),
    expected_execution_revision INTEGER NOT NULL CHECK (
        expected_execution_revision >= 0
    ),
    canonical_payload_fingerprint TEXT NOT NULL,
    canonical_command_json TEXT NOT NULL,
    approval_fingerprint TEXT NOT NULL,
    policy_fingerprint TEXT NOT NULL,
    received_at TEXT NOT NULL CHECK (
        length(received_at) = 27
        AND substr(received_at, 5, 1) = '-'
        AND substr(received_at, 8, 1) = '-'
        AND substr(received_at, 11, 1) = 'T'
        AND substr(received_at, 14, 1) = ':'
        AND substr(received_at, 17, 1) = ':'
        AND substr(received_at, 20, 1) = '.'
        AND substr(received_at, 27, 1) = 'Z'
    ),
    processing_outcome TEXT NOT NULL CHECK (
        processing_outcome IN ('REGISTERED', 'REPLAY', 'CONFLICT', 'REJECTED')
    ),
    mode TEXT NOT NULL CHECK (mode = 'PAPER'),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    record_fingerprint TEXT NOT NULL,
    UNIQUE (command_id, canonical_payload_fingerprint)
);

CREATE TABLE execution_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    logical_operation_fingerprint TEXT NOT NULL,
    command_id TEXT NOT NULL REFERENCES execution_commands(command_id),
    aggregate_id TEXT NOT NULL REFERENCES execution_aggregates(aggregate_id),
    reservation_status TEXT NOT NULL CHECK (
        reservation_status IN ('RESERVED', 'RESOLVED', 'CONFLICT', 'UNKNOWN')
    ),
    original_result_fingerprint TEXT,
    created_at TEXT NOT NULL CHECK (
        length(created_at) = 27
        AND substr(created_at, 5, 1) = '-'
        AND substr(created_at, 8, 1) = '-'
        AND substr(created_at, 11, 1) = 'T'
        AND substr(created_at, 14, 1) = ':'
        AND substr(created_at, 17, 1) = ':'
        AND substr(created_at, 20, 1) = '.'
        AND substr(created_at, 27, 1) = 'Z'
    ),
    resolved_at TEXT CHECK (
        resolved_at IS NULL
        OR (
            length(resolved_at) = 27
            AND substr(resolved_at, 5, 1) = '-'
            AND substr(resolved_at, 8, 1) = '-'
            AND substr(resolved_at, 11, 1) = 'T'
            AND substr(resolved_at, 14, 1) = ':'
            AND substr(resolved_at, 17, 1) = ':'
            AND substr(resolved_at, 20, 1) = '.'
            AND substr(resolved_at, 27, 1) = 'Z'
        )
    ),
    conflict INTEGER NOT NULL CHECK (conflict IN (0, 1)),
    mode TEXT NOT NULL CHECK (mode = 'PAPER'),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    record_fingerprint TEXT NOT NULL,
    UNIQUE (idempotency_key, logical_operation_fingerprint)
);

CREATE TABLE execution_transitions (
    transition_record_id TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL REFERENCES execution_aggregates(aggregate_id),
    transition_id TEXT NOT NULL,
    source_state TEXT NOT NULL,
    destination_state TEXT NOT NULL,
    previous_revision INTEGER NOT NULL CHECK (previous_revision >= 0),
    next_revision INTEGER NOT NULL CHECK (
        next_revision = previous_revision + 1
    ),
    lifecycle_input_kind TEXT NOT NULL,
    input_identity TEXT NOT NULL,
    command_id TEXT NOT NULL REFERENCES execution_commands(command_id),
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL REFERENCES execution_idempotency(idempotency_key),
    broker_observation_identity TEXT,
    receipt_fingerprint TEXT,
    failure_fingerprint TEXT,
    replay_indicator TEXT NOT NULL CHECK (
        replay_indicator IN ('NOT_REPLAY', 'REPLAY_SUPPRESSED')
    ),
    side_effect_intent_kinds_json TEXT NOT NULL,
    evidence_intent_kinds_json TEXT NOT NULL,
    safe_reason_code TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode = 'PAPER'),
    recorded_at TEXT NOT NULL CHECK (
        length(recorded_at) = 27
        AND substr(recorded_at, 5, 1) = '-'
        AND substr(recorded_at, 8, 1) = '-'
        AND substr(recorded_at, 11, 1) = 'T'
        AND substr(recorded_at, 14, 1) = ':'
        AND substr(recorded_at, 17, 1) = ':'
        AND substr(recorded_at, 20, 1) = '.'
        AND substr(recorded_at, 27, 1) = 'Z'
    ),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    record_fingerprint TEXT NOT NULL,
    UNIQUE (aggregate_id, next_revision),
    UNIQUE (aggregate_id, transition_id)
);

CREATE TABLE execution_broker_references (
    broker_reference TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL REFERENCES execution_aggregates(aggregate_id),
    command_id TEXT NOT NULL REFERENCES execution_commands(command_id),
    adapter_identity TEXT NOT NULL,
    reference_status TEXT NOT NULL CHECK (
        reference_status IN ('ACTIVE', 'REPLACED', 'CANCELLED', 'TERMINAL')
    ),
    first_seen_at TEXT NOT NULL CHECK (
        length(first_seen_at) = 27
        AND substr(first_seen_at, 5, 1) = '-'
        AND substr(first_seen_at, 8, 1) = '-'
        AND substr(first_seen_at, 11, 1) = 'T'
        AND substr(first_seen_at, 14, 1) = ':'
        AND substr(first_seen_at, 17, 1) = ':'
        AND substr(first_seen_at, 20, 1) = '.'
        AND substr(first_seen_at, 27, 1) = 'Z'
    ),
    last_seen_at TEXT NOT NULL CHECK (
        length(last_seen_at) = 27
        AND substr(last_seen_at, 5, 1) = '-'
        AND substr(last_seen_at, 8, 1) = '-'
        AND substr(last_seen_at, 11, 1) = 'T'
        AND substr(last_seen_at, 14, 1) = ':'
        AND substr(last_seen_at, 17, 1) = ':'
        AND substr(last_seen_at, 20, 1) = '.'
        AND substr(last_seen_at, 27, 1) = 'Z'
    ),
    active INTEGER NOT NULL CHECK (active IN (0, 1)),
    replaced_by_reference TEXT,
    mode TEXT NOT NULL CHECK (mode = 'PAPER'),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    record_fingerprint TEXT NOT NULL
);

CREATE UNIQUE INDEX ux_execution_broker_references_active_aggregate
ON execution_broker_references(aggregate_id)
WHERE active = 1;

CREATE TABLE execution_receipts (
    receipt_fingerprint TEXT PRIMARY KEY,
    aggregate_id TEXT REFERENCES execution_aggregates(aggregate_id),
    command_id TEXT REFERENCES execution_commands(command_id),
    receipt_kind TEXT NOT NULL,
    broker_reference TEXT,
    safe_status TEXT NOT NULL,
    safe_message_code TEXT NOT NULL,
    recorded_at TEXT NOT NULL CHECK (
        length(recorded_at) = 27
        AND substr(recorded_at, 5, 1) = '-'
        AND substr(recorded_at, 8, 1) = '-'
        AND substr(recorded_at, 11, 1) = 'T'
        AND substr(recorded_at, 14, 1) = ':'
        AND substr(recorded_at, 17, 1) = ':'
        AND substr(recorded_at, 20, 1) = '.'
        AND substr(recorded_at, 27, 1) = 'Z'
    ),
    mode TEXT NOT NULL CHECK (mode = 'PAPER'),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    record_fingerprint TEXT NOT NULL UNIQUE
);

CREATE TABLE execution_failures (
    failure_fingerprint TEXT PRIMARY KEY,
    aggregate_id TEXT REFERENCES execution_aggregates(aggregate_id),
    command_id TEXT REFERENCES execution_commands(command_id),
    failure_kind TEXT NOT NULL,
    severity TEXT NOT NULL,
    retryable INTEGER NOT NULL CHECK (retryable IN (0, 1)),
    terminal INTEGER NOT NULL CHECK (terminal IN (0, 1)),
    reconciliation_required INTEGER NOT NULL CHECK (reconciliation_required IN (0, 1)),
    safe_message_code TEXT NOT NULL,
    recorded_at TEXT NOT NULL CHECK (
        length(recorded_at) = 27
        AND substr(recorded_at, 5, 1) = '-'
        AND substr(recorded_at, 8, 1) = '-'
        AND substr(recorded_at, 11, 1) = 'T'
        AND substr(recorded_at, 14, 1) = ':'
        AND substr(recorded_at, 17, 1) = ':'
        AND substr(recorded_at, 20, 1) = '.'
        AND substr(recorded_at, 27, 1) = 'Z'
    ),
    mode TEXT NOT NULL CHECK (mode = 'PAPER'),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    record_fingerprint TEXT NOT NULL UNIQUE
);

CREATE TABLE execution_approvals (
    approval_fingerprint TEXT PRIMARY KEY,
    bound_fingerprint TEXT NOT NULL,
    approval_kind TEXT NOT NULL,
    approver_safe_reference TEXT NOT NULL,
    approved_at TEXT NOT NULL CHECK (
        length(approved_at) = 27
        AND substr(approved_at, 5, 1) = '-'
        AND substr(approved_at, 8, 1) = '-'
        AND substr(approved_at, 11, 1) = 'T'
        AND substr(approved_at, 14, 1) = ':'
        AND substr(approved_at, 17, 1) = ':'
        AND substr(approved_at, 20, 1) = '.'
        AND substr(approved_at, 27, 1) = 'Z'
    ),
    expires_at TEXT CHECK (
        expires_at IS NULL
        OR (
            length(expires_at) = 27
            AND substr(expires_at, 5, 1) = '-'
            AND substr(expires_at, 8, 1) = '-'
            AND substr(expires_at, 11, 1) = 'T'
            AND substr(expires_at, 14, 1) = ':'
            AND substr(expires_at, 17, 1) = ':'
            AND substr(expires_at, 20, 1) = '.'
            AND substr(expires_at, 27, 1) = 'Z'
        )
    ),
    revocation_reference TEXT,
    recorded_at TEXT NOT NULL CHECK (
        length(recorded_at) = 27
        AND substr(recorded_at, 5, 1) = '-'
        AND substr(recorded_at, 8, 1) = '-'
        AND substr(recorded_at, 11, 1) = 'T'
        AND substr(recorded_at, 14, 1) = ':'
        AND substr(recorded_at, 17, 1) = ':'
        AND substr(recorded_at, 20, 1) = '.'
        AND substr(recorded_at, 27, 1) = 'Z'
    ),
    mode TEXT NOT NULL CHECK (mode = 'PAPER'),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    record_fingerprint TEXT NOT NULL UNIQUE
);

CREATE TABLE execution_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL REFERENCES execution_aggregates(aggregate_id),
    starting_local_revision INTEGER NOT NULL CHECK (starting_local_revision >= 0),
    starting_lifecycle_state TEXT NOT NULL,
    broker_observation_references_json TEXT NOT NULL,
    result_classification TEXT NOT NULL,
    resulting_transition_id TEXT,
    resulting_revision INTEGER CHECK (
        resulting_revision IS NULL OR resulting_revision >= starting_local_revision
    ),
    operator_action_required INTEGER NOT NULL CHECK (operator_action_required IN (0, 1)),
    unresolved INTEGER NOT NULL CHECK (unresolved IN (0, 1)),
    safe_reason_code TEXT NOT NULL,
    recorded_at TEXT NOT NULL CHECK (
        length(recorded_at) = 27
        AND substr(recorded_at, 5, 1) = '-'
        AND substr(recorded_at, 8, 1) = '-'
        AND substr(recorded_at, 11, 1) = 'T'
        AND substr(recorded_at, 14, 1) = ':'
        AND substr(recorded_at, 17, 1) = ':'
        AND substr(recorded_at, 20, 1) = '.'
        AND substr(recorded_at, 27, 1) = 'Z'
    ),
    mode TEXT NOT NULL CHECK (mode = 'PAPER'),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    record_fingerprint TEXT NOT NULL UNIQUE
);

CREATE TABLE schema_migrations (
    migration_id TEXT PRIMARY KEY,
    migration_name TEXT NOT NULL,
    checksum TEXT NOT NULL,
    applied_at TEXT NOT NULL CHECK (
        length(applied_at) = 27
        AND substr(applied_at, 5, 1) = '-'
        AND substr(applied_at, 8, 1) = '-'
        AND substr(applied_at, 11, 1) = 'T'
        AND substr(applied_at, 14, 1) = ':'
        AND substr(applied_at, 17, 1) = ':'
        AND substr(applied_at, 20, 1) = '.'
        AND substr(applied_at, 27, 1) = 'Z'
    ),
    application_version TEXT NOT NULL,
    previous_schema_version INTEGER NOT NULL CHECK (previous_schema_version >= 0),
    resulting_schema_version INTEGER NOT NULL CHECK (resulting_schema_version >= 1),
    safe_notes TEXT NOT NULL,
    UNIQUE (migration_id, checksum)
);

CREATE INDEX idx_execution_aggregates_lifecycle_state
ON execution_aggregates(lifecycle_state);

CREATE INDEX idx_execution_aggregates_consequential_state
ON execution_aggregates(outcome_unknown, reconciliation_required);

CREATE INDEX idx_execution_aggregates_updated_at
ON execution_aggregates(updated_at);

CREATE INDEX idx_execution_commands_aggregate_received
ON execution_commands(aggregate_id, received_at);

CREATE INDEX idx_execution_commands_idempotency_key
ON execution_commands(idempotency_key);

CREATE INDEX idx_execution_idempotency_aggregate
ON execution_idempotency(aggregate_id);

CREATE INDEX idx_execution_transitions_command
ON execution_transitions(command_id);

CREATE INDEX idx_execution_broker_references_aggregate_active
ON execution_broker_references(aggregate_id, active);

CREATE INDEX idx_execution_receipts_command_aggregate
ON execution_receipts(command_id, aggregate_id);

CREATE INDEX idx_execution_failures_command_aggregate
ON execution_failures(command_id, aggregate_id);

CREATE INDEX idx_execution_reconciliations_aggregate_unresolved
ON execution_reconciliations(aggregate_id, unresolved);

CREATE INDEX idx_schema_migrations_resulting_version
ON schema_migrations(resulting_schema_version);

CREATE TRIGGER trg_execution_commands_no_update
BEFORE UPDATE ON execution_commands
BEGIN
    SELECT RAISE(ABORT, 'execution_commands is immutable');
END;

CREATE TRIGGER trg_execution_commands_no_delete
BEFORE DELETE ON execution_commands
BEGIN
    SELECT RAISE(ABORT, 'execution_commands is immutable');
END;

CREATE TRIGGER trg_execution_transitions_no_update
BEFORE UPDATE ON execution_transitions
BEGIN
    SELECT RAISE(ABORT, 'execution_transitions is append-only');
END;

CREATE TRIGGER trg_execution_transitions_no_delete
BEFORE DELETE ON execution_transitions
BEGIN
    SELECT RAISE(ABORT, 'execution_transitions is append-only');
END;

CREATE TRIGGER trg_execution_receipts_no_update
BEFORE UPDATE ON execution_receipts
BEGIN
    SELECT RAISE(ABORT, 'execution_receipts is immutable');
END;

CREATE TRIGGER trg_execution_receipts_no_delete
BEFORE DELETE ON execution_receipts
BEGIN
    SELECT RAISE(ABORT, 'execution_receipts is immutable');
END;

CREATE TRIGGER trg_execution_failures_no_update
BEFORE UPDATE ON execution_failures
BEGIN
    SELECT RAISE(ABORT, 'execution_failures is immutable');
END;

CREATE TRIGGER trg_execution_failures_no_delete
BEFORE DELETE ON execution_failures
BEGIN
    SELECT RAISE(ABORT, 'execution_failures is immutable');
END;

CREATE TRIGGER trg_execution_approvals_no_update
BEFORE UPDATE ON execution_approvals
BEGIN
    SELECT RAISE(ABORT, 'execution_approvals is immutable');
END;

CREATE TRIGGER trg_execution_approvals_no_delete
BEFORE DELETE ON execution_approvals
BEGIN
    SELECT RAISE(ABORT, 'execution_approvals is immutable');
END;

CREATE TRIGGER trg_execution_reconciliations_no_update
BEFORE UPDATE ON execution_reconciliations
BEGIN
    SELECT RAISE(ABORT, 'execution_reconciliations is append-only');
END;

CREATE TRIGGER trg_execution_reconciliations_no_delete
BEFORE DELETE ON execution_reconciliations
BEGIN
    SELECT RAISE(ABORT, 'execution_reconciliations is append-only');
END;

CREATE TRIGGER trg_schema_migrations_no_update
BEFORE UPDATE ON schema_migrations
BEGIN
    SELECT RAISE(ABORT, 'schema_migrations is immutable');
END;

CREATE TRIGGER trg_schema_migrations_no_delete
BEFORE DELETE ON schema_migrations
BEGIN
    SELECT RAISE(ABORT, 'schema_migrations is immutable');
END;
