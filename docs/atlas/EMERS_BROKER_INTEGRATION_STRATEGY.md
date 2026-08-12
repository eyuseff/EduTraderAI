# EMERS Broker Integration Strategy

## 1. Purpose

This strategy defines how EMERS should approach broker integrations safely and credibly.

## 2. Broker-integration principles

Use official supported APIs only, documented authentication only, no browser automation for trading, no reverse-engineered private endpoints, no credential scraping, no assumed order success, explicit broker acknowledgment, deterministic qualification where possible, full lifecycle evidence, safe retry policy, duplicate prevention, visible unresolved states, Paper qualification before external exposure, and separate approval for every supported broker.

## 3. Current Alpaca Paper foundation

The current foundation includes Alpaca Paper lifecycle evidence and v4.1 planning for deterministic one-share Paper qualification. This does not authorize live trading.

## 4. Adapter architecture

Broker adapters should translate broker APIs into explicit application contracts without recalculating risk, sizing, or policy outcomes.

## 5. Qualification requirements

Each broker requires Paper or sandbox validation where available, endpoint verification, credential safety, non-marketable test flow where practical, order status retrieval, cancellation, cleanup, evidence, and duplicate prevention.

## 6. Order lifecycle

Lifecycle states include created, submitted, acknowledged, rejected, partially filled, filled, cancelled, expired, unresolved, and failed.

## 7. State reconciliation

Application state must reconcile with broker truth for orders, fills, open orders, cancellations, and positions.

## 8. Idempotency

Every material broker action needs an idempotency strategy to prevent duplicate orders and replay confusion.

## 9. Failure handling

Failures must be visible, typed, and recoverable where possible. Unknown broker state must not be treated as success.

## 10. Cancellation

Cancellation must retrieve broker confirmation or clearly mark unresolved state.

## 11. Partial fills

Partial fills require explicit handling for remaining quantity, exposure, order status, and audit evidence.

## 12. Market-hours behavior

Market-hours assumptions must be explicit. Qualification must avoid accidental fills and understand order validity.

## 13. Rate limits

Broker rate limits require backoff, bounded retry, visibility, and no uncontrolled retry loops.

## 14. Credential handling

Credentials must be loaded securely, redacted, revocable, and never committed, logged, or included in support artifacts.

## 15. Sandbox and Paper environments

Paper or sandbox environments must be technically separated from live endpoints and fail closed when ambiguous.

## 16. Future live-trading requirements

Future live trading would require separate legal, regulatory, security, operational, broker, and release approval. It is not authorized by Atlas.

## 17. Multi-broker considerations

Multi-broker support requires consistent contracts, broker-specific capabilities, qualification per broker, evidence per broker, and clear unsupported behavior.

## 18. Broker selection criteria

Evaluate official API availability, Paper or sandbox support, API documentation quality, account eligibility, geographic availability, supported instruments, order types, rate limits, webhook or event support, authentication model, operational reliability, legal and contractual restrictions, support quality, auditability, cost, and maintenance burden.

## 19. Unsupported integration methods

Unsupported methods include browser automation for trading, scraping credentials, reverse-engineered private endpoints, unofficial trading routes, and integration paths that cannot provide broker acknowledgment and audit evidence.

## 20. eToro research status

eToro integration remains a research question. No assumption should be made that a suitable official trading API is available for the intended account type, jurisdiction, or use case.

Any future investigation must verify official API availability, permitted account access, geographic and account restrictions, trading capability, Paper or sandbox support, authentication, terms of use, commercial restrictions, data-access rights, and legal and regulatory implications. Browser automation or unofficial integration should not be recommended.

## 21. Open decisions

Open decisions include next broker research target, qualification contract, supported order types, evidence schema, webhook handling, and broker capability matrix.
