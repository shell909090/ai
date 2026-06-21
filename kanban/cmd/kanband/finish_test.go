package main

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestExtractFinish(t *testing.T) {
	cases := []struct {
		name string
		in   map[string]any
		want string
	}{
		{"nil", nil, ""},
		{"empty", map[string]any{}, ""},
		{"no info", map[string]any{"role": "assistant"}, ""},
		{"info no finish", map[string]any{"info": map[string]any{"role": "assistant"}}, ""},
		{"finish stop", map[string]any{"info": map[string]any{"role": "assistant", "finish": "stop"}}, "stop"},
		{"finish tool-calls", map[string]any{"info": map[string]any{"role": "assistant", "finish": "tool-calls"}}, "tool-calls"},
		{"finish length", map[string]any{"info": map[string]any{"role": "assistant", "finish": "length"}}, "length"},
		{"finish error", map[string]any{"info": map[string]any{"role": "assistant", "finish": "error"}}, "error"},
		{"finish non-string", map[string]any{"info": map[string]any{"finish": 42}}, ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := extractFinish(c.in)
			if got != c.want {
				t.Errorf("extractFinish(%v) = %q, want %q", c.in, got, c.want)
			}
		})
	}
}

func TestIsAbnormalFinish(t *testing.T) {
	cases := []struct {
		finish string
		want   bool
	}{
		{"", false},
		{"stop", false},
		{"tool-calls", false},
		{"length", true},
		{"error", true},
		{"unknown", false},
	}
	for _, c := range cases {
		got := isAbnormalFinish(c.finish)
		if got != c.want {
			t.Errorf("isAbnormalFinish(%q) = %v, want %v", c.finish, got, c.want)
		}
	}
}

// fakeTrello is a minimal Trello stand-in for markCardFinished tests.
// It records each API call and returns canned responses.
type fakeTrello struct {
	mu          sync.Mutex
	comments    []string
	labelAdds   []string
	moves       []move
	labelExists map[string]string
	cards       []trelloCard
}

type move struct {
	cardID string
	listID string
}

func newFakeTrello() *fakeTrello {
	return &fakeTrello{labelExists: map[string]string{}}
}

func (f *fakeTrello) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/1/cards/", f.cardsHandler)
	mux.HandleFunc("/1/labels", f.labelsHandler)
	mux.HandleFunc("/1/boards/", f.boardsHandler)
	mux.HandleFunc("/1/lists/", f.listCardsHandler)
	return mux
}

func (f *fakeTrello) boardsHandler(w http.ResponseWriter, r *http.Request) {
	// /1/boards/{boardID}/labels?fields=...
	if !strings.HasSuffix(r.URL.Path, "/labels") {
		w.WriteHeader(http.StatusNotFound)
		return
	}
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	out := []map[string]string{}
	for name, id := range f.labelExists {
		out = append(out, map[string]string{"id": id, "name": name, "color": "red", "idBoard": "b1"})
	}
	_ = json.NewEncoder(w).Encode(out)
}

func (f *fakeTrello) listCardsHandler(w http.ResponseWriter, r *http.Request) {
	// /1/lists/{listID}/cards?fields=...
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	if !strings.HasSuffix(r.URL.Path, "/cards") {
		w.WriteHeader(http.StatusNotFound)
		return
	}
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.cards == nil {
		_, _ = w.Write([]byte(`[]`))
		return
	}
	_ = json.NewEncoder(w).Encode(f.cards)
}

func (f *fakeTrello) cardsHandler(w http.ResponseWriter, r *http.Request) {
	path := strings.TrimPrefix(r.URL.Path, "/1/cards/")
	parts := strings.SplitN(path, "/", 2)
	cardID := parts[0]
	suffix := ""
	if len(parts) == 2 {
		suffix = "/" + parts[1]
	}
	switch {
	case strings.HasSuffix(suffix, "/actions/comments") && r.Method == http.MethodPost:
		var body struct {
			Text string `json:"text"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		f.mu.Lock()
		f.comments = append(f.comments, body.Text)
		f.mu.Unlock()
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"id":"ac1","data":{"text":"x"}}`))
	case suffix == "" && r.Method == http.MethodPut:
		var body struct {
			IDList string `json:"idList"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		f.mu.Lock()
		f.moves = append(f.moves, move{cardID: cardID, listID: body.IDList})
		f.mu.Unlock()
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"id":"` + cardID + `"}`))
	case suffix == "/idLabels" && r.Method == http.MethodPost:
		var body struct {
			Value string `json:"value"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		f.mu.Lock()
		f.labelAdds = append(f.labelAdds, body.Value)
		f.mu.Unlock()
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"id":"lb1"}`))
	default:
		w.WriteHeader(http.StatusNotFound)
	}
	_ = cardID
}

func (f *fakeTrello) labelsHandler(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		out := []map[string]string{}
		for name, id := range f.labelExists {
			out = append(out, map[string]string{"id": id, "name": name, "color": "red", "idBoard": "b1"})
		}
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(out)
	case http.MethodPost:
		var body struct{ Name, Color, IDBoard string }
		_ = json.NewDecoder(r.Body).Decode(&body)
		id := "lbl_" + body.Name
		f.mu.Lock()
		f.labelExists[body.Name] = id
		f.mu.Unlock()
		w.WriteHeader(http.StatusOK)
		_ = json.NewEncoder(w).Encode(map[string]string{"id": id, "name": body.Name, "color": body.Color, "idBoard": body.IDBoard})
	}
}

func newServerWithFake(t *testing.T) (*server, *fakeTrello) {
	t.Helper()
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	t.Cleanup(srv.Close)

	// The server uses real Trello API URL; redirect by overriding httpc
	// is not possible because the URL is hard-coded. Instead we use a
	// custom transport that rewrites the host.
	transport := &rewriteTransport{base: http.DefaultTransport, target: srv.URL}
	httpc := &http.Client{Timeout: 5 * time.Second, Transport: transport}

	s := &server{
		cfg: config{
			TrelloKey:       "k",
			TrelloToken:     "t",
			OpenCodeBaseURL: "http://opencode.invalid",
			OpenCodeUser:    "u",
			OpenCodePass:    "p",
			HTTPTimeout:     5 * time.Second,
		},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{"needs-attention": "lbl_needs-attention"},
		httpc:        httpc,
	}
	return s, trello
}

type rewriteTransport struct {
	base   http.RoundTripper
	target string
}

func (r *rewriteTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	// Redirect api.trello.com → the fake server
	if strings.HasPrefix(req.URL.String(), "https://api.trello.com/") {
		newURL := r.target + strings.TrimPrefix(req.URL.String(), "https://api.trello.com")
		u, err := url.Parse(newURL)
		if err == nil {
			req.URL = u
			req.Host = u.Host
		}
	}
	return r.base.RoundTrip(req)
}

// drainLog returns a writer that records all bytes written to it.
type drainLog struct {
	mu  sync.Mutex
	buf strings.Builder
}

func (d *drainLog) Write(p []byte) (int, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.buf.Write(p)
}

func (d *drainLog) String() string {
	d.mu.Lock()
	defer d.mu.Unlock()
	return d.buf.String()
}

func TestMarkCardFinishedNormal(t *testing.T) {
	s, trello := newServerWithFake(t)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	s.markCardFinished(context.Background(), log, "c1", "ses1", "stop")

	if got := len(trello.comments); got != 1 {
		t.Fatalf("comments=%d, want 1", got)
	}
	if !strings.Contains(trello.comments[0], "✅ Completed session ses1") {
		t.Errorf("comment=%q, want contain '✅ Completed session ses1'", trello.comments[0])
	}
	if got := len(trello.labelAdds); got != 0 {
		t.Errorf("labelAdds=%d, want 0", got)
	}
	if got := len(trello.moves); got != 1 || trello.moves[0] != (move{"c1", doneID}) {
		t.Errorf("moves=%v, want [{c1 %s}]", trello.moves, doneID)
	}
	if _, ok := s.cardSessions["c1"]; ok {
		t.Errorf("card still in cardSessions after finish")
	}
	if _, ok := s.sessionCards["ses1"]; ok {
		t.Errorf("session still in sessionCards after finish")
	}
}

func TestMarkCardFinishedToolCalls(t *testing.T) {
	// tool-calls finish is still a valid completion signal; no
	// needs-attention should be added.
	s, trello := newServerWithFake(t)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.markCardFinished(context.Background(), &drainLog{}, "c1", "ses1", "tool-calls")

	if got := len(trello.comments); got != 1 {
		t.Errorf("tool-calls should write only the ✅ comment, got %d", got)
	}
	if got := len(trello.labelAdds); got != 0 {
		t.Errorf("tool-calls should not add needs-attention, got %d", got)
	}
}

func TestMarkCardFinishedError(t *testing.T) {
	s, trello := newServerWithFake(t)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.markCardFinished(context.Background(), &drainLog{}, "c1", "ses1", "error")

	if got := len(trello.comments); got != 2 {
		t.Fatalf("error finish should write 2 comments, got %d", got)
	}
	if !strings.Contains(trello.comments[0], "✅ Completed") {
		t.Errorf("first comment=%q", trello.comments[0])
	}
	if !strings.Contains(trello.comments[1], "❌ Error in session ses1") {
		t.Errorf("second comment=%q", trello.comments[1])
	}
	if !strings.Contains(trello.comments[1], "finish=error") {
		t.Errorf("second comment should include finish=error, got %q", trello.comments[1])
	}
	if got := len(trello.labelAdds); got != 1 || trello.labelAdds[0] != "lbl_needs-attention" {
		t.Errorf("labelAdds=%v, want [lbl_needs-attention]", trello.labelAdds)
	}
}

func TestMarkCardFinishedLength(t *testing.T) {
	s, trello := newServerWithFake(t)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.markCardFinished(context.Background(), &drainLog{}, "c1", "ses1", "length")

	if got := len(trello.labelAdds); got != 1 {
		t.Errorf("length finish should add needs-attention, got %d", got)
	}
}

func TestMarkCardFinishedIdempotent(t *testing.T) {
	// Second call on an already-finished card must be a no-op.
	s, trello := newServerWithFake(t)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusCompleted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	s.markCardFinished(context.Background(), log, "c1", "ses1", "stop")

	if got := len(trello.comments); got != 0 {
		t.Errorf("second call should be no-op, got %d comments", got)
	}
	if got := len(trello.moves); got != 0 {
		t.Errorf("second call should be no-op, got %d moves", got)
	}
	if !strings.Contains(log.String(), "finish.skip") {
		t.Errorf("expected finish.skip log, got %s", log.String())
	}
}

func TestMarkCardFinishedUnknownCard(t *testing.T) {
	s, trello := newServerWithFake(t)
	// no entry in cardSessions
	log := &drainLog{}
	s.markCardFinished(context.Background(), log, "missing", "sesX", "stop")

	if got := len(trello.comments); got != 0 {
		t.Errorf("unknown card should be no-op, got %d comments", got)
	}
	if !strings.Contains(log.String(), "finish.skip") {
		t.Errorf("expected finish.skip log, got %s", log.String())
	}
}

// TestCheckOneSessionSkipsWhenNoFinish exercises the watcher path: when
// the last message has no info.finish (still streaming), the watcher
// must not call markCardFinished.
func TestCheckOneSessionSkipsWhenNoFinish(t *testing.T) {
	// Stand up a fake opencode server that returns a message with no
	// finish field. The check should be a no-op.
	var calls int32
	oc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		atomic.AddInt32(&calls, 1)
		_, _ = w.Write([]byte(`[{"info":{"role":"assistant"}}]`))
	}))
	defer oc.Close()

	s := &server{
		cfg:          config{OpenCodeBaseURL: oc.URL, OpenCodeUser: "u", OpenCodePass: "p"},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 5 * time.Second},
	}
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"

	log := &drainLog{}
	s.checkOneSession(context.Background(), log, "ses1")

	if got := atomic.LoadInt32(&calls); got != 1 {
		t.Errorf("ocGetLastMessage called %d times, want 1", got)
	}
	if _, ok := s.cardSessions["c1"]; !ok {
		t.Errorf("card should still be in cardSessions (no finish yet)")
	}
}

func TestCheckOneSessionTriggersOnFinish(t *testing.T) {
	// Stand up a fake opencode that returns a finished message. The
	// watcher should call markCardFinished and remove the card from
	// cardSessions. We don't have a Trello fake here so markCardFinished
	// will fail on Trello calls — wrap with a fake Trello too.
	oc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		_, _ = w.Write([]byte(`[{"info":{"role":"assistant","finish":"stop"}}]`))
	}))
	defer oc.Close()

	trello := newFakeTrello()
	tr := httptest.NewServer(trello.handler())
	defer tr.Close()

	s := &server{
		cfg: config{
			OpenCodeBaseURL: oc.URL,
			OpenCodeUser:    "u",
			OpenCodePass:    "p",
			TrelloKey:       "k",
			TrelloToken:     "t",
			HTTPTimeout:     5 * time.Second,
		},
		cardSessions: make(map[string]*sessionInfo),
		sessionCards: make(map[string]string),
		labels:       map[string]string{},
		httpc:        &http.Client{Timeout: 5 * time.Second, Transport: &rewriteTransport{base: http.DefaultTransport, target: tr.URL}},
	}
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"

	s.checkOneSession(context.Background(), &drainLog{}, "ses1")

	if _, ok := s.cardSessions["c1"]; ok {
		t.Errorf("card should be removed from cardSessions after finish")
	}
	if got := len(trello.moves); got != 1 || trello.moves[0].listID != doneID {
		t.Errorf("moves=%v, want one move to %s", trello.moves, doneID)
	}
}

// Ensure markCardFinished only writes a single ✅ comment on abnormal
// finish when needs-attention label is missing (no panic, comment still
// present).
func TestMarkCardFinishedAbnormalNoLabel(t *testing.T) {
	s, trello := newServerWithFake(t)
	delete(s.labels, "needs-attention")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	s.markCardFinished(context.Background(), log, "c1", "ses1", "error")

	if got := len(trello.comments); got != 2 {
		t.Errorf("error finish should still write 2 comments, got %d", got)
	}
	if !strings.Contains(log.String(), "finish.label.missing") {
		t.Errorf("expected finish.label.missing log, got %s", log.String())
	}
}

// silence unused imports in some build configs.
var _ = io.Discard
