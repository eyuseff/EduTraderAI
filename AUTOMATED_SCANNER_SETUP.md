# EduTrader AI v3.2 — Automated Scanner

This release is locked to paper brokers. The automated page scans a controlled liquid-stock universe, evaluates the market regime, ranks trend/momentum candidates, passes every proposal through the existing risk manager, and can submit paper bracket orders only after an explicit UI confirmation.

## Run

```bash
python3 -m pip install -r requirements.txt
python3 -m streamlit run app.py
```

## Safety defaults

- Paper brokers only
- Long only
- Maximum 3 new paper orders per cycle
- Maximum 5 open positions
- 0.25% account risk per trade
- 1% daily loss lock
- 50% maximum total exposure
- Minimum 2:1 reward/risk
- Market-regime gate
- Liquidity and price filters
- Audit log at `logs/automation_audit.jsonl`

Run in preview mode first. Paper execution is still a simulation and does not establish that a strategy is profitable.
