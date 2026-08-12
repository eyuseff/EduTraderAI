.PHONY: benchmark coverage verify

verify:
	python3 scripts/verify_release.py --coverage

coverage:
	python3 -m coverage erase
	python3 -m coverage run -m pytest -q
	python3 -m coverage report

benchmark:
	python3 scripts/benchmark_release.py
