# EMERS Product Principles

## Document control

| Field | Value |
|---|---|
| Document | EMERS Product Principles |
| Status | Foundational product standard |
| Organization | EMERS Technologies |
| Product | EMERS Trade |

Each principle includes meaning, required behavior, prohibited behavior, design
test, engineering implication, and expected evidence.

## 1. Risk before return

| Field | Guidance |
|---|---|
| Principle | Risk before return |
| Meaning | The product must explain downside before emphasizing upside. |
| Required product behavior | Show planned loss, exposure, rejection reasons, and uncertainty before reward. |
| Prohibited behavior | Lead with profit language while hiding risk. |
| Design test | Can a user understand what can go wrong before seeing possible reward? |
| Engineering implication | Risk fields and rejection paths must be first-class contracts. |
| Evidence expected | Risk and reward calculations, rejection evidence, and UI screenshots. |

## 2. Human control

| Field | Guidance |
|---|---|
| Principle | Human control |
| Meaning | Meaningful user authority remains central. |
| Required product behavior | Require explicit authorization for consequential broker actions. |
| Prohibited behavior | Let automation silently remove approval. |
| Design test | Can the user approve, reject, stop, or disable the action? |
| Engineering implication | Services must expose approval state and block unauthorized submission. |
| Evidence expected | Approval logs, tests, and broker-order reconciliation. |

## 3. Explain before acting

| Field | Guidance |
|---|---|
| Principle | Explain before acting |
| Meaning | Material actions need reasons before execution. |
| Required product behavior | Present rationale, assumptions, and policy outcomes before submission. |
| Prohibited behavior | Submit first and explain afterward. |
| Design test | Can the action be explained in plain language before it happens? |
| Engineering implication | Planner and service results must carry explanations. |
| Evidence expected | Preview evidence and policy traces. |

## 4. Safe by default

| Field | Guidance |
|---|---|
| Principle | Safe by default |
| Meaning | Unsafe or unclear state must fail closed. |
| Required product behavior | Default to simulator or Paper-safe behavior and reject invalid configuration. |
| Prohibited behavior | Proceed with ambiguous broker mode. |
| Design test | What happens when configuration is missing or contradictory? |
| Engineering implication | Startup validation must block unsafe combinations. |
| Evidence expected | Configuration validation tests and health reports. |

## 5. Paper before external exposure

| Field | Guidance |
|---|---|
| Principle | Paper before external exposure |
| Meaning | Broker workflows must be qualified in Paper before broader exposure. |
| Required product behavior | Require Paper-only qualification and evidence before expansion. |
| Prohibited behavior | Treat live-like exposure as implicit or automatic. |
| Design test | Has the broker path been proven safely in Paper? |
| Engineering implication | Broker adapters need explicit mode checks. |
| Evidence expected | Paper qualification artifacts and endpoint guard tests. |

## 6. One action, one authorization

| Field | Guidance |
|---|---|
| Principle | One action, one authorization |
| Meaning | One approval should map to one material action. |
| Required product behavior | Prevent duplicate submission and idempotency confusion. |
| Prohibited behavior | Reuse approval to submit multiple orders unexpectedly. |
| Design test | Does each order have one clear authorization record? |
| Engineering implication | Idempotency and correlation IDs must be preserved. |
| Evidence expected | Duplicate-prevention tests and order-count reconciliation. |

## 7. Broker truth over application assumptions

| Field | Guidance |
|---|---|
| Principle | Broker truth over application assumptions |
| Meaning | The broker state is authoritative for submitted orders. |
| Required product behavior | Retrieve and reconcile broker acknowledgment, status, cancellation, fills, and open orders. |
| Prohibited behavior | Assume success from application state alone. |
| Design test | Can the app prove what the broker saw? |
| Engineering implication | Adapters must surface broker status without recalculating plans. |
| Evidence expected | Broker status evidence and reconciliation reports. |

## 8. Visible failures

| Field | Guidance |
|---|---|
| Principle | Visible failures |
| Meaning | Failures must be shown, not hidden. |
| Required product behavior | Display failure states and preserve failure evidence. |
| Prohibited behavior | Convert errors into silent no-ops. |
| Design test | Would an operator know what failed and what remains unresolved? |
| Engineering implication | Errors need typed outcomes and observable metrics. |
| Evidence expected | Failure mapping tests and incident records. |

## 9. Honest uncertainty

| Field | Guidance |
|---|---|
| Principle | Honest uncertainty |
| Meaning | Market information and models are uncertain. |
| Required product behavior | Mark stale, delayed, incomplete, estimated, or model-generated information. |
| Prohibited behavior | Represent uncertain estimates as facts. |
| Design test | Can the user tell what is known and what is assumed? |
| Engineering implication | Contracts should distinguish facts, assumptions, and model outputs. |
| Evidence expected | Evidence fields and explanation tests. |

## 10. Evidence for material actions

| Field | Guidance |
|---|---|
| Principle | Evidence for material actions |
| Meaning | Important decisions must be reconstructable. |
| Required product behavior | Create redacted evidence for previews, submissions, broker outcomes, and release gates. |
| Prohibited behavior | Leave no trail for consequential actions. |
| Design test | Could a reviewer reconstruct the sequence later? |
| Engineering implication | Events, metrics, and exports must share identifiers. |
| Evidence expected | JSON/JSONL artifacts, hashes, and manifest checks. |

## 11. Privacy and security by design

| Field | Guidance |
|---|---|
| Principle | Privacy and security by design |
| Meaning | Sensitive information should be minimized and protected. |
| Required product behavior | Redact credentials, secrets, account numbers, balances, and personal data from documents and evidence. |
| Prohibited behavior | Print secrets or store unnecessary account data. |
| Design test | Does the feature work without exposing sensitive data? |
| Engineering implication | Evidence serializers must enforce redaction. |
| Evidence expected | Secret scans and redaction tests. |

## 12. Reversible operations

| Field | Guidance |
|---|---|
| Principle | Reversible operations |
| Meaning | Prefer reversible or cleanly recoverable paths before irreversible action. |
| Required product behavior | Use preview, confirmation, cancellation, rollback, and cleanup checks where possible. |
| Prohibited behavior | Make irreversible changes without warning or escape. |
| Design test | Can the operator stop or recover from the action? |
| Engineering implication | Broker flows need cancellation and cleanup states when available. |
| Evidence expected | Cleanup evidence and rollback tests. |

## 13. Calm product design

| Field | Guidance |
|---|---|
| Principle | Calm product design |
| Meaning | The interface should support disciplined thought. |
| Required product behavior | Use plain language, clear hierarchy, and no manipulative urgency. |
| Prohibited behavior | Use fear, hype, countdowns, or casino-like cues. |
| Design test | Does the design make the user calmer and better informed? |
| Engineering implication | Presentation code should favor clarity over engagement tricks. |
| Evidence expected | UX review notes and rejected-claim checks. |

## 14. No engagement manipulation

| Field | Guidance |
|---|---|
| Principle | No engagement manipulation |
| Meaning | The product should not optimize trading frequency at the expense of wellbeing. |
| Required product behavior | Measure quality, safety, and understanding rather than clicks or order count. |
| Prohibited behavior | Pressure users to trade more often. |
| Design test | Does the feature benefit the user even if they choose not to trade? |
| Engineering implication | Analytics must avoid perverse incentives. |
| Evidence expected | Metric definitions and product review records. |

## 15. Compatibility and migration discipline

| Field | Guidance |
|---|---|
| Principle | Compatibility and migration discipline |
| Meaning | Changes should preserve trusted workflows. |
| Required product behavior | Version evidence schemas, document migrations, and keep v4.0 workflows compatible unless deprecated. |
| Prohibited behavior | Break workflows silently. |
| Design test | Can existing users and evidence still be understood? |
| Engineering implication | Interfaces need versioning and compatibility tests. |
| Evidence expected | Migration notes and backward-compatibility tests. |

## 16. Every release earns trust

| Field | Guidance |
|---|---|
| Principle | Every release earns trust |
| Meaning | Release is a safety event, not a calendar event. |
| Required product behavior | Require tests, evidence, documented limitations, and explicit approval. |
| Prohibited behavior | Ship around failed safety gates. |
| Design test | Would the release withstand a serious operational review? |
| Engineering implication | Verification and manifest checks must remain release gates. |
| Evidence expected | Release reports, hashes, and verification output. |

## Feature-decision test

A proposed feature should not proceed unless the team can answer:

- Does it make the user safer?
- Does it improve decision quality?
- Does it preserve meaningful human control?
- Can its behavior be explained?
- Can its failure be detected?
- Can its actions be audited?
- Can it be tested deterministically?
- Can it be disabled or reversed?
- Does it avoid misleading claims?
- Is the user benefit greater than the added risk and complexity?
