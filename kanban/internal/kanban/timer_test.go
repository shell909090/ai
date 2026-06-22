package kanban

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

// ---------- helpers ----------

func makeFinishMsg(finish string) map[string]any {
	return map[string]any{"info": map[string]any{"finish": finish}}
}

func makeSummaryMsg(finish, text string) map[string]any {
	return map[string]any{
		"info":  map[string]any{"finish": finish},
		"parts": []any{map[string]any{"type": "text", "text": text}},
	}
}

// ---------- hasLabel ----------

func TestHasLabel(t *testing.T) {
	card := trelloCard{Labels: []trelloLabel{{Name: "human"}, {Name: "proj:agent"}}}
	if !hasLabel(card, "human") {
		t.Error("hasLabel(human) = false, want true")
	}
	if hasLabel(card, "attention") {
		t.Error("hasLabel(attention) = true, want false")
	}
	if hasLabel(card, "") {
		t.Error("hasLabel empty name should be false")
	}
}

// ---------- destroyTask ----------

func TestDestroyTask(t *testing.T) {
	s, _ := New(Config{DefaultProj: "default"})
	s.tasks["c1"] = &Task{CardID: "c1", Proj: "agent"}
	s.totalCount = 1
	s.projCount["agent"] = 1

	s.destroyTask("c1")

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be removed")
	}
	if s.totalCount != 0 {
		t.Errorf("totalCount=%d, want 0", s.totalCount)
	}
	if s.projCount["agent"] != 0 {
		t.Errorf("projCount[agent]=%d, want 0", s.projCount["agent"])
	}
}

func TestDestroyTaskIdempotent(t *testing.T) {
	s, _ := New(Config{DefaultProj: "default"})
	s.destroyTask("nonexistent") // should not panic
}

func TestDestroyTaskNegativeProtection(t *testing.T) {
	s, _ := New(Config{DefaultProj: "default"})
	s.tasks["c1"] = &Task{CardID: "c1", Proj: "agent"}
	s.totalCount = 0 // already at 0 — should not go negative
	s.projCount["agent"] = 0

	log := &drainLog{}
	withLogWriter(t, log)
	s.destroyTask("c1")

	if s.totalCount != 0 {
		t.Errorf("totalCount=%d, want 0", s.totalCount)
	}
	if !strings.Contains(log.String(), "error.count.negative") {
		t.Error("expected error.count.negative log")
	}
}

// ---------- session.finish: checkOneFinish ----------

func TestCheckOneFinishSkipsWhenNoFinish(t *testing.T) {
	oc := &fakeOpencode{}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default"}
	s.totalCount = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; !ok {
		t.Error("task should remain when no finish")
	}
}

func TestCheckOneFinishSkipsToolCalls(t *testing.T) {
	oc := &fakeOpencode{message: makeFinishMsg("tool-calls")}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default"}
	s.totalCount = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; !ok {
		t.Error("task should remain for tool-calls finish")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) > 0 {
		t.Error("no moves expected for tool-calls")
	}
}

func TestCheckOneFinishAbortDone(t *testing.T) {
	oc := &fakeOpencode{message: makeFinishMsg("stop")}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	abortTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Abort: &abortTime}
	s.totalCount = 1
	s.projCount["default"] = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed after abort done")
	}
	if s.totalCount != 0 {
		t.Errorf("totalCount=%d, want 0", s.totalCount)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	var found bool
	for _, c := range trello.comments {
		if strings.Contains(c, "Abort completed") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected 'Abort completed' comment, got %v", trello.comments)
	}
	if len(trello.moves) > 0 {
		t.Error("abort done should not move card")
	}
}

func TestCheckOneFinishAbnormalFinishes(t *testing.T) {
	abnormal := []string{"length", "content-filter", "error", "unknown"}
	for _, finish := range abnormal {
		t.Run(finish, func(t *testing.T) {
			oc := &fakeOpencode{message: makeFinishMsg(finish)}
			ocSrv := httptest.NewServer(oc.handler())
			defer ocSrv.Close()
			trello := newFakeTrello()
			trSrv := httptest.NewServer(trello.handler())
			defer trSrv.Close()

			s := newTestServer(t, trSrv.URL, ocSrv.URL)
			s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default"}
			s.totalCount = 1

			s.checkOneFinish(context.Background(), "c1", time.Now())

			if _, ok := s.tasks["c1"]; ok {
				t.Error("task should be destroyed after abnormal finish")
			}
			trello.mu.Lock()
			defer trello.mu.Unlock()
			if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
				t.Errorf("card should move to done, moves=%v", trello.moves)
			}
			if len(trello.labelAdds) != 1 || trello.labelAdds[0] != testAttentionID {
				t.Errorf("attention label expected, labelAdds=%v", trello.labelAdds)
			}
			var found bool
			for _, c := range trello.comments {
				if strings.Contains(c, "finish="+finish) {
					found = true
				}
			}
			if !found {
				t.Errorf("comment should mention finish=%s, got %v", finish, trello.comments)
			}
		})
	}
}

func TestCheckOneFinishStopSendsSummary(t *testing.T) {
	oc := &fakeOpencode{
		sessionID: "ses1",
		message:   makeFinishMsg("stop"),
	}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default",
		Model: ModelRef{ProviderID: "test", ModelID: "model"}}
	s.totalCount = 1

	now := time.Now()
	s.checkOneFinish(context.Background(), "c1", now)

	s.mu.Lock()
	task, ok := s.tasks["c1"]
	s.mu.Unlock()
	if !ok {
		t.Fatal("task should remain while waiting for summary")
	}
	if task.Summary == nil {
		t.Error("task.Summary should be set after summary prompt sent")
	}

	oc.mu.Lock()
	found := false
	for _, pc := range oc.promptCalls {
		if strings.Contains(pc.Prompt, "总结") {
			found = true
		}
	}
	oc.mu.Unlock()
	if !found {
		t.Error("summary prompt should have been sent")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) > 0 {
		t.Error("card should not move on first stop")
	}
}

func TestCheckOneFinishStopWithSummaryCompletes(t *testing.T) {
	summaryText := "完成了一个 bug 修复。"
	oc := &fakeOpencode{message: makeSummaryMsg("stop", summaryText)}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	sumTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Summary: &sumTime}
	s.totalCount = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed after completion")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
		t.Errorf("card should move to done, moves=%v", trello.moves)
	}
	var summaryComment string
	for _, c := range trello.comments {
		if strings.Contains(c, summaryText) {
			summaryComment = c
		}
	}
	if summaryComment == "" {
		t.Errorf("summary comment not found in %v", trello.comments)
	}
	if !strings.HasPrefix(summaryComment, "Task finished. Summary:") {
		t.Errorf("comment=%q, want 'Task finished. Summary:'", summaryComment)
	}
}

func TestCheckOneFinishSummaryAbnormal(t *testing.T) {
	// Summary phase gets an error finish → should still add attention
	// because session ended abnormally overall.
	oc := &fakeOpencode{message: makeFinishMsg("error")}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	sumTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Summary: &sumTime}
	s.totalCount = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed")
	}
	// Rule 3 fires (finish=error, no abort) → attention + done.
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
		t.Errorf("moves=%v", trello.moves)
	}
	if len(trello.labelAdds) != 1 {
		t.Errorf("attention should be added, labelAdds=%v", trello.labelAdds)
	}
}

// ---------- doing.out ----------

func TestHandleDoingOut(t *testing.T) {
	oc := &fakeOpencode{}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default"}
	s.totalCount = 1

	now := time.Now()
	s.handleDoingOut(context.Background(), "c1", now)

	s.mu.Lock()
	task, ok := s.tasks["c1"]
	s.mu.Unlock()
	if !ok {
		t.Fatal("task should remain (not destroyed) after doing.out")
	}
	if task.Abort == nil {
		t.Error("task.Abort should be set")
	}

	oc.mu.Lock()
	aborts := oc.abortCalls
	oc.mu.Unlock()
	if len(aborts) != 1 {
		t.Errorf("abort should be sent once, got %d", len(aborts))
	}

	trello.mu.Lock()
	defer trello.mu.Unlock()
	var found bool
	for _, c := range trello.comments {
		if strings.Contains(c, "Abort requested") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected 'Abort requested' comment, got %v", trello.comments)
	}
	if len(trello.moves) > 0 {
		t.Error("doing.out should not move card immediately")
	}
}

func TestHandleDoingOutIdempotent(t *testing.T) {
	oc := &fakeOpencode{}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	s := newTestServer(t, "http://api.trello.invalid", ocSrv.URL)

	abortTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Abort: &abortTime}

	s.handleDoingOut(context.Background(), "c1", time.Now())

	oc.mu.Lock()
	defer oc.mu.Unlock()
	if len(oc.abortCalls) > 0 {
		t.Error("second abort should not be sent")
	}
}

// ---------- doing.in ----------

func TestHandleDoingInStartsSession(t *testing.T) {
	oc := &fakeOpencode{sessionID: "ses_new"}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	card := trelloCard{ID: "c1", Name: "Test card", Desc: "do the thing"}
	s.handleDoingIn(context.Background(), card, time.Now())

	s.mu.Lock()
	task, ok := s.tasks["c1"]
	total := s.totalCount
	projCount := s.projCount["default"]
	s.mu.Unlock()

	if !ok {
		t.Fatal("task not created")
	}
	if task.SessionID != "ses_new" {
		t.Errorf("SessionID=%q, want ses_new", task.SessionID)
	}
	if total != 1 {
		t.Errorf("totalCount=%d, want 1", total)
	}
	if projCount != 1 {
		t.Errorf("projCount[default]=%d, want 1", projCount)
	}

	trello.mu.Lock()
	defer trello.mu.Unlock()
	var found bool
	for _, c := range trello.comments {
		if strings.Contains(c, "Started session ses_new") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected 'Started session ses_new', got %v", trello.comments)
	}
}

func TestHandleDoingInSkipsHuman(t *testing.T) {
	// human card detection happens in reconcileDoing, not handleDoingIn directly,
	// but handleDoingIn won't be called for human cards.
	// This test verifies idempotency: already-tracked cards are ignored.
	s := newTestServer(t, "http://api.trello.invalid", "http://oc.invalid")
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses_existing"}
	s.totalCount = 1

	s.handleDoingIn(context.Background(), trelloCard{ID: "c1"}, time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.totalCount != 1 {
		t.Error("should not double-count already-tracked card")
	}
}

func TestHandleDoingInProjFail(t *testing.T) {
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	s := newTestServer(t, trSrv.URL, "http://oc.invalid")
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}

	card := trelloCard{
		ID:     "c1",
		Labels: []trelloLabel{{Name: "proj:unknown"}},
	}
	s.handleDoingIn(context.Background(), card, time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should not be created on proj parse fail")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
		t.Errorf("moves=%v, want move to done", trello.moves)
	}
	if len(trello.labelAdds) != 1 {
		t.Error("attention label should be added")
	}
	var found bool
	for _, c := range trello.comments {
		if strings.Contains(c, "project label is invalid") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected proj error comment, got %v", trello.comments)
	}
}

func TestHandleDoingInModelFail(t *testing.T) {
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	s := newTestServer(t, trSrv.URL, "http://oc.invalid")
	s.cfg.AllowedModels = []AllowedModel{{Label: "model:ok", ProviderID: "p", ModelID: "m"}}

	card := trelloCard{
		ID:     "c1",
		Labels: []trelloLabel{{Name: "model:notinlist"}},
	}
	s.handleDoingIn(context.Background(), card, time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should not be created on model parse fail")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
		t.Errorf("moves=%v, want move to done", trello.moves)
	}
	var found bool
	for _, c := range trello.comments {
		if strings.Contains(c, "model label is invalid") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected model error comment, got %v", trello.comments)
	}
}

func TestHandleDoingInCapFull(t *testing.T) {
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	s := newTestServer(t, trSrv.URL, "http://oc.invalid")
	s.totalCount = s.cfg.MaxDoingTotal // at global cap

	s.handleDoingIn(context.Background(), trelloCard{ID: "c1"}, time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should not be created when at cap")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testTodoID {
		t.Errorf("card should go back to todo, moves=%v", trello.moves)
	}
	var found bool
	for _, c := range trello.comments {
		if strings.Contains(c, "capacity is full") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected capacity comment, got %v", trello.comments)
	}
}

func TestHandleDoingInProjCapFull(t *testing.T) {
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	s := newTestServer(t, trSrv.URL, "http://oc.invalid")
	s.projCount["default"] = s.cfg.MaxDoingPerProject // proj at cap

	s.handleDoingIn(context.Background(), trelloCard{ID: "c1"}, time.Now())

	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testTodoID {
		t.Errorf("card should go back to todo, moves=%v", trello.moves)
	}
}

// ---------- timeout ----------

func TestCheckOneTimeoutAbort(t *testing.T) {
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	s := newTestServer(t, trSrv.URL, "http://oc.invalid")
	s.cfg.AbortTimeout = time.Millisecond

	abortTime := time.Now().Add(-time.Second) // set 1s ago
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Abort: &abortTime}
	s.totalCount = 1
	s.projCount["default"] = 1

	s.checkOneTimeout(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed on abort timeout")
	}
	if s.totalCount != 0 {
		t.Errorf("totalCount=%d, want 0", s.totalCount)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	var found bool
	for _, c := range trello.comments {
		if strings.Contains(c, "Abort timeout") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected 'Abort timeout' comment, got %v", trello.comments)
	}
	if len(trello.labelAdds) != 1 {
		t.Error("attention label should be added on abort timeout")
	}
	if len(trello.moves) > 0 {
		t.Error("abort timeout should not move card")
	}
}

func TestCheckOneTimeoutSummary(t *testing.T) {
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	s := newTestServer(t, trSrv.URL, "http://oc.invalid")
	s.cfg.SummaryTimeout = time.Millisecond

	sumTime := time.Now().Add(-time.Second) // set 1s ago
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Summary: &sumTime}
	s.totalCount = 1
	s.projCount["default"] = 1

	s.checkOneTimeout(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed on summary timeout")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
		t.Errorf("card should move to done on summary timeout, moves=%v", trello.moves)
	}
	var found bool
	for _, c := range trello.comments {
		if strings.Contains(c, "Summary timeout") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected 'Summary timeout' comment, got %v", trello.comments)
	}
}

func TestCheckOneTimeoutNoTimeout(t *testing.T) {
	s := newTestServer(t, "http://api.trello.invalid", "http://oc.invalid")
	s.cfg.AbortTimeout = time.Hour
	s.cfg.SummaryTimeout = time.Hour

	abortTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Abort: &abortTime}
	s.totalCount = 1

	s.checkOneTimeout(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; !ok {
		t.Error("task should remain when not timed out")
	}
}

// ---------- promoteTodo ----------

func TestPromoteTodoBasic(t *testing.T) {
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	oc := &fakeOpencode{sessionID: "ses_promoted"}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	// MaxDoingTotal=2, MaxDoingPerProject=1
	trello.setCards(testTodoID, []trelloCard{
		{ID: "t1", Name: "T1"},
		{ID: "t2", Name: "T2", Labels: []trelloLabel{{Name: "proj:other"}}},
	})

	s.promoteTodo(context.Background(), time.Now())

	// Only 1 card from "default" proj can be promoted (per-project=1)
	// t2 has proj:other but it's not in AllowedProjects, so it gets moved to done.
	// Actually wait: default config has no AllowedProjects, so proj:other is unknown
	// and t2 should go to done with attention.
	// t1 has no proj label → uses DefaultProj="default", cap not hit → promoted.
	s.mu.Lock()
	total := s.totalCount
	s.mu.Unlock()

	if total != 1 {
		t.Errorf("totalCount=%d, want 1 (only t1 promoted; t2 has unknown proj)", total)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	var promotedToDoingT1, movedToDoneT2 bool
	for _, m := range trello.moves {
		if m.cardID == "t1" && m.listID == testDoingID {
			promotedToDoingT1 = true
		}
		if m.cardID == "t2" && m.listID == testDoneID {
			movedToDoneT2 = true
		}
	}
	if !promotedToDoingT1 {
		t.Errorf("t1 should be promoted to doing, moves=%v", trello.moves)
	}
	if !movedToDoneT2 {
		t.Errorf("t2 should be moved to done (unknown proj), moves=%v", trello.moves)
	}
}

func TestPromoteTodoSkipsHuman(t *testing.T) {
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	oc := &fakeOpencode{sessionID: "ses_x"}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	trello.setCards(testTodoID, []trelloCard{
		{ID: "t1", Name: "human task", Labels: []trelloLabel{{Name: "human"}}},
	})

	s.promoteTodo(context.Background(), time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.totalCount != 0 {
		t.Error("human card should not be promoted")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) > 0 {
		t.Errorf("human card should not be moved, got %v", trello.moves)
	}
}

func TestPromoteTodoStopsAtGlobalCap(t *testing.T) {
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	oc := &fakeOpencode{sessionID: "ses_x"}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	s.cfg.MaxDoingTotal = 2
	s.cfg.MaxDoingPerProject = 3 // high per-project cap
	s.totalCount = 2             // already at global cap

	trello.setCards(testTodoID, []trelloCard{{ID: "t1", Name: "T1"}})
	s.promoteTodo(context.Background(), time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.totalCount != 2 {
		t.Error("should not promote when at global cap")
	}
}

func TestPromoteTodoSkipsWhenProjAtCap(t *testing.T) {
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	oc := &fakeOpencode{sessionID: "ses_x"}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	s.cfg.MaxDoingTotal = 5
	s.cfg.MaxDoingPerProject = 1
	s.projCount["default"] = 1 // default proj at cap

	// Two cards: t1 (default proj) and t2 (agent proj with AllowedProjects entry)
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	trello.setCards(testTodoID, []trelloCard{
		{ID: "t1", Name: "T1"}, // default proj → at cap
		{ID: "t2", Name: "T2", Labels: []trelloLabel{{Name: "proj:agent"}}}, // agent proj → not at cap
	})

	s.promoteTodo(context.Background(), time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.totalCount != 1 {
		t.Errorf("totalCount=%d, want 1 (only t2 promoted)", s.totalCount)
	}
	if _, ok := s.tasks["t2"]; !ok {
		t.Error("t2 (agent proj) should be promoted")
	}
	if _, ok := s.tasks["t1"]; ok {
		t.Error("t1 (default proj at cap) should not be promoted")
	}
}

// ---------- reconcileDoing ----------

func TestReconcileDoingOutThenIn(t *testing.T) {
	// doing.out keeps the task (just sets Abort). Capacity is NOT released
	// until abort is confirmed via finish or timeout. So c_new cannot start
	// when c_old holds the capacity slot.
	oc := &fakeOpencode{sessionID: "ses_new"}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	// c_old is tracked but no longer in doing → doing.out sets abort
	// c_new is in doing but c_old holds the capacity slot → c_new cannot start
	s.tasks["c_old"] = &Task{CardID: "c_old", SessionID: "ses_old", Proj: "default"}
	s.totalCount = 1
	s.projCount["default"] = 1

	trello.setCards(testDoingID, []trelloCard{{ID: "c_new", Name: "new card"}})

	s.reconcileDoing(context.Background(), time.Now())

	s.mu.Lock()
	oldTask, oldOk := s.tasks["c_old"]
	_, newOk := s.tasks["c_new"]
	s.mu.Unlock()

	// c_old should remain in tasks with Abort set (capacity still held).
	if !oldOk {
		t.Error("c_old should remain in tasks after doing.out")
	} else if oldTask.Abort == nil {
		t.Error("c_old.Abort should be set after doing.out")
	}

	// c_new cannot start because c_old's capacity slot is still held.
	if newOk {
		t.Error("c_new should not start while c_old holds capacity")
	}

	// Abort requested comment for c_old.
	trello.mu.Lock()
	defer trello.mu.Unlock()
	var abortComment bool
	for _, c := range trello.comments {
		if strings.Contains(c, "Abort requested") {
			abortComment = true
		}
	}
	if !abortComment {
		t.Errorf("expected 'Abort requested' comment, got %v", trello.comments)
	}
	// c_new moved back to todo due to capacity.
	var backToTodo bool
	for _, m := range trello.moves {
		if m.cardID == "c_new" && m.listID == testTodoID {
			backToTodo = true
		}
	}
	if !backToTodo {
		t.Errorf("c_new should move back to todo due to capacity, moves=%v", trello.moves)
	}
}

func TestReconcileDoingIgnoresHuman(t *testing.T) {
	oc := &fakeOpencode{}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	trello.setCards(testDoingID, []trelloCard{
		{ID: "c1", Name: "human task", Labels: []trelloLabel{{Name: "human"}}},
	})

	s.reconcileDoing(context.Background(), time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.tasks["c1"]; ok {
		t.Error("human card should be ignored in doing")
	}
}

// ---------- tick order ----------

func TestTickRunsInOrder(t *testing.T) {
	// Verify tick calls: finish → reconcile → timeout → promote
	// by observing effects. A card with a stop-finish should be moved to
	// done in the first tick.
	oc := &fakeOpencode{
		sessionID: "ses1",
		messagesQueue: []map[string]any{
			makeFinishMsg("stop"),
			makeSummaryMsg("stop", "all done"),
		},
	}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	sumTime := time.Now()
	s.tasks["c1"] = &Task{
		CardID:    "c1",
		SessionID: "ses1",
		Proj:      "default",
		Model:     ModelRef{ProviderID: "test", ModelID: "model"},
		Summary:   &sumTime, // summary already sent
	}
	s.totalCount = 1

	s.tick(context.Background(), time.Now())

	// After tick: checkSessionFinish sees stop + summary set → move to done + destroy.
	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed after tick completes the finish flow")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
		t.Errorf("card should move to done, moves=%v", trello.moves)
	}
}

// ---------- capacity release → same-tick promote ----------

func TestCapacityReleasedInSameTick(t *testing.T) {
	// c_old is tracked but not in Trello doing → doing.out releases capacity.
	// t1 is in todo → can be promoted in the same tick's promoteTodo.
	oc := &fakeOpencode{
		sessionID: "ses_old",
		message:   makeFinishMsg("stop"), // c_old's finish
	}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	trello := newFakeTrello()
	trSrv := httptest.NewServer(trello.handler())
	defer trSrv.Close()
	// oc needs ses_new for the promoted card
	oc.mu.Lock()
	oc.sessionID = "ses_old"
	oc.mu.Unlock()

	s := newTestServer(t, trSrv.URL, ocSrv.URL)
	s.cfg.MaxDoingTotal = 1
	s.cfg.MaxDoingPerProject = 1

	abortTime := time.Now().Add(-2 * s.cfg.AbortTimeout) // already timed out
	s.tasks["c_old"] = &Task{CardID: "c_old", SessionID: "ses_old", Proj: "default", Abort: &abortTime}
	s.totalCount = 1
	s.projCount["default"] = 1

	trello.setCards(testDoingID, nil) // c_old not in doing
	trello.setCards(testTodoID, []trelloCard{{ID: "t1", Name: "T1"}})

	// oc returns a different session ID for the new promoted card
	oc.mu.Lock()
	oc.sessionID = "ses_promoted"
	oc.mu.Unlock()

	s.tick(context.Background(), time.Now())

	s.mu.Lock()
	total := s.totalCount
	_, t1Ok := s.tasks["t1"]
	s.mu.Unlock()

	// After tick:
	// - checkSessionFinish: c_old has abort+stop → abort done, destroy task (total=0)
	// - reconcileDoing: c_old already destroyed, no out; no in
	// - checkTimeouts: c_old already gone
	// - promoteTodo: total=0 < 1, t1 can be promoted
	if total != 1 {
		t.Errorf("totalCount=%d, want 1 (t1 promoted after c_old destroyed)", total)
	}
	if !t1Ok {
		t.Error("t1 should be in tasks after promotion")
	}
}

// ---------- api tests ----------

func TestOcSendPromptUsesModel(t *testing.T) {
	oc := &fakeOpencode{sessionID: "ses1"}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	s := newTestServer(t, "http://api.trello.invalid", ocSrv.URL)

	model := ModelRef{ProviderID: "test-prov", ModelID: "test-mod"}
	err := s.ocSendPrompt(context.Background(), "ses1", model, "hello")
	if err != nil {
		t.Fatalf("ocSendPrompt: %v", err)
	}

	oc.mu.Lock()
	defer oc.mu.Unlock()
	if len(oc.promptCalls) != 1 {
		t.Fatalf("expected 1 prompt call, got %d", len(oc.promptCalls))
	}
	if !strings.Contains(oc.promptCalls[0].Model, "test-prov") {
		t.Errorf("model=%q, want contains test-prov", oc.promptCalls[0].Model)
	}
}

func TestOcCreateSessionReturnsID(t *testing.T) {
	oc := &fakeOpencode{sessionID: "ses_abc"}
	ocSrv := httptest.NewServer(oc.handler())
	defer ocSrv.Close()
	s := newTestServer(t, "http://api.trello.invalid", ocSrv.URL)

	id, err := s.ocCreateSession(context.Background(), ModelRef{ProviderID: "p", ModelID: "m"})
	if err != nil {
		t.Fatalf("ocCreateSession: %v", err)
	}
	if id != "ses_abc" {
		t.Errorf("id=%q, want ses_abc", id)
	}
}

func TestReconcileDoingError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s := newTestServer(t, srv.URL, "http://oc.invalid")
	log := &drainLog{}
	withLogWriter(t, log)

	s.reconcileDoing(context.Background(), time.Now())

	if !strings.Contains(log.String(), "reconcile.doing.error") {
		t.Errorf("expected reconcile.doing.error log, got %s", log.String())
	}
}
