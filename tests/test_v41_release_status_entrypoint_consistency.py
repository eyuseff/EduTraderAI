from pathlib import Path


README_PATH = Path("README.md")
PLAN_PATH = Path("docs/operations/V41_STABLE_PROMOTION_PLAN.md")
LOG_PATH = Path("docs/operations/V41_RELEASE_OBSERVATION_LOG.md")


def _table_rows(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) != 2 or cells[0] in {"Item", "---"}:
            continue
        rows[cells[0]] = cells[1]
    return rows


def test_root_readme_release_status_matches_authoritative_v41_records() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    plan = _table_rows(PLAN_PATH)
    log = _table_rows(LOG_PATH)

    assert f"- Release candidate: {plan['Release candidate']}" in readme
    assert f"- RC commit: {plan['RC commit']}" in readme
    assert f"- RC published: {plan['RC published UTC']}" in readme
    assert f"- Earliest Stable review: {plan['Earliest Stable review']}" in readme
    assert f"- Stable observation gate: tracked in issue {log['Tracking issue']}" in readme
    assert f"- Current recommendation: {log['Recommendation']}" in readme

    assert log["Recommendation"] == plan["Recommendation"]
