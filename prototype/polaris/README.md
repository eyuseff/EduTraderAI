# Polaris Phase 1 Prototype

## Purpose

Polaris Phase 1 is the first visible and clickable EMERS Trade product prototype. It translates Project Horizon into a static review artifact covering Home Dashboard, Opportunity Detail, Trade Plan, Risk Review, Paper Approval, Broker Submission and Status, Order Detail, and Position Detail.

## Scope

This is an isolated prototype. It is not production software and is not connected to EduTraderAI Engine, Alpaca, any broker, real market data, production configuration, credentials, customer information, authentication, cloud infrastructure, databases, notification services, or live trading.

## How to open

Open `prototype/polaris/index.html` directly in a browser. No package manager, build step, local server, or dependency installation is required.

## Simulated data statement

All symbols, prices, portfolio values, order identifiers, broker messages, timestamps, audit events, and evidence identifiers are simulated.

## Controls

- Review AAPL from the Home dashboard.
- Create Trade Plan.
- Edit quantity, entry, stop, or target to recalculate risk values.
- Complete all risk acknowledgements to unlock Paper approval.
- Use `AUTHORIZE PAPER ORDER` to start a simulated order lifecycle.
- Use prototype controls to simulate partial fill, full fill, rejection, cancellation, unknown state, reconciliation, degraded mode, and emergency stop.

## Supported flows

Home Dashboard -> Opportunity Detail -> Trade Plan -> Risk Review -> Paper Approval -> Broker Status -> Order Detail -> Position Detail after full fill.

## Accessibility notes

The prototype uses semantic HTML, keyboard-accessible buttons and inputs, visible focus, labels, text-supported status indicators, reduced-motion support, and responsive stacking. It does not claim formal accessibility compliance.

## Reset behavior

Audit events and simulated order state are held in browser memory. Refreshing the browser resets the prototype.

## Review process

Reviewers should use the Polaris checklist and confirm risk visibility, Paper-mode clarity, approval gating, broker-state truth, degraded behavior, emergency stop behavior, and absence of pressure-to-trade patterns.

## Production isolation confirmation

The prototype contains no external calls, credentials, broker connections, package dependencies, production imports, or real market/customer data.
