# EduTrader AI v3.1 — Paper-Trading Foundation

This release is intentionally locked to **paper trading**. It includes a local
simulator and an optional Alpaca Paper adapter. There is no live-broker adapter.

## 1. Install

```bash
cd /Users/EYUSEFF/Documents/GitHub/EduTraderAI_v1
python3 -m pip install -r requirements.txt
```

## 2. Run the local simulator

```bash
python3 -m streamlit run app.py
```

Choose **Local Simulator** in the sidebar. It needs no account or credentials.

## 3. Optional: connect Alpaca Paper

Create paper API credentials in your Alpaca paper account. In the same Terminal
window used to launch Streamlit, export them:

```bash
export ALPACA_API_KEY="YOUR_PAPER_KEY"
export ALPACA_SECRET_KEY="YOUR_PAPER_SECRET"
python3 -m streamlit run app.py
```

Do not paste credentials into Python files, GitHub, screenshots, or chat.

## 4. Test

```bash
python3 -m pytest -q
```

## 5. Git

```bash
git add app.py app_legacy.py broker trading tests requirements.txt .env.example .gitignore PAPER_TRADING_SETUP.md
git commit -m "Add paper trading foundation and risk controls"
git push
```

## Built-in limits

- 0.25% account risk per trade
- 1% daily-loss lock
- 5 maximum positions
- 50% maximum total exposure
- 12% maximum single position
- minimum 2:1 reward/risk
- stocks priced at least $10
- long-only
- duplicate position/order protection
- exact manual confirmation before each paper order
