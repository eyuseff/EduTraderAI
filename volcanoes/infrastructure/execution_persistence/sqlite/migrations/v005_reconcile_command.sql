-- V005 broadens only the durable command operation vocabulary for F6B recovery.
-- The migration runner temporarily disables foreign-key enforcement around this
-- transaction and validates pragma_foreign_key_check before commit. This lets
-- the parent command table be replaced without rewriting its dependent tables.

CREATE TABLE _v005_execution_commands (
    command_id TEXT PRIMARY KEY,
    aggregate_id TEXT NOT NULL REFERENCES execution_aggregates(aggregate_id)
        DEFERRABLE INITIALLY DEFERRED,
    correlation_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    operation TEXT NOT NULL CHECK (
        operation IN ('SUBMIT', 'CANCEL', 'REPLACE', 'RECONCILE')
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

INSERT INTO _v005_execution_commands (
    command_id,
    aggregate_id,
    correlation_id,
    idempotency_key,
    operation,
    expected_execution_revision,
    canonical_payload_fingerprint,
    canonical_command_json,
    approval_fingerprint,
    policy_fingerprint,
    received_at,
    processing_outcome,
    mode,
    schema_version,
    record_fingerprint
)
SELECT
    command_id,
    aggregate_id,
    correlation_id,
    idempotency_key,
    operation,
    expected_execution_revision,
    canonical_payload_fingerprint,
    canonical_command_json,
    approval_fingerprint,
    policy_fingerprint,
    received_at,
    processing_outcome,
    mode,
    schema_version,
    record_fingerprint
FROM execution_commands;

DROP TRIGGER trg_execution_commands_no_update;
DROP TRIGGER trg_execution_commands_no_delete;
DROP INDEX idx_execution_commands_aggregate_received;
DROP INDEX idx_execution_commands_idempotency_key;
DROP TABLE execution_commands;
ALTER TABLE _v005_execution_commands RENAME TO execution_commands;

CREATE INDEX idx_execution_commands_aggregate_received
ON execution_commands(aggregate_id, received_at);
CREATE INDEX idx_execution_commands_idempotency_key
ON execution_commands(idempotency_key);

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
