// kanband is a long-running scheduler that polls the Trello "doing"
// list, starts an opencode session per card, and detects session
// completion by polling /session/{id}/message?limit=1 for info.finish.
//
// Per poll (default 5s):
//  1. GET /1/lists/{doingID}/cards?fields=...
//  2. For each card id not yet in cardSessions:
//     - create an opencode session in cfg.WorkDir
//     - POST "▶️ Started session <id>" comment
//     - async-send card description as the prompt (no done URL)
//
// HTTP server (default :8087) exposes:
//
//	GET  /health   liveness probe
//
// Background finish watcher (every IdleInterval, default 10s):
//   - for every registered session, GET /session/{id}/message?limit=1
//   - if info.finish is present, the model has stopped speaking for
//     this turn → trigger markCardFinished
//   - finish = error or length additionally writes a ❌ comment and
//     adds the needs-attention label
//
// There is no agent-driven completion signal: agent does not call any
// scheduler endpoint. The watcher is the single completion path; no
// per-card locks, no post-done cool-down, no done URL. See design.md
// §6.5 and §7.3.
//
// State is in-memory only. Restart loses all in-flight session
// mappings; any not-yet-completed card will be re-discovered on the
// next poll and start a fresh session.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"syscall"
	"time"
)

const (
	boardID = "6a369a37d68f530666bce32e"
	doingID = "6a36a4625fe4a561ecc34bc6"
	doneID  = "6a36a4630e0cee0f90d16394"
)

type config struct {
	TrelloKey       string
	TrelloToken     string
	OpenCodeUser    string
	OpenCodePass    string
	OpenCodeBaseURL string
	WorkDir         string
	PollInterval    time.Duration
	HTTPTimeout     time.Duration
	HTTPListen      string
	IdleInterval    time.Duration
}

type trelloCard struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Desc   string `json:"desc"`
	IDList string `json:"idList"`
	URL    string `json:"url"`
}

type trelloLabel struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	Color   string `json:"color"`
	IDBoard string `json:"idBoard"`
}

type ocSession struct {
	ID        string `json:"id"`
	Slug      string `json:"slug"`
	Directory string `json:"directory"`
	ProjectID string `json:"projectID"`
}

const (
	statusStarted   = "started"
	statusCompleted = "completed"
)

type sessionInfo struct {
	cardID    string
	cardName  string
	sessionID string
	status    string
	startedAt time.Time
}

type server struct {
	cfg          config
	mu           sync.Mutex
	cardSessions map[string]*sessionInfo // cardID -> info
	sessionCards map[string]string       // sessionID -> cardID
	labels       map[string]string       // label name -> id
	httpc        *http.Client
}

type logRec struct {
	Time   string `json:"time"`
	Event  string `json:"event"`
	Detail string `json:"detail,omitempty"`
}

func main() {
	pollStr := flag.String("poll", "5s", "poll interval (e.g. 5s, 10s)")
	idleStr := flag.String("idle", "10s", "finish-watcher interval (e.g. 5s, 30s)")
	workdir := flag.String("workdir", "", "workdir for opencode session (default $KANBAN_WORKDIR; must be absolute)")
	logPath := flag.String("log", "", "log file path (default stderr)")
	httpListen := flag.String("http", "127.0.0.1:8087", "HTTP listen address for /health")
	flag.Parse()

	cfg, err := loadConfig()
	if err != nil {
		die("config: %v", err)
	}
	cfg.HTTPListen = *httpListen
	if *workdir != "" {
		cfg.WorkDir = *workdir
	}
	if cfg.WorkDir == "" {
		die("workdir is required: pass -workdir <abs-path> or set KANBAN_WORKDIR")
	}
	abs, err := filepath.Abs(cfg.WorkDir)
	if err != nil {
		die("resolve workdir: %v", err)
	}
	if info, err := os.Stat(abs); err != nil {
		die("workdir not accessible: %v", err)
	} else if !info.IsDir() {
		die("workdir is not a directory: %s", abs)
	}
	cfg.WorkDir = abs
	d, err := time.ParseDuration(*pollStr)
	if err != nil {
		die("parse -poll: %v", err)
	}
	cfg.PollInterval = d
	di, err := time.ParseDuration(*idleStr)
	if err != nil {
		die("parse -idle: %v", err)
	}
	cfg.IdleInterval = di

	w := io.Writer(os.Stderr)
	if *logPath != "" {
		f, err := os.Create(*logPath)
		if err != nil {
			die("open log: %v", err)
		}
		w = f
		defer f.Close()
	}

	srv := &server{
		cfg:          cfg,
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       make(map[string]string),
		httpc:        &http.Client{Timeout: cfg.HTTPTimeout},
	}
	srv.log(w, "start", fmt.Sprintf("poll=%s idle=%s workdir=%s http=%s",
		cfg.PollInterval, cfg.IdleInterval, cfg.WorkDir, cfg.HTTPListen))

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()

	if err := srv.loadLabels(ctx); err != nil {
		srv.log(w, "labels.error", err.Error())
	}

	httpErrCh := make(chan error, 1)
	go func() {
		httpErrCh <- srv.serveHTTP(ctx)
	}()

	go srv.runFinishWatcher(ctx, w)

	ticker := time.NewTicker(cfg.PollInterval)
	defer ticker.Stop()

	srv.pollOnce(ctx, w)

	for {
		select {
		case <-ctx.Done():
			srv.log(w, "stop", "signal received")
			return
		case err := <-httpErrCh:
			if err != nil && !errors.Is(err, http.ErrServerClosed) {
				srv.log(w, "http.error", err.Error())
			}
			return
		case <-ticker.C:
			srv.pollOnce(ctx, w)
		}
	}
}

func (s *server) serveHTTP(ctx context.Context) error {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /health", func(w http.ResponseWriter, r *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	srv := &http.Server{Addr: s.cfg.HTTPListen, Handler: mux}
	go func() {
		<-ctx.Done()
		shutCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutCtx)
	}()
	return srv.ListenAndServe()
}

func (s *server) pollOnce(ctx context.Context, w io.Writer) {
	cards, err := s.trelloListCards(ctx, doingID)
	if err != nil {
		s.log(w, "poll.error", err.Error())
		return
	}
	s.log(w, "poll", fmt.Sprintf("doing_cards=%d", len(cards)))

	var newCards []trelloCard
	s.mu.Lock()
	for _, c := range cards {
		if _, busy := s.cardSessions[c.ID]; !busy {
			s.cardSessions[c.ID] = &sessionInfo{cardID: c.ID, cardName: c.Name, status: statusStarted}
			newCards = append(newCards, c)
		}
	}
	s.mu.Unlock()
	s.log(w, "poll.new", fmt.Sprintf("new_cards=%d", len(newCards)))

	for _, c := range newCards {
		go s.processCard(ctx, w, c)
	}
}

func (s *server) processCard(ctx context.Context, w io.Writer, card trelloCard) {
	sess, err := s.ocCreateSession(ctx)
	if err != nil {
		s.log(w, "opencode.session.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		s.mu.Lock()
		delete(s.cardSessions, card.ID)
		s.mu.Unlock()
		return
	}
	s.log(w, "opencode.session", fmt.Sprintf("card=%s session=%s", card.ID, sess.ID))

	s.mu.Lock()
	info := s.cardSessions[card.ID]
	info.sessionID = sess.ID
	s.sessionCards[sess.ID] = card.ID
	s.mu.Unlock()

	comment := fmt.Sprintf("▶️ Started session %s\nWorkspace: %s", sess.ID, sess.Directory)
	if err := s.trelloAddComment(ctx, card.ID, comment); err != nil {
		s.log(w, "trello.comment.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
	} else {
		s.log(w, "trello.comment", fmt.Sprintf("card=%s session=%s", card.ID, sess.ID))
	}

	if err := s.ocSendPromptAsync(ctx, sess.ID, card.Desc); err != nil {
		s.log(w, "opencode.prompt.fail", fmt.Sprintf("card=%s session=%s err=%v", card.ID, sess.ID, err))
		s.mu.Lock()
		delete(s.cardSessions, card.ID)
		delete(s.sessionCards, sess.ID)
		s.mu.Unlock()
		return
	}
	s.log(w, "opencode.prompt", fmt.Sprintf("card=%s session=%s body_len=%d", card.ID, sess.ID, len(card.Desc)))

	s.mu.Lock()
	info.startedAt = time.Now()
	s.mu.Unlock()
	s.log(w, "card.started", fmt.Sprintf("id=%s session=%s", card.ID, sess.ID))
}

func (s *server) log(w io.Writer, event, detail string) {
	rec := logRec{Time: time.Now().Format(time.RFC3339), Event: event, Detail: detail}
	_ = json.NewEncoder(w).Encode(rec)
}

func writeJSON(w http.ResponseWriter, status int, body any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func loadConfig() (config, error) {
	c := config{
		OpenCodeBaseURL: envOr("KANBAN_OPENCODE_URL", "http://127.0.0.1:4096"),
		WorkDir:         os.Getenv("KANBAN_WORKDIR"),
		HTTPTimeout:     15 * time.Second,
		PollInterval:    5 * time.Second,
		HTTPListen:      "127.0.0.1:8087",
		IdleInterval:    10 * time.Second,
	}
	env, err := readDotenv(".env")
	if err != nil {
		return c, fmt.Errorf("read .env: %w", err)
	}
	c.TrelloKey = env["TRELLO_API_KEY"]
	c.TrelloToken = env["TRELLO_TOKEN"]
	c.OpenCodeUser = env["OPENCODE_SERVER_USERNAME"]
	c.OpenCodePass = env["OPENCODE_SERVER_PASSWORD"]
	if c.TrelloKey == "" || c.TrelloToken == "" {
		return c, fmt.Errorf("TRELLO_API_KEY or TRELLO_TOKEN missing")
	}
	if c.OpenCodeUser == "" || c.OpenCodePass == "" {
		return c, fmt.Errorf("OPENCODE_SERVER_USERNAME or OPENCODE_SERVER_PASSWORD missing")
	}
	return c, nil
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func readDotenv(path string) (map[string]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	out := make(map[string]string)
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		eq := strings.IndexByte(line, '=')
		if eq <= 0 {
			continue
		}
		out[strings.TrimSpace(line[:eq])] = strings.TrimSpace(line[eq+1:])
	}
	return out, nil
}

func die(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "FATAL: "+format+"\n", args...)
	os.Exit(2)
}

func (s *server) trelloListCards(ctx context.Context, listID string) ([]trelloCard, error) {
	u := fmt.Sprintf("https://api.trello.com/1/lists/%s/cards?key=%s&token=%s&fields=name,desc,idList,url",
		listID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return nil, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var cards []trelloCard
	if err := json.NewDecoder(resp.Body).Decode(&cards); err != nil {
		return nil, err
	}
	return cards, nil
}

func (s *server) trelloAddComment(ctx context.Context, cardID, text string) error {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s/actions/comments?key=%s&token=%s",
		cardID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	body, _ := json.Marshal(map[string]string{"text": text})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}

func (s *server) trelloMoveCard(ctx context.Context, cardID, listID string) error {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s?key=%s&token=%s",
		cardID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	body, _ := json.Marshal(map[string]string{"idList": listID})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPut, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}

func (s *server) trelloAddLabel(ctx context.Context, cardID, labelID string) error {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s/idLabels?key=%s&token=%s",
		cardID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	body, _ := json.Marshal(map[string]string{"value": labelID})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}

func (s *server) trelloListLabels(ctx context.Context) ([]trelloLabel, error) {
	u := fmt.Sprintf("https://api.trello.com/1/boards/%s/labels?key=%s&token=%s&fields=name,color",
		boardID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return nil, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var labels []trelloLabel
	if err := json.NewDecoder(resp.Body).Decode(&labels); err != nil {
		return nil, err
	}
	return labels, nil
}

func (s *server) trelloCreateLabel(ctx context.Context, name, color string) (string, error) {
	u := fmt.Sprintf("https://api.trello.com/1/labels?key=%s&token=%s",
		s.cfg.TrelloKey, s.cfg.TrelloToken)
	body, _ := json.Marshal(map[string]string{"name": name, "color": color, "idBoard": boardID})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.httpc.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return "", fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var lbl trelloLabel
	if err := json.NewDecoder(resp.Body).Decode(&lbl); err != nil {
		return "", err
	}
	return lbl.ID, nil
}

func (s *server) loadLabels(ctx context.Context) error {
	known := []struct {
		name, color string
	}{
		{"needs-attention", "red"},
		{"no-worktree", "yellow"},
	}
	labels, err := s.trelloListLabels(ctx)
	if err != nil {
		return fmt.Errorf("list: %w", err)
	}
	byName := make(map[string]string)
	for _, l := range labels {
		if l.Name != "" {
			byName[l.Name] = l.ID
		}
	}
	for _, k := range known {
		if id, ok := byName[k.name]; ok {
			s.labels[k.name] = id
			continue
		}
		id, err := s.trelloCreateLabel(ctx, k.name, k.color)
		if err != nil {
			return fmt.Errorf("create %s: %w", k.name, err)
		}
		s.labels[k.name] = id
	}
	return nil
}

func (s *server) ocCreateSession(ctx context.Context) (ocSession, error) {
	u := s.cfg.OpenCodeBaseURL + "/session?directory=" + url.QueryEscape(s.cfg.WorkDir)
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, strings.NewReader("{}"))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(s.cfg.OpenCodeUser, s.cfg.OpenCodePass)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return ocSession{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return ocSession{}, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var sess ocSession
	if err := json.NewDecoder(resp.Body).Decode(&sess); err != nil {
		return ocSession{}, err
	}
	if !strings.HasPrefix(sess.ID, "ses_") {
		return sess, fmt.Errorf("unexpected id=%q", sess.ID)
	}
	return sess, nil
}

func (s *server) ocSendPromptAsync(ctx context.Context, sessionID, prompt string) error {
	u := fmt.Sprintf("%s/session/%s/prompt_async?directory=%s",
		s.cfg.OpenCodeBaseURL, sessionID, url.QueryEscape(s.cfg.WorkDir))
	body, _ := json.Marshal(map[string]any{
		"model": map[string]string{"providerID": "opencode-go", "modelID": "minimax-m3"},
		"parts": []map[string]string{{"type": "text", "text": prompt}},
	})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(s.cfg.OpenCodeUser, s.cfg.OpenCodePass)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 204 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}

func (s *server) ocGetLastMessage(ctx context.Context, sessionID string) (map[string]any, error) {
	u := fmt.Sprintf("%s/session/%s/message?limit=1", s.cfg.OpenCodeBaseURL, sessionID)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	req.SetBasicAuth(s.cfg.OpenCodeUser, s.cfg.OpenCodePass)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return nil, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var msgs []map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&msgs); err != nil {
		return nil, err
	}
	if len(msgs) == 0 {
		return nil, nil
	}
	return msgs[len(msgs)-1], nil
}
