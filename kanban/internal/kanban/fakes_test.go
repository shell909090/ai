package kanban

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"time"
)

// ---------- fakeBoardGateway ----------

// fakeBoardGateway implements BoardGateway for tests.
// It records all operations and lets tests inspect and seed board state.
type fakeBoardGateway struct {
	mu           sync.Mutex
	comments     []string
	labelAdds    []string
	labelRemoves []string
	moves        []moveRec
	cardsByList  map[string][]CardSnapshot
	knownLabels  map[string]bool
	listCardsErr error // if non-nil, ListCards returns this error
	moveErr      error // if non-nil, MoveCard returns this error
	commentErr   error // if non-nil, AddComment returns this error
	labelErr     error // if non-nil, label mutations return this error
	createErr    error // if non-nil, CreateCard returns this error
}

type moveRec struct {
	cardID CardID
	list   string // logical list name
}

func newFakeBoardGateway() *fakeBoardGateway {
	return &fakeBoardGateway{
		cardsByList: make(map[string][]CardSnapshot),
		knownLabels: map[string]bool{
			"attention":   true,
			"human":       true,
			"proj:agent":  true,
			"proj:kanban": true,
		},
	}
}

func (f *fakeBoardGateway) setCards(listName string, cards []CardSnapshot) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.cardsByList[listName] = cards
}

func (f *fakeBoardGateway) ListCards(_ context.Context, listName string) ([]CardSnapshot, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.listCardsErr != nil {
		return nil, f.listCardsErr
	}
	cards := f.cardsByList[listName]
	if cards == nil {
		return []CardSnapshot{}, nil
	}
	return append([]CardSnapshot(nil), cards...), nil
}

func (f *fakeBoardGateway) GetCard(_ context.Context, id CardID) (CardSnapshot, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	for _, cards := range f.cardsByList {
		for _, c := range cards {
			if c.ID == id {
				return c, nil
			}
		}
	}
	return CardSnapshot{}, fmt.Errorf("card %s not found", id)
}

func (f *fakeBoardGateway) MoveCard(_ context.Context, id CardID, listName string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.moveErr != nil {
		return f.moveErr
	}
	f.moves = append(f.moves, moveRec{cardID: id, list: listName})
	return nil
}

func (f *fakeBoardGateway) AddComment(_ context.Context, _ CardID, text string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.commentErr != nil {
		return f.commentErr
	}
	f.comments = append(f.comments, text)
	return nil
}

func (f *fakeBoardGateway) AddLabel(_ context.Context, _ CardID, labelName string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.labelErr != nil {
		return f.labelErr
	}
	if !f.knownLabels[labelName] {
		return fmt.Errorf("%w: %s", ErrUnknownLabel, labelName)
	}
	f.labelAdds = append(f.labelAdds, labelName)
	return nil
}

func (f *fakeBoardGateway) RemoveLabel(_ context.Context, _ CardID, labelName string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.labelErr != nil {
		return f.labelErr
	}
	if !f.knownLabels[labelName] {
		return fmt.Errorf("%w: %s", ErrUnknownLabel, labelName)
	}
	f.labelRemoves = append(f.labelRemoves, labelName)
	return nil
}

func (f *fakeBoardGateway) CreateCard(_ context.Context, listName, title, description string, labels []string) (CardSnapshot, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.createErr != nil {
		return CardSnapshot{}, f.createErr
	}
	for _, labelName := range labels {
		if !f.knownLabels[labelName] {
			return CardSnapshot{}, fmt.Errorf("%w: %s", ErrUnknownLabel, labelName)
		}
	}
	card := CardSnapshot{
		ID:          "new_card_id",
		Title:       title,
		Description: description,
		List:        listName,
		Labels:      append([]string(nil), labels...),
	}
	f.cardsByList[listName] = append(f.cardsByList[listName], card)
	return card, nil
}

// ---------- fakeOpencode ----------

// fakeOpencode is a minimal opencode stand-in for tests.
// Used by opencode driver tests in api_test.go.
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

// ---------- fakeAgentDriver ----------

// fakeAgentDriver implements AgentDriver for tests.
type fakeAgentDriver struct {
	mu          sync.Mutex
	sessionID   string
	state       AgentState
	stateQueue  []AgentState
	abortCalls  []string
	promptCalls []agentPromptCall
	createErr   error
	abortErr    error
	promptErr   error
}

type agentPromptCall struct {
	SessionID string
	Prompt    string
	Labels    []string
}

func (f *fakeAgentDriver) CreateSession(_ context.Context, _ string, _ []string) (string, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.createErr != nil {
		return "", f.createErr
	}
	id := f.sessionID
	if id == "" {
		id = "ses_fake"
	}
	return id, nil
}

func (f *fakeAgentDriver) AbortSession(_ context.Context, sessionID string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.abortCalls = append(f.abortCalls, sessionID)
	return f.abortErr
}

func (f *fakeAgentDriver) SendPrompt(_ context.Context, sessionID, prompt string, labels []string) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.promptCalls = append(f.promptCalls, agentPromptCall{SessionID: sessionID, Prompt: prompt, Labels: append([]string(nil), labels...)})
	return f.promptErr
}

func (f *fakeAgentDriver) SessionState(_ context.Context, _ string) (AgentState, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.stateQueue) > 0 {
		s := f.stateQueue[0]
		f.stateQueue = f.stateQueue[1:]
		return s, nil
	}
	return f.state, nil
}

// ---------- drainLog ----------

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

// ---------- fakeHookRunner ----------

// fakeHookRunner is an injectable HookRunner for tests.
type fakeHookRunner struct {
	mu     sync.Mutex
	calls  []hookCall
	result HookResult
	err    error
}

type hookCall struct {
	Event   string
	CardID  CardID
	Proj    string
	Workdir string
}

func (f *fakeHookRunner) RunHook(_ context.Context, event string, _ *Task, card CardSnapshot,
	proj AllowedProject, agentName, agentType string, workdir string, _ ProjectConfig) (HookResult, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.calls = append(f.calls, hookCall{Event: event, CardID: card.ID, Proj: proj.Name, Workdir: workdir})
	return f.result, f.err
}

// ---------- test server helpers ----------

// newTestServer builds a Server wired to the given fake BoardGateway.
func newTestServer(t interface {
	testingTB
	Fatal(...any)
}, board BoardGateway) *Server {
	t.Helper()
	cfg := Config{
		TrelloKey:          "k",
		TrelloToken:        "t",
		TrelloBoardID:      "board_test",
		HTTPTimeout:        2 * time.Second,
		HTTPListen:         "127.0.0.1:0",
		PollInterval:       time.Second,
		AbortTimeout:       60 * time.Second,
		SummaryTimeout:     60 * time.Second,
		HookDefaultTimeout: 5 * time.Second,
		HookMaxOutputBytes: 4096,
		DefaultAgent:       "test-agent",
		Agents:             map[string]AgentConfig{"test-agent": {Type: "fake"}},
		MaxDoingTotal:      2,
		MaxDoingPerProject: 1,
		TrelloLists: map[string]string{
			"todo":  "list_todo",
			"doing": "list_doing",
			"done":  "list_done",
		},
		TrelloLabels: map[string]string{
			"human":     "human",
			"attention": "attention",
		},
	}
	s, err := New(cfg)
	if err != nil {
		t.Fatal("New failed:", err)
	}
	s.SetBoard(board)
	s.hookRunner = &fakeHookRunner{}
	s.drivers = map[string]AgentDriver{"test-agent": &fakeAgentDriver{}}
	return s
}

// newFakeHTTPServer starts an httptest.Server with the given handler and registers cleanup.
// Used by opencode driver tests.
func newFakeHTTPServer(t interface {
	testingTB
	Helper()
	Cleanup(func())
}, h http.HandlerFunc) string {
	t.Helper()
	srv := httptest.NewServer(h)
	t.Cleanup(srv.Close)
	return srv.URL
}
