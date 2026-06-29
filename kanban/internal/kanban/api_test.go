package kanban

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestTrelloListCards(t *testing.T) {
	trello := newFakeTrello()
	trello.setCards(testDoingID, []trelloCard{{ID: "c1", Name: "first"}})
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newTestServer(t, srv.URL)
	got, err := s.trelloListCards(context.Background(), testDoingID)
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
	}))
	defer srv.Close()
	s := newTestServer(t, srv.URL)
	_, err := s.trelloListCards(context.Background(), testDoingID)
	if err == nil {
		t.Fatal("expected error on 500")
	}
}

func TestTrelloAddComment(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newTestServer(t, srv.URL)
	if err := s.trelloAddComment(context.Background(), "c1", "hi"); err != nil {
		t.Fatal(err)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.comments) != 1 || trello.comments[0] != "hi" {
		t.Errorf("comments=%v, want [hi]", trello.comments)
	}
}

func TestTrelloAddCommentError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s := newTestServer(t, srv.URL)
	if err := s.trelloAddComment(context.Background(), "c1", "hi"); err == nil {
		t.Error("expected error on 500")
	}
}

func TestTrelloMoveCard(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newTestServer(t, srv.URL)
	if err := s.trelloMoveCard(context.Background(), "c1", testDoneID); err != nil {
		t.Fatal(err)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0] != (moveRec{cardID: "c1", listID: testDoneID}) {
		t.Errorf("moves=%v, want [{c1 %s}]", trello.moves, testDoneID)
	}
}

func TestTrelloMoveCardError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s := newTestServer(t, srv.URL)
	if err := s.trelloMoveCard(context.Background(), "c1", testDoneID); err == nil {
		t.Error("expected error on 500")
	}
}

func TestTrelloAddLabel(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newTestServer(t, srv.URL)
	if err := s.trelloAddLabel(context.Background(), "c1", "lbl_x"); err != nil {
		t.Fatal(err)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.labelAdds) != 1 || trello.labelAdds[0] != "lbl_x" {
		t.Errorf("labelAdds=%v, want [lbl_x]", trello.labelAdds)
	}
}

func TestTrelloListBoardLabels(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newTestServer(t, srv.URL)
	got, err := s.trelloListBoardLabels(context.Background(), testBoardID)
	if err != nil {
		t.Fatal(err)
	}
	// fakeTrello returns attention, human, proj:agent, proj:kanban labels
	if len(got) < 2 {
		t.Errorf("len=%d, want at least 2", len(got))
	}
}

func TestTrelloListBoardLabelsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s := newTestServer(t, srv.URL)
	if _, err := s.trelloListBoardLabels(context.Background(), testBoardID); err == nil {
		t.Error("expected error on 500")
	}
}

func TestResolveLabelID(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newTestServer(t, srv.URL)

	id, err := s.resolveLabelID(context.Background(), testAttentionName)
	if err != nil {
		t.Fatalf("resolveLabelID: %v", err)
	}
	if id != testAttentionID {
		t.Errorf("id=%q, want %q", id, testAttentionID)
	}
	// Second call uses cache.
	id2, err := s.resolveLabelID(context.Background(), testAttentionName)
	if err != nil {
		t.Fatalf("resolveLabelID (cached): %v", err)
	}
	if id2 != id {
		t.Errorf("cached id=%q, want %q", id2, id)
	}
}

func TestResolveLabelIDNoBoardID(t *testing.T) {
	s := newTestServer(t, "http://api.trello.invalid")
	s.cfg.TrelloBoardID = ""
	_, err := s.resolveLabelID(context.Background(), "attention")
	if err == nil {
		t.Error("expected error when board_id not configured")
	}
}

func TestHTTPHandler(t *testing.T) {
	s := newTestServer(t, "http://api.trello.invalid")
	h := s.HTTPHandler()
	req := httptest.NewRequest("GET", "/health", nil)
	rec := httptest.NewRecorder()
	h.ServeHTTP(rec, req)
	if rec.Code != 200 {
		t.Errorf("code=%d, want 200", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), `"status":"ok"`) {
		t.Errorf("body=%q", rec.Body.String())
	}
}

// ---------- opencode driver tests ----------

func TestOpenCodeDriverCreateSession(t *testing.T) {
	oc := &fakeOpencode{sessionID: "ses_abc"}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	d, _ := newOpenCodeDriver(
		map[string]any{"base_url": srv.URL},
		func(string) string { return "" },
		&http.Client{},
	)
	id, err := d.CreateSession(context.Background(), "/tmp", nil)
	if err != nil {
		t.Fatal(err)
	}
	if id != "ses_abc" {
		t.Errorf("id=%q", id)
	}
}

func TestOpenCodeDriverSendPromptUsesModel(t *testing.T) {
	oc := &fakeOpencode{sessionID: "ses1"}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	d, _ := newOpenCodeDriver(
		map[string]any{
			"base_url":      srv.URL,
			"default_model": map[string]any{"providerID": "test-prov", "modelID": "test-mod"},
		},
		func(string) string { return "" },
		&http.Client{},
	)
	err := d.SendPrompt(context.Background(), "ses1", "hello", nil)
	if err != nil {
		t.Fatalf("SendPrompt: %v", err)
	}
	oc.mu.Lock()
	defer oc.mu.Unlock()
	if len(oc.promptCalls) != 1 {
		t.Fatalf("expected 1 prompt call")
	}
	if !strings.Contains(oc.promptCalls[0].Model, "test-prov") {
		t.Errorf("model=%q, want contains test-prov", oc.promptCalls[0].Model)
	}
}

func TestOpenCodeDriverSessionStateRunning(t *testing.T) {
	oc := &fakeOpencode{message: nil} // no message → running
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	d, _ := newOpenCodeDriver(map[string]any{"base_url": srv.URL}, func(string) string { return "" }, &http.Client{})
	state, err := d.SessionState(context.Background(), "ses1")
	if err != nil {
		t.Fatal(err)
	}
	if state.Kind != "running" {
		t.Errorf("kind=%q, want running", state.Kind)
	}
}

func TestOpenCodeDriverSessionStateFinished(t *testing.T) {
	oc := &fakeOpencode{message: makeFinishMsg("stop")}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	d, _ := newOpenCodeDriver(map[string]any{"base_url": srv.URL}, func(string) string { return "" }, &http.Client{})
	state, err := d.SessionState(context.Background(), "ses1")
	if err != nil {
		t.Fatal(err)
	}
	if state.Kind != "finished" {
		t.Errorf("kind=%q, want finished", state.Kind)
	}
	if state.RawFinish != "stop" {
		t.Errorf("rawFinish=%q, want stop", state.RawFinish)
	}
}

func TestOpenCodeDriverSessionStateFailed(t *testing.T) {
	for _, finish := range []string{"length", "content-filter", "error", "unknown"} {
		t.Run(finish, func(t *testing.T) {
			oc := &fakeOpencode{message: makeFinishMsg(finish)}
			srv := httptest.NewServer(oc.handler())
			defer srv.Close()
			d, _ := newOpenCodeDriver(map[string]any{"base_url": srv.URL}, func(string) string { return "" }, &http.Client{})
			state, err := d.SessionState(context.Background(), "ses1")
			if err != nil {
				t.Fatal(err)
			}
			if state.Kind != "failed" {
				t.Errorf("kind=%q, want failed (finish=%s)", state.Kind, finish)
			}
		})
	}
}
