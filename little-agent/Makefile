.PHONY: fmt lint build unittest test clean ts-deps install dev run

_STATIC := little_agent/frontends/static

fmt:
	uv run ruff format little_agent tests
	cd $(_STATIC) && npx prettier --write 'src/**/*.ts'

lint:
	uv run ruff check little_agent tests
	uv run mypy little_agent --strict
	cd $(_STATIC) && npx eslint 'src/**/*.ts' && npx tsc --noEmit

build:
	find little_agent -name '*.py' | xargs uv run python -m py_compile
	cd $(_STATIC) && npx esbuild src/app.ts --bundle --format=iife \
	    --outfile=app.js --target=es2020

unittest:
	uv run pytest tests/ -v
	cd $(_STATIC) && npx vitest run

test:
	uv run pytest tests/ --cov=little_agent --cov-report=term-missing
	cd $(_STATIC) && npx vitest run

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
