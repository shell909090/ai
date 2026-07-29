GO ?= go
PYTHON ?= python3
BIN ?= bin

.PHONY: all fmt lint build unittest smoke test serve clean

all: fmt lint build test

fmt:
	$(GO) fmt ./...

lint:
	$(GO) vet ./...

build:
	mkdir -p $(BIN)
	$(GO) build -o $(BIN)/kanband ./cmd/kanband

unittest:
	$(GO) test ./...
	$(PYTHON) -m unittest scripts/kanbanctl_test.py

smoke: build
	python3 scripts/connectivity-test.py

test: unittest smoke

serve: build
	./$(BIN)/kanband

clean:
	rm -rf $(BIN)/
