// Finish watcher: the single source of truth for "session has ended".
//
// Every IdleInterval (default 10s) the watcher iterates registered
// sessions, calls GET /session/{id}/message?limit=1, and inspects the
// last message's info.finish. Any non-empty finish value means the model
// has stopped talking for this turn, so the watcher either asks the
// same session for a 140-character summary (first finish) or, once
// that summary is back, runs the completion flow: 📝 Summary comment
// + ✅ comment + move the card to done. Abnormal finishes (error /
// length) additionally write a diagnostic comment and add the
// needs-attention label.
//
// No agent-driven signal, no done URL, no per-card locks, no
// post-done cool-down. See design.md §6.5, §7.3, and §7.7.
package kanban

import (
	"context"
	"fmt"
	"strings"
	"time"
)

// Default limits for the post-completion summary prompt. Centralised
// here so the tests and the production code share the same constants.
const (
	summaryCharLimit = 140
	summaryTimeout   = 60 * time.Second
)

// summaryPromptText is sent verbatim to the opencode session as the
// follow-up after the model has emitted its first final assistant
// message. The wording emphasises the *result* of the run, not the
// task description (which is already in the card description). See
// docs/req.md §5.4.4 and docs/design.md §7.7 for the rationale.
const summaryPromptText = `请用 140 个字以内简要总结本次运行的*结果*，不是任务说明。聚焦：
- 实际做了哪些操作（执行了哪些命令、修改/创建/查看了哪些文件）
- 关键产出（新增/修改/删除的文件、跑通的测试、产生的数据、得到的结论）
- 任何值得人类关注的副产品（意外发现、未完成项、需要 follow-up 的事）

仅输出总结本身，不要任何前缀、解释、Markdown 标记。`

// summaryFallbackEmpty is the comment body used when the model
// produced no readable text for the summary (e.g. the parts list
// contained only tool calls).
const summaryFallbackEmpty = "（本次会话未产生可读总结）"

// ExtractFinish returns the info.finish value from the last opencode
// message, or "" if the field is absent. The field is omitted while
// the model is still streaming or before the first assistant message
// has been produced; it is set once the assistant message has been
// finalized — regardless of the finish reason (stop / tool-calls /
// length / error). Any non-empty return value means the model has
// finished speaking for this turn.
//
// Exposed (capitalised) so external callers and tests can use it.
func ExtractFinish(last map[string]any) string {
	return extractFinish(last)
}

func extractFinish(last map[string]any) string {
	if last == nil {
		return ""
	}
	info, _ := last["info"].(map[string]any)
	v, ok := info["finish"]
	if !ok {
		return ""
	}
	s, _ := v.(string)
	return s
}

// IsAbnormalFinish reports whether the finish value indicates the agent
// session ended in a state that needs human attention. Only "stop" is
// a clean completion; every other value emitted by opencode
// (length / tool-calls / content-filter / error / unknown) means
// something went wrong or the model is still going to act. The caller
// should add the needs-attention label and write a diagnostic comment
// in those cases.
//
// The empty string means "no finish value seen yet" — the model is
// still streaming — and is treated as not-abnormal so the function
// stays a clean predicate over real finish values. (The scheduler
// never reaches this with an empty string in practice: the watcher
// short-circuits on `finish == ""` before entering the completion
// branches.)
//
// The set of values is sourced from opencode's FinishReason schema
// (packages/llm/src/schema/ids.ts). "tool-calls" and "unknown" are
// not strictly "broken" — the model is still running — but treating
// them as abnormal is consistent with opencode's own "is finished?"
// check (packages/opencode/src/session/prompt.ts:1341) and means the
// scheduler never asks a still-running model for a summary.
func IsAbnormalFinish(finish string) bool {
	return isAbnormalFinish(finish)
}

func isAbnormalFinish(finish string) bool {
	return finish != "" && finish != "stop"
}

// ExtractSummaryText returns the post-completion summary text from the
// last opencode message, truncated to charLimit runes. The function
// walks the message parts, concatenates every part with type "text",
// trims whitespace, and truncates. If charLimit is <= 0 the default
// summaryCharLimit is used. If no text is found, a fixed fallback
// string is returned. The function is pure: no I/O, no clock, no
// global state — easy to unit-test.
//
// Exposed (capitalised) so external callers and tests can use it.
func ExtractSummaryText(last map[string]any, charLimit int) string {
	if charLimit <= 0 {
		charLimit = summaryCharLimit
	}
	if last == nil {
		return summaryFallbackEmpty
	}
	parts, _ := last["parts"].([]any)
	var sb strings.Builder
	for _, p := range parts {
		pm, ok := p.(map[string]any)
		if !ok {
			continue
		}
		if t, _ := pm["type"].(string); t != "text" {
			continue
		}
		if txt, ok := pm["text"].(string); ok {
			sb.WriteString(txt)
		}
	}
	trimmed := strings.TrimSpace(sb.String())
	if trimmed == "" {
		return summaryFallbackEmpty
	}
	runes := []rune(trimmed)
	if len(runes) > charLimit {
		return string(runes[:charLimit]) + "…"
	}
	return trimmed
}

// runFinishWatcher ticks on IdleInterval and checks every registered
// session for model finish. Returns when ctx is cancelled.
func (s *Server) runFinishWatcher(ctx context.Context) {
	t := time.NewTicker(s.cfg.IdleInterval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			s.checkAllSessions(ctx)
		}
	}
}

func (s *Server) checkAllSessions(ctx context.Context) {
	s.mu.Lock()
	sessionIDs := make([]string, 0, len(s.sessionCards))
	for sid := range s.sessionCards {
		sessionIDs = append(sessionIDs, sid)
	}
	s.mu.Unlock()
	for _, sid := range sessionIDs {
		s.checkOneSession(ctx, sid)
	}
}

// checkOneSession inspects a single session's last message and drives
// either the summary request (first finish) or MarkCardFinished (after
// the summary comes back). No per-card lock is required: this is the
// only path that transitions a card out of the started state, so
// there is nothing to race against.
func (s *Server) checkOneSession(ctx context.Context, sessionID string) {
	last, err := s.ocGetLastMessage(ctx, sessionID)
	if err != nil {
		s.log("finish.message.fail", fmt.Sprintf("session=%s err=%v", sessionID, err))
		return
	}
	finish := extractFinish(last)
	if finish == "" {
		return
	}

	s.mu.Lock()
	cardID, ok := s.sessionCards[sessionID]
	if !ok {
		s.mu.Unlock()
		return
	}
	info := s.cardSessions[cardID]
	if info == nil {
		s.mu.Unlock()
		return
	}

	switch info.status {
	case statusStarted:
		s.mu.Unlock()
		s.log("finish.detected", fmt.Sprintf("card=%s session=%s finish=%s", cardID, sessionID, finish))
		if finish == "stop" {
			s.requestSummary(ctx, cardID, sessionID, finish)
		} else {
			// Any non-stop finish: skip the summary round-trip.
			// tool-calls / unknown mean the model is still going
			// to act (asking it for a summary is pointless);
			// length / content-filter / error mean this turn is
			// already broken. Either way, mark done with
			// needs-attention and let a human investigate.
			s.log("finish.abnormal.skip_summary", fmt.Sprintf("card=%s session=%s finish=%s", cardID, sessionID, finish))
			s.MarkCardFinished(ctx, cardID, sessionID, finish, "")
		}
	case statusSummarizing:
		timedOut := time.Since(info.summaryStartedAt) > summaryTimeout
		// lastFinish was captured when the summary prompt was
		// sent. The work's abnormal-state decision must use the
		// original finish, not the summary response's finish.
		firstFinish := info.lastFinish
		s.mu.Unlock()
		if timedOut {
			s.log("finish.summary.timeout", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
			s.MarkCardFinished(ctx, cardID, sessionID, firstFinish, "")
			return
		}
		summary := ExtractSummaryText(last, summaryCharLimit)
		if isAbnormalFinish(finish) {
			summary = fmt.Sprintf("（总结生成失败: finish=%s）", finish)
		}
		s.MarkCardFinished(ctx, cardID, sessionID, firstFinish, summary)
	default:
		s.mu.Unlock()
	}
}

// requestSummary sends the post-completion summary prompt to the
// given session and, on success, transitions the card into
// statusSummarizing. If the send fails, it falls through to
// MarkCardFinished with an empty summary so the card is still moved
// to done — the summary is a soft signal, not a hard gate.
func (s *Server) requestSummary(ctx context.Context, cardID, sessionID, finish string) {
	if err := s.ocSendPromptAsync(ctx, sessionID, summaryPromptText); err != nil {
		s.log("finish.summary.skip", fmt.Sprintf("card=%s session=%s reason=send-fail err=%v", cardID, sessionID, err))
		s.MarkCardFinished(ctx, cardID, sessionID, finish, "")
		return
	}
	s.mu.Lock()
	info, ok := s.cardSessions[cardID]
	if !ok {
		s.mu.Unlock()
		return
	}
	info.status = statusSummarizing
	info.summaryStartedAt = time.Now()
	info.lastFinish = finish
	s.mu.Unlock()
	s.log("finish.summary.requested", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
}

// MarkCardFinished runs the completion flow for a card whose session
// has produced a final assistant message (and, when statusSummarizing,
// returned a summary). It updates in-memory state, writes a 📝
// Summary comment when summary is non-empty, writes a ✅ comment,
// optionally writes a ❌ error comment and adds the needs-attention
// label on abnormal finish, then moves the card to done.
//
// Idempotent: if the card is in a terminal state the call is a no-op
// (logged as finish.skip). Both statusStarted (first finish) and
// statusSummarizing (after the summary is back) are valid entry
// points; statusCompleted is not.
//
// Note: the verify three-checks gate (build / lint / unittest) lives in
// T005 and is not yet wired in. When T005 lands, run it between the
// comment step and the move step; on failure under the retry limit
// send a fix prompt and leave the card in doing; over the limit move
// it back to todo.
func (s *Server) MarkCardFinished(ctx context.Context, cardID, sessionID, finish, summary string) {
	s.mu.Lock()
	info, ok := s.cardSessions[cardID]
	if !ok || info == nil {
		s.mu.Unlock()
		s.log("finish.skip", fmt.Sprintf("card=%s session=%s reason=unknown", cardID, sessionID))
		return
	}
	if info.status != statusStarted && info.status != statusSummarizing {
		s.mu.Unlock()
		s.log("finish.skip", fmt.Sprintf("card=%s session=%s reason=not-started", cardID, sessionID))
		return
	}
	info.status = statusCompleted
	s.mu.Unlock()

	if summary != "" {
		summaryComment := "📝 Summary: " + summary
		if err := s.trelloAddComment(ctx, cardID, summaryComment); err != nil {
			s.log("finish.summary.comment.fail", fmt.Sprintf("card=%s err=%v", cardID, err))
		}
	}

	comment := fmt.Sprintf("✅ Completed session %s", formatSessionRef(s.cfg.OpenCodeBaseURL, s.cfg.WorkDir, sessionID))
	if err := s.trelloAddComment(ctx, cardID, comment); err != nil {
		s.log("finish.comment.fail", fmt.Sprintf("card=%s err=%v", cardID, err))
	}

	if isAbnormalFinish(finish) {
		errMsg := fmt.Sprintf(
			"❌ Error in session %s (finish=%s). 用 opencode attach %s --session %s 查看。",
			formatSessionRef(s.cfg.OpenCodeBaseURL, s.cfg.WorkDir, sessionID),
			finish, s.cfg.OpenCodeBaseURL, sessionID)
		if err := s.trelloAddComment(ctx, cardID, errMsg); err != nil {
			s.log("finish.errcomment.fail", fmt.Sprintf("card=%s err=%v", cardID, err))
		}
		if labelID, hasLabel := s.labels["needs-attention"]; hasLabel {
			if err := s.trelloAddLabel(ctx, cardID, labelID); err != nil {
				s.log("finish.label.fail", fmt.Sprintf("card=%s err=%v", cardID, err))
			}
		} else {
			s.log("finish.label.missing", fmt.Sprintf("card=%s label=needs-attention", cardID))
		}
	}

	if err := s.trelloMoveCard(ctx, cardID, doneID); err != nil {
		s.log("finish.move.fail", fmt.Sprintf("card=%s err=%v", cardID, err))
	}

	s.mu.Lock()
	delete(s.cardSessions, cardID)
	delete(s.sessionCards, sessionID)
	s.mu.Unlock()

	s.log("finish.done", fmt.Sprintf("card=%s session=%s finish=%s", cardID, sessionID, finish))
}
