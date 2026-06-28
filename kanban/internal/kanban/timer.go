package kanban

import (
	"context"
	"fmt"
	"time"
)

// tick runs one scheduler iteration in the fixed order required by design.md §5:
//  1. check session finish
//  2. reconcile doing
//  3. check timeouts
//  4. promote todo
func (s *Server) tick(ctx context.Context, now time.Time) {
	s.checkSessionFinish(ctx, now)
	s.reconcileDoing(ctx, now)
	s.checkTimeouts(ctx, now)
	s.promoteTodo(ctx, now)
}

// checkSessionFinish polls every tracked session for a finish event.
// Pending tasks (SessionID == "__pending__") are skipped.
func (s *Server) checkSessionFinish(ctx context.Context, now time.Time) {
	s.mu.Lock()
	cardIDs := make([]string, 0, len(s.tasks))
	for id, t := range s.tasks {
		if t.SessionID != "__pending__" {
			cardIDs = append(cardIDs, id)
		}
	}
	s.mu.Unlock()

	for _, cardID := range cardIDs {
		s.checkOneFinish(ctx, cardID, now)
	}
}

// checkOneFinish handles finish detection for a single task.
// Implements the rules from design.md §6.1.
func (s *Server) checkOneFinish(ctx context.Context, cardID string, now time.Time) {
	s.mu.Lock()
	task, ok := s.tasks[cardID]
	if !ok {
		s.mu.Unlock()
		return
	}
	sessionID := task.SessionID
	s.mu.Unlock()

	last, err := s.ocGetLastMessage(ctx, sessionID)
	if err != nil {
		s.log("finish.message.fail", fmt.Sprintf("card=%s session=%s err=%v", cardID, sessionID, err))
		return
	}

	finish := extractFinish(last)
	// Rule 1: no finish or tool-calls → session still active.
	if finish == "" || finish == "tool-calls" {
		return
	}

	s.mu.Lock()
	task, ok = s.tasks[cardID]
	if !ok {
		s.mu.Unlock()
		return
	}
	taskSnap := *task
	s.mu.Unlock()

	abort := taskSnap.Abort
	summary := taskSnap.Summary
	model := taskSnap.Model

	// Rule 2: abort was in progress → write abort success comment, run abort hook, destroy task.
	if abort != nil {
		s.trelloAddComment(ctx, cardID, fmt.Sprintf("Abort completed for session %s.", sessionID))
		if hookErr := s.runFinishHook(ctx, "session_abort", &taskSnap); hookErr != nil {
			s.addAttentionLabel(ctx, cardID)
			s.trelloAddComment(ctx, cardID, fmt.Sprintf("Hook session_abort failed: %v. Task tracking was still released.", hookErr))
			s.log("hook.session_abort.fail", fmt.Sprintf("card=%s err=%v", cardID, hookErr))
		}
		s.destroyTask(cardID)
		s.log("finish.abort.done", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
		return
	}

	// Rule 3: non-stop finish → abnormal end.
	if finish != "stop" {
		s.trelloMoveCard(ctx, cardID, s.listIDFor("done"))
		s.addAttentionLabel(ctx, cardID)
		s.trelloAddComment(ctx, cardID, fmt.Sprintf("Session ended abnormally: finish=%s. Please check manually.", finish))
		s.destroyTask(cardID)
		s.log("finish.abnormal", fmt.Sprintf("card=%s session=%s finish=%s", cardID, sessionID, finish))
		return
	}

	// Rule 4: stop + summary already sent → write completion comment, run finish hook, move done.
	if summary != nil {
		summaryText := ExtractSummaryText(last, summaryCharLimit)
		s.trelloAddComment(ctx, cardID, "Task finished. Summary:\n"+summaryText)
		if hookErr := s.runFinishHook(ctx, "session_finish", &taskSnap); hookErr != nil {
			s.addAttentionLabel(ctx, cardID)
			s.trelloAddComment(ctx, cardID, fmt.Sprintf("Hook session_finish failed: %v. Task was still moved to done.", hookErr))
			s.log("hook.session_finish.fail", fmt.Sprintf("card=%s err=%v", cardID, hookErr))
		}
		s.trelloMoveCard(ctx, cardID, s.listIDFor("done"))
		s.destroyTask(cardID)
		s.log("finish.done", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
		return
	}

	// Rule 5: stop + no summary → send summary prompt, set task.summary time.
	if err := s.ocSendPrompt(ctx, sessionID, model, summaryPromptText); err != nil {
		s.log("finish.summary.send.fail", fmt.Sprintf("card=%s session=%s err=%v", cardID, sessionID, err))
		// Complete without summary on send failure.
		s.trelloAddComment(ctx, cardID, "Task finished.")
		s.trelloMoveCard(ctx, cardID, s.listIDFor("done"))
		s.destroyTask(cardID)
		return
	}
	t := now
	s.mu.Lock()
	if task, ok := s.tasks[cardID]; ok {
		task.Summary = &t
	}
	s.mu.Unlock()
	s.log("finish.summary.requested", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
}

// reconcileDoing compares task state with Trello doing list.
// Processes doing.out before doing.in to avoid capacity count errors.
func (s *Server) reconcileDoing(ctx context.Context, now time.Time) {
	doing, err := s.trelloListCards(ctx, s.listIDFor("doing"))
	if err != nil {
		s.log("reconcile.doing.error", err.Error())
		return
	}

	// Only cards with a proj:* label are AI-managed; all others are ignored.
	doingSet := make(map[string]trelloCard, len(doing))
	for _, c := range doing {
		if !hasProjLabel(c) {
			continue
		}
		doingSet[c.ID] = c
	}

	s.mu.Lock()
	var outIDs []string
	for id := range s.tasks {
		if _, ok := doingSet[id]; !ok {
			outIDs = append(outIDs, id)
		}
	}
	var inCards []trelloCard
	for id, c := range doingSet {
		if _, ok := s.tasks[id]; !ok {
			inCards = append(inCards, c)
		}
	}
	s.mu.Unlock()

	// doing.out first (releases capacity).
	for _, id := range outIDs {
		s.handleDoingOut(ctx, id, now)
	}
	// doing.in after (uses capacity).
	for _, c := range inCards {
		s.handleDoingIn(ctx, c, now)
	}

	s.log("reconcile.doing", fmt.Sprintf("out=%d in=%d", len(outIDs), len(inCards)))
}

// handleDoingOut handles a card that left the doing list.
// Sends abort signal and sets task.abort; does not destroy the task yet.
func (s *Server) handleDoingOut(ctx context.Context, cardID string, now time.Time) {
	s.mu.Lock()
	task, ok := s.tasks[cardID]
	if !ok {
		s.mu.Unlock()
		return
	}
	if task.Abort != nil || task.SessionID == "__pending__" {
		s.mu.Unlock()
		return // already aborting or not yet started
	}
	sessionID := task.SessionID
	s.mu.Unlock()

	if err := s.ocAbortSession(ctx, sessionID); err != nil {
		s.log("doing.out.abort.fail", fmt.Sprintf("card=%s session=%s err=%v", cardID, sessionID, err))
	}

	t := now
	s.mu.Lock()
	if task, ok := s.tasks[cardID]; ok {
		task.Abort = &t
	}
	s.mu.Unlock()

	s.trelloAddComment(ctx, cardID, fmt.Sprintf("Abort requested for session %s.", sessionID))
	s.log("doing.out", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
}

// handleDoingIn handles a card newly found in the doing list.
// Implements the flow from design.md §7.3.
func (s *Server) handleDoingIn(ctx context.Context, card trelloCard, now time.Time) {
	s.mu.Lock()
	_, exists := s.tasks[card.ID]
	s.mu.Unlock()
	if exists {
		return
	}

	// Cards without proj:* label are not AI-managed; silently ignore.
	if !hasProjLabel(card) {
		return
	}

	// Parse proj label.
	proj, err := parseProj(card, s.cfg)
	if err != nil {
		s.trelloMoveCard(ctx, card.ID, s.listIDFor("done"))
		s.addAttentionLabel(ctx, card.ID)
		s.trelloAddComment(ctx, card.ID, "Cannot start task: project label is invalid: "+err.Error()+".")
		s.log("doing.in.proj.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		return
	}

	// Parse model label.
	model, err := parseModel(card, s.cfg)
	if err != nil {
		s.trelloMoveCard(ctx, card.ID, s.listIDFor("done"))
		s.addAttentionLabel(ctx, card.ID)
		s.trelloAddComment(ctx, card.ID, "Cannot start task: model label is invalid: "+err.Error()+".")
		s.log("doing.in.model.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		return
	}

	// Check capacity.
	s.mu.Lock()
	total := s.totalCount
	projCount := s.projCount[proj]
	s.mu.Unlock()

	if total >= s.cfg.MaxDoingTotal || projCount >= s.cfg.MaxDoingPerProject {
		s.trelloMoveCard(ctx, card.ID, s.listIDFor("todo"))
		s.trelloAddComment(ctx, card.ID, fmt.Sprintf("Cannot start task now: capacity is full for project %s.", proj))
		s.log("doing.in.cap", fmt.Sprintf("card=%s proj=%s total=%d projCount=%d", card.ID, proj, total, projCount))
		return
	}

	// Find the AllowedProject and load its .kanban.yml.
	allowedProj, _ := findProject(proj, s.cfg)
	pc, err := loadProjectConfig(allowedProj)
	if err != nil {
		s.trelloMoveCard(ctx, card.ID, s.listIDFor("done"))
		s.addAttentionLabel(ctx, card.ID)
		s.trelloAddComment(ctx, card.ID, "Cannot start task: failed to load .kanban.yml: "+err.Error()+".")
		s.log("doing.in.kanban_yml.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		return
	}

	// Create a pending task that counts against capacity from this point on.
	pendingTask := &Task{
		CardID:    card.ID,
		CardTitle: card.Name,
		CardURL:   card.URL,
		SessionID: "__pending__",
		Proj:      proj,
		Model:     model,
		Workdir:   allowedProj.Root,
	}
	s.mu.Lock()
	s.tasks[card.ID] = pendingTask
	s.totalCount++
	s.projCount[proj]++
	s.mu.Unlock()

	// Run session_new hook.
	workdir := allowedProj.Root
	hookResult, err := s.hookRunner.RunHook(ctx, "session_new", pendingTask, card, allowedProj, model, workdir, pc)
	if err != nil {
		s.trelloMoveCard(ctx, card.ID, s.listIDFor("done"))
		s.addAttentionLabel(ctx, card.ID)
		s.trelloAddComment(ctx, card.ID, fmt.Sprintf("Hook session_new failed: %v. Please check manually.", err))
		s.log("hook.session_new.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		s.destroyTask(card.ID)
		return
	}

	if hookResult.Workdir != "" {
		workdir = hookResult.Workdir
	}
	if hookResult.Comment != "" {
		s.trelloAddComment(ctx, card.ID, truncateString(hookResult.Comment, 500))
	}

	// Render the initial prompt using the project's .kanban.yml template/addons.
	prompt, promptErr := renderInitialPrompt(card, allowedProj, model, pc)
	if promptErr != nil {
		// Non-fatal: fall back to raw card description.
		s.log("doing.in.prompt.render.fail", fmt.Sprintf("card=%s err=%v, falling back to card.Desc", card.ID, promptErr))
		prompt = card.Desc
	}

	// Create opencode session.
	sessionID, err := s.ocCreateSession(ctx, model, workdir)
	if err != nil {
		s.log("doing.in.session.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		s.destroyTask(card.ID)
		return
	}

	// Send the initial prompt.
	if err := s.ocSendPrompt(ctx, sessionID, model, prompt); err != nil {
		s.log("doing.in.prompt.fail", fmt.Sprintf("card=%s session=%s err=%v", card.ID, sessionID, err))
		// Abort the already-created session to avoid leaving an orphan on the opencode side.
		if abortErr := s.ocAbortSession(ctx, sessionID); abortErr != nil {
			s.log("doing.in.session.abort.fail", fmt.Sprintf("card=%s session=%s err=%v", card.ID, sessionID, abortErr))
		}
		s.destroyTask(card.ID)
		return
	}

	// Upgrade pending task to a real session.
	s.mu.Lock()
	if t, ok := s.tasks[card.ID]; ok {
		t.SessionID = sessionID
		t.Workdir = workdir
	}
	s.mu.Unlock()

	s.trelloAddComment(ctx, card.ID, fmt.Sprintf("Started session %s.", sessionID))
	s.log("doing.in.started", fmt.Sprintf("card=%s session=%s proj=%s", card.ID, sessionID, proj))
}

// runFinishHook runs a session_finish or session_abort hook using data from the task snapshot.
func (s *Server) runFinishHook(ctx context.Context, event string, task *Task) error {
	allowedProj, _ := findProject(task.Proj, s.cfg)
	pc, err := loadProjectConfig(allowedProj)
	if err != nil {
		return fmt.Errorf("load project config: %w", err)
	}
	partialCard := trelloCard{ID: task.CardID, Name: task.CardTitle, URL: task.CardURL}
	_, hookErr := s.hookRunner.RunHook(ctx, event, task, partialCard, allowedProj, task.Model, task.Workdir, pc)
	return hookErr
}

// truncateString truncates s to at most maxRunes runes, adding "…" if truncated.
func truncateString(s string, maxRunes int) string {
	runes := []rune(s)
	if len(runes) <= maxRunes {
		return s
	}
	return string(runes[:maxRunes]) + "…"
}

// checkTimeouts handles abort and summary timeouts.
func (s *Server) checkTimeouts(ctx context.Context, now time.Time) {
	s.mu.Lock()
	cardIDs := make([]string, 0, len(s.tasks))
	for id := range s.tasks {
		cardIDs = append(cardIDs, id)
	}
	s.mu.Unlock()

	for _, cardID := range cardIDs {
		s.checkOneTimeout(ctx, cardID, now)
	}
}

func (s *Server) checkOneTimeout(ctx context.Context, cardID string, now time.Time) {
	s.mu.Lock()
	task, ok := s.tasks[cardID]
	if !ok {
		s.mu.Unlock()
		return
	}
	abort := task.Abort
	summary := task.Summary
	sessionID := task.SessionID
	s.mu.Unlock()

	if abort != nil && now.After(abort.Add(s.cfg.AbortTimeout)) {
		s.addAttentionLabel(ctx, cardID)
		s.trelloAddComment(ctx, cardID, fmt.Sprintf("Abort timeout for session %s. Please check manually.", sessionID))
		s.destroyTask(cardID)
		s.log("timeout.abort", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
		return
	}

	if summary != nil && now.After(summary.Add(s.cfg.SummaryTimeout)) {
		s.trelloMoveCard(ctx, cardID, s.listIDFor("done"))
		s.addAttentionLabel(ctx, cardID)
		s.trelloAddComment(ctx, cardID, "Summary timeout. Task was moved to done, but summary did not finish in time.")
		s.destroyTask(cardID)
		s.log("timeout.summary", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
	}
}

// promoteTodo promotes eligible cards from todo to doing.
// Implements design.md §9.
func (s *Server) promoteTodo(ctx context.Context, now time.Time) {
	s.mu.Lock()
	if s.totalCount >= s.cfg.MaxDoingTotal {
		s.mu.Unlock()
		return
	}
	s.mu.Unlock()

	todo, err := s.trelloListCards(ctx, s.listIDFor("todo"))
	if err != nil {
		s.log("promote.todo.error", err.Error())
		return
	}

	promoted := 0
	for _, card := range todo {
		s.mu.Lock()
		if s.totalCount >= s.cfg.MaxDoingTotal {
			s.mu.Unlock()
			return
		}
		s.mu.Unlock()

		// Cards without proj:* label are not AI-managed; skip silently.
		if !hasProjLabel(card) {
			continue
		}

		proj, err := parseProj(card, s.cfg)
		if err != nil {
			s.trelloMoveCard(ctx, card.ID, s.listIDFor("done"))
			s.addAttentionLabel(ctx, card.ID)
			s.trelloAddComment(ctx, card.ID, "Cannot start task: project label is invalid: "+err.Error()+".")
			continue
		}

		if _, err := parseModel(card, s.cfg); err != nil {
			s.trelloMoveCard(ctx, card.ID, s.listIDFor("done"))
			s.addAttentionLabel(ctx, card.ID)
			s.trelloAddComment(ctx, card.ID, "Cannot start task: model label is invalid: "+err.Error()+".")
			continue
		}

		s.mu.Lock()
		projCount := s.projCount[proj]
		s.mu.Unlock()
		if projCount >= s.cfg.MaxDoingPerProject {
			continue // proj at capacity, try next card
		}

		if err := s.trelloMoveCard(ctx, card.ID, s.listIDFor("doing")); err != nil {
			s.log("promote.move.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
			continue
		}

		s.handleDoingIn(ctx, card, now)
		promoted++
	}
	s.log("promote.done", fmt.Sprintf("promoted=%d", promoted))
}

// addAttentionLabel adds the attention label to a card, looking up its ID lazily.
func (s *Server) addAttentionLabel(ctx context.Context, cardID string) {
	name := s.labelNameFor("attention")
	if name == "" {
		s.log("attention.label.missing", fmt.Sprintf("card=%s attention label not configured", cardID))
		return
	}
	id, err := s.resolveLabelID(ctx, name)
	if err != nil {
		s.log("attention.label.fail", fmt.Sprintf("card=%s name=%s err=%v", cardID, name, err))
		return
	}
	if err := s.trelloAddLabel(ctx, cardID, id); err != nil {
		s.log("attention.label.add.fail", fmt.Sprintf("card=%s id=%s err=%v", cardID, id, err))
	}
}

// resolveLabelID returns the Trello label ID for a label name,
// using a cached lookup against the board's label list.
func (s *Server) resolveLabelID(ctx context.Context, name string) (string, error) {
	s.mu.Lock()
	if id, ok := s.labelIDs[name]; ok {
		s.mu.Unlock()
		return id, nil
	}
	s.mu.Unlock()

	if s.cfg.TrelloBoardID == "" {
		return "", fmt.Errorf("board_id not configured, cannot resolve label %q", name)
	}

	labels, err := s.trelloListBoardLabels(ctx, s.cfg.TrelloBoardID)
	if err != nil {
		return "", fmt.Errorf("list board labels: %w", err)
	}

	s.mu.Lock()
	for _, l := range labels {
		if l.Name != "" {
			s.labelIDs[l.Name] = l.ID
		}
	}
	id := s.labelIDs[name]
	s.mu.Unlock()

	if id == "" {
		return "", fmt.Errorf("label %q not found on board", name)
	}
	return id, nil
}
