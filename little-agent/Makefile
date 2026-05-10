.PHONY: fmt lint build clean unittest test install dev run

fmt:
	uv run ruff format little_agent tests

lint:
	uv run ruff check little_agent tests
	uv run mypy little_agent --strict

build:
	find little_agent -name '*.py' | xargs uv run python -m py_compile
	cd little_agent/frontends/static && npx tsc --project tsconfig.json

clean:
	find little_agent -name '*.pyc' -delete
	find little_agent -name '__pycache__' -type d -exec rm -rf {} +
	rm -f little_agent/frontends/static/app.js

unittest:
	uv run pytest tests/ -v

test: unittest
	uv run pytest tests/ --cov=little_agent --cov-report=term-missing

install:
	uv sync

dev:
	uv sync --extra dev

run: build
	uv run python -m little_agent.main --config ~/.config/little_agent/config.yaml
