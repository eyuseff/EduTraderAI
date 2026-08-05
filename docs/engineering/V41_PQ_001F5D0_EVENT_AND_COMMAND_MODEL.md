# V41-PQ-001F5D0 Event and Command Model

## Purpose

Separate lifecycle inputs from lifecycle states before implementation. This is
design only.

Sentinel review status: accepted as part of ADR-006 acceptance on 2026-08-04.

## Input categories

| Category | Examples | Owner | Notes |
|---|---|---|---|
| Operator/application commands | `CREATE_AGGREGATE`, `RECORD_APPROVAL`, `REQUEST_CANCELLATION`, `REQUEST_REPLACEMENT`, `ABORT_BEFORE_DISPATCH` | Application boundary | Must include expected execution revision where state-changing. |
| Eligibility recording commands | `RECORD_ELIGIBILITY`, `RECORD_INELIGIBLE`, `RECORD_INDETERMINATE` | Future lifecycle application service | Consume F5C results explicitly; eligibility never mutates automatically. |
| Persistence/idempotency commands | `RESERVE_IDEMPOTENCY` | Future persistence layer | Must be durable before broker side effects. |
| Internal lifecycle events | `PREPARE_DISPATCH`, `BEGIN_DISPATCH`, `RECORD_DISPATCH`, `FAIL_TERMINALLY` | Future execution orchestrator | May carry future side-effect intent, but does not execute by itself. |
| Broker observations | `OBSERVE_BROKER_ACKNOWLEDGEMENT`, `OBSERVE_BROKER_REJECTION`, `OBSERVE_PARTIAL_FILL`, `OBSERVE_FILL`, `OBSERVE_CANCELLATION`, `OBSERVE_REPLACEMENT` | Broker adapter observation | Observations propose facts; lifecycle accepts or rejects them. |
| Reconciliation observations | `REQUIRE_RECONCILIATION`, `RECORD_RECONCILIATION_CONSISTENT`, `RECORD_RECONCILIATION_BROKER_AHEAD`, `RECORD_RECONCILIATION_CONFLICTING` | Reconciliation service | Read-only comparison facts until accepted. |

## Proposed lifecycle inputs

- `CREATE_AGGREGATE`
- `RECORD_ELIGIBILITY`
- `RECORD_INELIGIBLE`
- `RECORD_INDETERMINATE`
- `RECORD_APPROVAL`
- `RESERVE_IDEMPOTENCY`
- `PREPARE_DISPATCH`
- `BEGIN_DISPATCH`
- `RECORD_DISPATCH`
- `OBSERVE_BROKER_ACKNOWLEDGEMENT`
- `OBSERVE_BROKER_REJECTION`
- `OBSERVE_PARTIAL_FILL`
- `OBSERVE_FILL`
- `REQUEST_CANCELLATION`
- `RECORD_CANCELLATION_DISPATCH`
- `OBSERVE_CANCELLATION`
- `REQUEST_REPLACEMENT`
- `RECORD_REPLACEMENT_DISPATCH`
- `OBSERVE_REPLACEMENT`
- `MARK_OUTCOME_UNKNOWN`
- `REQUIRE_RECONCILIATION`
- `RECORD_RECONCILIATION_CONSISTENT`
- `RECORD_RECONCILIATION_BROKER_AHEAD`
- `RECORD_RECONCILIATION_CONFLICTING`
- `ABORT_BEFORE_DISPATCH`
- `FAIL_TERMINALLY`

## Command facts required later

Future lifecycle commands must carry:

- aggregate identity;
- command identity;
- correlation identity;
- idempotency key where applicable;
- expected execution revision;
- command payload fingerprint;
- input type;
- safe source reference;
- explicit timestamp supplied by caller;
- Paper mode;
- optional receipt/failure/reconciliation fingerprint.

## Event facts required later

Future lifecycle events should record:

- transition ID;
- previous state;
- next state;
- previous revision;
- next revision;
- accepted/rejected classification;
- replay classification;
- side-effect intent classification;
- evidence intent classification;
- reconciliation requirement;
- terminality impact;
- safe reason code.

## Boundary rules

- Broker observations are not commands issued by the application.
- Application commands do not fabricate broker observations.
- Eligibility results are recorded inputs, not automatic mutation.
- Command creation is not dispatch.
- Dispatch record is not broker acknowledgement.
- Broker acknowledgement is not fill.
- Cancellation request is not cancellation.
- Replacement request is not replacement.

## Future side-effect intent labels

The lifecycle may later emit side-effect intent labels such as
`WOULD_DISPATCH`, `REQUEST_BROKER_SUBMIT`, `REQUEST_BROKER_CANCEL`, or
`REQUEST_BROKER_REPLACE`. F5D0 does not implement those intents, and no
transition authorizes execution by itself.
