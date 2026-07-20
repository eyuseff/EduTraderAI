# EduTraderAI Architecture

## Overview

EduTraderAI is organized as a collection of independent layers connected through explicit domain objects.

The architecture separates:

- market observations,
- trading decisions,
- position sizing,
- risk validation,
- order execution,
- portfolio accounting,
- historical simulation,
- analytics,
- and artificial intelligence.

## Primary Flow

```text
MarketFeed
    |
    v
Strategy
    |
    v
TradeIntent
    |
    v
PositionSizer
    |
    v
PositionSizingResult
    |
    v
OrderBuilder
    |
    v
TradeRequest
    |
    v
RiskManager
    |
    v
ExecutionPipeline
    |
    v
Order
    |
    v
Broker
    |
    v
Portfolio
    |
    v
Ledger