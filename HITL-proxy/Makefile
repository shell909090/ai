.PHONY: fmt lint test build clean

fmt:
	gofmt -w .
	goimports -w .

lint:
	golangci-lint run ./...

test:
	go test ./...

build: build-proxy build-bridge

build-proxy:
	go build -o bin/hitl-proxy ./cmd/hitl-proxy

build-bridge:
	go build -o bin/hitl-bridge ./cmd/hitl-bridge

clean:
	rm -rf bin/
