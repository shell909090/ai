package auth

import (
	"context"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"fmt"
)

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

func hashKey(key string) string {
	h := sha256.Sum256([]byte(key))
	return hex.EncodeToString(h[:])
}
