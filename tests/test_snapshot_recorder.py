from datetime import datetime, timezone
from decimal import Decimal

from volcanoes.analytics.portfolio_snapshot import PortfolioSnapshot
from volcanoes.analytics.snapshot_recorder import SnapshotRecorder


def make_snapshot(value: str) -> PortfolioSnapshot:
    equity = Decimal(value)

    return PortfolioSnapshot(
        timestamp=datetime.now(timezone.utc),
        cash=equity,
        market_value=Decimal("0"),
        equity=equity,
        realized_pnl=Decimal("0"),
        unrealized_pnl=Decimal("0"),
        open_positions=0,
    )


def test_new_recorder_is_empty():
    recorder = SnapshotRecorder()

    assert len(recorder) == 0
    assert recorder.snapshots == ()


def test_record_snapshot():
    recorder = SnapshotRecorder()

    recorder.record(make_snapshot("100"))

    assert len(recorder) == 1


def test_record_multiple_snapshots():
    recorder = SnapshotRecorder()

    recorder.record(make_snapshot("100"))
    recorder.record(make_snapshot("200"))
    recorder.record(make_snapshot("300"))

    assert len(recorder) == 3
    assert recorder.snapshots[2].equity == Decimal("300")


def test_snapshots_are_immutable():
    recorder = SnapshotRecorder()

    recorder.record(make_snapshot("100"))

    snapshots = recorder.snapshots

    assert isinstance(snapshots, tuple)


def test_clear():
    recorder = SnapshotRecorder()

    recorder.record(make_snapshot("100"))
    recorder.record(make_snapshot("200"))

    recorder.clear()

    assert len(recorder) == 0
