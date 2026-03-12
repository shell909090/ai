.PHONY: fmt lint unittest build smoketest test clean

fmt:
	gofmt -w .
	goimports -w .

lint:
	golangci-lint run ./...
	cd cmd/hitl-bridge && uv run ruff check .

unittest:
	go test ./...
	cd cmd/hitl-bridge && uv run pytest test_hitl_bridge.py

build: unittest build-proxy build-bridge

build-proxy:
	go build -o bin/hitl-proxy ./cmd/hitl-proxy

build-bridge:
	cd cmd/hitl-bridge && uv sync

smoketest: build-proxy
	cd cmd/hitl-bridge && uv run pytest test_smoke.py

test: build smoketest

clean:
	rm -rf bin/
