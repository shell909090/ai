.PHONY: fmt lint lint-py build unittest test clean ts-deps install dev run coverage-warn

_STATIC := little_agent/frontends/static

fmt:
	uv run ruff format little_agent tests
	cd $(_STATIC) && npx prettier --write 'src/**/*.ts'

lint: lint-py
	cd $(_STATIC) && npx eslint 'src/**/*.ts' && npx tsc --noEmit

lint-py:
	uv run ruff check little_agent tests
	uv run mypy little_agent --strict

build:
	find little_agent -name '*.py' | xargs uv run python -m py_compile
	cd $(_STATIC) && npx esbuild src/app.ts --bundle --format=iife \
	    --outfile=app.js --target=es2020

unittest:
	uv run pytest tests/ -v
	cd $(_STATIC) && npx vitest run

test:
	uv run pytest tests/ --cov=little_agent --cov-report=term-missing
	@$(MAKE) coverage-warn --no-print-directory || true
	cd $(_STATIC) && npx vitest run

coverage-warn:
	@uv run coverage report 2>/dev/null | awk 'NR>2 && $$NF ~ /^[0-9]+%$$/ { \
	    pct=$$NF+0; if (pct < 50) print "WARNING: coverage below 50% in " $$1 ": " $$NF \
	}' || true

ts-deps:
	cd $(_STATIC) && npm ci

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
