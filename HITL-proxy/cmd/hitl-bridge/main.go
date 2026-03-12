package main

import (
	"bufio"
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"log"
	"os"

	"github.com/mark3labs/mcp-go/client/transport"
	"github.com/mark3labs/mcp-go/mcp"
)

// hitl-bridge: stdio ↔ SSE bridge for MCP.
// Reads JSON-RPC messages from stdin, forwards to the SSE server, writes responses to stdout.
func main() {
	sseURL := flag.String("url", "http://localhost:8080/mcp/sse", "SSE endpoint URL")
	flag.Parse()

	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	sse, err := transport.NewSSE(*sseURL)
	if err != nil {
		log.Fatalf("create SSE transport: %v", err)
	}

	if err := sse.Start(ctx); err != nil {
		log.Fatalf("start SSE transport: %v", err)
	}
	defer sse.Close()

	// Forward server notifications to stdout
	sse.SetNotificationHandler(func(notification mcp.JSONRPCNotification) {
		data, err := json.Marshal(notification)
		if err != nil {
			log.Printf("marshal notification: %v", err)
			return
		}
		fmt.Fprintf(os.Stdout, "%s\n", data)
	})

	scanner := bufio.NewScanner(os.Stdin)
	scanner.Buffer(make([]byte, 0, 1024*1024), 1024*1024)

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		// Peek at the message to determine if it's a request or notification
		var peek struct {
			ID     *json.RawMessage `json:"id"`
			Method string           `json:"method"`
		}
		if err := json.Unmarshal(line, &peek); err != nil {
			log.Printf("parse message: %v", err)
			continue
		}

		if peek.ID == nil {
			// It's a notification
			var notif mcp.JSONRPCNotification
			if err := json.Unmarshal(line, &notif); err != nil {
				log.Printf("parse notification: %v", err)
				continue
			}
			if err := sse.SendNotification(ctx, notif); err != nil {
				log.Printf("send notification: %v", err)
			}
		} else {
			// It's a request
			var req transport.JSONRPCRequest
			if err := json.Unmarshal(line, &req); err != nil {
				log.Printf("parse request: %v", err)
				continue
			}

			resp, err := sse.SendRequest(ctx, req)
			if err != nil {
				log.Printf("send request: %v", err)
				continue
			}

			data, err := json.Marshal(resp)
			if err != nil {
				log.Printf("marshal response: %v", err)
				continue
			}
			fmt.Fprintf(os.Stdout, "%s\n", data)
		}
	}

	if err := scanner.Err(); err != nil {
		log.Fatalf("stdin scan: %v", err)
	}
}
