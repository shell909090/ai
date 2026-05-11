.PHONY: fmt lint lint-py build frontend package-static unittest test clean ts-deps install dev run coverage-warn

FRONTEND := frontend
_STATIC := little_agent/_static

fmt:
	uv run ruff format little_agent tests
	cd $(FRONTEND) && npx prettier --write 'src/**/*.ts'

lint: lint-py
	cd $(FRONTEND) && npx eslint 'src/**/*.ts' && npx tsc --noEmit

lint-py:
	uv run ruff check little_agent tests
	uv run mypy little_agent --strict

frontend:
	cd $(FRONTEND) && npm ci && npm run build

package-static: frontend
	rm -rf $(_STATIC)
	mkdir -p $(_STATIC)
	cp -r $(FRONTEND)/dist/. $(_STATIC)/

build: package-static
	find little_agent -name '*.py' | xargs uv run python -m py_compile

unittest:
	uv run pytest tests/ -v
	cd $(FRONTEND) && npx vitest run

test:
	uv run pytest tests/ --cov=little_agent --cov-report=term-missing
	@$(MAKE) coverage-warn --no-print-directory || true
	cd $(FRONTEND) && npx vitest run

coverage-warn:
	@uv run coverage report 2>/dev/null | awk 'NR>2 && $$NF ~ /^[0-9]+%$$/ { \
	    pct=$$NF+0; if (pct < 50) print "WARNING: coverage below 50% in " $$1 ": " $$NF \
	}' || true

ts-deps:
	cd $(FRONTEND) && npm ci

clean:
	find little_agent -name '*.pyc' -delete
	find little_agent -name '__pycache__' -type d -exec rm -rf {} +
	rm -rf $(FRONTEND)/dist/
	rm -rf $(FRONTEND)/node_modules/
	rm -rf $(_STATIC)/
	rm -rf dist/ build/ *.egg-info/
	rm -f .coverage
	rm -rf htmlcov/ .pytest_cache/ .ruff_cache/

install:
	uv sync
	cd $(FRONTEND) && npm install

dev:
	uv sync --extra dev
	cd $(FRONTEND) && npm install

run: build
	uv run python -m little_agent.main --config ~/.config/little_agent/config.yaml
