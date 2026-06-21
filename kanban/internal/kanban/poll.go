package kanban

import (
	"context"
	"fmt"
	"strings"
	"time"
)

// defaultProject is the project name used when a card has no proj:*
// label. Cards with this name share the same per-project slot.
const defaultProject = "default"

// projectOf returns the project name from a card's labels. The first
// label matching "proj:NAME" wins; absent any such label, the
// defaultProject is returned. Multiple proj:* labels are not
// validated here — the first one is taken, and a warning is logged.
func projectOf(card trelloCard) string {
	for _, l := range card.Labels {
		if strings.HasPrefix(l.Name, "proj:") {
			return strings.TrimPrefix(l.Name, "proj:")
		}
	}
	return defaultProject
}

// countByProject returns the total number of cards in cardSessions and
// a per-project breakdown. Both are derived from the in-memory state,
// so a single O(N) sweep of cardSessions is enough — no extra Trello
// call. Caller is responsible for holding s.mu if it needs a
// consistent snapshot.
func (s *Server) countByProject() (total int, perProject map[string]int) {
	perProject = make(map[string]int)
	for _, info := range s.cardSessions {
		total++
		perProject[info.project]++
	}
	return total, perProject
}

// pollOnce runs one scheduler iteration:
//  1. List doing; detect drag-outs (cards we know about but Trello
//     no longer shows in doing). For each, abort the opencode session
//     and move the card to icebox.
//  2. Detect new cards in doing (human moved, or auto-promoted by
//     this very poll in step 3 last cycle). Add to cardSessions and
//     start processCard.
//  3. List todo; for each card, check whether promoting it would
//     exceed the global or per-project cap. If not, register in
//     cardSessions and start processCard right away (do not wait for
//     the next poll).
func (s *Server) pollOnce(ctx context.Context) {
	doing, err := s.trelloListCards(ctx, doingID)
	if err != nil {
		s.log("poll.error", err.Error())
		return
	}
	s.log("poll", fmt.Sprintf("doing_cards=%d", len(doing)))

	// Step 1: drag-outs. The set of cardIDs Trello currently shows in
	// doing is the source of truth.
	currentDoing := make(map[string]struct{}, len(doing))
	for _, c := range doing {
		currentDoing[c.ID] = struct{}{}
	}
	s.mu.Lock()
	draggedOut := make([]string, 0)
	for cardID := range s.cardSessions {
		if _, ok := currentDoing[cardID]; !ok {
			draggedOut = append(draggedOut, cardID)
		}
	}
	s.mu.Unlock()
	for _, cardID := range draggedOut {
		s.handleDragOut(ctx, cardID)
	}

	// Step 2: brand-new cards in doing (we just learned about them).
	// processCard takes it from here; nothing else to do.
	var newDoing []trelloCard
	s.mu.Lock()
	for _, c := range doing {
		if _, busy := s.cardSessions[c.ID]; !busy {
			s.cardSessions[c.ID] = &sessionInfo{
				cardID:   c.ID,
				cardName: c.Name,
				project:  projectOf(c),
				status:   statusStarted,
			}
			newDoing = append(newDoing, c)
		}
	}
	s.mu.Unlock()
	for _, c := range newDoing {
		go s.processCard(ctx, c)
	}
	s.log("poll.new_doing", fmt.Sprintf("new_cards=%d", len(newDoing)))

	// Step 3: auto-promote from todo. Counts come from the in-memory
	// cardSessions (so the cost is O(N) on the doing set, no extra
	// Trello round trip).
	todo, err := s.trelloListCards(ctx, todoID)
	if err != nil {
		s.log("poll.todo.error", err.Error())
		return
	}
	s.log("poll.todo", fmt.Sprintf("todo_cards=%d", len(todo)))

	total, perProject := s.countByProject()
	promoted := 0
	for _, c := range todo {
		if total >= s.cfg.MaxDoingTotal {
			break
		}
		project := projectOf(c)
		if perProject[project] >= s.cfg.MaxDoingPerProject {
			continue
		}
		// Register in cardSessions before moving the card so the
		// next poll (or a concurrent one) won't double-process.
		s.mu.Lock()
		if _, busy := s.cardSessions[c.ID]; busy {
			s.mu.Unlock()
			continue
		}
		s.cardSessions[c.ID] = &sessionInfo{
			cardID:   c.ID,
			cardName: c.Name,
			project:  project,
			status:   statusStarted,
		}
		s.mu.Unlock()
		total++
		perProject[project]++
		promoted++

		card := c
		if err := s.trelloMoveCard(ctx, card.ID, doingID); err != nil {
			s.log("promote.move.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
			// Roll back the in-memory entry; the user can re-promote
			// later by re-queueing the card.
			s.mu.Lock()
			delete(s.cardSessions, card.ID)
			s.mu.Unlock()
			total--
			perProject[project]--
			promoted--
			continue
		}
		s.log("promote", fmt.Sprintf("card=%s project=%s", card.ID, project))
		go s.processCard(ctx, card)
	}
	s.log("poll.promoted", fmt.Sprintf("promoted=%d", promoted))
}

// handleDragOut cleans up after a card that was in doing but no
// longer is. It aborts the opencode session (best-effort), removes
// the card from in-memory state, and moves the card to icebox — the
// icebox is the "needs re-review" zone, distinct from todo so the
// auto-promotion feature does not pick it back up.
//
// If the card was waiting for the post-completion summary, the
// summary is abandoned and an audit log line is emitted.
func (s *Server) handleDragOut(ctx context.Context, cardID string) {
	s.mu.Lock()
	info, ok := s.cardSessions[cardID]
	if !ok {
		s.mu.Unlock()
		return
	}
	sessionID := info.sessionID
	wasSummarizing := info.status == statusSummarizing
	delete(s.cardSessions, cardID)
	if sessionID != "" {
		delete(s.sessionCards, sessionID)
	}
	s.mu.Unlock()

	if wasSummarizing {
		s.log("finish.summary.aborted", fmt.Sprintf("card=%s session=%s reason=drag-out", cardID, sessionID))
	}

	if sessionID != "" {
		if err := s.ocAbortSession(ctx, sessionID); err != nil {
			s.log("dragout.abort.fail", fmt.Sprintf("card=%s session=%s err=%v", cardID, sessionID, err))
		}
	}
	if err := s.trelloMoveCard(ctx, cardID, iceboxID); err != nil {
		s.log("dragout.move.fail", fmt.Sprintf("card=%s err=%v", cardID, err))
		return
	}
	s.log("dragout", fmt.Sprintf("card=%s session=%s → icebox", cardID, sessionID))
}

// processCard starts an opencode session for the given card, posts a
// Started comment, and async-sends the card description as the prompt.
// The card must already be in cardSessions (with project set) before
// this is called; the caller in pollOnce owns that bookkeeping.
// On any error the card is removed from cardSessions and the
// sessionCards mapping is rolled back; the next poll will see the
// card still in doing and have nothing to do with it, leaving
// recovery to the user (drag it out to icebox manually).
func (s *Server) processCard(ctx context.Context, card trelloCard) {
	sess, err := s.ocCreateSession(ctx)
	if err != nil {
		s.log("opencode.session.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		s.mu.Lock()
		delete(s.cardSessions, card.ID)
		s.mu.Unlock()
		return
	}
	s.log("opencode.session", fmt.Sprintf("card=%s session=%s", card.ID, sess.ID))

	s.mu.Lock()
	info := s.cardSessions[card.ID]
	info.sessionID = sess.ID
	s.sessionCards[sess.ID] = card.ID
	s.mu.Unlock()

	// Best-effort rename so the opencode web session list aligns
	// with the Trello card title. A failure here does not block the
	// agent from running; we log and continue.
	if err := s.ocRenameSession(ctx, sess.ID, card.Name); err != nil {
		s.log("session.rename.fail", fmt.Sprintf("card=%s session=%s err=%v", card.ID, sess.ID, err))
	} else {
		s.log("session.rename", fmt.Sprintf("card=%s session=%s title=%q", card.ID, sess.ID, card.Name))
	}

	comment := fmt.Sprintf("▶️ Started session %s\nWorkspace: %s",
		formatSessionRef(s.cfg.OpenCodeBaseURL, s.cfg.WorkDir, sess.ID), sess.Directory)
	if err := s.trelloAddComment(ctx, card.ID, comment); err != nil {
		s.log("trello.comment.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
	} else {
		s.log("trello.comment", fmt.Sprintf("card=%s session=%s", card.ID, sess.ID))
	}

	if err := s.ocSendPromptAsync(ctx, sess.ID, card.Desc); err != nil {
		s.log("opencode.prompt.fail", fmt.Sprintf("card=%s session=%s err=%v", card.ID, sess.ID, err))
		s.mu.Lock()
		delete(s.cardSessions, card.ID)
		delete(s.sessionCards, sess.ID)
		s.mu.Unlock()
		return
	}
	s.log("opencode.prompt", fmt.Sprintf("card=%s session=%s body_len=%d", card.ID, sess.ID, len(card.Desc)))

	s.mu.Lock()
	info.startedAt = time.Now()
	s.mu.Unlock()
	s.log("card.started", fmt.Sprintf("id=%s session=%s", card.ID, sess.ID))
}
