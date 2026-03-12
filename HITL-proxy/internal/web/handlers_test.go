package web

import (
	"net/http"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"strconv"
	"strings"
	"testing"

	"github.com/shell909090/ai/HITL-proxy/internal/auth"
	"github.com/shell909090/ai/HITL-proxy/internal/database"
)

func newTestHandler(t *testing.T, password string) *Handler {
	t.Helper()
	db, err := database.Open(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })

	authenticator := auth.NewAuthenticator(db)
	h, err := NewHandler(nil, db, nil, nil, authenticator, password)
	if err != nil {
		t.Fatalf("NewHandler: %v", err)
	}
	return h
}

func TestBasicAuth_NoCreds(t *testing.T) {
	h := newTestHandler(t, "secret")
	inner := h.basicAuth(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	r := httptest.NewRequest(http.MethodGet, "/", nil)
	w := httptest.NewRecorder()
	inner(w, r)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
	if w.Header().Get("WWW-Authenticate") == "" {
		t.Error("want WWW-Authenticate header")
	}
}

func TestBasicAuth_WrongUsername(t *testing.T) {
	h := newTestHandler(t, "secret")
	inner := h.basicAuth(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	r := httptest.NewRequest(http.MethodGet, "/", nil)
	r.SetBasicAuth("notadmin", "secret")
	w := httptest.NewRecorder()
	inner(w, r)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

func TestBasicAuth_WrongPassword(t *testing.T) {
	h := newTestHandler(t, "secret")
	inner := h.basicAuth(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	r := httptest.NewRequest(http.MethodGet, "/", nil)
	r.SetBasicAuth("admin", "wrong")
	w := httptest.NewRecorder()
	inner(w, r)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

func TestBasicAuth_ValidCreds(t *testing.T) {
	h := newTestHandler(t, "secret")
	inner := h.basicAuth(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
	})

	r := httptest.NewRequest(http.MethodGet, "/", nil)
	r.SetBasicAuth("admin", "secret")
	w := httptest.NewRecorder()
	inner(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d", w.Code)
	}
}

func TestListAPIKeys_RequiresAuth(t *testing.T) {
	h := newTestHandler(t, "secret")
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	r := httptest.NewRequest(http.MethodGet, "/admin/apikeys", nil)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusUnauthorized {
		t.Errorf("want 401, got %d", w.Code)
	}
}

func TestCreateAPIKey_CacheControlNoStore(t *testing.T) {
	h := newTestHandler(t, "secret")
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	form := url.Values{"agent_name": {"test-agent"}}
	r := httptest.NewRequest(http.MethodPost, "/admin/apikeys", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.SetBasicAuth("admin", "secret")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusOK {
		t.Errorf("want 200, got %d", w.Code)
	}
	if cc := w.Header().Get("Cache-Control"); cc != "no-store" {
		t.Errorf("want Cache-Control: no-store, got %q", cc)
	}
}

func TestCreateAPIKey_KeyAppearsInResponse(t *testing.T) {
	h := newTestHandler(t, "secret")
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	form := url.Values{"agent_name": {"bot"}}
	r := httptest.NewRequest(http.MethodPost, "/admin/apikeys", strings.NewReader(form.Encode()))
	r.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	r.SetBasicAuth("admin", "secret")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	body := w.Body.String()
	if !strings.Contains(body, "sk-") {
		t.Error("response should contain the generated key (sk- prefix)")
	}
}

func TestDeleteAPIKey_Redirects(t *testing.T) {
	h := newTestHandler(t, "secret")
	mux := http.NewServeMux()
	h.RegisterRoutes(mux)

	// Create a key first
	if err := h.authenticator.CreateKey("sk-testkey", "agent"); err != nil {
		t.Fatalf("CreateKey: %v", err)
	}
	keys, err := h.authenticator.ListKeys()
	if err != nil || len(keys) == 0 {
		t.Fatal("expected at least one key")
	}
	id := keys[0].ID

	r := httptest.NewRequest(http.MethodPost, "/admin/apikeys/"+strconv.FormatInt(id, 10)+"/delete", nil)
	r.SetBasicAuth("admin", "secret")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, r)

	if w.Code != http.StatusSeeOther {
		t.Errorf("want 303, got %d", w.Code)
	}
	if loc := w.Header().Get("Location"); loc != "/admin/apikeys" {
		t.Errorf("want redirect to /admin/apikeys, got %q", loc)
	}
}
