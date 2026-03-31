FROM golang:1.23-alpine AS builder

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN go build -o /bin/hitl-proxy ./cmd/hitl-proxy

FROM alpine:3.20

RUN apk add --no-cache ca-certificates

WORKDIR /app
COPY --from=builder /bin/hitl-proxy /app/hitl-proxy
COPY static/ /app/static/

EXPOSE 8080

ENTRYPOINT ["/app/hitl-proxy"]
CMD ["--config", "/app/config.yaml"]
