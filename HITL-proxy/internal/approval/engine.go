package approval

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"time"
)

// Engine manages the HITL approval flow.
// All state resides in SQLite. The handler goroutine polls the DB
// until the request reaches a terminal state.
type Engine struct {
	db             *sql.DB
	defaultTimeout time.Duration
	pollInterval   time.Duration
	hub            *SSEHub
}

func NewEngine(db *sql.DB, timeout, pollInterval time.Duration, hub *SSEHub) *Engine {
	return &Engine{
		db:             db,
		defaultTimeout: timeout,
		pollInterval:   pollInterval,
		hub:            hub,
	}
}

// CheckAndWait checks if the operation requires approval.
// If not, returns (true, nil) immediately.
// If yes, creates a request and polls the DB until resolved, cancelled, or expired.
func (e *Engine) CheckAndWait(ctx context.Context, operationID, agentName, paramsJSON, reason string) (bool, error) {
	required, err := e.isRequired(operationID)
	if err != nil {
		return false, fmt.Errorf("check approval rule: %w", err)
	}
	if !required {
		return true, nil
	}

	// Create pending request with timeout
	timeoutAt := time.Now().Add(e.defaultTimeout)
	result, err := e.db.Exec(
		`INSERT INTO approval_requests (operation_id, agent_name, params_json, reason, status, timeout_at)
		VALUES (?, ?, ?, ?, 'pending', ?)`,
		operationID, agentName, paramsJSON, reason, timeoutAt,
	)
	if err != nil {
		return false, fmt.Errorf("create approval request: %w", err)
	}

	reqID, err := result.LastInsertId()
	if err != nil {
		return false, fmt.Errorf("get request id: %w", err)
	}

	// Broadcast new request event
	e.hub.Broadcast(SSEEvent{Type: "new_request", ID: reqID})

	// Poll loop
	ticker := time.NewTicker(e.pollInterval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			// Agent disconnected or context cancelled
			if e.markCancelled(reqID) {
				e.hub.Broadcast(SSEEvent{Type: "decided", ID: reqID})
				return false, fmt.Errorf("approval cancelled: %w", ctx.Err())
			}
			// Lost the race — someone already decided. Read the result.
			status, err := e.getStatus(reqID)
			if err != nil {
				return false, fmt.Errorf("read status after cancel race: %w", err)
			}
			return status == "approved", nil

		case <-ticker.C:
			status, err := e.getStatus(reqID)
			if err != nil {
				return false, fmt.Errorf("poll status: %w", err)
			}
			switch status {
			case "pending":
				continue
			case "approved":
				return true, nil
			case "rejected":
				return false, nil
			case "expired":
				return false, fmt.Errorf("approval request expired")
			case "cancelled":
				return false, fmt.Errorf("approval request cancelled")
			default:
				return false, fmt.Errorf("unexpected approval status: %s", status)
			}
		}
	}
}

// Decide resolves a pending approval request.
func (e *Engine) Decide(reqID int64, approved bool, decidedBy string) error {
	status := "rejected"
	if approved {
		status = "approved"
	}

	now := time.Now()
	res, err := e.db.Exec(
		`UPDATE approval_requests SET status = ?, decided_at = ?, decided_by = ? WHERE id = ? AND status = 'pending'`,
		status, now, decidedBy, reqID,
	)
	if err != nil {
		return fmt.Errorf("update approval request: %w", err)
	}
	rows, _ := res.RowsAffected()
	if rows == 0 {
		return fmt.Errorf("request %d not found or already decided", reqID)
	}

	e.hub.Broadcast(SSEEvent{Type: "decided", ID: reqID})
	return nil
}

// CleanupOrphans marks all pending requests as expired.
// Called once at startup to handle records orphaned by a previous crash.
func (e *Engine) CleanupOrphans() error {
	res, err := e.db.Exec(`UPDATE approval_requests SET status = 'expired' WHERE status = 'pending'`)
	if err != nil {
		return fmt.Errorf("cleanup orphans: %w", err)
	}
	n, _ := res.RowsAffected()
	if n > 0 {
		log.Printf("cleaned up %d orphaned approval requests", n)
	}
	return nil
}

// StartBackgroundTimer runs a goroutine that periodically expires timed-out requests.
func (e *Engine) StartBackgroundTimer(ctx context.Context, scanInterval time.Duration) {
	go func() {
		ticker := time.NewTicker(scanInterval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
				e.expireTimedOut()
			}
		}
	}()
}

func (e *Engine) expireTimedOut() {
	res, err := e.db.Exec(
		`UPDATE approval_requests SET status = 'expired' WHERE status = 'pending' AND timeout_at <= ?`,
		time.Now(),
	)
	if err != nil {
		log.Printf("expire timed out requests: %v", err)
		return
	}
	n, _ := res.RowsAffected()
	if n > 0 {
		log.Printf("expired %d timed-out approval requests", n)
		e.hub.Broadcast(SSEEvent{Type: "expired"})
	}
}

// getStatus reads the current status of a request.
func (e *Engine) getStatus(reqID int64) (string, error) {
	var status string
	err := e.db.QueryRow(`SELECT status FROM approval_requests WHERE id = ?`, reqID).Scan(&status)
	if err != nil {
		return "", fmt.Errorf("get status: %w", err)
	}
	return status, nil
}

// markCancelled attempts to set a request to cancelled.
// Returns true if the row was updated, false if someone else already decided.
func (e *Engine) markCancelled(reqID int64) bool {
	res, err := e.db.Exec(
		`UPDATE approval_requests SET status = 'cancelled' WHERE id = ? AND status = 'pending'`,
		reqID,
	)
	if err != nil {
		log.Printf("mark cancelled: %v", err)
		return false
	}
	n, _ := res.RowsAffected()
	return n > 0
}

// GetPending returns all pending approval requests with enriched operation info.
func (e *Engine) GetPending() ([]Request, error) {
	rows, err := e.db.Query(`
		SELECT ar.id, ar.operation_id, ar.agent_name, ar.params_json, ar.reason,
			ar.status, ar.created_at, ar.timeout_at,
			COALESCE(o.summary, ''), COALESCE(o.description, ''),
			COALESCE(o.method, ''), COALESCE(o.path, '')
		FROM approval_requests ar
		LEFT JOIN operations o ON o.operation_id = ar.operation_id
		WHERE ar.status = 'pending'
		ORDER BY ar.created_at DESC
	`)
	if err != nil {
		return nil, fmt.Errorf("query pending: %w", err)
	}
	defer rows.Close()

	return scanRequests(rows)
}

// GetRequest returns a single approval request by ID.
func (e *Engine) GetRequest(id int64) (*Request, error) {
	rows, err := e.db.Query(`
		SELECT ar.id, ar.operation_id, ar.agent_name, ar.params_json, ar.reason,
			ar.status, ar.created_at, ar.timeout_at,
			COALESCE(o.summary, ''), COALESCE(o.description, ''),
			COALESCE(o.method, ''), COALESCE(o.path, '')
		FROM approval_requests ar
		LEFT JOIN operations o ON o.operation_id = ar.operation_id
		WHERE ar.id = ?
	`, id)
	if err != nil {
		return nil, fmt.Errorf("query request: %w", err)
	}
	defer rows.Close()

	reqs, err := scanRequests(rows)
	if err != nil {
		return nil, err
	}
	if len(reqs) == 0 {
		return nil, fmt.Errorf("request %d not found", id)
	}
	return &reqs[0], nil
}

func (e *Engine) isRequired(operationID string) (bool, error) {
	var required bool
	err := e.db.QueryRow(
		`SELECT required FROM approval_rules WHERE operation_id = ?`, operationID,
	).Scan(&required)
	if err == sql.ErrNoRows {
		return false, nil
	}
	return required, err
}

// SetRule creates or updates an approval rule.
func (e *Engine) SetRule(operationID string, required bool) error {
	_, err := e.db.Exec(
		`INSERT INTO approval_rules (operation_id, required) VALUES (?, ?)
		ON CONFLICT(operation_id) DO UPDATE SET required = excluded.required`,
		operationID, required,
	)
	return err
}

// RuleRow holds an operation and its current approval rule state.
type RuleRow struct {
	OperationID string
	SpecName    string
	Method      string
	Path        string
	Summary     string
	Required    bool
}

// ListRules returns all operations with their approval rule status (LEFT JOIN).
func (e *Engine) ListRules() ([]RuleRow, error) {
	rows, err := e.db.Query(`
		SELECT o.operation_id, s.name, o.method, o.path, COALESCE(o.summary, ''),
			COALESCE(ar.required, 0)
		FROM operations o
		JOIN specs s ON s.id = o.spec_id
		LEFT JOIN approval_rules ar ON ar.operation_id = o.operation_id
		ORDER BY s.name, o.path, o.method
	`)
	if err != nil {
		return nil, fmt.Errorf("query rules: %w", err)
	}
	defer rows.Close()

	var result []RuleRow
	for rows.Next() {
		var r RuleRow
		if err := rows.Scan(&r.OperationID, &r.SpecName, &r.Method, &r.Path, &r.Summary, &r.Required); err != nil {
			return nil, fmt.Errorf("scan rule: %w", err)
		}
		result = append(result, r)
	}
	return result, rows.Err()
}

func scanRequests(rows *sql.Rows) ([]Request, error) {
	var result []Request
	for rows.Next() {
		var r Request
		if err := rows.Scan(
			&r.ID, &r.OperationID, &r.AgentName, &r.ParamsJSON, &r.Reason,
			&r.Status, &r.CreatedAt, &r.TimeoutAt,
			&r.Summary, &r.Description, &r.Method, &r.Path,
		); err != nil {
			return nil, fmt.Errorf("scan request: %w", err)
		}
		result = append(result, r)
	}
	return result, rows.Err()
}
