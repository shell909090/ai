.PHONY: lint test scan complexity mccabe cognitive security clean

lint:
	uv run --no-env-file ruff check .

test:
	uv run --no-env-file python -m unittest discover -s tests -v

scan: complexity security

complexity: mccabe cognitive

mccabe:
	uv run --locked --no-env-file ruff check --select C901 --ignore-noqa --no-fix .

cognitive:
	uv run --locked --no-env-file python scripts/check_cognitive_complexity.py .

security:
	uv lock --check
	trivy filesystem --scanners vuln --include-dev-deps --exit-code 1 \
		--skip-dirs .venv --skip-dirs .git --skip-dirs .cache \
		--skip-dirs .ruff_cache --skip-dirs __pycache__ --skip-dirs tests/__pycache__ \
		--skip-dirs scripts/__pycache__ --ignorefile /dev/null --disable-telemetry .

clean:
	rm -rf __pycache__ tests/__pycache__ scripts/__pycache__ .ruff_cache
