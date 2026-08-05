# V41-PQ-001F5E2A SQLite Schema Design

## Purpose

Design the future production SQLite schema for the F5E1A persistence records. This document is schema design only; it creates no production SQL file and deploys no database.

## Representation rules

- Opaque identities: `TEXT`.
- Enums: canonical `TEXT` constrained by `CHECK`.
- Booleans: `INTEGER NOT NULL CHECK(value IN (0, 1))`.
- Datetimes: normalized UTC `TEXT` in `YYYY-MM-DDTHH:MM:SS.ffffffZ` format.
- Quantities/prices: canonical decimal `TEXT`; no floating point and no
  SQLite `REAL`.
- Fingerprints: deterministic `TEXT`.
- Mode: constrained to Paper-only values accepted by the contracts.
- Raw broker objects, credentials, SDK objects, callbacks, and raw payloads: prohibited.
- Authoritative timestamps must be timezone-aware at the contract boundary and
  serialized by the application, never by SQLite default clock functions.

## Table inventory

| Table | Contract | Role |
|---|---|---|
| `execution_aggregates` | `ExecutionAggregateRecord` | Materialized local lifecycle state. |
| `execution_commands` | `ExecutionCommandRecord` | Immutable command identity and payload binding. |
| `execution_idempotency` | `ExecutionIdempotencyRecord` | Permanent logical operation reservation. |
| `execution_transitions` | `ExecutionTransitionRecord` | Append-only accepted lifecycle journal. |
| `execution_broker_references` | `ExecutionBrokerReferenceRecord` | Normalized broker-reference observations. |
| `execution_receipts` | `ExecutionReceiptRecord` | Normalized safe receipt facts. |
| `execution_failures` | `ExecutionFailureRecord` | Normalized safe failure facts. |
| `execution_approvals` | `ExecutionApprovalRecord` | Approval fingerprints and safe references. |
| `execution_reconciliations` | `ExecutionReconciliationRecord` | Append-only reconciliation facts. |
| `schema_migrations` | adapter metadata | Migration ordering and checksums. |

## `execution_aggregates`

Primary key: `aggregate_id TEXT`.

Columns: `correlation_id`, `lifecycle_state`, `execution_revision`, `cumulative_filled_quantity`, `requested_quantity`, `active_broker_reference`, `outcome_unknown`, `reconciliation_required`, `command_terminal`, `aggregate_terminal`, `last_transition_id`, `last_command_id`, `last_idempotency_key`, `last_receipt_fingerprint`, `last_failure_fingerprint`, `mode`, `created_at`, `updated_at`, `schema_version`, `record_fingerprint`.

Constraints:

- `execution_revision >= 0`;
- boolean fields constrained to `0/1`;
- `mode` constrained to Paper;
- quantity text must be canonical decimal text;
- `outcome_unknown` and `reconciliation_required` consistency checked where possible;
- `last_transition_id` references accepted transition identity once present.

Mutable fields are only the materialized snapshot fields updated through exact CAS. Identity, creation timestamp, mode, and record lineage are immutable.

## `execution_commands`

Primary key: `command_id TEXT`.

Columns: `aggregate_id`, `correlation_id`, `idempotency_key`, `operation`, `expected_execution_revision`, `canonical_payload_fingerprint`, `canonical_command_json`, `approval_fingerprint`, `policy_fingerprint`, `received_at`, `processing_outcome`, `mode`, `schema_version`, `record_fingerprint`.

Constraints:

- FK to aggregate;
- operation constrained;
- command ID permanently maps to one canonical payload fingerprint;
- no overwrite/upsert that can change payload binding;
- no raw Python object or callback.
- `processing_outcome` is immutable after command insertion. It captures the
  command registration outcome represented by `ExecutionCommandRecord`; later
  lifecycle results belong in aggregate state, transitions, receipts, failures,
  or reconciliation records.

Replay query: load by `command_id`; if fingerprint matches, replay; if fingerprint differs, command conflict.

## `execution_idempotency`

Primary key: `idempotency_key TEXT`.

Columns: `logical_operation_fingerprint`, `command_id`, `aggregate_id`, `reservation_status`, `original_result_fingerprint`, `created_at`, `resolved_at`, `conflict`, `mode`, `schema_version`, `record_fingerprint`.

Constraints:

- FK to command and aggregate;
- status constrained;
- conflict constrained boolean;
- key bound forever to one logical fingerprint;
- no delete/reuse while replay may matter.

Reservation occurs during authoritative command intake before lifecycle progression to dispatch preparation.

## `execution_transitions`

Primary key: `transition_record_id TEXT`.

Columns: `aggregate_id`, `transition_id`, `source_state`, `destination_state`, `previous_revision`, `next_revision`, `lifecycle_input_kind`, `input_identity`, `command_id`, `correlation_id`, `idempotency_key`, `broker_observation_identity`, `receipt_fingerprint`, `failure_fingerprint`, `replay_indicator`, `side_effect_intent_kinds_json`, `evidence_intent_kinds_json`, `safe_reason_code`, `mode`, `recorded_at`, `schema_version`, `record_fingerprint`.

Constraints:

- FK to aggregate and command;
- `next_revision = previous_revision + 1`;
- unique `(aggregate_id, next_revision)`;
- accepted transitions only;
- append-only.

Recommendation: create SQLite triggers rejecting `UPDATE` and `DELETE` on this
table in the implementation slice. Trigger failures map to a normalized
integrity/immutability infrastructure failure.

## `execution_broker_references`

Primary key: `broker_reference TEXT`.

Columns: `aggregate_id`, `command_id`, `adapter_identity`, `reference_status`, `first_seen_at`, `last_seen_at`, `active`, `replaced_by_reference`, `mode`, `schema_version`, `record_fingerprint`.

Constraints:

- FK to aggregate and command;
- active flag constrained;
- one normalized broker reference maps to one aggregate;
- partial unique index for active aggregate/reference ownership where needed;
- no raw broker payload or secrets.

## Receipts and failures

`execution_receipts` primary key: `record_fingerprint` or receipt fingerprint extracted from `PaperExecutionReceipt`.

`execution_failures` primary key: `record_fingerprint` or failure fingerprint extracted from `PaperExecutionFailure`.

Both store normalized safe fields from the contract object, aggregate/command references where available, timestamps, status/kind/severity classifications, reconciliation flags, `schema_version`, and `record_fingerprint`. Both are immutable after insert and receive update/delete denial triggers.

## Approvals

`execution_approvals` primary key: `approval_fingerprint`.

Columns: `bound_fingerprint`, `approval_kind`, `approver_safe_reference`, `approved_at`, `expires_at`, `revocation_reference`, `mode`, `recorded_at`, `schema_version`, `record_fingerprint`.

No authentication data, tokens, sessions, or credentials are stored.

## Reconciliations

`execution_reconciliations` primary key: `reconciliation_id`.

Columns: `aggregate_id`, `starting_local_revision`, `starting_lifecycle_state`, `broker_observation_references_json`, `result_classification`, `resulting_transition_id`, `resulting_revision`, `operator_action_required`, `unresolved`, `safe_reason_code`, `mode`, `recorded_at`, `schema_version`, `record_fingerprint`.

Rows are append-only. Prior reconciliation facts are never overwritten.

## `schema_migrations`

Primary key: `migration_id TEXT`.

Columns: `migration_name`, `checksum`, `applied_at`, `application_version`, `previous_schema_version`, `resulting_schema_version`, `success_marker`, `safe_notes`.

Duplicate ID with different checksum fails. Failed migrations must not insert false success rows.

Migration rows are immutable after insert and receive update/delete denial
triggers.

## Key indexes

- `execution_aggregates(lifecycle_state)`;
- `execution_aggregates(outcome_unknown, reconciliation_required)`;
- `execution_commands(aggregate_id, received_at)`;
- `execution_commands(idempotency_key)`;
- `execution_idempotency(aggregate_id)`;
- `execution_transitions(aggregate_id, next_revision) UNIQUE`;
- `execution_transitions(command_id)`;
- `execution_broker_references(aggregate_id, active)`;
- `execution_reconciliations(aggregate_id, unresolved)`;
- `schema_migrations(resulting_schema_version)`.

## Append-only trigger model

Future implementation should define denial triggers for:

- `execution_commands`: reject `UPDATE` and `DELETE`;
- `execution_transitions`: reject `UPDATE` and `DELETE`;
- `execution_receipts`: reject `UPDATE` and `DELETE`;
- `execution_failures`: reject `UPDATE` and `DELETE`;
- `execution_approvals`: reject `UPDATE` and `DELETE`;
- `execution_reconciliations`: reject `UPDATE` and `DELETE`;
- `schema_migrations`: reject `UPDATE` and `DELETE`.

`execution_idempotency` is not fully append-only because controlled status
resolution is required. Allowed updates are limited to reservation status,
original result fingerprint, resolved timestamp, conflict flag, and record
fingerprint under an exact current-status predicate.

`execution_broker_references` allows controlled updates to `last_seen_at`,
`active`, `reference_status`, and `replaced_by_reference` only under explicit
ownership checks. Silent active ownership transfer is prohibited.
