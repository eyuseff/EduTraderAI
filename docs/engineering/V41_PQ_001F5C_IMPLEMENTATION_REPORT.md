# V41-PQ-001F5C Implementation Report: Execution Eligibility Core

## 1. Executive summary

V41-PQ-001F5C implements a deterministic, pure, synchronous,
side-effect-free Paper execution eligibility core over the immutable F5B
execution contracts. It evaluates whether an immutable Paper execution command
satisfies explicit eligibility criteria. It authorizes nothing and executes
nothing.

## 2. Starting baseline

Starting branch: `feature/edutrader-v4.1`.

Starting HEAD: `01c6f0689d37ea61a544922b29fd6afb99923c65`.

Baseline expectations: V41-PQ-001F5B contracts implemented, ADR-004 accepted,
no executor, no broker adapter, no persistence, no Live support, and exactly
one production Paper shadow-observation call site.

## 3. Scope implemented

- `PaperExecutionEligibilityService`.
- Immutable `PaperExecutionEligibilityPolicy`.
- Immutable `PaperExecutionEligibilityResult`.
- Immutable `PaperExecutionEligibilityCriterionResult`.
- Stable decision, criterion, outcome, severity, and failure-code enums.
- Deterministic eligibility policy and result fingerprints.
- Focused eligibility tests and architecture-boundary tests.

## 4. Scope excluded

No executor, broker adapter, broker call, persistence, durable idempotency
reservation, stale-revision storage check, market-capability evaluation,
market-session evaluation, risk evaluation, account evaluation,
emergency-stop lookup, retry behavior, timeout behavior, reconciliation,
runtime wiring, event publishing, metrics, external logging, UI, API, CLI,
configuration, dependencies, or Live behavior were added.

## 5. ADR-005 summary

ADR-005 is Accepted. It records the Paper execution model, the bounded-context
boundary, the distinction between qualification, readiness, eligibility,
approval evidence, and execution authority, and the rule that eligibility is
advisory only.

## 6. Package structure

The new package is `volcanoes/application/execution/eligibility/`:

- `__init__.py`
- `enums.py`
- `errors.py`
- `policy.py`
- `result.py`
- `service.py`

The root execution package exports approved public eligibility types.

## 7. Public API

Primary API:

```python
PaperExecutionEligibilityService().evaluate(
    command,
    policy,
    evaluated_at=evaluation_timestamp,
)
```

The API consumes immutable F5B execution commands and immutable eligibility
policy objects, then returns an immutable advisory result.

## 8. Eligibility policy

`PaperExecutionEligibilityPolicy` is immutable, deterministic, serializable,
fingerprinted, explicit, and free of callbacks, predicates, services, runtime
references, environment access, and mutable collections.

## 9. Decision model

Top-level decisions are `ELIGIBLE`, `INELIGIBLE`, and `INDETERMINATE`.

## 10. Criterion model

Criterion outcomes are `PASS`, `FAIL`, and `UNRESOLVED`. Each criterion result
includes stable criterion, outcome, severity, code, safe message,
authority-impact flag, external-evidence flag, and related command and aggregate
identities.

## 11. Result model

The result contains command identity, aggregate identity, correlation identity,
policy fingerprint, command payload fingerprint, evaluation timestamp, ordered
criteria, counts, advisory flag, authorization flag, action flag, and result
fingerprint.

## 12. Decision precedence

Decision precedence is deterministic:

1. Invalid API input or contradictory policy raises a typed eligibility error.
2. Any failed deterministic criterion yields `INELIGIBLE`.
3. Otherwise, any unresolved mandatory criterion yields `INDETERMINATE`.
4. Otherwise, all criteria pass and the result is `ELIGIBLE`.

## 13. Time model

The service never reads the system clock. Expiry evaluation uses only an
explicit timezone-aware `evaluated_at` timestamp, normalized to UTC.

## 14. Paper-mode evaluation

The `PAPER_MODE_VALID` criterion requires the command to be structurally Paper
mode when `require_paper_mode=True`. F5B exposes no Live mode.

## 15. Operation evaluation

`OPERATION_ALLOWED` checks the command operation against the deterministic
allowed-operation tuple in the eligibility policy.

## 16. Identity consistency

The service checks aggregate and correlation identity consistency between the
command envelope and command context when required by policy.

## 17. Payload fingerprint verification

The service recomputes the command payload fingerprint with the centralized F5B
canonicalization and compares it with the stored command fingerprint.

## 18. Idempotency representation

The service verifies that an idempotency key is present. Durable reservation is
not implemented. Because F5B does not expose enough public seed material to
recompute every key safely, optional consistency verification returns
`INDETERMINATE` with `IDEMPOTENCY_KEY_UNVERIFIABLE`.

## 19. Revision compatibility

Submit commands must expect execution revision zero when the policy requires an
initial submit revision. Cancel and replace revisions are represented without
storage lookup.

## 20. Intent compatibility

Submit commands require submit intent, replace commands require replacement
intent, and cancel commands carry no intent. The service does not perform
market-capability, tradability, tick-size, lot-size, or account checks.

## 21. Approval evidence

Explicit approval evidence is required by default. Approval evidence does not
authorize execution.

## 22. Approval binding

Approval binding can match the command payload fingerprint or the relevant
operation target fingerprint: submit intent, replace intent, or cancel aggregate
identity.

## 23. Approval expiry

Approval must not be after `evaluated_at`. Expiry is exclusive: an approval with
`expires_at <= evaluated_at` is expired. An approval exactly at `approved_at`
passes.

## 24. Policy snapshot compatibility

The command policy snapshot is checked for stable compatibility facts: operation
allowed, Paper-only required, explicit approval required, execution revision
required, and deterministic idempotency required.

## 25. Context consistency

`CONTEXT_CONSISTENT` confirms that command and context agree on aggregate and
correlation identity. It does not query runtime state.

## 26. External prerequisites

Market capability, emergency-stop clearance, risk clearance, and account
clearance are never evaluated by F5C. If the policy requires them, the result
contains unresolved criterion evidence and becomes `INDETERMINATE` unless a
deterministic failure already makes it `INELIGIBLE`.

## 27. Unresolved evidence model

`UNRESOLVED` means required evidence is outside the pure F5C input and must not
be guessed. External unresolved criteria set `external_evidence_required=True`.

## 28. Determinism

The same command, policy, and evaluation timestamp produce the same decision,
criterion order, criterion results, counts, safe messages, policy fingerprint,
and result fingerprint.

## 29. Purity

The service performs no I/O, mutation, clock reads, randomness, environment
access, file access, network access, broker access, simulator access,
persistence, logging, metrics, or event publication.

## 30. Advisory-only guarantee

Eligibility remains advisory only. `ELIGIBLE` does not authorize execution.

## 31. Architecture boundaries

Architecture tests enforce that qualification and readiness do not import
execution eligibility, that eligibility imports no outward runtime or
infrastructure dependencies, and that no runtime execution call site consumes
eligibility results.

## 32. Tests added

Focused tests cover policy immutability, serialization, fingerprints,
contradictory policies, time behavior, Paper mode, operations, identities,
payload fingerprints, idempotency representation, revisions, intents, approval
evidence, policy snapshots, external prerequisites, decision precedence,
results, determinism, and purity.

## 33. Architecture tests added

Architecture tests were added for qualification/readiness non-dependence,
eligibility outward dependency bans, side-effect token bans, no executor or port
definitions, no Live symbol introduction, and no runtime eligibility consumers.

## 34. Verification results

Verification is recorded in the final task report after Black, Ruff, MyPy,
focused tests, architecture tests, and `make verify` complete.

## 35. Known limitations

- No durable idempotency reservation.
- No persisted stale-revision check.
- No broker availability check.
- No market-session or market-capability evaluation.
- No account, balance, permission, or risk evaluation.
- No emergency-stop lookup.
- No reconciliation.

## 36. Deferred capabilities

Deferred capabilities include deterministic dry-run execution, broker adapter
translation, persistence, durable idempotency, reconciliation, market capability
contracts, runtime wiring, and Live support under a future ADR.

## 37. Risks

The principal risk is that future code could misinterpret `ELIGIBLE` as runtime
authority. ADR-005 and architecture tests explicitly reject that interpretation.

## 38. Next recommended slice

Next recommended slice: V41-PQ-001F5D — deterministic dry-run executor.

## 39. Explicit non-authorization statement

F5C implemented eligibility behavior only. `ELIGIBLE` does not authorize broker
submission, persistence, idempotency reservation, risk clearance, market
clearance, account clearance, emergency-stop clearance, runtime dispatch, or
readiness authority transfer.

## 40. Explicit non-execution statement

No runtime action was executed. No broker was called. No simulator state was
accessed. No simulator mutation occurred. No scanner or supervisor lifecycle
changed. No production runtime wiring was added.
