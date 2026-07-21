# EduTraderAI v4.0.0-rc1 Paper Validation Runbook

## Safety rules

- Use only Local Simulator or Alpaca Paper. Stop immediately if a broker does not
  report paper mode.
- Never place credentials in source, logs, screenshots, validation exports, or
  this repository.
- Do not run simultaneous application processes against the same paper account;
  supervisor locks and idempotency are process-local.
- Metrics and supervisor state reset on restart. Export before stopping and treat
  every restart as a new validation session.

## Before each session

1. Confirm the source is the intended `v4.0.0-rc1` tag and the worktree is clean.
2. Run `make verify`; require a zero exit status.
3. Start without Alpaca credentials in Local Simulator and confirm startup.
4. In development mode, open **Operational Validation** and confirm the RC,
   active paths, broker mode, null publisher, process-local supervisor state, and
   latest verification status.
5. Record the UTC start and initial counters in `VALIDATION_LOG.md`.

## Simulator workflow

1. On Paper Order, preview an approved trade and verify displayed quantity, risk,
   exposure, and reward/risk.
2. Submit once with `PAPER TRADE`; verify symbol and quantity against Orders &
   Positions. A repeated confirmation must not create an unintended second order.
3. Exercise a policy rejection and confirm no broker submission.
4. Exercise plan-drift rejection using controlled test fixtures, not by racing the
   user interface.
5. Run Automated Scanner preview-only, then a controlled confirmed paper
   submission. Repeat the same signal in the controlled suite and verify replay or
   duplicate protection.
6. Confirm a same-symbol request is admitted after the prior request finishes;
   unresolved busy state is an incident.

## Rollback exercises

1. Set both `USE_DETERMINISTIC_PREVIEW` and
   `USE_DETERMINISTIC_SUBMISSION` to `False`; restart and exercise one manual
   preview/submission. Never use a mixed setting—the startup validator must reject
   it.
2. Restore both manual flags to `True`.
3. Set `USE_DETERMINISTIC_SCANNER` to `False`; restart and exercise one legacy
   scanner preview/submission path.
4. Restore the scanner flag to `True` and verify diagnostics show the supervised
   path.

## Alpaca Paper smoke

1. Use operator-managed Alpaca Paper credentials in environment variables only.
2. Select Alpaca Paper and confirm the broker reports paper mode.
3. Perform one preview and one conservatively sized paper submission/cancellation
   lifecycle under the operator's approved test conditions.
4. Reconcile symbol, quantity, order ID, and status without copying the complete
   account identifier.
5. Remove credentials from the environment after the session.

If credentials are unavailable, verify that selecting Alpaca Paper fails closed
before execution and record the credentialed smoke as pending—not passed.

## Export and close

1. Open Operational Validation and select **Export sanitized validation
   snapshot**. The ignored local file is written under `build/validation/` only on
   operator request.
2. Review it for the version, timestamp, flags, health, metrics, verification
   metadata, and known limitations. Confirm it contains no secret or account data.
3. Reconcile counts with broker evidence, log the session, and record warnings
   separately from failures.
4. Stop the app cleanly. File incidents for every unexplained crash, quantity
   mismatch, drift submission, duplicate, correlation gap, lock leak, deadlock,
   broker failure, or instrumentation failure.
