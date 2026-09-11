# Advanced indicators, scoring & news (research layer)

Feature branch: `feature/advanced-indicators-news-research`

## What this adds

- `volcanoes/market/advanced_indicators.py` — Bollinger, ADX, Stochastic, MFI, OBV, Supertrend
- `volcanoes/market/advanced_scoring.py` — hybrid score (−18…+25) + soft block
- `volcanoes/market/global_rotation_advanced_integration.py` — wire into Global Rotation candidates
- `volcanoes/market/news_provider.py` — Finnhub + offline mock
- `volcanoes/market/news_scoring.py` / `news_integration.py` — news score (−5…+5)

**Research / advisory only.** No broker connections, no order submission, quantity remains 0.

## Quick start

```bash
# from repo root
PYTHONPATH=. python3 demo_news_integration.py
PYTHONPATH=. python3 -m pytest tests/test_advanced_indicators.py tests/test_advanced_scoring.py tests/test_global_rotation_advanced_integration.py tests/test_news_provider.py -q
```

Optional live news:

```bash
export FINNHUB_API_KEY=your_key
export NEWS_PROVIDER=finnhub
```

## Safety

- Fail-closed when API key missing or network fails
- Soft block (ADX < 15) only demotes category to `esperar`
- Does not enable Live, Alpaca, or eToro
