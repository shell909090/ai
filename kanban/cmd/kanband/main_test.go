package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestReadDotenv(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, ".env")
	must := func(err error) {
		t.Helper()
		if err != nil {
			t.Fatal(err)
		}
	}
	must(os.WriteFile(path, []byte(strings.Join([]string{
		"# a comment",
		"",
		"FOO=bar",
		"EMPTY=",
		"QUOTED = \"hello world\"",
		"BADLINE_NO_EQUALS",
		"KEY=value",
	}, "\n")), 0644))
	got, err := readDotenv(path)
	if err != nil {
		t.Fatal(err)
	}
	if got["FOO"] != "bar" {
		t.Errorf("FOO=%q, want bar", got["FOO"])
	}
	if got["EMPTY"] != "" {
		t.Errorf("EMPTY=%q, want empty", got["EMPTY"])
	}
	if got["QUOTED"] != "\"hello world\"" {
		t.Errorf("QUOTED=%q", got["QUOTED"])
	}
	if got["KEY"] != "value" {
		t.Errorf("KEY=%q", got["KEY"])
	}
	if _, ok := got["BADLINE_NO_EQUALS"]; ok {
		t.Error("malformed line should be skipped")
	}
}

func TestReadDotenvMissing(t *testing.T) {
	_, err := readDotenv("/nonexistent/.env")
	if err == nil {
		t.Fatal("expected error on missing file")
	}
}

func TestEnvOr(t *testing.T) {
	key := "KANBAN_TEST_ENVOR"
	os.Unsetenv(key)
	if got := envOr(key, "def"); got != "def" {
		t.Errorf("unset env: got %q, want def", got)
	}
	os.Setenv(key, "real")
	defer os.Unsetenv(key)
	if got := envOr(key, "def"); got != "real" {
		t.Errorf("set env: got %q, want real", got)
	}
}

func TestWriteJSON(t *testing.T) {
	w := httptest.NewRecorder()
	writeJSON(w, http.StatusTeapot, map[string]string{"k": "v"})
	if w.Code != http.StatusTeapot {
		t.Errorf("code=%d, want 418", w.Code)
	}
	if !strings.Contains(w.Body.String(), `"k":"v"`) {
		t.Errorf("body=%q", w.Body.String())
	}
}

// fakeOpencode is a minimal opencode stand-in for processCard /
// ocCreateSession / ocGetLastMessage tests.
type fakeOpencode struct {
	sessionID string
	message   map[string]any
}

func (f *fakeOpencode) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/session", f.sessionHandler)
	mux.HandleFunc("/session/", f.subHandler)
	return mux
}

func (f *fakeOpencode) subHandler(w http.ResponseWriter, r *http.Request) {
	switch {
	case strings.HasSuffix(r.URL.Path, "/prompt_async"):
		f.promptHandler(w, r)
	case strings.HasSuffix(r.URL.Path, "/message"):
		f.messageHandler(w, r)
	default:
		w.WriteHeader(http.StatusNotFound)
	}
}

func (f *fakeOpencode) sessionHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	w.WriteHeader(http.StatusOK)
	_, _ = w.Write([]byte(`{"id":"` + f.sessionID + `","directory":"/tmp","projectID":"p1"}`))
}

func (f *fakeOpencode) messageHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	if f.message == nil {
		_, _ = w.Write([]byte(`[]`))
		return
	}
	data, _ := json.Marshal(f.message)
	_, _ = w.Write([]byte("[" + string(data) + "]"))
}

func (f *fakeOpencode) promptHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func newServerFull(ocURL, trelloURL string) *server {
	httpc := &http.Client{Timeout: 2 * time.Second, Transport: &rewriteTransport{base: http.DefaultTransport, target: trelloURL}}
	return &server{
		cfg: config{
			TrelloKey:       "k",
			TrelloToken:     "t",
			OpenCodeUser:    "u",
			OpenCodePass:    "p",
			OpenCodeBaseURL: ocURL,
			WorkDir:         "/tmp",
			HTTPTimeout:     2 * time.Second,
		},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{"needs-attention": "lbl_needs-attention"},
		httpc:        httpc,
	}
}

func TestTrelloListCards(t *testing.T) {
	trello := newFakeTrello()
	trello.cards = []trelloCard{{ID: "c1", Name: "first"}}
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newServerFull("http://opencode.invalid", srv.URL)
	got, err := s.trelloListCards(context.Background(), doingID)
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 1 || got[0].ID != "c1" {
		t.Errorf("got %v, want [c1]", got)
	}
}

func TestTrelloListCardsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("boom"))
	}))
	defer srv.Close()
	s := newServerFull("http://opencode.invalid", srv.URL)
	_, err := s.trelloListCards(context.Background(), doingID)
	if err == nil {
		t.Fatal("expected error on 500")
	}
}

func TestTrelloAddComment(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newServerFull("http://opencode.invalid", srv.URL)
	if err := s.trelloAddComment(context.Background(), "c1", "hi"); err != nil {
		t.Fatal(err)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.comments) != 1 || trello.comments[0] != "hi" {
		t.Errorf("comments=%v, want [hi]", trello.comments)
	}
}

func TestTrelloMoveCard(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newServerFull("http://opencode.invalid", srv.URL)
	if err := s.trelloMoveCard(context.Background(), "c1", doneID); err != nil {
		t.Fatal(err)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0] != (move{cardID: "c1", listID: doneID}) {
		t.Errorf("moves=%v, want [{c1 %s}]", trello.moves, doneID)
	}
}

func TestTrelloAddLabel(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newServerFull("http://opencode.invalid", srv.URL)
	if err := s.trelloAddLabel(context.Background(), "c1", "lbl_x"); err != nil {
		t.Fatal(err)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.labelAdds) != 1 || trello.labelAdds[0] != "lbl_x" {
		t.Errorf("labelAdds=%v, want [lbl_x]", trello.labelAdds)
	}
}

func TestTrelloListAndCreateLabel(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newServerFull("http://opencode.invalid", srv.URL)
	got, err := s.trelloListLabels(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if len(got) != 0 {
		t.Errorf("expected empty list, got %v", got)
	}
	id, err := s.trelloCreateLabel(context.Background(), "foo", "red")
	if err != nil {
		t.Fatal(err)
	}
	if id == "" {
		t.Error("expected non-empty id")
	}
}

func TestLoadLabels(t *testing.T) {
	trello := newFakeTrello()
	trello.labelExists["needs-attention"] = "pre_existing"
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newServerFull("http://opencode.invalid", srv.URL)
	if err := s.loadLabels(context.Background()); err != nil {
		t.Fatal(err)
	}
	if s.labels["needs-attention"] != "pre_existing" {
		t.Errorf("labels=%v", s.labels)
	}
	if _, ok := s.labels["no-worktree"]; !ok {
		t.Errorf("no-worktree should be created, labels=%v", s.labels)
	}
}

func TestOcCreateSession(t *testing.T) {
	oc := &fakeOpencode{sessionID: "ses_xyz"}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s := &server{
		cfg:          config{OpenCodeBaseURL: srv.URL, OpenCodeUser: "u", OpenCodePass: "p"},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 2 * time.Second},
	}
	sess, err := s.ocCreateSession(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	if sess.ID != "ses_xyz" {
		t.Errorf("id=%q, want ses_xyz", sess.ID)
	}
}

func TestOcCreateSessionBadID(t *testing.T) {
	oc := &fakeOpencode{sessionID: "not-prefixed"}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s := &server{
		cfg:          config{OpenCodeBaseURL: srv.URL, OpenCodeUser: "u", OpenCodePass: "p"},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 2 * time.Second},
	}
	_, err := s.ocCreateSession(context.Background())
	if err == nil {
		t.Fatal("expected error for bad session id prefix")
	}
}

func TestOcCreateSessionError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s := &server{
		cfg:          config{OpenCodeBaseURL: srv.URL, OpenCodeUser: "u", OpenCodePass: "p"},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 2 * time.Second},
	}
	_, err := s.ocCreateSession(context.Background())
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestOcGetLastMessageEmpty(t *testing.T) {
	oc := &fakeOpencode{}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s := &server{
		cfg:          config{OpenCodeBaseURL: srv.URL, OpenCodeUser: "u", OpenCodePass: "p"},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 2 * time.Second},
	}
	last, err := s.ocGetLastMessage(context.Background(), "ses1")
	if err != nil {
		t.Fatal(err)
	}
	if last != nil {
		t.Errorf("last=%v, want nil", last)
	}
}

func TestOcGetLastMessageWithFinish(t *testing.T) {
	oc := &fakeOpencode{message: map[string]any{
		"info": map[string]any{"role": "assistant", "finish": "stop"},
	}}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s := &server{
		cfg:          config{OpenCodeBaseURL: srv.URL, OpenCodeUser: "u", OpenCodePass: "p"},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 2 * time.Second},
	}
	last, err := s.ocGetLastMessage(context.Background(), "ses1")
	if err != nil {
		t.Fatal(err)
	}
	if extractFinish(last) != "stop" {
		t.Errorf("extractFinish=%q, want stop", extractFinish(last))
	}
}

func TestOcSendPromptAsync(t *testing.T) {
	var receivedBody string
	oc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body := make([]byte, 4096)
		n, _ := r.Body.Read(body)
		receivedBody = string(body[:n])
		w.WriteHeader(http.StatusNoContent)
	}))
	defer oc.Close()
	s := &server{
		cfg:          config{OpenCodeBaseURL: oc.URL, OpenCodeUser: "u", OpenCodePass: "p", WorkDir: "/tmp"},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 2 * time.Second},
	}
	if err := s.ocSendPromptAsync(context.Background(), "ses1", "hello"); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(receivedBody, "hello") {
		t.Errorf("body should contain prompt, got %q", receivedBody)
	}
}

func TestOcSendPromptAsyncError(t *testing.T) {
	oc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte("boom"))
	}))
	defer oc.Close()
	s := &server{
		cfg:          config{OpenCodeBaseURL: oc.URL, OpenCodeUser: "u", OpenCodePass: "p", WorkDir: "/tmp"},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 2 * time.Second},
	}
	err := s.ocSendPromptAsync(context.Background(), "ses1", "hello")
	if err == nil {
		t.Fatal("expected error on 500")
	}
}

func TestProcessCard(t *testing.T) {
	trello := newFakeTrello()
	tr := httptest.NewServer(trello.handler())
	defer tr.Close()
	oc := &fakeOpencode{sessionID: "ses_proc"}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s := newServerFull(ocURL.URL, tr.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", cardName: "n1", status: statusStarted}
	card := trelloCard{ID: "c1", Name: "n1", Desc: "do the thing"}
	s.processCard(context.Background(), &drainLog{}, card)

	s.mu.Lock()
	defer s.mu.Unlock()
	info, ok := s.cardSessions["c1"]
	if !ok {
		t.Fatal("c1 not in cardSessions")
	}
	if info.sessionID != "ses_proc" {
		t.Errorf("sessionID=%q, want ses_proc", info.sessionID)
	}
	if info.startedAt.IsZero() {
		t.Error("startedAt should be set")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.comments) != 1 {
		t.Errorf("expected Started comment, got %v", trello.comments)
	}
}

func TestProcessCardSessionError(t *testing.T) {
	trello := newFakeTrello()
	tr := httptest.NewServer(trello.handler())
	defer tr.Close()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	s := newServerFull(srv.URL, tr.URL)
	card := trelloCard{ID: "c1", Name: "n1"}
	s.processCard(context.Background(), &drainLog{}, card)

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("c1 should be removed on session error")
	}
}

func TestProcessCardPromptError(t *testing.T) {
	trello := newFakeTrello()
	tr := httptest.NewServer(trello.handler())
	defer tr.Close()
	// opencode: session POST returns 200 with id, prompt_async returns 500
	mux := http.NewServeMux()
	mux.HandleFunc("/session", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"id":"ses_p"}`))
	})
	mux.HandleFunc("/session/", func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/prompt_async") {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		_, _ = w.Write([]byte(`[]`))
	})
	ocURL := httptest.NewServer(mux)
	defer ocURL.Close()

	s := newServerFull(ocURL.URL, tr.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", cardName: "n1", status: statusStarted}
	card := trelloCard{ID: "c1", Name: "n1", Desc: "x"}
	s.processCard(context.Background(), &drainLog{}, card)

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("c1 should be removed on prompt error")
	}
}

func TestPollOnceNoNew(t *testing.T) {
	trello := newFakeTrello()
	tr := httptest.NewServer(trello.handler())
	defer tr.Close()
	oc := &fakeOpencode{}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s := newServerFull(ocURL.URL, tr.URL)
	s.pollOnce(context.Background(), &drainLog{})

	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.cardSessions) != 0 {
		t.Errorf("cardSessions=%v, want empty", s.cardSessions)
	}
}

func TestRunFinishWatcherStopsOnCancel(t *testing.T) {
	s := &server{
		cfg:          config{IdleInterval: 20 * time.Millisecond},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: time.Second},
	}
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		s.runFinishWatcher(ctx, &drainLog{})
		close(done)
	}()
	time.Sleep(50 * time.Millisecond)
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("runFinishWatcher did not return after cancel")
	}
}

func TestCheckOneSessionServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s := &server{
		cfg:          config{OpenCodeBaseURL: srv.URL, OpenCodeUser: "u", OpenCodePass: "p"},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 2 * time.Second},
	}
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	s.checkOneSession(context.Background(), log, "ses1")
	if !strings.Contains(log.String(), "finish.message.fail") {
		t.Errorf("expected finish.message.fail log, got %s", log.String())
	}
}

func TestCheckOneSessionUnknownSession(t *testing.T) {
	oc := &fakeOpencode{}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s := &server{
		cfg:          config{OpenCodeBaseURL: srv.URL, OpenCodeUser: "u", OpenCodePass: "p"},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 2 * time.Second},
	}
	// No registration — checkOneSession should be a no-op.
	s.checkOneSession(context.Background(), &drainLog{}, "ses_orphan")
	// No assertion; just ensure no panic.
}

func TestPollOncePollError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s := newServerFull("http://opencode.invalid", srv.URL)
	log := &drainLog{}
	s.pollOnce(context.Background(), log)
	if !strings.Contains(log.String(), "poll.error") {
		t.Errorf("expected poll.error log, got %s", log.String())
	}
}
