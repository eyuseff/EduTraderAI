# Polaris Phase 1 Interaction Map

## Primary journey

Home Dashboard -> AAPL Review -> Opportunity Detail -> Create Trade Plan -> Trade Plan Builder -> Review Risk -> Risk Review -> Continue to Paper Approval -> Paper Approval -> AUTHORIZE PAPER ORDER -> Submission and Broker Status -> View Order -> Order Detail -> Simulate Full Fill -> View Position -> Position Detail.

## Trade-plan editing

Quantity, entry, stop, and target update capital required, maximum planned loss, potential gain, reward-to-risk ratio, portfolio exposure after trade, and remaining risk budget. No external action occurs.

## Acknowledgement gating

Paper Approval remains unavailable until all four risk acknowledgements are selected: maximum planned loss, stop limitation, portfolio impact, and uncertainty.

## Simulated broker lifecycle

Authorization records approval, then simulates submission pending, submitted, and acknowledged. The prototype does not automatically show filled.

## Prototype order controls

- Partial fill: updates filled and remaining quantity, average simulated fill, and evidence.
- Full fill: reconciles final state and creates a simulated position.
- Cancellation: first moves to cancellation requested, then requires separate simulated broker cancellation confirmation.
- Rejection: records rejected state and plain-language reason.
- Unknown state: records unresolved state and blocks assumption of completion.
- Reconciliation: marks reconciliation required without inventing final broker state.

## Degraded mode

The global `SIMULATE DEGRADED MODE` control changes data status to delayed, broker status to unavailable, and disables consequential submission/cancellation/fill controls.

## Emergency stop

Emergency Stop opens a confirmation. Activation blocks new authorizations and simulated submission controls while leaving existing states visible.

## Evidence drawer

The Evidence drawer is available globally and shows in-memory audit events for material prototype actions.
