# EduTraderAI v4.1 Implementation Status

Date: 2026-08-16

This snapshot reconciles the original backlog with repository evidence now merged into `main`. It does not replace the backlog's prioritization and does not convert external evidence or proposed architecture into completed work.

## Status vocabulary

- **IMPLEMENTED** — repository implementation and offline CI evidence are present.
- **IMPLEMENTED / EXTERNAL EVIDENCE REQUIRED** — the repository-side control exists, but connected Paper evidence is still required.
- **PROPOSED / DECISION REQUIRED** — design work exists, but a consequential architecture or governance choice remains open.

## Paper qualification — P0

| Item | Status | Current evidence / remaining boundary |
|---|---|---|
| V41-PQ-001 State machine | IMPLEMENTED | Qualification state-machine and scenario coverage are present. |
| V41-PQ-002 Paper-only endpoint/broker guard | IMPLEMENTED / EXTERNAL EVIDENCE REQUIRED | Fail-closed Paper boundaries exist; selected real Paper endpoint/configuration has not been exercised by this audit. |
| V41-PQ-003 Deterministic one-share quantity | IMPLEMENTED / EXTERNAL EVIDENCE REQUIRED | PR #50 enforces exactly one share at qualification translation; eventual connected request still needs redacted evidence. |
| V41-PQ-004 Safe non-marketable limit | IMPLEMENTED / EXTERNAL EVIDENCE REQUIRED | PR #51 builds/validates a safe limit below an explicitly supplied best ask; connected fresh reference-price evidence remains external. |
| V41-PQ-005 Ack/status/cancel lifecycle | IMPLEMENTED / EXTERNAL EVIDENCE REQUIRED | Deterministic fake-broker lifecycle exists; real Paper lifecycle evidence remains required. |
| V41-PQ-006 Duplicate-execution prevention | IMPLEMENTED / EXTERNAL EVIDENCE REQUIRED | Offline replay/idempotency/concurrency controls exist; connected broker evidence may still be required for qualification sign-off. |
| V41-PQ-007 Redacted immutable evidence | IMPLEMENTED / EXTERNAL EVIDENCE REQUIRED | Canonical evidence/redaction/digest infrastructure exists; final connected qualification artifact and manifest row remain external. |

The authoritative detailed audit is `V41_PAPER_QUALIFICATION_IMPLEMENTATION_AUDIT_2026-08-16.md`.

## Coordination — P1

| Item | Status | Current evidence / remaining boundary |
|---|---|---|
| V41-CC-001 Inventory locks/idempotency/state | IMPLEMENTED | PR #53 documents process-local versus durable coordination boundaries. |
| V41-CC-002 Distributed requirements | IMPLEMENTED | PR #54 defines technology-neutral fencing, CAS, takeover, replay and recovery invariants. |
| V41-CC-003 Select architecture | PROPOSED / DECISION REQUIRED | PR #55 adds ADR-012 as `Proposed`: extend the existing durable DB authority; keep SQLite only for validated current topology; prefer a transactional server DB before claiming multi-host support. Runtime migration is not approved merely by this status document. |

## Event publication — P1

| Item | Status | Current evidence / remaining boundary |
|---|---|---|
| V41-EP-001 Inventory NullEventPublisher | IMPLEMENTED | PR #56 documents verified production defaults and audit/recovery gaps. |
| V41-EP-002 External publisher contract | IMPLEMENTED | PR #57 defines vendor-neutral identity, serialization, ordering, backpressure, retry and safety semantics. No transport vendor was selected. |
| V41-EP-003 Delivery observability | IMPLEMENTED | PR #58 adds transport-neutral capability/status diagnostics and bounded event-only retry behavior without making events execution authority. |

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

## Remaining non-automatic boundaries

The remaining work is not accurately represented as generic missing implementation:

1. **Connected Paper qualification evidence** — verified Paper endpoint/configuration, approved secret path, fresh price reference, explicit consequential-action confirmation, controlled one-share lifecycle, and final redacted immutable evidence.
2. **Coordination architecture acceptance** — ADR-012 remains Proposed. A server-database migration or multi-host topology claim must not be inferred from offline documentation.
3. **External event transport selection**, if desired — the contract and observability layer exist, but no vendor/backend has been selected or connected.

No status in this file authorizes Live trading, broker credentials, external order submission, production `state/` access, release tags, deployments, or publication of release artifacts.
