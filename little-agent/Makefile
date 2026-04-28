.PHONY: fmt lint build unittest test install dev

fmt:
	uv run ruff format little_agent tests

lint:
	uv run ruff check little_agent tests
	uv run mypy little_agent --strict

build:
	uv run python -m py_compile little_agent/types.py
	uv run python -m py_compile little_agent/agent/core.py
	uv run python -m py_compile little_agent/backends/openai.py
	uv run python -m py_compile little_agent/frontends/cli.py
	uv run python -m py_compile little_agent/tools/manager.py
	uv run python -m py_compile little_agent/main.py

unittest:
	uv run pytest tests/ -v

test: unittest
	uv run pytest tests/ --cov=little_agent --cov-report=term-missing

install:
	uv sync

dev:
	uv sync --extra dev
