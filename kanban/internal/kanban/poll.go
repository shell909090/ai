package kanban

import (
	"context"
	"fmt"
	"time"
)

// pollOnce reads the doing list and starts a session for every card
// that is not already in cardSessions. Each new card is processed in
// its own goroutine.
func (s *Server) pollOnce(ctx context.Context) {
	cards, err := s.trelloListCards(ctx, doingID)
	if err != nil {
		s.log("poll.error", err.Error())
		return
	}
	s.log("poll", fmt.Sprintf("doing_cards=%d", len(cards)))

	var newCards []trelloCard
	s.mu.Lock()
	for _, c := range cards {
		if _, busy := s.cardSessions[c.ID]; !busy {
			s.cardSessions[c.ID] = &sessionInfo{cardID: c.ID, cardName: c.Name, status: statusStarted}
			newCards = append(newCards, c)
		}
	}
	s.mu.Unlock()
	s.log("poll.new", fmt.Sprintf("new_cards=%d", len(newCards)))

	for _, c := range newCards {
		go s.processCard(ctx, c)
	}
}

// processCard starts an opencode session for the given card, posts a
// Started comment, and async-sends the card description as the prompt.
// On any error the card is removed from cardSessions and the
// sessionCards mapping is rolled back; the user can re-queue by moving
// the card back to doing.
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

	comment := fmt.Sprintf("▶️ Started session %s\nWorkspace: %s", sess.ID, sess.Directory)
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
