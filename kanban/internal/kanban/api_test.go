package kanban

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
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
	// Body must carry the binding's DefaultModel so opencode can route
	// the prompt to the right provider/model.
	if !strings.Contains(receivedBody, `"providerID":"opencode-go"`) {
		t.Errorf("body missing providerID, got %q", receivedBody)
	}
	if !strings.Contains(receivedBody, `"modelID":"minimax-m3"`) {
		t.Errorf("body missing modelID, got %q", receivedBody)
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

// --- T017: ocRenameSession ---

func TestOcRenameSessionSuccess(t *testing.T) {
	var (
		gotPath     string
		gotQuery    url.Values
		gotTitle    string
		gotMethod   string
		gotUser     string
		gotPass     string
		gotAuthHdr  string
		gotCTHeader string
	)
	ocSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotQuery = r.URL.Query()
		gotMethod = r.Method
		gotUser, gotPass, _ = r.BasicAuth()
		gotAuthHdr = r.Header.Get("Authorization")
		gotCTHeader = r.Header.Get("Content-Type")
		body, _ := io.ReadAll(r.Body)
		var parsed struct {
			Title string `json:"title"`
		}
		_ = json.Unmarshal(body, &parsed)
		gotTitle = parsed.Title
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"id":"ses_x","title":"` + parsed.Title + `"}`))
	}))
	defer ocSrv.Close()

	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", ocSrv.URL)
	if err := s.ocRenameSession(context.Background(), "ses_x", "新标题"); err != nil {
		t.Fatalf("ocRenameSession: %v", err)
	}

	if gotMethod != http.MethodPatch {
		t.Errorf("method=%q, want PATCH", gotMethod)
	}
	if gotPath != "/session/ses_x" {
		t.Errorf("path=%q, want /session/ses_x", gotPath)
	}
	if gotQuery.Get("directory") != "/tmp" {
		t.Errorf("directory query=%q, want /tmp", gotQuery.Get("directory"))
	}
	if gotTitle != "新标题" {
		t.Errorf("title=%q, want 新标题", gotTitle)
	}
	if gotCTHeader != "application/json" {
		t.Errorf("Content-Type=%q, want application/json", gotCTHeader)
	}
	if !strings.Contains(gotAuthHdr, "Basic ") {
		t.Errorf("Authorization=%q, want Basic prefix", gotAuthHdr)
	}
	if gotUser != "u" || gotPass != "p" {
		t.Errorf("BasicAuth user=%q pass=%q, want u/p", gotUser, gotPass)
	}
}

func TestOcRenameSessionFailure(t *testing.T) {
	ocSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		_, _ = w.Write([]byte(`{"error":"boom"}`))
	}))
	defer ocSrv.Close()

	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", ocSrv.URL)
	err := s.ocRenameSession(context.Background(), "ses_x", "新标题")
	if err == nil {
		t.Fatal("expected error on 500, got nil")
	}
	if !strings.Contains(err.Error(), "500") {
		t.Errorf("error=%q, want 500 mentioned", err.Error())
	}
}
