package kanban

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
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
			if got := ExtractFinish(c.in); got != c.want {
				t.Errorf("ExtractFinish(%v) = %q, want %q", c.in, got, c.want)
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
		if got := IsAbnormalFinish(c.finish); got != c.want {
			t.Errorf("IsAbnormalFinish(%q) = %v, want %v", c.finish, got, c.want)
		}
	}
}

// newTestServerWithFake wires a Server against the given fake Trello
// and (optional) opencode stand-ins. The workdir is /tmp so the
// constructor accepts it.
func newTestServerWithFake(t *testing.T, trelloURL, ocURL string) (*Server, *fakeTrello) {
	t.Helper()
	httpc := &http.Client{Timeout: 2 * time.Second, Transport: &rewriteTransport{base: http.DefaultTransport, target: trelloURL}}
	s, err := New(Config{
		TrelloKey:       "k",
		TrelloToken:     "t",
		OpenCodeUser:    "u",
		OpenCodePass:    "p",
		OpenCodeBaseURL: ocURL,
		WorkDir:         "/tmp",
		HTTPTimeout:     2 * time.Second,
		HTTPListen:      "127.0.0.1:0",
		PollInterval:    time.Second,
		IdleInterval:    time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	s.httpc = httpc
	s.labels = map[string]string{"needs-attention": "lbl_needs-attention"}
	return s, nil
}

func TestMarkCardFinishedNormal(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)
	s.MarkCardFinished(context.Background(), "c1", "ses1", "stop")

	if got := len(trello.comments); got != 1 {
		t.Fatalf("comments=%d, want 1", got)
	}
	if !strings.Contains(trello.comments[0], "✅ Completed session ses1") {
		t.Errorf("comment=%q", trello.comments[0])
	}
	if got := len(trello.labelAdds); got != 0 {
		t.Errorf("labelAdds=%d, want 0", got)
	}
	if got := len(trello.moves); got != 1 || trello.moves[0] != (moveRec{"c1", doneID}) {
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
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.MarkCardFinished(context.Background(), "c1", "ses1", "tool-calls")

	if got := len(trello.comments); got != 1 {
		t.Errorf("tool-calls should write only the ✅ comment, got %d", got)
	}
	if got := len(trello.labelAdds); got != 0 {
		t.Errorf("tool-calls should not add needs-attention, got %d", got)
	}
}

func TestMarkCardFinishedError(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.MarkCardFinished(context.Background(), "c1", "ses1", "error")

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
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.MarkCardFinished(context.Background(), "c1", "ses1", "length")

	if got := len(trello.labelAdds); got != 1 {
		t.Errorf("length finish should add needs-attention, got %d", got)
	}
}

func TestMarkCardFinishedIdempotent(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusCompleted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)
	s.MarkCardFinished(context.Background(), "c1", "ses1", "stop")

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
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	log := &drainLog{}
	withLogWriter(t, log)
	s.MarkCardFinished(context.Background(), "missing", "sesX", "stop")

	if got := len(trello.comments); got != 0 {
		t.Errorf("unknown card should be no-op, got %d comments", got)
	}
	if !strings.Contains(log.String(), "finish.skip") {
		t.Errorf("expected finish.skip log, got %s", log.String())
	}
}

func TestMarkCardFinishedAbnormalNoLabel(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	delete(s.labels, "needs-attention")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)
	s.MarkCardFinished(context.Background(), "c1", "ses1", "error")

	if got := len(trello.comments); got != 2 {
		t.Errorf("error finish should still write 2 comments, got %d", got)
	}
	if !strings.Contains(log.String(), "finish.label.missing") {
		t.Errorf("expected finish.label.missing log, got %s", log.String())
	}
}

func TestCheckOneSessionSkipsWhenNoFinish(t *testing.T) {
	oc := &fakeOpencode{}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.checkOneSession(context.Background(), "ses1")
	if _, ok := s.cardSessions["c1"]; !ok {
		t.Error("card should still be in cardSessions (no finish yet)")
	}
}

func TestCheckOneSessionTriggersOnFinish(t *testing.T) {
	oc := &fakeOpencode{message: map[string]any{
		"info": map[string]any{"role": "assistant", "finish": "stop"},
	}}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"

	s.checkOneSession(context.Background(), "ses1")

	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("card should be removed from cardSessions after finish")
	}
	if got := len(trello.moves); got != 1 || trello.moves[0].listID != doneID {
		t.Errorf("moves=%v, want one move to %s", trello.moves, doneID)
	}
}

func TestCheckOneSessionServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)
	s.checkOneSession(context.Background(), "ses1")
	if !strings.Contains(log.String(), "finish.message.fail") {
		t.Errorf("expected finish.message.fail log, got %s", log.String())
	}
	if _, ok := s.cardSessions["c1"]; !ok {
		t.Error("card should remain in cardSessions on error")
	}
}

func TestCheckOneSessionUnknownSession(t *testing.T) {
	oc := &fakeOpencode{}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
	s.checkOneSession(context.Background(), "ses_orphan")
}

func TestRunFinishWatcherStopsOnCancel(t *testing.T) {
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", "http://opencode.invalid")
	s.cfg.IdleInterval = 20 * time.Millisecond
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		s.runFinishWatcher(ctx)
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

// keep encoding/json referenced from this file for tests.
var _ = json.Marshal
