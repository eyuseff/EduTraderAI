# V41-PQ-001F5E2A SQLite Security and Permissions

## File permissions

The database directory, database file, WAL file, SHM file, and backup files must use least-privilege local permissions and must not be world-readable. Parent directory ownership and write access must be validated at startup.

## Location restrictions

Execution persistence files must not be placed in:

- Git repository paths;
- `state/`;
- `state/simulated_broker.json`;
- build directories;
- temporary spike directories;
- cloud-synced folders;
- shared network folders;
- NFS or SMB mounts.

## Secret exclusion

The database must never contain API keys, secret keys, tokens, passwords, authorization headers, cookies, private keys, raw SDK objects, raw HTTP payloads without approved normalization, environment snapshots, raw exception stacks, or credential-bearing logs.

## Logging

Future SQL logging must avoid sensitive values and should prefer safe reason codes, fingerprints, and deterministic identities.

## Encryption

Database encryption is not implemented by this design. SQLCipher, filesystem encryption, key management, and support-export encryption remain deferred assessments.

## Support export

Any future support package must redact identifiers according to a documented policy and must not include credentials, personal account data, or raw broker payloads.

## Retention

Retention categories:

- command records;
- idempotency records;
- transition history;
- broker references;
- receipts;
- failures;
- approvals;
- reconciliations;
- backups;
- migration history.

Authoritative lifecycle history is not silently deleted. Final retention periods are deferred to legal, privacy, operational, and commercialization review.
