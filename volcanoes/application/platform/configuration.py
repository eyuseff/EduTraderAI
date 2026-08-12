"""Immutable startup configuration and fail-closed validation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum


class ConfigurationError(ValueError):
    """Raised before execution when platform configuration is unsafe."""


class BrokerMode(StrEnum):
    """Supported paper-broker modes."""

    SIMULATED_PAPER = "SIMULATED_PAPER"
    ALPACA_PAPER = "ALPACA_PAPER"


class ScannerExecutionMode(StrEnum):
    """Scanner orchestration implementation selected at startup."""

    SUPERVISED = "SUPERVISED"
    LEGACY_ROLLBACK = "LEGACY_ROLLBACK"


@dataclass(frozen=True, slots=True)
class DeterministicFeatureFlags:
    """Release flags controlling manual and scanner execution paths."""

    preview: bool = True
    submission: bool = True
    scanner: bool = True


@dataclass(frozen=True, slots=True)
class TradingPolicyConfiguration:
    """Validated values used to compose the existing trading policies."""

    risk_per_trade_pct: Decimal = Decimal("0.25")
    max_daily_loss_pct: Decimal = Decimal("1.0")
    max_open_positions: int = 5
    max_total_exposure_pct: Decimal = Decimal("50.0")
    max_single_position_pct: Decimal = Decimal("12.0")
    minimum_reward_risk: Decimal = Decimal("2.0")
    minimum_price: Decimal = Decimal("10.0")
    long_only: bool = True


@dataclass(frozen=True, slots=True)
class CredentialStatus:
    """Secret-free indication of required broker credential availability."""

    alpaca_api_key_present: bool = False
    alpaca_secret_key_present: bool = False


@dataclass(frozen=True, slots=True)
class PlatformConfiguration:
    """Complete presentation-neutral startup configuration."""

    feature_flags: DeterministicFeatureFlags
    policy: TradingPolicyConfiguration
    broker_mode: BrokerMode
    scanner_execution_mode: ScannerExecutionMode
    credentials: CredentialStatus = CredentialStatus()


def validate_configuration(
    configuration: PlatformConfiguration,
) -> PlatformConfiguration:
    """Validate all execution-affecting configuration before composition."""

    if not isinstance(configuration, PlatformConfiguration):
        raise ConfigurationError(
            "configuration must be a PlatformConfiguration instance."
        )

    _validate_feature_flags(configuration.feature_flags)
    _validate_policy(configuration.policy)
    _validate_broker_mode(configuration)
    _validate_scanner_mode(configuration)
    return configuration


def validate_broker_runtime(
    configuration: PlatformConfiguration,
    *,
    broker_is_paper: bool,
) -> None:
    """Reject any concrete broker that is not explicitly paper-only."""

    validate_configuration(configuration)
    if type(broker_is_paper) is not bool:
        raise ConfigurationError("broker_is_paper must be a boolean.")
    if not broker_is_paper:
        raise ConfigurationError(
            "The selected broker is not paper-only; execution is disabled."
        )


def _validate_feature_flags(flags: DeterministicFeatureFlags) -> None:
    if not isinstance(flags, DeterministicFeatureFlags):
        raise ConfigurationError("feature_flags must be DeterministicFeatureFlags.")
    for name in ("preview", "submission", "scanner"):
        if type(getattr(flags, name)) is not bool:
            raise ConfigurationError(
                f"Deterministic feature flag {name!r} must be a boolean."
            )

    if flags.preview != flags.submission:
        raise ConfigurationError(
            "Manual preview and submission flags must change together: use both "
            "deterministic paths or both legacy rollback paths."
        )


def _validate_policy(policy: TradingPolicyConfiguration) -> None:
    if not isinstance(policy, TradingPolicyConfiguration):
        raise ConfigurationError(
            "policy must be a TradingPolicyConfiguration instance."
        )

    decimal_fields = (
        "risk_per_trade_pct",
        "max_daily_loss_pct",
        "max_total_exposure_pct",
        "max_single_position_pct",
        "minimum_reward_risk",
        "minimum_price",
    )
    for name in decimal_fields:
        value = getattr(policy, name)
        if not isinstance(value, Decimal) or not value.is_finite():
            raise ConfigurationError(f"Policy {name} must be a finite Decimal.")

    percentage_fields = (
        "risk_per_trade_pct",
        "max_daily_loss_pct",
        "max_total_exposure_pct",
        "max_single_position_pct",
    )
    for name in percentage_fields:
        value = getattr(policy, name)
        if value <= 0 or value > Decimal("100"):
            raise ConfigurationError(f"Policy {name} must be within (0, 100].")

    if type(policy.max_open_positions) is not int or policy.max_open_positions < 1:
        raise ConfigurationError("Policy max_open_positions must be at least 1.")
    if policy.minimum_reward_risk <= 0:
        raise ConfigurationError("Policy minimum_reward_risk must be positive.")
    if policy.minimum_price <= 0:
        raise ConfigurationError("Policy minimum_price must be positive.")
    if policy.max_single_position_pct > policy.max_total_exposure_pct:
        raise ConfigurationError(
            "Policy max_single_position_pct cannot exceed " "max_total_exposure_pct."
        )
    if type(policy.long_only) is not bool or not policy.long_only:
        raise ConfigurationError(
            "The v4.0 paper execution adapter requires long_only=True."
        )


def _validate_broker_mode(configuration: PlatformConfiguration) -> None:
    if not isinstance(configuration.broker_mode, BrokerMode):
        raise ConfigurationError("broker_mode must be a supported BrokerMode.")
    if not isinstance(configuration.credentials, CredentialStatus):
        raise ConfigurationError("credentials must be a CredentialStatus instance.")
    for name in ("alpaca_api_key_present", "alpaca_secret_key_present"):
        if type(getattr(configuration.credentials, name)) is not bool:
            raise ConfigurationError(f"Credential status {name!r} must be boolean.")

    if configuration.broker_mode is BrokerMode.ALPACA_PAPER and not (
        configuration.credentials.alpaca_api_key_present
        and configuration.credentials.alpaca_secret_key_present
    ):
        raise ConfigurationError(
            "Alpaca Paper requires both ALPACA_API_KEY and "
            "ALPACA_SECRET_KEY before startup."
        )


def _validate_scanner_mode(configuration: PlatformConfiguration) -> None:
    if not isinstance(configuration.scanner_execution_mode, ScannerExecutionMode):
        raise ConfigurationError(
            "scanner_execution_mode must be a supported ScannerExecutionMode."
        )
    expected = (
        ScannerExecutionMode.SUPERVISED
        if configuration.feature_flags.scanner
        else ScannerExecutionMode.LEGACY_ROLLBACK
    )
    if configuration.scanner_execution_mode is not expected:
        raise ConfigurationError(
            "Scanner execution mode conflicts with USE_DETERMINISTIC_SCANNER."
        )
