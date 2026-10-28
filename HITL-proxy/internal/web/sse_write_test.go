package web

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/shell909090/ai/HITL-proxy/internal/approval"
)

type failedSSEWriter struct {
	header  http.Header
	writes  int
	flushes int
}

func (w *failedSSEWriter) Header() http.Header { return w.header }
func (w *failedSSEWriter) WriteHeader(int)     {}
func (w *failedSSEWriter) Write([]byte) (int, error) {
	w.writes++
	return 0, errors.New("client disconnected")
}
func (w *failedSSEWriter) Flush() { w.flushes++ }

func TestSSEStopsAfterWriteFailure(t *testing.T) {
	hub := approval.NewSSEHub()
	handler := &Handler{hub: hub}
	writer := &failedSSEWriter{header: make(http.Header)}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	request := httptest.NewRequest(http.MethodGet, "/events", nil).WithContext(ctx)
	done := make(chan struct{})
	go func() {
		defer close(done)
		handler.handleSSE(writer, request)
	}()
	// Broadcast until the handler has subscribed; no production hooks are needed.
	ticker := time.NewTicker(time.Millisecond)
	defer ticker.Stop()
	deadline := time.NewTimer(time.Second)
	defer deadline.Stop()
	for {
		select {
		case <-done:
			if writer.writes != 1 || writer.flushes != 0 {
				t.Fatalf("writes=%d flushes=%d; want one failed write and no flush", writer.writes, writer.flushes)
			}
			return
		case <-ticker.C:
			hub.Broadcast(approval.SSEEvent{Type: "new_request", ID: 1})
		case <-deadline.C:
			cancel()
			<-done
			t.Fatal("SSE handler did not return after write failure")
		}
	}
}
