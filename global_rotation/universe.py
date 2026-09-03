"""Versioned security-master loading for Global Rotation research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
import json
from pathlib import Path
from typing import Any, Mapping

from global_rotation.models import GlobalInstrument, RegionConfig


@dataclass(frozen=True)
class UniverseRegion:
    code: str
    benchmark_symbol: str
    currency: str
    fx_symbol: str | None = None
    fx_invert: bool = False

    def __post_init__(self) -> None:
        RegionConfig(self.code, self.benchmark_symbol, self.currency)
        if type(self.fx_invert) is not bool:
            raise ValueError("FX inversion must be true or false.")
        if self.currency != "USD" and not self.fx_symbol:
            raise ValueError(f"Region {self.code} requires an FX symbol.")

    def to_region_config(self) -> RegionConfig:
        return RegionConfig(
            code=self.code,
            benchmark_symbol=self.benchmark_symbol,
            currency=self.currency,
        )


@dataclass(frozen=True)
class UniverseSecurity:
    symbol: str
    name: str
    region: str
    exchange: str
    currency: str
    active: bool = True
    asset_type: str = "stock"
    etoro_eligible: bool | None = None
    fractional_enabled: bool = False
    underlying_buy_x1: bool = False
    is_cfd: bool = False
    is_247: bool = False

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("Universe symbol is required.")
        if not self.name.strip():
            raise ValueError(f"Universe name is required for {self.symbol}.")
        if not self.exchange.strip():
            raise ValueError(f"Exchange is required for {self.symbol}.")
        if len(self.currency.strip()) != 3:
            raise ValueError(f"Currency must have three letters for {self.symbol}.")
        if self.asset_type != "stock":
            raise ValueError(f"Only listed stocks are allowed: {self.symbol}.")
        if self.etoro_eligible is not None and type(self.etoro_eligible) is not bool:
            raise ValueError("eToro eligibility must be true, false, or null.")
        for name, value in (
            ("Active status", self.active),
            ("Fractional capability", self.fractional_enabled),
            ("BUY x1 capability", self.underlying_buy_x1),
            ("CFD status", self.is_cfd),
            ("24/7 status", self.is_247),
        ):
            if type(value) is not bool:
                raise ValueError(f"{name} must be true or false.")

    def to_instrument(self, *, fx_to_usd: Decimal) -> GlobalInstrument:
        return GlobalInstrument(
            symbol=self.symbol,
            region=self.region,
            currency=self.currency,
            fx_to_usd=fx_to_usd,
            etoro_eligible=self.etoro_eligible,
            fractional_enabled=self.fractional_enabled,
            underlying_buy_x1=self.underlying_buy_x1,
            is_cfd=self.is_cfd,
            is_247=self.is_247,
        )


@dataclass(frozen=True)
class UniverseSnapshot:
    schema_version: int
    universe_id: str
    version: str
    as_of: date
    source: str
    regions: tuple[UniverseRegion, ...]
    securities: tuple[UniverseSecurity, ...]

    def __post_init__(self) -> None:
        if self.schema_version != 1:
            raise ValueError("Unsupported universe schema version.")
        if not self.universe_id.strip() or not self.version.strip():
            raise ValueError("Universe id and version are required.")
        if not self.source.strip():
            raise ValueError("Universe source description is required.")
        region_codes = [item.code for item in self.regions]
        if not region_codes or len(region_codes) != len(set(region_codes)):
            raise ValueError("Universe regions must be present and unique.")
        symbols = [item.symbol.strip().upper() for item in self.securities]
        if not symbols or len(symbols) != len(set(symbols)):
            raise ValueError("Universe symbols must be present and unique.")
        regions = {item.code: item for item in self.regions}
        for security in self.securities:
            region = regions.get(security.region)
            if region is None:
                raise ValueError(
                    f"Security {security.symbol} references unknown region {security.region}."
                )
            if security.currency != region.currency:
                raise ValueError(
                    f"Security {security.symbol} currency does not match its region."
                )

    @property
    def active_securities(self) -> tuple[UniverseSecurity, ...]:
        return tuple(item for item in self.securities if item.active)

    @property
    def history_symbols(self) -> tuple[str, ...]:
        symbols = [item.symbol for item in self.active_securities]
        symbols.extend(item.benchmark_symbol for item in self.regions)
        symbols.extend(item.fx_symbol for item in self.regions if item.fx_symbol)
        return tuple(dict.fromkeys(symbols))


def _optional_bool(value: Any, *, field: str) -> bool | None:
    if value is None or isinstance(value, bool):
        return value
    raise ValueError(f"{field} must be true, false, or null.")


def _bool(value: Any, *, field: str, default: bool) -> bool:
    selected = default if value is None else value
    if isinstance(selected, bool):
        return selected
    raise ValueError(f"{field} must be true or false.")


def parse_universe(payload: Mapping[str, Any]) -> UniverseSnapshot:
    """Validate a decoded v1 universe payload."""

    regions = tuple(
        UniverseRegion(
            code=str(item["code"]).strip(),
            benchmark_symbol=str(item["benchmark_symbol"]).strip().upper(),
            currency=str(item["currency"]).strip().upper(),
            fx_symbol=(
                str(item["fx_symbol"]).strip().upper()
                if item.get("fx_symbol")
                else None
            ),
            fx_invert=_bool(item.get("fx_invert"), field="fx_invert", default=False),
        )
        for item in payload["regions"]
    )
    securities = tuple(
        UniverseSecurity(
            symbol=str(item["symbol"]).strip().upper(),
            name=str(item["name"]).strip(),
            region=str(item["region"]).strip(),
            exchange=str(item["exchange"]).strip().upper(),
            currency=str(item["currency"]).strip().upper(),
            active=_bool(item.get("active"), field="active", default=True),
            asset_type=str(item.get("asset_type", "stock")).strip().lower(),
            etoro_eligible=_optional_bool(
                item.get("etoro_eligible"), field="etoro_eligible"
            ),
            fractional_enabled=_bool(
                item.get("fractional_enabled"),
                field="fractional_enabled",
                default=False,
            ),
            underlying_buy_x1=_bool(
                item.get("underlying_buy_x1"),
                field="underlying_buy_x1",
                default=False,
            ),
            is_cfd=_bool(item.get("is_cfd"), field="is_cfd", default=False),
            is_247=_bool(item.get("is_247"), field="is_247", default=False),
        )
        for item in payload["securities"]
    )
    return UniverseSnapshot(
        schema_version=int(payload["schema_version"]),
        universe_id=str(payload["universe_id"]).strip(),
        version=str(payload["version"]).strip(),
        as_of=date.fromisoformat(str(payload["as_of"])),
        source=str(payload["source"]).strip(),
        regions=regions,
        securities=securities,
    )


def load_universe(path: str | Path) -> UniverseSnapshot:
    """Load a universe JSON file without network or broker side effects."""

    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Universe payload must be a JSON object.")
    return parse_universe(payload)
