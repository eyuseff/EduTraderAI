"""Deterministic, paper-only global rotation research core."""

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

__all__ = [
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
    "blocked_paper_preview",
    "size_paper_position",
]
