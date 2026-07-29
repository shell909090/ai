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

// Task tracks an in-flight agent session paired with a board card.
type Task struct {
	CardID    CardID
	CardTitle string // snapshot for hook env vars
	CardURL   string // snapshot for hook env vars
	SessionID string // "__pending__" during session_new hook execution
	Proj      string
	Agent     string     // agent config name selected for this task
	Workdir   string     // resolved after session_new hook; used for session creation and proj inference
	Labels    []string   // card label names captured at start; passed to later driver prompts
	Abort     *time.Time // set when abort was requested
	Summary   *time.Time // set when summary prompt was sent
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
// board poll loop, the agent session registry, and the HTTP /health
// endpoint. State is in-memory; restart loses in-flight session mappings.
type Server struct {
	cfg        Config
	mu         sync.Mutex
	tasks      map[CardID]*Task
	totalCount int
	projCount  map[string]int
	board      BoardGateway
	httpc      *http.Client // used by opencode driver tests; nil after full integration
	hookRunner HookRunner
	drivers    map[string]AgentDriver // agent name → driver
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
	httpc := &http.Client{Timeout: cfg.HTTPTimeout}
	return &Server{
		cfg:       cfg,
		tasks:     make(map[CardID]*Task),
		projCount: make(map[string]int),
		board:     NewTrelloGateway(cfg, httpc),
		httpc:     httpc,
		drivers:   make(map[string]AgentDriver),
		hookRunner: realHookRunner{
			defaultTimeout: cfg.HookDefaultTimeout,
			maxOutputBytes: cfg.HookMaxOutputBytes,
		},
	}, nil
}

// SetDrivers replaces the driver registry. Used by main after BuildDrivers.
func (s *Server) SetDrivers(drivers map[string]AgentDriver) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.drivers = drivers
}

// SetBoard replaces the board gateway. Used in tests to inject a fake.
func (s *Server) SetBoard(b BoardGateway) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.board = b
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

// HTTPHandler returns the HTTP handler for /health and, when ControlToken is set,
// the Control API at /control/v1/*.
func (s *Server) HTTPHandler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	if s.cfg.ControlToken != "" {
		s.registerControlRoutes(mux)
	}
	return mux
}

// hasLabel reports whether a card has a label with the given name.
func hasLabel(card CardSnapshot, name string) bool {
	if name == "" {
		return false
	}
	for _, l := range card.Labels {
		if l == name {
			return true
		}
	}
	return false
}

// destroyTask removes a task and decrements capacity counters.
// Counters are guarded to never go negative.
func (s *Server) destroyTask(cardID CardID) {
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
