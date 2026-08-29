"""Serializable presentation helpers for Global Rotation daily runs."""

from __future__ import annotations

from typing import Any

from global_rotation.daily import DailyGlobalRotationRun


def candidate_rows(run: DailyGlobalRotationRun) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for candidate in run.result.candidates:
        first_invalidation = (
            candidate.blockers[0]
            if candidate.blockers
            else f"Close below stop {candidate.stop_local} {candidate.currency}."
        )
        rows.append(
            {
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
                "position_value_usd": str(candidate.position_value_usd),
                "planned_loss_usd": str(candidate.planned_loss_usd),
                "target_profit_usd": str(candidate.target_profit_usd),
                "category": candidate.category,
                "blockers": " | ".join(candidate.blockers),
                "first_invalidation": first_invalidation,
            }
        )
    return rows


def data_issue_rows(run: DailyGlobalRotationRun) -> list[dict[str, str]]:
    return [
        {"symbol": item.symbol, "code": item.code, "message": item.message}
        for item in run.data_issues
    ]


def run_payload(run: DailyGlobalRotationRun) -> dict[str, Any]:
    categories: dict[str, int] = {}
    for candidate in run.result.candidates:
        categories[candidate.category] = categories.get(candidate.category, 0) + 1
    return {
        "run_id": run.run_id,
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
