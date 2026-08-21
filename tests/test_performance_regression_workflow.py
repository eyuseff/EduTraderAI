from pathlib import Path


WORKFLOW_PATH = Path(".github/workflows/benchmark-noise-study.yml")


def _step(source: str, name: str, next_name: str) -> str:
    return source.split(f"- name: {name}", maxsplit=1)[1].split(
        f"- name: {next_name}", maxsplit=1
    )[0]


def test_performance_gate_primes_candidate_and_base_symmetrically() -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")

    candidate_prime = _step(
        source,
        "Prime candidate runner before recorded samples",
        "Run candidate benchmark noise study",
    )
    base_prime = _step(
        source,
        "Prime base runner before recorded samples",
        "Run base benchmark noise study",
    )

    assert "python scripts/benchmark_noise_study.py" in candidate_prime
    assert "python _benchmark_base/scripts/benchmark_noise_study.py" in base_prime
    for step in (candidate_prime, base_prime):
        assert "--repeats 3" in step
        assert "--iterations 300" in step
        assert "--warmup 30" in step
        assert "|| true" not in step
        assert "continue-on-error" not in step

    assert source.index("Prime candidate runner before recorded samples") < source.index(
        "Run candidate benchmark noise study"
    )
    assert source.index("Check out exact pull-request base") < source.index(
        "Prime base runner before recorded samples"
    ) < source.index("Run base benchmark noise study")


def test_performance_gate_keeps_prime_evidence_separate_from_recorded_samples() -> None:
    source = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "--output build/benchmark_candidate_prime.json" in source
    assert "--output build/benchmark_reference_prime.json" in source
    assert "--output build/benchmark_candidate.json" in source
    assert "--output build/benchmark_reference.json" in source
    assert "--reference build/benchmark_reference.json" in source
    assert "--candidate build/benchmark_candidate.json" in source
    assert "build/benchmark_candidate_prime.json" in source
    assert "build/benchmark_reference_prime.json" in source
