"""Deterministic, paper-only global rotation research core."""

from global_rotation.daily import DailyGlobalRotationRun, DailyGlobalRotationService
from global_rotation.data import (
    DailyHistoryBatch,
    DataQualityIssue,
    YFinanceDailyHistoryProvider,
)
from global_rotation.engine import GlobalRotationEngine
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
    PaperSizeResult,
    blocked_paper_preview,
    size_paper_position,
)
from global_rotation.universe import (
    UniverseRegion,
    UniverseSecurity,
    UniverseSnapshot,
    load_universe,
    parse_universe,
)

__all__ = [
    "DailyGlobalRotationRun",
    "DailyGlobalRotationService",
    "DailyHistoryBatch",
    "DataQualityIssue",
    "GlobalInstrument",
    "GlobalRotationCandidate",
    "GlobalRotationEngine",
    "GlobalRotationResult",
    "PaperPortfolioContext",
    "PaperRiskPolicy",
    "PaperSizeResult",
    "RegionConfig",
    "RotationPolicy",
    "ScanRejection",
    "UniverseRegion",
    "UniverseSecurity",
    "UniverseSnapshot",
    "YFinanceDailyHistoryProvider",
    "blocked_paper_preview",
    "load_universe",
    "parse_universe",
    "size_paper_position",
]
