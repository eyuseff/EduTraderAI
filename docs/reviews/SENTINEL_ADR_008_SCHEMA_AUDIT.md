# Sentinel ADR-008 Schema Audit

## Audit result

PASS.

ADR-008 and F5E2A schema design map every F5E1A durable record to an explicit SQLite table or justified storage model.

## Representation decisions

- Opaque identities: `TEXT`.
- Enums: canonical `TEXT` plus `CHECK`.
- Booleans: constrained `INTEGER`.
- Decimals: canonical decimal `TEXT`; SQLite `REAL` rejected.
- Timestamps: UTC `TEXT` in `YYYY-MM-DDTHH:MM:SS.ffffffZ`; database default current timestamp rejected for authoritative records.
- Fingerprints: deterministic `TEXT`.
- Secrets/raw broker payloads: excluded.

## Table audit

| Table | Contract | Primary key | Core constraints | Startup validation |
|---|---|---|---|---|
| `execution_aggregates` | `ExecutionAggregateRecord` | `aggregate_id` | revision non-negative, Paper mode, boolean checks, canonical quantity text, consequential-state consistency | Required table, indexes, revision/history invariant. |
| `execution_commands` | `ExecutionCommandRecord` | `command_id` | immutable command ID to payload fingerprint binding, operation check, FK aggregate | Required table, immutability trigger, fingerprint consistency. |
| `execution_idempotency` | `ExecutionIdempotencyRecord` | `idempotency_key` | permanent logical fingerprint binding, status check, FK command/aggregate, no destructive reuse | Required table, binding consistency. |
| `execution_transitions` | `ExecutionTransitionRecord` | `transition_record_id` | unique aggregate/revision, `next = previous + 1`, accepted transitions only, append-only | Required table, immutability trigger, journal/snapshot consistency. |
| `execution_broker_references` | `ExecutionBrokerReferenceRecord` | `broker_reference` | one reference to one aggregate, active ownership bounded, no raw broker object | Required table, ownership consistency. |
| `execution_receipts` | `ExecutionReceiptRecord` | fingerprint | immutable normalized safe receipt facts | Required table, immutability trigger. |
| `execution_failures` | `ExecutionFailureRecord` | fingerprint | immutable normalized safe failure facts | Required table, immutability trigger. |
| `execution_approvals` | `ExecutionApprovalRecord` | `approval_fingerprint` | safe approver reference, no auth secrets, immutable | Required table, immutability trigger. |
| `execution_reconciliations` | `ExecutionReconciliationRecord` | `reconciliation_id` | append-only facts, unresolved/operator flags | Required table, immutability trigger, unresolved query. |
| `schema_migrations` | Migration metadata | `migration_id` | immutable ID/checksum/version record | Required table, ordering/checksum validation. |

## Command immutability decision

`processing_outcome` remains in `execution_commands` only as an immutable insertion-time field matching `ExecutionCommandRecord`. Later lifecycle results must be expressed through aggregate state, transitions, receipts, failures, or reconciliations. No command-row update is accepted.

## Controlled mutable records

`execution_idempotency` may receive controlled status-resolution updates only under exact current-status predicates. `execution_broker_references` may receive controlled observation/replacement updates only under explicit ownership checks. Silent ownership transfer is prohibited.

## Index decision

Required indexes are tied to command replay, idempotency replay/conflict, aggregate lifecycle/restart discovery, transition history, active broker-reference lookup, unresolved reconciliation discovery, and migration ordering. Speculative performance indexes are deferred.

## Audit conclusion

No missing, redundant, or unsafe blocking schema elements remain. F5E2B may implement schema SQL and schema validation only.
