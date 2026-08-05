# Sentinel ADR-006 Findings Register

## Review scope

Review target: `docs/adr/ADR-006-PAPER-EXECUTION-LIFECYCLE.md` and supporting
F5D0 lifecycle documents.

Review date: 2026-08-04.

## Findings summary

| Severity | Open | Closed | Total |
|---|---:|---:|---:|
| Critical | 0 | 0 | 0 |
| Major | 0 | 2 | 2 |
| Minor | 0 | 3 | 3 |
| Observation | 2 | 4 | 6 |

## Findings

| ID | Severity | Affected document | Affected states/transitions | Description | Safety consequence | Required remediation | Disposition | Verification method |
|---|---|---|---|---|---|---|---|---|
| ADR006-MAJ-001 | Major | ADR-006, state model, transition table | `ELIGIBILITY_EVALUATED`, `READY_FOR_DISPATCH`, PX-TRN-002..008 | Lifecycle acceptance required clearer statement that eligibility recording and ready-for-dispatch are non-authoritative. | Could let future implementers treat eligibility or local readiness as dispatch authority. | Add explicit non-authority wording and keep ADR-006 acceptance contingent on no dispatch authority. | Closed | ADR status and checklist confirm no transition authorizes broker dispatch. |
| ADR006-MAJ-002 | Major | Transition table, reconciliation model | `OUTCOME_UNKNOWN`, `RECONCILIATION_REQUIRED`, PX-TRN-012, PX-TRN-025..028 | Recovery destinations needed bounded interpretation so reconciliation cannot silently overwrite terminal truth. | Could permit unsafe rollback or blind retry after ambiguous dispatch. | Bind reconciliation to explicit outcomes and concrete allowed recovery destinations only. | Closed | Transition audit confirms no automatic retry and bounded recovery destinations. |
| ADR006-MIN-001 | Minor | State model | `WORKING`, `BROKER_ACKNOWLEDGED` | Existing F5B has `WORKING`; F5D0 deferred it. | Low ambiguity when broker adapter mapping arrives. | Document `WORKING` as deferred adapter mapping state. | Closed | State inventory lists `WORKING` as deferred. |
| ADR006-MIN-002 | Minor | Transition table | PX-TRN-028 | Conflict recording uses no-op unless new fact. | Future implementation must test no revision increment on duplicate conflict evidence. | Capture in replay/failure matrix. | Closed | Failure matrix and transition audit include duplicate/conflict behavior. |
| ADR006-MIN-003 | Minor | Dry-run plan | Dry-run effect model | Dry-run outcome contract is deferred. | Future F5D2 could overuse lifecycle states. | Require separate dry-run outcome model and prohibit broker-truth states. | Closed | Checklist dry-run isolation passes. |
| ADR006-OBS-001 | Observation | All lifecycle docs | All states | State count remains 22. | None. | None. | Closed | State inventory audited. |
| ADR006-OBS-002 | Observation | Transition table | PX-TRN-001..030 | Transition count remains 30. | None. | None. | Closed | Transition audit audited all IDs. |
| ADR006-OBS-003 | Observation | ADR-006 | ADR status | ADR can move from Proposed to Accepted after this review. | None if acceptance text remains non-authorizing. | Set status to Accepted. | Closed | ADR status updated. |
| ADR006-OBS-004 | Observation | Roadmap/design | F5D1 scope | F5D1 is ready for implementation with strict constraints. | None. | Record exact F5D1 scope and deferred items. | Closed | Roadmap/design updated. |
| ADR006-OBS-005 | Observation | Future F5D1 | Guard implementation | Some guards require future persistence or external evidence and must not be faked in F5D1. | Future risk if ignored. | Keep deferred guard classes explicit. | Deferred | Guard audit in review report. |
| ADR006-OBS-006 | Observation | Future F5D2 | Dry-run evidence | Dry-run evidence label schema remains deferred. | Future test-planning item. | Define in F5D2. | Deferred | Dry-run readiness audit. |
