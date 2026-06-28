// Package kanban is the long-running scheduler library.
package kanban

import (
	"context"
	"errors"
	"fmt"
	"net/http"
	"sync"
	"time"
)

// Task tracks an in-flight opencode session paired with a Trello card.
type Task struct {
	CardID    string
	CardTitle string // snapshot for hook env vars
	CardURL   string // snapshot for hook env vars
	SessionID string // "__pending__" during session_new hook execution
	Proj      string
	Model     ModelRef
	Workdir   string     // resolved after session_new hook; used for session creation and proj inference
	Abort     *time.Time // set when abort was requested
	Summary   *time.Time // set when summary prompt was sent
}

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

// ocSession is the response from POST /session.
type ocSession struct {
	ID        string `json:"id"`
	Slug      string `json:"slug"`
	Directory string `json:"directory"`
	ProjectID string `json:"projectID"`
}

// logRec is the JSON shape written to the log writer.
type logRec struct {
	Time   string `json:"time"`
	Event  string `json:"event"`
	Detail string `json:"detail,omitempty"`
}

// Server is the kanban scheduler. One Server per process; it owns the
// Trello poll loop, the opencode session registry, and the HTTP /health
// endpoint. State is in-memory; restart loses in-flight session mappings.
type Server struct {
	cfg        Config
	mu         sync.Mutex
	tasks      map[string]*Task // keyed by card_id
	totalCount int
	projCount  map[string]int
	labelIDs   map[string]string // Trello label name → Trello label ID (cached)
	httpc      *http.Client
	hookRunner HookRunner // injectable; defaults to realHookRunner in New()
}

// New constructs a Server. It does not start any background goroutines;
// call Run for that.
func New(cfg Config) (*Server, error) {
	if cfg.PollInterval <= 0 {
		cfg.PollInterval = 5 * time.Second
	}
	if cfg.HTTPTimeout <= 0 {
		cfg.HTTPTimeout = 15 * time.Second
	}
	if cfg.HTTPListen == "" {
		cfg.HTTPListen = "127.0.0.1:8087"
	}
	if cfg.MaxDoingTotal <= 0 {
		cfg.MaxDoingTotal = 3
	}
	if cfg.MaxDoingPerProject <= 0 {
		cfg.MaxDoingPerProject = 1
	}
	if cfg.AbortTimeout <= 0 {
		cfg.AbortTimeout = 60 * time.Second
	}
	if cfg.SummaryTimeout <= 0 {
		cfg.SummaryTimeout = 60 * time.Second
	}
	if cfg.HookDefaultTimeout <= 0 {
		cfg.HookDefaultTimeout = 120 * time.Second
	}
	if cfg.HookMaxOutputBytes <= 0 {
		cfg.HookMaxOutputBytes = 8192
	}
	return &Server{
		cfg:       cfg,
		tasks:     make(map[string]*Task),
		projCount: make(map[string]int),
		labelIDs:  make(map[string]string),
		httpc:     &http.Client{Timeout: cfg.HTTPTimeout},
		hookRunner: realHookRunner{
			defaultTimeout: cfg.HookDefaultTimeout,
			maxOutputBytes: cfg.HookMaxOutputBytes,
		},
	}, nil
}

// Run starts the HTTP server and the single timer loop, blocking until
// ctx is cancelled or the HTTP server returns a non-shutdown error.
func (s *Server) Run(ctx context.Context) error {
	httpErrCh := make(chan error, 1)
	go func() {
		httpErrCh <- s.serveHTTP(ctx)
	}()

	ticker := time.NewTicker(s.cfg.PollInterval)
	defer ticker.Stop()

	s.tick(ctx, time.Now())

	for {
		select {
		case <-ctx.Done():
			return nil
		case err := <-httpErrCh:
			if err != nil && !errors.Is(err, http.ErrServerClosed) {
				return fmt.Errorf("http: %w", err)
			}
			return nil
		case now := <-ticker.C:
			s.tick(ctx, now)
		}
	}
}

// HTTPHandler returns the HTTP handler for /health.
func (s *Server) HTTPHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	return mux
}

// listIDFor returns the Trello list ID for a logical list name (todo/doing/done).
func (s *Server) listIDFor(name string) string {
	return s.cfg.TrelloLists[name]
}

// labelNameFor returns the Trello label name for a logical key (human/attention).
func (s *Server) labelNameFor(key string) string {
	return s.cfg.TrelloLabels[key]
}

// hasLabel reports whether a card has a label with the given name.
func hasLabel(card trelloCard, name string) bool {
	if name == "" {
		return false
	}
	for _, l := range card.Labels {
		if l.Name == name {
			return true
		}
	}
	return false
}

// destroyTask removes a task and decrements capacity counters.
// Counters are guarded to never go negative.
func (s *Server) destroyTask(cardID string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	task, ok := s.tasks[cardID]
	if !ok {
		return
	}
	delete(s.tasks, cardID)
	s.totalCount--
	if s.totalCount < 0 {
		s.log("error.count.negative", fmt.Sprintf("totalCount went negative card=%s, resetting to 0", cardID))
		s.totalCount = 0
	}
	s.projCount[task.Proj]--
	if s.projCount[task.Proj] < 0 {
		s.log("error.count.negative", fmt.Sprintf("projCount[%s] went negative card=%s, resetting to 0", task.Proj, cardID))
		s.projCount[task.Proj] = 0
	}
}
