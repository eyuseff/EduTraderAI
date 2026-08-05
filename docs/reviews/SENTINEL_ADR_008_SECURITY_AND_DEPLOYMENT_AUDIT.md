# Sentinel ADR-008 Security and Deployment Audit

## Audit result

PASS.

The deployment envelope and security model are narrow enough for initial SQLite schema/migration foundation work.

## Deployment envelope

- one machine;
- one application process owning execution writes;
- one active execution authority;
- one active write coordinator;
- local filesystem only;
- no concurrent execution writer process;
- read-only/backup/maintenance connections only under explicit safe procedures;
- no NFS, SMB, cloud-sync, remote filesystem, multi-host, or active-active deployment.

## Path and symlink rules

Database files must reside in an approved local application data directory outside source, Git, build, temp, `state/`, `state/simulated_broker.json`, cloud-sync, and network-share paths. Symlinks must be resolved; if the resolved path violates restrictions or cannot be proven local, startup fails closed.

## Permission rules

Parent directory, database, WAL, SHM, and backup files require least-privilege local permissions and must not be world-readable. Permission denial, read-only filesystem, or unverifiable ownership blocks execution startup.

## Secret exclusion

Database and logs must not contain API keys, secrets, tokens, passwords, authorization headers, cookies, private keys, raw SDK objects, raw broker payloads, environment snapshots, raw exception stacks, or credential-bearing SQL logs.

## Encryption and retention

Database encryption is honestly deferred. Retention categories are identified, but final retention periods are deferred to legal/privacy/operational review before commercialization.

## PostgreSQL migration governance

Mandatory triggers require ADR review, SQLite feature-expansion freeze, PostgreSQL runtime validation, migration planning, and broker scale-up block.

## Audit conclusion

No security or deployment blocker remains. Broker execution remains `NOT_AUTHORIZED`.
