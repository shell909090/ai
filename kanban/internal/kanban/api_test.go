package kanban

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// ---------- trelloTestServer ----------

// trelloTestServer is a minimal fake Trello HTTP server for TrelloGateway unit tests.
type trelloTestServer struct {
	comments  []string
	moves     []struct{ cardID, listID string }
	labelAdds []string
}

func (f *trelloTestServer) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/1/cards", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		var body struct{ Name, Desc string }
		_ = json.NewDecoder(r.Body).Decode(&body)
		_ = json.NewEncoder(w).Encode(map[string]any{"id": "new_card", "name": body.Name, "idList": "list_todo"})
	})
	mux.HandleFunc("/1/cards/", func(w http.ResponseWriter, r *http.Request) {
		path := strings.TrimPrefix(r.URL.Path, "/1/cards/")
		parts := strings.SplitN(path, "/", 2)
		cardID := parts[0]
		suffix := ""
		if len(parts) == 2 {
			suffix = "/" + parts[1]
		}
		switch {
		case suffix == "/actions/comments" && r.Method == http.MethodPost:
			var body struct {
				Text string `json:"text"`
			}
			_ = json.NewDecoder(r.Body).Decode(&body)
			f.comments = append(f.comments, body.Text)
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{}`))
		case suffix == "" && r.Method == http.MethodPut:
			var body struct {
				IDList string `json:"idList"`
			}
			_ = json.NewDecoder(r.Body).Decode(&body)
			f.moves = append(f.moves, struct{ cardID, listID string }{cardID, body.IDList})
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{}`))
		case suffix == "/idLabels" && r.Method == http.MethodPost:
			var body struct {
				Value string `json:"value"`
			}
			_ = json.NewDecoder(r.Body).Decode(&body)
			f.labelAdds = append(f.labelAdds, body.Value)
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	})
	mux.HandleFunc("/1/lists/", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		// Return a fixed list of cards.
		cards := []map[string]any{
			{"id": "c1", "name": "First", "desc": "", "idList": "list_doing", "url": "", "labels": []any{}},
		}
		_ = json.NewEncoder(w).Encode(cards)
	})
	mux.HandleFunc("/1/boards/", func(w http.ResponseWriter, r *http.Request) {
		labels := []map[string]string{
			{"id": "lbl_attn", "name": "attention", "color": "red"},
			{"id": "lbl_human", "name": "human", "color": "green"},
		}
		_ = json.NewEncoder(w).Encode(labels)
	})
	return mux
}

func newTrelloGatewayForTest(t *testing.T, serverURL string) *TrelloGateway {
	t.Helper()
	cfg := Config{
		TrelloKey:     "k",
		TrelloToken:   "t",
		TrelloBoardID: "board_test",
		TrelloLists: map[string]string{
			"todo":  "list_todo",
			"doing": "list_doing",
			"done":  "list_done",
		},
		TrelloLabels: map[string]string{
			"attention": "attention",
		},
	}
	httpc := &http.Client{
		Transport: &rewriteTransport{base: http.DefaultTransport, target: serverURL},
	}
	return NewTrelloGateway(cfg, httpc)
}

// rewriteTransport redirects api.trello.com to the test server.
type rewriteTransport struct {
	base   http.RoundTripper
	target string
}

func (r *rewriteTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if strings.HasPrefix(req.URL.String(), "https://api.trello.com/") {
		newURL := r.target + strings.TrimPrefix(req.URL.String(), "https://api.trello.com")
		req = req.Clone(req.Context())
		req.URL, _ = req.URL.Parse(newURL)
		req.Host = req.URL.Host
	}
	return r.base.RoundTrip(req)
}

// ---------- TrelloGateway tests ----------

func TestTrelloGatewayListCards(t *testing.T) {
	fake := &trelloTestServer{}
	srv := httptest.NewServer(fake.handler())
	defer srv.Close()

	gw := newTrelloGatewayForTest(t, srv.URL)
	cards, err := gw.ListCards(context.Background(), "doing")
	if err != nil {
		t.Fatal(err)
	}
	if len(cards) != 1 || string(cards[0].ID) != "c1" {
		t.Errorf("cards=%v", cards)
	}
}

func TestTrelloGatewayListCardsError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	gw := newTrelloGatewayForTest(t, srv.URL)
	_, err := gw.ListCards(context.Background(), "doing")
	if err == nil {
		t.Fatal("expected error on 500")
	}
}

func TestTrelloGatewayListCardsUnknownList(t *testing.T) {
	gw := newTrelloGatewayForTest(t, "http://trello.invalid")
	_, err := gw.ListCards(context.Background(), "nosuchlist")
	if err == nil {
		t.Fatal("expected error for unknown list")
	}
}

func TestTrelloGatewayAddComment(t *testing.T) {
	fake := &trelloTestServer{}
	srv := httptest.NewServer(fake.handler())
	defer srv.Close()

	gw := newTrelloGatewayForTest(t, srv.URL)
	if err := gw.AddComment(context.Background(), "c1", "hello"); err != nil {
		t.Fatal(err)
	}
	if len(fake.comments) != 1 || fake.comments[0] != "hello" {
		t.Errorf("comments=%v", fake.comments)
	}
}

func TestTrelloGatewayAddCommentError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	gw := newTrelloGatewayForTest(t, srv.URL)
	if err := gw.AddComment(context.Background(), "c1", "hi"); err == nil {
		t.Error("expected error on 500")
	}
}

func TestTrelloGatewayMoveCard(t *testing.T) {
	fake := &trelloTestServer{}
	srv := httptest.NewServer(fake.handler())
	defer srv.Close()

	gw := newTrelloGatewayForTest(t, srv.URL)
	if err := gw.MoveCard(context.Background(), "c1", "done"); err != nil {
		t.Fatal(err)
	}
	if len(fake.moves) != 1 || fake.moves[0].listID != "list_done" {
		t.Errorf("moves=%v", fake.moves)
	}
}

func TestTrelloGatewayMoveCardError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	gw := newTrelloGatewayForTest(t, srv.URL)
	if err := gw.MoveCard(context.Background(), "c1", "done"); err == nil {
		t.Error("expected error on 500")
	}
}

func TestTrelloGatewayAddLabel(t *testing.T) {
	fake := &trelloTestServer{}
	srv := httptest.NewServer(fake.handler())
	defer srv.Close()

	gw := newTrelloGatewayForTest(t, srv.URL)
	// "attention" label name should be resolved to "lbl_attn" internally.
	if err := gw.AddLabel(context.Background(), "c1", "attention"); err != nil {
		t.Fatal(err)
	}
	if len(fake.labelAdds) != 1 || fake.labelAdds[0] != "lbl_attn" {
		t.Errorf("labelAdds=%v, want [lbl_attn]", fake.labelAdds)
	}
}

func TestTrelloGatewayAddLabelUnknown(t *testing.T) {
	fake := &trelloTestServer{}
	srv := httptest.NewServer(fake.handler())
	defer srv.Close()

	gw := newTrelloGatewayForTest(t, srv.URL)
	err := gw.AddLabel(context.Background(), "c1", "notexist")
	if err == nil {
		t.Fatal("expected error for unknown label")
	}
}

func TestTrelloGatewayResolveLabelIDCaching(t *testing.T) {
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.Contains(r.URL.Path, "/boards/") {
			calls++
		}
		labels := []map[string]string{{"id": "lbl_attn", "name": "attention", "color": "red"}}
		_ = json.NewEncoder(w).Encode(labels)
	}))
	defer srv.Close()

	gw := newTrelloGatewayForTest(t, srv.URL)
	// First resolution fetches from board.
	id1, err := gw.resolveLabelID(context.Background(), "attention")
	if err != nil || id1 != "lbl_attn" {
		t.Fatalf("first resolve: err=%v id=%q", err, id1)
	}
	// Second resolution uses cache — no additional board API call.
	id2, err := gw.resolveLabelID(context.Background(), "attention")
	if err != nil || id2 != id1 {
		t.Fatalf("second resolve: err=%v id=%q", err, id2)
	}
	if calls > 1 {
		t.Errorf("board labels fetched %d times, want 1 (cached)", calls)
	}
}

func TestTrelloGatewayResolveLabelIDNoBoardID(t *testing.T) {
	cfg := Config{
		TrelloKey:   "k",
		TrelloToken: "t",
		TrelloLists: map[string]string{"todo": "L1", "doing": "L2", "done": "L3"},
	}
	gw := NewTrelloGateway(cfg, &http.Client{})
	_, err := gw.resolveLabelID(context.Background(), "attention")
	if err == nil {
		t.Error("expected error when board_id not configured")
	}
}

// ---------- HTTPHandler ----------

func TestHTTPHandler(t *testing.T) {
	s := newTestServer(t, newFakeBoardGateway())
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

func testOpenCodeRaw(baseURL string) map[string]any {
	return map[string]any{
		"base_url":      baseURL,
		"default_model": map[string]any{"providerID": "test-prov", "modelID": "test-mod"},
	}
}

func TestOpenCodeDriverCreateSession(t *testing.T) {
	oc := &fakeOpencode{sessionID: "ses_abc"}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	d, _ := newOpenCodeDriver(
		testOpenCodeRaw(srv.URL),
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
		testOpenCodeRaw(srv.URL),
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

func TestOpenCodeDriverRequiresDefaultModel(t *testing.T) {
	_, err := newOpenCodeDriver(map[string]any{"base_url": "http://example.test"}, func(string) string { return "" }, &http.Client{})
	if err == nil || !strings.Contains(err.Error(), "default_model") {
		t.Fatalf("err=%v, want default_model validation error", err)
	}
}

func TestOpenCodeDriverValidatesAllowedModels(t *testing.T) {
	raw := testOpenCodeRaw("http://example.test")
	raw["allowed_models"] = []any{map[string]any{"label": "model:bad", "providerID": "p"}}
	_, err := newOpenCodeDriver(raw, func(string) string { return "" }, &http.Client{})
	if err == nil || !strings.Contains(err.Error(), "allowed_models") {
		t.Fatalf("err=%v, want allowed_models validation error", err)
	}
}

func TestOpenCodeDriverSessionStateRunning(t *testing.T) {
	oc := &fakeOpencode{message: nil} // no message → running
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	d, _ := newOpenCodeDriver(testOpenCodeRaw(srv.URL), func(string) string { return "" }, &http.Client{})
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
	d, _ := newOpenCodeDriver(testOpenCodeRaw(srv.URL), func(string) string { return "" }, &http.Client{})
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
			d, _ := newOpenCodeDriver(testOpenCodeRaw(srv.URL), func(string) string { return "" }, &http.Client{})
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
