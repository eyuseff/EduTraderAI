#!/usr/bin/env python3
"""Run the read-only Global Rotation daily scanner and write audit artifacts."""

from __future__ import annotations

import argparse
import csv
from decimal import Decimal
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from global_rotation.daily import DailyGlobalRotationService  # noqa: E402
from global_rotation.data import YFinanceDailyHistoryProvider  # noqa: E402
from global_rotation.reporting import (  # noqa: E402
    candidate_rows,
    data_issue_rows,
    run_payload,
)
from global_rotation.risk import PaperPortfolioContext  # noqa: E402
from global_rotation.universe import load_universe  # noqa: E402


def _portfolio(path: Path) -> PaperPortfolioContext:
    payload = json.loads(path.read_text(encoding="utf-8"))
    required = {
        "equity_usd",
        "buying_power_usd",
        "current_exposure_usd",
        "realized_loss_today_usd",
        "open_symbols",
        "qualification_phase",
    }
    missing = sorted(required.difference(payload))
    if missing:
        raise ValueError(f"Portfolio snapshot is missing: {', '.join(missing)}.")
    if not isinstance(payload["qualification_phase"], bool):
        raise ValueError("qualification_phase must be true or false.")
    if not isinstance(payload["open_symbols"], list):
        raise ValueError("open_symbols must be a JSON array.")
    return PaperPortfolioContext(
        equity_usd=Decimal(str(payload["equity_usd"])),
        buying_power_usd=Decimal(str(payload["buying_power_usd"])),
        current_exposure_usd=Decimal(str(payload["current_exposure_usd"])),
        realized_loss_today_usd=Decimal(str(payload["realized_loss_today_usd"])),
        open_symbols=tuple(str(item) for item in payload["open_symbols"]),
        qualification_phase=payload["qualification_phase"],
    )


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a read-only EduTrader + Volcanes global Paper screen."
    )
    parser.add_argument(
        "--universe",
        type=Path,
        default=ROOT / "data/global_rotation_universe_starter_v1.json",
    )
    parser.add_argument(
        "--portfolio-json",
        type=Path,
        required=True,
        help="Required broker-truth Paper portfolio snapshot; no defaults are invented.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "build/global_rotation",
    )
    parser.add_argument("--provider-cap", type=int, default=500)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    universe = load_universe(args.universe)
    portfolio = _portfolio(args.portfolio_json)
    service = DailyGlobalRotationService(
        YFinanceDailyHistoryProvider(maximum_symbols=args.provider_cap)
    )
    run = service.run(universe=universe, portfolio=portfolio)
    output = args.output_dir / run.run_id
    output.mkdir(parents=True, exist_ok=True)
    (output / "summary.json").write_text(
        json.dumps(run_payload(run), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    _write_csv(output / "candidates.csv", candidate_rows(run))
    _write_csv(output / "data_quality.csv", data_issue_rows(run))
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
