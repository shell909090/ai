package auth

import (
	"errors"
	"path/filepath"
	"testing"

	"github.com/shell909090/ai/HITL-proxy/internal/database"
)

func TestDeleteKey_NotFound(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	a := NewAuthenticator(db)

	err = a.DeleteKey(9999)
	if err == nil {
		t.Fatal("expected error when deleting non-existent key, got nil")
	}
	if !errors.Is(err, ErrNotFound) {
		t.Errorf("expected ErrNotFound, got %v", err)
	}
}

func TestDeleteKey_ExistingKey(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	a := NewAuthenticator(db)

	if err := a.CreateKey("sk-test", "agent1"); err != nil {
		t.Fatalf("create key: %v", err)
	}

	keys, err := a.ListKeys()
	if err != nil {
		t.Fatalf("list keys: %v", err)
	}
	if len(keys) != 1 {
		t.Fatalf("expected 1 key, got %d", len(keys))
	}

	if err := a.DeleteKey(keys[0].ID); err != nil {
		t.Errorf("delete existing key: %v", err)
	}

	keys, err = a.ListKeys()
	if err != nil {
		t.Fatalf("list keys after delete: %v", err)
	}
	if len(keys) != 0 {
		t.Errorf("expected 0 keys after delete, got %d", len(keys))
	}
}
