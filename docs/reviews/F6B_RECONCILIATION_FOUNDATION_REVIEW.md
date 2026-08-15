# F6B Reconciliation Foundation Review

## Scope

This review covers only the pure read-first reconciliation foundation introduced on `feature/f6b-reconciliation-foundation`.

## Acceptance checks

- [x] Reconciliation remains read-only and deterministic.
- [x] No broker adapter, broker credential, simulator access, runtime wiring, or dispatch path is introduced.
- [x] The eight ADR-006 reconciliation outcomes remain the bounded classification surface.
- [x] Recovery proposals are limited to the seven ADR-006 destinations.
- [x] Incomplete evidence fails closed to continued reconciliation.
- [x] Broker-reference conflicts require operator action.
- [x] Fill-quantity conflicts require operator action.
- [x] Missing local or broker orders do not invent state.
- [x] `OUTCOME_UNKNOWN` may advance only when broker evidence proves a permitted destination.
- [x] Automatic redispatch is absent.

## Remaining F6B work

This foundation does not complete F6B. Remaining review-critical work includes durable reconciliation history, exact replay semantics, adversarial concurrency, corruption handling, crash/fault-injection matrices, and operator recovery command persistence. Those should be implemented and validated in subsequent isolated slices.
