package kanban

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
)

// defaultLogWriter is the writer Server.log writes to. Tests can
// override by reassigning; production callers (cmd/kanband) use
// SetLogWriter when a -log file is requested.
var defaultLogWriter io.Writer = os.Stderr

// SetLogWriter swaps the global log writer. Not safe to call from
// multiple goroutines concurrently with log lines; intended to be
// called once during process startup.
func SetLogWriter(w io.Writer) { defaultLogWriter = w }

func (s *Server) log(event, detail string) {
	rec := logRec{Time: time.Now().Format(time.RFC3339), Event: event, Detail: detail}
	_ = json.NewEncoder(defaultLogWriter).Encode(rec)
}

// stderr returns the log writer for one-shot log calls; tests can swap
// the package-level defaultLogWriter to capture output.
func (s *Server) stderr() io.Writer { return defaultLogWriter }

func (s *Server) serveHTTP(ctx context.Context) error {
	srv := &http.Server{Addr: s.cfg.HTTPListen, Handler: s.HTTPHandler()}
	go func() {
		<-ctx.Done()
		shutCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutCtx)
	}()
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		return fmt.Errorf("http: %w", err)
	}
	return nil
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}
