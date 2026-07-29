# V41-PQ-001D Implementation Report: Qualification Evidence Adapter

## 1. Purpose

V41-PQ-001D implements the canonical evidence-adapter contract for ADR-004 Paper qualification evidence.

The adapter transforms qualification `EvidenceIntent` objects into deterministic, redacted, integrity-checked canonical evidence records suitable for future persistence and replay preparation. This slice establishes the evidence contract only; it does not establish durable persistence or runtime integration.

## 2. Scope implemented

- Canonical qualification evidence record model.
- Canonical schema version.
- Evidence type mapping.
- Deterministic evidence-record builder.
- Evidence normalization and canonical JSON serialization.
- SHA-256 integrity digest and verification helper.
- Strict metadata and safe-message redaction policy.
- Port-compatible in-memory canonical evidence recorder.
- Application-service compatibility through the existing `QualificationEvidenceRecorder` port.
- Scenario-harness compatibility with canonical records.
- Evidence-adapter tests and architecture fitness checks.

## 3. Scope excluded

- Disk persistence.
- Database persistence.
- File rotation or retention policy.
- Encryption-at-rest infrastructure.
- External event publishing.
- Message queues.
- Broker request logging.
- Replay engine.
- Distributed tracing.
- Runtime wiring.
- CLI, API, or UI entry points.
- Live-environment evidence.

## 4. Architecture

The implemented dependency direction is:

```text
EvidenceIntent
      ↓
Qualification Evidence Adapter
      ↓
Canonical Qualification Evidence Record
      ↓
Abstract QualificationEvidenceRecorder Port
      ↓
Future durable adapter — deferred
```

The state machine produces `EvidenceIntent`. The application service passes those intents through the existing recorder port. Canonical transformation lives inside the adapter/recorder layer, not in `service.py` and not in `state_machine.py`.

## 5. Files created

- `volcanoes/application/qualification/evidence.py`
- `tests/test_paper_qualification_evidence.py`
- `docs/engineering/V41_PQ_001D_IMPLEMENTATION_REPORT.md`

## 6. Files updated

- `volcanoes/application/qualification/contracts.py`
- `volcanoes/application/qualification/state_machine.py`
- `volcanoes/application/qualification/__init__.py`
- `tests/test_architecture_dependencies.py`
- `docs/engineering/V41_PQ_001_DESIGN.md`
- `docs/roadmap/EDUTRADERAI_V4_1_ROADMAP.md`

## 7. Canonical evidence model

`QualificationEvidenceRecord` is immutable and contains:

- schema version;
- deterministic evidence ID;
- evidence type;
- qualification run ID;
- qualification scenario ID;
- transition ID;
- event type;
- command ID;
- correlation ID;
- idempotency key;
- source and destination states;
- previous and next revisions when supplied by `EvidenceIntent`;
- qualification result;
- reason code;
- actor type;
- environment;
- safe operator message;
- reconciliation, replay, and diagnostic flags;
- safe object reference;
- explicit timestamp supplied by the caller;
- normalized metadata;
- redaction metadata;
- integrity metadata.

No unsupported broker facts, account identifiers, credentials, or timestamps are invented.

## 8. Schema version

The canonical evidence schema identifier is:

```text
qualification-evidence/v1
```

Unknown schema versions fail deterministically with `EvidenceSchemaVersionError`. No backward compatibility beyond this version is claimed.

## 9. Evidence-type mapping

The implemented evidence types are:

- `QUALIFICATION_TRANSITION_ACCEPTED`
- `QUALIFICATION_TRANSITION_REJECTED`
- `QUALIFICATION_IDEMPOTENCY_CONFLICT`
- `QUALIFICATION_GUARD_FAILED`
- `QUALIFICATION_RECONCILIATION_REQUIRED`
- `QUALIFICATION_TERMINAL_RESULT`

Mapping is deterministic from `EvidenceIntent` fields. The adapter does not emit evidence that implies broker execution, persistence durability, external publishing, or live-trading authorization.

## 10. Record identity

Evidence IDs are deterministic SHA-256-derived identifiers prefixed with `qe-`.

The identity input includes stable fields:

- schema version;
- qualification run ID;
- transition ID;
- command ID;
- source state;
- destination state;
- previous revision;
- next revision;
- evidence type;
- replay indicator.

Equivalent logical input produces the same ID. Materially different identity input produces a different ID. Same ID with conflicting canonical content is rejected by the in-memory recorder.

## 11. Timestamp policy

The adapter never reads wall-clock time. `occurred_at` must be supplied explicitly as a timezone-aware `datetime`. Naïve timestamps are rejected. Timestamps are normalized to ISO 8601 UTC with `Z` suffix.

## 12. Normalization

The adapter normalizes:

- enum values to stable strings;
- timestamps to UTC `Z`;
- optional fields to explicit `null`;
- metadata keys to sorted lowercase keys;
- tuples to ordered arrays during serialization;
- booleans and integer revisions as primitive JSON values.

Unsupported metadata types are rejected safely.

## 13. Canonical serialization

`serialize_qualification_evidence(record)` emits compact deterministic JSON using:

- sorted keys;
- `ensure_ascii=True`;
- compact separators;
- explicit `null` handling;
- `allow_nan=False`.

The output is suitable for future hashing, persistence, audit comparison, and replay preparation. It is not a durable event format by itself.

## 14. Integrity digest

`compute_evidence_digest(record)` computes SHA-256 over canonical evidence excluding the digest value itself.

`verify_evidence_digest(record)` verifies that digest. The digest is not a digital signature and does not establish authenticity by itself. It only supports comparison against a trusted reference.

## 15. Redaction policy

Secret-like metadata keys are replaced with `[REDACTED]` and recorded in redaction metadata. Prohibited raw payload fields such as `raw_payload` and `broker_payload` are rejected.

The adapter detects key terms including API keys, secrets, tokens, passwords, authorization, cookies, private/access/refresh keys, account numbers, connection strings, and database URLs.

## 16. Safe-message policy

Safe messages must be non-empty, length-bounded, single-line, and free of exception traces or authorization headers. Messages containing known secret markers are replaced with `[REDACTED]` and marked in redaction metadata.

## 17. Metadata policy

Metadata is immutable and tightly constrained. Allowed values are strings, integers, booleans, null, and tuples of those scalar values. Nested mappings, sets, callables, exception objects, SDK objects, bytes, absolute local paths, and raw payload fields are rejected.

## 18. Evidence builder API

The public adapter API is:

```python
QualificationEvidenceAdapter.build(intent, *, occurred_at, additional_metadata=())
QualificationEvidenceAdapter.build_many(intents, *, occurred_at, additional_metadata=())
```

The adapter preserves input order, does not mutate intents, does not persist, does not publish, validates schema, normalizes fields, redacts unsafe values, derives deterministic identity, and computes integrity metadata.

## 19. Recorder adapter

`InMemoryCanonicalQualificationEvidenceRecorder` implements the existing `QualificationEvidenceRecorder` port. It accepts `EvidenceIntent` objects, builds canonical records internally, stores immutable snapshots in deterministic insertion order, and returns `EvidenceRecordReference` values.

It is explicitly non-durable and local.

## 20. Port compatibility

The existing `QualificationEvidenceRecorder` port remains unchanged. The application service still sends evidence intents through the port and receives safe references. No concrete global recorder was introduced.

## 21. Application-service integration

`PaperQualificationService` remains unaware of canonical serialization, digest calculation, redaction, and storage infrastructure. No evidence transformation logic was added to `service.py`.

## 22. Scenario-harness integration

The scenario harness works with the canonical in-memory recorder because the recorder implements the existing port. Tests assert canonical schema, evidence IDs, transition trace, revision trace, evidence type trace, redaction status, and digest validity.

## 23. Duplicate behavior

Duplicate behavior is deterministic:

- same evidence ID and equivalent canonical content returns the existing reference and does not append a second record;
- same evidence ID and conflicting canonical content raises `EvidenceRecordConflictError`;
- replayed commands that produce no evidence intents do not cause the recorder to manufacture records.

## 24. Error model

Evidence errors include:

- `QualificationEvidenceError`
- `EvidenceSchemaVersionError`
- `EvidenceValidationError`
- `EvidenceRedactionError`
- `EvidenceSerializationError`
- `EvidenceIntegrityError`
- `EvidenceRecordConflictError`

Each exposes a stable reason code and safe message without original secret values or raw payloads.

## 25. Security

Tests prove fake secrets do not appear in record fields, canonical serialization, digest metadata, record IDs, exception text, or evidence references. No real credentials are used.

## 26. Privacy

Canonical records include only qualification traceability fields. They do not include personal names, email addresses, phone numbers, home addresses, government identifiers, account balances, complete broker account identifiers, machine usernames, or local repository paths.

## 27. Default scenario evidence trace

The default `PQ-SCN-005` evidence transition trace is:

```text
PQ-TRN-001
PQ-TRN-002
PQ-TRN-005
PQ-TRN-006
PQ-TRN-009
PQ-TRN-010
PQ-TRN-011
PQ-TRN-015
PQ-TRN-017
PQ-TRN-030
```

The revision trace is:

```text
1, 2, 3, 4, 5, 6, 7, 8, 9, 10
```

The evidence-type trace is:

```text
QUALIFICATION_TRANSITION_ACCEPTED
QUALIFICATION_TRANSITION_ACCEPTED
QUALIFICATION_TRANSITION_ACCEPTED
QUALIFICATION_TRANSITION_ACCEPTED
QUALIFICATION_TRANSITION_ACCEPTED
QUALIFICATION_TRANSITION_ACCEPTED
QUALIFICATION_TRANSITION_ACCEPTED
QUALIFICATION_TRANSITION_ACCEPTED
QUALIFICATION_TRANSITION_ACCEPTED
QUALIFICATION_TERMINAL_RESULT
```

## 28. Determinism

Given identical `EvidenceIntent`, timestamp, schema version, metadata, adapter configuration, and scenario inputs, the canonical record, record ID, serialization, digest, evidence reference, and ordered evidence stream are logically equivalent.

## 29. Architectural fitness functions

Architecture tests enforce that:

- evidence adapter imports no broker, simulator, UI, CLI, infrastructure, network, filesystem, event publisher, or subprocess modules;
- evidence adapter contains no runtime-effect tokens;
- `service.py` does not implement canonical serialization;
- `state_machine.py` and scenario models do not import the evidence adapter;
- qualification package boundaries remain inward-only.

## 30. Test coverage

`tests/test_paper_qualification_evidence.py` covers canonical record building, schema validation, identity, timestamp normalization, serialization determinism, digest verification, redaction, metadata validation, duplicate semantics, service compatibility, scenario-harness compatibility, default trace/revision/evidence-type assertions, and no-external-effect proof.

## 31. No-external-effect proof

Tests prove the adapter and recorder do not open files, access simulator state, read environment variables, call network clients, instantiate broker adapters, or invoke external event publishers.

## 32. Persistence boundary

Canonical records are not durable. The in-memory recorder is for deterministic local execution and tests only.

## 33. Publishing boundary

No external publisher is connected. The adapter does not import `EventPublisher` or `NullEventPublisher`.

## 34. Broker boundary

No broker call occurs. Canonical evidence may record normalized broker observation facts already represented in `EvidenceIntent`, but it never verifies broker state or claims a broker side effect occurred beyond the approved transition evidence.

## 35. Coordination boundary

No cross-process coordination is added. Duplicate detection is process-local within an in-memory recorder instance.

## 36. Known limitations

- No durable evidence store.
- No hash chain across prior evidence records.
- No production persistence transaction boundary.
- No replay engine.
- No runtime entry point.
- No Paper workflow integration.

## 37. Rollback

No runtime integration was added. Rollback consists of not using the canonical recorder/adapter. Existing Paper Order behavior is unchanged.

## 38. Verification results

Initial focused verification after implementation:

```text
python3 -m pytest -q \
  tests/test_paper_qualification_state_machine.py \
  tests/test_paper_qualification_service.py \
  tests/test_paper_qualification_scenarios.py \
  tests/test_paper_qualification_evidence.py \
  tests/test_architecture_dependencies.py

304 passed
```

Final verification:

```text
Focused qualification/evidence/architecture tests: 304 passed
Focused Ruff: PASS
Focused MyPy: PASS
make verify: PASS
Full pytest suite: 677 passed
Architecture tests: 30 passed
Coverage: 82.2%
```

## 39. Next implementation slice

Next: V41-PQ-001E — Paper Qualification Workflow Integration Design.

V41-PQ-001 remains in progress. Runtime integration, production persistence, durable evidence storage, broker execution wiring, and cross-process coordination remain deferred.
