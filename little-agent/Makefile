.PHONY: fmt lint build unittest test install dev run docker-build docker-unittest docker-test

DOCKER_IMAGE ?= little-agent-test

fmt:
	uv run ruff format little_agent tests

lint:
	uv run ruff check little_agent tests
	uv run mypy little_agent --strict

build:
	uv run python -m py_compile little_agent/types.py
	uv run python -m py_compile little_agent/agent/context.py
	uv run python -m py_compile little_agent/agent/core.py
	uv run python -m py_compile little_agent/backends/exceptions.py
	uv run python -m py_compile little_agent/backends/openai.py
	uv run python -m py_compile little_agent/compressor.py
	uv run python -m py_compile little_agent/frontends/acp.py
	uv run python -m py_compile little_agent/frontends/cli.py
	uv run python -m py_compile little_agent/tools/bash.py
	uv run python -m py_compile little_agent/tools/manager.py
	uv run python -m py_compile little_agent/tools/task.py
	uv run python -m py_compile little_agent/main.py

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

docker-build:
	docker build -t $(DOCKER_IMAGE) .

docker-unittest: docker-build
	docker run --rm $(DOCKER_IMAGE) uv run pytest tests/ -v --timeout=60

docker-test: docker-build
	docker run --rm $(DOCKER_IMAGE) uv run pytest tests/ --cov=little_agent --cov-report=term-missing --timeout=60
