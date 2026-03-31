package auth

import (
	"context"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"

	"github.com/shell909090/ai/HITL-proxy/internal/database"
)

func newTestAuth(t *testing.T) *Authenticator {
	t.Helper()
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return NewAuthenticator(db)
}

func TestValidate_ValidKey(t *testing.T) {
	a := newTestAuth(t)

	if err := a.CreateKey("sk-valid", "agentX"); err != nil {
		t.Fatalf("create key: %v", err)
	}

	name, err := a.Validate("sk-valid")
	if err != nil {
		t.Fatalf("validate: %v", err)
	}
	if name != "agentX" {
		t.Errorf("expected agentX, got %q", name)
	}
}

func TestValidate_InvalidKey(t *testing.T) {
	a := newTestAuth(t)

	_, err := a.Validate("no-such-key")
	if err == nil {
		t.Fatal("expected error for invalid key, got nil")
	}
}

func TestCreateKey_ThenValidate(t *testing.T) {
	a := newTestAuth(t)

	keys := []struct {
		key   string
		agent string
	}{
		{"sk-one", "agent1"},
		{"sk-two", "agent2"},
	}
	for _, kv := range keys {
		if err := a.CreateKey(kv.key, kv.agent); err != nil {
			t.Fatalf("create key %q: %v", kv.key, err)
		}
	}

	for _, kv := range keys {
		got, err := a.Validate(kv.key)
		if err != nil {
			t.Errorf("validate %q: %v", kv.key, err)
			continue
		}
		if got != kv.agent {
			t.Errorf("key %q: expected agent %q, got %q", kv.key, kv.agent, got)
		}
	}
}

func TestListKeys_Empty(t *testing.T) {
	a := newTestAuth(t)

	keys, err := a.ListKeys()
	if err != nil {
		t.Fatalf("list keys: %v", err)
	}
	if len(keys) != 0 {
		t.Errorf("expected 0 keys, got %d", len(keys))
	}
}

func TestListKeys_Multiple(t *testing.T) {
	a := newTestAuth(t)

	agents := []string{"alice", "bob", "carol"}
	for i, ag := range agents {
		if err := a.CreateKey("sk-"+ag, ag); err != nil {
			t.Fatalf("create key %d: %v", i, err)
		}
	}

	keys, err := a.ListKeys()
	if err != nil {
		t.Fatalf("list keys: %v", err)
	}
	if len(keys) != len(agents) {
		t.Errorf("expected %d keys, got %d", len(agents), len(keys))
	}

	// Verify all returned keys have non-empty agent names and valid IDs.
	for _, k := range keys {
		if k.ID == 0 {
			t.Errorf("key has zero ID: %+v", k)
		}
		if k.AgentName == "" {
			t.Errorf("key has empty AgentName: %+v", k)
		}
	}
}

// --- context helpers ---

func TestContextWithAgent_RoundTrip(t *testing.T) {
	ctx := ContextWithAgent(context.Background(), "myAgent")
	name, ok := AgentFromContext(ctx)
	if !ok {
		t.Fatal("AgentFromContext: expected ok=true")
	}
	if name != "myAgent" {
		t.Errorf("expected myAgent, got %q", name)
	}
}

func TestAgentFromContext_Missing(t *testing.T) {
	_, ok := AgentFromContext(context.Background())
	if ok {
		t.Error("expected ok=false from empty context")
	}
}

// --- middleware ---

func okHandler(t *testing.T, wantAgent string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		name, ok := AgentFromContext(r.Context())
		if !ok {
			t.Error("middleware: agent not in context")
		}
		if name != wantAgent {
			t.Errorf("middleware: agent want %q, got %q", wantAgent, name)
		}
		w.WriteHeader(http.StatusOK)
	})
}

func TestMiddleware_ValidKey(t *testing.T) {
	a := newTestAuth(t)
	if err := a.CreateKey("sk-mw", "mwAgent"); err != nil {
		t.Fatalf("create key: %v", err)
	}

	handler := a.Middleware(okHandler(t, "mwAgent"))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer sk-mw")
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusOK {
		t.Errorf("expected 200, got %d", rr.Code)
	}
}

func TestMiddleware_MissingHeader(t *testing.T) {
	a := newTestAuth(t)
	handler := a.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("inner handler should not be called")
	}))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", rr.Code)
	}
}

func TestMiddleware_InvalidKey(t *testing.T) {
	a := newTestAuth(t)
	handler := a.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		t.Error("inner handler should not be called")
	}))

	req := httptest.NewRequest(http.MethodGet, "/", nil)
	req.Header.Set("Authorization", "Bearer no-such-key")
	rr := httptest.NewRecorder()
	handler.ServeHTTP(rr, req)

	if rr.Code != http.StatusUnauthorized {
		t.Errorf("expected 401, got %d", rr.Code)
	}
}
