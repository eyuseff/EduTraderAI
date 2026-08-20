# EduTraderAI documentation

> **Current-status boundary:** this file is a documentation index, not the authoritative release-status record. For the current repository status, start with the [root README](../README.md) and the operational documents linked below. Historical engineering, roadmap, prototype, and vision documents may describe earlier states and must not be treated as current implementation or release authority.

## Current v4.1 release line

EduTraderAI is in the `v4.1.0-rc1` **Paper-only** release-candidate observation window.

- RC commit: `3296e319cafacd89ad703ca49b298b953b51223d`
- RC published UTC: `2026-08-20T17:20:13Z`
- Earliest Stable review: `2026-08-27T17:20:13Z`
- Stable-promotion tracking: issue `#94`

Do not infer Stable readiness from elapsed time, CI success, repository activity, or the pre-RC connected qualification. The Stable gate also requires the documented post-RC Paper-market observation sessions and the final review/acceptance steps. No order may be submitted, replaced, or cancelled merely to satisfy the observation quota.

## Authoritative operational documents

- [v4.1 Stable promotion plan](operations/V41_STABLE_PROMOTION_PLAN.md)
- [v4.1 release observation log](operations/V41_RELEASE_OBSERVATION_LOG.md)
- [release readiness assessment](operations/RELEASE_READINESS_ASSESSMENT_V4.md)
- [evidence manifest](operations/EVIDENCE_MANIFEST.md)
- [RC runbook](operations/RC_RUNBOOK.md)
- [final GO/NO-GO review](operations/FINAL_GO_NO_GO_REVIEW_V4.md)
- [operator release acceptance](operations/OPERATOR_RELEASE_ACCEPTANCE_V4.md)

The historical [v4.0 observation log](operations/RELEASE_OBSERVATION_LOG.md) is retained as release-history evidence and does **not** count toward the v4.1 Stable gate.

## Repository validation gates

Pull requests into `main` are expected to pass the established repository gates before merge:

- **Continuous feature validation**
- **Release verification**
- **Performance regression gate**

These repository gates run without broker credentials and do not authorize broker activity, Live trading, deployment, or release publication.

## Documentation map

- `adr/` — architecture decision records
- `engineering/` — implementation reports, inventories, reviews, and test strategies
- `operations/` — release, evidence, incident, qualification, and operator procedures
- `roadmap/` — planning and benchmark baselines
- `architecture/` — architecture reference material
- `atlas/`, `horizon/`, `vision/` — directional product and experience documents

Documents outside the authoritative operational set can be valuable historical or design context, but status statements inside them may be superseded by later implementation, accepted ADRs, merged pull requests, or release evidence. When status conflicts, use the root README, current operational documents, accepted ADRs, the exact repository state, and current CI evidence.

## Safety boundary

Current repository documentation does not grant authority to enable Live trading, expose broker credentials or account identifiers, access protected production `state/`, deploy production services, publish unredacted evidence, or create/publish a Stable release without the explicit promotion gates being satisfied.
