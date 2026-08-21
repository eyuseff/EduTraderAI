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
| Observed commit | Record the exact RC/main commit actually observed. |
| Environment | Confirm Paper-only operation; do not record Live credentials or identifiers. |
| Account-active status | Record only the fully redacted active/inactive result; never an account identifier. |
| Blocking-flag status | Record only fully redacted blocking-flag results. |
| AAPL eligibility | Record the eligibility result observed for AAPL. |
| Quote freshness | Record the freshness result without raw broker payloads. |
| Application observations | Summarize the application observations actually performed. |
| Broker observations | Summarize broker observations actually performed; this template does not require or authorize an order. |
| Incident summary | Record `None` or a sanitized incident summary/reference. |
| Cleanup status | Record final cleanup status, including whether any order or position remains unresolved, without broker identifiers. |

A session is not countable if any required field is absent or if the proposed public record contains credentials, account identifiers, broker order identifiers, raw broker payloads, or unredacted logs. Do not increment the session count until a completed, redacted numbered session section is appended and reviewed against this contract.

Counted evidence sections must use the exact heading form `### Session N`, beginning with `### Session 1` and increasing consecutively by one. The `Post-RC Paper-market sessions` status above must equal the number of those completed numbered sections; a template, prose note, CI run, or unnumbered section cannot advance the count.

## Recorded sessions

No qualifying post-RC Paper-market sessions are recorded yet.

When a qualifying session is available, append a numbered section containing only redacted, reviewable evidence and update the session count above. Do not infer broker-side observations from repository or CI state.
