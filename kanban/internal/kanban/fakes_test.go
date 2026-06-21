package kanban

import (
	"encoding/json"
	"net/http"
	"net/url"
	"strings"
	"sync"
)

// fakeTrello is a minimal Trello stand-in for tests. It records every
// call and returns canned responses. cardsByList separates the canned
// card sets per Trello list id so a test can pre-load doing and todo
// independently.
type fakeTrello struct {
	mu          sync.Mutex
	comments    []string
	labelAdds   []string
	moves       []moveRec
	labelExists map[string]string
	cardsByList map[string][]trelloCard
}

type moveRec struct {
	cardID string
	listID string
}

func newFakeTrello() *fakeTrello {
	return &fakeTrello{
		labelExists: map[string]string{},
		cardsByList: map[string][]trelloCard{},
	}
}

// setCards pre-loads a list id with the given cards. Use this in
// tests instead of touching the unexported cardsByList directly.
func (f *fakeTrello) setCards(listID string, cards []trelloCard) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.cardsByList[listID] = cards
}

func (f *fakeTrello) handler() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/1/cards/", f.cardsHandler)
	mux.HandleFunc("/1/labels", f.labelsHandler)
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

func (f *fakeTrello) boardsHandler(w http.ResponseWriter, r *http.Request) {
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

func (f *fakeTrello) listsHandler(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	if !strings.HasSuffix(r.URL.Path, "/cards") {
		w.WriteHeader(http.StatusNotFound)
		return
	}
	// URL is /1/lists/{listID}/cards
	path := strings.TrimPrefix(r.URL.Path, "/1/lists/")
	listID := strings.TrimSuffix(path, "/cards")
	f.mu.Lock()
	defer f.mu.Unlock()
	cards := f.cardsByList[listID]
	if cards == nil {
		_, _ = w.Write([]byte(`[]`))
		return
	}
	_ = json.NewEncoder(w).Encode(cards)
}

// fakeOpencode is a minimal opencode stand-in. It serves /session and
// renameCall records a single PATCH /session/{id} request handled by
// the fake opencode, so tests can assert that the scheduler issued
// the rename and used the right body.
type renameCall struct {
	SessionID string
	Title     string
	Directory string
}

// /session/* from canned responses so we can test the scheduler
// without a real opencode server. The /session/{id}/message endpoint
// pulls from messagesQueue first (FIFO) and falls back to message
// when the queue is empty, so tests can drive multi-step flows like
// "first finish → summary prompt → summary response". The PATCH
// /session/{id} (rename) endpoint records into renames and responds
// 200 by default; tests can set renameStatusCode to simulate failure.
type fakeOpencode struct {
	sessionID        string
	message          map[string]any
	messagesQueue    []map[string]any
	renames          []renameCall
	renameStatusCode int // default 200 when 0
	mu               sync.Mutex
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
	_, _ = w.Write([]byte(`{"id":"` + f.sessionID + `","directory":"/tmp","projectID":"p1"}`))
}

func (f *fakeOpencode) subHandler(w http.ResponseWriter, r *http.Request) {
	switch {
	case strings.HasSuffix(r.URL.Path, "/prompt_async"):
		w.WriteHeader(http.StatusNoContent)
	case strings.HasSuffix(r.URL.Path, "/message"):
		if r.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
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
	case r.Method == http.MethodPatch && strings.HasPrefix(r.URL.Path, "/session/"):
		// PATCH /session/{id}?directory=... (rename)
		var body struct {
			Title string `json:"title"`
		}
		_ = json.NewDecoder(r.Body).Decode(&body)
		parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/session/"), "/")
		f.mu.Lock()
		f.renames = append(f.renames, renameCall{
			SessionID: parts[0],
			Title:     body.Title,
			Directory: r.URL.Query().Get("directory"),
		})
		code := f.renameStatusCode
		f.mu.Unlock()
		if code == 0 {
			code = http.StatusOK
		}
		w.WriteHeader(code)
		if code >= 300 {
			_, _ = w.Write([]byte(`{"error":"simulated"}`))
		} else {
			_, _ = w.Write([]byte(`{"id":"` + parts[0] + `","title":"` + body.Title + `"}`))
		}
	default:
		w.WriteHeader(http.StatusNotFound)
	}
}

// rewriteTransport intercepts requests to https://api.trello.com and
// rewrites the host to a test server. Other hosts pass through
// unchanged.
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

// drainLog captures everything written to it for later assertion.
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

// withLogWriter swaps defaultLogWriter for the duration of the test.
func withLogWriter(t testingTB, w interface{ Write([]byte) (int, error) }) {
	t.Helper()
	old := defaultLogWriter
	defaultLogWriter = w
	t.Cleanup(func() { defaultLogWriter = old })
}

// testingTB is the minimal interface satisfied by *testing.T and
// *testing.B.
type testingTB interface {
	Helper()
	Cleanup(func())
}
