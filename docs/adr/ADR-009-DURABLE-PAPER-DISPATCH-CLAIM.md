# ADR-009: Durable Paper Dispatch Claim

Status: Accepted for F6A

## Decision

SQLite is the sole authoritative election mechanism for controlled Paper dispatch. A
caller supplies only a submission identity and the durable command identity. Guard
facts and order payload facts are never accepted from the caller. The claim
transaction loads the control row, command, aggregate, idempotency reservation,
approval, and policy bindings; validates the command's duplicate-key-free canonical
JSON and payload fingerprint; derives the complete immutable `ControlledPaperOrder`;
and attempts one append-only claim insert.

The control row is created fail closed with `enabled = 0`, `paper_mode = 1`,
`emergency_stop_active = 1`, `legacy_authority_active = 1`, and `generation = 1`.
Mutation requires an exact generation compare-and-swap. Claims never expire and
cannot be released, reassigned, taken over, or retried automatically.

Only the transaction that inserts and commits a claim receives an opaque in-process
winner grant. An exact replay, an existing claim, a losing connection, or a fresh
process receives durable evidence but no effect authority.

The winner opens a second short transaction. That transaction rereads the
authoritative control row, requires the same generation and a dispatch-permitting
state, and inserts exactly one append-only authorization. Its commit is the
emergency-stop linearization point. A stop committed before this transaction reads
control prevents authorization and therefore prevents the effect. A stop committed
after authorization cannot retract the already granted one-shot effect; this is the
documented limit of F6A.

No local transaction remains open while the supplied synthetic one-shot effect
boundary is invoked. Runtime composition and concrete broker adapters are outside
F6A.

After the effect returns or raises, a third short transaction atomically records the
append-only resolution, broker-reference ownership, and all available observation or
failure fingerprints. A recording failure is reported as `OUTCOME_UNKNOWN`; every
broker reference and evidence fingerprint already observed remains in the returned
result. Automatic retry is always false.

For a broker-reference ownership conflict, the third transaction captures the exact
authoritative existing owner's aggregate ID, command ID, and immutable ownership
record fingerprint. Those values are part of the durable resolution and its
fingerprint. The same transaction revalidates the complete tuple immediately before
resolution insertion. Startup and replay require the current ownership row to match
that recorded tuple exactly; merely belonging to some different aggregate and
command is insufficient. Conflict recording never rewrites or transfers ownership.

## Canonical command and client-order identity

The order is derived from the committed command JSON. Parsing rejects duplicate
keys, requires the exact submission schema, requires byte-for-byte canonical JSON,
and recomputes the `pcf` payload fingerprint. The schema binds operation, Paper
mode, instrument, asset class, currency, venue, side, quantity, order type, time in
force, and the order-type-specific price fields. The durable command envelope binds
command, aggregate, correlation, idempotency, approval, policy, and expected
revision.

Client-order identity uses the project's deterministic domain-separated canonical
encoding with domain `paper-client-order-v1` and inputs submission ID, command ID,
idempotency key, and canonical payload fingerprint. It is `paper-` followed by the
first 42 lowercase hexadecimal SHA-256 characters (48 characters total), and is
stable across processes, connections, and restarts.

## Crash windows and recovery

A crash after claim commit but before authorization permanently blocks automatic
redispatch. A crash after authorization commit, including during or after the
external effect, also permanently blocks automatic redispatch and may require
reconciliation. Non-expiring claims deliberately trade availability for at-most-once
automatic dispatch authority. Operator inspection, reconciliation, and any explicit
recovery or abandonment mechanism are deferred to F6B.

The in-memory adapter mirrors storage-neutral results for deterministic tests but is
not authoritative for real dispatch.
