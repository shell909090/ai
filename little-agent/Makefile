.PHONY: fmt lint lint-py build frontend package-static unittest test clean ts-deps install dev run coverage-warn ts-coverage ts-coverage-warn ci-test

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

# Diagnostic-wrapped ts-coverage. Probabilistic OOM has been observed
# (see docs/log.md F-1). Each run appends timestamp + mem snapshots + a
# 2-second polling memory time series to $(FRONTEND)/coverage-debug.log
# so that if the system hangs, after reboot we can read the file to see:
#   - when the last run started
#   - what memory state was at that moment
#   - how memory evolved up to the hang (time series stops at crash)
TS_COVERAGE_LOG := $(FRONTEND)/coverage-debug.log

ts-coverage:
	@{ echo "=== $$(date -Iseconds) START ==="; \
	   echo "[before] $$(free -m | grep '^Mem:' | tr -s ' ')"; \
	} >> $(TS_COVERAGE_LOG)
	-@LOG="$$(pwd)/$(TS_COVERAGE_LOG)"; \
	 ( while true; do \
	     printf '[poll %s] %s\n' "$$(date -Iseconds)" "$$(free -m | grep '^Mem:' | tr -s ' ')" >> "$$LOG"; \
	     sleep 2; \
	   done ) & POLLER=$$!; \
	 ( cd $(FRONTEND) && npx vitest run --coverage 2>&1 | tee -a coverage-debug.log ); \
	 kill $$POLLER 2>/dev/null; wait $$POLLER 2>/dev/null; true
	@{ echo "[after]  $$(free -m | grep '^Mem:' | tr -s ' ')"; \
	   echo "=== $$(date -Iseconds) END ==="; echo ""; \
	} >> $(TS_COVERAGE_LOG)
	@$(MAKE) ts-coverage-warn --no-print-directory || true

ts-coverage-warn:
	@node -e " \
	  try { \
	    var r = require('./$(FRONTEND)/coverage/coverage-summary.json'); \
	    var p = r.total.lines.pct; \
	    if (p < 50) process.stdout.write('WARNING: TypeScript coverage below 50%: ' + p + '%\n'); \
	  } catch (e) {} \
	" 2>/dev/null || true

ci-test:
	uv run pytest tests/test_ci.py -v

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
