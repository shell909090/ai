package database

import (
	"path/filepath"
	"testing"
)

func TestOpen(t *testing.T) {
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "test.db")

	db, err := Open(dbPath)
	if err != nil {
		t.Fatalf("Open: %v", err)
	}
	defer db.Close()

	// Verify tables exist
	tables := []string{"specs", "operations", "operation_deps", "api_keys", "authz_rules", "approval_rules", "approval_requests", "audit_log"}
	for _, table := range tables {
		var name string
		err := db.QueryRow("SELECT name FROM sqlite_master WHERE type='table' AND name=?", table).Scan(&name)
		if err != nil {
			t.Errorf("table %s not found: %v", table, err)
		}
	}

	// Verify FTS5 virtual table
	var name string
	err = db.QueryRow("SELECT name FROM sqlite_master WHERE type='table' AND name='operations_fts'").Scan(&name)
	if err != nil {
		t.Errorf("FTS5 table not found: %v", err)
	}
}
