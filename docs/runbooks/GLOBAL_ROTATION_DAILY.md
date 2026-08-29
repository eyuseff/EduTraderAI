# Global Rotation Daily Runbook

## Safety posture

Global Rotation is a read-only research screen. It does not submit orders and
does not connect to eToro Real. Every bundled security has unverified eToro
eligibility, so the starter universe returns zero quantities even when its
technical filters pass.

## Streamlit button

Start the existing application:

```bash
python3 -m streamlit run app.py
```

Select `Global Rotation Paper`, leave qualification phase enabled, and press
`Run Global Rotation Paper`. The page shows the data-load count, scanner funnel,
candidate table, data-quality quarantine, and a downloadable audit JSON.

The bundled starter contains 64 stocks across six regions and requests 75 daily
series after benchmarks and FX are included. It is intentionally not described
as an 8,000-stock production universe.

## Headless CLI

The CLI requires an explicit Paper portfolio snapshot so equity, exposure, and
loss values are never invented. Create a local JSON file with all fields:

```json
{
  "equity_usd": "REQUIRED",
  "buying_power_usd": "REQUIRED",
  "current_exposure_usd": "REQUIRED",
  "realized_loss_today_usd": "REQUIRED",
  "open_symbols": [],
  "qualification_phase": true
}
```

Run:

```bash
python3 scripts/run_global_rotation_daily.py \
  --portfolio-json /absolute/path/to/paper-portfolio.json
```

The command writes a run-specific directory under `build/global_rotation/`
containing:

- `summary.json` — run identity, market dates, funnel, candidates, and an
  explicit zero-order execution record;
- `candidates.csv` — scores, risk/target fields, category, blockers, and first
  invalidation;
- `data_quality.csv` — missing, invalid, or stale market series.

## Scale boundary

The Yahoo reader is capped at 500 symbols because it is a research convenience,
not an institutional feed. The target ~8,000-name universe requires a reviewed
security-master and market-data provider with exchange calendars, corporate
actions, delistings, survivorship controls, retries, rate limits, and licensing.
Do not raise the cap and call the result production-ready.

## eToro gate

Only authenticated Demo + Read evidence may set account eligibility,
fractional support, and BUY x1 underlying capability. Until the existing 401
authentication issue is resolved, those fields remain unverified and sizing
stays at zero. Never infer eligibility from a public symbol page alone.
