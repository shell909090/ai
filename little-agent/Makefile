.PHONY: fmt fmt-py fmt-ts lint lint-py lint-ts build build-py build-ts \
        unittest unittest-py unittest-ts test clean ts-deps install dev run

_STATIC := little_agent/frontends/static

# ── top-level aliases ──────────────────────────────────────────────────────
fmt: fmt-py fmt-ts
lint: lint-py lint-ts
build: build-py build-ts
unittest: unittest-py unittest-ts

# ── Python ──────────���──────────────────────────────────────────────────────
fmt-py:
	uv run ruff format little_agent tests

lint-py:
	uv run ruff check little_agent tests
	uv run mypy little_agent --strict

build-py:
	find little_agent -name '*.py' | xargs uv run python -m py_compile

unittest-py:
	uv run pytest tests/ -v

test: unittest-py
	uv run pytest tests/ --cov=little_agent --cov-report=term-missing

# ── TypeScript ──────────────────────────────────────────────────────────────
fmt-ts:
	cd $(_STATIC) && npx prettier --write 'src/**/*.ts'

lint-ts:
	cd $(_STATIC) && npx eslint 'src/**/*.ts' && npx tsc --noEmit

build-ts:
	cd $(_STATIC) && npx esbuild src/app.ts --bundle --format=iife \
	    --outfile=app.js --target=es2020

unittest-ts:
	cd $(_STATIC) && npx vitest run

ts-deps:
	cd $(_STATIC) && npm ci

# ── housekeeping ────────────────────────────────────────────────────────────
clean:
	find little_agent -name '*.pyc' -delete
	find little_agent -name '__pycache__' -type d -exec rm -rf {} +
	rm -f $(_STATIC)/app.js

install:
	uv sync
	cd $(_STATIC) && npm install

dev:
	uv sync --extra dev
	cd $(_STATIC) && npm install

run: build
	uv run python -m little_agent.main --config ~/.config/little_agent/config.yaml
