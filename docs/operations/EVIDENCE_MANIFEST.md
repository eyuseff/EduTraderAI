# EduTraderAI v4.0 Operational Evidence Manifest

This manifest records the integrity of local operational-validation evidence.
It does not contain credentials, complete account identifiers, or live-broker
payloads. Files under `build/validation/` are intentionally ignored by Git and
must remain available in the operator's local evidence location until the stable
decision is complete.

Rows explicitly marked `EXCLUDED` preserve historical source-path provenance
only. They identify mutable runtime files and must not be evaluated as immutable
evidence. Their authoritative frozen replacements are recorded in the governance
correction below.

## Release identity

| Item | Value |
|---|---|
| Release candidate | `v4.0.0-rc1` |
| Release-candidate commit | `ddc765b95d0663991db5aade74acbf09c66e3323` |
| Current corrective commit | `6a1cf97b9027ceb92242a032bca9b4bb802ff662` |
| Valid observation sessions | 5 of 5 |

## Evidence-governance correction — 2026-07-22

This is an administrative evidence correction, not a software correction or an
operational validation session. Two historical rows pointed at live runtime
paths whose contents can change during normal operation. Exact historical bytes
matching the previously recorded hashes were recovered from the original
validation working tree and frozen under immutable names in `build/validation/`.
The old paths and hashes remain recorded below for provenance, but the frozen
paths in this table supersede them as the authoritative evidence targets.

| Authoritative frozen path | Historical mutable source path | Reason | SHA-256 | Status |
|---|---|---|---|---|
| `build/validation/session1-simulated-broker-state-frozen.json` | `state/simulated_broker.json` | The simulator rewrites its live state during order, cancellation, position-close, and reset operations | `669ed4abfe0ff1b50b54ca1011eef0aba214a5e04bd41c4a0764bda60657811c` | Recovered byte-for-byte and verified |
| `build/validation/session1-scanner-audit-frozen.jsonl` | `logs/automation_audit.jsonl` | The scanner audit writer appends runtime events to the live log | `a0dce8f6ecf924d1373a338f0fa159bf3c247223c776111f5c5ae2ff4b646f01` | Recovered byte-for-byte and verified |

Future immutable-integrity checks must verify the two frozen paths above and
must exclude the corresponding live runtime paths. No historical digest was
deleted or changed.

## Historical Session 1 evidence

Session 1 did not receive stable credit, but its simulator order remains
preserved as historical incident evidence. The original row below is retained
as source-path provenance and is superseded by the frozen broker-state entry in
the 2026-07-22 governance correction. The live path must not be reset merely to
match evidence and must not be mixed with later isolated session state.

| Historical mutable source path | Bytes | Modified UTC | SHA-256 |
|---|---:|---|---|
| EXCLUDED — `state/simulated_broker.json`; source provenance only | 2737 | 2026-07-21T03:20:41.851976Z | `669ed4abfe0ff1b50b54ca1011eef0aba214a5e04bd41c4a0764bda60657811c` |

## Session 2 evidence

Session 2 used an isolated Local Simulator state. The temporary broker state was
removed only after the authoritative export and reconciler evidence were
written. These three files are the retained session record.

| Evidence role | Path | Bytes | Modified UTC | SHA-256 |
|---|---|---:|---|---|
| Initial health and zero-counter snapshot | `build/validation/session2-initial-20260721T033959Z.json` | 3567 | 2026-07-21T03:40:00.498823Z | `bffb354c0175e6bc21b28b4ea7af6d375c432f50862a9b43d6f67e66e34a145f` |
| Authoritative final operational snapshot | `build/validation/session2-final-20260721T033959Z.json` | 3651 | 2026-07-21T03:40:03.865724Z | `44d5cf603f7373be8ba279fc1d3bd1df87d83115f84398e6723d1f636620223d` |
| Supplementary broker and counter reconciliation | `build/validation/session2-observer-20260721T033959Z.json` | 7979 | 2026-07-21T03:40:03.867419Z | `06486efedad80951d1ce1fb265f5565a12d7000b526e2a3b836e8a8984ee46b3` |

The final export records three previews, two approved plans, one rejected plan,
one submission, no scanner signal, six event-publication attempts, and zero
drift, duplicate, cooldown, symbol-busy, broker, or instrumentation failures.
The observer evidence records a successful reconciliation for every required
counter, latency, deterministic-quantity, and broker-order check.

## Session 3 evidence

Session 3 used a fresh isolated Local Simulator state and a controlled MSFT
scanner signal. The temporary runtime directory was removed after the simulator
state and scanner audit were preserved. No external market or broker call was
made.

| Evidence role | Path | Bytes | Modified UTC | SHA-256 |
|---|---|---:|---|---|
| Initial health and zero-counter snapshot | `build/validation/session3-initial-20260721T154621Z.json` | 3567 | 2026-07-21T15:46:21Z | `224cb44d5751bf00814461c5cf253c9a25ec26155eba5b14b795c2e4597c17c3` |
| Authoritative final operational snapshot | `build/validation/session3-final-20260721T154621Z.json` | 3671 | 2026-07-21T15:46:22Z | `89700b3e04e6e3819dbeb0ae68a4bfb6f5297841eaddb4ccf228c774ad71c9cc` |
| Broker and counter reconciliation | `build/validation/session3-observer-20260721T154621Z.json` | 11195 | 2026-07-21T15:46:22Z | `11abb6137638a374a96e4b1cda582cf8d47c72cdef303afce8bafacdd3bdb506` |
| Preserved isolated simulator state | `build/validation/session3-broker-20260721T154621Z.json` | 835 | 2026-07-21T15:46:21Z | `29299f24af900a646898c000376441b86ba5a400655a6a5c557215b5bbc6279d` |
| Controlled scanner audit | `build/validation/session3-scanner-audit-20260721T154621Z.jsonl` | 343 | 2026-07-21T15:46:21Z | `abf923322438f246ccd3675cbb1eb25a4f67a592b4736ebda4bf06fe2fac1a55` |
| Pre-session verification metadata | `build/validation/session3-pre-verification-20260721T154621Z.json` | 230 | 2026-07-21T15:46:59Z | `52ad5010b2adcb51ea8c60e927eab144f06976aac96ea22342a5fe18f5acd1f5` |
| Post-session verification metadata | `build/validation/session3-post-verification-20260721T154621Z.json` | 230 | 2026-07-21T15:47:19Z | `54afbb6b9d460d62489f29cd44b88ff3cf70a7097933e3f57ebc7c922b36e5fa` |

The final export records four previews, three approved plans, one rejected plan,
two submissions, one scanner signal, one scanner decision, ten event-publication
attempts, and zero drift, replay, conflict, duplicate, cooldown, symbol-busy,
broker, or instrumentation failures. The two submissions and two unique broker
orders agree on AAPL 100 and MSFT 100. The LOW rejection created no order.

## Session 4 evidence

Session 4 used a fresh isolated Local Simulator state, a controlled AMZN scanner
signal, and a manual NVDA scenario distinct from Session 3. The temporary runtime
state was removed only after broker state and scanner audit evidence were
preserved. No external market or broker call was made.

| Evidence role | Path | Bytes | Modified UTC | SHA-256 |
|---|---|---:|---|---|
| Initial health and zero-counter snapshot | `build/validation/session4-initial-20260721T160635Z.json` | 3567 | 2026-07-21T16:06:35.970676Z | `540faea2441ee9fbae02b745f63c5fd7b8fb3d5aa1d529ba0a96c0de0014e93f` |
| Authoritative final operational snapshot | `build/validation/session4-final-20260721T160635Z.json` | 3682 | 2026-07-21T16:06:37.182834Z | `cf3ee66d4c4ca73cf0e770f36e4ca000b5d6d5b8e5182c99ea7aa4c57d5120fd` |
| Broker and counter reconciliation | `build/validation/session4-observer-20260721T160635Z.json` | 5465 | 2026-07-21T16:09:22.840955Z | `1f482b39777e885d25b89f2acec92fa09c80040fba85fa3237f895f694f09b16` |
| Preserved isolated simulator state | `build/validation/session4-broker-20260721T160635Z.json` | 830 | 2026-07-21T16:06:36.068250Z | `ada10887cb812973bb32c67e2f75a424ba0b525504fbbf4b5d74c36e48d9a288` |
| Controlled scanner audit | `build/validation/session4-scanner-audit-20260721T160635Z.jsonl` | 342 | 2026-07-21T16:06:36.068354Z | `9fe341752ece4b8d73e2a33bef6272f8aefde88e859f9d7c20af6937a39e8749` |
| Pre-session verification metadata | `build/validation/session4-pre-verification-20260721T160635Z.json` | 230 | 2026-07-21T16:02:43.863234Z | `b3e7eeff322b3d007a7c4257f90dae97e784a6cf01cc8951c5c0f3d0f61e6827` |
| Post-session verification metadata | `build/validation/session4-post-verification-20260721T160635Z.json` | 230 | 2026-07-21T16:14:46.043932Z | `8c67be7893064ba9a7c3dc79738313861115ed283937a20ac60159e80e161758` |
| Retained observer-harness mismatch record | `build/validation/session4-failure-20260721T160635Z.json` | 10201 | 2026-07-21T16:06:37.185099Z | `6b07c54728da9d11001a5fc15692b294d3b5d18fd23adb8b0823eba3325885d9` |

The final export records six previews, four approved plans, two rejected plans,
two submissions, one scanner signal, one scanner decision, 14 event-publication
attempts, and zero drift, replay, conflict, duplicate, cooldown, symbol-busy,
broker, or instrumentation failures. The two submissions and unique broker
orders agree on NVDA 125 and AMZN 62. BADRR was rejected for reward/risk and
created no order. The two extra UI-driven preview outcomes are explicitly
reconciled in the observer record. `OV-2026-07-21-003` retains the original
external-harness mismatch without changing the authoritative session evidence.

## Invalid Session 5 attempt evidence

The Session 5 attempt used fresh isolated Local Simulator state and stopped at
the mandatory rejection gate. TSLA 62 was submitted once and reconciled in the
partial record. The planned OVERCAP rejection instead produced a valid
deterministic quantity cap to 40 and remained approved, so the scanner, final
export, and post-session verification were not run. These files document an
invalid attempt and add no stable-session credit.

| Evidence role | Path | Bytes | Modified UTC | SHA-256 |
|---|---|---:|---|---|
| Initial health and zero-counter snapshot | `build/validation/session5-initial-20260722T122838Z.json` | 3567 | 2026-07-22T12:28:38.523884Z | `a84fcd1121b83ce61affe6e28f80242f9936decc7bcc70a3f381b5b86ee2710b` |
| Pre-session verification metadata | `build/validation/session5-pre-verification-20260722T122838Z.json` | 230 | 2026-07-22T12:23:27.489768Z | `72c5edeef76911b8a6ee359faccfc408df335e8393d65525a9859667795512d0` |
| Partial observer and stop record | `build/validation/session5-failure-20260722T122838Z.json` | 3497 | 2026-07-22T12:28:38.571761Z | `ba53a4641cf235bbbb6fb6be5d15e26a7ba1389a83f5edeffa9b4e543465e2d5` |
| Preserved partial isolated simulator state | `build/validation/session5-partial-broker-20260722T122838Z.json` | 457 | 2026-07-22T12:30:01.961074Z | `4583340f9c3c969e6b098a6a01af26a90d7eb9ec6736b6ef4a24c425267a7ffb` |

The partial broker state contains exactly one accepted TSLA bracket-limit order
for 62 shares. No OVERCAP order exists. Because the final snapshot was not
exported, the attempt has no authoritative final metrics or full event-attempt
reconciliation. `OV-2026-07-22-004` records the Low operations/scenario-selection
failure. The manifest's valid-session count remains 3 of 5.

## Invalid Session 6 attempt evidence

Session 6 stopped at the mandatory repository identity gate. The observed
branch and HEAD did not match the required validation branch and corrective
commit. No verification, application, simulator, manual, rejection, scanner, or
broker workflow started. This attempt adds no stable-session credit.

| Evidence role | Path | Bytes | Modified UTC | SHA-256 |
|---|---|---:|---|---|
| Repository-gate failure and stop record | `build/validation/session6-failure-20260722T193908Z.json` | 1547 | 2026-07-22T19:39:42.219018Z | `4d7c60b0eb7366ab144b17171a662a73f103e64e86fb51ebd83f0764ad76387f` |

Incident `OV-2026-07-22-005` classifies the mismatch as a Low
operations/configuration issue. No product defect or trading outcome occurred.
The manifest's valid-session count remains 3 of 5.

## Session 7 evidence

Session 7 used fresh isolated Local Simulator state and a controlled CRM scanner
signal. The manual AMD trade, BADRR7 hard rejection, supervised scanner order,
operational metrics, and broker evidence reconciled exactly. No external market
or broker call was made.

| Evidence role | Path | Bytes | Modified UTC | SHA-256 |
|---|---|---:|---|---|
| Initial health and zero-counter snapshot | `build/validation/session7-initial-20260722T201156Z.json` | 3567 | 2026-07-22T20:11:57.516712Z | `06075da892a4f0dc379291aedd6d3ac0c22b8fa7d6df8c56945a0672fbc65b6d` |
| Authoritative final operational snapshot | `build/validation/session7-final-20260722T201156Z.json` | 3678 | 2026-07-22T20:11:57.657905Z | `f6875e2d3e98255d64014323313b33301d903f67a1a0c7a346a48530ae13e35a` |
| Broker and counter reconciliation | `build/validation/session7-observer-20260722T201156Z.json` | 5051 | 2026-07-22T20:12:53.421493Z | `a0f10808b82175366fd0eb4c4649e90dc0fe98370fe3d4a93a461a762538473f` |
| Preserved isolated simulator state | `build/validation/session7-broker-20260722T201156Z.json` | 828 | 2026-07-22T20:11:57.625460Z | `b60846097f4ab880fe0e6f682e1cbf3f781d6585d6ab82c2ef586a11e7aa4c02` |
| Controlled scanner audit | `build/validation/session7-scanner-audit-20260722T201156Z.jsonl` | 341 | 2026-07-22T20:11:57.625550Z | `c167085ed27cffa5453c0ec80849e792e56702414e3f151303819b7265be7e5f` |
| Pre-session verification metadata | `build/validation/session7-pre-verification-20260722T201156Z.json` | 230 | 2026-07-22T20:07:12.176891Z | `62677f5ade468575bc42926358827580835d4a3047dfa7e3050c7bb25b296ddf` |
| Post-session verification metadata | `build/validation/session7-post-verification-20260722T201156Z.json` | 230 | 2026-07-22T20:12:27.000541Z | `0b37973037f7ea8231c8b1e2eaaa761a7e5d68703a5c1f39dac1b15b4f958528` |

The final export records five previews, four approved plans, one rejected plan,
two submissions, one scanner signal, one scanner decision, and eleven event
publication attempts. The two submissions and two unique simulator orders agree
on AMD 125 and CRM 62. BADRR7 was rejected because reward/risk 1.50 was below
the required 2.00, displayed approved quantity `—`, and created no order. Drift,
replay, conflict, duplicate execution, cooldown, symbol-busy, broker failure,
and instrumentation failure counters were all zero. Session 7 adds stable credit
and advances the campaign to 4 of 5 valid sessions.

## Session 8 evidence

Session 8 used fresh isolated Local Simulator state and a controlled ORCL
scanner signal. The manual MSFT trade, BADRR8 hard rejection, supervised
scanner order, operational metrics, simulator evidence, scanner audit, and
passively observed publication sequence reconciled exactly. No external market
or broker call was made.

| Evidence role | Path | Bytes | Modified UTC | SHA-256 |
|---|---|---:|---|---|
| Initial health and zero-counter snapshot | `build/validation/session8-initial-20260723T125022Z.json` | 3567 | 2026-07-23T13:03:44Z | `b4972cf147e1a04e9916d57411a7ff18de1ce7524606333fd78a5cd33936bb41` |
| Authoritative final operational snapshot | `build/validation/session8-final-20260723T125022Z.json` | 3666 | 2026-07-23T13:03:44Z | `9c091c1c1ae0138ba1d824cf540a76719b93a4e5823c661d2ed0366ad4619cc1` |
| Observer, event, and counter reconciliation | `build/validation/session8-observer-20260723T125022Z.json` | 12835 | 2026-07-23T13:06:37Z | `26b5b7d33957735c7bb83f76a6361fd5ac16b8884b4c49fd77c540edacd6f89b` |
| Preserved isolated simulator state | `build/validation/session8-broker-20260723T125022Z.json` | 830 | 2026-07-23T13:03:44Z | `c27e7e970f0846066608ee3092f16d873426237ec934458ef1b523c50299b768` |
| Controlled scanner audit | `build/validation/session8-scanner-audit-20260723T125022Z.jsonl` | 342 | 2026-07-23T13:03:44Z | `02e5fb33dda21aac31609ad1e889b68aaa661c64768fbb1b2b473d752ee4e034` |
| Pre-session verification metadata | `build/validation/session8-pre-verification-20260723T125022Z.json` | 230 | 2026-07-23T12:59:37Z | `d2a2a2a2b0b24b46aa038d91681a4b1e0ac1a043ca491d572fba9195829c7ad7` |
| Post-session verification metadata | `build/validation/session8-post-verification-20260723T125022Z.json` | 230 | 2026-07-23T13:12:45Z | `7ab0c8dfae12e29d0e5f83aaae6b416f332d4c834b5a6f1733c9a167c22a1516` |

The final export records five previews, four approved plans, one rejected plan,
two submissions, one scanner signal, one scanner decision, and eleven event
publication attempts. The submissions and two unique accepted simulator orders
agree on MSFT 125 and ORCL 62. BADRR8 was rejected because reward/risk 1.50 was
below the required 2.00, displayed approved quantity `—`, and created no order.
Drift, replay, conflict, duplicate execution, cooldown, symbol-busy, broker
failure, instrumentation failure, external market calls, and external broker
calls were all zero. Session 8 adds stable-session credit and satisfies the
five-session operational-validation count at 5 of 5. This does not declare v4
Stable; the seven-calendar-day span, credentialed Alpaca Paper smoke, and final
infrastructure dispositions remain pending.

## Alpaca Paper smoke-test evidence

The Alpaca Paper smoke test was completed by the operator through the normal
EduTraderAI Paper Order workflow and finalized without any additional broker
interaction. The evidence is redacted and records the lifecycle as
operator-reported facts: Paper authentication had succeeded, the account was
ACTIVE, the LLY bracket-limit order was accepted, zero shares filled, the order
was cancelled, no position was created, no open orders remained, and no live
order occurred.

The qualification has an accepted limitation: the controlled smoke procedure
specified a one-share maximum, but the existing risk engine approved and
submitted 100 shares. The order was intentionally non-marketable at the
observed market level, remained unfilled, and was cancelled successfully.

| Evidence role | Path | Bytes | Modified UTC | SHA-256 |
|---|---|---:|---|---|
| Redacted Alpaca Paper smoke-test lifecycle and reconciliation summary | `build/validation/alpaca-paper-smoke-20260728T203604Z.json` | 4835 | 2026-07-28T20:37:09.725280Z | `8bad2738bfc2fa36122800ce52d619165c972e6df8d2875609102b9435f5e561` |

The smoke test is classified as **PASS WITH ACCEPTED LIMITATION**. It proves
Paper authentication, application-to-broker submission, broker acknowledgment,
broker status visibility, zero-fill verification, cancellation, final
no-open-orders state, and no live trading. It does not demonstrate deterministic
one-share smoke-test sizing.


## Final GO / NO-GO release-review evidence

The final review was documentation and evidence work only. No broker endpoint was
contacted, no credentials were accessed, and no order was submitted. The review
classified the candidate as **CONDITIONAL GO** pending operator acceptance of the
documented Paper-only release restrictions and accepted limitations.

| Evidence role | Path | Bytes | Modified UTC | SHA-256 |
|---|---|---:|---|---|
| Redacted final GO / NO-GO review decision and release-gate summary | `build/validation/final-go-no-go-review-20260728T205012Z.json` | 5527 | 2026-07-28T20:50:59.619260Z | `9af1e8971aebebf0040fc2714f9a476ffe03e6f8a6e45c00a8e9582b0328f80b` |


## Stable release authorization evidence

The operator accepted the completed validation campaign and authorized the
EduTraderAI v4.0.0 Stable release under the documented Paper-only deployment
restrictions. This authorization evidence contains no credentials, account
identifiers, broker payloads, or live-order data.

| Evidence role | Path | Bytes | Modified UTC | SHA-256 |
|---|---|---:|---|---|
| Redacted operator acceptance and Stable release authorization record | `build/validation/stable-release-authorization-20260728T205723Z.json` | 3153 | 2026-07-28T20:57:59.410701Z | `bf49882b78054b1ded966fbe0eccb338d307d33f42daef936146495aa905c21e` |

## Supporting preflight and rehearsal evidence

These ignored local artifacts are retained because the validation log cites the
preflight or controlled rehearsal, or because they are the original timestamped
copies of named Session 2 evidence. They do not add stable-session credit.

| Role | Path | SHA-256 |
|---|---|---|
| Pre-campaign release/export rehearsal | `build/validation/v4.0.0-rc1-20260720-225515.json` | `70841068050290c4f5efc9ed3848c9dbb27580a20973d9685a679698255e4f55` |
| Pre-campaign release/export rehearsal | `build/validation/v4.0.0-rc1-20260720-230009.json` | `6a1255b2edb5664a0da7d54a8c9b1b22082132edb3dc9856432a9885ab121c31` |
| Campaign kickoff preflight | `build/validation/v4.0.0-rc1-20260720-230714.json` | `4958ef533dd00dfc13a9732bb8295f9e796a5df05e3ab21283d1217f3aa7766e` |
| Controlled scanner rehearsal | `build/validation/v4.0.0-rc1-20260720-230901.json` | `770f9265d85b9a2f85c85af0c8328db456bb3c9cb9b70533cd05bf072fdb0ed1` |
| Rehearsal scanner audit — EXCLUDED mutable source; superseded by frozen evidence | `logs/automation_audit.jsonl` | `a0dce8f6ecf924d1373a338f0fa159bf3c247223c776111f5c5ae2ff4b646f01` |
| Original Session 2 initial export; byte-identical to named initial evidence | `build/validation/v4.0.0-rc1-20260720-234000.json` | `bffb354c0175e6bc21b28b4ea7af6d375c432f50862a9b43d6f67e66e34a145f` |
| Original Session 2 final export; byte-identical to named final evidence | `build/validation/v4.0.0-rc1-20260720-234003.json` | `44d5cf603f7373be8ba279fc1d3bd1df87d83115f84398e6723d1f636620223d` |

`build/verification.json` and `build/coverage.json` are rolling release-tool
outputs overwritten by every required `make verify`; they are not immutable
session paths. Their Session 2 digests at the prior checkpoint were
`7296733ec3b7078fcea395002d0f438c8823ee1a9b9f2529aec7f26fde250c33` and
`6567662670f762b4e259e50bc0c3232f441d50a4bc0b56fff6c40dfa78e080a3`.
Session 3 preserves its pre- and post-session verification metadata under the
named immutable paths above. The current rolling post-session outputs have
SHA-256 `54afbb6b9d460d62489f29cd44b88ff3cf70a7097933e3f57ebc7c922b36e5fa`
and `402af39c7dd8774be978f1fd2d8db82970632e63db9a0500f85ab45108afab3c`.

## Integrity procedure

Before a weekly review or stable decision:

1. Recompute SHA-256 for every authoritative immutable evidence file. Skip rows
   explicitly marked `EXCLUDED` and verify their superseding frozen records.
2. Compare path, size, and digest with this manifest and `VALIDATION_LOG.md`.
3. Parse every JSON file and confirm the final export remains sanitized.
4. Record missing files, digest changes, parse failures, or sensitive content as
   evidence incidents before continuing the campaign.
5. Add later sessions without replacing or renaming earlier evidence entries.
