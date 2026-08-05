# V41-PQ-001F5E2A PostgreSQL Migration Triggers

## Mandatory triggers

SQLite execution persistence must stop expanding and PostgreSQL migration planning becomes blocking before:

- multiple application hosts;
- multiple active execution workers;
- shared remote database requirement;
- high write concurrency;
- public multi-user deployment;
- managed web service deployment;
- network filesystem proposal;
- availability or failover requirements;
- operational backup needs exceeding local file backup;
- concurrency evidence showing SQLite limitations;
- database size or maintenance burden exceeding the validated operating envelope;
- remote operations requiring centralized database administration.

## Governance after a trigger

Once any trigger occurs:

- no new feature expansion on SQLite execution persistence without formal review;
- broker-execution scale-up is prohibited until migration is designed;
- Sentinel review must reassess storage selection;
- SQLite remains eligible only for the already validated local Paper envelope.

## Migration path model

Future migration must preserve:

- aggregate IDs;
- command IDs;
- idempotency keys and logical fingerprints;
- execution revisions;
- transition journal order;
- broker references;
- receipt/failure fingerprints;
- approval fingerprints;
- reconciliation IDs;
- UTC timestamps;
- safe reason codes;
- mode and schema versions.

Dual-write is prohibited unless separately designed and reviewed. Initial migration likely requires maintenance outage, source backup, target PostgreSQL load, invariant validation, reconciliation-state preservation, and rollback plan.
