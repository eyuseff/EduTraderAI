# EMERS Information Architecture

## 1. Purpose

Define how EMERS Trade organizes product areas, navigation, statuses, objects, and current versus future information.

## 2. Information-architecture principles

Risk and state first; broker truth visible; stale data labeled; future features separated; every material object has identifiers; evidence stays reachable.

## 3. Primary navigation

Conceptual primary navigation: Home, Portfolio, Opportunities, Watchlists, Trade Plans, Orders, Journal, Alerts, Evidence, Assistant, Settings, Administration.

Administration, multi-user functions, and advanced Assistant capabilities are future or not authorized until validated.

## 4. Secondary navigation

Secondary navigation may include filters, account scope, broker environment, portfolio segment, open/closed status, risk state, evidence status, and time period.

## 5. Global status areas

Global status should show environment, broker connection, data freshness, unresolved orders, critical alerts, system health, and emergency-stop access.

## 6. Page hierarchy

Home summarizes. Portfolio and Opportunities provide context. Trade Plans and Orders manage consequential workflows. Evidence and Journal support review. Settings controls configuration.

## 7. Object model

| Object | Purpose | Ownership | Status | Relationships | Required identifiers | Audit relevance | Availability |
|---|---|---|---|---|---|---|---|
| portfolio | User holdings and risk context | User/broker | current or calculated | account, position, risk policy | portfolio ID, timestamp | high | current |
| account | Broker account snapshot | broker | current/stale/unavailable | broker connection, portfolio | account ref, timestamp | high | current |
| broker connection | External broker link | broker adapter | connected/degraded/offline | account, order | broker ID, environment | high | current |
| instrument | Tradable security | market data | active/unavailable | opportunity, position | symbol, venue where known | medium | current |
| opportunity | Candidate for review | scanner/analytics | new/reviewed/rejected | instrument, recommendation | opportunity ID | medium | current |
| recommendation | Decision-support output | rules/analytics/AI | draft/explained/stale | opportunity, trade plan | recommendation ID, source | high | current/future |
| trade plan | Proposed action | EduTraderAI Engine | approved/rejected/drifted | risk assessment, approval | plan ID, correlation ID | high | current |
| risk assessment | Risk and policy result | risk service | pass/reject/warn | trade plan, portfolio | assessment ID | high | current |
| approval | Operator authorization | user | pending/granted/denied/expired | trade plan, order | approval ID, user ID future | high | current |
| order | Broker-facing request | broker | draft/submitted/acknowledged/final | approval, execution | order ID, broker ID | high | current |
| execution | Submission workflow | application service | pending/complete/failed | order, broker status | execution ID | high | current |
| position | Held instrument exposure | broker | open/closed/stale | portfolio, instrument | position ID or symbol | high | current |
| alert | User-visible event | system | new/acknowledged/resolved | object causing alert | alert ID | medium | future |
| journal entry | Decision note/review | user/system | draft/final | trade plan, position | entry ID | medium | future |
| evidence record | Auditable artifact | system | created/verified/missing | material action | hash, path, correlation ID | high | current |
| system event | Operational event | system | published/failed/null-delivered | service, evidence | event ID, correlation ID | medium | current/future |
| user preference | Personal setting | user | active/default | UI, alerts | preference key | low | future |
| risk policy | Configured guardrail | operator/admin | active/draft | risk assessment | policy ID, version | high | current/future |

## 8. Search and filtering

Search and filtering should preserve context, distinguish current from historical records, and avoid hiding unresolved critical states.

## 9. Context preservation

Users should retain symbol, plan, risk, broker, and evidence context when moving between pages.

## 10. Desktop structure

Desktop can support multi-panel review: summary, detail, risk, evidence, and action panels.

## 11. Mobile structure

Mobile should prioritize monitoring, alerts, review, acknowledgement, and carefully validated approval; it must not hide risk.

## 12. Role-based possibilities

Roles are future: viewer, operator, admin, reviewer, and support. Multi-user access requires identity, authorization, and audit design.

## 13. Current versus future scope

Current scope is private Paper-first operation. Future scope includes multi-user, mobile, Assistant expansion, and administration only after validation.

## 14. Navigation risks

Risks include burying broker state, overemphasizing opportunities, hiding evidence, confusing Paper/live modes, and mobile simplification.

## 15. Open decisions

Open decisions include final nav labels, mobile tab count, Assistant placement, Evidence prominence, Administration scope, and role model.
