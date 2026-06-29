package kanban

import (
	"context"
	"fmt"
	"net/http"
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
	s, _ := New(Config{})
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
	s, _ := New(Config{})
	s.destroyTask("nonexistent") // should not panic
}

func TestDestroyTaskNegativeProtection(t *testing.T) {
	s, _ := New(Config{})
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
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "running"}

	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent"}
	s.totalCount = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; !ok {
		t.Error("task should remain when no finish")
	}
}

func TestCheckOneFinishSkipsToolCalls(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "running", RawFinish: "tool-calls"}

	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent"}
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
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop"}

	abortTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Abort: &abortTime}
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
			trello := newFakeTrello()
			trSrv := newFakeTrelloServer(t, trello)

			s := newTestServer(t, trSrv)
			fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
			fakeDriver.state = AgentState{Kind: "failed", RawFinish: finish}

			s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent"}
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
				if strings.Contains(c, "status="+finish) {
					found = true
				}
			}
			if !found {
				t.Errorf("comment should mention status=%s, got %v", finish, trello.comments)
			}
		})
	}
}

func TestCheckOneFinishStopSendsSummary(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses1"
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop"}

	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent"}
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

	fakeDriver.mu.Lock()
	found := false
	for _, pc := range fakeDriver.promptCalls {
		if strings.Contains(pc.Prompt, "总结") {
			found = true
		}
	}
	fakeDriver.mu.Unlock()
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
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop", Text: summaryText}

	sumTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Summary: &sumTime}
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
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "failed", RawFinish: "error"}

	sumTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Summary: &sumTime}
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
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)

	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent"}
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

	fakeDriver.mu.Lock()
	aborts := fakeDriver.abortCalls
	fakeDriver.mu.Unlock()
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
	s := newTestServer(t, "http://api.trello.invalid")
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)

	abortTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Abort: &abortTime}

	s.handleDoingOut(context.Background(), "c1", time.Now())

	fakeDriver.mu.Lock()
	defer fakeDriver.mu.Unlock()
	if len(fakeDriver.abortCalls) > 0 {
		t.Error("second abort should not be sent")
	}
}

// ---------- doing.in ----------

func TestHandleDoingInStartsSession(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_new"

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	card := trelloCard{
		ID:     "c1",
		Name:   "Test card",
		Desc:   "do the thing",
		Labels: []trelloLabel{{Name: "proj:agent"}},
	}
	s.handleDoingIn(context.Background(), card, time.Now())

	s.mu.Lock()
	task, ok := s.tasks["c1"]
	total := s.totalCount
	projCount := s.projCount["agent"]
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
		t.Errorf("projCount[agent]=%d, want 1", projCount)
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

func TestHandleDoingInIgnoresNoProjLabel(t *testing.T) {
	s := newTestServer(t, "http://api.trello.invalid")
	card := trelloCard{ID: "c1", Name: "no proj", Desc: "human task"}
	s.handleDoingIn(context.Background(), card, time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.tasks["c1"]; ok {
		t.Error("card without proj:* label should be silently ignored")
	}
	if s.totalCount != 0 {
		t.Errorf("totalCount=%d, want 0", s.totalCount)
	}
}

func TestHandleDoingInIdempotent(t *testing.T) {
	// Already-tracked cards must not be double-counted.
	s := newTestServer(t, "http://api.trello.invalid")
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
	trSrv := newFakeTrelloServer(t, trello)
	s := newTestServer(t, trSrv)
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

func TestHandleDoingInAgentFail(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)
	s := newTestServer(t, trSrv)
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}

	card := trelloCard{
		ID:     "c1",
		Labels: []trelloLabel{{Name: "proj:agent"}, {Name: "agent:notinlist"}},
	}
	s.handleDoingIn(context.Background(), card, time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should not be created on agent parse fail")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
		t.Errorf("moves=%v, want move to done", trello.moves)
	}
	var found bool
	for _, c := range trello.comments {
		if strings.Contains(c, "agent label is invalid") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected agent error comment, got %v", trello.comments)
	}
}

func TestHandleDoingInCapFull(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)
	s := newTestServer(t, trSrv)
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	s.totalCount = s.cfg.MaxDoingTotal // at global cap

	card := trelloCard{ID: "c1", Labels: []trelloLabel{{Name: "proj:agent"}}}
	s.handleDoingIn(context.Background(), card, time.Now())

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
	trSrv := newFakeTrelloServer(t, trello)
	s := newTestServer(t, trSrv)
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	s.projCount["agent"] = s.cfg.MaxDoingPerProject // proj:agent at cap

	card := trelloCard{ID: "c1", Labels: []trelloLabel{{Name: "proj:agent"}}}
	s.handleDoingIn(context.Background(), card, time.Now())

	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testTodoID {
		t.Errorf("card should go back to todo, moves=%v", trello.moves)
	}
}

// ---------- timeout ----------

func TestCheckOneTimeoutAbort(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)
	s := newTestServer(t, trSrv)
	s.cfg.AbortTimeout = time.Millisecond

	abortTime := time.Now().Add(-time.Second) // set 1s ago
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Abort: &abortTime}
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
	trSrv := newFakeTrelloServer(t, trello)
	s := newTestServer(t, trSrv)
	s.cfg.SummaryTimeout = time.Millisecond

	sumTime := time.Now().Add(-time.Second) // set 1s ago
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Summary: &sumTime}
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
	s := newTestServer(t, "http://api.trello.invalid")
	s.cfg.AbortTimeout = time.Hour
	s.cfg.SummaryTimeout = time.Hour

	abortTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Abort: &abortTime}
	s.totalCount = 1

	s.checkOneTimeout(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; !ok {
		t.Error("task should remain when not timed out")
	}
}

// ---------- promoteTodo ----------

func TestPromoteTodoBasic(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_promoted"

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	// t1: no proj:* label → silently skipped (not moved, no comment)
	// t2: unknown proj label → moved to done + attention
	// t3: valid proj:agent → promoted to doing
	trello.setCards(testTodoID, []trelloCard{
		{ID: "t1", Name: "T1"},
		{ID: "t2", Name: "T2", Labels: []trelloLabel{{Name: "proj:unknown"}}},
		{ID: "t3", Name: "T3", Labels: []trelloLabel{{Name: "proj:agent"}}},
	})

	s.promoteTodo(context.Background(), time.Now())

	s.mu.Lock()
	total := s.totalCount
	s.mu.Unlock()

	// t1 silently skipped, t2 moved to done, t3 promoted
	if total != 1 {
		t.Errorf("totalCount=%d, want 1 (only t3 promoted)", total)
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	var t1Moved, t2ToDone, t3ToDoing bool
	for _, m := range trello.moves {
		if m.cardID == "t1" {
			t1Moved = true
		}
		if m.cardID == "t2" && m.listID == testDoneID {
			t2ToDone = true
		}
		if m.cardID == "t3" && m.listID == testDoingID {
			t3ToDoing = true
		}
	}
	if t1Moved {
		t.Errorf("t1 (no proj label) should not be moved, moves=%v", trello.moves)
	}
	if !t2ToDone {
		t.Errorf("t2 (unknown proj) should be moved to done, moves=%v", trello.moves)
	}
	if !t3ToDoing {
		t.Errorf("t3 (valid proj) should be promoted to doing, moves=%v", trello.moves)
	}
	// t1 should produce no comments
	for _, c := range trello.comments {
		// comments for t1 would be problematic
		_ = c
	}
}

func TestPromoteTodoSkipsNoProjLabel(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	// Cards without proj:* label are not AI-managed and must be silently skipped.
	trello.setCards(testTodoID, []trelloCard{
		{ID: "t1", Name: "no proj task"},
		{ID: "t2", Name: "human task", Labels: []trelloLabel{{Name: "human"}}},
	})

	s.promoteTodo(context.Background(), time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.totalCount != 0 {
		t.Error("cards without proj:* label should not be promoted")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) > 0 {
		t.Errorf("cards without proj:* label should not be moved, got %v", trello.moves)
	}
}

func TestPromoteTodoNoProjSkippedNextProjStarts(t *testing.T) {
	// Cards without proj:* label must be skipped silently; subsequent proj-labeled cards
	// must still be promoted (continue, not return).
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_y"

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	trello.setCards(testTodoID, []trelloCard{
		{ID: "t1", Name: "no proj"}, // silently skipped
		{ID: "t2", Name: "AI task", Labels: []trelloLabel{{Name: "proj:agent"}}}, // promoted
	})

	s.promoteTodo(context.Background(), time.Now())

	s.mu.Lock()
	total := s.totalCount
	_, t2ok := s.tasks["t2"]
	s.mu.Unlock()

	if total != 1 {
		t.Errorf("totalCount=%d, want 1", total)
	}
	if !t2ok {
		t.Error("t2 (proj:agent) should be promoted")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	for _, m := range trello.moves {
		if m.cardID == "t1" {
			t.Errorf("t1 (no proj:*) must not be moved, got %v", trello.moves)
		}
	}
}

func TestPromoteTodoStopsAtGlobalCap(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
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
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	s.cfg.MaxDoingTotal = 5
	s.cfg.MaxDoingPerProject = 1
	s.cfg.AllowedProjects = []AllowedProject{
		{Label: "proj:kanban", Name: "kanban"},
		{Label: "proj:agent", Name: "agent"},
	}
	s.projCount["kanban"] = 1 // proj:kanban at cap

	// t1 has proj:kanban (at cap → skip), t2 has proj:agent (not at cap → promoted)
	trello.setCards(testTodoID, []trelloCard{
		{ID: "t1", Name: "T1", Labels: []trelloLabel{{Name: "proj:kanban"}}},
		{ID: "t2", Name: "T2", Labels: []trelloLabel{{Name: "proj:agent"}}},
	})

	s.promoteTodo(context.Background(), time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.totalCount != 1 {
		t.Errorf("totalCount=%d, want 1 (only t2 promoted)", s.totalCount)
	}
	if _, ok := s.tasks["t2"]; !ok {
		t.Error("t2 (proj:agent) should be promoted")
	}
	if _, ok := s.tasks["t1"]; ok {
		t.Error("t1 (proj:kanban at cap) should not be promoted")
	}
}

// ---------- reconcileDoing ----------

func TestReconcileDoingOutThenIn(t *testing.T) {
	// doing.out keeps the task (just sets Abort). Capacity is NOT released
	// until abort is confirmed via finish or timeout. So c_new cannot start
	// when c_old holds the capacity slot.
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_new"

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	// c_old is tracked but no longer in doing → doing.out sets abort
	// c_new has proj:agent and is in doing but c_old holds the capacity slot → c_new moves back to todo
	s.tasks["c_old"] = &Task{CardID: "c_old", SessionID: "ses_old", Proj: "agent", Agent: "test-agent"}
	s.totalCount = 1
	s.projCount["agent"] = 1

	trello.setCards(testDoingID, []trelloCard{
		{ID: "c_new", Name: "new card", Labels: []trelloLabel{{Name: "proj:agent"}}},
	})

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

func TestReconcileDoingIgnoresNoProjLabel(t *testing.T) {
	// Cards without proj:* label in the doing list are not AI-managed and must be ignored.
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	trello.setCards(testDoingID, []trelloCard{
		{ID: "c1", Name: "no proj task"},
		{ID: "c2", Name: "human task", Labels: []trelloLabel{{Name: "human"}}},
	})

	s.reconcileDoing(context.Background(), time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.tasks["c1"]; ok {
		t.Error("card without proj:* label should be ignored in doing")
	}
	if _, ok := s.tasks["c2"]; ok {
		t.Error("human card without proj:* label should be ignored in doing")
	}
	if s.totalCount != 0 {
		t.Errorf("totalCount=%d, want 0", s.totalCount)
	}
}

// ---------- tick order ----------

func TestTickRunsInOrder(t *testing.T) {
	// Verify tick calls: finish → reconcile → timeout → promote
	// by observing effects. A card with a stop-finish should be moved to
	// done in the first tick.
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	// First state call: finished → sends summary prompt, sets Summary
	// But task already has Summary set → goes straight to done
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop", Text: "all done"}

	sumTime := time.Now()
	s.tasks["c1"] = &Task{
		CardID:    "c1",
		SessionID: "ses1",
		Proj:      "default",
		Agent:     "test-agent",
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
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	// c_old has abort+stop → abort done, destroy task (total=0)
	// Use stateQueue: first call for c_old returns finished (abort done)
	// then t1 will use ses_promoted session id
	fakeDriver.stateQueue = []AgentState{
		{Kind: "finished", RawFinish: "stop"},
	}
	fakeDriver.sessionID = "ses_promoted"

	s.cfg.MaxDoingTotal = 1
	s.cfg.MaxDoingPerProject = 1
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}

	abortTime := time.Now().Add(-2 * s.cfg.AbortTimeout) // already timed out
	s.tasks["c_old"] = &Task{CardID: "c_old", SessionID: "ses_old", Proj: "agent", Agent: "test-agent", Abort: &abortTime}
	s.totalCount = 1
	s.projCount["agent"] = 1

	trello.setCards(testDoingID, nil) // c_old not in doing
	trello.setCards(testTodoID, []trelloCard{
		{ID: "t1", Name: "T1", Labels: []trelloLabel{{Name: "proj:agent"}}},
	})

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

// ---------- api tests (reconcileDoing error) ----------

func TestReconcileDoingError(t *testing.T) {
	srv := newFakeHTTPServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	s := newTestServer(t, srv)
	log := &drainLog{}
	withLogWriter(t, log)

	s.reconcileDoing(context.Background(), time.Now())

	if !strings.Contains(log.String(), "reconcile.doing.error") {
		t.Errorf("expected reconcile.doing.error log, got %s", log.String())
	}
}

// ---------- orphan session compensation ----------

func TestHandleDoingInAbortsSessionOnPromptFail(t *testing.T) {
	// When CreateSession succeeds but SendPrompt fails,
	// AbortSession must be called to avoid an orphan session.
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_orphan"
	fakeDriver.promptErr = fmt.Errorf("prompt failed")

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent", Root: "/repo"}}

	card := trelloCard{ID: "c1", Labels: []trelloLabel{{Name: "proj:agent"}}}
	s.handleDoingIn(context.Background(), card, time.Now())

	// Task must be gone (capacity released).
	s.mu.Lock()
	_, taskExists := s.tasks["c1"]
	total := s.totalCount
	s.mu.Unlock()

	if taskExists {
		t.Error("task should be destroyed after prompt failure")
	}
	if total != 0 {
		t.Errorf("totalCount=%d, want 0", total)
	}

	// abort must have been called for the created session.
	fakeDriver.mu.Lock()
	aborts := fakeDriver.abortCalls
	fakeDriver.mu.Unlock()
	if len(aborts) != 1 || aborts[0] != "ses_orphan" {
		t.Errorf("expected abort of ses_orphan, got abortCalls=%v", aborts)
	}
}

// ---------- session_new hook integration ----------

func TestHandleDoingInSessionNewHookSuccess(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_new"

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent", Root: "/repo/agent"}}
	hook := s.hookRunner.(*fakeHookRunner)
	hook.result = HookResult{Workdir: "/repo/agent/worktree", Comment: "Worktree ready."}

	card := trelloCard{
		ID:     "c1",
		Name:   "My task",
		Desc:   "do the thing",
		Labels: []trelloLabel{{Name: "proj:agent"}},
	}
	s.handleDoingIn(context.Background(), card, time.Now())

	s.mu.Lock()
	task, ok := s.tasks["c1"]
	s.mu.Unlock()

	if !ok {
		t.Fatal("task not created")
	}
	if task.SessionID != "ses_new" {
		t.Errorf("SessionID=%q, want ses_new", task.SessionID)
	}
	if task.Workdir != "/repo/agent/worktree" {
		t.Errorf("Workdir=%q, want /repo/agent/worktree", task.Workdir)
	}
	if task.CardTitle != "My task" {
		t.Errorf("CardTitle=%q, want 'My task'", task.CardTitle)
	}

	hook.mu.Lock()
	defer hook.mu.Unlock()
	if len(hook.calls) != 1 || hook.calls[0].Event != "session_new" {
		t.Errorf("hook calls=%v", hook.calls)
	}

	// Verify the hook's comment was posted to Trello.
	trello.mu.Lock()
	defer trello.mu.Unlock()
	var hookComment, startedComment bool
	for _, c := range trello.comments {
		if strings.Contains(c, "Worktree ready.") {
			hookComment = true
		}
		if strings.Contains(c, "Started session ses_new") {
			startedComment = true
		}
	}
	if !hookComment {
		t.Errorf("hook comment not found in %v", trello.comments)
	}
	if !startedComment {
		t.Errorf("started comment not found in %v", trello.comments)
	}
}

func TestHandleDoingInSessionNewHookFail(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent", Root: "/repo"}}
	hook := s.hookRunner.(*fakeHookRunner)
	hook.err = fmt.Errorf("hook script failed: exit 1")

	card := trelloCard{
		ID:     "c1",
		Labels: []trelloLabel{{Name: "proj:agent"}},
	}
	s.handleDoingIn(context.Background(), card, time.Now())

	// Task must be destroyed (no remaining task, capacity released).
	s.mu.Lock()
	_, ok := s.tasks["c1"]
	total := s.totalCount
	s.mu.Unlock()

	if ok {
		t.Error("task should be destroyed after hook failure")
	}
	if total != 0 {
		t.Errorf("totalCount=%d, want 0 (capacity released)", total)
	}

	// Card must move to done with attention and a comment.
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
		t.Errorf("card should move to done, moves=%v", trello.moves)
	}
	if len(trello.labelAdds) != 1 {
		t.Error("attention label should be added")
	}
	var found bool
	for _, c := range trello.comments {
		if strings.Contains(c, "Hook session_new failed") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected hook failure comment, got %v", trello.comments)
	}
}

func TestHandleDoingInPendingTaskCountsCapacity(t *testing.T) {
	// When the hook fails, the pending task must be destroyed and capacity released.
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	s.cfg.MaxDoingTotal = 1
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent", Root: "/repo"}}
	hook := s.hookRunner.(*fakeHookRunner)
	hook.err = fmt.Errorf("hook failed")

	card := trelloCard{ID: "c1", Labels: []trelloLabel{{Name: "proj:agent"}}}
	s.handleDoingIn(context.Background(), card, time.Now())

	// After failure: total must be 0 (capacity fully released).
	s.mu.Lock()
	total := s.totalCount
	s.mu.Unlock()
	if total != 0 {
		t.Errorf("totalCount=%d, want 0 after hook failure", total)
	}
}

func TestCheckSessionFinishSkipsPending(t *testing.T) {
	s := newTestServer(t, "http://api.trello.invalid")
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop"}

	// Pending task must be skipped — no API calls made.
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "__pending__", Proj: "agent", Agent: "test-agent"}
	s.totalCount = 1

	s.checkSessionFinish(context.Background(), time.Now())

	// Task must still be there.
	s.mu.Lock()
	_, ok := s.tasks["c1"]
	s.mu.Unlock()
	if !ok {
		t.Error("pending task should remain untouched in checkSessionFinish")
	}

	// No API calls made to driver.
	fakeDriver.mu.Lock()
	defer fakeDriver.mu.Unlock()
	if len(fakeDriver.promptCalls) > 0 || len(fakeDriver.abortCalls) > 0 {
		t.Error("checkSessionFinish should not call driver for pending tasks")
	}
}

// ---------- session_finish hook ----------

func TestCheckOneFinishStopWithSummaryRunsFinishHook(t *testing.T) {
	summaryText := "Done."
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop", Text: summaryText}

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	hook := s.hookRunner.(*fakeHookRunner)

	sumTime := time.Now()
	s.tasks["c1"] = &Task{
		CardID: "c1", CardTitle: "T1", SessionID: "ses1",
		Proj: "agent", Agent: "test-agent", Summary: &sumTime,
	}
	s.totalCount = 1
	s.projCount["agent"] = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	// Hook must have been called.
	hook.mu.Lock()
	calls := hook.calls
	hook.mu.Unlock()
	if len(calls) != 1 || calls[0].Event != "session_finish" {
		t.Errorf("session_finish hook not called, calls=%v", calls)
	}

	// Task must be gone, card moved to done.
	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
		t.Errorf("card should move to done, moves=%v", trello.moves)
	}
}

func TestCheckOneFinishStopWithSummaryHookFail(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop", Text: "summary"}

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	hook := s.hookRunner.(*fakeHookRunner)
	hook.err = fmt.Errorf("finish hook failed")

	sumTime := time.Now()
	s.tasks["c1"] = &Task{
		CardID: "c1", SessionID: "ses1", Proj: "agent", Agent: "test-agent", Summary: &sumTime,
	}
	s.totalCount = 1
	s.projCount["agent"] = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	// Task must still be destroyed and card moved to done despite hook failure.
	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed even on hook failure")
	}
	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.moves) != 1 || trello.moves[0].listID != testDoneID {
		t.Errorf("card should still move to done on hook failure, moves=%v", trello.moves)
	}
	// attention label must be added.
	if len(trello.labelAdds) != 1 {
		t.Errorf("attention should be added on hook failure, labelAdds=%v", trello.labelAdds)
	}
	var hookFailComment bool
	for _, c := range trello.comments {
		if strings.Contains(c, "Hook session_finish failed") {
			hookFailComment = true
		}
	}
	if !hookFailComment {
		t.Errorf("hook failure comment not found in %v", trello.comments)
	}
}

// ---------- session_abort hook ----------

func TestCheckOneFinishAbortDoneRunsAbortHook(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop"}

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	hook := s.hookRunner.(*fakeHookRunner)

	abortTime := time.Now()
	s.tasks["c1"] = &Task{
		CardID: "c1", CardTitle: "T1", SessionID: "ses1",
		Proj: "agent", Agent: "test-agent", Abort: &abortTime,
	}
	s.totalCount = 1
	s.projCount["agent"] = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	hook.mu.Lock()
	calls := hook.calls
	hook.mu.Unlock()
	if len(calls) != 1 || calls[0].Event != "session_abort" {
		t.Errorf("session_abort hook not called, calls=%v", calls)
	}
	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed after abort done")
	}
}

func TestCheckOneFinishAbortDoneHookFail(t *testing.T) {
	trello := newFakeTrello()
	trSrv := newFakeTrelloServer(t, trello)

	s := newTestServer(t, trSrv)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop"}

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	hook := s.hookRunner.(*fakeHookRunner)
	hook.err = fmt.Errorf("abort hook failed")

	abortTime := time.Now()
	s.tasks["c1"] = &Task{
		CardID: "c1", SessionID: "ses1", Proj: "agent", Agent: "test-agent", Abort: &abortTime,
	}
	s.totalCount = 1
	s.projCount["agent"] = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	// Task must be destroyed and capacity released despite hook failure.
	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed even on abort hook failure")
	}
	if s.totalCount != 0 {
		t.Errorf("totalCount=%d, want 0", s.totalCount)
	}

	trello.mu.Lock()
	defer trello.mu.Unlock()
	if len(trello.labelAdds) != 1 {
		t.Errorf("attention should be added on abort hook failure, labelAdds=%v", trello.labelAdds)
	}
	var hookFailComment bool
	for _, c := range trello.comments {
		if strings.Contains(c, "Hook session_abort failed") {
			hookFailComment = true
		}
	}
	if !hookFailComment {
		t.Errorf("hook failure comment not found in %v", trello.comments)
	}
}
