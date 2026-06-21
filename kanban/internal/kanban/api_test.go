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
	trello.setCards(doingID, []trelloCard{{ID: "c1", Name: "first"}})
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
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
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	_, err := s.trelloListCards(context.Background(), doingID)
	if err == nil {
		t.Fatal("expected error on 500")
	}
}

func TestTrelloAddComment(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
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
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	if err := s.trelloAddComment(context.Background(), "c1", "hi"); err == nil {
		t.Error("expected error on 500")
	}
}

func TestTrelloMoveCard(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	if err := s.trelloMoveCard(context.Background(), "c1", doneID); err != nil {
		t.Fatal(err)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0] != (moveRec{cardID: "c1", listID: doneID}) {
		t.Errorf("moves=%v, want [{c1 %s}]", trello.moves, doneID)
	}
}

func TestTrelloMoveCardError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	if err := s.trelloMoveCard(context.Background(), "c1", doneID); err == nil {
		t.Error("expected error on 500")
	}
}

func TestTrelloAddLabel(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
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
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
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

func TestTrelloListLabelsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	if _, err := s.trelloListLabels(context.Background()); err == nil {
		t.Error("expected error on 500")
	}
}

func TestTrelloCreateLabelError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	if _, err := s.trelloCreateLabel(context.Background(), "foo", "red"); err == nil {
		t.Error("expected error on 500")
	}
}

func TestLoadLabels(t *testing.T) {
	trello := newFakeTrello()
	trello.labelExists["needs-attention"] = "pre_existing"
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
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
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
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
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
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
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
	_, err := s.ocCreateSession(context.Background())
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestOcGetLastMessageEmpty(t *testing.T) {
	oc := &fakeOpencode{}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
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
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
	last, err := s.ocGetLastMessage(context.Background(), "ses1")
	if err != nil {
		t.Fatal(err)
	}
	if ExtractFinish(last) != "stop" {
		t.Errorf("ExtractFinish=%q, want stop", ExtractFinish(last))
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
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", oc.URL)
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
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", oc.URL)
	if err := s.ocSendPromptAsync(context.Background(), "ses1", "hello"); err == nil {
		t.Fatal("expected error on 500")
	}
}

func TestHTTPHandler(t *testing.T) {
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", "http://opencode.invalid")
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
