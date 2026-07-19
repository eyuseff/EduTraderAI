from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class VolcanesConfig:
    """Central configuration for the Volcanes engine."""

    project_root: Path = Path(__file__).resolve().parent.parent
    database_name: str = "volcanes.db"
    paper_trading_only: bool = True

    @property
    def database_path(self) -> Path:
        return self.project_root / self.database_name


config = VolcanesConfig()
