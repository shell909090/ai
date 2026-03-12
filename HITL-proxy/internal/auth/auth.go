package auth

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"fmt"
	"time"
)

// APIKey holds non-secret metadata about a stored key.
type APIKey struct {
	ID        int64
	AgentName string
	CreatedAt time.Time
}

type contextKey int

const agentNameKey contextKey = iota

// ContextWithAgent returns a new context carrying the agent name.
func ContextWithAgent(ctx context.Context, agentName string) context.Context {
	return context.WithValue(ctx, agentNameKey, agentName)
}

// AgentFromContext extracts the agent name from ctx.
func AgentFromContext(ctx context.Context) (string, bool) {
	name, ok := ctx.Value(agentNameKey).(string)
	return name, ok
}

// Authenticator validates API keys and resolves agent names.
type Authenticator struct {
	db *sql.DB
}

func NewAuthenticator(db *sql.DB) *Authenticator {
	return &Authenticator{db: db}
}

// Validate checks the API key and returns the agent name.
func (a *Authenticator) Validate(apiKey string) (string, error) {
	hash := hashKey(apiKey)
	var agentName string
	err := a.db.QueryRow(
		`SELECT agent_name FROM api_keys WHERE key_hash = ?`, hash,
	).Scan(&agentName)
	if err == sql.ErrNoRows {
		return "", fmt.Errorf("invalid API key")
	}
	if err != nil {
		return "", fmt.Errorf("query api_keys: %w", err)
	}
	return agentName, nil
}

// CreateKey stores a new API key for an agent.
func (a *Authenticator) CreateKey(apiKey, agentName string) error {
	hash := hashKey(apiKey)
	_, err := a.db.Exec(
		`INSERT INTO api_keys (key_hash, agent_name) VALUES (?, ?)`,
		hash, agentName,
	)
	if err != nil {
		return fmt.Errorf("insert api_key: %w", err)
	}
	return nil
}

// ListKeys returns all API keys (without hashes), newest first.
func (a *Authenticator) ListKeys() ([]APIKey, error) {
	rows, err := a.db.Query(`SELECT id, agent_name, created_at FROM api_keys ORDER BY created_at DESC`)
	if err != nil {
		return nil, fmt.Errorf("query api_keys: %w", err)
	}
	defer rows.Close()

	var keys []APIKey
	for rows.Next() {
		var k APIKey
		if err := rows.Scan(&k.ID, &k.AgentName, &k.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan api_key: %w", err)
		}
		keys = append(keys, k)
	}
	return keys, rows.Err()
}

// DeleteKey removes an API key by ID.
func (a *Authenticator) DeleteKey(id int64) error {
	_, err := a.db.Exec(`DELETE FROM api_keys WHERE id = ?`, id)
	if err != nil {
		return fmt.Errorf("delete api_key: %w", err)
	}
	return nil
}

func hashKey(key string) string {
	h := sha256.Sum256([]byte(key))
	return hex.EncodeToString(h[:])
}
