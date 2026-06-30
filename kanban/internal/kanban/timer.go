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
	cardIDs := make([]CardID, 0, len(s.tasks))
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
// Implements the rules from design.md §8.
func (s *Server) checkOneFinish(ctx context.Context, cardID CardID, now time.Time) {
	s.mu.Lock()
	task, ok := s.tasks[cardID]
	if !ok {
		s.mu.Unlock()
		return
	}
	sessionID := task.SessionID
	agentName := task.Agent
	s.mu.Unlock()

	s.mu.Lock()
	driver, ok := s.drivers[agentName]
	s.mu.Unlock()
	if !ok {
		s.log("finish.driver.missing", fmt.Sprintf("card=%s agent=%s", cardID, agentName))
		return
	}

	state, err := driver.SessionState(ctx, sessionID)
	if err != nil {
		s.log("finish.state.fail", fmt.Sprintf("card=%s session=%s err=%v", cardID, sessionID, err))
		return
	}

	// Rule 1: session still active.
	if state.Kind == "running" {
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

	// Rule 2: abort was in progress → write abort success comment, run abort hook, destroy task.
	if abort != nil {
		s.board.AddComment(ctx, cardID, fmt.Sprintf("Abort completed for session %s.", sessionID))
		if hookErr := s.runFinishHook(ctx, "session_abort", &taskSnap); hookErr != nil {
			s.board.AddLabel(ctx, cardID, s.cfg.TrelloLabels["attention"])
			s.board.AddComment(ctx, cardID, fmt.Sprintf("Hook session_abort failed: %v. Task tracking was still released.", hookErr))
			s.log("hook.session_abort.fail", fmt.Sprintf("card=%s err=%v", cardID, hookErr))
		}
		s.destroyTask(cardID)
		s.log("finish.abort.done", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
		return
	}

	// Rule 3: failed → abnormal end.
	if state.Kind == "failed" {
		s.board.MoveCard(ctx, cardID, "done")
		s.board.AddLabel(ctx, cardID, s.cfg.TrelloLabels["attention"])
		s.board.AddComment(ctx, cardID, fmt.Sprintf("Session ended abnormally: status=%s. Please check manually.", state.RawFinish))
		s.destroyTask(cardID)
		s.log("finish.abnormal", fmt.Sprintf("card=%s session=%s finish=%s", cardID, sessionID, state.RawFinish))
		return
	}

	// From here state.Kind == "finished".

	// Rule 4: finished + summary already sent → write completion comment, run finish hook, move done.
	if summary != nil {
		s.board.AddComment(ctx, cardID, "Task finished. Summary:\n"+state.Text)
		if hookErr := s.runFinishHook(ctx, "session_finish", &taskSnap); hookErr != nil {
			s.board.AddLabel(ctx, cardID, s.cfg.TrelloLabels["attention"])
			s.board.AddComment(ctx, cardID, fmt.Sprintf("Hook session_finish failed: %v. Task was still moved to done.", hookErr))
			s.log("hook.session_finish.fail", fmt.Sprintf("card=%s err=%v", cardID, hookErr))
		}
		s.board.MoveCard(ctx, cardID, "done")
		s.destroyTask(cardID)
		s.log("finish.done", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
		return
	}

	// Rule 5: finished + no summary → send summary prompt, set task.summary time.
	if err := driver.SendPrompt(ctx, sessionID, summaryPromptText, taskSnap.Labels); err != nil {
		s.log("finish.summary.send.fail", fmt.Sprintf("card=%s session=%s err=%v", cardID, sessionID, err))
		s.board.AddLabel(ctx, cardID, s.cfg.TrelloLabels["attention"])
		s.board.AddComment(ctx, cardID, fmt.Sprintf("Task finished, but summary prompt failed for session %s: %v. Please check manually.", sessionID, err))
		s.board.MoveCard(ctx, cardID, "done")
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

// reconcileDoing compares task state with the doing list.
// Processes doing.out before doing.in to avoid capacity count errors.
func (s *Server) reconcileDoing(ctx context.Context, now time.Time) {
	doing, err := s.board.ListCards(ctx, "doing")
	if err != nil {
		s.log("reconcile.doing.error", err.Error())
		return
	}

	// Only cards with a proj:* label are AI-managed; all others are ignored.
	doingSet := make(map[CardID]CardSnapshot, len(doing))
	for _, c := range doing {
		if !hasProjLabel(c) {
			continue
		}
		doingSet[c.ID] = c
	}

	s.mu.Lock()
	var outIDs []CardID
	for id := range s.tasks {
		if _, ok := doingSet[id]; !ok {
			outIDs = append(outIDs, id)
		}
	}
	var inCards []CardSnapshot
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
func (s *Server) handleDoingOut(ctx context.Context, cardID CardID, now time.Time) {
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
	agentName := task.Agent
	s.mu.Unlock()

	s.mu.Lock()
	driver, ok := s.drivers[agentName]
	s.mu.Unlock()
	if ok {
		if err := driver.AbortSession(ctx, sessionID); err != nil {
			s.log("doing.out.abort.fail", fmt.Sprintf("card=%s session=%s err=%v", cardID, sessionID, err))
		}
	} else {
		s.log("doing.out.driver.missing", fmt.Sprintf("card=%s agent=%s", cardID, agentName))
	}

	t := now
	s.mu.Lock()
	if task, ok := s.tasks[cardID]; ok {
		task.Abort = &t
	}
	s.mu.Unlock()

	s.board.AddComment(ctx, cardID, fmt.Sprintf("Abort requested for session %s.", sessionID))
	s.log("doing.out", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
}

// handleDoingIn handles a card newly found in the doing list.
// Implements the flow from design.md §9.3.
func (s *Server) handleDoingIn(ctx context.Context, card CardSnapshot, now time.Time) {
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
		s.board.MoveCard(ctx, card.ID, "done")
		s.board.AddLabel(ctx, card.ID, s.cfg.TrelloLabels["attention"])
		s.board.AddComment(ctx, card.ID, "Cannot start task: project label is invalid: "+err.Error()+".")
		s.log("doing.in.proj.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		return
	}

	// Parse agent label.
	agentName, err := parseAgent(card, s.cfg)
	if err != nil {
		s.board.MoveCard(ctx, card.ID, "done")
		s.board.AddLabel(ctx, card.ID, s.cfg.TrelloLabels["attention"])
		s.board.AddComment(ctx, card.ID, "Cannot start task: agent label is invalid: "+err.Error()+".")
		s.log("doing.in.agent.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		return
	}

	s.mu.Lock()
	driver, driverOk := s.drivers[agentName]
	s.mu.Unlock()
	if !driverOk {
		s.board.MoveCard(ctx, card.ID, "done")
		s.board.AddLabel(ctx, card.ID, s.cfg.TrelloLabels["attention"])
		s.board.AddComment(ctx, card.ID, fmt.Sprintf("Cannot start task: agent %q has no driver loaded.", agentName))
		s.log("doing.in.driver.missing", fmt.Sprintf("card=%s agent=%s", card.ID, agentName))
		return
	}

	// Check capacity.
	s.mu.Lock()
	total := s.totalCount
	projCount := s.projCount[proj]
	s.mu.Unlock()

	if total >= s.cfg.MaxDoingTotal || projCount >= s.cfg.MaxDoingPerProject {
		s.board.MoveCard(ctx, card.ID, "todo")
		s.board.AddComment(ctx, card.ID, fmt.Sprintf("Cannot start task now: capacity is full for project %s.", proj))
		s.log("doing.in.cap", fmt.Sprintf("card=%s proj=%s total=%d projCount=%d", card.ID, proj, total, projCount))
		return
	}

	// Find the AllowedProject and load its .kanban.yml.
	allowedProj, _ := findProject(proj, s.cfg)
	pc, err := loadProjectConfig(allowedProj)
	if err != nil {
		s.board.MoveCard(ctx, card.ID, "done")
		s.board.AddLabel(ctx, card.ID, s.cfg.TrelloLabels["attention"])
		s.board.AddComment(ctx, card.ID, "Cannot start task: failed to load .kanban.yml: "+err.Error()+".")
		s.log("doing.in.kanban_yml.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		return
	}

	agentType := s.cfg.Agents[agentName].Type

	// Create a pending task that counts against capacity from this point on.
	pendingTask := &Task{
		CardID:    card.ID,
		CardTitle: card.Title,
		CardURL:   card.URL,
		SessionID: "__pending__",
		Proj:      proj,
		Agent:     agentName,
		Workdir:   allowedProj.Root,
		Labels:    append([]string(nil), card.Labels...),
	}
	s.mu.Lock()
	s.tasks[card.ID] = pendingTask
	s.totalCount++
	s.projCount[proj]++
	s.mu.Unlock()

	// Run session_new hook.
	workdir := allowedProj.Root
	hookResult, err := s.hookRunner.RunHook(ctx, "session_new", pendingTask, card, allowedProj, agentName, agentType, workdir, pc)
	if err != nil {
		s.board.MoveCard(ctx, card.ID, "done")
		s.board.AddLabel(ctx, card.ID, s.cfg.TrelloLabels["attention"])
		s.board.AddComment(ctx, card.ID, fmt.Sprintf("Hook session_new failed: %v. Please check manually.", err))
		s.log("hook.session_new.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		s.destroyTask(card.ID)
		return
	}

	if hookResult.Workdir != "" {
		workdir = hookResult.Workdir
	}
	if hookResult.Comment != "" {
		s.board.AddComment(ctx, card.ID, truncateString(hookResult.Comment, 500))
	}

	// Render the initial prompt using the project's .kanban.yml template/addons.
	prompt, promptErr := renderInitialPrompt(card, allowedProj, agentName, agentType, pc)
	if promptErr != nil {
		// Non-fatal: fall back to raw card description.
		s.log("doing.in.prompt.render.fail", fmt.Sprintf("card=%s err=%v, falling back to card.Description", card.ID, promptErr))
		prompt = card.Description
	}

	// Create agent session.
	sessionID, err := driver.CreateSession(ctx, workdir, card.Labels)
	if err != nil {
		s.log("doing.in.session.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		s.failStartTask(ctx, card.ID, fmt.Sprintf("Cannot start task: failed to create session for proj %s with agent %s: %v. Please check manually.", proj, agentName, err))
		s.destroyTask(card.ID)
		return
	}

	// Send the initial prompt.
	if err := driver.SendPrompt(ctx, sessionID, prompt, card.Labels); err != nil {
		s.log("doing.in.prompt.fail", fmt.Sprintf("card=%s session=%s err=%v", card.ID, sessionID, err))
		// Abort the already-created session to avoid leaving an orphan on the agent side.
		if abortErr := driver.AbortSession(ctx, sessionID); abortErr != nil {
			s.log("doing.in.session.abort.fail", fmt.Sprintf("card=%s session=%s err=%v", card.ID, sessionID, abortErr))
		}
		s.failStartTask(ctx, card.ID, fmt.Sprintf("Cannot start task: failed to send initial prompt for session %s, proj %s, agent %s: %v. Session abort was requested; please check manually.", sessionID, proj, agentName, err))
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

	s.board.AddComment(ctx, card.ID, fmt.Sprintf("Started session %s.", sessionID))
	s.log("doing.in.started", fmt.Sprintf("card=%s session=%s proj=%s agent=%s", card.ID, sessionID, proj, agentName))
}

func (s *Server) failStartTask(ctx context.Context, cardID CardID, comment string) {
	s.board.MoveCard(ctx, cardID, "done")
	s.board.AddLabel(ctx, cardID, s.cfg.TrelloLabels["attention"])
	s.board.AddComment(ctx, cardID, comment)
}

// runFinishHook runs a session_finish or session_abort hook using data from the task snapshot.
func (s *Server) runFinishHook(ctx context.Context, event string, task *Task) error {
	allowedProj, _ := findProject(task.Proj, s.cfg)
	pc, err := loadProjectConfig(allowedProj)
	if err != nil {
		return fmt.Errorf("load project config: %w", err)
	}
	agentType := s.cfg.Agents[task.Agent].Type
	partialCard := CardSnapshot{ID: task.CardID, Title: task.CardTitle, URL: task.CardURL}
	_, hookErr := s.hookRunner.RunHook(ctx, event, task, partialCard, allowedProj, task.Agent, agentType, task.Workdir, pc)
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
	cardIDs := make([]CardID, 0, len(s.tasks))
	for id := range s.tasks {
		cardIDs = append(cardIDs, id)
	}
	s.mu.Unlock()

	for _, cardID := range cardIDs {
		s.checkOneTimeout(ctx, cardID, now)
	}
}

func (s *Server) checkOneTimeout(ctx context.Context, cardID CardID, now time.Time) {
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
		s.board.AddLabel(ctx, cardID, s.cfg.TrelloLabels["attention"])
		s.board.AddComment(ctx, cardID, fmt.Sprintf("Abort timeout for session %s. Please check manually.", sessionID))
		s.destroyTask(cardID)
		s.log("timeout.abort", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
		return
	}

	if summary != nil && now.After(summary.Add(s.cfg.SummaryTimeout)) {
		s.board.MoveCard(ctx, cardID, "done")
		s.board.AddLabel(ctx, cardID, s.cfg.TrelloLabels["attention"])
		s.board.AddComment(ctx, cardID, "Summary timeout. Task was moved to done, but summary did not finish in time.")
		s.destroyTask(cardID)
		s.log("timeout.summary", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
	}
}

// promoteTodo promotes eligible cards from todo to doing.
// Implements design.md §11.
func (s *Server) promoteTodo(ctx context.Context, now time.Time) {
	s.mu.Lock()
	if s.totalCount >= s.cfg.MaxDoingTotal {
		s.mu.Unlock()
		return
	}
	s.mu.Unlock()

	todo, err := s.board.ListCards(ctx, "todo")
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
			s.board.MoveCard(ctx, card.ID, "done")
			s.board.AddLabel(ctx, card.ID, s.cfg.TrelloLabels["attention"])
			s.board.AddComment(ctx, card.ID, "Cannot start task: project label is invalid: "+err.Error()+".")
			continue
		}

		if _, err := parseAgent(card, s.cfg); err != nil {
			s.board.MoveCard(ctx, card.ID, "done")
			s.board.AddLabel(ctx, card.ID, s.cfg.TrelloLabels["attention"])
			s.board.AddComment(ctx, card.ID, "Cannot start task: agent label is invalid: "+err.Error()+".")
			continue
		}

		s.mu.Lock()
		projCount := s.projCount[proj]
		s.mu.Unlock()
		if projCount >= s.cfg.MaxDoingPerProject {
			continue // proj at capacity, try next card
		}

		if err := s.board.MoveCard(ctx, card.ID, "doing"); err != nil {
			s.log("promote.move.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
			continue
		}

		s.handleDoingIn(ctx, card, now)
		promoted++
	}
	s.log("promote.done", fmt.Sprintf("promoted=%d", promoted))
}
