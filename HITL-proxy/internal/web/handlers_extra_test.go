package web

import (
	"bytes"
	"fmt"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"github.com/shell909090/ai/HITL-proxy/internal/approval"
	"github.com/shell909090/ai/HITL-proxy/internal/auth"
	"github.com/shell909090/ai/HITL-proxy/internal/cred"
	"github.com/shell909090/ai/HITL-proxy/internal/database"
	"github.com/shell909090/ai/HITL-proxy/internal/search"
)

// minimalValidSpec is a tiny but valid OpenAPI 3.0 spec used in import tests.
const minimalValidSpec = `{
  "openapi": "3.0.0",
  "info": {"title": "Test", "version": "1.0.0"},
  "paths": {
    "/items": {
      "get": {
        "operationId": "listItems",
        "summary": "List items",
        "responses": {"200": {"description": "ok"}}
      }
    }
  }
}`

// newFullTestHandler creates a Handler wired up with a real engine, searcher,
// hub, authenticator and credential store — all backed by a temp SQLite DB.
func newFullTestHandler(t *testing.T, password string) (*Handler, *http.ServeMux) {
	t.Helper()
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })

	hub := approval.NewSSEHub()
	engine := approval.NewEngine(db, 5*time.Minute, 10*time.Millisecond, hub)
	searcher := search.NewHybridSearcher(db, nil)
	authenticator := auth.NewAuthenticator(db)

	// 32-byte AES key for cred store
	credKey := []byte("01234567890123456789012345678901")
	credStore, err := cred.NewStore(filepath.Join(dir, "creds.enc"), credKey)
	if err != nil {
		t.Fatalf("cred store: %v", err)
	}

	h, err := NewHandler(engine, db, searcher, hub, authenticator, credStore, password)
	if err != nil {
		t.Fatalf("NewHandler: %v", err)
	}

	mux := http.NewServeMux()
	h.RegisterRoutes(mux)
	return h, mux
}

// --- GET / (pendingHandler) ---

func TestPendingHandler_NoPending_Returns200(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodGet, "/", nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d; body: %s", w.Code, w.Body.String())
	}
}

// --- POST /approval/:id/approve and /reject ---

func insertPendingRequest(t *testing.T, h *Handler, opID string) int64 {
	t.Helper()
	res, err := h.db.Exec(
		`INSERT INTO approval_requests (operation_id, agent_name, params_json, reason, status, timeout_at)
		VALUES (?, 'agent', '{}', 'test', 'pending', datetime('now', '+5 minutes'))`,
		opID,
	)
	if err != nil {
		t.Fatalf("insert pending request: %v", err)
	}
	id, _ := res.LastInsertId()
	return id
}

func TestApproveHandler_ApprovesRequest(t *testing.T) {
	h, mux := newFullTestHandler(t, "testpass")
	reqID := insertPendingRequest(t, h, "op-web-approve")

	r := httptest.NewRequest(http.MethodPost, fmt.Sprintf("/approval/%d/approve", reqID), nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d; body: %s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "Approved") {
		t.Errorf("want 'Approved' in body, got: %s", w.Body.String())
	}
}

func TestRejectHandler_RejectsRequest(t *testing.T) {
	h, mux := newFullTestHandler(t, "testpass")
	reqID := insertPendingRequest(t, h, "op-web-reject")

	r := httptest.NewRequest(http.MethodPost, fmt.Sprintf("/approval/%d/reject", reqID), nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d; body: %s", w.Code, w.Body.String())
	}
	if !strings.Contains(w.Body.String(), "Rejected") {
		t.Errorf("want 'Rejected' in body, got: %s", w.Body.String())
	}
}

func TestApproveHandler_InvalidID_Returns400(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodPost, "/approval/notanid/approve", nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

func TestApproveHandler_NonExistentID_Returns500(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodPost, "/approval/"+strconv.Itoa(99999)+"/approve", nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	// Decide returns error for unknown ID → 500
	if w.Code != http.StatusInternalServerError {
		t.Errorf("want 500, got %d", w.Code)
	}
}

// --- GET /admin/specs ---

func TestAdminSpecs_Returns200(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodGet, "/admin/specs", nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d; body: %s", w.Code, w.Body.String())
	}
}

func TestAdminSpecs_RequiresAuth(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodGet, "/admin/specs", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

// --- POST /specs/import ---

func TestImportSpec_ValidSpec_Returns200(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodPost, "/specs/import?name=testspec",
		strings.NewReader(minimalValidSpec))
	r.Header.Set("Content-Type", "application/json")
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d; body: %s", w.Code, w.Body.String())
	}
	if ct := w.Header().Get("Content-Type"); !strings.HasPrefix(ct, "application/json") {
		t.Errorf("want Content-Type application/json, got %s", ct)
	}
}

func TestImportSpec_InvalidSpec_Returns400(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodPost, "/specs/import?name=bad",
		strings.NewReader(`{"not": "valid openapi"}`))
	r.Header.Set("Content-Type", "application/json")
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d; body: %s", w.Code, w.Body.String())
	}
}

// --- POST /admin/specs/import (form upload) ---

func TestAdminImportSpecForm_ValidSpec_Redirects(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	_ = mw.WriteField("name", "formspec")
	fw, err := mw.CreateFormFile("file", "spec.json")
	if err != nil {
		t.Fatalf("create form file: %v", err)
	}
	fmt.Fprint(fw, minimalValidSpec)
	mw.Close()

	r := httptest.NewRequest(http.MethodPost, "/admin/specs/import", &buf)
	r.Header.Set("Content-Type", mw.FormDataContentType())
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusSeeOther {
		t.Errorf("want 303, got %d; body: %s", w.Code, w.Body.String())
	}
	if loc := w.Header().Get("Location"); loc != "/admin/specs" {
		t.Errorf("want redirect to /admin/specs, got %q", loc)
	}
}

func TestAdminImportSpecForm_InvalidSpec_Returns400(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	var buf bytes.Buffer
	mw := multipart.NewWriter(&buf)
	_ = mw.WriteField("name", "bad")
	fw, err := mw.CreateFormFile("file", "spec.json")
	if err != nil {
		t.Fatalf("create form file: %v", err)
	}
	fmt.Fprint(fw, `{"garbage": true}`)
	mw.Close()

	r := httptest.NewRequest(http.MethodPost, "/admin/specs/import", &buf)
	r.Header.Set("Content-Type", mw.FormDataContentType())
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d; body: %s", w.Code, w.Body.String())
	}
}

// --- GET /admin/rules ---

func TestAdminRules_Returns200(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodGet, "/admin/rules", nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d; body: %s", w.Code, w.Body.String())
	}
}

// --- POST /admin/rules ---

func TestAdminSetRule_Returns200(t *testing.T) {
	h, mux := newFullTestHandler(t, "testpass")

	// Insert a spec and operation first so the rule row can be found after update
	db := h.db
	res, err := db.Exec(`INSERT INTO specs (name, raw_json) VALUES ('svc', '{}')`)
	if err != nil {
		t.Fatalf("insert spec: %v", err)
	}
	specID, _ := res.LastInsertId()
	_, err = db.Exec(
		`INSERT INTO operations (spec_id, operation_id, method, path, summary) VALUES (?, 'doThing', 'GET', '/things', 'Do a thing')`,
		specID,
	)
	if err != nil {
		t.Fatalf("insert operation: %v", err)
	}

	form := "operation_id=doThing&required=1"
	r := httptest.NewRequest(http.MethodPost, "/admin/rules",
		strings.NewReader(form))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d; body: %s", w.Code, w.Body.String())
	}
}

// --- GET /admin/apikeys (authenticated) ---

func TestAdminAPIKeys_AuthenticatedReturns200(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodGet, "/admin/apikeys", nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d; body: %s", w.Code, w.Body.String())
	}
}

// --- GET /admin/creds ---

func TestAdminCreds_Returns200(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodGet, "/admin/creds", nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d; body: %s", w.Code, w.Body.String())
	}
}

// --- GET /approval/:id (detail) ---

func TestDetail_InvalidID_Returns400(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodGet, "/approval/bad", nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

func TestDetail_NotFound_Returns404(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodGet, "/approval/99999", nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusNotFound {
		t.Errorf("want 404, got %d", w.Code)
	}
}

// --- POST /admin/specs/:id/delete ---

func TestDeleteSpec_Returns303(t *testing.T) {
	h, mux := newFullTestHandler(t, "testpass")

	// Import a spec first
	r := httptest.NewRequest(http.MethodPost, "/specs/import?name=deleteme",
		strings.NewReader(minimalValidSpec))
	r.Header.Set("Content-Type", "application/json")
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("import failed: %d %s", w.Code, w.Body.String())
	}

	// Find the spec ID
	var specID int64
	if err := h.db.QueryRow(`SELECT id FROM specs WHERE name = 'deleteme'`).Scan(&specID); err != nil {
		t.Fatalf("find spec: %v", err)
	}

	r2 := httptest.NewRequest(http.MethodPost, fmt.Sprintf("/admin/specs/%d/delete", specID), nil)
	r2.SetBasicAuth("admin", "testpass")
	w2 := httptest.NewRecorder()
	mux.ServeHTTP(w2, r2)

	if w2.Code != http.StatusSeeOther {
		t.Errorf("want 303, got %d; body: %s", w2.Code, w2.Body.String())
	}
	if loc := w2.Header().Get("Location"); loc != "/admin/specs" {
		t.Errorf("want redirect to /admin/specs, got %q", loc)
	}
}

func TestDeleteSpec_NotFound_Returns404(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodPost, "/admin/specs/99999/delete", nil)
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusNotFound {
		t.Errorf("want 404, got %d", w.Code)
	}
}

// --- Raw-header creds (spec with no securitySchemes) ---

// minimalSpecNoSchemes has no components.securitySchemes, triggering raw-header mode.
const minimalSpecNoSchemes = `{
  "openapi": "3.0.0",
  "info": {"title": "NoSchemes", "version": "1.0.0"},
  "paths": {
    "/ping": {
      "get": {
        "operationId": "ping",
        "responses": {"200": {"description": "ok"}}
      }
    }
  }
}`

func TestSetCreds_RawMode_NewKeyVal(t *testing.T) {
	h, mux := newFullTestHandler(t, "testpass")

	// Import spec with no security schemes.
	r := httptest.NewRequest(http.MethodPost, "/specs/import?name=rawspec",
		strings.NewReader(minimalSpecNoSchemes))
	r.Header.Set("Content-Type", "application/json")
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("import failed: %d %s", w.Code, w.Body.String())
	}

	// Set a raw header cred via __new_key/__new_val.
	form := "spec_name=rawspec&__new_key=Authorization&__new_val=Bearer+tok123"
	r2 := httptest.NewRequest(http.MethodPost, "/admin/creds", strings.NewReader(form))
	r2.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r2.SetBasicAuth("admin", "testpass")
	w2 := httptest.NewRecorder()
	mux.ServeHTTP(w2, r2)
	if w2.Code != http.StatusSeeOther {
		t.Errorf("want 303, got %d; body: %s", w2.Code, w2.Body.String())
	}

	// Verify the cred was stored.
	creds, _ := h.credStore.Get("rawspec")
	if creds["Authorization"] != "Bearer tok123" {
		t.Errorf("want 'Bearer tok123', got %q", creds["Authorization"])
	}
}

func TestDeleteCred_RemovesEntry(t *testing.T) {
	h, mux := newFullTestHandler(t, "testpass")

	// Seed a cred entry directly.
	if err := h.credStore.Set("svc", map[string]string{"Authorization": "Bearer tok"}); err != nil {
		t.Fatalf("set creds: %v", err)
	}

	form := "spec_name=svc&key=Authorization"
	r := httptest.NewRequest(http.MethodPost, "/admin/creds/delete", strings.NewReader(form))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusSeeOther {
		t.Errorf("want 303, got %d; body: %s", w.Code, w.Body.String())
	}

	creds, _ := h.credStore.Get("svc")
	if _, exists := creds["Authorization"]; exists {
		t.Errorf("expected Authorization to be deleted, still present")
	}
}

func TestDeleteCred_MissingParams_Returns400(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	r := httptest.NewRequest(http.MethodPost, "/admin/creds/delete",
		strings.NewReader("spec_name=svc"))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusBadRequest {
		t.Errorf("want 400, got %d", w.Code)
	}
}

func TestAdminCreds_RawMode_Shows200(t *testing.T) {
	_, mux := newFullTestHandler(t, "testpass")

	// Import spec with no security schemes.
	r := httptest.NewRequest(http.MethodPost, "/specs/import?name=rawspec2",
		strings.NewReader(minimalSpecNoSchemes))
	r.Header.Set("Content-Type", "application/json")
	r.SetBasicAuth("admin", "testpass")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)
	if w.Code != http.StatusOK {
		t.Fatalf("import failed: %d %s", w.Code, w.Body.String())
	}

	r2 := httptest.NewRequest(http.MethodGet, "/admin/creds", nil)
	r2.SetBasicAuth("admin", "testpass")
	w2 := httptest.NewRecorder()
	mux.ServeHTTP(w2, r2)
	if w2.Code != http.StatusOK {
		t.Errorf("want 200, got %d; body: %s", w2.Code, w2.Body.String())
	}
	if !strings.Contains(w2.Body.String(), "raw headers") {
		t.Errorf("want raw-header hint in body, got: %s", w2.Body.String())
	}
}
