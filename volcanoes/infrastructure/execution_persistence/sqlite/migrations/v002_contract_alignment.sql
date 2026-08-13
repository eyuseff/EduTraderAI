CREATE TEMP TABLE _v002_guard (
    value INTEGER NOT NULL CHECK (value = 0)
);

INSERT INTO _v002_guard (value)
SELECT count(*)
FROM execution_commands
WHERE processing_outcome NOT IN ('REGISTERED', 'REPLAY', 'CONFLICT', 'REJECTED');

INSERT INTO _v002_guard (value)
SELECT count(*)
FROM execution_idempotency
WHERE reservation_status NOT IN ('RESERVED', 'RESOLVED', 'CONFLICT', 'UNKNOWN');

INSERT INTO _v002_guard (value)
SELECT count(*)
FROM execution_transitions
WHERE replay_indicator = 'REPLAY_SUPPRESSED'
   OR replay_indicator <> 'NOT_REPLAY';

INSERT INTO _v002_guard (value)
SELECT count(*)
FROM execution_broker_references
WHERE reference_status NOT IN ('ACTIVE', 'REPLACED', 'TERMINAL');

INSERT INTO _v002_guard (value)
SELECT count(*) FROM execution_receipts;

INSERT INTO _v002_guard (value)
SELECT count(*) FROM execution_failures;

DROP TRIGGER trg_execution_commands_no_update;
DROP TRIGGER trg_execution_commands_no_delete;
DROP TRIGGER trg_execution_transitions_no_update;
DROP TRIGGER trg_execution_transitions_no_delete;
DROP TRIGGER trg_execution_receipts_no_update;
DROP TRIGGER trg_execution_receipts_no_delete;
DROP TRIGGER trg_execution_failures_no_update;
DROP TRIGGER trg_execution_failures_no_delete;

ALTER TABLE execution_commands RENAME TO _v001_execution_commands;
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
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    record_fingerprint TEXT NOT NULL,
    UNIQUE (command_id, canonical_payload_fingerprint)
);
INSERT INTO execution_commands
SELECT command_id, aggregate_id, correlation_id, idempotency_key, operation,
       expected_execution_revision, canonical_payload_fingerprint,
       canonical_command_json, approval_fingerprint, policy_fingerprint,
       received_at,
       CASE processing_outcome
           WHEN 'REGISTERED' THEN 'PENDING'
           WHEN 'REPLAY' THEN 'REPLAYED'
           WHEN 'CONFLICT' THEN 'CONFLICTED'
           WHEN 'REJECTED' THEN 'REJECTED'
       END,
       mode, schema_version, record_fingerprint
FROM _v001_execution_commands;

ALTER TABLE execution_idempotency RENAME TO _v001_execution_idempotency;
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
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    record_fingerprint TEXT NOT NULL,
    UNIQUE (idempotency_key, logical_operation_fingerprint)
);
INSERT INTO execution_idempotency
SELECT idempotency_key, logical_operation_fingerprint, command_id, aggregate_id,
       CASE reservation_status
           WHEN 'RESERVED' THEN 'RESERVED'
           WHEN 'RESOLVED' THEN 'COMPLETED'
           WHEN 'CONFLICT' THEN 'CONFLICTED'
           WHEN 'UNKNOWN' THEN 'RECONCILIATION_REQUIRED'
       END,
       original_result_fingerprint, created_at, resolved_at, conflict, mode,
       schema_version, record_fingerprint
FROM _v001_execution_idempotency;

ALTER TABLE execution_transitions RENAME TO _v001_execution_transitions;
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
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    record_fingerprint TEXT NOT NULL,
    UNIQUE (aggregate_id, next_revision),
    UNIQUE (aggregate_id, transition_id)
);
INSERT INTO execution_transitions
SELECT transition_record_id, aggregate_id, transition_id, source_state,
       destination_state, previous_revision, next_revision, lifecycle_input_kind,
       input_identity, command_id, correlation_id, idempotency_key,
       broker_observation_identity, receipt_fingerprint, failure_fingerprint,
       'NONE', side_effect_intent_kinds_json, evidence_intent_kinds_json,
       safe_reason_code, mode, recorded_at, schema_version, record_fingerprint
FROM _v001_execution_transitions;

ALTER TABLE execution_broker_references RENAME TO _v001_execution_broker_references;
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
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    record_fingerprint TEXT NOT NULL
);
INSERT INTO execution_broker_references
SELECT broker_reference, aggregate_id, command_id, adapter_identity,
       reference_status, first_seen_at, last_seen_at, active,
       replaced_by_reference, mode, schema_version, record_fingerprint
FROM _v001_execution_broker_references;

ALTER TABLE execution_receipts RENAME TO _v001_execution_receipts;
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
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    record_fingerprint TEXT NOT NULL UNIQUE
);

ALTER TABLE execution_failures RENAME TO _v001_execution_failures;
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
    schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
    record_fingerprint TEXT NOT NULL UNIQUE
);

-- Each legacy child table is retained until all replacement tables exist.
-- Renaming a parent rewrites legacy foreign-key metadata to the legacy name;
-- therefore children must be dropped before their legacy parents.
DROP TABLE _v001_execution_transitions;
DROP TABLE _v001_execution_broker_references;
DROP TABLE _v001_execution_receipts;
DROP TABLE _v001_execution_failures;
DROP TABLE _v001_execution_idempotency;
DROP TABLE _v001_execution_commands;

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

INSERT INTO _v002_guard (value)
SELECT count(*) FROM pragma_foreign_key_check;

DROP TABLE _v002_guard;
