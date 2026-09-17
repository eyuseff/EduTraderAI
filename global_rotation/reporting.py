"""Serializable presentation helpers for Global Rotation daily runs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from global_rotation.congressional import CongressionalSignal
from global_rotation.daily import DailyGlobalRotationRun


def _f7_fields(signal: CongressionalSignal | None) -> dict[str, Any]:
    if signal is None:
        return {
            "f7_available": False,
            "f7_score": None,
            "f7_direction": "unavailable",
            "f7_priority_adjustment": 0,
            "f7_trade_count": 0,
            "f7_purchase_count": 0,
            "f7_sale_count": 0,
            "f7_latest_publication_age_days": None,
            "f7_median_disclosure_lag_days": None,
            "f7_sources": "",
            "f7_reasons": "",
        }
    return {
        "f7_available": signal.available,
        "f7_score": signal.score if signal.available else None,
        "f7_direction": signal.direction,
        "f7_priority_adjustment": signal.priority_adjustment,
        "f7_trade_count": signal.trade_count,
        "f7_purchase_count": signal.purchase_count,
        "f7_sale_count": signal.sale_count,
        "f7_latest_publication_age_days": signal.freshest_publication_age_days,
        "f7_median_disclosure_lag_days": signal.median_disclosure_lag_days,
        "f7_sources": " | ".join(signal.source_names),
        "f7_reasons": " | ".join(signal.reasons),
    }


def candidate_rows(
    run: DailyGlobalRotationRun,
    congressional_signals: Mapping[str, CongressionalSignal] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in run.result.candidates:
        first_invalidation = (
            candidate.blockers[0]
            if candidate.blockers
            else f"Close below stop {candidate.stop_local} {candidate.currency}."
        )
        row: dict[str, Any] = {
            "symbol": candidate.symbol,
            "region": candidate.region,
            "edu_score": candidate.edu_score,
            "volcano_score": candidate.volcano_score,
            "guardian_approved": candidate.guardian_approved,
            "entry_local": str(candidate.entry_local),
            "entry_usd": str(candidate.entry_usd),
            "rsi14": str(candidate.rsi14),
            "atr14_local": str(candidate.atr14_local),
            "gap_pct": str(candidate.gap_pct),
            "daily_change_pct": str(candidate.daily_change_pct),
            "relative_volume": str(candidate.relative_volume),
            "stop_local": str(candidate.stop_local),
            "stop_pct": str(candidate.stop_pct),
            "target_local": str(candidate.target_local),
            "target_pct": str(candidate.target_pct),
            "resistance_local": str(candidate.resistance_local),
            "reward_risk_to_resistance": str(candidate.reward_risk_to_resistance),
            "quantity": str(candidate.quantity),
            "reserved_position_value_usd": str(candidate.reserved_position_value_usd),
            "position_value_usd": str(candidate.position_value_usd),
            "planned_loss_usd": str(candidate.planned_loss_usd),
            "target_profit_usd": str(candidate.target_profit_usd),
            "category": candidate.category,
            "blockers": " | ".join(candidate.blockers),
            "first_invalidation": first_invalidation,
        }
        if congressional_signals is not None:
            signal = congressional_signals.get(candidate.symbol.upper())
            f7_fields = _f7_fields(signal)
            row["research_priority_score"] = max(
                0,
                min(
                    100,
                    round((candidate.edu_score + candidate.volcano_score) / 2)
                    + int(f7_fields["f7_priority_adjustment"]),
                ),
            )
            row.update(f7_fields)
        rows.append(row)
    if congressional_signals is not None:
        rows.sort(
            key=lambda row: (
                int(row["research_priority_score"]),
                int(row["edu_score"]),
                int(row["volcano_score"]),
                str(row["symbol"]),
            ),
            reverse=True,
        )
    return rows


def data_issue_rows(run: DailyGlobalRotationRun) -> list[dict[str, str]]:
    return [
        {"symbol": item.symbol, "code": item.code, "message": item.message}
        for item in run.data_issues
    ]


def run_payload(
    run: DailyGlobalRotationRun,
    congressional_signals: Mapping[str, CongressionalSignal] | None = None,
    congressional_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    categories: dict[str, int] = {}
    for candidate in run.result.candidates:
        categories[candidate.category] = categories.get(candidate.category, 0) + 1
    payload: dict[str, Any] = {
        "run_id": run.run_id,
        "evidence_fingerprints": {
            "operator_schema": run.operator_schema,
            "universe_sha256": run.universe_sha256,
            "portfolio_sha256": run.portfolio_sha256,
            "market_data_sha256": run.market_data_sha256,
            "data_quality_sha256": run.data_quality_sha256,
            "result_sha256": run.result_sha256,
            "risk_policy_sha256": run.risk_policy_sha256,
            "rotation_policy_sha256": run.rotation_policy_sha256,
        },
        "universe": {
            "id": run.universe_id,
            "version": run.universe_version,
            "active_stocks": run.universe_size,
        },
        "market_data": {
            "histories_requested": run.histories_requested,
            "histories_loaded": run.histories_loaded,
            "as_of_by_region": {
                key: value.isoformat() for key, value in run.as_of_by_region.items()
            },
            "fx_as_of_by_region": {
                key: value.isoformat() for key, value in run.fx_as_of_by_region.items()
            },
            "quality_issue_count": len(run.data_issues),
        },
        "scan": {
            "scanned": run.result.scanned,
            "valid": run.result.valid,
            "candidate_count": len(run.result.candidates),
            "categories": categories,
        },
        "candidates": candidate_rows(run),
        "data_issues": data_issue_rows(run),
        "execution": {
            "mode": "RESEARCH_PAPER_PREVIEW_ONLY",
            "orders_submitted": 0,
            "manual_confirmation_required": True,
        },
    }
    if congressional_signals is not None or congressional_context is not None:
        signals = congressional_signals or {}
        f7_context = dict(congressional_context or {})
        f7_context.update(
            {
                "framework": "F7_CONGRESSIONAL_MARKET_INTELLIGENCE",
                "mode": "OPTIONAL_RESEARCH_ENRICHMENT",
                "signals_supplied": len(signals),
                "candidate_signals_available": sum(
                    signal.available for signal in signals.values()
                ),
                "changes_execution_eligibility": False,
                "can_bypass_guardian": False,
            }
        )
        payload["congressional_intelligence"] = f7_context
        payload["candidates"] = candidate_rows(run, signals)
    return payload
