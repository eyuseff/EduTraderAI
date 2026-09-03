"""Application service for a read-only Global Rotation daily run."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from hashlib import sha256
import json
from types import MappingProxyType
from typing import Any, Mapping

import pandas as pd

from global_rotation.data import (
    REQUIRED_COLUMNS,
    DataQualityIssue,
    DailyHistoryProvider,
)
from global_rotation.engine import GlobalRotationEngine
from global_rotation.models import GlobalRotationResult
from global_rotation.risk import PaperPortfolioContext, PaperRiskPolicy
from global_rotation.universe import UniverseRegion, UniverseSnapshot


@dataclass(frozen=True)
class DailyGlobalRotationRun:
    run_id: str
    operator_schema: str
    universe_sha256: str
    portfolio_sha256: str
    market_data_sha256: str
    data_quality_sha256: str
    result_sha256: str
    risk_policy_sha256: str
    rotation_policy_sha256: str
    universe_id: str
    universe_version: str
    universe_size: int
    histories_requested: int
    histories_loaded: int
    as_of_by_region: Mapping[str, date]
    fx_as_of_by_region: Mapping[str, date]
    result: GlobalRotationResult
    data_issues: tuple[DataQualityIssue, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "as_of_by_region",
            MappingProxyType(dict(sorted(self.as_of_by_region.items()))),
        )
        object.__setattr__(
            self,
            "fx_as_of_by_region",
            MappingProxyType(dict(sorted(self.fx_as_of_by_region.items()))),
        )


def _json_default(value: object) -> str:
    if isinstance(value, (date, Decimal)):
        return value.isoformat() if isinstance(value, date) else str(value)
    raise TypeError(f"Unsupported canonical JSON type: {type(value).__name__}.")


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=_json_default,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _market_data_sha256(histories: Mapping[str, pd.DataFrame]) -> str:
    """Fingerprint every OHLCV value that can influence a daily scan."""

    payload: dict[str, dict[str, object]] = {}
    for symbol in sorted(histories):
        frame = histories[symbol].loc[:, list(REQUIRED_COLUMNS)].sort_index()
        payload[symbol] = {
            "index": [pd.Timestamp(item).isoformat() for item in frame.index],
            "ohlcv_float_hex": [
                [float(value).hex() for value in row]
                for row in frame.itertuples(index=False, name=None)
            ],
        }
    return _canonical_sha256(payload)


def _result_sha256(result: GlobalRotationResult) -> str:
    return _canonical_sha256(
        {
            "candidates": [asdict(item) for item in result.candidates],
            "rejected": [asdict(item) for item in result.rejected],
            "regimes": {
                key: asdict(value) for key, value in sorted(result.regimes.items())
            },
            "scanned": result.scanned,
            "valid": result.valid,
        }
    )


def _last_session(frame: pd.DataFrame) -> date:
    return pd.Timestamp(frame.index[-1]).date()


def _region_fx_rate(
    region: UniverseRegion,
    histories: Mapping[str, pd.DataFrame],
    *,
    expected_session: date,
) -> tuple[Decimal | None, date | None, str | None]:
    if region.currency == "USD":
        return Decimal("1"), expected_session, None
    if not region.fx_symbol or region.fx_symbol not in histories:
        return None, None, "MISSING_FX"
    frame = histories[region.fx_symbol]
    session_mask = pd.Index(
        [pd.Timestamp(item).date() == expected_session for item in frame.index]
    )
    matching = frame.loc[session_mask]
    if matching.empty:
        return None, None, "STALE_FX"
    value = Decimal(str(float(matching["Close"].iloc[-1])))
    if not value.is_finite() or value <= 0:
        return None, None, "INVALID_FX"
    rate = Decimal("1") / value if region.fx_invert else value
    return rate, expected_session, None


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
        fx_sessions: dict[str, date] = {}
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
            benchmark_session = _last_session(benchmark)
            fx_rate, fx_session, fx_issue = _region_fx_rate(
                region,
                histories,
                expected_session=benchmark_session,
            )
            if fx_rate is None:
                issues.append(
                    DataQualityIssue(
                        region.fx_symbol or region.currency,
                        fx_issue or "INVALID_FX",
                        f"Region {region.code} was skipped because same-session FX "
                        f"for {benchmark_session} is unavailable or invalid.",
                    )
                )
                continue
            regions.append(region)
            region_sessions[region.code] = benchmark_session
            if fx_session is None:
                raise RuntimeError("Accepted FX data did not record a session.")
            fx_sessions[region.code] = fx_session
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
        universe_sha256 = _canonical_sha256(asdict(universe))
        portfolio_sha256 = _canonical_sha256(asdict(portfolio))
        market_data_sha256 = _market_data_sha256(batch.histories)
        data_quality_sha256 = _canonical_sha256([asdict(issue) for issue in issues])
        result_sha256 = _result_sha256(result)
        risk_policy_sha256 = _canonical_sha256(asdict(self.risk_policy))
        rotation_policy_sha256 = _canonical_sha256(asdict(engine.rotation_policy))
        operator_schema = "global-rotation-daily-output-v2"
        run_id = _canonical_sha256(
            {
                "operator_schema": operator_schema,
                "universe_sha256": universe_sha256,
                "portfolio_sha256": portfolio_sha256,
                "market_data_sha256": market_data_sha256,
                "data_quality_sha256": data_quality_sha256,
                "result_sha256": result_sha256,
                "risk_policy_sha256": risk_policy_sha256,
                "rotation_policy_sha256": rotation_policy_sha256,
                "histories_requested": batch.requested,
                "histories_loaded": batch.loaded,
                "as_of_by_region": {
                    key: value.isoformat()
                    for key, value in sorted(region_sessions.items())
                },
                "fx_as_of_by_region": {
                    key: value.isoformat() for key, value in sorted(fx_sessions.items())
                },
            }
        )
        return DailyGlobalRotationRun(
            run_id=run_id,
            operator_schema=operator_schema,
            universe_sha256=universe_sha256,
            portfolio_sha256=portfolio_sha256,
            market_data_sha256=market_data_sha256,
            data_quality_sha256=data_quality_sha256,
            result_sha256=result_sha256,
            risk_policy_sha256=risk_policy_sha256,
            rotation_policy_sha256=rotation_policy_sha256,
            universe_id=universe.universe_id,
            universe_version=universe.version,
            universe_size=len(universe.active_securities),
            histories_requested=batch.requested,
            histories_loaded=batch.loaded,
            as_of_by_region=region_sessions,
            fx_as_of_by_region=fx_sessions,
            result=result,
            data_issues=tuple(issues),
        )
