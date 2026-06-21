// Package kanban is the long-running scheduler library. The cmd/kanband
// binary is a thin wrapper around it. See design.md §6 for the
// interfaces exposed here.
package kanban

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"sync"
	"time"
)

// sessionInfo is the per-card state held in cardSessions.
type sessionInfo struct {
	cardID    string
	cardName  string
	sessionID string
	project   string
	status    string
	startedAt time.Time
	// summaryStartedAt is set when the scheduler sends the
	// post-completion summary prompt. Used to enforce the timeout in
	// §7.7 of design.md.
	summaryStartedAt time.Time
	// lastFinish remembers the finish value of the first final
	// assistant message so MarkCardFinished can decide whether to
	// escalate to needs-attention based on the work's actual
	// outcome, not on the summary response's outcome. The summary
	// round's abnormal finish (error / length) is informational
	// only — the work is already done at that point.
	lastFinish string
}

// Status values for sessionInfo.status.
const (
	statusStarted     = "started"
	statusSummarizing = "summarizing"
	statusCompleted   = "completed"
)

// Trello HTTP API shapes we consume.
type trelloCard struct {
	ID     string        `json:"id"`
	Name   string        `json:"name"`
	Desc   string        `json:"desc"`
	IDList string        `json:"idList"`
	URL    string        `json:"url"`
	Labels []trelloLabel `json:"labels"`
}

type trelloLabel struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	Color   string `json:"color"`
	IDBoard string `json:"idBoard"`
}

// Opencode HTTP API shape for POST /session.
type ocSession struct {
	ID        string `json:"id"`
	Slug      string `json:"slug"`
	Directory string `json:"directory"`
	ProjectID string `json:"projectID"`
}

// logRec is the JSON shape of every line the server writes to its log
// writer.
type logRec struct {
	Time   string `json:"time"`
	Event  string `json:"event"`
	Detail string `json:"detail,omitempty"`
}

// Board + list IDs from the active Trello board. Constants in one place
// so tests and production share them.
const (
	boardID  = "6a369a37d68f530666bce32e"
	iceboxID = "6a36a461229793dd1a9e8d28"
	todoID   = "6a36a462ff3d43852d8c4ad4"
	doingID  = "6a36a4625fe4a561ecc34bc6"
	doneID   = "6a36a4630e0cee0f90d16394"
)

// Server is the kanban scheduler. One Server per process; it owns the
// Trello poll loop, the opencode session registry, the finish watcher,
// and the HTTP /health endpoint. State is in-memory; restart loses
// in-flight session mappings.
type Server struct {
	cfg          Config
	mu           sync.Mutex
	cardSessions map[string]*sessionInfo
	sessionCards map[string]string
	labels       map[string]string
	httpc        *http.Client
}

// New constructs a Server. It does not start any background goroutines;
// call Run for that. New validates only the workdir; deeper checks
// (Trello credentials, opencode reachability) happen in the first poll
// cycle and are logged.
func New(cfg Config) (*Server, error) {
	if cfg.WorkDir == "" {
		return nil, errors.New("workdir is required")
	}
	if cfg.PollInterval <= 0 {
		cfg.PollInterval = 5 * time.Second
	}
	if cfg.IdleInterval <= 0 {
		cfg.IdleInterval = 10 * time.Second
	}
	if cfg.HTTPTimeout <= 0 {
		cfg.HTTPTimeout = 15 * time.Second
	}
	if cfg.HTTPListen == "" {
		cfg.HTTPListen = "127.0.0.1:8087"
	}
	if cfg.MaxDoingTotal <= 0 {
		cfg.MaxDoingTotal = 2
	}
	if cfg.MaxDoingPerProject <= 0 {
		cfg.MaxDoingPerProject = 1
	}
	return &Server{
		cfg:          cfg,
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       make(map[string]string),
		httpc:        &http.Client{Timeout: cfg.HTTPTimeout},
	}, nil
}

// Run starts the HTTP server, finish watcher and poll ticker and blocks
// until ctx is cancelled or one of the long-running components returns
// a non-Shutdown error. The first error is returned; a clean shutdown
// (ctx cancel) returns nil.
func (s *Server) Run(ctx context.Context) error {
	httpErrCh := make(chan error, 1)
	go func() {
		httpErrCh <- s.serveHTTP(ctx)
	}()

	go s.runFinishWatcher(ctx)

	ticker := time.NewTicker(s.cfg.PollInterval)
	defer ticker.Stop()

	s.pollOnce(ctx)

	for {
		select {
		case <-ctx.Done():
			return nil
		case err := <-httpErrCh:
			if err != nil && !errors.Is(err, http.ErrServerClosed) {
				return fmt.Errorf("http: %w", err)
			}
			return nil
		case <-ticker.C:
			s.pollOnce(ctx)
		}
	}
}

// HTTPHandler returns the HTTP handler for /health. Exposed for tests
// that want to drive the handler without going through Run.
func (s *Server) HTTPHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	return mux
}
