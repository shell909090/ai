package kanban

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// ---------- helpers ----------

const testToken = "test-control-token"

func newControlServer(t *testing.T, board BoardGateway) *Server {
	t.Helper()
	s := newTestServer(t, board)
	s.cfg.ControlToken = testToken
	s.cfg.AllowedProjects = []AllowedProject{
		{Label: "proj:agent", Name: "agent", Root: "/repo/agent"},
		{Label: "proj:kanban", Name: "kanban", Root: "/repo/kanban"},
	}
	return s
}

func controlDo(t *testing.T, s *Server, method, path, token string, body any) *httptest.ResponseRecorder {
	t.Helper()
	var reqBody *bytes.Reader
	if body != nil {
		b, _ := json.Marshal(body)
		reqBody = bytes.NewReader(b)
	} else {
		reqBody = bytes.NewReader(nil)
	}
	req := httptest.NewRequest(method, path, reqBody)
	req.Header.Set("Content-Type", "application/json")
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	rec := httptest.NewRecorder()
	s.HTTPHandler().ServeHTTP(rec, req)
	return rec
}

// ---------- authentication ----------

func TestControlAuthMissingToken(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	rec := controlDo(t, s, "GET", "/control/v1/lists", "", nil)
	if rec.Code != http.StatusUnauthorized {
		t.Errorf("code=%d, want 401", rec.Code)
	}
}

func TestControlAuthWrongToken(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	rec := controlDo(t, s, "GET", "/control/v1/lists", "wrong-token", nil)
	if rec.Code != http.StatusUnauthorized {
		t.Errorf("code=%d, want 401", rec.Code)
	}
}

func TestControlAuthEmptyBearer(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	req := httptest.NewRequest("GET", "/control/v1/lists", nil)
	req.Header.Set("Authorization", "Bearer ")
	rec := httptest.NewRecorder()
	s.HTTPHandler().ServeHTTP(rec, req)
	if rec.Code != http.StatusUnauthorized {
		t.Errorf("empty Bearer should be 401, got %d", rec.Code)
	}
}

func TestControlAuthCorrectToken(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	rec := controlDo(t, s, "GET", "/control/v1/lists", testToken, nil)
	if rec.Code == http.StatusUnauthorized {
		t.Error("valid token should not get 401")
	}
}

// ---------- list lists ----------

func TestControlListLists(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	rec := controlDo(t, s, "GET", "/control/v1/lists", testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d, want 200; body=%s", rec.Code, rec.Body.String())
	}
	var resp struct {
		Lists []struct {
			Name string `json:"name"`
		} `json:"lists"`
	}
	if err := json.NewDecoder(rec.Body).Decode(&resp); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(resp.Lists) != 3 {
		t.Errorf("len(lists)=%d, want 3", len(resp.Lists))
	}
}

// ---------- list cards ----------

func TestControlListCardsUnknownList(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	rec := controlDo(t, s, "GET", "/control/v1/cards?list=unknown", testToken, nil)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("code=%d, want 400", rec.Code)
	}
}

func TestControlListCards(t *testing.T) {
	board := newFakeBoardGateway()
	board.setCards("todo", []CardSnapshot{
		{ID: "c1", Title: "T1", Labels: []string{"proj:agent"}},
		{ID: "c2", Title: "T2"},
	})

	s := newControlServer(t, board)
	rec := controlDo(t, s, "GET", "/control/v1/cards?list=todo", testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	var cards []controlCardJSON
	if err := json.NewDecoder(rec.Body).Decode(&cards); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if len(cards) != 2 {
		t.Errorf("len(cards)=%d, want 2", len(cards))
	}
}

// ---------- create card ----------

func TestControlCreateCardEmptyTitle(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	rec := controlDo(t, s, "POST", "/control/v1/cards", testToken, map[string]string{
		"title": "", "cwd": "/repo/agent",
	})
	if rec.Code != http.StatusBadRequest {
		t.Errorf("code=%d, want 400", rec.Code)
	}
	if !strings.Contains(rec.Body.String(), "title") {
		t.Errorf("error should mention title, got: %s", rec.Body.String())
	}
}

func TestControlCreateCardUnknownProject(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	rec := controlDo(t, s, "POST", "/control/v1/cards", testToken, map[string]string{
		"title": "T", "project": "nonexistent",
	})
	if rec.Code != http.StatusBadRequest {
		t.Errorf("code=%d, want 400", rec.Code)
	}
}

func TestControlCreateCardCwdInference(t *testing.T) {
	board := newFakeBoardGateway()
	// Add proj:agent to known labels so CreateCard can resolve it.
	board.knownLabels["proj:agent"] = true

	s := newControlServer(t, board)
	rec := controlDo(t, s, "POST", "/control/v1/cards", testToken, map[string]any{
		"title":       "New task",
		"description": "desc",
		"cwd":         "/repo/agent/subdir",
	})
	if rec.Code != http.StatusCreated {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestControlCreateCardExplicitProject(t *testing.T) {
	board := newFakeBoardGateway()
	board.knownLabels["proj:kanban"] = true

	s := newControlServer(t, board)
	rec := controlDo(t, s, "POST", "/control/v1/cards", testToken, map[string]any{
		"title":   "Task",
		"project": "kanban",
	})
	if rec.Code != http.StatusCreated {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
}

func TestControlCreateCardNoCwdNoProject(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	rec := controlDo(t, s, "POST", "/control/v1/cards", testToken, map[string]any{
		"title": "Task",
		// neither cwd nor project
	})
	if rec.Code != http.StatusBadRequest {
		t.Errorf("code=%d, want 400", rec.Code)
	}
}

// ---------- move card ----------

func TestControlMoveCardUnknownList(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	rec := controlDo(t, s, "POST", "/control/v1/cards/c1/move", testToken, map[string]string{
		"list": "nonexistent",
	})
	if rec.Code != http.StatusBadRequest {
		t.Errorf("code=%d, want 400", rec.Code)
	}
}

func TestControlMoveCard(t *testing.T) {
	board := newFakeBoardGateway()
	s := newControlServer(t, board)

	rec := controlDo(t, s, "POST", "/control/v1/cards/c1/move", testToken, map[string]string{
		"list": "done",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.moves) != 1 || board.moves[0].list != "done" {
		t.Errorf("moves=%v", board.moves)
	}
}

// ---------- add comment ----------

func TestControlAddCommentTooLong(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	longText := strings.Repeat("x", controlMaxCommentLen+1)
	rec := controlDo(t, s, "POST", "/control/v1/cards/c1/comments", testToken, map[string]string{
		"text": longText,
	})
	if rec.Code != http.StatusBadRequest {
		t.Errorf("code=%d, want 400", rec.Code)
	}
}

func TestControlAddComment(t *testing.T) {
	board := newFakeBoardGateway()
	s := newControlServer(t, board)

	rec := controlDo(t, s, "POST", "/control/v1/cards/c1/comments", testToken, map[string]string{
		"text": "Hello!",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.comments) != 1 || board.comments[0] != "Hello!" {
		t.Errorf("comments=%v", board.comments)
	}
}

// ---------- add/remove label ----------

func TestControlAddLabelUnknown(t *testing.T) {
	board := newFakeBoardGateway()
	s := newControlServer(t, board)

	rec := controlDo(t, s, "POST", "/control/v1/cards/c1/labels", testToken, map[string]string{
		"label": "notexist",
	})
	if rec.Code != http.StatusBadRequest {
		t.Errorf("code=%d, want 400", rec.Code)
	}
}

func TestControlAddLabel(t *testing.T) {
	board := newFakeBoardGateway()
	s := newControlServer(t, board)

	rec := controlDo(t, s, "POST", "/control/v1/cards/c1/labels", testToken, map[string]string{
		"label": "attention",
	})
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	board.mu.Lock()
	defer board.mu.Unlock()
	if len(board.labelAdds) != 1 {
		t.Errorf("labelAdds=%v", board.labelAdds)
	}
}

func TestControlRemoveLabelUnknown(t *testing.T) {
	board := newFakeBoardGateway()
	s := newControlServer(t, board)

	rec := controlDo(t, s, "DELETE", "/control/v1/cards/c1/labels/unknownlabel", testToken, nil)
	if rec.Code != http.StatusBadRequest {
		t.Errorf("code=%d, want 400", rec.Code)
	}
}

// ---------- project inference ----------

func TestInferProjectExact(t *testing.T) {
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:agent", Name: "agent", Root: "/repo/agent"},
		},
	}
	proj, err := inferProject("/repo/agent", cfg, nil)
	if err != nil || proj.Name != "agent" {
		t.Errorf("err=%v proj=%+v", err, proj)
	}
}

func TestInferProjectSubdir(t *testing.T) {
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:agent", Name: "agent", Root: "/repo/agent"},
		},
	}
	proj, err := inferProject("/repo/agent/src/pkg", cfg, nil)
	if err != nil || proj.Name != "agent" {
		t.Errorf("err=%v proj=%+v", err, proj)
	}
}

func TestInferProjectNoBoundaryMismatch(t *testing.T) {
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:agent", Name: "agent", Root: "/repo/agent"},
		},
	}
	_, err := inferProject("/repo/agent2", cfg, nil)
	if err == nil {
		t.Error("expected error: /repo/agent should not match /repo/agent2")
	}
}

func TestInferProjectLongestWins(t *testing.T) {
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:repo", Name: "repo", Root: "/repo"},
			{Label: "proj:agent", Name: "agent", Root: "/repo/agent"},
		},
	}
	proj, err := inferProject("/repo/agent/src", cfg, nil)
	if err != nil || proj.Name != "agent" {
		t.Errorf("expected 'agent' (longest match), err=%v proj=%+v", err, proj)
	}
}

func TestInferProjectAmbiguous(t *testing.T) {
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:a", Name: "a", Root: "/repo/a"},
			{Label: "proj:b", Name: "b", Root: "/repo/b"},
		},
	}
	_, err := inferProject("/repo/a/src", cfg, nil)
	if err != nil {
		t.Errorf("expected unambiguous match for /repo/a/src, got err=%v", err)
	}
}

func TestInferProjectNoMatch(t *testing.T) {
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:agent", Name: "agent", Root: "/repo/agent"},
		},
	}
	_, err := inferProject("/other/dir", cfg, nil)
	if err == nil {
		t.Error("expected error for unmatched cwd")
	}
}

func TestInferProjectFromTaskWorkdir(t *testing.T) {
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:agent", Name: "agent", Root: "/repo/agent"},
		},
	}
	tasks := map[string]*Task{
		"c1": {Proj: "agent", Workdir: "/repo/worktrees/card-123"},
	}
	proj, err := inferProject("/repo/worktrees/card-123/subdir", cfg, tasks)
	if err != nil || proj.Name != "agent" {
		t.Errorf("err=%v proj=%+v", err, proj)
	}
}

func TestInferProjectTwoAmbiguousRoots(t *testing.T) {
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:a", Name: "a", Root: "/shared/a"},
			{Label: "proj:b", Name: "b", Root: "/shared/b"},
		},
	}
	_, err := inferProject("/other", cfg, nil)
	if err == nil {
		t.Error("expected error for unmatched cwd")
	}
}

// Verify audit log output contains expected fields.
func TestControlAuditLog(t *testing.T) {
	board := newFakeBoardGateway()
	s := newControlServer(t, board)
	s.cfg.TrelloToken = "TRELLO_SECRET_9876"

	log := &drainLog{}
	withLogWriter(t, log)

	_ = controlDo(t, s, "POST", "/control/v1/cards/c1/move", testToken, map[string]string{"list": "done"})

	if !strings.Contains(log.String(), "control.move_card") {
		t.Errorf("audit log missing control.move_card; got: %s", log.String())
	}
	if strings.Contains(log.String(), "TRELLO_SECRET_9876") {
		t.Error("audit log must not contain Trello token")
	}
}

// verify control API routes are NOT registered when token is empty
func TestControlRoutesRequireToken(t *testing.T) {
	s := newTestServer(t, newFakeBoardGateway())
	// ControlToken is empty → routes not registered.
	rec := controlDo(t, s, "GET", "/control/v1/lists", testToken, nil)
	if rec.Code != http.StatusNotFound {
		t.Errorf("control routes should not exist without ControlToken, got %d", rec.Code)
	}
}

func TestControlCreateCardRegistersRoute(t *testing.T) {
	s := newControlServer(t, newFakeBoardGateway())
	rec := controlDo(t, s, "POST", "/control/v1/cards", "", nil)
	if rec.Code == http.StatusNotFound {
		t.Error("route should be registered (got 404)")
	}
}

func TestInferProjectSymlink(t *testing.T) {
	realDir := t.TempDir()
	linkDir := filepath.Join(t.TempDir(), "link")
	if err := os.Symlink(realDir, linkDir); err != nil {
		t.Skip("symlink not supported:", err)
	}
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:a", Name: "a", Root: realDir},
		},
	}
	proj, err := inferProject(linkDir, cfg, nil)
	if err != nil || proj.Name != "a" {
		t.Errorf("expected proj 'a' via symlink, got err=%v proj=%+v", err, proj)
	}
}

func TestInferProjectEmptyCwd(t *testing.T) {
	cfg := Config{AllowedProjects: []AllowedProject{{Label: "proj:a", Name: "a", Root: "/repo"}}}
	_, err := inferProject("", cfg, nil)
	if err == nil {
		t.Error("expected error for empty cwd")
	}
}

func TestControlCreateCardFromTaskWorkdir(t *testing.T) {
	board := newFakeBoardGateway()
	board.knownLabels["proj:agent"] = true

	s := newControlServer(t, board)
	s.mu.Lock()
	s.tasks["c_existing"] = &Task{
		CardID:  "c_existing",
		Proj:    "agent",
		Workdir: "/repo/worktrees/wt1",
	}
	s.mu.Unlock()

	rec := controlDo(t, s, "POST", "/control/v1/cards", testToken, map[string]any{
		"title": "New from workdir",
		"cwd":   "/repo/worktrees/wt1/src",
	})
	if rec.Code == http.StatusBadRequest && strings.Contains(rec.Body.String(), "not under any") {
		t.Errorf("cwd inference failed: %s", rec.Body.String())
	}
}

// ---------- fakeBoardGateway show-card support ----------

func TestControlShowCard(t *testing.T) {
	board := newFakeBoardGateway()
	board.setCards("todo", []CardSnapshot{
		{ID: "c1", Title: "My card", List: "todo", Labels: []string{"proj:agent"}},
	})
	s := newControlServer(t, board)

	rec := controlDo(t, s, "GET", "/control/v1/cards/c1", testToken, nil)
	if rec.Code != http.StatusOK {
		t.Fatalf("code=%d body=%s", rec.Code, rec.Body.String())
	}
	var card controlCardJSON
	if err := json.NewDecoder(rec.Body).Decode(&card); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if card.ID != "c1" || card.Name != "My card" {
		t.Errorf("card=%+v", card)
	}
}
