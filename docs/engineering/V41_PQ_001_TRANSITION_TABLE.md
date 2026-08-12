# V41-PQ-001 Transition Table

## 1. Purpose

This document defines the proposed deterministic transition table for ADR-004. It is design-only and does not implement production behavior.

## 2. State categories

| State | Category | Terminal |
|---|---|---|
| `NOT_STARTED` | Initial | No |
| `PRECHECK_PENDING` | Active | No |
| `PRECHECK_FAILED` | Recoverable failure | No |
| `READY_FOR_APPROVAL` | Waiting | No |
| `APPROVAL_PENDING` | Waiting | No |
| `APPROVED` | Active | No |
| `SUBMISSION_PENDING` | Active | No |
| `SUBMITTED` | Externally uncertain | No |
| `ACKNOWLEDGED` | Waiting | No |
| `PARTIALLY_FILLED` | Waiting | No |
| `FILLED` | Terminal order lifecycle | Scenario-dependent |
| `CANCELLATION_REQUESTED` | Waiting | No |
| `CANCELLED` | Terminal order lifecycle | Scenario-dependent |
| `REJECTED` | Terminal order lifecycle or operator rejection | Scenario-dependent |
| `EXPIRED` | Terminal order lifecycle | Scenario-dependent |
| `UNRESOLVED` | Externally uncertain | No |
| `RECONCILIATION_REQUIRED` | Reconciliation required | No |
| `QUALIFIED` | Terminal success | Yes |
| `DISQUALIFIED` | Terminal failure | Yes |
| `ABORTED` | Terminal failure | Yes |

Terminal workflow states are `QUALIFIED`, `DISQUALIFIED`, and `ABORTED`. Order lifecycle states such as `FILLED`, `CANCELLED`, `REJECTED`, and `EXPIRED` are terminal for the broker order but may still require a final qualification-result transition.

## 3. Transition matrix

| ID | Source state | Event or command | Guard | Destination state | Side effect | Evidence event | Idempotency behavior | Retry classification | Invalid-state behavior | Operator-visible message | Qualification-result impact | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PQ-TRN-001 | `NOT_STARTED` | `START_QUALIFICATION` | Scenario authorized; Paper-only mode selected | `PRECHECK_PENDING` | None beyond creating run intent | `QualificationStarted` | Same key and payload returns existing run | Safe local retry | Reject and preserve state | Qualification prechecks are running. No broker request has been sent. | `PENDING` | Creates `qualification_run_id`. |
| PQ-TRN-002 | `PRECHECK_PENDING` | `PRECHECKS_PASSED` | Paper endpoint, adapter, config, credentials, evidence sink available | `READY_FOR_APPROVAL` | None | `PrechecksPassed` | Replay returns same decision | Safe local retry | Reject and preserve state | Qualification is ready for operator approval. | `PENDING` | No broker request yet. |
| PQ-TRN-003 | `PRECHECK_PENDING` | `PRECHECKS_FAILED` | Failure reason is safe and redacted | `PRECHECK_FAILED` | Block consequential actions | `PrechecksFailed` | Replay returns same failure | Retry after correction | Reject and preserve state | Qualification prechecks did not pass. No broker request was sent. | `FAILED` or `INCONCLUSIVE` | Result depends on scenario. |
| PQ-TRN-004 | `PRECHECK_FAILED` | `START_QUALIFICATION` | New run ID or corrected same-run retry allowed by policy | `PRECHECK_PENDING` | None | `PrecheckRetryStarted` | Same payload may replay; changed payload needs new key | Safe local retry | Reject and preserve state | Qualification prechecks are running. No broker request has been sent. | `PENDING` | No external side effect. |
| PQ-TRN-005 | `READY_FOR_APPROVAL` | `APPROVAL_REQUESTED` | Approval surface available; emergency stop inactive | `APPROVAL_PENDING` | Display approval request | `ApprovalRequested` | Replay returns existing approval request | Safe local retry | Reject and preserve state | Operator approval is required before any broker request. | `PENDING` | Approval scope must include scenario and order intent. |
| PQ-TRN-006 | `APPROVAL_PENDING` | `OPERATOR_APPROVED` | Operator phrase/action valid; plan still current; evidence writable | `APPROVED` | Record approval only | `OperatorApproved` | Replay returns same approval, no second approval | Safe local retry | Reject and preserve state | Operator approval was recorded. No broker request has been sent yet. | `PENDING` | One approval maps to one material action. |
| PQ-TRN-007 | `APPROVAL_PENDING` | `OPERATOR_REJECTED` | Operator rejection captured | `REJECTED` | Block submission | `OperatorRejected` | Replay returns same rejection | Non-retryable in same run | Reject and preserve state | The operator rejected the qualification request. No broker request was sent. | Scenario-dependent `PASSED` or `FAILED` | Rejection-handling scenario may pass. |
| PQ-TRN-008 | `READY_FOR_APPROVAL` | `OPERATOR_REJECTED` | Operator rejection captured | `REJECTED` | Block submission | `OperatorRejected` | Replay returns same rejection | Non-retryable in same run | Reject and preserve state | The operator rejected the qualification request. No broker request was sent. | Scenario-dependent | Supports rejection before explicit approval screen. |
| PQ-TRN-009 | `APPROVED` | `SUBMISSION_STARTED` | Approval not expired; no duplicate key; state revision matches | `SUBMISSION_PENDING` | Prepare broker command | `SubmissionStarted` | Replay returns same state | Safe local retry before send | Reject and preserve state | A broker request is being prepared. | `PENDING` | No broker request yet. |
| PQ-TRN-010 | `SUBMISSION_PENDING` | `BROKER_REQUEST_SENT` | Broker capability available; idempotency key unused for different payload | `SUBMITTED` | Send exactly one broker request | `BrokerRequestSent` | Same command never sends twice; returns recorded attempt | Unsafe external retry unless durable idempotency proves safe | Reject and preserve state | The request was sent. Broker acknowledgment is pending. | `PENDING` | If response is lost, move unresolved. |
| PQ-TRN-011 | `SUBMITTED` | `BROKER_ACKNOWLEDGED` | Broker response matches run/order identity | `ACKNOWLEDGED` | Record broker reference | `BrokerAcknowledged` | Duplicate ack returns recorded ack | Safe read/event replay | Reject or reconcile | The broker acknowledged the order. The order has not necessarily filled. | `PENDING` | Acknowledgment is not fill. |
| PQ-TRN-012 | `ACKNOWLEDGED` | `BROKER_PARTIAL_FILL_REPORTED` | Broker fill quantity > 0 and < order quantity | `PARTIALLY_FILLED` | Record partial fill | `BrokerPartialFillReported` | Duplicate same fill ignored/replayed | Safe event replay | Reject or reconcile | The broker reported a partial fill. | Scenario-dependent | May disqualify zero-fill scenario. |
| PQ-TRN-013 | `ACKNOWLEDGED` | `BROKER_FILL_REPORTED` | Broker full fill evidence present | `FILLED` | Record fill | `BrokerFillReported` | Duplicate fill replayed | Safe event replay | Reject or reconcile | The broker reported the full fill. | Scenario-dependent | Not automatically `QUALIFIED`. |
| PQ-TRN-014 | `PARTIALLY_FILLED` | `BROKER_FILL_REPORTED` | Remaining quantity filled | `FILLED` | Record final fill | `BrokerFillReported` | Duplicate fill replayed | Safe event replay | Reject or reconcile | The broker reported the full fill. | Scenario-dependent | Full fill after partial. |
| PQ-TRN-015 | `ACKNOWLEDGED` | `CANCELLATION_REQUESTED` | Cancellation supported; no terminal broker state observed | `CANCELLATION_REQUESTED` | Send cancellation request | `CancellationRequested` | Same command never cancels twice; returns recorded request | Idempotent external retry only with broker-safe key | Reject and preserve state | Cancellation was requested but has not yet been confirmed. | `PENDING` | Confirmation required. |
| PQ-TRN-016 | `PARTIALLY_FILLED` | `CANCELLATION_REQUESTED` | Cancellation supported for remainder | `CANCELLATION_REQUESTED` | Send cancellation request | `CancellationRequested` | Same command never cancels twice | Idempotent external retry only | Reject and preserve state | Cancellation was requested but has not yet been confirmed. | Scenario-dependent | Partial-fill cleanup path. |
| PQ-TRN-017 | `CANCELLATION_REQUESTED` | `BROKER_CANCELLATION_CONFIRMED` | Broker cancellation confirmation matches order | `CANCELLED` | Record cancellation | `BrokerCancellationConfirmed` | Duplicate confirmation replayed | Safe event replay | Reject or reconcile | The broker confirmed cancellation. | Scenario-dependent | Required for no-open-order scenarios. |
| PQ-TRN-018 | `SUBMITTED` | `BROKER_REJECTED` | Broker rejection matches request | `REJECTED` | Record broker rejection | `BrokerRejected` | Duplicate rejection replayed | Safe event replay | Reject or reconcile | The broker rejected the request. | Scenario-dependent | Broker rejection scenario may pass. |
| PQ-TRN-019 | `ACKNOWLEDGED` | `BROKER_REJECTED` | Broker rejection matches order and lifecycle permits | `REJECTED` | Record broker rejection | `BrokerRejected` | Duplicate rejection replayed | Safe event replay | Reject or reconcile | The broker rejected the request. | Scenario-dependent | Handles late rejection. |
| PQ-TRN-020 | `SUBMITTED` | `BROKER_EXPIRED` | Broker expiration matches request | `EXPIRED` | Record expiration | `BrokerExpired` | Duplicate expiration replayed | Safe event replay | Reject or reconcile | The broker reported that the order expired. | Scenario-dependent | Not automatic failure. |
| PQ-TRN-021 | `ACKNOWLEDGED` | `BROKER_EXPIRED` | Broker expiration matches order | `EXPIRED` | Record expiration | `BrokerExpired` | Duplicate expiration replayed | Safe event replay | Reject or reconcile | The broker reported that the order expired. | Scenario-dependent | Used for non-marketable orders. |
| PQ-TRN-022 | `SUBMITTED` | `TIMEOUT_DETECTED` | Broker outcome unknown after send | `UNRESOLVED` | Block duplicate submission | `SubmissionTimeoutUnresolved` | Replay returns unresolved | Read/reconcile only | Reject and preserve state | The final broker state cannot currently be confirmed. | `INCONCLUSIVE` | Never blindly retry submit. |
| PQ-TRN-023 | `SUBMISSION_PENDING` | `TIMEOUT_DETECTED` | Cannot prove whether broker request was sent | `UNRESOLVED` | Block duplicate submission | `SubmissionPreparationTimeout` | Replay returns unresolved | Reconcile before retry | Reject and preserve state | The final broker state cannot currently be confirmed. | `INCONCLUSIVE` | Conservative safe failure. |
| PQ-TRN-024 | `UNRESOLVED` | `RECONCILIATION_STARTED` | Read-only broker reconciliation available | `RECONCILIATION_REQUIRED` | Perform read-only reconciliation | `ReconciliationStarted` | Replay returns active reconciliation | Safe read retry | Reject and preserve state | Broker reconciliation is required before qualification can continue. | `INCONCLUSIVE` | No write/order side effect. |
| PQ-TRN-025 | `RECONCILIATION_REQUIRED` | `RECONCILIATION_RESOLVED` | Broker truth found and evidence complete | `ACKNOWLEDGED` | Record reconciled broker state | `ReconciliationResolvedAcknowledged` | Duplicate replayed | Safe read/event replay | Reject and preserve state | The broker acknowledged the order. The order has not necessarily filled. | `PENDING` | Destination may vary by broker truth. |
| PQ-TRN-026 | `RECONCILIATION_REQUIRED` | `RECONCILIATION_RESOLVED` | Broker proves cancellation | `CANCELLED` | Record reconciled cancellation | `ReconciliationResolvedCancelled` | Duplicate replayed | Safe read/event replay | Reject and preserve state | The broker confirmed cancellation. | Scenario-dependent | No inferred completion. |
| PQ-TRN-027 | `RECONCILIATION_REQUIRED` | `RECONCILIATION_RESOLVED` | Broker proves rejection or no order created | `REJECTED` | Record reconciled rejection/no-order | `ReconciliationResolvedRejected` | Duplicate replayed | Safe read/event replay | Reject and preserve state | The request was rejected or no broker order was found. | Scenario-dependent | Negative scenario may pass. |
| PQ-TRN-028 | `RECONCILIATION_REQUIRED` | `QUALIFICATION_CRITERIA_FAILED` | Reconciliation failed or evidence incomplete | `DISQUALIFIED` | Finalize failed run | `QualificationDisqualified` | Replay returns final result | Non-retryable in same run | Reject and preserve state | The qualification run did not meet the approved criteria. | `FAILED` | Terminal. |
| PQ-TRN-029 | `ACKNOWLEDGED` | `QUALIFICATION_CRITERIA_MET` | Scenario requires only acknowledgment and all evidence exists | `QUALIFIED` | Finalize successful run | `QualificationPassed` | Replay returns final result | Non-retryable in same run | Reject and preserve state | The approved Paper qualification criteria were completed successfully. | `PASSED` | Only for ack-only scenario. |
| PQ-TRN-030 | `CANCELLED` | `QUALIFICATION_CRITERIA_MET` | Scenario requires cancellation/no-open-order/no-position evidence | `QUALIFIED` | Finalize successful run | `QualificationPassed` | Replay returns final result | Non-retryable in same run | Reject and preserve state | The approved Paper qualification criteria were completed successfully. | `PASSED` | Expected for one-share non-marketable smoke. |
| PQ-TRN-031 | `FILLED` | `QUALIFICATION_CRITERIA_MET` | Scenario requires fill and fill evidence exists | `QUALIFIED` | Finalize successful run | `QualificationPassed` | Replay returns final result | Non-retryable in same run | Reject and preserve state | The approved Paper qualification criteria were completed successfully. | `PASSED` | Fill scenario only. |
| PQ-TRN-032 | `REJECTED` | `QUALIFICATION_CRITERIA_MET` | Scenario is a rejection-handling scenario and rejection evidence exists | `QUALIFIED` | Finalize successful negative scenario | `QualificationPassed` | Replay returns final result | Non-retryable in same run | Reject and preserve state | The approved Paper qualification criteria were completed successfully. | `PASSED` | System behavior can pass on rejection scenario. |
| PQ-TRN-033 | Any non-terminal | `QUALIFICATION_CRITERIA_FAILED` | Required evidence or lifecycle criterion failed | `DISQUALIFIED` | Finalize failed run | `QualificationDisqualified` | Replay returns final result | Non-retryable in same run | Reject and preserve state | The qualification run did not meet the approved criteria. | `FAILED` | No further mutation. |
| PQ-TRN-034 | Any non-terminal | `ABORT_REQUESTED` | Actor authorized to abort; no unsafe broker side effect in progress or reconciliation path recorded | `ABORTED` | Block future commands for this run | `QualificationAborted` | Replay returns aborted result | Non-retryable in same run | Reject and preserve state | Qualification was aborted. No further action will occur in this run. | `ABORTED` | If broker state is unknown, first move unresolved/reconcile. |
| PQ-TRN-035 | Any persisted active state | `PROCESS_RESTARTED` | Durable state/evidence loaded and hash verified | Same logical state or `RECONCILIATION_REQUIRED` | Resume or require reconciliation | `QualificationRecovered` | Repeat restart is safe | Safe recovery/read retry | Reject if evidence corrupt | Qualification state was recovered from evidence. | Existing result or `INCONCLUSIVE` | V41-PQ-002 implementation requirement. |


## Sentinel correction: narrowed general transitions

Rows that use broad source wording are templates, not permission for arbitrary mutation:

- PQ-TRN-033 applies only to non-terminal states after scenario criteria can be evaluated from complete evidence. It may not bypass `RECONCILIATION_REQUIRED` when broker state is unknown.
- PQ-TRN-034 applies only when aborting will not hide an uncertain broker side effect. If a broker request may have crossed the external boundary, the run must first enter `UNRESOLVED` or `RECONCILIATION_REQUIRED`.
- PQ-TRN-035 is a recovery template for persisted active states. It is not implemented as restart durability until V41-PQ-002 exists.

## Sentinel correction: explicit failure destinations

| Transition group | Failure before external effect | Failure after possible external effect | Evidence failure |
|---|---|---|---|
| Precheck and approval | Preserve source or move to `PRECHECK_FAILED` / `REJECTED` as specified | Not applicable | Preserve source and report evidence unavailable |
| Submission preparation | Preserve source if broker request provably not sent | `UNRESOLVED` | `UNRESOLVED` if send status is uncertain |
| Broker request sent | Not applicable | `UNRESOLVED` or `RECONCILIATION_REQUIRED` | `UNRESOLVED` and block duplicate submission |
| Broker lifecycle observation | Preserve source for invalid event; reconcile for plausible conflicting broker event | `RECONCILIATION_REQUIRED` | Preserve source or require reconciliation if evidence loss affects broker truth |
| Cancellation | Preserve source if cancellation provably not sent | `UNRESOLVED` or `RECONCILIATION_REQUIRED` | `UNRESOLVED` if cancellation side effect is uncertain |
| Finalization | Preserve source and keep result pending/inconclusive | Not applicable | Block `QUALIFIED` / `DISQUALIFIED` until evidence exists |

## 4. Invalid-transition examples

Invalid transitions must be rejected deterministically, preserve the current state, produce diagnostic evidence where possible, perform no transition side effects, return a typed error, and avoid leaking credentials or sensitive broker payloads.

Invalid examples:

- `NOT_STARTED` directly to `QUALIFIED`.
- `PRECHECK_FAILED` to `SUBMISSION_PENDING`.
- `READY_FOR_APPROVAL` to `SUBMITTED` without approval.
- `APPROVED` directly to `ACKNOWLEDGED` without submission evidence.
- `SUBMITTED` directly to `FILLED` without broker lifecycle evidence.
- `CANCELLATION_REQUESTED` directly to `CANCELLED` without broker confirmation.
- `UNRESOLVED` directly to `QUALIFIED` without reconciliation.
- `REJECTED` to `FILLED`.
- Terminal state mutation without a new qualification run.
- Repeated approval producing a second order.
- Repeated submission producing a duplicate broker request.

## 5. Event-ordering rules

- Approval events are valid only after prechecks pass and approval is requested or the run is ready for approval.
- Submission events are valid only after approval.
- Broker acknowledgment is valid only after a broker request is sent or reconciled.
- Fill, rejection, expiration, and cancellation events must match the broker order identity or reconciliation proof.
- Cancellation confirmation is valid only after cancellation request or reconciliation proof.
- Qualification success requires scenario-specific terminal evidence, not merely a locally generated order ID.

## 6. Duplicate-event behavior

Duplicate events with the same identity and equivalent payload return the previously recorded transition decision and do not increment state revision. Duplicate events with the same identity and conflicting payload fail with an idempotency conflict and no side effect.

## 7. Out-of-order-event behavior

Out-of-order events are rejected if harmless and moved to `RECONCILIATION_REQUIRED` if they imply the broker may have changed state outside the expected local sequence. Example: a fill reported before acknowledgment must not be ignored if it contains a valid broker order reference; it should trigger reconciliation.

## 8. Reconciliation transitions

Reconciliation transitions are read-only with respect to the broker. They may update qualification state only after broker truth is observed and evidence is recorded. They must never submit, cancel, or replace an order unless a separate operator-approved command authorizes that action.

## 9. Restart transitions

`PROCESS_RESTARTED` must load the last committed state and evidence. If state and evidence agree, resume from the recorded state. If the last consequential side effect cannot be proven, move to `RECONCILIATION_REQUIRED` or `UNRESOLVED`. If evidence is corrupt, fail closed and require operator review.
