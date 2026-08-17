# v4.1 Connected Paper qualification evidence

## Purpose

This runbook defines the evidence boundary for the single remaining v4.1 Connected Paper qualification gate. It does not authorize Live trading, credential publication, production activation, or unattended financial transactions.

## Preconditions

Before any connected Paper session, confirm all of the following outside this repository:

- the broker session is explicitly Paper/sandbox, not Live;
- the credential path is approved and secrets are not copied into repository files, logs, issues, PRs, or evidence artifacts;
- the market reference is fresh enough for the operator's qualification procedure;
- the intended order is exactly one share, BUY, LIMIT, DAY, with the limit strictly below the observed best ask;
- the consequential broker action is separately authorized at execution time.

If any precondition is uncertain, stop. The offline tooling in this repository must not compensate for missing broker or credential evidence.

## Evidence to collect

Create one redacted JSON object with schema version `connected-paper-qualification-evidence-v1`. The object must state `environment: PAPER`, `live_trading: false`, `credentials_embedded: false`, and `consequential_action_confirmed: true`; include the fresh `reference_best_ask`; include a timezone-aware UTC `observed_at`; record the one-share BUY/LIMIT/DAY order facts; and record whether submission, acknowledgment, status observation, cancellation request, cancellation confirmation, and cleanup verification each occurred.

`connected-paper-qualification-evidence-v1` is a closed schema. Do not add unrecognized top-level, order, or lifecycle fields. If future qualification evidence needs additional metadata, define and review a new schema contract instead of silently extending v1.

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
    "limit_price": "100.49"
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

The validator fails closed if the payload claims a non-Paper environment, Live trading, embedded credentials, lacks explicit consequential-action confirmation, has a missing or non-UTC observation timestamp, a non-BUY side, quantity other than one, a non-LIMIT or non-DAY order, a marketable/crossing limit, incomplete submit/ack/status/cancel/cleanup evidence, secret-shaped fields, or any unrecognized v1 field.

## Review record

For issue #69, retain only the redacted evidence artifact, the validator PASS report, its SHA-256, and the relevant repository commit/PR reference. Do not paste credential values or unredacted broker traffic into GitHub.

The v4.1 Connected Paper gate is complete only when the connected Paper session itself has occurred through an approved broker interface and the resulting redacted evidence passes this offline validator. Repository automation alone cannot satisfy the broker-side event requirement.
