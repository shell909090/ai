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

// ---------- project / count helpers ----------

func TestProjectOf(t *testing.T) {
	cases := []struct {
		name string
		card trelloCard
		want string
	}{
		{"no labels", trelloCard{}, defaultProject},
		{"unrelated label", trelloCard{Labels: []trelloLabel{{Name: "bug"}}}, defaultProject},
		{"proj label", trelloCard{Labels: []trelloLabel{{Name: "proj:agent"}}}, "agent"},
		{"first proj wins", trelloCard{Labels: []trelloLabel{{Name: "a"}, {Name: "proj:ai"}, {Name: "proj:kanban"}}}, "ai"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := projectOf(c.card); got != c.want {
				t.Errorf("projectOf = %q, want %q", got, c.want)
			}
		})
	}
}

func TestCountByProject(t *testing.T) {
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", "http://opencode.invalid")
	s.cardSessions = map[string]*sessionInfo{
		"c1": {cardID: "c1", project: "agent"},
		"c2": {cardID: "c2", project: "agent"},
		"c3": {cardID: "c3", project: "ai"},
		"c4": {cardID: "c4", project: defaultProject},
	}
	total, per := s.countByProject()
	if total != 4 {
		t.Errorf("total=%d, want 4", total)
	}
	if per["agent"] != 2 {
		t.Errorf("agent=%d, want 2", per["agent"])
	}
	if per["ai"] != 1 {
		t.Errorf("ai=%d, want 1", per["ai"])
	}
	if per[defaultProject] != 1 {
		t.Errorf("default=%d, want 1", per[defaultProject])
	}
}

func TestAcceptNewCard(t *testing.T) {
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", "http://opencode.invalid")
	// Defaults: MaxDoingTotal=2, MaxDoingPerProject=1.
	card := trelloCard{ID: "x", Labels: []trelloLabel{{Name: "proj:agent"}}}

	// Under cap → accept.
	if reject, reason := s.acceptNewCard(card, 0, map[string]int{}); reject {
		t.Errorf("empty cap: reject=true reason=%q, want false", reason)
	}
	// Per-project cap hit → reject; reason names the project.
	if reject, reason := s.acceptNewCard(card, 1, map[string]int{"agent": 1}); !reject {
		t.Errorf("per-project=1 hit: reject=false, want true")
	} else if !strings.Contains(reason, "project=agent") {
		t.Errorf("reason=%q, want project=agent", reason)
	} else if !strings.Contains(reason, "global=2") {
		t.Errorf("reason=%q, want global=2", reason)
	} else if !strings.Contains(reason, "per-project=1") {
		t.Errorf("reason=%q, want per-project=1", reason)
	}
	// Global cap hit → reject; takes precedence over per-project
	// even when per-project would still allow.
	if reject, reason := s.acceptNewCard(card, 2, map[string]int{"agent": 0, "other": 1}); !reject {
		t.Errorf("global=2 hit: reject=false, want true")
	} else if !strings.Contains(reason, "global=2") {
		t.Errorf("reason=%q, want global=2", reason)
	}
	// No proj:* label uses defaultProject.
	def := trelloCard{ID: "y"}
	if reject, reason := s.acceptNewCard(def, 1, map[string]int{defaultProject: 1}); !reject {
		t.Errorf("default project cap hit: reject=false, want true")
	} else if !strings.Contains(reason, "project="+defaultProject) {
		t.Errorf("reason=%q, want project=%s", reason, defaultProject)
	}
	// Accept path returns empty reason.
	if reject, reason := s.acceptNewCard(card, 0, map[string]int{"agent": 0}); reject || reason != "" {
		t.Errorf("under cap: reject=%v reason=%q, want false/empty", reject, reason)
	}
}

// ---------- drag-out (Feature A) ----------

func TestHandleDragOut(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	// opencode: abort returns 200, prompt returns 204
	oc := &fakeOpencode{}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", project: "agent", status: statusStarted}
	s.sessionCards["ses1"] = "c1"

	log := &drainLog{}
	withLogWriter(t, log)
	s.handleDragOut(context.Background(), "c1")

	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("c1 should be removed from cardSessions")
	}
	if _, ok := s.sessionCards["ses1"]; ok {
		t.Error("ses1 should be removed from sessionCards")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0] != (moveRec{cardID: "c1", listID: iceboxID}) {
		t.Errorf("moves=%v, want [{c1 %s}]", trello.moves, iceboxID)
	}
	if !strings.Contains(log.String(), `"event":"dragout"`) {
		t.Errorf("expected dragout log, got %s", log.String())
	}
}

func TestHandleDragOutAbandonsSummary(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c1"] = &sessionInfo{
		cardID: "c1", sessionID: "ses1", project: "agent",
		status: statusSummarizing, summaryStartedAt: time.Now(),
	}
	s.sessionCards["ses1"] = "c1"

	log := &drainLog{}
	withLogWriter(t, log)
	s.handleDragOut(context.Background(), "c1")

	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("c1 should be removed from cardSessions")
	}
	if !strings.Contains(log.String(), "finish.summary.aborted") {
		t.Errorf("expected finish.summary.aborted log, got %s", log.String())
	}
	if !strings.Contains(log.String(), "reason=drag-out") {
		t.Errorf("expected reason=drag-out in log, got %s", log.String())
	}
}

func TestHandleDragOutAbortFailure(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	// opencode: every request returns 500
	oc := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer oc.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, oc.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", project: "agent", status: statusStarted}
	s.sessionCards["ses1"] = "c1"

	log := &drainLog{}
	withLogWriter(t, log)
	s.handleDragOut(context.Background(), "c1")

	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("c1 should still be removed from cardSessions even if abort fails")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 {
		t.Errorf("move to icebox should still happen on abort fail, got %v", trello.moves)
	}
	if !strings.Contains(log.String(), "dragout.abort.fail") {
		t.Errorf("expected dragout.abort.fail log, got %s", log.String())
	}
}

func TestHandleDragOutUnknownCard(t *testing.T) {
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", "http://opencode.invalid")
	// No entry for "missing" — handleDragOut should be a no-op.
	s.handleDragOut(context.Background(), "missing")
}

func TestPollOnceDragOutTriggersAbort(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	// Card is registered but doing list is empty → drag-out
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", project: "agent", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	trello.setCards(doingID, nil)
	trello.setCards(todoID, nil)

	s.pollOnce(context.Background())

	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("c1 should be removed after drag-out")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != iceboxID {
		t.Errorf("expected move to icebox, got %v", trello.moves)
	}
}

// ---------- auto-promote (Feature B) ----------

func TestPollOnceAutoPromote(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{sessionID: "ses_xyz"}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	// 3 todo cards, all "default" project. With MaxDoingTotal=2
	// and MaxDoingPerProject=1, only 1 can be promoted (per-project
	// limit binds first, since all cards share a project).
	trello.setCards(doingID, nil)
	trello.setCards(todoID, []trelloCard{
		{ID: "t1", Name: "t1"},
		{ID: "t2", Name: "t2"},
		{ID: "t3", Name: "t3"},
	})

	s.pollOnce(context.Background())

	// Wait briefly for the goroutine to register the session.
	deadline := time.Now().Add(time.Second)
	for time.Now().Before(deadline) {
		s.mu.Lock()
		count := len(s.sessionCards)
		s.mu.Unlock()
		if count >= 1 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if got := len(s.cardSessions); got != 1 {
		t.Errorf("cardSessions=%d, want 1 (per-project=1 binds first)", got)
	}
}

func TestPollOnceRespectsMaxTotal(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{sessionID: "ses_xyz"}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	// MaxDoingTotal=2, MaxDoingPerProject=1 (defaults).
	// 5 todo cards across different projects so per-project doesn't
	// bite first.
	trello.setCards(doingID, nil)
	trello.setCards(todoID, []trelloCard{
		{ID: "t1", Name: "t1", Labels: []trelloLabel{{Name: "proj:a"}}},
		{ID: "t2", Name: "t2", Labels: []trelloLabel{{Name: "proj:b"}}},
		{ID: "t3", Name: "t3", Labels: []trelloLabel{{Name: "proj:c"}}},
		{ID: "t4", Name: "t4", Labels: []trelloLabel{{Name: "proj:d"}}},
		{ID: "t5", Name: "t5", Labels: []trelloLabel{{Name: "proj:e"}}},
	})

	s.pollOnce(context.Background())

	// Wait briefly for any goroutines to settle.
	time.Sleep(100 * time.Millisecond)
	s.mu.Lock()
	defer s.mu.Unlock()
	if got := len(s.cardSessions); got != 2 {
		t.Errorf("cardSessions=%d, want 2 (MaxDoingTotal=2)", got)
	}
}

func TestPollOnceRespectsMaxPerProject(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{sessionID: "ses_xyz"}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	// 3 todo cards, two "proj:a" and one "proj:b". MaxTotal=5, MaxPer=1.
	trello.setCards(doingID, nil)
	trello.setCards(todoID, []trelloCard{
		{ID: "t1", Name: "t1", Labels: []trelloLabel{{Name: "proj:a"}}},
		{ID: "t2", Name: "t2", Labels: []trelloLabel{{Name: "proj:a"}}},
		{ID: "t3", Name: "t3", Labels: []trelloLabel{{Name: "proj:b"}}},
	})
	s.cfg.MaxDoingTotal = 5
	s.cfg.MaxDoingPerProject = 1

	s.pollOnce(context.Background())

	time.Sleep(100 * time.Millisecond)
	s.mu.Lock()
	defer s.mu.Unlock()
	if got := len(s.cardSessions); got != 2 {
		t.Errorf("cardSessions=%d, want 2 (a:1, b:1)", got)
	}
	// Make sure we promoted one a, one b (not two a's).
	gotA, gotB := 0, 0
	for _, info := range s.cardSessions {
		switch info.project {
		case "a":
			gotA++
		case "b":
			gotB++
		}
	}
	if gotA != 1 || gotB != 1 {
		t.Errorf("per-project split: a=%d, b=%d, want 1/1", gotA, gotB)
	}
}

func TestPollOnceNoPromoteWhenAtCapacity(t *testing.T) {
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	oc := &fakeOpencode{}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	// doing already has 2 cards (at MaxDoingTotal=2), both default project
	s.cardSessions["d1"] = &sessionInfo{cardID: "d1", project: defaultProject, status: statusStarted, sessionID: "ses_d1"}
	s.cardSessions["d2"] = &sessionInfo{cardID: "d2", project: defaultProject, status: statusStarted, sessionID: "ses_d2"}
	s.sessionCards["ses_d1"] = "d1"
	s.sessionCards["ses_d2"] = "d2"
	trello.setCards(doingID, []trelloCard{{ID: "d1"}, {ID: "d2"}})
	trello.setCards(todoID, []trelloCard{{ID: "t1"}})

	s.pollOnce(context.Background())

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.cardSessions["t1"]; ok {
		t.Error("t1 should not be promoted when at capacity")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) > 2 {
		// existing d1/d2 may or may not show as moves depending on what
		// the test setup does; the important thing is no move to t1
		for _, m := range trello.moves {
			if m.cardID == "t1" {
				t.Errorf("t1 was moved unexpectedly: %v", m)
			}
		}
	}
}

func TestPollOncePromoteMoveFailureRollsBack(t *testing.T) {
	// Set up a fake trello that returns 500 only for moves to the
	// "doing" list (i.e., the promote step).
	trello := newFakeTrello()
	trURL := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch {
		case strings.HasPrefix(r.URL.Path, "/1/lists/") && strings.HasSuffix(r.URL.Path, "/cards"):
			// Distinguish doing vs todo by listID
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
			// Parse target list from body
			var body struct {
				IDList string `json:"idList"`
			}
			_ = json.NewDecoder(r.Body).Decode(&body)
			if body.IDList == doingID {
				w.WriteHeader(http.StatusInternalServerError)
				return
			}
			// Other moves (drag-out to icebox) succeed.
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

	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	trello.setCards(doingID, nil)
	trello.setCards(todoID, []trelloCard{{ID: "t1", Name: "t1"}})

	log := &drainLog{}
	withLogWriter(t, log)
	s.pollOnce(context.Background())

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.cardSessions["t1"]; ok {
		t.Error("t1 should be rolled back when move fails")
	}
	if !strings.Contains(log.String(), "promote.move.fail") {
		t.Errorf("expected promote.move.fail log, got %s", log.String())
	}
}
