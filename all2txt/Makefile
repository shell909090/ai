.PHONY: fmt lint build unittest test

fmt:
	uv run ruff format all2txt tests

lint:
	uv run ruff check all2txt tests

build:
	find all2txt tests -name '*.py' | xargs uv run python -m py_compile

unittest:
	uv run pytest

test: unittest
