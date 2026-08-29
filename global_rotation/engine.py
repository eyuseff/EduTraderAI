"""Deterministic orchestration for regional EduTrader + Volcanes scans."""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

from global_rotation.models import (
    GlobalInstrument,
    GlobalRotationCandidate,
    GlobalRotationResult,
    RegionConfig,
    RotationPolicy,
    ScanRejection,
)
from global_rotation.risk import (
    PaperPortfolioContext,
    PaperRiskPolicy,
    blocked_paper_preview,
    size_paper_position,
)
from market.regime import MarketRegime, classify_market
from scanner_engine.automated_scanner import _atr, _rsi
from strategies.trend_momentum import score_candidate
from volcanoes.domain import Candidate as VolcanoCandidate
from volcanoes.guardian.guardian import Guardian
from volcanoes.scanner.momentum import score_momentum


def _decimal(value: float | int | Decimal) -> Decimal:
    return Decimal(str(round(float(value), 8)))


def _clean_history(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(frame.columns):
        missing = ", ".join(sorted(required.difference(frame.columns)))
        raise ValueError(f"Market history is missing columns: {missing}.")
    clean = frame.loc[:, ["Open", "High", "Low", "Close", "Volume"]].dropna()
    if len(clean) < 210:
        raise ValueError("At least 210 complete daily bars are required.")
    return clean


class GlobalRotationEngine:
    """Rank paper-only global long candidates without broker side effects."""

    def __init__(
        self,
        *,
        regions: Sequence[RegionConfig],
        rotation_policy: RotationPolicy | None = None,
        risk_policy: PaperRiskPolicy | None = None,
    ) -> None:
        self.regions = {region.code: region for region in regions}
        if not self.regions:
            raise ValueError("At least one region must be configured.")
        self.rotation_policy = rotation_policy or RotationPolicy()
        self.risk_policy = risk_policy or PaperRiskPolicy()
        self.guardian = Guardian(minimum_score=self.rotation_policy.volcano_min_score)

    def scan(
        self,
        *,
        instruments: Sequence[GlobalInstrument],
        histories: Mapping[str, pd.DataFrame],
        portfolio: PaperPortfolioContext,
    ) -> GlobalRotationResult:
        regimes, regime_rejections = self._classify_regions(histories)
        candidates: list[GlobalRotationCandidate] = []
        rejected: list[ScanRejection] = list(regime_rejections)
        seen: set[str] = set()
        valid = 0

        for instrument in instruments:
            symbol = instrument.symbol.strip().upper()
            if symbol in seen:
                rejected.append(
                    ScanRejection(
                        symbol, instrument.region, "Duplicate universe symbol."
                    )
                )
                continue
            seen.add(symbol)
            region = self.regions.get(instrument.region)
            if region is None:
                rejected.append(
                    ScanRejection(
                        symbol, instrument.region, "Region is not configured."
                    )
                )
                continue
            frame = histories.get(instrument.symbol)
            if frame is None:
                rejected.append(
                    ScanRejection(
                        symbol, instrument.region, "Market history unavailable."
                    )
                )
                continue
            try:
                clean = _clean_history(frame)
            except ValueError as exc:
                rejected.append(ScanRejection(symbol, instrument.region, str(exc)))
                continue
            valid += 1
            candidate = self._evaluate(
                instrument=instrument,
                frame=clean,
                regime=regimes[region.code],
                portfolio=portfolio,
            )
            if candidate is None:
                rejected.append(
                    ScanRejection(
                        symbol,
                        instrument.region,
                        "Neither scanner reached its threshold.",
                    )
                )
            else:
                candidates.append(candidate)

        category_order = {"preparar": 0, "esperar": 1, "vigilar": 2, "no perseguir": 3}
        candidates.sort(
            key=lambda item: (
                category_order[item.category],
                -(item.edu_score + item.volcano_score),
                -float(item.reward_risk_to_resistance),
                item.symbol,
            )
        )
        return GlobalRotationResult(
            candidates=tuple(candidates[: self.rotation_policy.max_candidates]),
            rejected=tuple(rejected),
            regimes=regimes,
            scanned=len(instruments),
            valid=valid,
        )

    def _classify_regions(
        self,
        histories: Mapping[str, pd.DataFrame],
    ) -> tuple[dict[str, MarketRegime], list[ScanRejection]]:
        regimes: dict[str, MarketRegime] = {}
        rejected: list[ScanRejection] = []
        for region in self.regions.values():
            frame = histories.get(region.benchmark_symbol)
            if frame is None:
                raise RuntimeError(
                    f"Benchmark history unavailable for {region.code}: {region.benchmark_symbol}."
                )
            clean = _clean_history(frame)
            close = float(clean["Close"].iloc[-1])
            sma50 = float(clean["Close"].rolling(50).mean().iloc[-1])
            sma200 = float(clean["Close"].rolling(200).mean().iloc[-1])
            volatility_pct = float(
                clean["Close"].pct_change().tail(20).std() * np.sqrt(252) * 100
            )
            regimes[region.code] = classify_market(
                close,
                sma50,
                sma200,
                volatility_pct,
                benchmark_symbol=region.benchmark_symbol,
            )
        return regimes, rejected

    def _evaluate(
        self,
        *,
        instrument: GlobalInstrument,
        frame: pd.DataFrame,
        regime: MarketRegime,
        portfolio: PaperPortfolioContext,
    ) -> GlobalRotationCandidate | None:
        policy = self.rotation_policy
        close = float(frame["Close"].iloc[-1])
        previous = float(frame["Close"].iloc[-2])
        sma20 = float(frame["Close"].rolling(20).mean().iloc[-1])
        sma50 = float(frame["Close"].rolling(50).mean().iloc[-1])
        sma200 = float(frame["Close"].rolling(200).mean().iloc[-1])
        ema20 = float(frame["Close"].ewm(span=20, adjust=False).mean().iloc[-1])
        rsi14 = _rsi(frame["Close"])
        atr14 = _atr(frame)
        average_volume = float(frame["Volume"].tail(20).mean())
        relative_volume = (
            float(frame["Volume"].iloc[-1] / average_volume) if average_volume else 0.0
        )
        gap_pct = ((float(frame["Open"].iloc[-1]) / previous) - 1) * 100
        daily_change = ((close / previous) - 1) * 100

        edu = score_candidate(
            symbol=instrument.symbol,
            close=close,
            sma20=sma20,
            sma50=sma50,
            rsi14=rsi14,
            atr14=atr14,
            average_volume=average_volume,
            daily_change_pct=daily_change,
        )
        volcano_score, volcano_reasons = score_momentum(
            price=close,
            sma20=sma20,
            ema20=ema20,
            rsi14=rsi14,
        )
        guardian_decision = self.guardian.evaluate(
            VolcanoCandidate(
                symbol=instrument.symbol,
                strategy_name="Momentum",
                score=volcano_score,
                entry_price=close,
                explanation=" ".join(volcano_reasons),
            )
        )
        edu_pass = edu.score >= policy.edu_min_score
        volcano_pass = guardian_decision.approved
        if not edu_pass and not volcano_pass:
            return None

        fx = instrument.fx_to_usd
        entry_local = _decimal(edu.entry_price)
        entry_usd = entry_local * fx
        stop_local = _decimal(edu.stop_price)
        stop_usd = stop_local * fx
        stop_pct = (entry_local - stop_local) / entry_local
        target_pct = max(policy.minimum_target_pct, stop_pct * Decimal("2"))
        target_local = entry_local * (Decimal("1") + target_pct)
        stretch_target_local = entry_local * (Decimal("1") + policy.stretch_target_pct)
        resistance_local = _decimal(
            frame["High"].iloc[-(policy.resistance_lookback + 1) : -1].max()
        )
        risk_local = entry_local - stop_local
        reward_risk_to_resistance = (
            (resistance_local - entry_local) / risk_local
            if risk_local > 0
            else Decimal("0")
        )

        blockers: list[str] = []
        if not edu_pass:
            blockers.append(f"EduTrader score below {policy.edu_min_score}.")
        if not volcano_pass:
            blockers.append(guardian_decision.reason)
        if not regime.tradeable:
            blockers.append(f"Regional regime is {regime.label}.")
        if entry_usd < policy.minimum_price_usd:
            blockers.append("USD-equivalent price is below the minimum.")
        if _decimal(average_volume) < policy.minimum_average_volume:
            blockers.append("Average volume is below the minimum.")
        if close <= sma200:
            blockers.append("Price is below SMA200.")
        if abs(_decimal(daily_change)) > policy.maximum_daily_move_pct:
            blockers.append("Daily move exceeds the 4% chase limit.")
        if abs(_decimal(gap_pct)) > policy.maximum_gap_pct:
            blockers.append("Opening gap exceeds the 4% review limit.")
        if stop_pct > policy.maximum_stop_pct:
            blockers.append("Stop distance exceeds 7.5% for the 5–20 session mandate.")
        if target_pct > policy.stretch_target_pct:
            blockers.append("Minimum 2R target would exceed the 15% stretch target.")
        if resistance_local < target_local:
            blockers.append(
                "Prior 60-session resistance does not provide 2R target space."
            )
        if instrument.etoro_eligible is None:
            blockers.append("eToro eligibility is unverified.")
        elif instrument.etoro_eligible is False:
            blockers.append("Instrument is unavailable for this eToro account.")
        if not instrument.underlying_buy_x1 or instrument.is_cfd or instrument.is_247:
            blockers.append("Instrument is not an eligible BUY x1 underlying stock.")

        if blockers:
            size = blocked_paper_preview(
                portfolio=portfolio,
                policy=self.risk_policy,
            )
        else:
            size = size_paper_position(
                symbol=instrument.symbol,
                entry_usd=entry_usd,
                stop_usd=stop_usd,
                target_usd=target_local * fx,
                fractional_enabled=instrument.fractional_enabled,
                portfolio=portfolio,
                policy=self.risk_policy,
            )
        blockers.extend(size.blockers)

        if edu_pass and volcano_pass and not blockers:
            category = "preparar"
        elif (
            abs(_decimal(daily_change)) > policy.maximum_daily_move_pct
            or abs(_decimal(gap_pct)) > policy.maximum_gap_pct
            or target_pct > policy.stretch_target_pct
        ):
            category = "no perseguir"
        elif edu_pass and volcano_pass:
            category = "esperar"
        else:
            category = "vigilar"

        reasons = tuple(
            dict.fromkeys([*edu.reasons, *volcano_reasons, guardian_decision.reason])
        )
        return GlobalRotationCandidate(
            symbol=instrument.symbol.strip().upper(),
            region=instrument.region,
            currency=instrument.currency,
            regime=regime,
            edu_score=edu.score,
            volcano_score=volcano_score,
            guardian_approved=guardian_decision.approved,
            guardian_reason=guardian_decision.reason,
            entry_local=entry_local.quantize(Decimal("0.01")),
            entry_usd=entry_usd.quantize(Decimal("0.01")),
            rsi14=_decimal(rsi14).quantize(Decimal("0.01")),
            atr14_local=_decimal(atr14).quantize(Decimal("0.01")),
            gap_pct=_decimal(gap_pct).quantize(Decimal("0.01")),
            daily_change_pct=_decimal(daily_change).quantize(Decimal("0.01")),
            relative_volume=_decimal(relative_volume).quantize(Decimal("0.01")),
            stop_local=stop_local.quantize(Decimal("0.01")),
            stop_pct=(stop_pct * Decimal("100")).quantize(Decimal("0.01")),
            target_local=target_local.quantize(Decimal("0.01")),
            target_pct=(target_pct * Decimal("100")).quantize(Decimal("0.01")),
            stretch_target_local=stretch_target_local.quantize(Decimal("0.01")),
            resistance_local=resistance_local.quantize(Decimal("0.01")),
            reward_risk_to_resistance=reward_risk_to_resistance.quantize(
                Decimal("0.01")
            ),
            quantity=size.quantity,
            position_value_usd=size.position_value_usd,
            planned_loss_usd=size.planned_loss_usd,
            target_profit_usd=size.target_profit_usd,
            category=category,
            blockers=tuple(blockers),
            reasons=reasons,
        )
