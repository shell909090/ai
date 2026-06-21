package kanban

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestProcessCard(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{sessionID: "ses_proc"}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", cardName: "n1", status: statusStarted}
	card := trelloCard{ID: "c1", Name: "n1", Desc: "do the thing"}
	s.processCard(context.Background(), card)

	s.mu.Lock()
	defer s.mu.Unlock()
	info, ok := s.cardSessions["c1"]
	if !ok {
		t.Fatal("c1 not in cardSessions")
	}
	if info.sessionID != "ses_proc" {
		t.Errorf("sessionID=%q, want ses_proc", info.sessionID)
	}
	if info.startedAt.IsZero() {
		t.Error("startedAt should be set")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.comments) != 1 {
		t.Fatalf("expected Started comment, got %d", len(trello.comments))
	}
	if !strings.Contains(trello.comments[0], "▶️ Started session [ses_proc](") {
		t.Errorf("comment=%q, want markdown link to session", trello.comments[0])
	}
	oc.mu.Lock()
	defer oc.mu.Unlock()
	if len(oc.renames) != 1 {
		t.Fatalf("expected 1 rename, got %d", len(oc.renames))
	}
	if oc.renames[0].SessionID != "ses_proc" || oc.renames[0].Title != "n1" {
		t.Errorf("rename=%+v, want ses_proc/n1", oc.renames[0])
	}
}

func TestProcessCardRenameFailureContinues(t *testing.T) {
	// Rename failure must be best-effort: the scheduler still posts
	// the Started comment, still sends the prompt, and still maps
	// the session. Only the rename log is emitted as failure.
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{sessionID: "ses_proc", renameStatusCode: http.StatusInternalServerError}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	log := &drainLog{}
	withLogWriter(t, log)
	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", cardName: "n1", status: statusStarted}
	card := trelloCard{ID: "c1", Name: "n1", Desc: "do the thing"}
	s.processCard(context.Background(), card)

	if !strings.Contains(log.String(), "session.rename.fail") {
		t.Errorf("expected session.rename.fail log, got %s", log.String())
	}
	if _, ok := s.cardSessions["c1"]; !ok {
		t.Error("card should still be in cardSessions despite rename failure")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.comments) != 1 {
		t.Errorf("Started comment should still be written, got %d", len(trello.comments))
	}
}

func TestProcessCardSessionError(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()

	s, _ := newTestServerWithFake(t, srv.URL, trURL.URL)
	card := trelloCard{ID: "c1", Name: "n1"}
	s.processCard(context.Background(), card)

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("c1 should be removed on session error")
	}
}

func TestProcessCardPromptError(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	mux := http.NewServeMux()
	mux.HandleFunc("/session", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"id":"ses_p"}`))
	})
	mux.HandleFunc("/session/", func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/prompt_async") {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		_, _ = w.Write([]byte(`[]`))
	})
	ocURL := httptest.NewServer(mux)
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", cardName: "n1", status: statusStarted}
	card := trelloCard{ID: "c1", Name: "n1", Desc: "x"}
	s.processCard(context.Background(), card)

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("c1 should be removed on prompt error")
	}
}

func TestPollOnceNoNew(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.pollOnce(context.Background())

	s.mu.Lock()
	defer s.mu.Unlock()
	if len(s.cardSessions) != 0 {
		t.Errorf("cardSessions=%v, want empty", s.cardSessions)
	}
}

func TestPollOncePollError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	log := &drainLog{}
	withLogWriter(t, log)
	s.pollOnce(context.Background())
	if !strings.Contains(log.String(), "poll.error") {
		t.Errorf("expected poll.error log, got %s", log.String())
	}
}

func TestPollOnceNewCardTriggersProcess(t *testing.T) {
	trello := newFakeTrello()
	trello.setCards(doingID, []trelloCard{{ID: "c1", Name: "first"}})
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{sessionID: "ses_xyz"}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.pollOnce(context.Background())

	// pollOnce starts processCard in a goroutine; wait for it.
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		s.mu.Lock()
		_, ok := s.sessionCards["ses_xyz"]
		s.mu.Unlock()
		if ok {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	s.mu.Lock()
	if _, ok := s.cardSessions["c1"]; !ok {
		t.Error("c1 should be in cardSessions after poll")
	}
	if _, ok := s.sessionCards["ses_xyz"]; !ok {
		t.Error("ses_xyz should be in sessionCards after processCard")
	}
	s.mu.Unlock()
}
