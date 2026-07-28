# EduTraderAI

> **A deterministic, explainable trading research and execution platform.**

EduTraderAI is a professional-grade Python trading platform designed for disciplined strategy research, historical simulation, paper trading, and eventually carefully controlled live trading.

The project is being developed with one primary objective:

> **Build a trading platform that can be trusted—not because it promises profits, but because every decision is reproducible, explainable, and governed by deterministic risk controls.**

Artificial Intelligence is an enhancement to the platform—not its decision maker.


---

# EMERS Vision Documents

The v4.1 development line introduces EMERS as the working user-facing brand
architecture while EduTraderAI remains the technical engine. These documents are
working product and company-vision materials pending legal, trademark, domain,
and regulatory review:

- `docs/vision/EMERS_CONSTITUTION.md`
- `docs/vision/EMERS_PRODUCT_VISION.md`
- `docs/vision/EMERS_BRAND_ARCHITECTURE.md`
- `docs/vision/EMERS_PRODUCT_PRINCIPLES.md`
- `docs/vision/EMERS_FIVE_YEAR_VISION.md`

# Project Status

| Item | Status |
|------|--------|
| Version | **0.5.0** |
| Architecture | Stable |
| Python | 3.13 |
| Tests | **111 Passing** |
| Documentation | In Progress |
| Continuous Integration | Planned |
| Analytics Engine | Planned |
| Paper Trading | Planned |
| AI Explorer | Planned |
| Live Trading | Planned |

---

# Vision

EduTraderAI is designed as a personal trading operating system.

Its responsibilities include:

- Market data processing
- Strategy evaluation
- Position sizing
- Deterministic risk management
- Order construction
- Broker abstraction
- Portfolio accounting
- Historical backtesting
- Performance analytics
- AI-assisted research
- Explainable decision support

The platform intentionally separates these concerns into independent layers.

---

# Guiding Principles

The architecture follows several permanent principles.

- Capital preservation before profit.
- Deterministic execution.
- AI recommends; AI never executes.
- Every trade must be explainable.
- One responsibility per component.
- Immutable domain models whenever practical.
- Explicit state over hidden state.
- Every production feature includes automated tests.
- Simplicity over cleverness.
- Long-term maintainability over short-term speed.

These principles are documented in:

```
docs/
    MISSION.md
    PRINCIPLES.md
    CONSTITUTION.md
```

---

# Architecture

```
MarketFeed
      │
      ▼
 Strategy
      │
      ▼
 TradeIntent
      │
      ▼
 PositionSizer
      │
      ▼
 RiskManager
      │
      ▼
 ExecutionPipeline
      │
      ▼
 Broker
      │
      ▼
 Portfolio
      │
      ▼
 Ledger

 HistoricalFeed
        │
        ▼
 BacktestEngine
        │
        ▼
 BacktestResult
        │
        ▼
 Analytics
```

Each layer has a single, well-defined responsibility.

---

# Current Features

## Domain

- Immutable business models
- TradeIntent
- Orders
- Trade Requests
- Validation

## Market

- Bar
- Quote
- HistoricalFeed
- MarketFeed interface

## Strategy

- Strategy interface
- NoOpStrategy

## Position Sizing

- Deterministic sizing
- Risk-based sizing

## Risk

- Portfolio exposure limits
- Position limits
- Buying power validation
- Risk violations

## Execution

- ExecutionPipeline
- OrderBuilder
- PaperBroker

## Portfolio

- Cash management
- Position tracking
- Equity calculations
- Ledger integration

## Backtesting

- Historical simulation
- Trade counting
- Deterministic orchestration
- BacktestResult

---

# Design Philosophy

EduTraderAI deliberately avoids the "AI trading bot" approach.

Instead:

```
AI
 │
 ▼
Recommendation

 │
 ▼

Guardian

 │
 ▼

TradeIntent

 │
 ▼

Deterministic Execution
```

The execution pipeline remains fully deterministic regardless of how a recommendation was generated.

---

# Repository Structure

```
EduTraderAI/

docs/
    adr/
    ARCHITECTURE.md
    AI_CONTEXT.md
    CHANGELOG.md
    CONSTITUTION.md
    MISSION.md
    PRINCIPLES.md
    ROADMAP.md

tests/

volcanoes/

.github/
```

---

# Running the Test Suite

Compile everything:

```bash
python3 -m compileall volcanoes tests
```

Run a specific test:

```bash
python3 -m pytest tests/test_backtest_engine.py -v
```

Run the complete regression suite:

```bash
python3 -m pytest -v
```

---

# Development Workflow

Every sprint follows the same process.

```
Architecture Review

↓

Implementation

↓

Compile

↓

Targeted Tests

↓

Regression Suite

↓

Documentation

↓

Git Commit

↓

Version Tag
```

No feature is considered complete until the full regression suite passes.

---

# Roadmap

## Version 0.5

Engineering

- Documentation
- ADRs
- README
- CI
- Repository standards

---

## Version 0.6

Analytics

- PortfolioSnapshot
- Equity Curve
- Drawdown
- Performance metrics
- Performance reports

---

## Version 0.7

Strategy Library

- Buy & Hold
- SMA Crossover
- RSI Mean Reversion
- Donchian Breakout

---

## Version 0.8

Configuration & Logging

- Configuration system
- Structured logging
- Reproducibility metadata

---

## Version 0.9

Paper Trading

- Live market feed
- Session management
- Dashboard
- Daily reports

---

## Version 1.0

Deterministic Trading Platform

Definition of Done:

- Stable architecture
- Reliable backtesting
- Analytics
- Strategy library
- Documentation
- Continuous integration
- Strong automated test coverage
- Paper trading
- Reproducible execution

---

## Version 2.0

AI Explorer

- AI-assisted market research
- Recommendation engine
- Confidence estimation
- Prompt versioning
- Guardian integration

---

## Version 3.0

Controlled Live Trading

- Broker adapters
- Reconciliation
- Operational safety
- Emergency shutdown
- Audit logging

---

# Documentation

Project documentation is located in the `docs` directory.

- **MISSION.md** – Project purpose
- **PRINCIPLES.md** – Engineering principles
- **CONSTITUTION.md** – Permanent design rules
- **ARCHITECTURE.md** – Technical architecture
- **ROADMAP.md** – Planned milestones
- **AI_CONTEXT.md** – Current project status
- **ADR/** – Architecture Decision Records

---

# Contributing

See `CONTRIBUTING.md`.

Every contribution must:

- preserve deterministic behavior,
- include automated tests,
- maintain documentation,
- keep the regression suite green.

---

# License

This project is released under the MIT License unless stated otherwise.

---

# Acknowledgements

EduTraderAI is being developed as a long-term engineering project focused on reliability, explainability, and disciplined software architecture.

The objective is not to automate trading blindly, but to create a platform that helps its owner make better, safer, and more informed trading decisions.