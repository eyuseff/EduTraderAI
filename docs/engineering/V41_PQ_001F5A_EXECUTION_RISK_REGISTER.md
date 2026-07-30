# V41-PQ-001F5A Execution Risk Register

## Purpose

Record execution risks before implementation. The register is intentionally
conservative because future Paper execution will cross a broker side-effect
boundary.

| ID | Risk | Cause | Impact | Likelihood | Severity | Prevention | Detection | Mitigation | Rollback | Owner layer | Target slice |
|---|---|---|---|---|---|---|---|---|---|---|---|
| F5A-R001 | Accidental Live execution | Shared endpoint/client or inferred mode | Real-money order | Low | Critical | Paper-only contracts; omit Live; adapter validates Paper | endpoint tests; config health | fail closed | disable executor guard | adapter/config | F5B/F6A |
| F5A-R002 | Duplicate order submission | retry after ambiguity or idempotency gap | double exposure | Medium | Critical | deterministic idempotency and durable reservation | broker/order reconciliation | stop new submits; reconcile | no rollback after dispatch; compensating cancel if safe | execution/persistence | F5E/F6B |
| F5A-R003 | Stale command execution | missing expected revision | outdated order action | Medium | High | optimistic execution revision | stale-revision tests | reject before dispatch | local only if pre-dispatch | execution core | F5B/F5C |
| F5A-R004 | Readiness mistaken for authority | semantic confusion | unintended execution | Medium | Critical | explicit approval contract; docs/tests | architecture tests | block command creation | disable new path | application | F5B/F5C |
| F5A-R005 | Qualification coupled to broker | import or side-effect leak | unsafe bounded context | Low | High | dependency rule | architecture tests | remove dependency before release | documentation/code revert before side effect | qualification | F5B+ |
| F5A-R006 | Broker-specific leakage | adapter details in qualification/planner | brittle market behavior | Medium | Medium | market-capability port | review and tests | move rules to adapter/capability | N/A | capability/adapters | F5C/F5F |
| F5A-R007 | Unsupported venue capability | unknown TIF/order type/session | broker rejection or unsafe order | Medium | High | fail-closed capability decision | capability tests | reject locally | local only | capability | F5C |
| F5A-R008 | Timeout ambiguity | network timeout after dispatch | duplicate or lost order | Medium | Critical | timeout => `OUTCOME_UNKNOWN` | timeout tests | reconcile before action | no broker rollback | execution/reconcile | F6B |
| F5A-R009 | Unsafe retry | generic retry loop | duplicate order | Medium | Critical | operation-aware retry policy | retry tests | disable retry; reconcile | no automatic rollback | orchestration | F6B |
| F5A-R010 | Lost acknowledgement | broker accepted but response lost | local/broker divergence | Medium | High | broker client ids and reconciliation | missing receipt checks | query broker | compensating action only | adapter/reconcile | F6B |
| F5A-R011 | Partial-fill mishandling | ack/fill conflated | wrong cancel/replace quantity | Medium | High | explicit partial fill state | fill-state tests | reconcile fills | cannot undo fill | execution/reconcile | F6B |
| F5A-R012 | Cancellation race | fill occurs before cancel | mistaken cancellation success | Medium | High | fill truth wins; cancel pending state | broker status evidence | reconcile | no fill rollback | execution/reconcile | F6B |
| F5A-R013 | Replacement race | fill before replace or non-atomic fallback | exposure mismatch | Medium | High | native replace only initially | replacement tests | reconcile original/replacement | compensating action only | execution/adapter | F6B |
| F5A-R014 | Process crash after broker acceptance | no durable receipt | unknown broker truth | Medium | Critical | durable command and broker ref | startup reconciliation | read-only reconciliation | no automatic resubmit | persistence/reconcile | F5E/F6B |
| F5A-R015 | Persistence inconsistency | non-atomic reservation/dispatch | duplicate or lost state | Medium | High | transaction boundary design | durability tests | halt execution | local rollback only before dispatch | persistence | F5E |
| F5A-R016 | Idempotency reservation failure | reservation not unique/durable | duplicate command | Medium | High | uniqueness constraint | conflict tests | reject and reconcile | pre-dispatch only | persistence | F5E |
| F5A-R017 | Reconciliation failure | broker query unavailable or conflicting | unresolved outcome | Medium | High | unresolved state and operator action | reconciliation result | block state-changing commands | none | reconcile | F6B |
| F5A-R018 | Emergency-stop race | stop set during dispatch | new order after stop | Low | High | check before reservation and dispatch; reconcile after ambiguity | audit timeline | prevent future orders; reconcile | no broker rollback | safety guard | F5C/F6A |
| F5A-R019 | Approval bypass | command lacks explicit approval | unauthorized order | Low | Critical | required approval fingerprint | approval tests | reject locally | local only | approval/application | F5C |
| F5A-R020 | Credential leakage | raw payload/exception logged | secret exposure | Low | Critical | redaction and prohibited fields | secret-scan tests | rotate credentials | N/A | adapter/security | F5B/F5F |
| F5A-R021 | Raw payload leakage | audit stores SDK response | privacy/security issue | Medium | High | safe receipt schema | audit review | redact and regenerate evidence if possible | cannot erase external logs | adapter/audit | F5B/F6C |
| F5A-R022 | Audit gap | event/audit failure after dispatch | incomplete evidence | Medium | High | append-only audit requirement | missing-record checks | operator incident; reconcile | none after dispatch | audit/persistence | F6C |
| F5A-R023 | Dual legacy/new execution | both paths authoritative | duplicate broker order | Low | Critical | one-authority-at-a-time guard | call-site scan | disable new path | no broker rollback | runtime/adapters | F6A/F7 |
| F5A-R024 | Scanner lifecycle interference | scanner bypasses supervisor/executor | unsafe automation | Low | High | scanner imports application services only | architecture tests | rollback scanner flag | no broker rollback if submitted | scanner/supervisor | F7 |
| F5A-R025 | Supervisor lifecycle interference | supervisor calculates risk or brokers directly | boundary erosion | Low | High | service-only orchestration | architecture tests | move logic back inward | N/A | supervisor | F5C+ |
| F5A-R026 | Market-session error | stale/unknown session facts | rejected or unintended order timing | Medium | High | capability decision with timestamp | session tests | reject unknown/closed | local only | capability | F5C |
| F5A-R027 | Symbol tradability error | symbol unavailable or unsupported | broker rejection | Medium | Medium | symbol capability check | capability tests | reject locally | local only | capability | F5C |
| F5A-R028 | Quantity/price normalization error | tick/lot/fraction rules ignored | broker rejection or wrong order | Medium | High | capability layer normalizes/validates | adapter certification | reject; correct adapter | local only before dispatch | capability/adapter | F5C/F5F |
| F5A-R029 | Rate-limit storm | unbounded queries/retries | broker lockout | Medium | Medium | bounded retry and backoff | metrics/alerts | halt retries | N/A | adapter/orchestration | F6B |
| F5A-R030 | Broker outage | broker unavailable | stalled execution | Medium | Medium | failure taxonomy and outage state | broker failure metrics | reject or mark unknown if dispatch possible | local only if pre-dispatch | adapter | F6A/F6B |
| F5A-R031 | Event duplication | replay publishes duplicate events | noisy audit | Medium | Medium | event idempotency | duplicate event checks | dedupe by event key | N/A | audit/events | F6C |
| F5A-R032 | Event loss | publisher failure | audit gap | Medium | High | command outcome independent of publisher; audit classification | event attempt metrics | operator incident | N/A | audit/events | F6C |
| F5A-R033 | Configuration drift | flags/endpoints change silently | wrong environment | Medium | High | startup validation and health | config tests | fail startup | restore config | platform | F6A |
| F5A-R034 | Unsupported Chilean venue assumptions | undocumented local market rules | invalid future broker behavior | Medium | Medium | require venue adapter and regulatory review | design review | block Chile adapter | N/A | capability/adapter | future |

## Critical-risk summary

The unresolved critical risks are not blockers for F5B contracts because F5B
does not execute broker side effects. They become blockers before F6A controlled
Paper broker submission unless mitigated by durable idempotency, revision,
Paper-only validation, explicit approval, reconciliation, adapter certification,
and one-authority runtime guarding.
