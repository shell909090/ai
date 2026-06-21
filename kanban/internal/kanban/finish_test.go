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

func TestExtractFinish(t *testing.T) {
	cases := []struct {
		name string
		in   map[string]any
		want string
	}{
		{"nil", nil, ""},
		{"empty", map[string]any{}, ""},
		{"no info", map[string]any{"role": "assistant"}, ""},
		{"info no finish", map[string]any{"info": map[string]any{"role": "assistant"}}, ""},
		{"finish stop", map[string]any{"info": map[string]any{"role": "assistant", "finish": "stop"}}, "stop"},
		{"finish tool-calls", map[string]any{"info": map[string]any{"role": "assistant", "finish": "tool-calls"}}, "tool-calls"},
		{"finish length", map[string]any{"info": map[string]any{"role": "assistant", "finish": "length"}}, "length"},
		{"finish error", map[string]any{"info": map[string]any{"role": "assistant", "finish": "error"}}, "error"},
		{"finish non-string", map[string]any{"info": map[string]any{"finish": 42}}, ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := ExtractFinish(c.in); got != c.want {
				t.Errorf("ExtractFinish(%v) = %q, want %q", c.in, got, c.want)
			}
		})
	}
}

func TestIsAbnormalFinish(t *testing.T) {
	// Per opencode's FinishReason schema, the field is one of
	// "stop", "length", "tool-calls", "content-filter", "error",
	// "unknown". Only "stop" is a clean completion; everything
	// else is abnormal and must escalate to needs-attention.
	cases := []struct {
		finish string
		want   bool
	}{
		{"", false},
		{"stop", false},
		{"length", true},
		{"tool-calls", true},
		{"content-filter", true},
		{"error", true},
		{"unknown", true},
	}
	for _, c := range cases {
		if got := IsAbnormalFinish(c.finish); got != c.want {
			t.Errorf("IsAbnormalFinish(%q) = %v, want %v", c.finish, got, c.want)
		}
	}
}

func TestExtractSummaryText(t *testing.T) {
	shortText := "我修了 bug。"
	// 150 Chinese characters to clearly exceed the 140-rune limit.
	longText := strings.Repeat("修", 150)
	// 140 Chinese characters exactly — at the boundary, no truncation.
	exactText := strings.Repeat("改", 140)

	cases := []struct {
		name      string
		in        map[string]any
		charLimit int
		want      string
	}{
		{"nil map", nil, 140, summaryFallbackEmpty},
		{"empty parts", map[string]any{"parts": []any{}}, 140, summaryFallbackEmpty},
		{"no parts field", map[string]any{"info": map[string]any{}}, 140, summaryFallbackEmpty},
		{"single text", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": shortText}},
		}, 140, shortText},
		{"multiple text concat", map[string]any{
			"parts": []any{
				map[string]any{"type": "text", "text": "第一段。"},
				map[string]any{"type": "step-start"},
				map[string]any{"type": "text", "text": "第二段。"},
			},
		}, 140, "第一段。第二段。"},
		{"whitespace trimmed", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": "  \n  " + shortText + "\n\t  "}},
		}, 140, shortText},
		{"long text truncated with ellipsis", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": longText}},
		}, 140, string([]rune(longText)[:140]) + "…"},
		{"exact 140 runes unchanged", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": exactText}},
		}, 140, exactText},
		{"rune boundary", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": "abcde"}},
		}, 3, "abc…"},
		{"charLimit zero uses default", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": longText}},
		}, 0, string([]rune(longText)[:summaryCharLimit]) + "…"},
		{"charLimit negative uses default", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": longText}},
		}, -1, string([]rune(longText)[:summaryCharLimit]) + "…"},
		{"only non-text parts", map[string]any{
			"parts": []any{
				map[string]any{"type": "step-start"},
				map[string]any{"type": "tool-call", "id": "x"},
			},
		}, 140, summaryFallbackEmpty},
		{"empty text part", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": ""}},
		}, 140, summaryFallbackEmpty},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := ExtractSummaryText(c.in, c.charLimit); got != c.want {
				t.Errorf("ExtractSummaryText(_, %d) = %q, want %q", c.charLimit, got, c.want)
			}
		})
	}
}

func TestMarkCardFinishedWritesSummaryFirst(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"

	s.MarkCardFinished(context.Background(), "c1", "ses1", "stop", "简短总结")

	if got := len(trello.comments); got != 2 {
		t.Fatalf("comments=%d, want 2 (Summary + ✅)", got)
	}
	if !strings.HasPrefix(trello.comments[0], "📝 Summary: ") {
		t.Errorf("first comment=%q, want 📝 Summary: prefix", trello.comments[0])
	}
	if !strings.Contains(trello.comments[0], "简短总结") {
		t.Errorf("first comment should contain summary text, got %q", trello.comments[0])
	}
	if !strings.Contains(trello.comments[1], "✅ Completed session [ses1]") {
		t.Errorf("second comment=%q, want ✅", trello.comments[1])
	}
}

func TestMarkCardFinishedStatusSummarizingIsValidEntry(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusSummarizing}
	s.sessionCards["ses1"] = "c1"

	s.MarkCardFinished(context.Background(), "c1", "ses1", "stop", "回来的总结")

	if got := len(trello.comments); got != 2 {
		t.Fatalf("comments=%d, want 2", got)
	}
	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("card should be removed after MarkCardFinished from statusSummarizing")
	}
}

// newTestServerWithFake wires a Server against the given fake Trello
// and (optional) opencode stand-ins. The workdir is /tmp so the
// constructor accepts it.
func newTestServerWithFake(t *testing.T, trelloURL, ocURL string) (*Server, *fakeTrello) {
	t.Helper()
	httpc := &http.Client{Timeout: 2 * time.Second, Transport: &rewriteTransport{base: http.DefaultTransport, target: trelloURL}}
	s, err := New(Config{
		TrelloKey:       "k",
		TrelloToken:     "t",
		OpenCodeUser:    "u",
		OpenCodePass:    "p",
		OpenCodeBaseURL: ocURL,
		WorkDir:         "/tmp",
		HTTPTimeout:     2 * time.Second,
		HTTPListen:      "127.0.0.1:0",
		PollInterval:    time.Second,
		IdleInterval:    time.Second,
	})
	if err != nil {
		t.Fatal(err)
	}
	s.httpc = httpc
	s.labels = map[string]string{"needs-attention": "lbl_needs-attention"}
	return s, nil
}

func TestMarkCardFinishedNormal(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)
	s.MarkCardFinished(context.Background(), "c1", "ses1", "stop", "")

	if got := len(trello.comments); got != 1 {
		t.Fatalf("comments=%d, want 1", got)
	}
	if !strings.Contains(trello.comments[0], "✅ Completed session [ses1]") {
		t.Errorf("comment=%q", trello.comments[0])
	}
	if got := len(trello.labelAdds); got != 0 {
		t.Errorf("labelAdds=%d, want 0", got)
	}
	if got := len(trello.moves); got != 1 || trello.moves[0] != (moveRec{"c1", doneID}) {
		t.Errorf("moves=%v, want [{c1 %s}]", trello.moves, doneID)
	}
	if _, ok := s.cardSessions["c1"]; ok {
		t.Errorf("card still in cardSessions after finish")
	}
	if _, ok := s.sessionCards["ses1"]; ok {
		t.Errorf("session still in sessionCards after finish")
	}
}

func TestMarkCardFinishedToolCalls(t *testing.T) {
	// "tool-calls" is abnormal under the new semantics — the
	// scheduler must escalate to needs-attention because asking a
	// still-running model for a summary is pointless.
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.MarkCardFinished(context.Background(), "c1", "ses1", "tool-calls", "")

	if got := len(trello.comments); got != 2 {
		t.Errorf("tool-calls should write ✅ + ❌, got %d", got)
	}
	if !strings.Contains(trello.comments[1], "❌ Error in session [ses1]") {
		t.Errorf("second comment=%q, want ❌", trello.comments[1])
	}
	if got := len(trello.labelAdds); got != 1 {
		t.Errorf("tool-calls should add needs-attention, got %d", got)
	}
}

func TestMarkCardFinishedError(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.MarkCardFinished(context.Background(), "c1", "ses1", "error", "")

	if got := len(trello.comments); got != 2 {
		t.Fatalf("error finish should write 2 comments, got %d", got)
	}
	if !strings.Contains(trello.comments[0], "✅ Completed") {
		t.Errorf("first comment=%q", trello.comments[0])
	}
	if !strings.Contains(trello.comments[1], "❌ Error in session [ses1]") {
		t.Errorf("second comment=%q", trello.comments[1])
	}
	if !strings.Contains(trello.comments[1], "finish=error") {
		t.Errorf("second comment should include finish=error, got %q", trello.comments[1])
	}
	if got := len(trello.labelAdds); got != 1 || trello.labelAdds[0] != "lbl_needs-attention" {
		t.Errorf("labelAdds=%v, want [lbl_needs-attention]", trello.labelAdds)
	}
}

func TestMarkCardFinishedLength(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.MarkCardFinished(context.Background(), "c1", "ses1", "length", "")

	if got := len(trello.labelAdds); got != 1 {
		t.Errorf("length finish should add needs-attention, got %d", got)
	}
}

func TestMarkCardFinishedIdempotent(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusCompleted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)
	s.MarkCardFinished(context.Background(), "c1", "ses1", "stop", "")

	if got := len(trello.comments); got != 0 {
		t.Errorf("second call should be no-op, got %d comments", got)
	}
	if got := len(trello.moves); got != 0 {
		t.Errorf("second call should be no-op, got %d moves", got)
	}
	if !strings.Contains(log.String(), "finish.skip") {
		t.Errorf("expected finish.skip log, got %s", log.String())
	}
}

func TestMarkCardFinishedUnknownCard(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	log := &drainLog{}
	withLogWriter(t, log)
	s.MarkCardFinished(context.Background(), "missing", "sesX", "stop", "")

	if got := len(trello.comments); got != 0 {
		t.Errorf("unknown card should be no-op, got %d comments", got)
	}
	if !strings.Contains(log.String(), "finish.skip") {
		t.Errorf("expected finish.skip log, got %s", log.String())
	}
}

func TestMarkCardFinishedAbnormalNoLabel(t *testing.T) {
	trello := newFakeTrello()
	srv := httptest.NewServer(trello.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, srv.URL, "http://opencode.invalid")
	delete(s.labels, "needs-attention")
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)
	s.MarkCardFinished(context.Background(), "c1", "ses1", "error", "")

	if got := len(trello.comments); got != 2 {
		t.Errorf("error finish should still write 2 comments, got %d", got)
	}
	if !strings.Contains(log.String(), "finish.label.missing") {
		t.Errorf("expected finish.label.missing log, got %s", log.String())
	}
}

func TestCheckOneSessionSkipsWhenNoFinish(t *testing.T) {
	oc := &fakeOpencode{}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	s.checkOneSession(context.Background(), "ses1")
	if _, ok := s.cardSessions["c1"]; !ok {
		t.Error("card should still be in cardSessions (no finish yet)")
	}
}

func TestCheckOneSessionRequestsSummaryOnFirstFinish(t *testing.T) {
	oc := &fakeOpencode{message: map[string]any{
		"info": map[string]any{"role": "assistant", "finish": "stop"},
	}}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)

	s.checkOneSession(context.Background(), "ses1")

	info, ok := s.cardSessions["c1"]
	if !ok {
		t.Fatal("card should stay in cardSessions while waiting for summary")
	}
	if info.status != statusSummarizing {
		t.Errorf("status=%q, want %q", info.status, statusSummarizing)
	}
	if info.summaryStartedAt.IsZero() {
		t.Error("summaryStartedAt should be set after requestSummary")
	}
	if got := len(trello.moves); got != 0 {
		t.Errorf("no move should happen on first finish, got %d", got)
	}
	if !strings.Contains(log.String(), "finish.summary.requested") {
		t.Errorf("expected finish.summary.requested log, got %s", log.String())
	}
}

func TestCheckOneSessionMarkDoneOnSummaryReturn(t *testing.T) {
	summary := "我修了一个 bug，加了测试，重命名了函数。"
	oc := &fakeOpencode{
		sessionID: "ses1",
		messagesQueue: []map[string]any{
			// First poll: model finishes its real work.
			{"info": map[string]any{"role": "assistant", "finish": "stop"}},
			// Second poll: model returns the summary.
			{
				"info": map[string]any{"role": "assistant", "finish": "stop"},
				"parts": []map[string]any{
					{"type": "text", "text": summary},
				},
			},
		},
	}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"

	// First poll: should switch to statusSummarizing.
	s.checkOneSession(context.Background(), "ses1")
	if got := s.cardSessions["c1"].status; got != statusSummarizing {
		t.Fatalf("after first poll status=%q, want %q", got, statusSummarizing)
	}

	// Second poll: should write the summary + done and move.
	s.checkOneSession(context.Background(), "ses1")

	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("card should be removed from cardSessions after done")
	}
	if got := len(trello.comments); got != 2 {
		t.Fatalf("comments=%d, want 2 (📝 Summary + ✅)", got)
	}
	if !strings.HasPrefix(trello.comments[0], "📝 Summary: ") {
		t.Errorf("first comment=%q, want 📝 Summary: prefix", trello.comments[0])
	}
	if !strings.Contains(trello.comments[0], summary) {
		t.Errorf("first comment should contain the summary text, got %q", trello.comments[0])
	}
	if !strings.Contains(trello.comments[1], "✅ Completed session [ses1]") {
		t.Errorf("second comment=%q, want ✅ Completed", trello.comments[1])
	}
	if got := len(trello.moves); got != 1 || trello.moves[0].listID != doneID {
		t.Errorf("moves=%v, want one move to %s", trello.moves, doneID)
	}
}

func TestCheckOneSessionSummaryTimeout(t *testing.T) {
	oc := &fakeOpencode{
		sessionID: "ses1",
		messagesQueue: []map[string]any{
			// First poll: model finishes its real work.
			{"info": map[string]any{"role": "assistant", "finish": "stop"}},
			// Second poll: model returns the summary (after timeout).
			{
				"info":  map[string]any{"role": "assistant", "finish": "stop"},
				"parts": []map[string]any{{"type": "text", "text": "晚了"}},
			},
		},
	}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)

	// First poll: should switch to statusSummarizing.
	s.checkOneSession(context.Background(), "ses1")
	// Pretend the summary prompt was sent long ago.
	s.mu.Lock()
	s.cardSessions["c1"].summaryStartedAt = time.Now().Add(-2 * summaryTimeout)
	s.mu.Unlock()

	s.checkOneSession(context.Background(), "ses1")

	if !strings.Contains(log.String(), "finish.summary.timeout") {
		t.Errorf("expected finish.summary.timeout log, got %s", log.String())
	}
	if got := len(trello.comments); got != 1 {
		t.Fatalf("comments=%d, want 1 (✅ only, no Summary on timeout)", got)
	}
	if !strings.Contains(trello.comments[0], "✅ Completed") {
		t.Errorf("comment=%q, want ✅", trello.comments[0])
	}
	if got := len(trello.moves); got != 1 || trello.moves[0].listID != doneID {
		t.Errorf("moves=%v, want one move to %s", trello.moves, doneID)
	}
}

func TestCheckOneSessionAbnormalFirstFinishSkipsSummary(t *testing.T) {
	// Any non-stop first finish must skip the summary round and
	// escalate to needs-attention directly. The opencode /prompt_async
	// endpoint must NOT be called.
	abnormalFinishes := []string{"length", "tool-calls", "content-filter", "error", "unknown"}
	for _, finish := range abnormalFinishes {
		t.Run(finish, func(t *testing.T) {
			trello := newFakeTrello()
			trURL := httptest.NewServer(trello.handler())
			defer trURL.Close()
			oc := &fakeOpencode{
				sessionID: "ses1",
				message: map[string]any{
					"info": map[string]any{"role": "assistant", "finish": finish},
				},
			}
			// The fake's prompt_async handler returns 204 — the
			// scheduler should never reach it for abnormal finishes.
			// We wrap it so any call fails the test loudly.
			origHandler := oc.handler()
			ocURL := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
				if strings.HasSuffix(r.URL.Path, "/prompt_async") {
					t.Errorf("prompt_async called for finish=%q; summary must be skipped", finish)
					w.WriteHeader(http.StatusInternalServerError)
					return
				}
				origHandler.ServeHTTP(w, r)
			}))
			defer ocURL.Close()
			s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
			s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
			s.sessionCards["ses1"] = "c1"

			s.checkOneSession(context.Background(), "ses1")

			if _, ok := s.cardSessions["c1"]; ok {
				t.Errorf("card should be removed after abnormal finish")
			}
			if got := len(trello.labelAdds); got != 1 || trello.labelAdds[0] != "lbl_needs-attention" {
				t.Errorf("labelAdds=%v, want [lbl_needs-attention]", trello.labelAdds)
			}
			if got := len(trello.moves); got != 1 || trello.moves[0].listID != doneID {
				t.Errorf("moves=%v, want one move to %s", trello.moves, doneID)
			}
			// Comments: ✅ + ❌ (no Summary comment)
			if got := len(trello.comments); got != 2 {
				t.Fatalf("comments=%d, want 2 (✅ + ❌, no Summary)", got)
			}
			if !strings.Contains(trello.comments[0], "✅ Completed session [ses1]") {
				t.Errorf("first comment=%q, want ✅", trello.comments[0])
			}
			if !strings.Contains(trello.comments[1], "❌ Error in session [ses1]") {
				t.Errorf("second comment=%q, want ❌", trello.comments[1])
			}
			if !strings.Contains(trello.comments[1], "finish="+finish) {
				t.Errorf("❌ comment should mention finish=%s, got %q", finish, trello.comments[1])
			}
		})
	}
}

func TestCheckOneSessionNormalFirstFinishAbnormalSummary(t *testing.T) {
	// First finish is "stop" (work done cleanly). Summary's
	// response is "error". The summary failure is informational
	// only — no needs-attention escalation.
	oc := &fakeOpencode{
		sessionID: "ses1",
		messagesQueue: []map[string]any{
			{"info": map[string]any{"role": "assistant", "finish": "stop"}},
			{
				"info":  map[string]any{"role": "assistant", "finish": "error"},
				"parts": []map[string]any{{"type": "text", "text": "略"}},
			},
		},
	}
	ocURL := httptest.NewServer(oc.handler())
	defer ocURL.Close()
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	s, _ := newTestServerWithFake(t, trURL.URL, ocURL.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"

	s.checkOneSession(context.Background(), "ses1")
	s.checkOneSession(context.Background(), "ses1")

	if got := len(trello.labelAdds); got != 0 {
		t.Errorf("labelAdds=%v, want [] (summary abnormal alone must not escalate)", trello.labelAdds)
	}
	// Should have 📝 Summary (with the abnormal-fallback text) + ✅
	if got := len(trello.comments); got != 2 {
		t.Fatalf("comments=%d, want 2 (Summary + ✅)", got)
	}
	if !strings.Contains(trello.comments[0], "（总结生成失败: finish=error）") {
		t.Errorf("summary comment=%q, want fallback", trello.comments[0])
	}
}

func TestRequestSummarySendFailFallsThrough(t *testing.T) {
	// Opencode server returns 500 on /prompt_async.
	ocSrv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if strings.HasSuffix(r.URL.Path, "/prompt_async") {
			w.WriteHeader(http.StatusInternalServerError)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	}))
	defer ocSrv.Close()
	trello := newFakeTrello()
	trURL := httptest.NewServer(trello.handler())
	defer trURL.Close()
	s, _ := newTestServerWithFake(t, trURL.URL, ocSrv.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)

	s.requestSummary(context.Background(), "c1", "ses1", "stop")

	if !strings.Contains(log.String(), "finish.summary.skip") {
		t.Errorf("expected finish.summary.skip log, got %s", log.String())
	}
	if _, ok := s.cardSessions["c1"]; ok {
		t.Error("card should be removed from cardSessions after direct done")
	}
	if got := len(trello.comments); got != 1 {
		t.Fatalf("comments=%d, want 1 (✅ only)", got)
	}
	if !strings.Contains(trello.comments[0], "✅ Completed") {
		t.Errorf("comment=%q, want ✅", trello.comments[0])
	}
	if got := len(trello.moves); got != 1 || trello.moves[0].listID != doneID {
		t.Errorf("moves=%v, want one move to %s", trello.moves, doneID)
	}
}

func TestCheckOneSessionServerError(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
	}))
	defer srv.Close()
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
	s.cardSessions["c1"] = &sessionInfo{cardID: "c1", sessionID: "ses1", status: statusStarted}
	s.sessionCards["ses1"] = "c1"
	log := &drainLog{}
	withLogWriter(t, log)
	s.checkOneSession(context.Background(), "ses1")
	if !strings.Contains(log.String(), "finish.message.fail") {
		t.Errorf("expected finish.message.fail log, got %s", log.String())
	}
	if _, ok := s.cardSessions["c1"]; !ok {
		t.Error("card should remain in cardSessions on error")
	}
}

func TestCheckOneSessionUnknownSession(t *testing.T) {
	oc := &fakeOpencode{}
	srv := httptest.NewServer(oc.handler())
	defer srv.Close()
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", srv.URL)
	s.checkOneSession(context.Background(), "ses_orphan")
}

func TestRunFinishWatcherStopsOnCancel(t *testing.T) {
	s, _ := newTestServerWithFake(t, "http://api.trello.invalid", "http://opencode.invalid")
	s.cfg.IdleInterval = 20 * time.Millisecond
	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{})
	go func() {
		s.runFinishWatcher(ctx)
		close(done)
	}()
	time.Sleep(50 * time.Millisecond)
	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("runFinishWatcher did not return after cancel")
	}
}

// keep encoding/json referenced from this file for tests.
var _ = json.Marshal
