package kanban

import (
	"context"
	"errors"
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
	card := CardSnapshot{Labels: []string{"human", "proj:agent"}}
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
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "running"}

	s.tasks["c1"] = &Task{
		CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent",
		Labels: []string{"proj:agent", "model:step-3.6"},
	}
	s.totalCount = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; !ok {
		t.Error("task should remain when no finish")
	}
}

func TestCheckOneFinishSkipsToolCalls(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "running", RawFinish: "tool-calls"}

	s.tasks["c1"] = &Task{
		CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent",
		Labels: []string{"proj:agent", "model:step-3.6"},
	}
	s.totalCount = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; !ok {
		t.Error("task should remain for tool-calls finish")
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) > 0 {
		t.Error("no moves expected for tool-calls")
	}
}

func TestCheckOneFinishAbortDone(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
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
	board.mu.Lock()
	defer board.mu.Unlock()
	var found bool
	for _, c := range board.comments {
		if strings.Contains(c, "Abort completed") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected 'Abort completed' comment, got %v", board.comments)
	}
	if len(board.moves) > 0 {
		t.Error("abort done should not move card")
	}
}

func TestCheckOneFinishAbnormalFinishes(t *testing.T) {
	abnormal := []string{"length", "content-filter", "error", "unknown"}
	for _, finish := range abnormal {
		t.Run(finish, func(t *testing.T) {
			board := newFakeBoardGateway()
			s := newTestServer(t, board)
			fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
			fakeDriver.state = AgentState{Kind: "failed", RawFinish: finish}

			s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent"}
			s.totalCount = 1

			s.checkOneFinish(context.Background(), "c1", time.Now())

			if _, ok := s.tasks["c1"]; ok {
				t.Error("task should be destroyed after abnormal finish")
			}
			board.mu.Lock()
			defer board.mu.Unlock()
			if len(board.moves) != 1 || board.moves[0].list != "done" {
				t.Errorf("card should move to done, moves=%v", board.moves)
			}
			if len(board.labelAdds) != 1 || board.labelAdds[0] != "attention" {
				t.Errorf("attention label expected, labelAdds=%v", board.labelAdds)
			}
			var found bool
			for _, c := range board.comments {
				if strings.Contains(c, "status="+finish) {
					found = true
				}
			}
			if !found {
				t.Errorf("comment should mention status=%s, got %v", finish, board.comments)
			}
		})
	}
}

func TestCheckOneFinishStopSendsSummary(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses1"
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop"}

	s.tasks["c1"] = &Task{
		CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent",
		Labels: []string{"proj:agent", "model:step-3.6"},
	}
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
	var summaryLabels []string
	for _, pc := range fakeDriver.promptCalls {
		if strings.Contains(pc.Prompt, "总结") {
			found = true
			summaryLabels = pc.Labels
		}
	}
	fakeDriver.mu.Unlock()
	if !found {
		t.Error("summary prompt should have been sent")
	}
	if !stringSliceContains(summaryLabels, "model:step-3.6") {
		t.Errorf("summary labels=%v, want model:step-3.6", summaryLabels)
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) > 0 {
		t.Error("card should not move on first stop")
	}
}

func TestCheckOneFinishStopWithSummaryCompletes(t *testing.T) {
	summaryText := "完成了一个 bug 修复。"
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop", Text: summaryText}

	sumTime := time.Now()
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Summary: &sumTime}
	s.totalCount = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed after completion")
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("card should move to done, moves=%v", board.moves)
	}
	var summaryComment string
	for _, c := range board.comments {
		if strings.Contains(c, summaryText) {
			summaryComment = c
		}
	}
	if summaryComment == "" {
		t.Errorf("summary comment not found in %v", board.comments)
	}
	if !strings.HasPrefix(summaryComment, "Task finished. Summary:") {
		t.Errorf("comment=%q, want 'Task finished. Summary:'", summaryComment)
	}
}

func TestCheckOneFinishSummaryAbnormal(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
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
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("moves=%v", board.moves)
	}
	if len(board.labelAdds) != 1 {
		t.Errorf("attention should be added, labelAdds=%v", board.labelAdds)
	}
}

func TestCheckOneFinishAbnormalMoveFailureKeepsTask(t *testing.T) {
	board := newFakeBoardGateway()
	board.moveErr = errors.New("move failed")
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "failed", RawFinish: "error"}

	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent"}
	s.totalCount = 1

	s.checkOneFinish(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; !ok {
		t.Error("task should remain when move-to-done fails")
	}
	if s.totalCount != 1 {
		t.Errorf("totalCount=%d, want 1", s.totalCount)
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.labelAdds) != 0 || len(board.comments) != 0 {
		t.Errorf("label/comment should wait until move succeeds, labels=%v comments=%v", board.labelAdds, board.comments)
	}
}

// ---------- doing.out ----------

func TestHandleDoingOut(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
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

	board.mu.Lock()
	defer board.mu.Unlock()
	var found bool
	for _, c := range board.comments {
		if strings.Contains(c, "Abort requested") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected 'Abort requested' comment, got %v", board.comments)
	}
	if len(board.moves) > 0 {
		t.Error("doing.out should not move card immediately")
	}
}

func TestHandleDoingOutIdempotent(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
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
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_new"

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	card := CardSnapshot{
		ID:          "c1",
		Title:       "Test card",
		Description: "do the thing",
		Labels:      []string{"proj:agent"},
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

	board.mu.Lock()
	defer board.mu.Unlock()
	var found bool
	for _, c := range board.comments {
		if strings.Contains(c, "Started session ses_new") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected 'Started session ses_new', got %v", board.comments)
	}
}

func TestHandleDoingInIgnoresNoProjLabel(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	card := CardSnapshot{ID: "c1", Title: "no proj", Description: "human task"}
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
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses_existing"}
	s.totalCount = 1

	s.handleDoingIn(context.Background(), CardSnapshot{ID: "c1"}, time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.totalCount != 1 {
		t.Error("should not double-count already-tracked card")
	}
}

func TestHandleDoingInProjFail(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}

	card := CardSnapshot{
		ID:     "c1",
		Labels: []string{"proj:unknown"},
	}
	s.handleDoingIn(context.Background(), card, time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should not be created on proj parse fail")
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("moves=%v, want move to done", board.moves)
	}
	if len(board.labelAdds) != 1 {
		t.Error("attention label should be added")
	}
	var found bool
	for _, c := range board.comments {
		if strings.Contains(c, "project label is invalid") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected proj error comment, got %v", board.comments)
	}
}

func TestHandleDoingInAgentFail(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}

	card := CardSnapshot{
		ID:     "c1",
		Labels: []string{"proj:agent", "agent:notinlist"},
	}
	s.handleDoingIn(context.Background(), card, time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should not be created on agent parse fail")
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("moves=%v, want move to done", board.moves)
	}
	var found bool
	for _, c := range board.comments {
		if strings.Contains(c, "agent label is invalid") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected agent error comment, got %v", board.comments)
	}
}

func TestHandleDoingInCapFull(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	s.totalCount = s.cfg.MaxDoingTotal // at global cap

	card := CardSnapshot{ID: "c1", Labels: []string{"proj:agent"}}
	s.handleDoingIn(context.Background(), card, time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should not be created when at cap")
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "todo" {
		t.Errorf("card should go back to todo, moves=%v", board.moves)
	}
	var found bool
	for _, c := range board.comments {
		if strings.Contains(c, "capacity is full") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected capacity comment, got %v", board.comments)
	}
}

func TestHandleDoingInProjCapFull(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	s.projCount["agent"] = s.cfg.MaxDoingPerProject // proj:agent at cap

	card := CardSnapshot{ID: "c1", Labels: []string{"proj:agent"}}
	s.handleDoingIn(context.Background(), card, time.Now())

	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "todo" {
		t.Errorf("card should go back to todo, moves=%v", board.moves)
	}
}

// ---------- timeout ----------

func TestCheckOneTimeoutAbort(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
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
	board.mu.Lock()
	defer board.mu.Unlock()
	var found bool
	for _, c := range board.comments {
		if strings.Contains(c, "Abort timeout") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected 'Abort timeout' comment, got %v", board.comments)
	}
	if len(board.labelAdds) != 1 {
		t.Error("attention label should be added on abort timeout")
	}
	if len(board.moves) > 0 {
		t.Error("abort timeout should not move card")
	}
}

func TestCheckOneTimeoutSummary(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	s.cfg.SummaryTimeout = time.Millisecond

	sumTime := time.Now().Add(-time.Second) // set 1s ago
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Summary: &sumTime}
	s.totalCount = 1
	s.projCount["default"] = 1

	s.checkOneTimeout(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed on summary timeout")
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("card should move to done on summary timeout, moves=%v", board.moves)
	}
	var found bool
	for _, c := range board.comments {
		if strings.Contains(c, "Summary timeout") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected 'Summary timeout' comment, got %v", board.comments)
	}
}

func TestCheckOneTimeoutSummaryMoveFailureKeepsTask(t *testing.T) {
	board := newFakeBoardGateway()
	board.moveErr = errors.New("move failed")
	s := newTestServer(t, board)
	s.cfg.SummaryTimeout = time.Millisecond

	sumTime := time.Now().Add(-time.Second)
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Summary: &sumTime}
	s.totalCount = 1
	s.projCount["default"] = 1

	s.checkOneTimeout(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; !ok {
		t.Error("task should remain when summary timeout move-to-done fails")
	}
	if s.totalCount != 1 {
		t.Errorf("totalCount=%d, want 1", s.totalCount)
	}
}

func TestCheckOneTimeoutSummaryCommentFailureReleasesTask(t *testing.T) {
	board := newFakeBoardGateway()
	board.commentErr = errors.New("comment failed")
	s := newTestServer(t, board)
	s.cfg.SummaryTimeout = time.Millisecond

	sumTime := time.Now().Add(-time.Second)
	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "ses1", Proj: "default", Agent: "test-agent", Summary: &sumTime}
	s.totalCount = 1
	s.projCount["default"] = 1

	s.checkOneTimeout(context.Background(), "c1", time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed when move succeeds even if comment fails")
	}
}

func TestCheckOneTimeoutNoTimeout(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
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
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_promoted"

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	// t1: no proj:* label → silently skipped (not moved, no comment)
	// t2: unknown proj label → moved to done + attention
	// t3: valid proj:agent → promoted to doing
	board.setCards("todo", []CardSnapshot{
		{ID: "t1", Title: "T1"},
		{ID: "t2", Title: "T2", Labels: []string{"proj:unknown"}},
		{ID: "t3", Title: "T3", Labels: []string{"proj:agent"}},
	})

	s.promoteTodo(context.Background(), time.Now())

	s.mu.Lock()
	total := s.totalCount
	s.mu.Unlock()

	// t1 silently skipped, t2 moved to done, t3 promoted
	if total != 1 {
		t.Errorf("totalCount=%d, want 1 (only t3 promoted)", total)
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	var t1Moved, t2ToDone, t3ToDoing bool
	for _, m := range board.moves {
		if m.cardID == "t1" {
			t1Moved = true
		}
		if m.cardID == "t2" && m.list == "done" {
			t2ToDone = true
		}
		if m.cardID == "t3" && m.list == "doing" {
			t3ToDoing = true
		}
	}
	if t1Moved {
		t.Errorf("t1 (no proj label) should not be moved, moves=%v", board.moves)
	}
	if !t2ToDone {
		t.Errorf("t2 (unknown proj) should be moved to done, moves=%v", board.moves)
	}
	if !t3ToDoing {
		t.Errorf("t3 (valid proj) should be promoted to doing, moves=%v", board.moves)
	}
}

func TestPromoteTodoSkipsNoProjLabel(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	board.setCards("todo", []CardSnapshot{
		{ID: "t1", Title: "no proj task"},
		{ID: "t2", Title: "human task", Labels: []string{"human"}},
	})

	s.promoteTodo(context.Background(), time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.totalCount != 0 {
		t.Error("cards without proj:* label should not be promoted")
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) > 0 {
		t.Errorf("cards without proj:* label should not be moved, got %v", board.moves)
	}
}

func TestPromoteTodoNoProjSkippedNextProjStarts(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_y"

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	board.setCards("todo", []CardSnapshot{
		{ID: "t1", Title: "no proj"},                                 // silently skipped
		{ID: "t2", Title: "AI task", Labels: []string{"proj:agent"}}, // promoted
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
	board.mu.Lock()
	defer board.mu.Unlock()
	for _, m := range board.moves {
		if m.cardID == "t1" {
			t.Errorf("t1 (no proj:*) must not be moved, got %v", board.moves)
		}
	}
}

func TestPromoteTodoStopsAtGlobalCap(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	s.cfg.MaxDoingTotal = 2
	s.cfg.MaxDoingPerProject = 3 // high per-project cap
	s.totalCount = 2             // already at global cap

	board.setCards("todo", []CardSnapshot{{ID: "t1", Title: "T1"}})
	s.promoteTodo(context.Background(), time.Now())

	s.mu.Lock()
	defer s.mu.Unlock()
	if s.totalCount != 2 {
		t.Error("should not promote when at global cap")
	}
}

func TestPromoteTodoSkipsWhenProjAtCap(t *testing.T) {
	board := newFakeBoardGateway()
	board.knownLabels["proj:kanban"] = true
	s := newTestServer(t, board)
	s.cfg.MaxDoingTotal = 5
	s.cfg.MaxDoingPerProject = 1
	s.cfg.AllowedProjects = []AllowedProject{
		{Label: "proj:kanban", Name: "kanban"},
		{Label: "proj:agent", Name: "agent"},
	}
	s.projCount["kanban"] = 1 // proj:kanban at cap

	board.setCards("todo", []CardSnapshot{
		{ID: "t1", Title: "T1", Labels: []string{"proj:kanban"}},
		{ID: "t2", Title: "T2", Labels: []string{"proj:agent"}},
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
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_new"

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent"}}
	// c_old is tracked but no longer in doing → doing.out sets abort
	// c_new has proj:agent and is in doing but c_old holds the capacity slot → c_new moves back to todo
	s.tasks["c_old"] = &Task{CardID: "c_old", SessionID: "ses_old", Proj: "agent", Agent: "test-agent"}
	s.totalCount = 1
	s.projCount["agent"] = 1

	board.setCards("doing", []CardSnapshot{
		{ID: "c_new", Title: "new card", Labels: []string{"proj:agent"}},
	})

	s.reconcileDoing(context.Background(), time.Now())

	s.mu.Lock()
	oldTask, oldOk := s.tasks["c_old"]
	_, newOk := s.tasks["c_new"]
	s.mu.Unlock()

	if !oldOk {
		t.Error("c_old should remain in tasks after doing.out")
	} else if oldTask.Abort == nil {
		t.Error("c_old.Abort should be set after doing.out")
	}

	if newOk {
		t.Error("c_new should not start while c_old holds capacity")
	}

	board.mu.Lock()
	defer board.mu.Unlock()
	var abortComment bool
	for _, c := range board.comments {
		if strings.Contains(c, "Abort requested") {
			abortComment = true
		}
	}
	if !abortComment {
		t.Errorf("expected 'Abort requested' comment, got %v", board.comments)
	}
	var backToTodo bool
	for _, m := range board.moves {
		if m.cardID == "c_new" && m.list == "todo" {
			backToTodo = true
		}
	}
	if !backToTodo {
		t.Errorf("c_new should move back to todo due to capacity, moves=%v", board.moves)
	}
}

func TestReconcileDoingIgnoresNoProjLabel(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	board.setCards("doing", []CardSnapshot{
		{ID: "c1", Title: "no proj task"},
		{ID: "c2", Title: "human task", Labels: []string{"human"}},
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
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop", Text: "all done"}

	sumTime := time.Now()
	s.tasks["c1"] = &Task{
		CardID:    "c1",
		SessionID: "ses1",
		Proj:      "default",
		Agent:     "test-agent",
		Summary:   &sumTime,
	}
	s.totalCount = 1

	s.tick(context.Background(), time.Now())

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed after tick completes the finish flow")
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("card should move to done, moves=%v", board.moves)
	}
}

// ---------- capacity release → same-tick promote ----------

func TestCapacityReleasedInSameTick(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
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

	board.setCards("doing", nil) // c_old not in doing
	board.setCards("todo", []CardSnapshot{
		{ID: "t1", Title: "T1", Labels: []string{"proj:agent"}},
	})

	s.tick(context.Background(), time.Now())

	s.mu.Lock()
	total := s.totalCount
	_, t1Ok := s.tasks["t1"]
	s.mu.Unlock()

	if total != 1 {
		t.Errorf("totalCount=%d, want 1 (t1 promoted after c_old destroyed)", total)
	}
	if !t1Ok {
		t.Error("t1 should be in tasks after promotion")
	}
}

// ---------- api tests (reconcileDoing error) ----------

func TestReconcileDoingError(t *testing.T) {
	board := newFakeBoardGateway()
	board.listCardsErr = fmt.Errorf("server error")
	s := newTestServer(t, board)
	log := &drainLog{}
	withLogWriter(t, log)

	// Use a fake HTTP server that returns 500 for tests that still need one.
	srv := newFakeHTTPServer(t, func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	})
	_ = srv // not needed since board.listCardsErr triggers the error

	s.reconcileDoing(context.Background(), time.Now())

	if !strings.Contains(log.String(), "reconcile.doing.error") {
		t.Errorf("expected reconcile.doing.error log, got %s", log.String())
	}
}

// ---------- orphan session compensation ----------

func TestHandleDoingInAbortsSessionOnPromptFail(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_orphan"
	fakeDriver.promptErr = fmt.Errorf("prompt failed")

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent", Root: "/repo"}}

	card := CardSnapshot{ID: "c1", Labels: []string{"proj:agent"}}
	s.handleDoingIn(context.Background(), card, time.Now())

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

	fakeDriver.mu.Lock()
	aborts := fakeDriver.abortCalls
	fakeDriver.mu.Unlock()
	if len(aborts) != 1 || aborts[0] != "ses_orphan" {
		t.Errorf("expected abort of ses_orphan, got abortCalls=%v", aborts)
	}

	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("card should move to done on prompt failure, moves=%v", board.moves)
	}
	if len(board.labelAdds) != 1 || board.labelAdds[0] != "attention" {
		t.Errorf("attention should be added on prompt failure, labelAdds=%v", board.labelAdds)
	}
	var foundComment bool
	for _, c := range board.comments {
		if strings.Contains(c, "failed to send initial prompt") && strings.Contains(c, "ses_orphan") {
			foundComment = true
		}
	}
	if !foundComment {
		t.Errorf("prompt failure comment not found in %v", board.comments)
	}
}

func TestHandleDoingInCreateSessionFailVisibleOnBoard(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.createErr = fmt.Errorf("create failed")

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent", Root: "/repo"}}

	card := CardSnapshot{ID: "c1", Labels: []string{"proj:agent"}}
	s.handleDoingIn(context.Background(), card, time.Now())

	s.mu.Lock()
	_, taskExists := s.tasks["c1"]
	total := s.totalCount
	s.mu.Unlock()
	if taskExists {
		t.Error("task should be destroyed after create failure")
	}
	if total != 0 {
		t.Errorf("totalCount=%d, want 0", total)
	}

	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("card should move to done on create failure, moves=%v", board.moves)
	}
	if len(board.labelAdds) != 1 || board.labelAdds[0] != "attention" {
		t.Errorf("attention should be added on create failure, labelAdds=%v", board.labelAdds)
	}
	var foundComment bool
	for _, c := range board.comments {
		if strings.Contains(c, "failed to create session") && strings.Contains(c, "create failed") {
			foundComment = true
		}
	}
	if !foundComment {
		t.Errorf("create failure comment not found in %v", board.comments)
	}
}

// ---------- session_new hook integration ----------

func TestHandleDoingInSessionNewHookSuccess(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.sessionID = "ses_new"

	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent", Root: "/repo/agent"}}
	hook := s.hookRunner.(*fakeHookRunner)
	hook.result = HookResult{Workdir: "/repo/agent/worktree", Comment: "Worktree ready."}

	card := CardSnapshot{
		ID:          "c1",
		Title:       "My task",
		Description: "do the thing",
		Labels:      []string{"proj:agent"},
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

	board.mu.Lock()
	defer board.mu.Unlock()
	var hookComment, startedComment bool
	for _, c := range board.comments {
		if strings.Contains(c, "Worktree ready.") {
			hookComment = true
		}
		if strings.Contains(c, "Started session ses_new") {
			startedComment = true
		}
	}
	if !hookComment {
		t.Errorf("hook comment not found in %v", board.comments)
	}
	if !startedComment {
		t.Errorf("started comment not found in %v", board.comments)
	}
}

func TestHandleDoingInSessionNewHookFail(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent", Root: "/repo"}}
	hook := s.hookRunner.(*fakeHookRunner)
	hook.err = fmt.Errorf("hook script failed: exit 1")

	card := CardSnapshot{
		ID:     "c1",
		Labels: []string{"proj:agent"},
	}
	s.handleDoingIn(context.Background(), card, time.Now())

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

	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("card should move to done, moves=%v", board.moves)
	}
	if len(board.labelAdds) != 1 {
		t.Error("attention label should be added")
	}
	var found bool
	for _, c := range board.comments {
		if strings.Contains(c, "Hook session_new failed") {
			found = true
		}
	}
	if !found {
		t.Errorf("expected hook failure comment, got %v", board.comments)
	}
}

func TestHandleDoingInPendingTaskCountsCapacity(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	s.cfg.MaxDoingTotal = 1
	s.cfg.AllowedProjects = []AllowedProject{{Label: "proj:agent", Name: "agent", Root: "/repo"}}
	hook := s.hookRunner.(*fakeHookRunner)
	hook.err = fmt.Errorf("hook failed")

	card := CardSnapshot{ID: "c1", Labels: []string{"proj:agent"}}
	s.handleDoingIn(context.Background(), card, time.Now())

	s.mu.Lock()
	total := s.totalCount
	s.mu.Unlock()
	if total != 0 {
		t.Errorf("totalCount=%d, want 0 after hook failure", total)
	}
}

func TestCheckSessionFinishSkipsPending(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
	fakeDriver := s.drivers["test-agent"].(*fakeAgentDriver)
	fakeDriver.state = AgentState{Kind: "finished", RawFinish: "stop"}

	s.tasks["c1"] = &Task{CardID: "c1", SessionID: "__pending__", Proj: "agent", Agent: "test-agent"}
	s.totalCount = 1

	s.checkSessionFinish(context.Background(), time.Now())

	s.mu.Lock()
	_, ok := s.tasks["c1"]
	s.mu.Unlock()
	if !ok {
		t.Error("pending task should remain untouched in checkSessionFinish")
	}

	fakeDriver.mu.Lock()
	defer fakeDriver.mu.Unlock()
	if len(fakeDriver.promptCalls) > 0 || len(fakeDriver.abortCalls) > 0 {
		t.Error("checkSessionFinish should not call driver for pending tasks")
	}
}

// ---------- session_finish hook ----------

func TestCheckOneFinishStopWithSummaryRunsFinishHook(t *testing.T) {
	summaryText := "Done."
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
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

	hook.mu.Lock()
	calls := hook.calls
	hook.mu.Unlock()
	if len(calls) != 1 || calls[0].Event != "session_finish" {
		t.Errorf("session_finish hook not called, calls=%v", calls)
	}

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed")
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("card should move to done, moves=%v", board.moves)
	}
}

func TestCheckOneFinishStopWithSummaryHookFail(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
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

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed even on hook failure")
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("card should still move to done on hook failure, moves=%v", board.moves)
	}
	if len(board.labelAdds) != 1 {
		t.Errorf("attention should be added on hook failure, labelAdds=%v", board.labelAdds)
	}
	var hookFailComment bool
	for _, c := range board.comments {
		if strings.Contains(c, "Hook session_finish failed") {
			hookFailComment = true
		}
	}
	if !hookFailComment {
		t.Errorf("hook failure comment not found in %v", board.comments)
	}
}

// ---------- session_abort hook ----------

func TestCheckOneFinishAbortDoneRunsAbortHook(t *testing.T) {
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
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
	board := newFakeBoardGateway()
	s := newTestServer(t, board)
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

	if _, ok := s.tasks["c1"]; ok {
		t.Error("task should be destroyed even on abort hook failure")
	}
	if s.totalCount != 0 {
		t.Errorf("totalCount=%d, want 0", s.totalCount)
	}

	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.labelAdds) != 1 {
		t.Errorf("attention should be added on abort hook failure, labelAdds=%v", board.labelAdds)
	}
	var hookFailComment bool
	for _, c := range board.comments {
		if strings.Contains(c, "Hook session_abort failed") {
			hookFailComment = true
		}
	}
	if !hookFailComment {
		t.Errorf("hook failure comment not found in %v", board.comments)
	}
}

func stringSliceContains(values []string, want string) bool {
	for _, v := range values {
		if v == want {
			return true
		}
	}
	return false
}
