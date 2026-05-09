.PHONY: fmt lint build unittest test install dev run

fmt:
	uv run ruff format little_agent tests

lint:
	uv run ruff check little_agent tests
	uv run mypy little_agent --strict

build:
	find little_agent -name '*.py' | xargs uv run python -m py_compile

unittest:
	uv run pytest tests/ -v

test: unittest
	uv run pytest tests/ --cov=little_agent --cov-report=term-missing

install:
	uv sync

dev:
	uv sync --extra dev

run:
	uv run python -m little_agent.main --config .config.yaml
