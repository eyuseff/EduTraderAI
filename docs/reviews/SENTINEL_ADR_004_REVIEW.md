# Sentinel ADR-004 Engineering Review

## 1. Review title

Project Sentinel formal engineering review of ADR-004 — Paper Qualification State Machine.

## 2. Review date

2026-07-28.

## 3. Review scope

Adversarial review of ADR-004 and V41-PQ-001 design documents. The review looked for ambiguous state ownership, duplicate meanings, unreachable states, missing transitions, invalid transitions, unsafe retries, duplicate submissions, evidence gaps, restart hazards, race conditions, operator misunderstanding, false broker completion, unnecessary complexity, implementation ambiguity, and future incompatibility.

## 4. Reviewers

- Codex engineering reviewer acting under Project Sentinel instructions.

## 5. Materials reviewed

Primary materials:

- `docs/adr/ADR-004-PAPER-QUALIFICATION-STATE-MACHINE.md`.
- `docs/engineering/V41_PQ_001_DESIGN.md`.
- `docs/engineering/V41_PQ_001_TRANSITION_TABLE.md`.
- `docs/engineering/V41_PQ_001_TEST_STRATEGY.md`.

Source materials:

- `docs/vision/EMERS_CONSTITUTION.md`.
- `docs/vision/EMERS_PRODUCT_PRINCIPLES.md`.
- `docs/atlas/EMERS_PRODUCT_ARCHITECTURE.md`.
- `docs/atlas/EMERS_SECURITY_AND_TRUST_MODEL.md`.
- `docs/atlas/EMERS_BROKER_INTEGRATION_STRATEGY.md`.
- `docs/horizon/EMERS_TRADE_APPROVAL_EXPERIENCE.md`.
- `docs/horizon/EMERS_BROKER_STATUS_EXPERIENCE.md`.
- `docs/horizon/EMERS_FAILURE_AND_DEGRADED_MODE_UX.md`.
- `prototype/polaris/docs/POLARIS_INTERACTION_MAP.md`.
- `docs/roadmap/EDUTRADERAI_V4_1_ROADMAP.md`.

Implementation references checked:

- `app.py`.
- `broker/base.py`.
- `broker/simulated.py`.
- `broker/alpaca_paper.py`.
- `adapters/paper_order_preview.py`.
- `adapters/paper_order_submission.py`.
- `adapters/paper_broker_execution.py`.
- `volcanoes/execution/execution_pipeline.py`.
- `volcanoes/application/services/submit_trade.py`.
- `volcanoes/application/supervisor/supervisor.py`.
- `volcanoes/events/models.py`.
- `volcanoes/events/publisher.py`.
- `volcanoes/application/platform/configuration.py`.
- `volcanoes/application/platform/health.py`.

## 6. Method

The review attempted to break the design by walking state ownership, state minimality, reachability, transition completeness, invalid transitions, qualification semantics, idempotency, side-effect ordering, broker truth, reconciliation, restart recovery, concurrency, evidence, security, human factors, test completeness, simplicity, and future compatibility.

## 7. Executive outcome

Outcome: ACCEPTED.

Critical findings: 0.

Major findings: 4, all resolved during review.

Minor findings: 3, two resolved and one non-blocking follow-up left open.

Observations: 4, all deferred to already separated future work.

ADR-004 was changed from Proposed to Accepted only after required corrections were incorporated.

## 8. Severity summary

| Severity | Count | Open |
|---|---:|---:|
| CRITICAL | 0 | 0 |
| MAJOR | 4 | 0 |
| MINOR | 3 | 1 |
| OBSERVATION | 4 | 4 deferred |

## 9. Critical findings

None.

## 10. Major findings

Resolved major findings:

- SNT-004-001: State ownership required sharper separation.
- SNT-004-002: Default mandatory qualification scenario was not explicit enough.
- SNT-004-003: Broad transition sources could be misread as arbitrary mutation.
- SNT-004-004: Failure destinations were implied but not explicit enough.

See `docs/reviews/SENTINEL_ADR_004_FINDINGS_REGISTER.md` for full details and traceability.

## 11. Minor findings

Resolved:

- SNT-004-005: Side-effect ordering needed a stronger boundary contract.
- SNT-004-006: Transition coverage map needed explicit transition-ID requirements.

Open non-blocking:

- SNT-004-007: Operator message next-action language can be refined during UI implementation.

## 12. Observations

Deferred observations:

- SNT-004-008: Persistence durability remains V41-PQ-002.
- SNT-004-009: Cross-process coordination remains V41-CP-001.
- SNT-004-010: Exact timeout values remain deferred.
- SNT-004-011: UI entry point remains a future product choice.

## 13. State-model assessment

The final model clearly separates qualification workflow state from qualification result, approval state, broker lifecycle, broker-reported state, reconciliation, evidence, and emergency stop. The Sentinel owner table resolved the main ambiguity.

`UNRESOLVED` and `RECONCILIATION_REQUIRED` remain distinct and justified: unresolved means broker truth is unknown; reconciliation required means read-only recovery work is required before progression. `REJECTED`, `DISQUALIFIED`, and `ABORTED` remain distinct: rejected is an event/lifecycle outcome, disqualified is a qualification result state, and aborted is an operator/system stop of the run.

## 14. Transition assessment

The transition table remains at 35 transitions. Sentinel did not remove transitions because the table covers materially different operator, broker, reconciliation, finalization, abort, and restart cases. Broad transition rows were narrowed so they cannot bypass reconciliation or terminal-state rules.

## 15. Idempotency assessment

The model now has sufficient idempotency rules for start, approval, submission, cancellation, broker events, reconciliation, finalization, and abort. Same key plus same payload replays; same key plus different payload conflicts; uncertain external submission cannot be retried blindly.

## 16. Broker-truth assessment

Broker truth is preserved. The design explicitly distinguishes intent, approval, preparation, request sent, broker acknowledgment, broker lifecycle, and reconciliation. It does not infer success from no exception, transport success, local IDs, simulated state mutation, timeout, or absence of rejection.

## 17. Evidence assessment

The evidence envelope is sufficient for design acceptance. Sentinel strengthened finalization requirements by clarifying that evidence failure blocks qualification success and that mutable simulator state is not immutable evidence.

## 18. Failure and recovery assessment

The failure model is safe for design acceptance. The failure matrix confirms no reviewed failure path requires duplicate submission or false completion. Restart durability remains explicitly deferred to V41-PQ-002.

## 19. Concurrency assessment

Single-process expectations are clear: authoritative transition function, expected state/revision validation, monotonic revision, and stale command rejection. Multi-process safety remains deferred to V41-CP-001 and is not claimed.

## 20. Security assessment

The design enforces Paper-only scope, redaction, environment identity checks, no credential exposure, no live-trading authorization, no approval reuse across different payloads, and emergency-stop guard behavior.

## 21. Human-factors assessment

Operator-visible wording avoids false completion and distinguishes approved, submitted, acknowledged, filled, cancelled, unresolved, reconciliation required, and qualified. One minor follow-up remains: future UI implementation should add more explicit safest-next-action language to each message.

## 22. Testing assessment

The test strategy is adequate after adding transition-ID coverage requirements. It covers transitions, guards, invalid transitions, duplicate commands, duplicate broker events, stale revisions, out-of-order events, restart boundaries, failure injection, evidence assertions, no-side-effect assertions, result/workflow consistency, secret redaction, deterministic replay, emergency stop, degraded broker state, and reconciliation.

## 23. Simplicity assessment

The design is more complex than a boolean flag or simple status field, but the complexity is justified by broker truth, approval, idempotency, evidence, cancellation, unresolved state, and recovery requirements. Sentinel recommends keeping qualification workflow separate from broker lifecycle rather than collapsing states.

## 24. Future-compatibility assessment

The design is compatible with V41-PQ-002 persistence, V41-CP-001 coordination, future event publishing, durable evidence, restart recovery, future web UI, mobile monitoring, and later live-trading design review because it uses explicit interfaces and avoids selecting infrastructure prematurely.

## 25. Changes made during review

- ADR-004 accepted after corrections.
- Added state ownership table.
- Added default mandatory positive qualification scenario.
- Added failure-destination rule.
- Added side-effect boundary contract.
- Added narrowed transition-template rules.
- Added explicit failure-destination table.
- Added transition coverage map.
- Updated roadmap status.

## 26. Remaining implementation risks

- Persistence durability is not implemented.
- Cross-process coordination is not implemented.
- Timeout constants are not selected.
- External event publisher durability is not selected.
- UI entry point is not selected.
- Real broker qualification must use operator-approved Paper-only credentials and redacted evidence.

## 27. Approval checklist result

PASS WITH NOTE. See `docs/reviews/SENTINEL_ADR_004_APPROVAL_CHECKLIST.md`.

## 28. Final recommendation

Accept ADR-004 after Sentinel corrections. V41-PQ-001 may proceed to implementation only when separately authorized, with all deferred boundaries preserved.

## 29. ADR lifecycle decision

ADR-004 status changed from Proposed to Accepted. Acceptance is scoped to Paper qualification state-machine design only.

## 30. References

- `docs/reviews/SENTINEL_ADR_004_FINDINGS_REGISTER.md`.
- `docs/reviews/SENTINEL_ADR_004_FAILURE_MATRIX.md`.
- `docs/reviews/SENTINEL_ADR_004_APPROVAL_CHECKLIST.md`.
- `docs/adr/ADR-004-PAPER-QUALIFICATION-STATE-MACHINE.md`.
- `docs/engineering/V41_PQ_001_DESIGN.md`.
- `docs/engineering/V41_PQ_001_TRANSITION_TABLE.md`.
- `docs/engineering/V41_PQ_001_TEST_STRATEGY.md`.
