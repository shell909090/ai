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

// TestPollOnceNewDoingRespectsCap is the regression test for the
// T018 bug: humans can drag cards straight into doing, bypassing
// the auto-promote cap check. Step 2 must apply the same
// MaxDoingPerProject / MaxDoingTotal enforcement as Step 3 and
// push the card back to todo with a "并发上限" comment.
func TestPollOnceNewDoingRespectsCap(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	// Trello shows two proj:agent cards in doing. cardSessions
	// already has c_full registered (the pre-existing in-flight
	// card); c_new is the brand-new drag-in that must be rejected
	// because the per-project cap is hit.
	trello.setCards(doingID, []trelloCard{
		{ID: "c_full", Name: "c_full", Labels: []trelloLabel{{Name: "proj:agent"}}},
		{ID: "c_new", Name: "c_new", Labels: []trelloLabel{{Name: "proj:agent"}}},
	})
	trello.setCards(todoID, nil)

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c_full"] = &sessionInfo{cardID: "c_full", project: "agent", status: statusStarted, sessionID: "ses_full"}
	s.sessionCards["ses_full"] = "c_full"

	log := &drainLog{}
	withLogWriter(t, log)
	s.pollOnce(context.Background())

	// (a) no new session was started: c_new must not appear in
	// cardSessions (the reject path deliberately does not touch
	// cardSessions, so this is the strongest signal that the
	// helper fired before the register step).
	s.mu.Lock()
	if _, busy := s.cardSessions["c_new"]; busy {
		s.mu.Unlock()
		t.Fatal("c_new should not be in cardSessions after cap-reject")
	}
	if _, ok := s.sessionCards["ses_full"]; !ok {
		s.mu.Unlock()
		t.Fatal("prefilled c_full/ses_full should be untouched")
	}
	s.mu.Unlock()

	// (b) the new card was moved back to todo.
	trello.mu.Lock()
	defer trello.mu.Unlock()
	var movedToTodo bool
	for _, m := range trello.moves {
		if m.cardID == "c_new" && m.listID == todoID {
			movedToTodo = true
			break
		}
	}
	if !movedToTodo {
		t.Errorf("c_new should be moved to todo; moves=%v", trello.moves)
	}

	// (c) a comment containing "并发上限" was written before the
	// move, and a cap.reject log line was emitted.
	var capComment string
	for _, c := range trello.comments {
		if strings.Contains(c, "并发上限") {
			capComment = c
			break
		}
	}
	if capComment == "" {
		t.Errorf("expected cap-reject comment containing '并发上限', got %v", trello.comments)
	}
	if !strings.Contains(capComment, "project=agent") {
		t.Errorf("cap-reject comment should mention project=agent, got %q", capComment)
	}
	if !strings.Contains(log.String(), `"event":"cap.reject"`) {
		t.Errorf("expected cap.reject log, got %s", log.String())
	}
	if !strings.Contains(log.String(), "card=c_new") {
		t.Errorf("cap.reject log should mention card=c_new, got %s", log.String())
	}
	if !strings.Contains(log.String(), "project=agent") {
		t.Errorf("cap.reject log should mention project=agent, got %s", log.String())
	}
}

// TestPollOnceNewDoingAcceptsUnderCap verifies the per-project
// limit only fires for the same project: 1 proj:agent at cap +
// 1 new proj:other card must be accepted (per-project=1 for
// "other" is not yet hit; total=1 < MaxDoingTotal=2).
func TestPollOnceNewDoingAcceptsUnderCap(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{sessionID: "ses_new"}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	// Trello shows the pre-existing c_agent in doing (so it
	// doesn't get dragged out) plus the new c_other. Step 2 must
	// accept c_other because the per-project cap binds per
	// project, not globally.
	trello.setCards(doingID, []trelloCard{
		{ID: "c_agent", Name: "c_agent", Labels: []trelloLabel{{Name: "proj:agent"}}},
		{ID: "c_other", Name: "c_other", Labels: []trelloLabel{{Name: "proj:other"}}},
	})
	trello.setCards(todoID, nil)

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c_agent"] = &sessionInfo{cardID: "c_agent", project: "agent", status: statusStarted, sessionID: "ses_agent"}
	s.sessionCards["ses_agent"] = "c_agent"

	s.pollOnce(context.Background())

	// processCard runs in a goroutine; wait for the session to register.
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		s.mu.Lock()
		_, ok := s.sessionCards["ses_new"]
		s.mu.Unlock()
		if ok {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.cardSessions["c_other"]; !ok {
		t.Error("c_other should be accepted (different project, per-project cap not hit)")
	}
	// No move-to-todo should have been recorded for c_other, and
	// no cap-reject comment was written (the accept path writes
	// a Started comment, which is expected — we filter on the
	// "并发上限" prefix specifically).
	trello.mu.Lock()
	defer trello.mu.Unlock()
	for _, m := range trello.moves {
		if m.cardID == "c_other" && m.listID == todoID {
			t.Errorf("c_other should not be moved to todo; moves=%v", trello.moves)
		}
	}
	for _, c := range trello.comments {
		if strings.Contains(c, "并发上限") {
			t.Errorf("no cap-reject comment expected, got %q", c)
		}
	}
}

// TestPollOnceNewDoingAcceptsUnderTotalCap verifies the global
// cap binds across projects: with MaxDoingTotal=3 and 3 distinct
// projects, all three should be accepted (per-project=1 each,
// total goes 0→1→2→3 across iterations).
func TestPollOnceNewDoingAcceptsUnderTotalCap(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{sessionID: "ses_x"}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	trello.setCards(doingID, []trelloCard{
		{ID: "c1", Name: "c1", Labels: []trelloLabel{{Name: "proj:a"}}},
		{ID: "c2", Name: "c2", Labels: []trelloLabel{{Name: "proj:b"}}},
		{ID: "c3", Name: "c3", Labels: []trelloLabel{{Name: "proj:c"}}},
	})
	trello.setCards(todoID, nil)

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cfg.MaxDoingTotal = 3
	s.cfg.MaxDoingPerProject = 1

	s.pollOnce(context.Background())

	// Wait for all 3 sessions to register.
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		s.mu.Lock()
		count := 0
		for _, info := range s.cardSessions {
			if info.sessionID != "" {
				count++
			}
		}
		s.mu.Unlock()
		if count >= 3 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if got := len(s.cardSessions); got != 3 {
		t.Errorf("cardSessions=%d, want 3", got)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	for _, m := range trello.moves {
		if m.listID == todoID {
			t.Errorf("no card should be moved to todo; moves=%v", trello.moves)
		}
	}
}

// TestPollOnceNewDoingRejectMoveFailureIsLogged exercises the
// cap-reject error path: when trelloMoveCard returns an error
// during the Step 2 reject, the scheduler must log
// cap.move.fail and not panic. The card stays in doing from
// Trello's perspective; the next poll will re-evaluate it.
func TestPollOnceNewDoingRejectMoveFailureIsLogged(t *testing.T) {
	trello := newFakeTrello()
	// Wrap the fake Trello to force any move *to* todo to return
	// 500. Other Trello calls (comments, drag-out to icebox) pass
	// through. This isolates the cap-reject move path so its
	// error handling can be observed.
	trURL := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasPrefix(r.URL.Path, "/1/lists/") && strings.HasSuffix(r.URL.Path, "/cards"):
			path := strings.TrimPrefix(r.URL.Path, "/1/lists/")
			listID := strings.TrimSuffix(path, "/cards")
			trello.mu.Lock()
			cards := trello.cardsByList[listID]
			trello.mu.Unlock()
			if cards == nil {
				_, _ = w.Write([]byte(`[]`))
				return
			}
			_ = json.NewEncoder(w).Encode(cards)
		case strings.HasPrefix(r.URL.Path, "/1/cards/") && r.Method == http.MethodPut:
			var body struct {
				IDList string `json:"idList"`
			}
			_ = json.NewDecoder(r.Body).Decode(&body)
			if body.IDList == todoID {
				w.WriteHeader(http.StatusInternalServerError)
				return
			}
			// Other moves (drag-out to icebox) still succeed.
			cardID := strings.TrimPrefix(r.URL.Path, "/1/cards/")
			cardID = strings.SplitN(cardID, "/", 2)[0]
			trello.mu.Lock()
			trello.moves = append(trello.moves, moveRec{cardID: cardID, listID: body.IDList})
			trello.mu.Unlock()
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"id":"` + cardID + `"}`))
		default:
			trello.handler().ServeHTTP(w, r)
		}
	}))
	defer trURL.Close()
	oc := &fakeOpencode{}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	trello.setCards(doingID, []trelloCard{
		{ID: "c_full", Name: "c_full", Labels: []trelloLabel{{Name: "proj:agent"}}},
		{ID: "c_new", Name: "c_new", Labels: []trelloLabel{{Name: "proj:agent"}}},
	})
	trello.setCards(todoID, nil)

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c_full"] = &sessionInfo{cardID: "c_full", project: "agent", status: statusStarted, sessionID: "ses_full"}
	s.sessionCards["ses_full"] = "c_full"

	log := &drainLog{}
	withLogWriter(t, log)
	s.pollOnce(context.Background())

	// The cap-reject path should have logged the move failure
	// and the cap.reject decision, written the comment
	// (succeeded because we only forced move-to-todo to fail),
	// and left c_new out of cardSessions.
	if !strings.Contains(log.String(), "cap.move.fail") {
		t.Errorf("expected cap.move.fail log, got %s", log.String())
	}
	if !strings.Contains(log.String(), `"event":"cap.reject"`) {
		t.Errorf("expected cap.reject log, got %s", log.String())
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, busy := s.cardSessions["c_new"]; busy {
		t.Error("c_new must not be in cardSessions even when the reject move fails")
	}
}
