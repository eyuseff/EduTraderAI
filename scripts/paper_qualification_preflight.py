"""Offline, fail-closed preflight for the v4.1 connected Paper qualification.

This module intentionally has no broker adapter, credential, persistence, or
network dependency. It produces deterministic evidence for the one-share,
non-marketable LIMIT intent that may later be used by a separately authorized
connected Paper qualification step.
"""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from typing import Any

from volcanoes.application.qualification.integration.order_safety import (
    build_non_marketable_buy_limit_plan,
)


def _decimal(value: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError("value must be a decimal") from exc
    if not parsed.is_finite():
        raise argparse.ArgumentTypeError("value must be finite")
    return parsed


def build_preflight_evidence(
    *,
    symbol: str,
    reference_best_ask: Decimal,
    tick_size: Decimal = Decimal("0.01"),
) -> dict[str, Any]:
    """Return deterministic, non-sensitive evidence without external effects."""

    plan = build_non_marketable_buy_limit_plan(
        symbol=symbol,
        reference_best_ask=reference_best_ask,
        tick_size=tick_size,
    )
    intent = plan.order_intent
    return {
        "schema_version": "paper-qualification-preflight-v1",
        "preflight_passed": True,
        "environment": "PAPER",
        "action_executed": False,
        "broker_accessed": False,
        "credentials_loaded": False,
        "network_used": False,
        "persistence_accessed": False,
        "runtime_changed": False,
        "order_intent": {
            "symbol": intent.symbol,
            "quantity": intent.quantity,
            "order_type": intent.order_type.value,
            "time_in_force": intent.time_in_force.value,
            "limit_price": str(intent.limit_price),
        },
        "reference_best_ask": str(plan.reference_best_ask),
        "tick_size": str(plan.tick_size),
        "non_marketable": intent.limit_price < plan.reference_best_ask,
        "rationale": plan.rationale,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build offline evidence for the v4.1 Paper qualification preflight."
    )
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--reference-best-ask", required=True, type=_decimal)
    parser.add_argument("--tick-size", default=Decimal("0.01"), type=_decimal)
    args = parser.parse_args(argv)

    evidence = build_preflight_evidence(
        symbol=args.symbol,
        reference_best_ask=args.reference_best_ask,
        tick_size=args.tick_size,
    )
    print(json.dumps(evidence, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
