package authz

import (
	"database/sql"
	"fmt"
)

// Checker implements per-operationId authorization.
type Checker struct {
	db           *sql.DB
	defaultAllow bool
}

func NewChecker(db *sql.DB, defaultAllow bool) *Checker {
	return &Checker{db: db, defaultAllow: defaultAllow}
}

// Check returns whether the agent is allowed to call the operation.
// If no explicit rule exists, returns the default policy.
func (c *Checker) Check(agentName, operationID string) (bool, error) {
	var allowed bool
	err := c.db.QueryRow(
		`SELECT allowed FROM authz_rules WHERE agent_name = ? AND operation_id = ?`,
		agentName, operationID,
	).Scan(&allowed)
	if err == sql.ErrNoRows {
		return c.defaultAllow, nil
	}
	if err != nil {
		return false, fmt.Errorf("query authz_rules: %w", err)
	}
	return allowed, nil
}

// SetRule creates or updates an authorization rule.
func (c *Checker) SetRule(agentName, operationID string, allowed bool) error {
	_, err := c.db.Exec(
		`INSERT INTO authz_rules (agent_name, operation_id, allowed) VALUES (?, ?, ?)
		ON CONFLICT(agent_name, operation_id) DO UPDATE SET allowed = excluded.allowed`,
		agentName, operationID, allowed,
	)
	if err != nil {
		return fmt.Errorf("upsert authz_rule: %w", err)
	}
	return nil
}
