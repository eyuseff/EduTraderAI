# EduTraderAI v4.1 Stable Promotion Plan

## Purpose and boundary

This plan governs the Paper-only observation window between `v4.1.0-rc1` and
v4.1 Stable. It inherits the established v4.0 release discipline without
authorizing Live trading, unattended broker actions, credential persistence,
deployment, or automatic Stable publication.

## Release identity and observation window

| Item | Value |
|---|---|
| Release candidate | `v4.1.0-rc1` |
| RC commit | `3296e319cafacd89ad703ca49b298b953b51223d` |
| RC published UTC | `2026-08-20T17:20:13Z` |
| Minimum elapsed observation | Seven calendar days |
| Minimum separate Paper-market sessions | Five |
| Earliest Stable review | `2026-08-27T17:20:13Z` |
| Stable identity, if authorized | `v4.1.0` |

The Connected Alpaca Paper qualification completed before RC publication and
does not count as one of the five post-RC observation sessions. CI runs and
repository-only checks also do not count as Paper-market sessions.

## Required session evidence

Each post-RC session must record a timezone-aware UTC start and end, the exact
RC/main commit observed, Paper-only environment confirmation, account-active
and blocking-flag status in fully redacted form, AAPL eligibility, quote
freshness, application and broker observations performed, incident summary,
and cleanup status.

Credentials, account identifiers, broker order identifiers, raw broker
payloads, and unredacted logs must never be committed or published. A session
does not need an order. No additional order may be submitted, replaced, or
cancelled merely to satisfy an observation quota.

## Automated daily checks

The daily readiness monitor may perform only repository and GitHub read-only
checks:

1. confirm local `main`, `origin/main`, and the RC tag target;
2. confirm the GitHub release remains a non-draft prerelease;
3. confirm published asset names, sizes, and SHA-256 digests;
4. inspect CI conclusions and open issues;
5. validate the retained local connected-evidence bundle when available;
6. report elapsed days, recorded session count, incidents, and current
   `EXTEND VALIDATION`, `BLOCK`, or `READY FOR FINAL REVIEW` recommendation.

The monitor must not use broker credentials, contact a broker, access protected
runtime data, mutate repository files, create tags/releases, or deploy.

## Stable acceptance criteria

Stable review is blocked unless all conditions hold:

- seven calendar days have elapsed since RC publication;
- five separate post-RC Paper-market sessions are documented;
- no incorrect quantity, unintended duplicate, silent drift submission,
  unresolved order/position, unexplained crash, evidence drift, or unresolved
  incident exists;
- the one-share Connected Alpaca Paper qualification remains validator-clean;
- `make verify` and the protected performance regression gate pass on the exact
  proposed Stable commit;
- release evidence remains redacted, hash-valid, and bound to that commit;
- a final v4.1 GO/NO-GO review is recorded; and
- the operator explicitly accepts the final review and Paper-only restrictions.

Passing this plan does not authorize Live trading or deployment. Stable tag and
GitHub Release creation remain separate consequential publication actions.

## Current status

| Item | Status |
|---|---|
| Elapsed observation | In progress from `2026-08-20T17:20:13Z` |
| Post-RC Paper-market sessions | 2 of 5 recorded |
| Repository verification | PASS at RC publication |
| Performance gate | PASS at RC publication |
| Connected qualification | PASS; pre-RC and not session credit |
| Incidents | None recorded |
| Recommendation | **EXTEND VALIDATION** |
