// Finish watcher: the single source of truth for "session has ended".
//
// Every IdleInterval (default 10s) the watcher iterates registered
// sessions, calls GET /session/{id}/message?limit=1, and inspects the
// last message's info.finish. Any non-empty finish value means the model
// has stopped talking for this turn, so the watcher triggers the
// completion flow: ✅ comment + move the card to done; abnormal
// finishes (error / length) additionally write a diagnostic comment
// and add the needs-attention label.
//
// No agent-driven signal, no done URL, no per-card locks, no
// post-done cool-down. See design.md §6.5 and §7.3.
package main

import (
	"context"
	"fmt"
	"io"
	"time"
)

// extractFinish returns the info.finish value from the last opencode
// message, or "" if the field is absent. The field is omitted while
// the model is still streaming or before the first assistant message
// has been produced; it is set once the assistant message has been
// finalized — regardless of the finish reason (stop / tool-calls /
// length / error). Any non-empty return value means the model has
// finished speaking for this turn.
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

// isAbnormalFinish reports whether the finish value indicates the agent
// session ended in a state that needs human attention: the model errored
// (`error`) or hit the context-length limit (`length`). The caller
// should additionally mark needs-attention and write a diagnostic
// comment in that case.
func isAbnormalFinish(finish string) bool {
	return finish == "error" || finish == "length"
}

// runFinishWatcher ticks on IdleInterval and checks every registered
// session for model finish. Returns when ctx is cancelled.
func (s *server) runFinishWatcher(ctx context.Context, w io.Writer) {
	t := time.NewTicker(s.cfg.IdleInterval)
	defer t.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-t.C:
			s.checkAllSessions(ctx, w)
		}
	}
}

func (s *server) checkAllSessions(ctx context.Context, w io.Writer) {
	s.mu.Lock()
	sessionIDs := make([]string, 0, len(s.sessionCards))
	for sid := range s.sessionCards {
		sessionIDs = append(sessionIDs, sid)
	}
	s.mu.Unlock()
	for _, sid := range sessionIDs {
		s.checkOneSession(ctx, w, sid)
	}
}

// checkOneSession inspects a single session's last message and triggers
// markCardFinished when the model has produced a final assistant
// message. No per-card lock is required: this is the only path that
// transitions a card out of the started state, so there is nothing to
// race against.
func (s *server) checkOneSession(ctx context.Context, w io.Writer, sessionID string) {
	last, err := s.ocGetLastMessage(ctx, sessionID)
	if err != nil {
		s.log(w, "finish.message.fail", fmt.Sprintf("session=%s err=%v", sessionID, err))
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
	if info == nil || info.status != statusStarted {
		s.mu.Unlock()
		return
	}
	s.mu.Unlock()

	s.log(w, "finish.detected", fmt.Sprintf("card=%s session=%s finish=%s", cardID, sessionID, finish))
	s.markCardFinished(ctx, w, cardID, sessionID, finish)
}

// markCardFinished runs the completion flow for a card whose session
// has produced a final assistant message. It updates in-memory state,
// writes a ✅ comment, optionally writes a ❌ error comment and adds
// the needs-attention label on abnormal finish, then moves the card to
// done.
//
// Idempotent: if the card is not in started status the call is a no-op
// (logged as finish.skip).
//
// Note: the verify three-checks gate (build / lint / unittest) lives in
// T005 and is not yet wired in. When T005 lands, run it between the
// comment step and the move step; on failure under the retry limit
// send a fix prompt and leave the card in doing; over the limit move
// it back to todo.
func (s *server) markCardFinished(ctx context.Context, w io.Writer, cardID, sessionID, finish string) {
	s.mu.Lock()
	info, ok := s.cardSessions[cardID]
	if !ok || info == nil || info.status != statusStarted {
		s.mu.Unlock()
		s.log(w, "finish.skip", fmt.Sprintf("card=%s session=%s reason=not-started", cardID, sessionID))
		return
	}
	info.status = statusCompleted
	s.mu.Unlock()

	comment := fmt.Sprintf("✅ Completed session %s", sessionID)
	if err := s.trelloAddComment(ctx, cardID, comment); err != nil {
		s.log(w, "finish.comment.fail", fmt.Sprintf("card=%s err=%v", cardID, err))
	}

	if isAbnormalFinish(finish) {
		errMsg := fmt.Sprintf(
			"❌ Error in session %s (finish=%s). 用 opencode attach %s --session %s 查看。",
			sessionID, finish, s.cfg.OpenCodeBaseURL, sessionID)
		if err := s.trelloAddComment(ctx, cardID, errMsg); err != nil {
			s.log(w, "finish.errcomment.fail", fmt.Sprintf("card=%s err=%v", cardID, err))
		}
		if labelID, hasLabel := s.labels["needs-attention"]; hasLabel {
			if err := s.trelloAddLabel(ctx, cardID, labelID); err != nil {
				s.log(w, "finish.label.fail", fmt.Sprintf("card=%s err=%v", cardID, err))
			}
		} else {
			s.log(w, "finish.label.missing", fmt.Sprintf("card=%s label=needs-attention", cardID))
		}
	}

	if err := s.trelloMoveCard(ctx, cardID, doneID); err != nil {
		s.log(w, "finish.move.fail", fmt.Sprintf("card=%s err=%v", cardID, err))
	}

	s.mu.Lock()
	delete(s.cardSessions, cardID)
	delete(s.sessionCards, sessionID)
	s.mu.Unlock()

	s.log(w, "finish.done", fmt.Sprintf("card=%s session=%s finish=%s", cardID, sessionID, finish))
}
