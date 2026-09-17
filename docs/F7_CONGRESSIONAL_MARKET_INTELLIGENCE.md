# F7 — Congressional Market Intelligence

F7 adds public congressional securities disclosures as an optional research
enrichment for the Global Rotation Paper scanner.

## Operating boundary

F7 is **research-only**. It may change the presentation priority of candidates
that already exist, but it does not:

- create a candidate that failed EduTrader or Volcanes;
- approve an instrument rejected by Guardian;
- change position sizing, stops, targets, or exposure limits;
- submit, replace, or cancel an order;
- change the underlying Global Rotation `run_id` or result fingerprints.

The daily summary records `changes_execution_eligibility=false` and
`can_bypass_guardian=false` whenever F7 is enabled.

## Sources and provenance

The adapter is provider-neutral. A normalized snapshot may record
`capitoltrades` as its source/provenance, while official House/Senate disclosure
records can also be normalized into the same schema. The scanner deliberately
contains no HTML scraping logic and makes no live request to Capitol Trades.

This keeps the scoring core deterministic and lets the operator retain an
immutable input file whose SHA-256 is written into the daily summary.

## Look-ahead protection

`traded_on` and `published_on` are separate fields. A transaction is eligible
for F7 only when:

```text
published_on <= regional market as_of
```

The scorer therefore never uses a transaction merely because it happened in
the past if the disclosure was not yet public at the evaluation date.

## F7 factors in the first implementation

| Factor | Status | Behavior |
| --- | --- | --- |
| F7.1 Congressional purchase | Active | Positive research evidence |
| F7.2 Congressional sale | Active | Negative research evidence |
| F7.3 Disclosure recency | Active | Fresher public disclosures receive more weight |
| F7.4 Disclosure lag | Active | Longer trade-to-publication lag receives less weight |
| F7.5 Independent consensus | Active | Multiple independent disclosers strengthen the signal |
| F7.6 Reported transaction size | Active | Uses the disclosed amount range, not a fabricated exact value |
| F7.7 Repeat activity | Active | Repeated same-side activity adds evidence |
| F7.8 Committee/sector context | Captured | Committee names are retained as metadata; no subjective motive inference is scored |
| F7.9 Price distance from disclosure | Reserved | Requires deterministic historical price-at-publication enrichment |
| F7.10 Post-disclosure momentum | Reserved | Requires deterministic historical market-data enrichment |

The F7 signal is expressed as a direction (`bullish`, `bearish`, `mixed`,
`neutral`, or `unavailable`), a 0–100 evidence-strength score, and a bounded
research-priority adjustment from -15 to +15.

## Normalized JSON schema

```json
{
  "schema_version": 1,
  "source": "capitoltrades",
  "as_of": "2026-09-16",
  "trades": [
    {
      "symbol": "AAA",
      "politician": "Example Discloser",
      "transaction_type": "purchase",
      "traded_on": "2026-09-12",
      "published_on": "2026-09-14",
      "amount_low_usd": "50000",
      "amount_high_usd": "100000",
      "owner": "self",
      "chamber": "house",
      "committees": ["Example Committee"],
      "source_url": "https://example.invalid/disclosure",
      "disclosure_id": "example-001"
    }
  ]
}
```

Supported normalized transaction aliases include `purchase`/`buy` and
`sale`/`sell`; full and partial sales normalize to the same sale side.

## Daily operator usage

```bash
python scripts/run_global_rotation_daily.py \
  --portfolio-json /path/to/paper-portfolio.json \
  --congressional-json /path/to/congressional-snapshot.json
```

When `--congressional-json` is omitted, the legacy daily output remains
unchanged. When supplied, `candidates.csv` and `summary.json` gain F7 fields,
including:

- `research_priority_score`;
- `f7_score` and `f7_direction`;
- `f7_priority_adjustment`;
- purchase/sale counts;
- freshest public-disclosure age;
- median disclosure lag;
- source names and explainable reasons.

The `research_priority_score` is presentation-only. It is the existing
EduTrader/Volcanes score average plus the bounded F7 adjustment and is never
used as an execution authorization.
