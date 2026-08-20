# EduTraderAI

EduTraderAI is a deterministic, explainable trading research and execution platform. AI may assist research and recommendations; execution remains governed by deterministic controls and explicit operating boundaries.

## Current release status

The active development line is **v4.1, Paper-only**.

- Release candidate: `v4.1.0-rc1`
- RC commit: `3296e319cafacd89ad703ca49b298b953b51223d`
- RC published: `2026-08-20T17:20:13Z`
- Stable observation gate: tracked in issue #94
- Earliest Stable review: `2026-08-27T17:20:13Z`
- Current recommendation: **EXTEND VALIDATION**

The Stable observation window requires seven calendar days and five separate post-RC Paper-market sessions. Observation sessions do not require additional orders, and no order may be submitted, replaced, or cancelled merely to satisfy the observation quota.

Passing the Stable-promotion gate does **not** authorize Live trading, deployment, production credential use, unattended broker actions, or automatic Stable publication.

## Authoritative v4.1 operational documents

- [Stable promotion plan](docs/operations/V41_STABLE_PROMOTION_PLAN.md)
- [Release readiness assessment](docs/operations/RELEASE_READINESS_ASSESSMENT_V4.md)
- [Evidence manifest](docs/operations/EVIDENCE_MANIFEST.md)
- [Release observation log](docs/operations/RELEASE_OBSERVATION_LOG.md)
- [RC runbook](docs/operations/RC_RUNBOOK.md)

## Required repository gates

Changes proposed for the release line are expected to preserve the established repository gates:

- Continuous feature validation
- Release verification
- Performance regression gate

For broader engineering and architecture documentation, see [`docs/`](docs/).
