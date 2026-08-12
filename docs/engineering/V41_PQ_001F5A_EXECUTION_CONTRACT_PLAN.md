# V41-PQ-001F5A Execution Contract Plan

## Purpose

Plan immutable execution contracts for V41-PQ-001F5B without adding production
classes in F5A.

## Contract catalogue

| Contract | Responsibility | Mandatory fields | Prohibited fields | Invariants | Identity and revision behavior | Security | Persistence and serialization | Owner | Lifecycle | F5B |
|---|---|---|---|---|---|---|---|---|---|---|
| `PaperExecutionCommand` | Immutable request to perform one state-changing Paper operation. | command id, logical execution id, operation, mode, intent, approval reference, expected execution revision, idempotency key, correlation id, created time, policy snapshot fingerprint. | credentials, raw broker payload, account secrets, mutable broker objects, Streamlit objects. | Paper mode only; positive quantity where applicable; operation-specific required fields present. | command id + payload fingerprint must be stable; expected revision required for state changes. | Confidential metadata excluded; safe identifiers only. | Durable later; canonical JSON required. | execution application layer. | created before validation; never mutated. | Required. |
| `PaperExecutionCommandId` | Stable command identity. | prefix and digest/string value. | broker order id as sole value. | globally unique enough for local and durable use. | reused id with changed payload is conflict. | safe to log. | durable and serializable. | execution core. | command lifetime. | Required. |
| `PaperExecutionIntent` | Broker-neutral desired order facts. | symbol, side, quantity, limit/stop/target fields as applicable, order type, time in force. | broker SDK request, credentials, account number. | normalized symbol; no unsupported operation facts. | contributes to command fingerprint. | safe if no account data. | canonical serialization. | execution core. | command input. | Required. |
| `PaperExecutionContext` | Safe execution environment facts. | Paper mode, actor, source, correlation id, emergency-stop snapshot, capability snapshot id, clock timestamp. | live endpoint, secrets, mutable client. | mode is Paper; unknown environment fails closed. | context fingerprint included in command evidence. | redacted. | durable later. | application boundary. | command evaluation. | Required. |
| `PaperExecutionPolicySnapshot` | Immutable policy facts used for eligibility. | Paper-only policy, retry policy label, capability policy fingerprint, approval policy fingerprint. | executable callbacks, broker clients, secrets. | policy digest deterministic. | digest included in command. | safe to log after redaction. | canonical JSON. | execution policy layer. | command evaluation. | Required. |
| `PaperExecutionApproval` | Explicit authority record. | approval id, approver/actor type, scope, operation, logical execution id, expiry/staleness facts, fingerprint, timestamp. | readiness decision as approval, credentials. | approval scope matches command; not stale. | approval fingerprint binds to command fields. | operator identity may need redaction. | durable later. | approval boundary. | before command dispatch. | Required. |
| `PaperExecutionReceipt` | Normalized fact returned by broker adapter. | command id, operation, receipt kind, mode, broker reference if known, status, timestamp, safe message. | raw response, auth headers, secrets. | receipt kind must not overstate broker fact. | attaches to revision transition; may be duplicate-safe. | redacted. | append-only later. | adapter boundary. | after dispatch/query/reconcile. | Required. |
| `PaperExecutionOutcome` | Explainable result of command processing. | outcome status, command id, logical id, submitted flag when applicable, receipt refs, failure if any, next revision. | broker object, mutable state. | outcome must be terminal or non-terminal explicitly. | same command replay returns same logical outcome. | safe summary only. | serializable. | execution service. | command result. | Required. |
| `PaperExecutionFailure` | Typed safe failure. | code, category, retry classification, terminal flag, reconciliation flag, operator-action flag, safe explanation. | raw exception string if secret-bearing, stack with tokens. | no raw broker exception escapes. | may block revision transition or advance to failure state. | safe-to-expose flag. | serializable. | execution core/adapter boundary. | on failure. | Required. |
| `PaperExecutionStatus` | Execution state enum. | one of accepted execution states. | qualification states. | no overloaded broker statuses. | changes through revisioned transitions only. | safe. | durable. | execution state machine. | aggregate lifetime. | Required. |
| `PaperExecutionOperation` | Operation enum. | `SUBMIT`, `CANCEL`, `REPLACE`. | `LIVE`, bulk liquidation, complex multi-leg. | state-changing only. | operation part of command fingerprint. | safe. | serializable. | execution contracts. | command lifetime. | Required. |
| `PaperExecutionMode` | Paper-only mode marker. | `PAPER`. | `LIVE` in initial implementation. | omitted/unknown mode fails closed. | mode part of command and receipt fingerprint. | safe. | serializable. | execution contracts. | all records. | Required. |
| `PaperBrokerOrderReference` | External broker reference. | broker name/classification, broker order id or client id, Paper mode, safe status source. | credentials, account number, raw payload. | never sole internal identity. | linked to logical execution id. | broker id may be safe but still redacted when needed. | durable later. | adapter boundary. | after trusted broker fact. | Required. |
| `PaperExecutionRevision` | Optimistic execution version. | nonnegative integer. | qualification revision as alias. | increments on accepted state transition. | stale expected revision rejects before dispatch. | safe. | durable and indexed. | execution aggregate. | aggregate lifetime. | Required. |
| `PaperExecutionIdempotencyKey` | Deterministic replay key. | stable key string and payload fingerprint. | secrets, raw payload. | same key+payload replays; same key+different payload conflicts. | durable reservation later. | safe if generated from redacted facts. | durable uniqueness required later. | execution application layer. | command lifetime. | Required. |
| `PaperExecutionCorrelationId` | Trace id across qualification, approval, command, receipt, reconciliation. | stable id. | personal data. | carried unchanged. | not used as idempotency key. | safe. | durable. | application boundary. | full lifecycle. | Required. |
| `MarketCapabilityRequest` | Read request for capability validation. | symbol, order type, quantity, prices, time in force, mode, account capability context id. | credentials, broker client. | Paper-only; redacted. | contributes to capability decision fingerprint. | safe. | serializable. | capability port consumer. | before dispatch. | Required. |
| `MarketCapabilityDecision` | Capability allow/deny/unknown result. | allowed flag, code, explanation, capability snapshot id, timestamp, source type. | raw broker payload. | unknown fails closed for state-changing commands. | fingerprint included in command evidence. | safe. | durable later. | capability provider. | before dispatch. | Required. |
| `MarketCapabilityFailure` | Typed capability denial. | code, unsupported field, safe explanation, source. | raw external data with secrets. | non-retryable unless source timeout/read failure. | blocks command before dispatch. | safe. | serializable. | capability provider. | validation failure. | Required. |
| `PaperExecutionReconciliationRequest` | Read-only reconciliation input. | logical execution id, command id, broker refs, correlation id, expected local status. | credentials, mutable clients. | no state-changing operation. | may reference current revision but does not itself submit. | redacted. | durable later. | reconciliation service. | unknown/recovery. | Deferred after F5B. |
| `PaperExecutionReconciliationResult` | Comparison of local and broker truth. | result code, observed broker facts, local facts, recommended transition, operator-action flag. | raw payload, secrets. | cannot invent missing broker evidence. | may permit revisioned recovery transition. | redacted. | durable append-only. | reconciliation service. | recovery. | Deferred after F5B. |

## Command model

State-changing commands:

- `SUBMIT`;
- `CANCEL`;
- `REPLACE`, only with broker-native capability.

Read operations:

- `QUERY_STATUS`;
- `RECONCILE`.

`QUERY_STATUS` and `RECONCILE` should be separate ports, not execution
commands, because they do not create, cancel, or replace broker orders. Keeping
them read-only reduces accidental authority expansion and allows safer retry.

## Operation requirements

| Operation | Required identifiers | Expected revision | Idempotency | Retry | Terminal outcomes | Unknown outcomes | Capability |
|---|---|---|---|---|---|---|---|
| `SUBMIT` | command id, logical id, idempotency key, correlation id | required | same key+payload cannot create second order | only proven pre-dispatch | local rejected, broker rejected, filled eventually, failed terminal | post-dispatch timeout | order type, TIF, quantity, price, session, tradability |
| `CANCEL` | command id, logical id, broker ref, idempotency key | required | repeated cancel may replay or no-op if broker supports | bounded; filled-before-cancel handled | cancelled, filled, broker rejected | cancel timeout | cancellation support |
| `REPLACE` | command id, logical id, old broker ref, replacement intent | required | replacement key binds old and new facts | no blind retry | replaced, filled, broker rejected | replace timeout | native replacement support |
| `QUERY_STATUS` | logical id and broker ref | optional read snapshot revision | no mutation | bounded | observed status only | query timeout | query support |
| `RECONCILE` | logical id, command history, broker refs | current local revision for recommendation | no mutation | bounded | consistent, conflict, unresolved | reconciliation timeout | query/search support |

## Deferred implementation notes

F5B should implement only immutable contracts, enum values, safe validation, and
deterministic fingerprints. It should not implement broker ports, persistence,
runtime wiring, retry loops, reconciliation, or execution authority.
