UV_CACHE_DIR = $(CURDIR)/.uv-cache
UV_RUN = UV_CACHE_DIR=$(UV_CACHE_DIR) uv run --offline

.PHONY: fmt lint build unittest test

fmt:
	ruff check --select I --fix .
	ruff format tgbot.py tests

lint:
	ruff check .

build:
	$(UV_RUN) python -m py_compile tgbot.py

unittest:
	python3 -m coverage run -m unittest discover -s tests -v

test: unittest
	python3 -m coverage report -m
