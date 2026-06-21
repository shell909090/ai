GO ?= go
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

smoke: build
	python3 scripts/connectivity-test.py

test: unittest smoke

serve: build
	./$(BIN)/kanband

clean:
	rm -rf $(BIN)/
