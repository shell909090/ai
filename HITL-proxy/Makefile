.PHONY: fmt lint unittest build smoketest test run clean

IMAGE ?= hitl-proxy:latest

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

docker-build:
	docker build -t $(IMAGE) .

run: docker-build
	docker run --rm \
		--env-file .env \
		-p 8080:8080 \
		-v $(PWD)/config.yaml:/app/config.yaml:ro \
		-v $(PWD)/data:/app/data \
		$(IMAGE)

clean:
	rm -rf bin/
