"""Schema constants for the SQLite execution persistence foundation."""

from __future__ import annotations

from importlib import resources

SCHEMA_RESOURCE_PACKAGE = (
    "volcanoes.infrastructure.execution_persistence.sqlite.migrations"
)
INITIAL_SCHEMA_RESOURCE = "v001_initial_schema.sql"
CONTRACT_ALIGNMENT_SCHEMA_RESOURCE = "v002_contract_alignment.sql"

EXPECTED_TABLES: tuple[str, ...] = (
    "execution_aggregates",
    "execution_commands",
    "execution_idempotency",
    "execution_transitions",
    "execution_broker_references",
    "execution_receipts",
    "execution_failures",
    "execution_approvals",
    "execution_reconciliations",
    "schema_migrations",
)

EXPECTED_INDEXES: tuple[str, ...] = (
    "idx_execution_aggregates_lifecycle_state",
    "idx_execution_aggregates_consequential_state",
    "idx_execution_aggregates_updated_at",
    "idx_execution_commands_aggregate_received",
    "idx_execution_commands_idempotency_key",
    "idx_execution_idempotency_aggregate",
    "idx_execution_transitions_command",
    "idx_execution_broker_references_aggregate_active",
    "idx_execution_receipts_command_aggregate",
    "idx_execution_failures_command_aggregate",
    "idx_execution_reconciliations_aggregate_unresolved",
    "idx_schema_migrations_resulting_version",
)

EXPECTED_TRIGGERS: tuple[str, ...] = (
    "trg_execution_commands_no_update",
    "trg_execution_commands_no_delete",
    "trg_execution_transitions_no_update",
    "trg_execution_transitions_no_delete",
    "trg_execution_receipts_no_update",
    "trg_execution_receipts_no_delete",
    "trg_execution_failures_no_update",
    "trg_execution_failures_no_delete",
    "trg_execution_approvals_no_update",
    "trg_execution_approvals_no_delete",
    "trg_execution_reconciliations_no_update",
    "trg_execution_reconciliations_no_delete",
    "trg_schema_migrations_no_update",
    "trg_schema_migrations_no_delete",
)

EXPECTED_COLUMNS: dict[str, tuple[str, ...]] = {
    "execution_aggregates": (
        "aggregate_id",
        "correlation_id",
        "lifecycle_state",
        "execution_revision",
        "cumulative_filled_quantity",
        "requested_quantity",
        "active_broker_reference",
        "outcome_unknown",
        "reconciliation_required",
        "command_terminal",
        "aggregate_terminal",
        "last_transition_id",
        "last_command_id",
        "last_idempotency_key",
        "last_receipt_fingerprint",
        "last_failure_fingerprint",
        "mode",
        "created_at",
        "updated_at",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_commands": (
        "command_id",
        "aggregate_id",
        "correlation_id",
        "idempotency_key",
        "operation",
        "expected_execution_revision",
        "canonical_payload_fingerprint",
        "canonical_command_json",
        "approval_fingerprint",
        "policy_fingerprint",
        "received_at",
        "processing_outcome",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_idempotency": (
        "idempotency_key",
        "logical_operation_fingerprint",
        "command_id",
        "aggregate_id",
        "reservation_status",
        "original_result_fingerprint",
        "created_at",
        "resolved_at",
        "conflict",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_transitions": (
        "transition_record_id",
        "aggregate_id",
        "transition_id",
        "source_state",
        "destination_state",
        "previous_revision",
        "next_revision",
        "lifecycle_input_kind",
        "input_identity",
        "command_id",
        "correlation_id",
        "idempotency_key",
        "broker_observation_identity",
        "receipt_fingerprint",
        "failure_fingerprint",
        "replay_indicator",
        "side_effect_intent_kinds_json",
        "evidence_intent_kinds_json",
        "safe_reason_code",
        "mode",
        "recorded_at",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_broker_references": (
        "broker_reference",
        "aggregate_id",
        "command_id",
        "adapter_identity",
        "reference_status",
        "first_seen_at",
        "last_seen_at",
        "active",
        "replaced_by_reference",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_receipts": (
        "receipt_fingerprint",
        "aggregate_id",
        "command_id",
        "correlation_id",
        "operation",
        "receipt_kind",
        "status",
        "observed_execution_revision",
        "observed_at",
        "message_code",
        "broker_reference",
        "outcome_known",
        "reconciliation_required",
        "recorded_at",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_failures": (
        "failure_fingerprint",
        "aggregate_id",
        "command_id",
        "correlation_id",
        "failure_kind",
        "severity",
        "code",
        "safe_message",
        "retryable",
        "terminal",
        "reconciliation_required",
        "operator_action_required",
        "authority_impacting",
        "recorded_at",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_approvals": (
        "approval_fingerprint",
        "bound_fingerprint",
        "approval_kind",
        "approver_safe_reference",
        "approved_at",
        "expires_at",
        "revocation_reference",
        "recorded_at",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "execution_reconciliations": (
        "reconciliation_id",
        "aggregate_id",
        "starting_local_revision",
        "starting_lifecycle_state",
        "broker_observation_references_json",
        "result_classification",
        "resulting_transition_id",
        "resulting_revision",
        "operator_action_required",
        "unresolved",
        "safe_reason_code",
        "recorded_at",
        "mode",
        "schema_version",
        "record_fingerprint",
    ),
    "schema_migrations": (
        "migration_id",
        "migration_name",
        "checksum",
        "applied_at",
        "application_version",
        "previous_schema_version",
        "resulting_schema_version",
        "safe_notes",
    ),
}

AGGREGATE_CAS_UPDATE_SQL = """
UPDATE execution_aggregates
SET lifecycle_state = ?,
    execution_revision = ?,
    updated_at = ?,
    last_transition_id = ?,
    last_command_id = ?,
    last_idempotency_key = ?,
    record_fingerprint = ?
WHERE aggregate_id = ?
  AND execution_revision = ?
"""


def load_initial_schema_sql() -> str:
    """Return the canonical v001 schema SQL text."""

    return (
        resources.files(SCHEMA_RESOURCE_PACKAGE)
        .joinpath(INITIAL_SCHEMA_RESOURCE)
        .read_text(encoding="utf-8")
    )


def load_contract_alignment_schema_sql() -> str:
    """Return the canonical v002 schema-contract alignment SQL text."""

    return (
        resources.files(SCHEMA_RESOURCE_PACKAGE)
        .joinpath(CONTRACT_ALIGNMENT_SCHEMA_RESOURCE)
        .read_text(encoding="utf-8")
    )


__all__ = [
    "AGGREGATE_CAS_UPDATE_SQL",
    "CONTRACT_ALIGNMENT_SCHEMA_RESOURCE",
    "EXPECTED_COLUMNS",
    "EXPECTED_INDEXES",
    "EXPECTED_TABLES",
    "EXPECTED_TRIGGERS",
    "INITIAL_SCHEMA_RESOURCE",
    "SCHEMA_RESOURCE_PACKAGE",
    "load_initial_schema_sql",
    "load_contract_alignment_schema_sql",
]
