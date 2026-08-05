"""Scoring matrix for the isolated SQLite/PostgreSQL durability spike."""

from __future__ import annotations

from spikes.execution_durability.common.models import BackendAssessment

SCORE_SCALE = {
    0: "unsupported",
    1: "major limitation",
    2: "supported with significant conditions",
    3: "supported adequately",
    4: "strong support",
}

ASSESSMENTS: tuple[BackendAssessment, ...] = (
    BackendAssessment(
        "Contract fidelity",
        3,
        4,
        "SQLite executed; PostgreSQL static",
        "Both can model accepted records; PostgreSQL has stronger typed concurrency primitives.",
    ),
    BackendAssessment(
        "Atomic transactions",
        3,
        4,
        "SQLite executed rollback; PostgreSQL static",
        "SQLite passes local transactions; PostgreSQL is stronger for multi-worker services.",
    ),
    BackendAssessment(
        "Unique constraints",
        4,
        4,
        "SQLite executed; PostgreSQL static",
        "Both support required uniqueness.",
    ),
    BackendAssessment(
        "CAS concurrency",
        3,
        4,
        "SQLite executed two-connection writer serialization",
        "SQLite works under single-machine writer serialization; PostgreSQL supports row-level contention.",
    ),
    BackendAssessment(
        "Idempotency races",
        3,
        4,
        "SQLite executed unique-key race approximation",
        "SQLite adequate locally; PostgreSQL better for concurrent workers.",
    ),
    BackendAssessment(
        "Append-only journal integrity",
        4,
        4,
        "SQLite executed; PostgreSQL static",
        "Primary keys and CHECK constraints model append-only accepted transitions.",
    ),
    BackendAssessment(
        "Restart recovery",
        3,
        4,
        "SQLite reopen executed; PostgreSQL static",
        "SQLite file reopen works locally; PostgreSQL has stronger service restart recovery.",
    ),
    BackendAssessment(
        "Cross-process support",
        2,
        4,
        "Architectural assessment",
        "SQLite has one-writer limits; PostgreSQL designed for multi-process access.",
    ),
    BackendAssessment(
        "Multi-worker support",
        1,
        4,
        "Architectural assessment",
        "SQLite should not be selected for multiple active execution workers.",
    ),
    BackendAssessment(
        "Multi-host support",
        0,
        4,
        "Architectural assessment",
        "SQLite on network filesystems is prohibited; PostgreSQL supports multi-host clients.",
    ),
    BackendAssessment(
        "Migration support",
        3,
        4,
        "SQLite additive migration executed; PostgreSQL static",
        "SQLite migrations are possible but more operationally fragile.",
    ),
    BackendAssessment(
        "Backup/restore",
        3,
        4,
        "SQLite backup executed; PostgreSQL static",
        "SQLite backup API is adequate locally; PostgreSQL has mature dump/PITR options.",
    ),
    BackendAssessment(
        "Local setup simplicity",
        4,
        2,
        "Environment inventory",
        "SQLite is standard library; PostgreSQL tooling unavailable locally.",
    ),
    BackendAssessment(
        "Deterministic testing",
        4,
        3,
        "SQLite executed; PostgreSQL unavailable",
        "SQLite is easier to run hermetically in CI without services.",
    ),
    BackendAssessment(
        "Operational burden",
        4,
        2,
        "Architectural assessment",
        "SQLite has lower local burden; PostgreSQL requires service operations.",
    ),
    BackendAssessment(
        "Portability",
        3,
        3,
        "Architectural assessment",
        "Both portable; SQLite file constraints matter.",
    ),
    BackendAssessment(
        "Future web deployment",
        1,
        4,
        "Architectural assessment",
        "PostgreSQL is the safer web/multi-host target.",
    ),
    BackendAssessment(
        "Security operations",
        2,
        4,
        "Architectural assessment",
        "PostgreSQL has stronger managed controls; SQLite relies on local file controls.",
    ),
    BackendAssessment(
        "Failure observability",
        2,
        4,
        "Architectural assessment",
        "PostgreSQL exposes richer operational monitoring.",
    ),
    BackendAssessment(
        "Upgrade path",
        3,
        4,
        "Architectural assessment",
        "SQLite can start local Paper if migration triggers are explicit; PostgreSQL is the target for scale.",
    ),
)

FINAL_DECISION = "SELECT_SQLITE_WITH_MANDATORY_POSTGRESQL_MIGRATION_TRIGGER"
NEXT_RECOMMENDED_SLICE = "V41-PQ-001F5E2A — SQLITE DURABLE ADAPTER DESIGN"

SQLITE_DEPLOYMENT_CONDITIONS = (
    "single machine",
    "single application deployment authority",
    "local filesystem only",
    "WAL enabled",
    "foreign keys enabled",
    "explicit transactions",
    "busy timeout configured",
    "no network filesystem",
    "schema migrations required",
    "backup and restore procedure required",
    "CAS and uniqueness checks required",
    "multi-host deployment prohibited",
    "mandatory PostgreSQL migration triggers documented",
)

POSTGRESQL_MIGRATION_TRIGGERS = (
    "multiple application hosts",
    "multiple active execution workers",
    "remote shared database access",
    "high write concurrency",
    "public multi-user deployment",
    "managed web service deployment",
    "operational requirements exceeding local file backup",
    "network filesystem use",
    "availability requirements requiring database failover",
)


def total_scores() -> tuple[int, int]:
    return (
        sum(item.sqlite_score for item in ASSESSMENTS),
        sum(item.postgresql_score for item in ASSESSMENTS),
    )


__all__ = [
    "ASSESSMENTS",
    "FINAL_DECISION",
    "NEXT_RECOMMENDED_SLICE",
    "POSTGRESQL_MIGRATION_TRIGGERS",
    "SCORE_SCALE",
    "SQLITE_DEPLOYMENT_CONDITIONS",
    "total_scores",
]
