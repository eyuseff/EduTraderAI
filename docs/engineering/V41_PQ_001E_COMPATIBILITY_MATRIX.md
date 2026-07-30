# V41-PQ-001E Compatibility Matrix

## Scope

This matrix compares the current Paper runtime with the V41-PQ-001
qualification subsystem and the proposed integration layer. It is source-grounded
from the current repository and does not authorize runtime integration.

Compatibility statuses:

- `DIRECT`: compatible with minimal translation.
- `ADAPTER_REQUIRED`: compatible through an explicit adapter.
- `SEMANTIC_CONFLICT`: meaning differs and requires design resolution.
- `MISSING_CURRENT_CAPABILITY`: current runtime lacks the needed capability.
- `DEFERRED`: intentionally deferred to V41-PQ-002 or later.
- `NOT_APPLICABLE`: no mapping required.

## Matrix

| Concern | Existing representation | Qualification representation | Compatibility | Translation required | Loss risk | Temporary owner | Target owner | Implementation phase | Notes |
|---|---|---|---|---|---|---|---|---|---|
| Order intent | `TradeProposal`; scanner `StrategySignal` | `QualificationApplicationCommand` plus scenario metadata | ADAPTER_REQUIRED | Build command payload and scenario/run identity | Medium | Existing Paper runtime | Paper Qualification Facade | F1/F2 | Do not duplicate planner logic |
| Symbol | String, normalized in adapters | Payload fingerprint/object reference facts | DIRECT | Uppercase normalized symbol | Low | Existing runtime | Facade | F1 | Preserve display symbol separately if needed |
| Quantity | Planned quantity from `TradePlanner`; qualification scenario may require one share | Scenario expectation and broker observation facts | SEMANTIC_CONFLICT | Explicit scenario quantity contract | High | Existing planner | Qualification scenario plus planner compatibility | F1/F4 | Qualification one-share smoke must not bypass risk policy |
| Order type | Root broker `submit_bracket_order`; simulated `bracket-limit-simulation` | Scenario order intent summary and observation | ADAPTER_REQUIRED | Normalize broker order type | Medium | Broker adapter | Observation normalizer | F4 | No raw payload in evidence |
| Limit price | `entry_price` | Scenario/order fact | DIRECT | Decimal/string canonicalization | Low | Existing runtime | Facade | F1 | Must remain deterministic |
| Stop/target | `stop_price`, `target_price` | Scenario/order facts | DIRECT | Decimal/string canonicalization | Low | Existing runtime | Facade | F1 | Required for bracket order |
| Time in force | Alpaca adapter uses day order; simulator does not model full TIF | Scenario criteria | ADAPTER_REQUIRED | Add normalized TIF fact where available | Medium | Broker adapter | Observation normalizer | F4 | Simulator/Paper parity risk |
| Environment | `Local Simulator` or `Alpaca Paper`; `broker.is_paper` | Guard `PAPER_ENVIRONMENT`; environment string | DIRECT | Runtime guard facts | Low | Runtime config | Facade plus service guards | F1/F2 | Live must be refused |
| Approval state | `RiskDecision.approved`; confirmation phrase | `OPERATOR_APPROVED` event and guards | ADAPTER_REQUIRED | Translate operator confirmation into qualification command | Medium | `app.py` | Qualification service | F2/F3 | UI remains presentation owner |
| Command ID | Not first-class in current manual path | `CommandId` | ADAPTER_REQUIRED | Generate/preserve per command | Medium | Facade | Facade supplies; service records | F1 | Must be deterministic enough for replay |
| Correlation ID | `new_correlation_id()` in current runtime | `CorrelationId` | DIRECT | Preserve existing ID | Low | Runtime | Shared explicit contract | F1 | Align operational events/evidence |
| Idempotency key | Process-local manual and scanner protections | `IdempotencyKey` via repository port | ADAPTER_REQUIRED | Define key per qualification command | High | Existing runtime | Qualification repository | F1/F2 | Restart safety deferred |
| Run ID | None in current Paper runtime | `QualificationRunId` | ADAPTER_REQUIRED | Create per qualification run | Medium | Facade | Qualification repository | F1/F2 | Must be operator visible |
| Scenario ID | None in current Paper runtime | `QualificationScenarioId` | ADAPTER_REQUIRED | Select approved scenario | Medium | Facade | Qualification scenario catalog | F1/F2 | Per-scenario enablement recommended |
| Order ID | `BrokerOrder.order_id` | Safe object reference / broker observation | ADAPTER_REQUIRED | Normalize as safe reference | Medium | Broker adapter | Observation normalizer | F4 | Not proof of final success |
| Broker request ID | Not separately exposed | Safe object reference if available | MISSING_CURRENT_CAPABILITY | Add adapter support if broker exposes it | High | Broker adapter | Observation normalizer | F4/F6 | Alpaca client order ID currently not exposed by root protocol |
| Order status | `BrokerOrder.status` | Broker observation event type and guards | ADAPTER_REQUIRED | Map status to qualification event | High | Broker adapter | Observation normalizer | F4 | Stale/out-of-order risks |
| Cancellation status | Bulk cancel count | `BROKER_CANCELLATION_CONFIRMED` | MISSING_CURRENT_CAPABILITY | Need targeted cancellation proof | High | Existing broker | Future observation adapter | F5/F6 | Bulk count cannot prove one run safely |
| Fill status | Status may be `filled`; no fill history | Fill/partial-fill event types | MISSING_CURRENT_CAPABILITY | Need fill observation facts | High | Broker adapter | Observation normalizer | F5/F6 | Partial fill is unresolved |
| Position status | `get_positions`; `BrokerPortfolioView` | Guard/fact for no-position or position exists | ADAPTER_REQUIRED | Normalize read-only position evidence | Medium | Broker | Observation normalizer | F4/F6 | Reads are not durable evidence alone |
| Error model | Exceptions and `SubmitTradeResult` codes | Safe application result/errors | ADAPTER_REQUIRED | Safe error translation table | Medium | Runtime adapters | Facade | F2/F4 | Uncertainty must not become success |
| Retry policy | Process-local duplicate guards; no qualification retries | `RetryClassification` | SEMANTIC_CONFLICT | Map retry to command/event semantics | High | Runtime | Qualification service plus executor | F4/F6 | Blind retry prohibited |
| Timeout policy | No targeted qualification timeout found | `TIMEOUT_DETECTED`; unresolved states | MISSING_CURRENT_CAPABILITY | Add explicit timeout policy later | High | None | Reconciliation adapter | F6 | Do not invent working timeout |
| Evidence model | Operational exports, events, JSONL audit | Canonical qualification evidence | ADAPTER_REQUIRED | Record through `QualificationEvidenceRecorder` | Medium | Existing observability | Qualification evidence recorder | F7 | Qualification evidence authoritative |
| Event model | `volcanoes.events` operational events | Qualification evidence intents | ADAPTER_REQUIRED | Correlate but do not merge authority | Medium | Existing app services | Shared explicit contract | F7 | Null publisher not durable |
| Emergency stop | Bulk UI controls; qualification guard exists | `Guard.EMERGENCY_STOP_INACTIVE` | SEMANTIC_CONFLICT | Define runtime source of guard fact | High | Runtime | Facade/executor guard source | F2/F4 | Central source unresolved |
| Reconciliation | Manual validation docs; no runtime targeted service | Reconciliation state/events | MISSING_CURRENT_CAPABILITY | Build observation/reconciliation adapter | High | None | Future reconciliation adapter | F6 | Blocking before consequential rollout |
| Terminal outcome | `SubmitTradeResult`; broker status; UI message | `QualificationResult` independent of workflow state | ADAPTER_REQUIRED | Map terminal qualification result only after criteria evidence | High | Runtime | Qualification service | F7/F8 | Broker ACK alone is not passed |
| User-visible response | Streamlit success/error | Safe qualification result/message | ADAPTER_REQUIRED | Presentation mapping | Medium | `app.py` | Runtime presentation adapter | F3/F8 | Preserve current UI until enabled |

## Legacy logic classification

| Component | Classification | Rationale | Removal or retention condition | Phase | Rollback impact |
|---|---|---|---|---|---|
| `app.py` Paper Order page | WRAP | Current presentation entry point remains valid | Retain; call facade only under flag | F3 | Disable flag returns to existing path before broker effect |
| `preview_paper_order` | RETAIN | Deterministic preview remains correct trading planner path | Retain permanently unless future UI changes | F3 | Existing preview path remains stable |
| `submit_paper_order` | WRAP | Current deterministic submission remains execution-capable | Wrap through side-effect executor for qualification | F4 | Must not fallback after uncertain new-path send |
| `build_paper_order_planner` | RETAIN | Single planner config source | Retain | F1+ | Prevents planning drift |
| `PaperBrokerExecutionAdapter` | WRAP | Correct broker-effect translator but not qualification-aware | Use only inside side-effect executor | F4 | Executor can be disabled |
| `PaperBroker.cancel_all_orders` | DO_NOT_TOUCH | Bulk emergency control, not targeted qualification cancellation | Retain outside qualification until targeted path exists | F6 | Bulk fallback requires operator awareness |
| `PaperExecutionEngine.submit` | REMOVE_LATER | Legacy rollback path | Remove only after qualification parity and rollback retirement | F8+ | Current rollback remains available |
| `ExecutionSupervisor` scanner path | DO_NOT_TOUCH | Existing supervised scanner behavior is outside first manual qualification slice | Revisit after manual qualification acceptance | Later | Avoids widening blast radius |
| Operational events/metrics | RETAIN | Observability remains useful | Retain; add qualification metrics later | F7 | Not authoritative for qualification |
| Qualification scenario harness | RETAIN | Executable spec for behavior | Use for parity/acceptance tests | F1+ | No runtime rollback concern |
| In-memory qualification repository | SHADOW | Useful for tests and no-effect shadow mode | Do not use for durable production claims | F2/F3 | Safe to disable |

## Semantic conflicts requiring risk-register coverage

- Qualification quantity semantics versus current planner-produced quantity.
- Bulk cancellation versus targeted qualification cancellation.
- Process-local idempotency versus restart-safe qualification requirements.
- Operational event publication versus canonical qualification evidence.
- Current emergency controls versus ADR guard source of truth.
- Broker acknowledgment versus qualification pass criteria.
