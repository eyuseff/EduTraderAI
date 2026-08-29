"""Application service for a read-only Global Rotation daily run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
from typing import Mapping

import pandas as pd

from global_rotation.data import DataQualityIssue, DailyHistoryProvider
from global_rotation.engine import GlobalRotationEngine
from global_rotation.models import GlobalRotationResult
from global_rotation.risk import PaperPortfolioContext, PaperRiskPolicy
from global_rotation.universe import UniverseRegion, UniverseSnapshot


@dataclass(frozen=True)
class DailyGlobalRotationRun:
    run_id: str
    universe_id: str
    universe_version: str
    universe_size: int
    histories_requested: int
    histories_loaded: int
    as_of_by_region: dict[str, date]
    result: GlobalRotationResult
    data_issues: tuple[DataQualityIssue, ...]


def _last_session(frame: pd.DataFrame) -> date:
    return pd.Timestamp(frame.index[-1]).date()


def _region_fx_rate(
    region: UniverseRegion,
    histories: Mapping[str, pd.DataFrame],
) -> Decimal | None:
    if region.currency == "USD":
        return Decimal("1")
    if not region.fx_symbol or region.fx_symbol not in histories:
        return None
    value = Decimal(str(float(histories[region.fx_symbol]["Close"].iloc[-1])))
    if value <= 0:
        return None
    return Decimal("1") / value if region.fx_invert else value


class DailyGlobalRotationService:
    """Compose universe, read-only data, quality gates, and the pure scanner."""

    def __init__(
        self,
        provider: DailyHistoryProvider,
        *,
        risk_policy: PaperRiskPolicy | None = None,
    ) -> None:
        self.provider = provider
        self.risk_policy = risk_policy or PaperRiskPolicy()

    def run(
        self,
        *,
        universe: UniverseSnapshot,
        portfolio: PaperPortfolioContext,
    ) -> DailyGlobalRotationRun:
        batch = self.provider.load(universe.history_symbols)
        histories = dict(batch.histories)
        issues = list(batch.issues)
        regions: list[UniverseRegion] = []
        region_sessions: dict[str, date] = {}
        fx_rates: dict[str, Decimal] = {}

        for region in universe.regions:
            benchmark = histories.get(region.benchmark_symbol)
            if benchmark is None:
                issues.append(
                    DataQualityIssue(
                        region.benchmark_symbol,
                        "MISSING_BENCHMARK",
                        f"Region {region.code} was skipped because its benchmark is unavailable.",
                    )
                )
                continue
            fx_rate = _region_fx_rate(region, histories)
            if fx_rate is None:
                issues.append(
                    DataQualityIssue(
                        region.fx_symbol or region.currency,
                        "MISSING_FX",
                        f"Region {region.code} was skipped because FX is unavailable.",
                    )
                )
                continue
            regions.append(region)
            region_sessions[region.code] = _last_session(benchmark)
            fx_rates[region.code] = fx_rate

        if not regions:
            raise RuntimeError("No region passed benchmark and FX data-quality gates.")

        instruments = []
        active_region_codes = {item.code for item in regions}
        for security in universe.active_securities:
            if security.region not in active_region_codes:
                continue
            history = histories.get(security.symbol)
            if history is None:
                continue
            expected_session = region_sessions[security.region]
            actual_session = _last_session(history)
            if actual_session != expected_session:
                issues.append(
                    DataQualityIssue(
                        security.symbol,
                        "STALE_SESSION",
                        f"Last session {actual_session} does not match regional benchmark "
                        f"session {expected_session}.",
                    )
                )
                histories.pop(security.symbol, None)
                continue
            instruments.append(
                security.to_instrument(fx_to_usd=fx_rates[security.region])
            )

        engine = GlobalRotationEngine(
            regions=[item.to_region_config() for item in regions],
            risk_policy=self.risk_policy,
        )
        result = engine.scan(
            instruments=instruments,
            histories=histories,
            portfolio=portfolio,
        )
        identity = "|".join(
            [
                universe.universe_id,
                universe.version,
                *(f"{key}:{region_sessions[key]}" for key in sorted(region_sessions)),
            ]
        )
        run_id = sha256(identity.encode("utf-8")).hexdigest()[:16]
        return DailyGlobalRotationRun(
            run_id=run_id,
            universe_id=universe.universe_id,
            universe_version=universe.version,
            universe_size=len(universe.active_securities),
            histories_requested=batch.requested,
            histories_loaded=batch.loaded,
            as_of_by_region=region_sessions,
            result=result,
            data_issues=tuple(issues),
        )
