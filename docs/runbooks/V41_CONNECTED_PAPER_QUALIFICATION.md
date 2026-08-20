# v4.1 Connected Paper qualification evidence

## Purpose

This runbook defines the evidence boundary for the single remaining v4.1 Connected Paper qualification gate. It does not authorize Live trading, credential publication, production activation, or unattended financial transactions.

## Preconditions

Before any connected Paper session, confirm all of the following outside this repository:

- the broker session is explicitly Paper/sandbox, not Live;
- the credential path is approved and secrets are not copied into repository files, logs, issues, PRs, or evidence artifacts;
- the market reference is fresh enough for the operator's qualification procedure;
- both best bid and best ask are positive, fresh, and form an unlocked,
  uncrossed spread;
- the intended order is exactly one share, BUY, LIMIT, DAY;
- the limit is below the observed best bid and preserves the greater of 100
  basis points or USD 1.00 below the observed best ask;
- one explicit execution-time authorization covers exactly one submission and
  the immediate targeted cancellation of only the acknowledged broker order;
- position closeout is not implied by submission/cancellation authorization and
  requires a separate explicit authorization if any fill occurs.

If any precondition is uncertain, stop. The offline tooling in this repository must not compensate for missing broker or credential evidence.

The price buffer reduces fill probability but cannot guarantee a non-fill.
Quote movement, venue latency, and broker processing can fill any accepted
limit order. The operator must be prepared to stop and request separate
position-cleanup authority if a partial or full fill is observed.

## Offline buffered preflight

Use a fresh, timezone-aware quote observation and run the preflight as a module:

```bash
python -m scripts.paper_qualification_preflight \
  --symbol AAPL \
  --reference-best-bid 100.48 \
  --reference-best-ask 100.50
```

The v2 preflight fails closed for invalid or locked/crossed spreads and reports:

- exactly one share, BUY, LIMIT, DAY;
- a tick-aligned limit below the reference best bid;
- the configured absolute and proportional ask buffers;
- the effective buffer and explicit buffer-satisfaction flags; and
- false effect flags for broker, credential, network, persistence, and runtime
  access.

The default effective buffer is
`max(USD 1.00, reference_best_ask * 100 / 10000)`. An operator may configure a
larger reviewed buffer but must not weaken either default for Connected Paper
qualification.

## Controlled execution sequence

After the buffered preflight passes, use one effect-capable operator process
with one durable client-order identity. Do not route effects through the
qualification or certification packages; those packages remain brokerless.

1. Revalidate Paper endpoint, active account, all account blocks, market-open
   status, AAPL eligibility, quote freshness, spread, tick size, and the v2
   buffered plan immediately before dispatch.
2. Obtain explicit authority for exactly one submission plus immediate targeted
   cancellation of the acknowledged order. The authority does not include
   retry, replacement, bulk cancellation, or position closeout.
3. Durably claim the client-order identity before dispatch. If a claim already
   exists, stop without dispatch.
4. Submit exactly one AAPL BUY/LIMIT/DAY order for one share. Never retry a send
   whose outcome is uncertain; reconcile only by the durable client-order
   identity.
5. On acknowledgment, immediately observe the targeted broker order and request
   cancellation by its broker identifier. Never call a bulk cancellation API.
6. If status is `NEW`, `ACCEPTED`, or another zero-fill open state, continue
   targeted cancellation and require terminal cancellation evidence.
7. If status is partially filled, target-cancel the remaining quantity under
   the existing cancellation authority, record the fill, and stop for separate
   position-cleanup authorization.
8. If status is filled, do not issue a meaningless cancellation. Record the
   fill and stop for separate position-cleanup authorization.
9. If submission or cancellation outcome is ambiguous, do not retry. Reconcile
   only by the durable client/broker identity and retain `OUTCOME_UNKNOWN` until
   broker truth is established.
10. Verify the targeted order is terminal, no targeted open order remains, and
    whether any AAPL position exists. A nonzero position is not cleanup success.
11. Only after a zero-position, terminal-order result may the redacted v1
    connected evidence be assembled and validated offline.

Passing offline tests or preflight is not Connected Paper qualification. A
connected attempt that fills before cancellation does not satisfy the v1
cancel-confirmation evidence contract, even if a separately authorized
position closeout later restores a zero position.

## Evidence to collect

Create one redacted JSON object with schema version `connected-paper-qualification-evidence-v1`. The object must state `environment: PAPER`, `live_trading: false`, `credentials_embedded: false`, and `consequential_action_confirmed: true`; include the fresh `reference_best_ask`; include a timezone-aware UTC `observed_at`; record the one-share BUY/LIMIT/DAY order facts; and record whether submission, acknowledgment, status observation, cancellation request, cancellation confirmation, and cleanup verification each occurred.

`connected-paper-qualification-evidence-v1` is a closed schema. Do not add unrecognized top-level, order, or lifecycle fields. If future qualification evidence needs additional metadata, define and review a new schema contract instead of silently extending v1. Duplicate JSON object fields are also invalid at every depth; the validator rejects them before schema validation and fingerprinting so no field can be shadowed by parser last-value-wins behavior.

`consequential_action_confirmed: true` records only that the separately controlled execution-time authorization occurred. It is evidence, not an authorization mechanism, and the offline validator cannot grant broker-effect permission.

Do not include API keys, secrets, tokens, authorization headers, cookies, private keys, connection strings, raw broker payloads that contain secrets, or any Live credential material.

Example shape only:

```json
{
  "schema_version": "connected-paper-qualification-evidence-v1",
  "environment": "PAPER",
  "live_trading": false,
  "credentials_embedded": false,
  "consequential_action_confirmed": true,
  "reference_best_ask": "100.50",
  "order": {
    "symbol": "AAPL",
    "side": "BUY",
    "quantity": 1,
    "order_type": "LIMIT",
    "time_in_force": "DAY",
    "limit_price": "99.49"
  },
  "lifecycle": {
    "submitted": true,
    "acknowledged": true,
    "status_observed": true,
    "cancel_requested": true,
    "cancel_confirmed": true,
    "cleanup_verified": true
  },
  "observed_at": "<UTC timestamp>"
}
```

## Offline validation

Run the repository validator against the redacted JSON:

```bash
python scripts/validate_connected_paper_evidence.py /path/to/redacted-evidence.json
```

A passing report returns `validation: PASS`, a deterministic `evidence_sha256`, normalized safety facts, and explicit `false` flags confirming that the validator itself did not access a broker, load credentials, use network, submit an order, or change runtime state.

The validator fails closed if the payload claims a non-Paper environment, Live trading, embedded credentials, lacks explicit consequential-action confirmation, has a missing or non-UTC observation timestamp, a non-BUY side, quantity other than one, a non-LIMIT or non-DAY order, a marketable/crossing limit, incomplete submit/ack/status/cancel/cleanup evidence, duplicate JSON fields, secret-shaped fields, or any unrecognized v1 field.

## Review record

For issue #69, retain only the redacted evidence artifact, the validator PASS report, its SHA-256, and the relevant repository commit/PR reference. Do not paste credential values or unredacted broker traffic into GitHub.

The v4.1 Connected Paper gate is complete only when the connected Paper session itself has occurred through an approved broker interface and the resulting redacted evidence passes this offline validator. Repository automation alone cannot satisfy the broker-side event requirement.
