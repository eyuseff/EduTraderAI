"""Immutable startup configuration and fail-closed validation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
import re

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SQLITE_SUFFIXES = frozenset({".db", ".sqlite", ".sqlite3"})
_PROTECTED_PATH_PARTS = frozenset(
    {
        ".git",
        "build",
        "state",
        "alpaca",
        "live",
        "external-paper",
        "external_paper",
        "credentials",
        "credential",
        "secrets",
        "secret",
    }
)
_PROHIBITED_DATABASE_NAMES = frozenset({"simulated_broker.json"})
_APPLICATION_VERSION_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]{0,127}")
_PROTECTED_PATH_TOKEN_PATTERN = re.compile(
    r"(?:^|[._+-])(?:alpaca|credential|credentials|live|secret|secrets)(?:$|[._+-])"
    r"|(?:^|[._+-])external[-_+]paper(?:$|[._+-])",
    re.IGNORECASE,
)
_PROHIBITED_VERSION_TOKENS = re.compile(
    r"(?:^|[._+-])(alpaca|credential|credentials|external|live|secret|secrets)(?:$|[._+-])",
    re.IGNORECASE,
)


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
class PaperExecutionPersistenceRuntimeConfiguration:
    """Explicit local SQLite persistence runtime configuration."""

    database_path: Path
    application_version: str
    busy_timeout_ms: int


def validate_paper_execution_persistence_runtime_configuration(
    configuration: PaperExecutionPersistenceRuntimeConfiguration,
) -> PaperExecutionPersistenceRuntimeConfiguration:
    """Validate local persistence settings without changing the filesystem."""

    if not isinstance(configuration, PaperExecutionPersistenceRuntimeConfiguration):
        raise ConfigurationError(
            "configuration must be PaperExecutionPersistenceRuntimeConfiguration."
        )
    _validate_persistence_database_path(configuration.database_path)
    _validate_persistence_application_version(configuration.application_version)
    if (
        type(configuration.busy_timeout_ms) is not int
        or configuration.busy_timeout_ms <= 0
        or configuration.busy_timeout_ms > 60_000
    ):
        raise ConfigurationError("Persistence busy timeout is outside safe bounds.")
    return configuration


def _validate_persistence_database_path(database_path: Path) -> None:
    if not isinstance(database_path, Path):
        raise ConfigurationError("Persistence database path must be a Path.")
    if not database_path.is_absolute():
        raise ConfigurationError("Persistence database path must be absolute.")
    if not database_path.name:
        raise ConfigurationError("Persistence database path requires a file name.")
    if database_path.name.lower() in _PROHIBITED_DATABASE_NAMES:
        raise ConfigurationError("Persistence database name is protected.")
    if database_path.suffix.lower() not in _SQLITE_SUFFIXES:
        raise ConfigurationError("Persistence database path has an invalid suffix.")

    for candidate in (database_path, *database_path.parents):
        if candidate.exists() and candidate.is_symlink():
            raise ConfigurationError("Persistence database path cannot use symlinks.")

    resolved = database_path.resolve(strict=False)
    parent = resolved.parent
    if not parent.exists() or not parent.is_dir():
        raise ConfigurationError(
            "Persistence database parent must be an existing directory."
        )
    if resolved == _PROJECT_ROOT or resolved.is_relative_to(_PROJECT_ROOT):
        raise ConfigurationError(
            "Persistence database path cannot be inside the repository."
        )
    lowered_parts = {part.lower() for part in resolved.parts}
    if lowered_parts.intersection(_PROTECTED_PATH_PARTS) or any(
        _PROTECTED_PATH_TOKEN_PATTERN.search(part) is not None
        for part in resolved.parts
    ):
        raise ConfigurationError("Persistence database path is protected.")


def _validate_persistence_application_version(application_version: str) -> None:
    if (
        not isinstance(application_version, str)
        or _APPLICATION_VERSION_PATTERN.fullmatch(application_version) is None
        or _PROHIBITED_VERSION_TOKENS.search(application_version) is not None
    ):
        raise ConfigurationError("Persistence application version is malformed.")


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
