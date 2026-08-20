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

## Recorded sessions

No qualifying post-RC Paper-market sessions are recorded yet.

When a qualifying session is available, append a numbered section containing only redacted, reviewable evidence and update the session count above. Do not infer broker-side observations from repository or CI state.
