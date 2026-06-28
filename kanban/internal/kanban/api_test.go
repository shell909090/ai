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
	s := newTestServer(t, srv.URL, "http://opencode.invalid")
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
	s := newTestServer(t, srv.URL, "http://opencode.invalid")
	_, err := s.trelloListCards(context.Background(), testDoingID)
	if err == nil {
		t.Fatal("expected error on 500")
	}
}

func TestTrelloAddComment(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newTestServer(t, srv.URL, "http://opencode.invalid")
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
	s := newTestServer(t, srv.URL, "http://opencode.invalid")
	if err := s.trelloAddComment(context.Background(), "c1", "hi"); err == nil {
		t.Error("expected error on 500")
	}
}

func TestTrelloMoveCard(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newTestServer(t, srv.URL, "http://opencode.invalid")
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
	s := newTestServer(t, srv.URL, "http://opencode.invalid")
	if err := s.trelloMoveCard(context.Background(), "c1", testDoneID); err == nil {
		t.Error("expected error on 500")
	}
}

func TestTrelloAddLabel(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newTestServer(t, srv.URL, "http://opencode.invalid")
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
	s := newTestServer(t, srv.URL, "http://opencode.invalid")
	got, err := s.trelloListBoardLabels(context.Background(), testBoardID)
	if err != nil {
		t.Fatal(err)
	}
	// fakeTrello always returns human + attention labels
	if len(got) != 2 {
		t.Errorf("len=%d, want 2", len(got))
	}
}

func TestTrelloListBoardLabelsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s := newTestServer(t, srv.URL, "http://opencode.invalid")
	if _, err := s.trelloListBoardLabels(context.Background(), testBoardID); err == nil {
		t.Error("expected error on 500")
	}
}

func TestResolveLabelID(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s := newTestServer(t, srv.URL, "http://opencode.invalid")

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
	s := newTestServer(t, "http://api.trello.invalid", "http://opencode.invalid")
	s.cfg.TrelloBoardID = ""
	_, err := s.resolveLabelID(context.Background(), "attention")
	if err == nil {
		t.Error("expected error when board_id not configured")
	}
}

func TestOcCreateSessionReturnsSessionID(t *testing.T) {
	oc := &fakeOpencode{sessionID: "ses_xyz"}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s := newTestServer(t, "http://api.trello.invalid", srv.URL)
	id, err := s.ocCreateSession(context.Background(), ModelRef{ProviderID: "p", ModelID: "m"}, "")
	if err != nil {
		t.Fatal(err)
	}
	if id != "ses_xyz" {
		t.Errorf("id=%q, want ses_xyz", id)
	}
}

func TestOcCreateSessionBadID(t *testing.T) {
	oc := &fakeOpencode{sessionID: "not-prefixed"}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s := newTestServer(t, "http://api.trello.invalid", srv.URL)
	_, err := s.ocCreateSession(context.Background(), ModelRef{ProviderID: "p", ModelID: "m"}, "")
	if err == nil {
		t.Fatal("expected error for bad session id prefix")
	}
}

func TestOcCreateSessionError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s := newTestServer(t, "http://api.trello.invalid", srv.URL)
	_, err := s.ocCreateSession(context.Background(), ModelRef{ProviderID: "p", ModelID: "m"}, "")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestOcGetLastMessageEmpty(t *testing.T) {
	oc := &fakeOpencode{}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s := newTestServer(t, "http://api.trello.invalid", srv.URL)
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
		"info": map[string]any{"finish": "stop"},
	}}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s := newTestServer(t, "http://api.trello.invalid", srv.URL)
	last, err := s.ocGetLastMessage(context.Background(), "ses1")
	if err != nil {
		t.Fatal(err)
	}
	if ExtractFinish(last) != "stop" {
		t.Errorf("ExtractFinish=%q, want stop", ExtractFinish(last))
	}
}

func TestOcSendPromptBody(t *testing.T) {
	var receivedBody string
	ocSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body := make([]byte, 4096)
		n, _ := r.Body.Read(body)
		receivedBody = string(body[:n])
		w.WriteHeader(http.StatusNoContent)
	}))
	defer ocSrv.Close()
	s := newTestServer(t, "http://api.trello.invalid", ocSrv.URL)
	model := ModelRef{ProviderID: "my-prov", ModelID: "my-model"}
	if err := s.ocSendPrompt(context.Background(), "ses1", model, "hello world"); err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(receivedBody, "hello world") {
		t.Errorf("body should contain prompt, got %q", receivedBody)
	}
	if !strings.Contains(receivedBody, `"providerID":"my-prov"`) {
		t.Errorf("body missing providerID, got %q", receivedBody)
	}
	if !strings.Contains(receivedBody, `"modelID":"my-model"`) {
		t.Errorf("body missing modelID, got %q", receivedBody)
	}
}

func TestOcSendPromptError(t *testing.T) {
	ocSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer ocSrv.Close()
	s := newTestServer(t, "http://api.trello.invalid", ocSrv.URL)
	if err := s.ocSendPrompt(context.Background(), "ses1", ModelRef{}, "hi"); err == nil {
		t.Fatal("expected error on 500")
	}
}

func TestOcAbortSession(t *testing.T) {
	oc := &fakeOpencode{}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s := newTestServer(t, "http://api.trello.invalid", srv.URL)
	if err := s.ocAbortSession(context.Background(), "ses1"); err != nil {
		t.Fatal(err)
	}
	oc.mu.Lock()
	defer oc.mu.Unlock()
	if len(oc.abortCalls) != 1 {
		t.Errorf("expected 1 abort call, got %d", len(oc.abortCalls))
	}
}

func TestHTTPHandler(t *testing.T) {
	s := newTestServer(t, "http://api.trello.invalid", "http://opencode.invalid")
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
