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
		s.addBoardComment(ctx, cardID, fmt.Sprintf("Abort completed for session %s.", sessionID), "finish.abort.comment.fail")
		if hookErr := s.runFinishHook(ctx, "session_abort", &taskSnap); hookErr != nil {
			s.addAttentionLabel(ctx, cardID, "hook.session_abort.attention.fail")
			s.addBoardComment(ctx, cardID, fmt.Sprintf("Hook session_abort failed: %v. Task tracking was still released.", hookErr), "hook.session_abort.comment.fail")
			s.log("hook.session_abort.fail", fmt.Sprintf("card=%s err=%v", cardID, hookErr))
		}
		s.destroyTask(cardID)
		s.log("finish.abort.done", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
		return
	}

	// Rule 3: failed → abnormal end.
	if state.Kind == "failed" {
		if !s.moveCardOrLog(ctx, cardID, "done", "finish.abnormal.move.fail") {
			return
		}
		s.addAttentionLabel(ctx, cardID, "finish.abnormal.attention.fail")
		s.addBoardComment(ctx, cardID, fmt.Sprintf("Session ended abnormally: status=%s. Please check manually.", state.RawFinish), "finish.abnormal.comment.fail")
		s.destroyTask(cardID)
		s.log("finish.abnormal", fmt.Sprintf("card=%s session=%s finish=%s", cardID, sessionID, state.RawFinish))
		return
	}

	// From here state.Kind == "finished".

	// Rule 4: finished + summary already sent → write completion comment, run finish hook, move done.
	if summary != nil {
		s.addBoardComment(ctx, cardID, "Task finished. Summary:\n"+state.Text, "finish.done.comment.fail")
		if hookErr := s.runFinishHook(ctx, "session_finish", &taskSnap); hookErr != nil {
			s.addAttentionLabel(ctx, cardID, "hook.session_finish.attention.fail")
			s.addBoardComment(ctx, cardID, fmt.Sprintf("Hook session_finish failed: %v. Task was still moved to done.", hookErr), "hook.session_finish.comment.fail")
			s.log("hook.session_finish.fail", fmt.Sprintf("card=%s err=%v", cardID, hookErr))
		}
		if !s.moveCardOrLog(ctx, cardID, "done", "finish.done.move.fail") {
			return
		}
		s.destroyTask(cardID)
		s.log("finish.done", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
		return
	}

	// Rule 5: finished + no summary → send summary prompt, set task.summary time.
	if err := driver.SendPrompt(ctx, sessionID, summaryPromptText, taskSnap.Labels); err != nil {
		s.log("finish.summary.send.fail", fmt.Sprintf("card=%s session=%s err=%v", cardID, sessionID, err))
		if !s.moveCardOrLog(ctx, cardID, "done", "finish.summary.move.fail") {
			return
		}
		s.addAttentionLabel(ctx, cardID, "finish.summary.attention.fail")
		s.addBoardComment(ctx, cardID, fmt.Sprintf("Task finished, but summary prompt failed for session %s: %v. Please check manually.", sessionID, err), "finish.summary.comment.fail")
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

	s.addBoardComment(ctx, cardID, fmt.Sprintf("Abort requested for session %s.", sessionID), "doing.out.comment.fail")
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
		s.moveCardOrLog(ctx, card.ID, "done", "doing.in.proj.move.fail")
		s.addAttentionLabel(ctx, card.ID, "doing.in.proj.attention.fail")
		s.addBoardComment(ctx, card.ID, "Cannot start task: project label is invalid: "+err.Error()+".", "doing.in.proj.comment.fail")
		s.log("doing.in.proj.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		return
	}

	// Parse agent label.
	agentName, err := parseAgent(card, s.cfg)
	if err != nil {
		s.moveCardOrLog(ctx, card.ID, "done", "doing.in.agent.move.fail")
		s.addAttentionLabel(ctx, card.ID, "doing.in.agent.attention.fail")
		s.addBoardComment(ctx, card.ID, "Cannot start task: agent label is invalid: "+err.Error()+".", "doing.in.agent.comment.fail")
		s.log("doing.in.agent.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		return
	}

	s.mu.Lock()
	driver, driverOk := s.drivers[agentName]
	s.mu.Unlock()
	if !driverOk {
		s.moveCardOrLog(ctx, card.ID, "done", "doing.in.driver.move.fail")
		s.addAttentionLabel(ctx, card.ID, "doing.in.driver.attention.fail")
		s.addBoardComment(ctx, card.ID, fmt.Sprintf("Cannot start task: agent %q has no driver loaded.", agentName), "doing.in.driver.comment.fail")
		s.log("doing.in.driver.missing", fmt.Sprintf("card=%s agent=%s", card.ID, agentName))
		return
	}

	// Check capacity.
	s.mu.Lock()
	total := s.totalCount
	projCount := s.projCount[proj]
	s.mu.Unlock()

	if total >= s.cfg.MaxDoingTotal || projCount >= s.cfg.MaxDoingPerProject {
		s.moveCardOrLog(ctx, card.ID, "todo", "doing.in.cap.move.fail")
		s.addBoardComment(ctx, card.ID, fmt.Sprintf("Cannot start task now: capacity is full for project %s.", proj), "doing.in.cap.comment.fail")
		s.log("doing.in.cap", fmt.Sprintf("card=%s proj=%s total=%d projCount=%d", card.ID, proj, total, projCount))
		return
	}

	// Find the AllowedProject and load its .kanban.yml.
	allowedProj, _ := findProject(proj, s.cfg)
	pc, err := loadProjectConfig(allowedProj)
	if err != nil {
		s.moveCardOrLog(ctx, card.ID, "done", "doing.in.kanban_yml.move.fail")
		s.addAttentionLabel(ctx, card.ID, "doing.in.kanban_yml.attention.fail")
		s.addBoardComment(ctx, card.ID, "Cannot start task: failed to load .kanban.yml: "+err.Error()+".", "doing.in.kanban_yml.comment.fail")
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
		moved := s.moveCardOrLog(ctx, card.ID, "done", "hook.session_new.move.fail")
		s.addAttentionLabel(ctx, card.ID, "hook.session_new.attention.fail")
		s.addBoardComment(ctx, card.ID, fmt.Sprintf("Hook session_new failed: %v. Please check manually.", err), "hook.session_new.comment.fail")
		s.log("hook.session_new.fail", fmt.Sprintf("card=%s err=%v", card.ID, err))
		if moved {
			s.destroyTask(card.ID)
		}
		return
	}

	if hookResult.Workdir != "" {
		workdir = hookResult.Workdir
	}
	if hookResult.Comment != "" {
		s.addBoardComment(ctx, card.ID, truncateString(hookResult.Comment, 500), "hook.session_new.result_comment.fail")
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
		if s.failStartTask(ctx, card.ID, fmt.Sprintf("Cannot start task: failed to create session for proj %s with agent %s: %v. Please check manually.", proj, agentName, err)) {
			s.destroyTask(card.ID)
		}
		return
	}

	// Send the initial prompt.
	if err := driver.SendPrompt(ctx, sessionID, prompt, card.Labels); err != nil {
		s.log("doing.in.prompt.fail", fmt.Sprintf("card=%s session=%s err=%v", card.ID, sessionID, err))
		// Abort the already-created session to avoid leaving an orphan on the agent side.
		if abortErr := driver.AbortSession(ctx, sessionID); abortErr != nil {
			s.log("doing.in.session.abort.fail", fmt.Sprintf("card=%s session=%s err=%v", card.ID, sessionID, abortErr))
		}
		if s.failStartTask(ctx, card.ID, fmt.Sprintf("Cannot start task: failed to send initial prompt for session %s, proj %s, agent %s: %v. Session abort was requested; please check manually.", sessionID, proj, agentName, err)) {
			s.destroyTask(card.ID)
		}
		return
	}

	// Upgrade pending task to a real session.
	s.mu.Lock()
	if t, ok := s.tasks[card.ID]; ok {
		t.SessionID = sessionID
		t.Workdir = workdir
	}
	s.mu.Unlock()

	s.addBoardComment(ctx, card.ID, fmt.Sprintf("Started session %s.", sessionID), "doing.in.started.comment.fail")
	s.log("doing.in.started", fmt.Sprintf("card=%s session=%s proj=%s agent=%s", card.ID, sessionID, proj, agentName))
}

func (s *Server) failStartTask(ctx context.Context, cardID CardID, comment string) bool {
	if !s.moveCardOrLog(ctx, cardID, "done", "doing.in.fail_start.move.fail") {
		return false
	}
	s.addAttentionLabel(ctx, cardID, "doing.in.fail_start.attention.fail")
	s.addBoardComment(ctx, cardID, comment, "doing.in.fail_start.comment.fail")
	return true
}

func (s *Server) moveCardOrLog(ctx context.Context, cardID CardID, listName, event string) bool {
	if err := s.board.MoveCard(ctx, cardID, listName); err != nil {
		s.log(event, fmt.Sprintf("card=%s list=%s err=%v", cardID, listName, err))
		return false
	}
	return true
}

func (s *Server) addAttentionLabel(ctx context.Context, cardID CardID, event string) {
	labelName := s.cfg.TrelloLabels["attention"]
	if labelName == "" {
		s.log(event, fmt.Sprintf("card=%s attention label not configured", cardID))
		return
	}
	if err := s.board.AddLabel(ctx, cardID, labelName); err != nil {
		s.log(event, fmt.Sprintf("card=%s label=%s err=%v", cardID, labelName, err))
	}
}

func (s *Server) addBoardComment(ctx context.Context, cardID CardID, text, event string) {
	if err := s.board.AddComment(ctx, cardID, text); err != nil {
		s.log(event, fmt.Sprintf("card=%s err=%v", cardID, err))
	}
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
		s.addAttentionLabel(ctx, cardID, "timeout.abort.attention.fail")
		s.addBoardComment(ctx, cardID, fmt.Sprintf("Abort timeout for session %s. Please check manually.", sessionID), "timeout.abort.comment.fail")
		s.destroyTask(cardID)
		s.log("timeout.abort", fmt.Sprintf("card=%s session=%s", cardID, sessionID))
		return
	}

	if summary != nil && now.After(summary.Add(s.cfg.SummaryTimeout)) {
		if !s.moveCardOrLog(ctx, cardID, "done", "timeout.summary.move.fail") {
			return
		}
		s.addAttentionLabel(ctx, cardID, "timeout.summary.attention.fail")
		s.addBoardComment(ctx, cardID, "Summary timeout. Task was moved to done, but summary did not finish in time.", "timeout.summary.comment.fail")
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
			s.moveCardOrLog(ctx, card.ID, "done", "promote.proj.move.fail")
			s.addAttentionLabel(ctx, card.ID, "promote.proj.attention.fail")
			s.addBoardComment(ctx, card.ID, "Cannot start task: project label is invalid: "+err.Error()+".", "promote.proj.comment.fail")
			continue
		}

		if _, err := parseAgent(card, s.cfg); err != nil {
			s.moveCardOrLog(ctx, card.ID, "done", "promote.agent.move.fail")
			s.addAttentionLabel(ctx, card.ID, "promote.agent.attention.fail")
			s.addBoardComment(ctx, card.ID, "Cannot start task: agent label is invalid: "+err.Error()+".", "promote.agent.comment.fail")
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
