.PHONY: fmt lint build unittest test clean

fmt:
	uv run ruff format src/ tests/

lint:
	uv run ruff check src/ tests/

build:
	@find src/ -name "*.py" | xargs uv run python -m py_compile && echo "Build OK"

unittest:
	uv run pytest tests/ -v

test: unittest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .ruff_cache .pytest_cache
