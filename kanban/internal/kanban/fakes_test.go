package kanban

import (
	"encoding/json"
	"net/http"
	"net/url"
	"strings"
	"sync"
	"time"
)

// Test list and label IDs used consistently across all tests.
const (
	testTodoID        = "list_todo"
	testDoingID       = "list_doing"
	testDoneID        = "list_done"
	testBoardID       = "board_test"
	testAttentionName = "attention"
	testHumanName     = "human"
	testAttentionID   = "lbl_attention"
)

// fakeTrello is a minimal Trello stand-in for tests.
type fakeTrello struct {
	mu          sync.Mutex
	comments    []string
	labelAdds   []string
	moves       []moveRec
	cardsByList map[string][]trelloCard
}

type moveRec struct {
	cardID string
	listID string
}

func newFakeTrello() *fakeTrello {
	return &fakeTrello{
		cardsByList: map[string][]trelloCard{},
	}
}

func (f *fakeTrello) setCards(listID string, cards []trelloCard) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.cardsByList[listID] = cards
}

func (f *fakeTrello) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/1/cards/", f.cardsHandler)
	mux.HandleFunc("/1/boards/", f.boardsHandler)
	mux.HandleFunc("/1/lists/", f.listsHandler)
	return mux
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
		f.moves = append(f.moves, moveRec{cardID: cardID, listID: body.IDList})
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

func (f *fakeTrello) boardsHandler(w http.ResponseWriter, r *http.Request) {
	if !strings.HasSuffix(r.URL.Path, "/labels") || r.Method != http.MethodGet {
		w.WriteHeader(http.StatusNotFound)
		return
	}
	// Return the attention label so resolveLabelID can find it.
	labels := []map[string]string{
		{"id": testAttentionID, "name": testAttentionName, "color": "red", "idBoard": testBoardID},
		{"id": "lbl_human", "name": testHumanName, "color": "green", "idBoard": testBoardID},
	}
	_ = json.NewEncoder(w).Encode(labels)
}

func (f *fakeTrello) listsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet || !strings.HasSuffix(r.URL.Path, "/cards") {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	path := strings.TrimPrefix(r.URL.Path, "/1/lists/")
	listID := strings.TrimSuffix(path, "/cards")
	f.mu.Lock()
	cards := f.cardsByList[listID]
	f.mu.Unlock()
	if cards == nil {
		_, _ = w.Write([]byte(`[]`))
		return
	}
	_ = json.NewEncoder(w).Encode(cards)
}

// fakeOpencode is a minimal opencode stand-in for tests.
type fakeOpencode struct {
	mu            sync.Mutex
	sessionID     string
	message       map[string]any
	messagesQueue []map[string]any
	abortCalls    []string
	promptCalls   []promptCall
}

type promptCall struct {
	SessionID string
	Prompt    string
	Model     string
}

func (f *fakeOpencode) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/session", f.sessionHandler)
	mux.HandleFunc("/session/", f.subHandler)
	return mux
}

func (f *fakeOpencode) sessionHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	w.WriteHeader(http.StatusOK)
	id := f.sessionID
	if id == "" {
		id = "ses_fake"
	}
	_, _ = w.Write([]byte(`{"id":"` + id + `","directory":"/tmp","projectID":"p1"}`))
}

func (f *fakeOpencode) subHandler(w http.ResponseWriter, r *http.Request) {
	switch {
	case strings.HasSuffix(r.URL.Path, "/prompt_async") && r.Method == http.MethodPost:
		var body struct {
			Model struct {
				ProviderID string `json:"providerID"`
				ModelID    string `json:"modelID"`
			} `json:"model"`
			Parts []struct {
				Text string `json:"text"`
			} `json:"parts"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		parts := strings.Split(r.URL.Path, "/")
		sessionID := ""
		for i, p := range parts {
			if p == "session" && i+1 < len(parts) {
				sessionID = parts[i+1]
				break
			}
		}
		prompt := ""
		if len(body.Parts) > 0 {
			prompt = body.Parts[0].Text
		}
		f.mu.Lock()
		f.promptCalls = append(f.promptCalls, promptCall{
			SessionID: sessionID,
			Prompt:    prompt,
			Model:     body.Model.ProviderID + "/" + body.Model.ModelID,
		})
		f.mu.Unlock()
		w.WriteHeader(http.StatusNoContent)

	case strings.HasSuffix(r.URL.Path, "/abort") && r.Method == http.MethodPost:
		parts := strings.Split(r.URL.Path, "/")
		sessionID := ""
		for i, p := range parts {
			if p == "session" && i+1 < len(parts) {
				sessionID = parts[i+1]
				break
			}
		}
		f.mu.Lock()
		f.abortCalls = append(f.abortCalls, sessionID)
		f.mu.Unlock()
		w.WriteHeader(http.StatusOK)

	case strings.HasSuffix(r.URL.Path, "/message") && r.Method == http.MethodGet:
		f.mu.Lock()
		var last map[string]any
		if len(f.messagesQueue) > 0 {
			last = f.messagesQueue[0]
			f.messagesQueue = f.messagesQueue[1:]
		} else {
			last = f.message
		}
		f.mu.Unlock()
		if last == nil {
			_, _ = w.Write([]byte(`[]`))
			return
		}
		data, _ := json.Marshal(last)
		_, _ = w.Write([]byte("[" + string(data) + "]"))

	default:
		w.WriteHeader(http.StatusNotFound)
	}
}

// rewriteTransport intercepts requests to https://api.trello.com and
// rewrites the host to the fake test server.
type rewriteTransport struct {
	base   http.RoundTripper
	target string
}

func (r *rewriteTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if strings.HasPrefix(req.URL.String(), "https://api.trello.com/") {
		newURL := r.target + strings.TrimPrefix(req.URL.String(), "https://api.trello.com")
		if u, err := url.Parse(newURL); err == nil {
			req.URL = u
			req.Host = u.Host
		}
	}
	return r.base.RoundTrip(req)
}

// drainLog captures log output for assertions.
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

func withLogWriter(t testingTB, w interface{ Write([]byte) (int, error) }) {
	t.Helper()
	old := defaultLogWriter
	defaultLogWriter = w
	t.Cleanup(func() { defaultLogWriter = old })
}

type testingTB interface {
	Helper()
	Cleanup(func())
}

// newTestServer builds a Server wired to the given fake Trello and opencode URLs.
func newTestServer(t interface {
	testingTB
	Fatal(...any)
}, trelloURL, ocURL string) *Server {
	t.Helper()
	httpc := &http.Client{
		Timeout:   2 * time.Second,
		Transport: &rewriteTransport{base: http.DefaultTransport, target: trelloURL},
	}
	cfg := Config{
		TrelloKey:          "k",
		TrelloToken:        "t",
		TrelloBoardID:      testBoardID,
		OpenCodeUser:       "u",
		OpenCodePass:       "p",
		OpenCodeBaseURL:    ocURL,
		WorkDir:            "/tmp",
		HTTPTimeout:        2 * time.Second,
		HTTPListen:         "127.0.0.1:0",
		PollInterval:       time.Second,
		AbortTimeout:       60 * time.Second,
		SummaryTimeout:     60 * time.Second,
		DefaultModel:       ModelRef{ProviderID: "test", ModelID: "model"},
		DefaultProj:        "default",
		MaxDoingTotal:      2,
		MaxDoingPerProject: 1,
		TrelloLists: map[string]string{
			"todo":  testTodoID,
			"doing": testDoingID,
			"done":  testDoneID,
		},
		TrelloLabels: map[string]string{
			"human":     testHumanName,
			"attention": testAttentionName,
		},
	}
	s, err := New(cfg)
	if err != nil {
		t.Fatal("New failed:", err)
	}
	s.httpc = httpc
	return s
}
