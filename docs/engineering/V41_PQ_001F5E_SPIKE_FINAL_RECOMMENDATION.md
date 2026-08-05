# V41-PQ-001F5E Final Storage Recommendation

Final decision: `SELECT_SQLITE_WITH_MANDATORY_POSTGRESQL_MIGRATION_TRIGGER`.

Rationale:

SQLite passed 30/30 executable synthetic durability scenarios using standard-library tooling already available in the environment. PostgreSQL is architecturally stronger for multi-worker and multi-host execution but could not be executed safely in this environment without installing dependencies or provisioning a service.

SQLite is selected only for the initial local Paper durable adapter design and only under these mandatory conditions:

- single machine
- single application deployment authority
- local filesystem only
- WAL enabled
- foreign keys enabled
- explicit transactions
- busy timeout configured
- no network filesystem
- schema migrations required
- backup and restore procedure required
- CAS and uniqueness checks required
- multi-host deployment prohibited
- mandatory PostgreSQL migration triggers documented

Mandatory PostgreSQL migration triggers:

- multiple application hosts
- multiple active execution workers
- remote shared database access
- high write concurrency
- public multi-user deployment
- managed web service deployment
- operational requirements exceeding local file backup
- network filesystem use
- availability requirements requiring database failover

Next recommended slice: `V41-PQ-001F5E2A — SQLITE DURABLE ADAPTER DESIGN`.

This recommendation does not implement durable persistence, does not wire runtime persistence, and does not authorize broker execution.
