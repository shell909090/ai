package database

import (
	"database/sql"
	"fmt"

	_ "modernc.org/sqlite"
)

func Open(path string) (*sql.DB, error) {
	db, err := sql.Open("sqlite", path+"?_journal_mode=WAL&_busy_timeout=5000")
	if err != nil {
		return nil, fmt.Errorf("open database: %w", err)
	}

	if err := db.Ping(); err != nil {
		db.Close()
		return nil, fmt.Errorf("ping database: %w", err)
	}

	if _, err := db.Exec("PRAGMA foreign_keys = ON"); err != nil {
		db.Close()
		return nil, fmt.Errorf("enable foreign keys: %w", err)
	}

	if err := migrate(db); err != nil {
		db.Close()
		return nil, fmt.Errorf("migrate: %w", err)
	}

	return db, nil
}

// migrations is a sequential list of SQL statements.
// Each entry corresponds to a version (1-indexed).
// New migrations are appended; existing entries must never be modified.
var migrations = []string{
	// Migration 1: add timeout_at column and index
	`ALTER TABLE approval_requests ADD COLUMN timeout_at DATETIME;
	 CREATE INDEX IF NOT EXISTS idx_approval_pending_timeout
	     ON approval_requests(status, timeout_at);`,
	// Migration 2: add security scheme columns for credential injection
	`ALTER TABLE specs ADD COLUMN security_schemes_json TEXT NOT NULL DEFAULT '{}';
	 ALTER TABLE operations ADD COLUMN security_json TEXT NOT NULL DEFAULT '[]';`,
}

func migrate(db *sql.DB) error {
	// Apply base schema (all CREATE IF NOT EXISTS, idempotent)
	if _, err := db.Exec(schemaSQL); err != nil {
		return fmt.Errorf("apply base schema: %w", err)
	}

	// Ensure schema_version table exists
	if _, err := db.Exec(`CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL)`); err != nil {
		return fmt.Errorf("create schema_version table: %w", err)
	}

	// Get current version
	var current int
	err := db.QueryRow(`SELECT COALESCE(MAX(version), 0) FROM schema_version`).Scan(&current)
	if err != nil {
		return fmt.Errorf("get schema version: %w", err)
	}

	// Apply pending migrations
	for i := current; i < len(migrations); i++ {
		if _, err := db.Exec(migrations[i]); err != nil {
			return fmt.Errorf("apply migration %d: %w", i+1, err)
		}
		if _, err := db.Exec(`INSERT INTO schema_version (version) VALUES (?)`, i+1); err != nil {
			return fmt.Errorf("record migration %d: %w", i+1, err)
		}
	}

	return nil
}
