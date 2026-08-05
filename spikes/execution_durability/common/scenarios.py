"""Backend-neutral execution durability spike scenario catalog."""

from __future__ import annotations

from spikes.execution_durability.common.models import SpikeScenario

SCENARIOS: tuple[SpikeScenario, ...] = (
    SpikeScenario("S01", "Initial aggregate creation", "aggregate_created"),
    SpikeScenario("S02", "Immutable command insertion", "command_inserted"),
    SpikeScenario(
        "S03", "Same command ID and same payload replay", "exact_command_replay"
    ),
    SpikeScenario(
        "S04",
        "Same command ID and different payload conflict",
        "command_payload_conflict",
    ),
    SpikeScenario("S05", "New idempotency reservation", "idempotency_reserved"),
    SpikeScenario(
        "S06",
        "Same key and same logical fingerprint replay",
        "logical_idempotency_replay",
    ),
    SpikeScenario(
        "S07",
        "Same key and different logical fingerprint conflict",
        "idempotency_conflict",
    ),
    SpikeScenario("S08", "Aggregate compare-and-swap success", "cas_update_success"),
    SpikeScenario(
        "S09", "Aggregate stale-revision rejection", "stale_revision_rejected"
    ),
    SpikeScenario(
        "S10",
        "Atomic aggregate plus transition-journal commit",
        "aggregate_and_journal_committed",
    ),
    SpikeScenario(
        "S11", "Transaction rollback after staged failure", "rollback_no_partial_writes"
    ),
    SpikeScenario(
        "S12", "Transition-record duplicate replay", "transition_exact_replay"
    ),
    SpikeScenario(
        "S13", "Transition-record identity conflict", "transition_identity_conflict"
    ),
    SpikeScenario(
        "S14", "Active broker-reference uniqueness", "broker_reference_unique"
    ),
    SpikeScenario(
        "S15", "Duplicate normalized broker observation", "broker_reference_replay"
    ),
    SpikeScenario(
        "S16", "Conflicting normalized broker observation", "broker_reference_conflict"
    ),
    SpikeScenario(
        "S17",
        "Restart discovery by lifecycle state",
        "restart_discovery_result",
        restart_relevance=True,
    ),
    SpikeScenario(
        "S18",
        "Concurrent competing aggregate revisions",
        "one_cas_winner",
        concurrency_relevance=True,
    ),
    SpikeScenario(
        "S19",
        "Concurrent identical idempotency reservations",
        "one_reservation_then_replay",
        concurrency_relevance=True,
    ),
    SpikeScenario(
        "S20",
        "Concurrent conflicting idempotency reservations",
        "one_reservation_then_conflict",
        concurrency_relevance=True,
    ),
    SpikeScenario(
        "S21",
        "Dispatch-preparation transaction",
        "dispatch_pending_committed",
        restart_relevance=True,
    ),
    SpikeScenario(
        "S22",
        "Simulated crash after durable dispatch intent",
        "dispatch_intent_survives_reopen",
        restart_relevance=True,
    ),
    SpikeScenario(
        "S23",
        "Recovery discovery of DISPATCH_PENDING",
        "dispatch_pending_discovered",
        restart_relevance=True,
    ),
    SpikeScenario(
        "S24",
        "OUTCOME_UNKNOWN discovery",
        "outcome_unknown_discovered",
        restart_relevance=True,
    ),
    SpikeScenario(
        "S25",
        "RECONCILIATION_REQUIRED discovery",
        "reconciliation_required_discovered",
        restart_relevance=True,
    ),
    SpikeScenario(
        "S26",
        "Migration from schema version 1 to version 2",
        "migration_v2_applied",
        migration_relevance=True,
    ),
    SpikeScenario(
        "S27",
        "Backup and restore validation",
        "backup_restore_consistent",
        backup_relevance=True,
    ),
    SpikeScenario(
        "S28",
        "Foreign-key violation rollback",
        "foreign_key_rollback",
        migration_relevance=True,
    ),
    SpikeScenario(
        "S29",
        "Journal and snapshot consistency validation",
        "journal_snapshot_consistent",
    ),
    SpikeScenario("S30", "Secret-exclusion validation", "no_secrets_persisted"),
)

SCENARIO_BY_ID = {scenario.scenario_id: scenario for scenario in SCENARIOS}

__all__ = ["SCENARIOS", "SCENARIO_BY_ID"]
