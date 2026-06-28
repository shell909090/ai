package kanban

import (
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"path/filepath"
	"strings"
	"time"
)

const controlMaxCommentLen = 16384

// controlCardJSON is the wire format for cards returned by the Control API.
type controlCardJSON struct {
	ID     string   `json:"id"`
	Name   string   `json:"name"`
	Desc   string   `json:"desc"`
	URL    string   `json:"url"`
	List   string   `json:"list"` // logical list name
	Labels []string `json:"labels"`
}

// cardToJSON converts a trelloCard to the control API JSON shape.
func (s *Server) cardToJSON(card trelloCard) controlCardJSON {
	labels := make([]string, 0, len(card.Labels))
	for _, l := range card.Labels {
		labels = append(labels, l.Name)
	}
	listName := s.listNameFor(card.IDList)
	return controlCardJSON{
		ID:     card.ID,
		Name:   card.Name,
		Desc:   card.Desc,
		URL:    card.URL,
		List:   listName,
		Labels: labels,
	}
}

// listNameFor returns the logical list name ("todo"/"doing"/"done") for a Trello list ID.
func (s *Server) listNameFor(listID string) string {
	for name, id := range s.cfg.TrelloLists {
		if id == listID {
			return name
		}
	}
	return ""
}

// registerControlRoutes adds Control API handlers to the mux.
// Called only when ControlToken is set.
func (s *Server) registerControlRoutes(mux *http.ServeMux) {
	auth := s.controlMiddleware
	mux.HandleFunc("GET /control/v1/lists", auth(s.handleControlListLists))
	mux.HandleFunc("GET /control/v1/cards", auth(s.handleControlListCards))
	mux.HandleFunc("GET /control/v1/cards/{id}", auth(s.handleControlShowCard))
	mux.HandleFunc("POST /control/v1/cards", auth(s.handleControlCreateCard))
	mux.HandleFunc("POST /control/v1/cards/{id}/move", auth(s.handleControlMoveCard))
	mux.HandleFunc("POST /control/v1/cards/{id}/comments", auth(s.handleControlAddComment))
	mux.HandleFunc("POST /control/v1/cards/{id}/labels", auth(s.handleControlAddLabel))
	mux.HandleFunc("DELETE /control/v1/cards/{id}/labels/{label}", auth(s.handleControlRemoveLabel))
}

// controlMiddleware wraps a handler with Bearer-token authentication.
func (s *Server) controlMiddleware(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		auth := r.Header.Get("Authorization")
		if !strings.HasPrefix(auth, "Bearer ") || strings.TrimPrefix(auth, "Bearer ") != s.cfg.ControlToken {
			http.Error(w, `{"error":"unauthorized"}`, http.StatusUnauthorized)
			return
		}
		next(w, r)
	}
}

// controlAuditLog writes an audit log entry (no sensitive body).
func (s *Server) controlAuditLog(op, cardID, target string) {
	s.log("control."+op, fmt.Sprintf("card=%s target=%s", cardID, target))
}

// --- List operations ---

func (s *Server) handleControlListLists(w http.ResponseWriter, r *http.Request) {
	type listItem struct {
		Name string `json:"name"`
		ID   string `json:"id"`
	}
	var lists []listItem
	for name, id := range s.cfg.TrelloLists {
		lists = append(lists, listItem{Name: name, ID: id})
	}
	writeJSON(w, http.StatusOK, map[string]any{"lists": lists})
}

// --- Card operations ---

func (s *Server) handleControlListCards(w http.ResponseWriter, r *http.Request) {
	listName := r.URL.Query().Get("list")
	listID := s.cfg.TrelloLists[listName]
	if listID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "unknown list: " + listName})
		return
	}
	cards, err := s.trelloListCards(r.Context(), listID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	result := make([]controlCardJSON, 0, len(cards))
	for _, c := range cards {
		result = append(result, s.cardToJSON(c))
	}
	writeJSON(w, http.StatusOK, result)
}

func (s *Server) handleControlShowCard(w http.ResponseWriter, r *http.Request) {
	cardID := r.PathValue("id")
	card, err := s.trelloGetCard(r.Context(), cardID)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, s.cardToJSON(card))
}

func (s *Server) handleControlCreateCard(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Title       string   `json:"title"`
		Description string   `json:"description"`
		CWD         string   `json:"cwd"`
		Project     string   `json:"project"` // explicit override (project name)
		Model       string   `json:"model"`   // model alias
		Labels      []string `json:"labels"`  // extra labels (non-proj)
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON"})
		return
	}
	if strings.TrimSpace(req.Title) == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "title is required"})
		return
	}

	// Resolve project.
	var proj AllowedProject
	if req.Project != "" {
		var ok bool
		proj, ok = findProject(req.Project, s.cfg)
		if !ok {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": "unknown project: " + req.Project})
			return
		}
	} else if req.CWD != "" {
		s.mu.Lock()
		tasksCopy := make(map[string]*Task, len(s.tasks))
		for k, v := range s.tasks {
			t := *v
			tasksCopy[k] = &t
		}
		s.mu.Unlock()
		var err error
		proj, err = inferProject(req.CWD, s.cfg, tasksCopy)
		if err != nil {
			writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
			return
		}
	} else {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "either cwd or project is required"})
		return
	}

	// Collect label IDs.
	labelIDs, err := s.resolveLabelIDsForCreate(r.Context(), proj, req.Model, req.Labels)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": err.Error()})
		return
	}

	todoID := s.cfg.TrelloLists["todo"]
	card, err := s.trelloCreateCard(r.Context(), todoID, req.Title, req.Description, labelIDs)
	if err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	s.controlAuditLog("create_card", card.ID, "todo proj="+proj.Name)
	writeJSON(w, http.StatusCreated, s.cardToJSON(card))
}

func (s *Server) handleControlMoveCard(w http.ResponseWriter, r *http.Request) {
	cardID := r.PathValue("id")
	var req struct {
		List string `json:"list"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON"})
		return
	}
	listID := s.cfg.TrelloLists[req.List]
	if listID == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "unknown list: " + req.List})
		return
	}
	if err := s.trelloMoveCard(r.Context(), cardID, listID); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	s.controlAuditLog("move_card", cardID, req.List)
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleControlAddComment(w http.ResponseWriter, r *http.Request) {
	cardID := r.PathValue("id")
	var req struct {
		Text string `json:"text"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON"})
		return
	}
	if len(req.Text) > controlMaxCommentLen {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": fmt.Sprintf("comment exceeds max length %d", controlMaxCommentLen)})
		return
	}
	if err := s.trelloAddComment(r.Context(), cardID, req.Text); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	s.controlAuditLog("add_comment", cardID, "")
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleControlAddLabel(w http.ResponseWriter, r *http.Request) {
	cardID := r.PathValue("id")
	var req struct {
		Label string `json:"label"`
	}
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "invalid JSON"})
		return
	}
	if req.Label == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "label is required"})
		return
	}
	labelID, err := s.resolveLabelID(r.Context(), req.Label)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "unknown label: " + req.Label})
		return
	}
	if err := s.trelloAddLabel(r.Context(), cardID, labelID); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	s.controlAuditLog("add_label", cardID, req.Label)
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

func (s *Server) handleControlRemoveLabel(w http.ResponseWriter, r *http.Request) {
	cardID := r.PathValue("id")
	labelName := r.PathValue("label")
	if labelName == "" {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "label name is required"})
		return
	}
	labelID, err := s.resolveLabelID(r.Context(), labelName)
	if err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"error": "unknown label: " + labelName})
		return
	}
	if err := s.trelloRemoveLabel(r.Context(), cardID, labelID); err != nil {
		writeJSON(w, http.StatusInternalServerError, map[string]string{"error": err.Error()})
		return
	}
	s.controlAuditLog("remove_label", cardID, labelName)
	writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
}

// --- Project inference ---

// inferProject resolves the project for a given working directory.
// It matches cwd against AllowedProject.Root and active task.Workdir values,
// selecting the longest matching path (path-boundary-aware).
func inferProject(cwd string, cfg Config, tasks map[string]*Task) (AllowedProject, error) {
	if cwd == "" {
		return AllowedProject{}, fmt.Errorf("cwd is empty")
	}
	cwd = filepath.Clean(cwd)

	type candidate struct {
		proj    AllowedProject
		pathLen int
	}
	var candidates []candidate

	for _, p := range cfg.AllowedProjects {
		if p.Root == "" {
			continue
		}
		root := filepath.Clean(p.Root)
		if pathContainsDir(root, cwd) {
			candidates = append(candidates, candidate{proj: p, pathLen: len(root)})
		}
	}

	for _, t := range tasks {
		if t.Workdir == "" {
			continue
		}
		workdir := filepath.Clean(t.Workdir)
		if pathContainsDir(workdir, cwd) {
			if p, ok := findProject(t.Proj, cfg); ok {
				candidates = append(candidates, candidate{proj: p, pathLen: len(workdir)})
			}
		}
	}

	if len(candidates) == 0 {
		return AllowedProject{}, fmt.Errorf("cwd %q is not under any configured project root or active workdir", cwd)
	}

	// Find longest match length.
	maxLen := 0
	for _, c := range candidates {
		if c.pathLen > maxLen {
			maxLen = c.pathLen
		}
	}

	// Collect winners and check for ambiguity.
	seen := map[string]bool{}
	var winners []AllowedProject
	for _, c := range candidates {
		if c.pathLen == maxLen && !seen[c.proj.Name] {
			seen[c.proj.Name] = true
			winners = append(winners, c.proj)
		}
	}

	if len(winners) > 1 {
		names := make([]string, len(winners))
		for i, w := range winners {
			names[i] = w.Name
		}
		return AllowedProject{}, fmt.Errorf("ambiguous project for cwd %q: matches %s", cwd, strings.Join(names, ", "))
	}

	return winners[0], nil
}

// pathContainsDir reports whether root contains dir (path-boundary-aware).
// /repo/app does NOT match /repo/app2.
func pathContainsDir(root, dir string) bool {
	if root == dir {
		return true
	}
	return strings.HasPrefix(dir, root+string(filepath.Separator))
}

// resolveLabelIDsForCreate collects Trello label IDs for a new todo card.
func (s *Server) resolveLabelIDsForCreate(ctx context.Context, proj AllowedProject, modelAlias string, extraLabels []string) ([]string, error) {
	var ids []string

	// proj:* label
	if proj.Label != "" {
		id, err := s.resolveLabelID(ctx, proj.Label)
		if err != nil {
			return nil, fmt.Errorf("cannot resolve proj label %q: %w", proj.Label, err)
		}
		ids = append(ids, id)
	}

	// model:* label (optional)
	if modelAlias != "" {
		modelLabel, err := s.resolveModelLabel(modelAlias)
		if err != nil {
			return nil, err
		}
		id, err := s.resolveLabelID(ctx, modelLabel)
		if err != nil {
			return nil, fmt.Errorf("cannot resolve model label %q: %w", modelLabel, err)
		}
		ids = append(ids, id)
	}

	// extra labels (non-proj labels like "attention")
	for _, labelName := range extraLabels {
		id, err := s.resolveLabelID(ctx, labelName)
		if err != nil {
			return nil, fmt.Errorf("cannot resolve label %q: %w", labelName, err)
		}
		ids = append(ids, id)
	}

	return ids, nil
}

// resolveModelLabel converts a model alias (e.g. "sonnet") to the model label name.
func (s *Server) resolveModelLabel(alias string) (string, error) {
	// Try direct match against allowed model labels
	for _, m := range s.cfg.AllowedModels {
		if m.Label == alias || m.Label == "model:"+alias {
			return m.Label, nil
		}
	}
	return "", fmt.Errorf("unknown model alias: %q", alias)
}

// controlServeHTTP serves the Control API on a dedicated address.
func (s *Server) controlServeHTTP(ctx context.Context) error {
	mux := http.NewServeMux()
	s.registerControlRoutes(mux)
	srv := &http.Server{
		Addr:         s.cfg.ControlListen,
		Handler:      mux,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}
	go func() {
		<-ctx.Done()
		shutCtx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutCtx)
	}()
	if err := srv.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		return fmt.Errorf("control http: %w", err)
	}
	return nil
}
