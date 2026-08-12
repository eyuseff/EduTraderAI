# EduTraderAI Paper-Operation Incident

Copy this template for every crash, incorrect decision, unexpected broker
response, suspected duplicate, lock leak, correlation loss, or instrumentation
gap. Never paste credentials, complete account identifiers, or raw secret-bearing
broker responses.

## Identification

- Incident ID:
- UTC detected at:
- Operator:
- RC commit/tag:
- Broker mode: Simulator / Alpaca Paper
- Workflow: Manual / Scanner / Rollback
- Sanitized correlation ID (if available):
- Severity: Observation warning / Stable blocker

## Expected and observed behavior

- Expected:
- Observed:
- Was a broker order submitted? Yes / No / Unknown
- Expected deterministic quantity:
- Broker-submitted quantity:
- Relevant fixed-cardinality metric changes:

## Safety response

- Paper orders cancelled or positions closed:
- Scanner stopped:
- Rollback activated:
- Application restarted:
- Evidence preserved (sanitized paths only):

## Analysis and disposition

- Reproduction:
- Root cause:
- Trading outcome affected? Yes / No
- Instrumentation outcome affected? Yes / No
- Corrective action:
- Tests added or verification run:
- Resolved by/date:
- Stable-release disposition:
