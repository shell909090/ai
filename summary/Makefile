.PHONY: lint test

lint:
	uv run --no-env-file ruff check .

test:
	uv run --no-env-file python -m unittest discover -s tests -v
