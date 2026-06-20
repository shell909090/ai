package main

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strings"
	"time"
)

type Result string

const (
	ResultPass    Result = "PASS"
	ResultFail    Result = "FAIL"
	ResultSkipped Result = "SKIPPED"
)

type Report struct {
	Step   string `json:"step"`
	Result Result `json:"result"`
	Detail string `json:"detail,omitempty"`
}

type config struct {
	opencodeURL       string
	opencodeUser      string
	opencodePass      string
	trelloKey         string
	trelloToken       string
	opencodeBin       string
	logPath           string
	httpTimeout       time.Duration
	startupTimeout    time.Duration
	skipOpencodeStart bool
}

type opencodeRunner struct {
	cfg     config
	started *subprocessHandle
	owns    bool
}

func (r *opencodeRunner) shutdown() {
	if r.started != nil {
		r.started.Stop()
	}
}

type subprocessHandle struct {
	cmd    *exec.Cmd
	cancel context.CancelFunc
}

func loadConfig() config {
	c := config{
		opencodeURL:    os.Getenv("KANBAN_OPENCODE_URL"),
		opencodeUser:   os.Getenv("OPENCODE_SERVER_USERNAME"),
		opencodePass:   os.Getenv("OPENCODE_SERVER_PASSWORD"),
		trelloKey:      os.Getenv("TRELLO_API_KEY"),
		trelloToken:    os.Getenv("TRELLO_TOKEN"),
		opencodeBin:    envDefault("OPENCODE_BIN", "opencode"),
		logPath:        envDefault("KANBAN_OPENCODE_LOG", "/tmp/kanban-connectivity-opencode.log"),
		httpTimeout:    10 * time.Second,
		startupTimeout: 30 * time.Second,
	}
	if c.opencodeURL == "" {
		c.opencodeURL = "http://127.0.0.1:4096"
	}
	if v := os.Getenv("SKIP_OPENCODE"); v == "1" || strings.EqualFold(v, "true") {
		c.skipOpencodeStart = true
	}
	return c
}

func envDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func (c config) validate() error {
	if c.opencodeUser == "" {
		return fmt.Errorf("OPENCODE_SERVER_USERNAME not set")
	}
	if c.opencodePass == "" {
		return fmt.Errorf("OPENCODE_SERVER_PASSWORD not set")
	}
	return nil
}

func report(w io.Writer, step string, r Result, detail string) {
	rec := Report{Step: step, Result: r, Detail: detail}
	_ = json.NewEncoder(w).Encode(rec)
}

func reportf(w io.Writer, step string, r Result, format string, args ...any) {
	report(w, step, r, fmt.Sprintf(format, args...))
}

func httpDoBasic(ctx context.Context, method, u, user, pass, body string, timeout time.Duration) (int, string, error) {
	cctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()
	var rdr io.Reader
	if body != "" {
		rdr = strings.NewReader(body)
	}
	req, err := http.NewRequestWithContext(cctx, method, u, rdr)
	if err != nil {
		return 0, "", err
	}
	if body != "" {
		req.Header.Set("Content-Type", "application/json")
	}
	if user != "" {
		req.SetBasicAuth(user, pass)
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return 0, "", err
	}
	defer resp.Body.Close()
	rb, _ := io.ReadAll(io.LimitReader(resp.Body, 64*1024))
	return resp.StatusCode, string(rb), nil
}

func truncate(s string, n int) string {
	if len(s) <= n {
		return s
	}
	return s[:n] + "..."
}

func startOpencodeServer(ctx context.Context, cfg config) (*subprocessHandle, error) {
	logFile, err := os.Create(cfg.logPath)
	if err != nil {
		return nil, fmt.Errorf("create log: %w", err)
	}
	cctx, cancel := context.WithCancel(ctx)
	cmd := exec.CommandContext(cctx, cfg.opencodeBin, "serve", "--port", "4096", "--hostname", "127.0.0.1")
	cmd.Stdout = logFile
	cmd.Stderr = logFile
	cmd.Env = append(os.Environ(),
		"OPENCODE_SERVER_USERNAME="+cfg.opencodeUser,
		"OPENCODE_SERVER_PASSWORD="+cfg.opencodePass,
	)
	if err := cmd.Start(); err != nil {
		_ = logFile.Close()
		cancel()
		return nil, fmt.Errorf("start: %w", err)
	}
	return &subprocessHandle{cmd: cmd, cancel: cancel}, nil
}

func (h *subprocessHandle) Stop() {
	if h == nil {
		return
	}
	h.cancel()
	if h.cmd != nil && h.cmd.Process != nil {
		_ = h.cmd.Process.Kill()
		_, _ = h.cmd.Process.Wait()
	}
}

func waitForHealth(ctx context.Context, url, user, pass string, timeout time.Duration) error {
	deadline := time.Now().Add(timeout)
	var lastErr error
	for time.Now().Before(deadline) {
		code, _, err := httpDoBasic(ctx, http.MethodGet, url, user, pass, "", 2*time.Second)
		if err == nil && code == 200 {
			return nil
		}
		lastErr = err
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(500 * time.Millisecond):
		}
	}
	if lastErr != nil {
		return fmt.Errorf("timeout waiting for %s: %w", url, lastErr)
	}
	return fmt.Errorf("timeout waiting for %s", url)
}

func (r *opencodeRunner) ensureRunning(ctx context.Context, w io.Writer) bool {
	if r.cfg.skipOpencodeStart {
		reportf(w, "opencode.start", ResultSkipped, "connect mode url=%s", r.cfg.opencodeURL)
		return true
	}
	s, err := startOpencodeServer(ctx, r.cfg)
	if err != nil {
		report(w, "opencode.start", ResultFail, err.Error())
		return false
	}
	r.started = s
	r.owns = true
	reportf(w, "opencode.start", ResultPass, "pid=%d log=%s", s.cmd.Process.Pid, r.cfg.logPath)
	healthURL := strings.TrimRight(r.cfg.opencodeURL, "/") + "/global/health"
	if err := waitForHealth(ctx, healthURL, r.cfg.opencodeUser, r.cfg.opencodePass, r.cfg.startupTimeout); err != nil {
		report(w, "opencode.ready", ResultFail, err.Error())
		return false
	}
	report(w, "opencode.ready", ResultPass, healthURL)
	return true
}

func (r *opencodeRunner) runChecks(ctx context.Context, w io.Writer) bool {
	base := strings.TrimRight(r.cfg.opencodeURL, "/")
	user, pass := r.cfg.opencodeUser, r.cfg.opencodePass
	allOK := true

	allOK = r.checkHealth(ctx, w, base+"/global/health", user, pass) && allOK

	sessID, ok := r.checkSessionCreate(ctx, w, base+"/session", user, pass)
	if !ok {
		allOK = false
	} else {
		allOK = r.checkSessionGet(ctx, w, base+"/session/"+sessID, user, pass, sessID) && allOK
		allOK = r.checkSessionDelete(ctx, w, base+"/session/"+sessID, user, pass) && allOK
	}

	return allOK
}

func (r *opencodeRunner) checkHealth(ctx context.Context, w io.Writer, url, user, pass string) bool {
	code, body, err := httpDoBasic(ctx, http.MethodGet, url, user, pass, "", r.cfg.httpTimeout)
	if err != nil {
		reportf(w, "opencode.health", ResultFail, "request: %v", err)
		return false
	}
	if code != http.StatusOK {
		reportf(w, "opencode.health", ResultFail, "status=%d body=%s", code, truncate(body, 200))
		return false
	}
	var h struct {
		Healthy bool   `json:"healthy"`
		Version string `json:"version"`
	}
	if err := json.Unmarshal([]byte(body), &h); err != nil {
		reportf(w, "opencode.health", ResultFail, "unmarshal: %v body=%s", err, truncate(body, 200))
		return false
	}
	if !h.Healthy {
		reportf(w, "opencode.health", ResultFail, "healthy=false body=%s", truncate(body, 200))
		return false
	}
	reportf(w, "opencode.health", ResultPass, "version=%s", h.Version)
	return true
}

func (r *opencodeRunner) checkSessionCreate(ctx context.Context, w io.Writer, url, user, pass string) (string, bool) {
	code, body, err := httpDoBasic(ctx, http.MethodPost, url, user, pass, "{}", r.cfg.httpTimeout)
	if err != nil {
		reportf(w, "opencode.session.create", ResultFail, "request: %v", err)
		return "", false
	}
	if code != http.StatusOK {
		reportf(w, "opencode.session.create", ResultFail, "status=%d body=%s", code, truncate(body, 200))
		return "", false
	}
	var sess struct {
		ID string `json:"id"`
	}
	if err := json.Unmarshal([]byte(body), &sess); err != nil {
		reportf(w, "opencode.session.create", ResultFail, "unmarshal: %v body=%s", err, truncate(body, 200))
		return "", false
	}
	if !strings.HasPrefix(sess.ID, "ses_") {
		reportf(w, "opencode.session.create", ResultFail, "unexpected id=%q", sess.ID)
		return "", false
	}
	reportf(w, "opencode.session.create", ResultPass, "id=%s", sess.ID)
	return sess.ID, true
}

func (r *opencodeRunner) checkSessionGet(ctx context.Context, w io.Writer, url, user, pass, wantID string) bool {
	code, body, err := httpDoBasic(ctx, http.MethodGet, url, user, pass, "", r.cfg.httpTimeout)
	if err != nil {
		reportf(w, "opencode.session.get", ResultFail, "request: %v", err)
		return false
	}
	if code != http.StatusOK {
		reportf(w, "opencode.session.get", ResultFail, "status=%d body=%s", code, truncate(body, 200))
		return false
	}
	var got struct {
		ID string `json:"id"`
	}
	if err := json.Unmarshal([]byte(body), &got); err != nil {
		reportf(w, "opencode.session.get", ResultFail, "unmarshal: %v body=%s", err, truncate(body, 200))
		return false
	}
	if got.ID != wantID {
		reportf(w, "opencode.session.get", ResultFail, "id mismatch: got=%s want=%s", got.ID, wantID)
		return false
	}
	reportf(w, "opencode.session.get", ResultPass, "id=%s", got.ID)
	return true
}

func (r *opencodeRunner) checkSessionDelete(ctx context.Context, w io.Writer, url, user, pass string) bool {
	code, _, err := httpDoBasic(ctx, http.MethodDelete, url, user, pass, "", r.cfg.httpTimeout)
	if err != nil {
		reportf(w, "opencode.session.delete", ResultFail, "request: %v", err)
		return false
	}
	if code != http.StatusOK {
		reportf(w, "opencode.session.delete", ResultFail, "status=%d", code)
		return false
	}
	report(w, "opencode.session.delete", ResultPass, "")
	return true
}

func runTrelloCheck(ctx context.Context, w io.Writer, cfg config) (passed, ran bool) {
	if cfg.trelloKey == "" || cfg.trelloToken == "" {
		report(w, "trello.boards", ResultSkipped, "TRELLO_API_KEY or TRELLO_TOKEN not set")
		return true, false
	}
	u := fmt.Sprintf("https://api.trello.com/1/members/me/boards?key=%s&token=%s",
		url.QueryEscape(cfg.trelloKey), url.QueryEscape(cfg.trelloToken))
	code, body, err := httpDoBasic(ctx, http.MethodGet, u, "", "", "", cfg.httpTimeout)
	if err != nil {
		reportf(w, "trello.boards", ResultFail, "request: %v", err)
		return false, true
	}
	if code != http.StatusOK {
		reportf(w, "trello.boards", ResultFail, "status=%d body=%s", code, truncate(body, 200))
		return false, true
	}
	var boards []json.RawMessage
	if err := json.Unmarshal([]byte(body), &boards); err != nil {
		reportf(w, "trello.boards", ResultFail, "unmarshal: %v body=%s", err, truncate(body, 200))
		return false, true
	}
	reportf(w, "trello.boards", ResultPass, "count=%d", len(boards))
	return true, true
}

func main() {
	os.Exit(run())
}

func run() int {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	cfg := loadConfig()
	w := os.Stdout

	if err := cfg.validate(); err != nil {
		report(w, "config", ResultFail, err.Error())
		return 2
	}

	runner := &opencodeRunner{cfg: cfg}
	defer runner.shutdown()

	if !runner.ensureRunning(ctx, w) {
		report(w, "summary", ResultFail, "opencode startup failed")
		return 2
	}
	opencodeOK := runner.runChecks(ctx, w)
	trelloOK, trelloRan := runTrelloCheck(ctx, w, cfg)

	failed := !opencodeOK || (trelloRan && !trelloOK)
	status := ResultPass
	if failed {
		status = ResultFail
	}
	reportf(w, "summary", status, "opencode=%s trello=%s",
		boolLabel(opencodeOK, "ok", "fail"),
		trelloLabel(trelloOK, trelloRan),
	)

	if failed {
		return 2
	}
	return 0
}

func boolLabel(ok bool, yes, no string) string {
	if ok {
		return yes
	}
	return no
}

func trelloLabel(ok, ran bool) string {
	if !ran {
		return "skipped"
	}
	if ok {
		return "ok"
	}
	return "fail"
}
