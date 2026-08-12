# EMERS Product Architecture

## 1. Purpose

This document maps the EMERS Trade product structure from current validated capabilities to possible future product layers.

## 2. Product hierarchy

EMERS Technologies

- EMERS Trade
  - User Experience Layer
  - Decision Intelligence Layer
  - Risk and Portfolio Layer
  - Approval and Control Layer
  - Broker Integration Layer
  - Evidence and Audit Layer
  - EduTraderAI Engine

## 3. Capability map

CURRENT: EduTraderAI application, private single-user use, Paper-first broker behavior, operator approval, local evidence, single-process limitations, and validated release governance.

PLANNED: deterministic Paper qualification, coordination analysis, event observability, performance thresholds, and release automation.

POSSIBLE: secure web access, mobile review and approval, portfolio intelligence, configurable risk policies, alerts, notifications, multi-user access, durable audit storage, supported multi-broker integrations, explainable AI assistance, administration, and support tools.

NOT AUTHORIZED: live trading, commercial launch, unofficial broker integration, multi-user production operation, cloud deployment, or regulated financial-services representation.

## 4. Experience layers

The experience layer presents portfolio condition, opportunity review, risk, approval state, broker state, audit records, and degraded-mode status.

## 5. Decision layer

The decision layer organizes signals, rankings, explanations, deterministic calculations, AI-assisted summaries, and user decisions while separating facts from interpretations.

## 6. Risk layer

The risk layer handles sizing, reward/risk, exposure, policy checks, rejection reasons, and risk budget before possible reward.

## 7. Execution layer

The execution layer coordinates explicit authorization, deterministic plan submission, broker adapters, idempotency, and reconciliation.

## 8. Portfolio layer

The portfolio layer maintains holdings, exposure, buying power views, position state, and broker snapshots without treating application assumptions as broker truth.

## 9. Evidence layer

The evidence layer preserves material action history, release records, hashes, correlation IDs, and redacted artifacts.

## 10. Administration layer

Future administration may cover settings, broker configuration, user management, support, access controls, and audit review. It is not currently implemented.

## 11. Future commercial layers

Possible commercial layers include subscription management, support workflows, billing, customer onboarding, legal acceptance, and compliance records. These are not authorized by Atlas.

## 12. Capability boundaries

Broker state, risk rules, AI outputs, user approvals, evidence records, and UI presentation must remain distinguishable.

## 13. Current versus future capabilities

Future capabilities must be labeled planned or possible until implemented, tested, validated, and released.

## 14. Dependency map

User experience should call application services. Application services should call deterministic domain logic and adapter ports. Broker adapters and external systems stay outside the core. Evidence and observability should receive structured outputs rather than scrape UI state.

## 15. Architectural risks

Risks include leaking broker concerns into the core, allowing AI to bypass deterministic rules, treating application state as broker truth, adding multi-user features before identity and authorization exist, and expanding product layers without tests.

## 16. Open decisions

Open decisions include web architecture, mobile strategy, durable storage, event infrastructure, authentication provider, external coordination mechanism, broker expansion policy, and commercial administration model.
