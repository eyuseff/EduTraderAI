# EduTraderAI v4.1 Implementation Status

Date: 2026-08-16

This snapshot reconciles the original backlog with repository evidence now merged into `main`. It does not replace the backlog's prioritization and does not convert external evidence into completed work.

## Status vocabulary

- **IMPLEMENTED** — repository implementation and offline CI evidence are present, or an architecture/governance decision required by the backlog has been explicitly accepted.
- **IMPLEMENTED / EXTERNAL EVIDENCE REQUIRED** — the repository-side control exists, but connected Paper evidence is still required.
- **QUALIFIED** — the repository control and its required redacted Connected Paper evidence are present and validated.
- **PROPOSED / DECISION REQUIRED** — design work exists, but a consequential architecture or governance choice remains open.

## Paper qualification — P0

| Item | Status | Current evidence / remaining boundary |
|---|---|---|
| V41-PQ-001 State machine | IMPLEMENTED | Qualification state-machine and scenario coverage are present. |
| V41-PQ-002 Paper-only endpoint/broker guard | QUALIFIED | The 2026-08-20 qualification verified Alpaca Paper configuration and never enabled Live trading. |
| V41-PQ-003 Deterministic one-share quantity | QUALIFIED | The connected qualification submitted exactly one share. |
| V41-PQ-004 Safe non-marketable limit | QUALIFIED | The connected limit was `314.22`, below the fresh observed best ask of `317.40`. |
| V41-PQ-005 Ack/status/cancel lifecycle | QUALIFIED | The Paper order was acknowledged, observed, individually cancelled, and reconciled to zero fill, no position, and no open orders. |
| V41-PQ-006 Duplicate-execution prevention | QUALIFIED | The controlled qualification made one submission attempt and used only its targeted cancellation path. |
| V41-PQ-007 Redacted immutable evidence | QUALIFIED | The redacted local artifact passes the offline validator and is recorded with its immutable file digest in `EVIDENCE_MANIFEST.md`. |

The authoritative detailed audit is `V41_PAPER_QUALIFICATION_IMPLEMENTATION_AUDIT_2026-08-16.md`.

## Coordination — P1

| Item | Status | Current evidence / remaining boundary |
|---|---|---|
| V41-CC-001 Inventory locks/idempotency/state | IMPLEMENTED | PR #53 documents process-local versus durable coordination boundaries. |
| V41-CC-002 Distributed requirements | IMPLEMENTED | PR #54 defines technology-neutral fencing, CAS, takeover, replay and recovery invariants. |
| V41-CC-003 Select architecture | IMPLEMENTED | PR #55 proposed ADR-012 and PR #74 records owner acceptance for the current v4.1 topology: the durable execution database remains the sole consequential coordination authority, SQLite remains limited to the validated local durable topology, and no multi-host support is claimed. |

## Event publication — P1

| Item | Status | Current evidence / remaining boundary |
|---|---|---|
| V41-EP-001 Inventory NullEventPublisher | IMPLEMENTED | PR #56 documents verified production defaults and audit/recovery gaps. |
| V41-EP-002 External publisher contract | IMPLEMENTED | PR #57 defines vendor-neutral identity, serialization, ordering, backpressure, retry and safety semantics. No transport vendor was selected. |
| V41-EP-003 Delivery observability | IMPLEMENTED | PR #58 adds transport-neutral capability/status diagnostics and bounded event-only retry behavior without making events execution authority. PR #74 explicitly defers concrete external transport selection and makes it non-blocking for v4.1 release qualification. |

## Performance — P2

| Item | Status | Current evidence / remaining boundary |
|---|---|---|
| V41-PF-001 Benchmark definition | IMPLEMENTED | PR #59 formalizes the deterministic fixture/workloads/protocol. |
| V41-PF-002 Regression thresholds | IMPLEMENTED | PR #64 measures seven-run GitHub-runner noise. PR #65 adds paired base-vs-head gating: median and p95 block using `max(5%, 6 × baseline MAD%)` with a 15% fail-closed ceiling; p99 remains advisory because measured tails were materially noisier. Human release review remains mandatory. |

## Release automation — P2

| Item | Status | Current evidence / remaining boundary |
|---|---|---|
| V41-RA-001 Automated release summary | IMPLEMENTED | PR #60 generates sanitized JSON/Markdown summaries after verification and always preserves `HUMAN_REVIEW_REQUIRED`. |
| V41-RA-002 Evidence packaging | IMPLEMENTED | PR #62 produces deterministic local evidence ZIPs, SHA-256 manifests/sidecars, tamper/path/redaction checks and no automatic publication. |

## Additional hardening completed during the same automation pass

- PR #63 upgraded `actions/checkout` and `actions/setup-python` to their Node-24-generation v7 majors.
- PR #66 upgraded all active artifact uploads to `actions/upload-artifact@v7` after verifying the official v7.0.1 release.
- PR #67 closes the remaining known `RECONCILE` record-fingerprint gap by validating durable transition records through the canonical SQLite mapper and failing startup closed on tampering.
- PR #70 makes protected-path change detection fail closed by using complete Git history and refusing to mask unresolved diff ranges.
- PR #72 disables persisted checkout credentials in the established verification workflows and adds regression coverage for that boundary.
- PR #73 pins the established verification workflow actions to reviewed exact commit SHAs and adds allowlist regression coverage against mutable action-tag drift.

## Remaining non-automatic boundary

The Connected Alpaca Paper qualification gate tracked by issue #69 completed on
2026-08-20. Its redacted immutable local artifact and digest are recorded in
`docs/operations/EVIDENCE_MANIFEST.md`.

Any release tag, release artifact publication, or deployment remains a separate
human authorization boundary.

ADR-012 coordination architecture was accepted for the current supported topology by PR #74. External event transport selection was explicitly deferred by PR #74 and is not required for v4.1 release qualification.

No status in this file authorizes Live trading, broker credentials, external order submission, production `state/` access, release tags, deployments, or publication of release artifacts.
