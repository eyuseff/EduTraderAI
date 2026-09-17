"""Provider-neutral congressional disclosure intelligence for Global Rotation.

F7 is a research-only enrichment. It scores only disclosures that were already
public as of the evaluation date and never changes execution eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from statistics import median
from typing import Any, Iterable, Literal, Mapping, cast

CongressionalDirection = Literal[
    "bullish", "bearish", "mixed", "neutral", "unavailable"
]
CongressionalSide = Literal["purchase", "sale", "other"]

_TRANSACTION_ALIASES: dict[str, CongressionalSide] = {
    "buy": "purchase",
    "purchase": "purchase",
    "purchased": "purchase",
    "sell": "sale",
    "sale": "sale",
    "sold": "sale",
    "sale_full": "sale",
    "sale_partial": "sale",
    "sale (full)": "sale",
    "sale (partial)": "sale",
    "exchange": "other",
    "other": "other",
}


def _transaction_side(value: str) -> CongressionalSide:
    normalized = value.strip().lower().replace("-", "_")
    try:
        return _TRANSACTION_ALIASES[normalized]
    except KeyError as exc:
        raise ValueError(
            f"Unsupported congressional transaction type: {value!r}."
        ) from exc


def _finite_decimal(value: Any, *, field: str) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{field} must be a valid decimal amount.") from exc
    if not parsed.is_finite() or parsed < Decimal("0"):
        raise ValueError(f"{field} must be a finite non-negative amount.")
    return parsed


def _iso_date(value: Any, *, field: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be an ISO date string.")
    try:
        return date.fromisoformat(value.strip())
    except ValueError as exc:
        raise ValueError(f"{field} must use YYYY-MM-DD format.") from exc


@dataclass(frozen=True)
class CongressionalTrade:
    """One normalized, publicly disclosed securities transaction."""

    symbol: str
    politician: str
    transaction_type: str
    traded_on: date
    published_on: date
    amount_low_usd: Decimal | None = None
    amount_high_usd: Decimal | None = None
    owner: str | None = None
    chamber: str | None = None
    committees: tuple[str, ...] = ()
    source: str = "capitoltrades"
    source_url: str | None = None
    disclosure_id: str | None = None

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        politician = self.politician.strip()
        source = self.source.strip()
        if not symbol:
            raise ValueError("Congressional trade symbol is required.")
        if not politician:
            raise ValueError("Congressional trade politician is required.")
        if not source:
            raise ValueError("Congressional trade source is required.")
        if self.published_on < self.traded_on:
            raise ValueError("published_on cannot be earlier than traded_on.")
        for field, amount in (
            ("amount_low_usd", self.amount_low_usd),
            ("amount_high_usd", self.amount_high_usd),
        ):
            if amount is not None and (
                not isinstance(amount, Decimal)
                or not amount.is_finite()
                or amount < Decimal("0")
            ):
                raise ValueError(f"{field} must be a finite non-negative Decimal.")
        if (
            self.amount_low_usd is not None
            and self.amount_high_usd is not None
            and self.amount_high_usd < self.amount_low_usd
        ):
            raise ValueError("amount_high_usd cannot be below amount_low_usd.")
        committees = tuple(
            dict.fromkeys(item.strip() for item in self.committees if item.strip())
        )
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "politician", politician)
        object.__setattr__(
            self, "transaction_type", _transaction_side(self.transaction_type)
        )
        object.__setattr__(self, "source", source)
        object.__setattr__(self, "committees", committees)

    @property
    def side(self) -> CongressionalSide:
        return cast(CongressionalSide, self.transaction_type)

    @property
    def disclosure_lag_days(self) -> int:
        return (self.published_on - self.traded_on).days

    @property
    def reported_upper_amount_usd(self) -> Decimal | None:
        return self.amount_high_usd or self.amount_low_usd


@dataclass(frozen=True)
class CongressionalSnapshot:
    """Auditable normalized disclosure snapshot from one named source."""

    source: str
    as_of: date
    trades: tuple[CongressionalTrade, ...]
    schema_version: int = 1


@dataclass(frozen=True)
class CongressionalSignalPolicy:
    """Deterministic F7 scoring rules; execution gates remain out of scope."""

    lookback_days: int = 30
    very_recent_days: int = 3
    recent_days: int = 7
    moderate_recency_days: int = 14
    low_lag_days: int = 7
    moderate_lag_days: int = 21
    maximum_priority_adjustment: int = 15

    def __post_init__(self) -> None:
        values = (
            self.lookback_days,
            self.very_recent_days,
            self.recent_days,
            self.moderate_recency_days,
            self.low_lag_days,
            self.moderate_lag_days,
            self.maximum_priority_adjustment,
        )
        if any(type(value) is not int or value < 1 for value in values):
            raise ValueError(
                "Congressional signal policy values must be positive integers."
            )
        if not (
            self.very_recent_days <= self.recent_days <= self.moderate_recency_days
        ):
            raise ValueError(
                "Congressional publication-age thresholds are not monotonic."
            )
        if self.moderate_recency_days > self.lookback_days:
            raise ValueError("Moderate recency cannot exceed the lookback window.")
        if self.low_lag_days > self.moderate_lag_days:
            raise ValueError("Disclosure-lag thresholds are not monotonic.")


@dataclass(frozen=True)
class CongressionalSignal:
    """Explainable F7 signal for one ticker."""

    symbol: str
    as_of: date
    available: bool
    score: int
    direction: CongressionalDirection
    priority_adjustment: int
    trade_count: int
    purchase_count: int
    sale_count: int
    unique_purchase_traders: int
    unique_sale_traders: int
    freshest_publication_age_days: int | None
    median_disclosure_lag_days: float | None
    largest_reported_upper_usd: Decimal | None
    source_names: tuple[str, ...]
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not 0 <= self.score <= 100:
            raise ValueError("Congressional signal score must be between 0 and 100.")
        if not -15 <= self.priority_adjustment <= 15:
            raise ValueError(
                "Congressional priority adjustment must be between -15 and 15."
            )


def _freshness_points(age_days: int, policy: CongressionalSignalPolicy) -> int:
    if age_days <= policy.very_recent_days:
        return 20
    if age_days <= policy.recent_days:
        return 12
    if age_days <= policy.moderate_recency_days:
        return 5
    return 0


def _lag_points(lag_days: float, policy: CongressionalSignalPolicy) -> int:
    if lag_days <= policy.low_lag_days:
        return 15
    if lag_days <= policy.moderate_lag_days:
        return 8
    if lag_days <= policy.lookback_days:
        return 3
    return 0


def _amount_points(amount: Decimal | None) -> int:
    if amount is None:
        return 0
    if amount >= Decimal("250000"):
        return 15
    if amount >= Decimal("100000"):
        return 10
    if amount >= Decimal("50000"):
        return 5
    return 0


def _side_strength(
    trades: list[CongressionalTrade],
    *,
    side: CongressionalSide,
    as_of: date,
    policy: CongressionalSignalPolicy,
) -> tuple[int, list[str]]:
    selected = [trade for trade in trades if trade.side == side]
    if not selected:
        return 0, []

    score = 20
    reasons = [f"{len(selected)} disclosed {side} transaction(s) in lookback window."]
    freshest_age = min((as_of - trade.published_on).days for trade in selected)
    score += _freshness_points(freshest_age, policy)

    unique_traders = len({trade.politician.casefold() for trade in selected})
    if unique_traders >= 2:
        score += 15
    if unique_traders >= 3:
        score += 10
    if any(
        sum(1 for trade in selected if trade.politician.casefold() == politician) >= 2
        for politician in {trade.politician.casefold() for trade in selected}
    ):
        score += 10

    largest_amount = max(
        (
            trade.reported_upper_amount_usd
            for trade in selected
            if trade.reported_upper_amount_usd is not None
        ),
        default=None,
    )
    score += _amount_points(largest_amount)

    median_lag = float(median(trade.disclosure_lag_days for trade in selected))
    score += _lag_points(median_lag, policy)
    reasons.append(f"Freshest {side} disclosure is {freshest_age} day(s) old.")
    reasons.append(f"Median {side} disclosure lag is {median_lag:g} day(s).")
    if unique_traders >= 2:
        reasons.append(
            f"{unique_traders} independent disclosers reported {side} activity."
        )
    return min(score, 100), reasons


def score_congressional_activity(
    symbol: str,
    trades: Iterable[CongressionalTrade],
    *,
    as_of: date,
    policy: CongressionalSignalPolicy | None = None,
) -> CongressionalSignal:
    """Score one symbol using only disclosures public on or before ``as_of``."""

    active_policy = policy or CongressionalSignalPolicy()
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("Congressional signal symbol is required.")

    eligible = [
        trade
        for trade in trades
        if trade.symbol == normalized_symbol
        and trade.published_on <= as_of
        and (as_of - trade.published_on).days <= active_policy.lookback_days
    ]
    eligible.sort(key=lambda item: (item.published_on, item.traded_on, item.politician))
    if not eligible:
        return CongressionalSignal(
            symbol=normalized_symbol,
            as_of=as_of,
            available=False,
            score=0,
            direction="unavailable",
            priority_adjustment=0,
            trade_count=0,
            purchase_count=0,
            sale_count=0,
            unique_purchase_traders=0,
            unique_sale_traders=0,
            freshest_publication_age_days=None,
            median_disclosure_lag_days=None,
            largest_reported_upper_usd=None,
            source_names=(),
            reasons=(
                "No public congressional disclosure in the configured lookback window.",
            ),
        )

    purchase_strength, purchase_reasons = _side_strength(
        eligible, side="purchase", as_of=as_of, policy=active_policy
    )
    sale_strength, sale_reasons = _side_strength(
        eligible, side="sale", as_of=as_of, policy=active_policy
    )
    net = purchase_strength - sale_strength
    if purchase_strength and sale_strength and abs(net) < 10:
        direction: CongressionalDirection = "mixed"
    elif net > 0:
        direction = "bullish"
    elif net < 0:
        direction = "bearish"
    else:
        direction = "neutral"

    adjustment = int(round(net * active_policy.maximum_priority_adjustment / 100))
    adjustment = max(
        -active_policy.maximum_priority_adjustment,
        min(active_policy.maximum_priority_adjustment, adjustment),
    )
    purchase_traders = {
        trade.politician.casefold() for trade in eligible if trade.side == "purchase"
    }
    sale_traders = {
        trade.politician.casefold() for trade in eligible if trade.side == "sale"
    }
    largest_amount = max(
        (
            trade.reported_upper_amount_usd
            for trade in eligible
            if trade.reported_upper_amount_usd is not None
        ),
        default=None,
    )
    return CongressionalSignal(
        symbol=normalized_symbol,
        as_of=as_of,
        available=True,
        score=max(purchase_strength, sale_strength),
        direction=direction,
        priority_adjustment=adjustment,
        trade_count=len(eligible),
        purchase_count=sum(trade.side == "purchase" for trade in eligible),
        sale_count=sum(trade.side == "sale" for trade in eligible),
        unique_purchase_traders=len(purchase_traders),
        unique_sale_traders=len(sale_traders),
        freshest_publication_age_days=min(
            (as_of - trade.published_on).days for trade in eligible
        ),
        median_disclosure_lag_days=float(
            median(trade.disclosure_lag_days for trade in eligible)
        ),
        largest_reported_upper_usd=largest_amount,
        source_names=tuple(sorted({trade.source for trade in eligible})),
        reasons=tuple(purchase_reasons + sale_reasons),
    )


def score_congressional_universe(
    symbols: Iterable[str],
    trades: Iterable[CongressionalTrade],
    *,
    as_of: date,
    policy: CongressionalSignalPolicy | None = None,
) -> dict[str, CongressionalSignal]:
    records = tuple(trades)
    return {
        symbol.strip().upper(): score_congressional_activity(
            symbol, records, as_of=as_of, policy=policy
        )
        for symbol in symbols
    }


def parse_congressional_snapshot(payload: Mapping[str, Any]) -> CongressionalSnapshot:
    """Parse the normalized JSON interchange format used by the F7 adapter."""

    if payload.get("schema_version") != 1:
        raise ValueError("Congressional snapshot schema_version must equal 1.")
    source = payload.get("source")
    if not isinstance(source, str) or not source.strip():
        raise ValueError("Congressional snapshot source is required.")
    snapshot_as_of = _iso_date(payload.get("as_of"), field="as_of")
    raw_trades = payload.get("trades")
    if not isinstance(raw_trades, list):
        raise ValueError("Congressional snapshot trades must be a JSON array.")

    parsed: list[CongressionalTrade] = []
    for index, raw in enumerate(raw_trades):
        if not isinstance(raw, Mapping):
            raise ValueError(f"Congressional trade {index} must be a JSON object.")
        committees_value = raw.get("committees", [])
        if not isinstance(committees_value, list) or any(
            not isinstance(item, str) for item in committees_value
        ):
            raise ValueError(f"Congressional trade {index} committees must be strings.")
        record_source = raw.get("source", source)
        if not isinstance(record_source, str):
            raise ValueError(f"Congressional trade {index} source must be a string.")
        parsed.append(
            CongressionalTrade(
                symbol=str(raw.get("symbol", "")),
                politician=str(raw.get("politician", "")),
                transaction_type=str(raw.get("transaction_type", "")),
                traded_on=_iso_date(raw.get("traded_on"), field="traded_on"),
                published_on=_iso_date(raw.get("published_on"), field="published_on"),
                amount_low_usd=_finite_decimal(
                    raw.get("amount_low_usd"), field="amount_low_usd"
                ),
                amount_high_usd=_finite_decimal(
                    raw.get("amount_high_usd"), field="amount_high_usd"
                ),
                owner=(
                    str(raw["owner"]).strip()
                    if raw.get("owner") is not None
                    else None
                ),
                chamber=(
                    str(raw["chamber"]).strip()
                    if raw.get("chamber") is not None
                    else None
                ),
                committees=tuple(committees_value),
                source=record_source,
                source_url=(
                    str(raw["source_url"]).strip()
                    if raw.get("source_url") is not None
                    else None
                ),
                disclosure_id=(
                    str(raw["disclosure_id"]).strip()
                    if raw.get("disclosure_id") is not None
                    else None
                ),
            )
        )
    return CongressionalSnapshot(
        source=source.strip(),
        as_of=snapshot_as_of,
        trades=tuple(parsed),
    )


def load_congressional_snapshot(path: Path) -> CongressionalSnapshot:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("Congressional snapshot must be a JSON object.")
    return parse_congressional_snapshot(payload)


def congressional_signal_payload(signal: CongressionalSignal) -> dict[str, Any]:
    return {
        "symbol": signal.symbol,
        "as_of": signal.as_of.isoformat(),
        "available": signal.available,
        "score": signal.score,
        "direction": signal.direction,
        "priority_adjustment": signal.priority_adjustment,
        "trade_count": signal.trade_count,
        "purchase_count": signal.purchase_count,
        "sale_count": signal.sale_count,
        "unique_purchase_traders": signal.unique_purchase_traders,
        "unique_sale_traders": signal.unique_sale_traders,
        "freshest_publication_age_days": signal.freshest_publication_age_days,
        "median_disclosure_lag_days": signal.median_disclosure_lag_days,
        "largest_reported_upper_usd": (
            str(signal.largest_reported_upper_usd)
            if signal.largest_reported_upper_usd is not None
            else None
        ),
        "source_names": list(signal.source_names),
        "reasons": list(signal.reasons),
    }
