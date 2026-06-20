GO ?= go
BIN ?= bin

.PHONY: all fmt lint build unittest connect test clean

all: fmt lint build test

fmt:
	$(GO) fmt ./...

lint:
	$(GO) vet ./...

build:
	mkdir -p $(BIN)
	$(GO) build -o $(BIN)/kanban ./cmd/kanban
	$(GO) build -o $(BIN)/kanban-connectivity ./cmd/connectivity

unittest:
	$(GO) test ./...

connect: build
	./$(BIN)/kanban-connectivity

test: unittest connect

clean:
	rm -rf $(BIN)/
