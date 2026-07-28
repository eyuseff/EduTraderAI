# EMERS Technology Blueprint

## 1. Purpose

This blueprint describes a logical future technology direction for EMERS Trade. It is not an implementation decision.

## 2. Technology principles

Preserve validated behavior, extract services only when justified, avoid premature microservices, begin with a modular monolith where practical, maintain deterministic tests, separate broker state from assumptions, use explicit contracts, require idempotency, use durable state before multi-process or cloud deployment, preserve local development and Paper qualification, avoid fashion-driven architecture, and require measurable benefit before complexity.

## 3. Current-state architecture

Current state is a local Streamlit-oriented application using deterministic EduTraderAI services, adapters, Paper-first broker paths, process-local coordination, and local evidence artifacts.

## 4. Transitional architecture

Transition should clarify service boundaries, strengthen qualification workflows, add durable coordination where justified, and preserve the current single-process Paper workflow.

## 5. Target logical architecture

Conceptual target model:

```text
EMERS Web and Mobile Clients
            |
      EMERS API Gateway
            |
------------------------------------------------
| Identity and Access Service                  |
| Portfolio Service                            |
| Decision Intelligence Service                |
| Risk Policy Service                          |
| Approval Workflow Service                    |
| Order Management Service                     |
| Broker Integration Service                   |
| Market Data Service                          |
| Notification Service                         |
| Audit and Evidence Service                   |
------------------------------------------------
            |
      EduTraderAI Engine
            |
 Supported Broker and Data APIs
```

This is a logical model, not a microservice mandate or vendor decision.

## 6. Application services

Application services should remain presentation-neutral, deterministic where possible, explicit about side effects, and testable with fake adapters.

## 7. Frontend strategy

Frontend evolution may move from Streamlit toward secure web and mobile clients, but only after API, identity, session, and authorization models are designed.

## 8. API strategy

APIs should expose explicit contracts for preview, approval, submission, qualification, portfolio state, broker state, evidence, and diagnostics.

## 9. Background processing

Background work requires idempotency, durable state, retry limits, cancellation, reconciliation, and visible failure status before cloud or multi-process use.

## 10. Event architecture

Events should be structured, identifiable, auditable, and separated from UI logging. Durable publication remains a future decision.

## 11. State management

Material state must distinguish portfolio snapshots, broker truth, user approvals, command intent, event attempts, and final outcomes.

## 12. Storage strategy

Storage should begin with clear schemas and evidence needs. Durable storage is required before multi-user, multi-process, or recovery-dependent operation.

## 13. Deployment evolution

Stage 1: validated local application. Stage 2: modular local application with clearer boundaries. Stage 3: secure single-user web deployment. Stage 4: durable background processing and event infrastructure. Stage 5: controlled multi-user platform. Stage 6: supported mobile applications and multi-broker services. Each stage requires separate approval and validation.

## 14. Observability

Observability should report health, broker mode, execution path, event publisher type, coordination mode, evidence status, errors, and degraded operation.

## 15. Resilience

Resilience requires safe failure, clear retries, duplicate prevention, cancellation, state reconciliation, credential revocation handling, and operator-visible recovery steps.

## 16. Scalability

Scalability should not be pursued before safety and correctness. Multi-user or multi-worker scaling requires durable coordination and authorization.

## 17. Testing strategy

Testing must include unit, integration, architecture, security, redaction, broker fake, failure injection, evidence validation, and release-gate tests.

## 18. Release architecture

Releases should include verification, evidence, manifest integrity, operational readiness, rollback clarity, and human approval.

## 19. Technology decision criteria

Technology choices should be judged by safety, simplicity, testability, operational visibility, security, reversibility, maintainability, cost, and compatibility.

## 20. Open architecture questions

Open questions include API framework, identity provider, datastore, event infrastructure, deployment target, mobile architecture, broker event ingestion, and evidence retention model.
