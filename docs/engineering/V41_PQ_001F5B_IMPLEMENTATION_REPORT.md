# V41-PQ-001F5B Implementation Report

## 1. Executive summary

V41-PQ-001F5B implements the immutable contract vocabulary for the future Paper
execution bounded context.

The governing rule was:

```text
DEFINE EXECUTION PRECISELY.
EXECUTE NOTHING.
```

The slice adds strongly typed identities, a dedicated execution revision,
Paper-only enums, immutable instrument/intent/approval/policy/context/command/
receipt/failure contracts, centralized canonical serialization, centralized
SHA-256 fingerprinting, architecture-boundary tests, and focused contract
tests.

No executor, eligibility service, broker adapter, runtime wiring, persistence,
approval-decision logic, stale-revision enforcement, idempotency reservation,
market-capability evaluation, retry behavior, reconciliation behavior, metrics,
event publishing, UI, API, CLI, simulator access, broker call, or Live behavior
was added.

## 2. Starting baseline

- Branch: `feature/edutrader-v4.1`.
- Starting HEAD: `41bb6072d709c06226c2e571b617b8507396e3be`.
- Expected unrelated unstaged file: `state/simulated_broker.json`.
- F5A architecture review completed.
- V41-PQ-001 overall remained in progress.

## 3. Scope implemented

Implemented:

- `volcanoes/application/execution/` package.
- Immutable execution identity classes.
- Dedicated immutable execution revision.
- Paper-only enum vocabulary.
- Immutable inert execution contracts.
- Central deterministic canonical JSON serialization.
- Central SHA-256 fingerprint generation.
- Safe construction errors.
- Focused tests for identities, canonicalization, contracts, receipts, and
  failures.
- Architecture fitness tests for the new execution package.

## 4. Scope excluded

Excluded:

- executor implementation;
- eligibility evaluation;
- approval evaluation;
- idempotency reservation;
- stale-revision behavior;
- persistence;
- broker integration;
- market-capability evaluation;
- retry orchestration;
- timeout handling;
- reconciliation behavior;
- runtime wiring;
- event publishing;
- metrics;
- logging;
- UI, API, or CLI;
- Live enablement.

## 5. Package structure

```text
volcanoes/application/execution/
    __init__.py
    _canonical.py
    enums.py
    errors.py
    fingerprints.py
    identities/
        __init__.py
        _base.py
        aggregate_id.py
        broker_reference.py
        command_id.py
        correlation_id.py
        idempotency_key.py
        revision.py
    contracts/
        __init__.py
        _validation.py
        approval.py
        command.py
        context.py
        failure.py
        instrument.py
        intent.py
        policy.py
        receipt.py
```

## 6. Public exports

`volcanoes/application/execution/__init__.py` exports explicit public types:

- `PaperExecutionCommandId`
- `PaperExecutionCorrelationId`
- `PaperExecutionIdempotencyKey`
- `PaperExecutionAggregateId`
- `PaperExecutionRevision`
- `PaperBrokerOrderReference`
- `PaperExecutionOperation`
- `PaperExecutionMode`
- `PaperExecutionSide`
- `PaperExecutionOrderType`
- `PaperExecutionTimeInForce`
- `PaperExecutionStatus`
- `PaperExecutionReceiptKind`
- `PaperExecutionFailureKind`
- `PaperExecutionFailureSeverity`
- `PaperExecutionApprovalKind`
- `PaperExecutionInstrument`
- `PaperExecutionIntent`
- `PaperExecutionApproval`
- `PaperExecutionPolicySnapshot`
- `PaperExecutionContext`
- `PaperExecutionCommand`
- `PaperExecutionReceipt`
- `PaperExecutionFailure`
- safe local error classes.

Internal canonicalization and digest helpers are not exported from the package
root.

## 7. Canonicalization model

`volcanoes/application/execution/_canonical.py` is the single authority for
deterministic serialization. It provides:

- `canonicalize(value)`
- `canonical_json_bytes(value)`
- `canonical_json_text(value)`
- `normalize_decimal(value)`
- `normalize_datetime(value)`
- `normalize_text(value)`

The model uses stable mapping-key ordering, enum values, Decimal normalization,
UTC-aware datetime normalization, explicit `None`, tuple/list normalization,
Unicode NFC normalization, JSON-safe primitives, and compact sorted JSON.

It rejects floats, NaN, infinite Decimals, naive datetimes, nondeterministic
sets, non-text mapping keys, dataclasses without `to_primitive()`, unsupported
object types, Python `hash()`, repr-based hashing, memory addresses, random
salt, and locale-dependent output.

## 8. Fingerprint model

`volcanoes/application/execution/fingerprints.py` centralizes SHA-256
fingerprinting over canonical bytes.

Prefixes:

- `pec-` command identity
- `pcf-` command payload fingerprint
- `pcr-` correlation identity
- `pik-` idempotency key
- `pea-` aggregate identity
- `pbr-` broker reference
- `pap-` approval fingerprint
- `pps-` policy snapshot fingerprint
- `prc-` receipt fingerprint
- `pfl-` failure fingerprint

Fingerprints use lowercase 64-character SHA-256 hex digests with exact
three-letter prefixes.

## 9. Command identity model

`PaperExecutionCommandId` identifies one immutable command envelope. Its
external form is `pec-<sha256>`.

## 10. Payload fingerprint distinction

`PaperExecutionCommand` stores both:

- `command_id`, identifying the envelope; and
- `payload_fingerprint`, identifying immutable command content.

This supports future persistence distinctions:

- same command ID + same payload → deterministic replay;
- same command ID + different payload → duplicate conflict;
- different command ID + same logical operation → idempotency replay.

F5B represents the data only. It does not implement persistence or replay.

## 11. Correlation identity model

`PaperExecutionCorrelationId` links related Paper execution facts. Its external
form is `pcr-<sha256>`.

## 12. Idempotency model

`PaperExecutionIdempotencyKey` represents one logical state-changing operation.
Its external form is `pik-<sha256>`. F5B provides deterministic construction but
does not reserve, persist, replay, or enforce idempotency.

## 13. Aggregate identity model

`PaperExecutionAggregateId` represents one logical Paper order lifecycle. Its
external form is `pea-<sha256>`.

## 14. Broker-reference model

`PaperBrokerOrderReference` represents a redacted opaque Paper broker order
reference. Its external form is `pbr-<sha256>`. It is not required on
pre-submission commands and is never the sole internal identity.

## 15. Execution revision model

`PaperExecutionRevision` is a dedicated execution revision, separate from
qualification revision and broker version. It is integer-backed, non-negative,
immutable, hashable, and supports `initial()` and `next()`. F5B does not enforce
stale-revision behavior.

## 16. Paper-only model

`PaperExecutionMode` contains exactly one member: `PAPER`.

There is no `LIVE`, `PRODUCTION`, or `REAL_MONEY` execution mode. Commands and
receipts carry Paper mode explicitly.

## 17. Instrument model

`PaperExecutionInstrument` stores broker-neutral symbol, asset class, currency,
and optional venue. It normalizes symbols, bounds length, rejects unsafe
characters, and makes no tradability or Chilean-market rule claim.

## 18. Intent model

`PaperExecutionIntent` stores instrument, side, order type, quantity, time in
force, optional prices, and safe optional references. It requires Decimal
quantity/prices, positive finite values, broker-neutral fields, and universal
order-shape invariants.

Supported order types:

- `MARKET`
- `LIMIT`
- `STOP`
- `STOP_LIMIT`

Supported time-in-force values:

- `DAY`
- `GTC`

F5B does not validate tick size, lot size, market session, symbol tradability,
or venue support.

## 19. Approval model

`PaperExecutionApproval` is immutable approval evidence. It records approval
kind, approver reference, approval reference, bound fingerprint, timestamps,
and deterministic `pap-` fingerprint. It does not approve, authorize, revoke,
authenticate, or perform permission lookup.

## 20. Policy snapshot model

`PaperExecutionPolicySnapshot` captures descriptive policy facts only. It
normalizes allowed operations deterministically and computes a `pps-`
fingerprint. It has no predicate, callback, service reference, or evaluation
method.

## 21. Context model

`PaperExecutionContext` contains aggregate ID, correlation ID, source component,
requested timestamp, safe optional references, and immutable safe metadata. It
rejects sensitive metadata keys and values.

## 22. Command model

`PaperExecutionCommand` is inert immutable data. It contains command ID,
aggregate ID, correlation ID, idempotency key, operation, expected execution
revision, approval, policy snapshot, context, optional intent/replacement
intent, Paper mode, and payload fingerprint.

Supported state-changing operations:

- `SUBMIT`
- `CANCEL`
- `REPLACE`

`QUERY_STATUS` and `RECONCILE` remain future read-only ports and are not command
operations.

## 23. Status model

`PaperExecutionStatus` defines normalized status vocabulary without a transition
engine. It separates lifecycle states from receipt kind and broker raw status.

## 24. Receipt model

`PaperExecutionReceipt` is an immutable normalized observation. It records
command, aggregate, correlation, operation, receipt kind, normalized status,
observed execution revision, optional broker reference, observed time, message
code, outcome-known flag, reconciliation-required flag, Paper mode, and
deterministic `prc-` fingerprint.

Acknowledgement, partial fill, full fill, cancellation, replacement, unknown
outcome, and reconciliation-required facts are distinct.

## 25. Failure model

`PaperExecutionFailure` is immutable normalized failure data, not an exception
wrapper. It records kind, severity, stable code, safe message, retryable flag,
reconciliation requirement, operator-action requirement, terminality, authority
impact, optional identities, and deterministic `pfl-` fingerprint.

Retryability is descriptive only. No retry behavior exists.

## 26. Exception model

Local construction and invariant errors:

- `PaperExecutionContractError`
- `PaperExecutionIdentityError`
- `PaperExecutionRevisionError`
- `PaperExecutionInvariantError`
- `PaperExecutionSerializationError`

Broker failures are not modeled as local exceptions in F5B.

## 27. Sensitive-data protections

Contracts reject sensitive terms in aliases, metadata, receipt message codes,
and failure safe messages. Commands, approvals, receipts, failures, contexts,
canonical serialization, and fingerprints do not accept credentials, raw broker
payloads, authorization headers, cookies, private keys, session tokens, API
keys, database handles, broker clients, or runtime objects.

## 28. Architecture boundaries

Architecture tests prove:

- qualification does not import execution;
- readiness does not import execution;
- execution does not import qualification runtime integration;
- execution does not import adapters, brokers, simulators, scanners,
  supervisors, persistence, event publishers, logging, metrics, HTTP clients,
  or broker SDKs;
- execution does not read environment variables;
- no Live execution mode exists;
- no executor class exists;
- no runtime Paper execution call site exists;
- the existing shadow-observation call-site rule remains intact.

## 29. Focused tests

Added focused tests:

- `tests/test_paper_execution_identities.py`
- `tests/test_paper_execution_canonicalization.py`
- `tests/test_paper_execution_contracts.py`
- `tests/test_paper_execution_receipts.py`
- `tests/test_paper_execution_failures.py`

Focused execution tests passed: 147.

## 30. Architecture tests

Architecture tests passed: 59.

## 31. Verification results

Focused verification before full release verification:

- Black check: PASS.
- Ruff check: PASS.
- MyPy on `volcanoes/application/execution`: PASS.
- Focused execution tests: 147 passed.
- Architecture tests: 59 passed.

Full verification:

- `make verify`: PASS.
- Full pytest: 1149 passed.
- Architecture tests: 59 passed.
- Coverage: 84.7%.

## 32. Known limitations

- No executor exists.
- No eligibility service exists.
- No approval-decision logic exists.
- No persistence or idempotency reservation exists.
- No stale-revision enforcement exists.
- No market-capability evaluation exists.
- No broker adapter exists.
- No runtime wiring exists.
- No reconciliation behavior exists.

## 33. Deferred behavior

Deferred to later slices:

- F5C execution eligibility core;
- F5D deterministic dry-run executor;
- F5E persistence and idempotency foundation;
- F5F adapter certification harness;
- F6A controlled Paper broker submission;
- F6B reconciliation and recovery;
- F6C execution observation and audit.

## 34. Risks

Main remaining risks are accidental authority transfer, duplicate execution
without durable idempotency, stale command execution without enforcement,
adapter leakage, unsupported market capabilities, timeout ambiguity,
reconciliation gaps, approval misuse, and dual legacy/new execution.

F5B reduces vocabulary ambiguity but does not mitigate side-effect risks by
itself.

## 35. Recommended next slice

V41-PQ-001F5C — Execution Eligibility Core.

F5C should remain pure and broker-free. It should consume F5B contracts and
evaluate Paper-only, approval-evidence, expected-revision, idempotency-field,
emergency-stop-input, and market-capability-decision presence without executing
or reserving anything.

## 36. Explicit non-execution statement

F5B implemented contracts only. No executor was implemented. No eligibility
service was implemented. No approval evaluation was implemented. No persistence
was implemented. No idempotency reservation was implemented. No stale-revision
behavior was implemented. No broker adapter was implemented. No broker was
called. No runtime wiring was added. No readiness result became authority. No
simulator state was accessed. No Live behavior was added.

V41-PQ-001 remains incomplete.
