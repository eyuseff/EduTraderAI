# Sentinel ADR-006 Failure Matrix

## Purpose

Map safe lifecycle destinations for failures, replays, duplicates, and
ambiguous observations. This is review evidence only.

## Failure destination matrix

| Failure category | Before possible external effect | After possible external effect | Revision | Side-effect behavior |
|---|---|---|---|---|
| Contract construction error | Remain current or `FAILED_TERMINAL` for programming invariant | Preserve broker-truth state and require operator review | No increment unless accepted terminal transition | None |
| Eligibility `INELIGIBLE` | `INELIGIBLE` | Not applicable; eligibility must occur pre-dispatch | +1 on accepted record | None |
| Eligibility `INDETERMINATE` | `INELIGIBLE` for command progression | Not applicable | +1 on accepted record | None |
| Approval missing/stale | Remain current or `INELIGIBLE` | Not applicable | No increment unless accepted failure transition | None |
| Idempotency conflict | Remain current; conflict failure | Preserve current broker-truth state | No increment | None |
| Stale revision | Remain current; stale failure | Preserve current broker-truth state | No increment | None |
| Persistence conflict | Remain current pre-dispatch | `OUTCOME_UNKNOWN` only if dispatch ambiguity exists | No increment unless accepted unknown transition | None |
| Dispatch preparation failure | `ABORTED_BEFORE_DISPATCH` when safe | Not applicable | +1 when accepted abort | None |
| Timeout before dispatch boundary | `ABORTED_BEFORE_DISPATCH` or remain current | Not applicable | +1 only on accepted abort | None |
| Timeout after possible dispatch | Not applicable | `OUTCOME_UNKNOWN` | +1 accepted unknown | No retry |
| Broker rejection | Not applicable | `BROKER_REJECTED` | +1 accepted observation | None |
| Broker acknowledgement ambiguity | Not applicable | `OUTCOME_UNKNOWN` or `RECONCILIATION_REQUIRED` | +1 accepted unknown/reconcile | None |
| Duplicate broker observation | No-op | No-op unless new monotonic fact | No increment for duplicate | None |
| Conflicting broker observation | Not applicable | `RECONCILIATION_REQUIRED` | No normal increment | None |
| Partial fill conflict | Not applicable | `RECONCILIATION_REQUIRED` | No normal increment | None |
| Cancellation ambiguity | Not applicable | `OUTCOME_UNKNOWN` or `RECONCILIATION_REQUIRED` | +1 if accepted ambiguity transition | No repeat cancel |
| Replacement ambiguity | Not applicable | `OUTCOME_UNKNOWN` or `RECONCILIATION_REQUIRED` | +1 if accepted ambiguity transition | No repeat replace |
| Emergency stop race | Block pre-dispatch progression | Preserve in-flight truth and reconcile if ambiguous | Depends accepted transition | No new dispatch |

## Replay and duplicate matrix

| Input type | Replay identity | Exact duplicate | Conflicting duplicate | Revision | Evidence | Reconciliation |
|---|---|---|---|---|---|---|
| Lifecycle command | command ID + payload fingerprint | Return original outcome | Duplicate conflict | No increment | Replay marker | No unless conflict after effect |
| Eligibility observation | command ID + result fingerprint | No-op/replay | Conflict blocks progression | No increment | Replay marker | No |
| Approval observation | approval fingerprint + command binding | No-op/replay | Approval conflict | No increment | Replay marker | No |
| Idempotency reservation | idempotency key + logical payload | Replay reservation | Idempotency conflict | No increment | Replay/conflict marker | No |
| Dispatch record | dispatch identity + command payload | No repeat dispatch | Outcome unknown if ambiguous | No repeat increment | Dispatch replay marker | Yes if ambiguous |
| Broker acknowledgement | broker reference + receipt fingerprint | No-op | Reconciliation required | No increment | Duplicate marker | Yes on conflict |
| Partial fill | broker fill observation identity + cumulative quantity | No-op | Reconciliation required | No increment duplicate; +1 new monotonic fact | Fill evidence | Yes on conflict |
| Fill | broker fill observation identity | No-op | Reconciliation required | No increment duplicate | Fill evidence | Yes on conflict |
| Cancellation request | command ID + payload | Replay request | Duplicate conflict | No increment | Replay marker | No |
| Cancellation confirmation | broker reference + receipt fingerprint | No-op | Reconciliation required | No increment duplicate | Cancellation evidence | Yes on conflict |
| Replacement request | command ID + payload | Replay request | Duplicate conflict | No increment | Replay marker | No |
| Replacement confirmation | broker reference + receipt fingerprint | No-op | Reconciliation required | No increment duplicate | Replacement evidence | Yes on conflict |
| Reconciliation outcome | reconciliation run ID + comparison fingerprint | Replay outcome | Remain reconciliation required | No increment duplicate | Reconciliation evidence | Yes |

## Guard classification

| Guard | F5D1 implementable | Requires persistence | Requires external service | Requires broker evidence |
|---|---:|---:|---:|---:|
| expected revision matches | Yes with in-memory aggregate | Yes for durable use | No | No |
| Paper-only mode | Yes | No | No | No |
| command identity present | Yes | No | No | No |
| aggregate identity matches | Yes | No | No | No |
| correlation identity matches | Yes | No | No | No |
| idempotency key present | Yes | No | No | No |
| idempotency payload consistency | Partial | Yes | No | No |
| eligibility result recorded | Yes | No | No | No |
| eligibility decision compatible | Yes | No | No | No |
| explicit approval recorded | Yes | No | No | No |
| approval binding valid | Yes | No | No | No |
| approval unexpired at supplied evaluation time | Yes | No | No | No |
| policy snapshot compatible | Yes | No | No | No |
| external prerequisites represented | Yes as unresolved/deferred | No | Yes for clearance | No |
| emergency stop permits progression | No, represent deferred guard | No | Yes | No |
| persistence/idempotency reservation confirmed | No | Yes | No | No |
| broker observation identity present | Contract only | No | No | Yes |
| broker reference present where required | Contract only | No | No | Yes |
| fill quantity monotonic | Future aggregate can check | Yes for durable use | No | Yes |
| cancellation valid for current state | Yes | Yes for durable use | No | Later broker evidence |
| replacement valid for current state | Yes | Yes for durable use | Capability service later | Later broker evidence |
| reconciliation before consequential mutation | Yes as restricted state | Yes for durable use | Reconciliation service later | Yes |
