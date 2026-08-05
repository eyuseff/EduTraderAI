# V41-PQ-001F5E0 Security, Retention, and Redaction

## Purpose

Define persistence security and retention requirements before durable execution
storage exists. This is design only.

## Persistence exclusions

Never persist:

- API keys;
- secret keys;
- access tokens;
- refresh tokens;
- passwords;
- authorization headers;
- cookies;
- private keys;
- raw broker SDK objects;
- raw broker HTTP payloads without approved normalization;
- stack traces with secrets;
- environment-variable snapshots;
- personal information not required for execution.

## Allowed persistence shape

Persist only:

- safe aliases;
- normalized broker references;
- immutable fingerprints;
- safe reason codes;
- approved structured fields;
- redacted operator references;
- explicit timestamps with clear source semantics.

## Encryption requirements

Future implementation must decide and document encryption for:

- database file at rest;
- backups;
- broker account aliases if sensitive;
- operator identifiers;
- approval records.

No encryption is currently implemented by F5E0.

## Redaction requirements

Broker responses must be normalized before persistence. Raw SDK objects must
not cross the persistence boundary. Failure records must use stable codes, not
raw exception strings.

## Retention categories

| Category | Retention direction |
|---|---|
| Active aggregates | Retain while active and through reconciliation window |
| Commands | Retain to preserve idempotency and audit |
| Idempotency records | Retain at least through duplicate-risk window |
| Lifecycle history | Retain append-only until approved archival |
| Receipts | Retain with command history |
| Failures | Retain with command history |
| Approvals | Retain while needed to prove execution authority |
| Reconciliation records | Retain with affected aggregate |
| Dry-run results | Do not become execution authority; retention can be shorter |
| Broker references | Retain while needed for reconciliation and audit |
| Evidence/audit records | Retain by validation/audit policy |

## Deletion restrictions

Deletion must not break idempotency replay, aggregate reconstruction,
reconciliation, or audit. Legal/regulatory review is required before setting
final retention periods.

## Test data cleanup

Test execution stores must be isolated, clearly named, and safe to delete.
Production stores must never be selected by default test configuration.

## Sentinel ADR-007 review update

Review result: PASS. Secrets, authorization headers, cookies, private keys, raw SDK objects, raw HTTP payloads, environment snapshots, unredacted exception traces, and unnecessary personal data remain excluded. Retention categories are accepted, but final retention periods remain deferred to legal, regulatory, privacy, and operational review.
