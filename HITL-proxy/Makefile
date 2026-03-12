.PHONY: fmt lint test build clean

fmt:
	gofmt -w .
	goimports -w .

lint:
	golangci-lint run ./...
	cd cmd/hitl-bridge && uv run ruff check .

test:
	go test ./...
	cd cmd/hitl-bridge && uv run pytest

build: build-proxy build-bridge

build-proxy:
	go build -o bin/hitl-proxy ./cmd/hitl-proxy

build-bridge:
	cd cmd/hitl-bridge && uv sync

clean:
	rm -rf bin/
