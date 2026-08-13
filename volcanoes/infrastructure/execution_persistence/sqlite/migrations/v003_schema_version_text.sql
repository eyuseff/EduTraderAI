-- V003 is an unregistered review candidate. The migration runner owns its transaction.

-- 1. Pre-copy guards.
CREATE TEMP TABLE _v003_guard (value INTEGER NOT NULL CHECK (value = 0));

INSERT INTO _v003_guard (value)
SELECT count(*) FROM execution_aggregates
WHERE typeof(schema_version) <> 'integer' OR schema_version < 1
   OR CAST(CAST(schema_version AS TEXT) AS INTEGER) <> schema_version;
INSERT INTO _v003_guard (value)
SELECT count(*) FROM execution_commands
WHERE typeof(schema_version) <> 'integer' OR schema_version < 1
   OR CAST(CAST(schema_version AS TEXT) AS INTEGER) <> schema_version;
INSERT INTO _v003_guard (value)
SELECT count(*) FROM execution_idempotency
WHERE typeof(schema_version) <> 'integer' OR schema_version < 1
   OR CAST(CAST(schema_version AS TEXT) AS INTEGER) <> schema_version;
INSERT INTO _v003_guard (value)
SELECT count(*) FROM execution_transitions
WHERE typeof(schema_version) <> 'integer' OR schema_version < 1
   OR CAST(CAST(schema_version AS TEXT) AS INTEGER) <> schema_version;
INSERT INTO _v003_guard (value)
SELECT count(*) FROM execution_broker_references
WHERE typeof(schema_version) <> 'integer' OR schema_version < 1
   OR CAST(CAST(schema_version AS TEXT) AS INTEGER) <> schema_version;
INSERT INTO _v003_guard (value)
SELECT count(*) FROM execution_receipts
WHERE typeof(schema_version) <> 'integer' OR schema_version < 1
   OR CAST(CAST(schema_version AS TEXT) AS INTEGER) <> schema_version;
INSERT INTO _v003_guard (value)
SELECT count(*) FROM execution_failures
WHERE typeof(schema_version) <> 'integer' OR schema_version < 1
   OR CAST(CAST(schema_version AS TEXT) AS INTEGER) <> schema_version;
INSERT INTO _v003_guard (value)
SELECT count(*) FROM execution_approvals
WHERE typeof(schema_version) <> 'integer' OR schema_version < 1
   OR CAST(CAST(schema_version AS TEXT) AS INTEGER) <> schema_version;
INSERT INTO _v003_guard (value)
SELECT count(*) FROM execution_reconciliations
WHERE typeof(schema_version) <> 'integer' OR schema_version < 1
   OR CAST(CAST(schema_version AS TEXT) AS INTEGER) <> schema_version;

-- Active connection preconditions for SQLite rename semantics.
INSERT INTO _v003_guard (value)
SELECT CASE
    WHEN COALESCE((SELECT foreign_keys FROM pragma_foreign_keys), -1) = 1
     AND COALESCE(
         (SELECT legacy_alter_table FROM pragma_legacy_alter_table), -1
     ) = 0
    THEN 0
    ELSE 1
END;

-- 2. Trigger removal. schema_migrations triggers are intentionally retained.
DROP TRIGGER trg_execution_commands_no_update;
DROP TRIGGER trg_execution_commands_no_delete;
DROP TRIGGER trg_execution_transitions_no_update;
DROP TRIGGER trg_execution_transitions_no_delete;
DROP TRIGGER trg_execution_receipts_no_update;
DROP TRIGGER trg_execution_receipts_no_delete;
DROP TRIGGER trg_execution_failures_no_update;
DROP TRIGGER trg_execution_failures_no_delete;
DROP TRIGGER trg_execution_approvals_no_update;
DROP TRIGGER trg_execution_approvals_no_delete;
DROP TRIGGER trg_execution_reconciliations_no_update;
DROP TRIGGER trg_execution_reconciliations_no_delete;

-- 3. Child-first legacy renames: transitions; command children; commands and
-- reconciliations; independent approvals; aggregates last.
ALTER TABLE execution_transitions RENAME TO _v002_execution_transitions;
ALTER TABLE execution_idempotency RENAME TO _v002_execution_idempotency;
ALTER TABLE execution_broker_references RENAME TO _v002_execution_broker_references;
ALTER TABLE execution_receipts RENAME TO _v002_execution_receipts;
ALTER TABLE execution_failures RENAME TO _v002_execution_failures;
ALTER TABLE execution_commands RENAME TO _v002_execution_commands;
ALTER TABLE execution_reconciliations RENAME TO _v002_execution_reconciliations;
ALTER TABLE execution_approvals RENAME TO _v002_execution_approvals;
ALTER TABLE execution_aggregates RENAME TO _v002_execution_aggregates;

-- 4. Parent-first replacement tables. Every definition is effective-v002 DDL
-- copied verbatim except for schema_version's canonical positive-decimal text clause.
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
    schema_version TEXT NOT NULL
        CHECK (
            typeof(schema_version) = 'text'
            AND length(schema_version) > 0
            AND schema_version NOT GLOB '*[^0-9]*'
            AND schema_version NOT GLOB '0*'
        ),
    record_fingerprint TEXT NOT NULL,
    CHECK (outcome_unknown = 0 OR reconciliation_required = 1)
);

CREATE TABLE execution_commands (
    command_id TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL REFERENCES execution_aggregates(aggregate_id)
        DEFERRABLE INITIALLY DEFERRED,
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('SUBMIT', 'CANCEL', 'REPLACE')),
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
        processing_outcome IN (
            'PENDING', 'ACCEPTED', 'REPLAYED', 'CONFLICTED', 'REJECTED', 'ABORTED'
        )
    ),
    mode TEXT NOT NULL CHECK (mode = 'PAPER'),
    schema_version TEXT NOT NULL
        CHECK (
            typeof(schema_version) = 'text'
            AND length(schema_version) > 0
            AND schema_version NOT GLOB '*[^0-9]*'
            AND schema_version NOT GLOB '0*'
        ),
    record_fingerprint TEXT NOT NULL,
    UNIQUE (command_id, canonical_payload_fingerprint)
);

CREATE TABLE execution_idempotency (
    idempotency_key TEXT PRIMARY KEY,
    logical_operation_fingerprint TEXT NOT NULL,
    command_id TEXT NOT NULL REFERENCES execution_commands(command_id),
    aggregate_id TEXT NOT NULL REFERENCES execution_aggregates(aggregate_id)
        DEFERRABLE INITIALLY DEFERRED,
    reservation_status TEXT NOT NULL CHECK (
        reservation_status IN (
            'RESERVED', 'COMPLETED', 'CONFLICTED', 'RECONCILIATION_REQUIRED'
        )
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
    schema_version TEXT NOT NULL
        CHECK (
            typeof(schema_version) = 'text'
            AND length(schema_version) > 0
            AND schema_version NOT GLOB '*[^0-9]*'
            AND schema_version NOT GLOB '0*'
        ),
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
    next_revision INTEGER NOT NULL CHECK (next_revision = previous_revision + 1),
    lifecycle_input_kind TEXT NOT NULL,
    input_identity TEXT NOT NULL,
    command_id TEXT NOT NULL REFERENCES execution_commands(command_id),
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL REFERENCES execution_idempotency(idempotency_key),
    broker_observation_identity TEXT,
    receipt_fingerprint TEXT,
    failure_fingerprint TEXT,
    replay_indicator TEXT NOT NULL CHECK (replay_indicator = 'NONE'),
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
    schema_version TEXT NOT NULL
        CHECK (
            typeof(schema_version) = 'text'
            AND length(schema_version) > 0
            AND schema_version NOT GLOB '*[^0-9]*'
            AND schema_version NOT GLOB '0*'
        ),
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
        reference_status IN ('ACTIVE', 'TERMINAL', 'REPLACED')
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
    schema_version TEXT NOT NULL
        CHECK (
            typeof(schema_version) = 'text'
            AND length(schema_version) > 0
            AND schema_version NOT GLOB '*[^0-9]*'
            AND schema_version NOT GLOB '0*'
        ),
    record_fingerprint TEXT NOT NULL
);

CREATE TABLE execution_receipts (
    receipt_fingerprint TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL REFERENCES execution_aggregates(aggregate_id),
    command_id TEXT NOT NULL REFERENCES execution_commands(command_id),
    correlation_id TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (operation IN ('SUBMIT', 'CANCEL', 'REPLACE')),
    receipt_kind TEXT NOT NULL CHECK (receipt_kind IN (
        'COMMAND_ACCEPTED_LOCALLY', 'DISPATCH_RECORDED',
        'BROKER_ACKNOWLEDGED', 'BROKER_REJECTED', 'PARTIAL_FILL_OBSERVED',
        'FILL_OBSERVED', 'CANCEL_ACKNOWLEDGED', 'CANCEL_CONFIRMED',
        'REPLACE_ACKNOWLEDGED', 'REPLACE_CONFIRMED', 'OUTCOME_UNKNOWN',
        'RECONCILIATION_REQUIRED'
    )),
    status TEXT NOT NULL CHECK (status IN (
        'CREATED', 'REJECTED_LOCAL', 'RESERVED', 'DISPATCHED', 'ACKNOWLEDGED',
        'WORKING', 'PARTIALLY_FILLED', 'FILLED', 'CANCEL_PENDING', 'CANCELLED',
        'REPLACE_PENDING', 'REPLACED', 'BROKER_REJECTED', 'OUTCOME_UNKNOWN',
        'RECONCILIATION_REQUIRED', 'FAILED_TERMINAL'
    )),
    observed_execution_revision INTEGER NOT NULL CHECK (
        observed_execution_revision >= 0
    ),
    observed_at TEXT NOT NULL CHECK (
        length(observed_at) = 27
        AND substr(observed_at, 5, 1) = '-'
        AND substr(observed_at, 8, 1) = '-'
        AND substr(observed_at, 11, 1) = 'T'
        AND substr(observed_at, 14, 1) = ':'
        AND substr(observed_at, 17, 1) = ':'
        AND substr(observed_at, 20, 1) = '.'
        AND substr(observed_at, 27, 1) = 'Z'
    ),
    message_code TEXT NOT NULL,
    broker_reference TEXT,
    outcome_known INTEGER NOT NULL CHECK (outcome_known IN (0, 1)),
    reconciliation_required INTEGER NOT NULL CHECK (
        reconciliation_required IN (0, 1)
    ),
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
    schema_version TEXT NOT NULL
        CHECK (
            typeof(schema_version) = 'text'
            AND length(schema_version) > 0
            AND schema_version NOT GLOB '*[^0-9]*'
            AND schema_version NOT GLOB '0*'
        ),
    record_fingerprint TEXT NOT NULL UNIQUE
);

CREATE TABLE execution_failures (
    failure_fingerprint TEXT PRIMARY KEY,
    aggregate_id TEXT REFERENCES execution_aggregates(aggregate_id),
    command_id TEXT REFERENCES execution_commands(command_id),
    correlation_id TEXT,
    failure_kind TEXT NOT NULL CHECK (failure_kind IN (
        'CONTRACT_VALIDATION', 'APPROVAL_REQUIRED', 'APPROVAL_INVALID',
        'PAPER_MODE_VIOLATION', 'STALE_REVISION', 'DUPLICATE_CONFLICT',
        'UNSUPPORTED_OPERATION', 'UNSUPPORTED_CAPABILITY', 'INVALID_QUANTITY',
        'INVALID_PRICE', 'INVALID_TIME_IN_FORCE', 'MARKET_CLOSED',
        'BROKER_UNAVAILABLE', 'TRANSPORT_TIMEOUT', 'AUTHENTICATION_FAILURE',
        'AUTHORIZATION_FAILURE', 'RATE_LIMITED', 'BROKER_REJECTED',
        'ACKNOWLEDGEMENT_AMBIGUOUS', 'OUTCOME_UNKNOWN', 'CANCELLATION_RACE',
        'REPLACEMENT_RACE', 'RECONCILIATION_MISMATCH', 'PERSISTENCE_FAILURE',
        'INTERNAL_INVARIANT'
    )),
    severity TEXT NOT NULL CHECK (severity IN ('INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    code TEXT NOT NULL,
    safe_message TEXT NOT NULL,
    retryable INTEGER NOT NULL CHECK (retryable IN (0, 1)),
    terminal INTEGER NOT NULL CHECK (terminal IN (0, 1)),
    reconciliation_required INTEGER NOT NULL CHECK (
        reconciliation_required IN (0, 1)
    ),
    operator_action_required INTEGER NOT NULL CHECK (
        operator_action_required IN (0, 1)
    ),
    authority_impacting INTEGER NOT NULL CHECK (authority_impacting IN (0, 1)),
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
    schema_version TEXT NOT NULL
        CHECK (
            typeof(schema_version) = 'text'
            AND length(schema_version) > 0
            AND schema_version NOT GLOB '*[^0-9]*'
            AND schema_version NOT GLOB '0*'
        ),
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
    schema_version TEXT NOT NULL
        CHECK (
            typeof(schema_version) = 'text'
            AND length(schema_version) > 0
            AND schema_version NOT GLOB '*[^0-9]*'
            AND schema_version NOT GLOB '0*'
        ),
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
    schema_version TEXT NOT NULL
        CHECK (
            typeof(schema_version) = 'text'
            AND length(schema_version) > 0
            AND schema_version NOT GLOB '*[^0-9]*'
            AND schema_version NOT GLOB '0*'
        ),
    record_fingerprint TEXT NOT NULL UNIQUE
);

-- 5. Parent-first explicit copies. Only schema_version is converted.
INSERT INTO execution_aggregates (aggregate_id, correlation_id, lifecycle_state, execution_revision, cumulative_filled_quantity, requested_quantity, active_broker_reference, outcome_unknown, reconciliation_required, command_terminal, aggregate_terminal, last_transition_id, last_command_id, last_idempotency_key, last_receipt_fingerprint, last_failure_fingerprint, mode, created_at, updated_at, schema_version, record_fingerprint)
SELECT aggregate_id, correlation_id, lifecycle_state, execution_revision, cumulative_filled_quantity, requested_quantity, active_broker_reference, outcome_unknown, reconciliation_required, command_terminal, aggregate_terminal, last_transition_id, last_command_id, last_idempotency_key, last_receipt_fingerprint, last_failure_fingerprint, mode, created_at, updated_at, CAST(schema_version AS TEXT), record_fingerprint FROM _v002_execution_aggregates;
INSERT INTO execution_commands (command_id, aggregate_id, correlation_id, idempotency_key, operation, expected_execution_revision, canonical_payload_fingerprint, canonical_command_json, approval_fingerprint, policy_fingerprint, received_at, processing_outcome, mode, schema_version, record_fingerprint)
SELECT command_id, aggregate_id, correlation_id, idempotency_key, operation, expected_execution_revision, canonical_payload_fingerprint, canonical_command_json, approval_fingerprint, policy_fingerprint, received_at, processing_outcome, mode, CAST(schema_version AS TEXT), record_fingerprint FROM _v002_execution_commands;
INSERT INTO execution_idempotency (idempotency_key, logical_operation_fingerprint, command_id, aggregate_id, reservation_status, original_result_fingerprint, created_at, resolved_at, conflict, mode, schema_version, record_fingerprint)
SELECT idempotency_key, logical_operation_fingerprint, command_id, aggregate_id, reservation_status, original_result_fingerprint, created_at, resolved_at, conflict, mode, CAST(schema_version AS TEXT), record_fingerprint FROM _v002_execution_idempotency;
INSERT INTO execution_transitions (transition_record_id, aggregate_id, transition_id, source_state, destination_state, previous_revision, next_revision, lifecycle_input_kind, input_identity, command_id, correlation_id, idempotency_key, broker_observation_identity, receipt_fingerprint, failure_fingerprint, replay_indicator, side_effect_intent_kinds_json, evidence_intent_kinds_json, safe_reason_code, mode, recorded_at, schema_version, record_fingerprint)
SELECT transition_record_id, aggregate_id, transition_id, source_state, destination_state, previous_revision, next_revision, lifecycle_input_kind, input_identity, command_id, correlation_id, idempotency_key, broker_observation_identity, receipt_fingerprint, failure_fingerprint, replay_indicator, side_effect_intent_kinds_json, evidence_intent_kinds_json, safe_reason_code, mode, recorded_at, CAST(schema_version AS TEXT), record_fingerprint FROM _v002_execution_transitions;
INSERT INTO execution_broker_references (broker_reference, aggregate_id, command_id, adapter_identity, reference_status, first_seen_at, last_seen_at, active, replaced_by_reference, mode, schema_version, record_fingerprint)
SELECT broker_reference, aggregate_id, command_id, adapter_identity, reference_status, first_seen_at, last_seen_at, active, replaced_by_reference, mode, CAST(schema_version AS TEXT), record_fingerprint FROM _v002_execution_broker_references;
INSERT INTO execution_receipts (receipt_fingerprint, aggregate_id, command_id, correlation_id, operation, receipt_kind, status, observed_execution_revision, observed_at, message_code, broker_reference, outcome_known, reconciliation_required, recorded_at, mode, schema_version, record_fingerprint)
SELECT receipt_fingerprint, aggregate_id, command_id, correlation_id, operation, receipt_kind, status, observed_execution_revision, observed_at, message_code, broker_reference, outcome_known, reconciliation_required, recorded_at, mode, CAST(schema_version AS TEXT), record_fingerprint FROM _v002_execution_receipts;
INSERT INTO execution_failures (failure_fingerprint, aggregate_id, command_id, correlation_id, failure_kind, severity, code, safe_message, retryable, terminal, reconciliation_required, operator_action_required, authority_impacting, recorded_at, mode, schema_version, record_fingerprint)
SELECT failure_fingerprint, aggregate_id, command_id, correlation_id, failure_kind, severity, code, safe_message, retryable, terminal, reconciliation_required, operator_action_required, authority_impacting, recorded_at, mode, CAST(schema_version AS TEXT), record_fingerprint FROM _v002_execution_failures;
INSERT INTO execution_approvals (approval_fingerprint, bound_fingerprint, approval_kind, approver_safe_reference, approved_at, expires_at, revocation_reference, recorded_at, mode, schema_version, record_fingerprint)
SELECT approval_fingerprint, bound_fingerprint, approval_kind, approver_safe_reference, approved_at, expires_at, revocation_reference, recorded_at, mode, CAST(schema_version AS TEXT), record_fingerprint FROM _v002_execution_approvals;
INSERT INTO execution_reconciliations (reconciliation_id, aggregate_id, starting_local_revision, starting_lifecycle_state, broker_observation_references_json, result_classification, resulting_transition_id, resulting_revision, operator_action_required, unresolved, safe_reason_code, recorded_at, mode, schema_version, record_fingerprint)
SELECT reconciliation_id, aggregate_id, starting_local_revision, starting_lifecycle_state, broker_observation_references_json, result_classification, resulting_transition_id, resulting_revision, operator_action_required, unresolved, safe_reason_code, recorded_at, mode, CAST(schema_version AS TEXT), record_fingerprint FROM _v002_execution_reconciliations;

-- 6. Child-first legacy drops.
DROP TABLE _v002_execution_transitions;
DROP TABLE _v002_execution_idempotency;
DROP TABLE _v002_execution_broker_references;
DROP TABLE _v002_execution_receipts;
DROP TABLE _v002_execution_failures;
DROP TABLE _v002_execution_commands;
DROP TABLE _v002_execution_reconciliations;
DROP TABLE _v002_execution_approvals;
DROP TABLE _v002_execution_aggregates;

-- 7. Effective named index recreation.
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
CREATE UNIQUE INDEX ux_execution_broker_references_active_aggregate
ON execution_broker_references(aggregate_id) WHERE active = 1;
CREATE INDEX idx_execution_broker_references_aggregate_active
ON execution_broker_references(aggregate_id, active);
CREATE INDEX idx_execution_receipts_command_aggregate
ON execution_receipts(command_id, aggregate_id);
CREATE INDEX idx_execution_failures_command_aggregate
ON execution_failures(command_id, aggregate_id);
CREATE INDEX idx_execution_reconciliations_aggregate_unresolved
ON execution_reconciliations(aggregate_id, unresolved);

-- 8. Effective named trigger recreation.
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

-- Required effective index inventory.
INSERT INTO _v003_guard (value)
WITH expected_index(name, tbl_name) AS (
    VALUES
        ('idx_execution_aggregates_lifecycle_state', 'execution_aggregates'),
        ('idx_execution_aggregates_consequential_state', 'execution_aggregates'),
        ('idx_execution_aggregates_updated_at', 'execution_aggregates'),
        ('idx_execution_commands_aggregate_received', 'execution_commands'),
        ('idx_execution_commands_idempotency_key', 'execution_commands'),
        ('idx_execution_idempotency_aggregate', 'execution_idempotency'),
        ('idx_execution_transitions_command', 'execution_transitions'),
        (
            'ux_execution_broker_references_active_aggregate',
            'execution_broker_references'
        ),
        (
            'idx_execution_broker_references_aggregate_active',
            'execution_broker_references'
        ),
        ('idx_execution_receipts_command_aggregate', 'execution_receipts'),
        ('idx_execution_failures_command_aggregate', 'execution_failures'),
        (
            'idx_execution_reconciliations_aggregate_unresolved',
            'execution_reconciliations'
        )
),
actual_index AS (
    SELECT
        expected_index.name AS expected_name,
        expected_index.tbl_name AS expected_table,
        sqlite_master.name AS actual_name,
        sqlite_master.tbl_name AS actual_table,
        sqlite_master.type AS actual_type
    FROM expected_index
    LEFT JOIN sqlite_master ON sqlite_master.name = expected_index.name
)
SELECT CASE
    WHEN count(*) = 12
     AND sum(
         CASE
             WHEN actual_name = expected_name
              AND actual_type = 'index'
              AND actual_table = expected_table
             THEN 1
             ELSE 0
         END
     ) = 12
    THEN 0
    ELSE 1
END
FROM actual_index;

-- Required effective trigger inventory.
INSERT INTO _v003_guard (value)
WITH expected_trigger(name, tbl_name) AS (
    VALUES
        ('trg_execution_commands_no_update', 'execution_commands'),
        ('trg_execution_commands_no_delete', 'execution_commands'),
        ('trg_execution_transitions_no_update', 'execution_transitions'),
        ('trg_execution_transitions_no_delete', 'execution_transitions'),
        ('trg_execution_receipts_no_update', 'execution_receipts'),
        ('trg_execution_receipts_no_delete', 'execution_receipts'),
        ('trg_execution_failures_no_update', 'execution_failures'),
        ('trg_execution_failures_no_delete', 'execution_failures'),
        ('trg_execution_approvals_no_update', 'execution_approvals'),
        ('trg_execution_approvals_no_delete', 'execution_approvals'),
        ('trg_execution_reconciliations_no_update', 'execution_reconciliations'),
        ('trg_execution_reconciliations_no_delete', 'execution_reconciliations')
),
actual_trigger AS (
    SELECT
        expected_trigger.name AS expected_name,
        expected_trigger.tbl_name AS expected_table,
        sqlite_master.name AS actual_name,
        sqlite_master.tbl_name AS actual_table,
        sqlite_master.type AS actual_type
    FROM expected_trigger
    LEFT JOIN sqlite_master ON sqlite_master.name = expected_trigger.name
)
SELECT CASE
    WHEN count(*) = 12
     AND sum(
         CASE
             WHEN actual_name = expected_name
              AND actual_type = 'trigger'
              AND actual_table = expected_table
             THEN 1
             ELSE 0
         END
     ) = 12
    THEN 0
    ELSE 1
END
FROM actual_trigger;

-- 9. Integrity and cleanup gates.
INSERT INTO _v003_guard (value)
SELECT count(*) FROM pragma_foreign_key_check;
INSERT INTO _v003_guard (value)
SELECT count(*) FROM sqlite_master
WHERE type = 'table' AND name LIKE '_v002_execution_%';
DROP TABLE _v003_guard;
