# EduTraderAI v4.1 Release Observation Log

## Purpose and boundary

This is the canonical repository log for post-RC Paper-market observation sessions used by the `v4.1.0` Stable-promotion gate. It supplements the Stable promotion plan and issue #94 without authorizing broker credentials, unattended broker actions, additional orders, Live trading, deployment, or automatic Stable publication.

The historical `docs/operations/RELEASE_OBSERVATION_LOG.md` records the v4.0 observation campaign and is not v4.1 session evidence.

## Release identity

| Item | Value |
|---|---|
| Release candidate | `v4.1.0-rc1` |
| RC commit | `3296e319cafacd89ad703ca49b298b953b51223d` |
| RC published UTC | `2026-08-20T17:20:13Z` |
| Minimum elapsed observation | Seven calendar days |
| Minimum separate Paper-market sessions | Five |
| Earliest Stable review | `2026-08-27T17:20:13Z` |
| Tracking issue | `#94` |

## Current status

| Item | Status |
|---|---|
| Post-RC Paper-market sessions | 0 of 5 recorded |
| Incidents | None recorded |
| Recommendation | **EXTEND VALIDATION** |

No post-RC Paper-market session is credited merely because CI, repository checks, or the pre-RC Connected Alpaca Paper qualification passed.

## Session eligibility

A session may be counted only when its evidence records all fields required by `V41_STABLE_PROMOTION_PLAN.md`: timezone-aware UTC start and end timestamps, the exact RC/main commit observed, Paper-only environment confirmation, fully redacted account-active and blocking-flag status, AAPL eligibility, quote freshness, application and broker observations performed, incident summary, and cleanup status.

Credentials, account identifiers, broker order identifiers, raw broker payloads, and unredacted logs must never be committed or published. A session does not require an order, and no order may be submitted, replaced, or cancelled merely to satisfy the observation quota.

## Required session record shape

Every numbered session section appended to this log must contain the following redacted fields. This table is a recording contract only; it is not session evidence and does not itself create session credit.

| Required field | Recording rule |
|---|---|
| Session start UTC | Record a timezone-aware UTC start timestamp. |
| Session end UTC | Record a timezone-aware UTC end timestamp. |
| Observed commit | Record the full lowercase 40-character SHA of the exact RC/main commit actually observed; it must resolve as a repository commit on the RC-to-current-HEAD lineage. |
| Environment | Record `PAPER` exactly after confirming Paper-only operation; any other value is non-qualifying. Do not record Live credentials or identifiers. |
| Account-active status | Record exactly `ACTIVE` or `INACTIVE`; never record an account identifier. |
| Blocking-flag status | Record exactly `CLEAR` or `BLOCKED`; never record raw broker/account flags or identifiers. |
| AAPL eligibility | Record exactly `ELIGIBLE` or `INELIGIBLE`; never record raw broker eligibility payloads or identifiers. |
| Quote freshness | Record exactly `FRESH` or `STALE`; never record raw broker quote payloads or identifiers. |
| Application observations | Record exactly `OBSERVED` when the required application observations completed without a reportable issue, or `ISSUE #N` using a positive repository issue number when a finding exists; never record free-form logs, identifiers, or payloads. |
| Broker observations | Record exactly `OBSERVED` when the required broker observations completed without a reportable issue, or `ISSUE #N` using a positive repository issue number when a finding exists; never record free-form broker data, identifiers, or payloads; this template does not require or authorize an order. |
| Incident summary | Record exactly `NONE` when no incident occurred or `ISSUE #N` using a positive repository issue number; never record free-form incident details, identifiers, or raw broker payloads in this log. |
| Cleanup status | Record exactly `CLEAN` or `UNRESOLVED`; never record raw order/position identifiers, account identifiers, broker identifiers, or broker payloads. |

A session is not countable if any required field is absent or if the proposed public record contains credentials, account identifiers, broker order identifiers, raw broker payloads, or unredacted logs. Do not increment the session count until a completed, redacted numbered session section is appended and reviewed against this contract.

Counted evidence sections must use the exact heading form `### Session N`, beginning with `### Session 1` and increasing consecutively by one. The `Post-RC Paper-market sessions` status above must equal the number of those completed numbered sections; a template, prose note, CI run, or unnumbered section cannot advance the count.

Within each numbered section, every required field must be recorded as exactly one two-cell Markdown table row in the form `| Required field | Redacted value |`. The value must be non-empty and substantive. Blank values and placeholders such as `TBD`, `TODO`, `N/A`, `NA`, `UNKNOWN`, or `-` do not qualify as session evidence and must not advance the count.

The `Observed commit` field is fail-closed and lineage-bound: every counted session must record a full lowercase 40-character SHA that resolves to a repository commit, is the RC commit or one of its descendants, and is an ancestor of the repository `HEAD` validating the evidence. Branch names, abbreviated SHAs, nonexistent objects, pre-RC commits, and commits outside that RC-to-current-HEAD lineage are non-qualifying.

The `Environment` field is fail-closed: every counted session must record exactly `PAPER`. Any other value, including `LIVE`, does not qualify for session credit.

The `Account-active status` field is fail-closed and identifier-free: every counted session must record exactly `ACTIVE` or `INACTIVE`. Any other value is non-qualifying so an account number, account name, or other account identifier cannot be embedded in this field.

The `Blocking-flag status` field is fail-closed and redacted: every counted session must record exactly `CLEAR` when no blocking broker/account flag is observed or `BLOCKED` when any blocking flag is observed. Any other value is non-qualifying; never record raw flag names, raw flag values, account identifiers, or broker identifiers in this field.

The `AAPL eligibility` field is fail-closed and redacted: every counted session must record exactly `ELIGIBLE` when AAPL is eligible for the observed Paper workflow or `INELIGIBLE` when it is not. Any other value is non-qualifying; never record raw broker eligibility responses, asset identifiers, account identifiers, or broker identifiers in this field.

The `Quote freshness` field is fail-closed and redacted: every counted session must record exactly `FRESH` when the session's reviewed quote-freshness check passes or `STALE` when it does not. Any other value is non-qualifying; never record raw broker quote payloads, broker quote identifiers, account identifiers, or broker identifiers in this field.

The `Application observations` field is fail-closed and reference-only: every counted session must record exactly `OBSERVED` when the required application observations completed without a reportable issue, or `ISSUE #N` where `N` is a positive repository issue number containing the sanitized finding. Any other value is non-qualifying; never record free-form application logs, identifiers, or payloads in this log.

The `Broker observations` field is fail-closed and reference-only: every counted session must record exactly `OBSERVED` when the required broker observations completed without a reportable issue, or `ISSUE #N` where `N` is a positive repository issue number containing the sanitized finding. Any other value is non-qualifying; never record free-form broker data, account identifiers, broker order identifiers, broker identifiers, or raw broker payloads in this log. Recording this field does not require or authorize an order.

The `Incident summary` field is fail-closed and reference-only: every counted session must record exactly `NONE` when no incident occurred, or `ISSUE #N` where `N` is a positive repository issue number containing the sanitized incident record. Any other value is non-qualifying; never record free-form incident details, identifiers, or raw broker payloads in this log.

The `Cleanup status` field is fail-closed and redacted: every counted session must record exactly `CLEAN` when no unresolved order or position remains at end-of-session cleanup, or `UNRESOLVED` when any order or position remains unresolved or cleanup cannot be completed. Any other value is non-qualifying; never record order identifiers, position identifiers, account identifiers, broker identifiers, or raw broker payloads in this field.

## Recorded sessions

No qualifying post-RC Paper-market sessions are recorded yet.

When a qualifying session is available, append a numbered section containing only redacted, reviewable evidence and update the session count above. Do not infer broker-side observations from repository or CI state.
