package approval

import (
	"database/sql"
	"fmt"
	"sync"
	"time"
)

// Engine manages the HITL approval flow.
// When approval is required, it creates a DB record, blocks on a channel,
// and returns once the request is approved or rejected via the web UI.
type Engine struct {
	db      *sql.DB
	pending sync.Map // map[int64]chan bool
}

func NewEngine(db *sql.DB) *Engine {
	return &Engine{db: db}
}

// CheckAndWait checks if the operation requires approval.
// If not, returns (true, nil) immediately.
// If yes, creates a request and blocks until resolved.
func (e *Engine) CheckAndWait(operationID, agentName, paramsJSON, reason string) (bool, error) {
	required, err := e.isRequired(operationID)
	if err != nil {
		return false, fmt.Errorf("check approval rule: %w", err)
	}
	if !required {
		return true, nil
	}

	// Create pending request
	result, err := e.db.Exec(
		`INSERT INTO approval_requests (operation_id, agent_name, params_json, reason, status)
		VALUES (?, ?, ?, ?, 'pending')`,
		operationID, agentName, paramsJSON, reason,
	)
	if err != nil {
		return false, fmt.Errorf("create approval request: %w", err)
	}

	reqID, err := result.LastInsertId()
	if err != nil {
		return false, fmt.Errorf("get request id: %w", err)
	}

	// Create channel and register in pending map
	ch := make(chan bool, 1)
	e.pending.Store(reqID, ch)
	defer e.pending.Delete(reqID)

	// Block until decision
	approved := <-ch
	return approved, nil
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

	// Unblock the waiting goroutine
	if ch, ok := e.pending.Load(reqID); ok {
		ch.(chan bool) <- approved
	}

	return nil
}

// GetPending returns all pending approval requests with enriched operation info.
func (e *Engine) GetPending() ([]Request, error) {
	rows, err := e.db.Query(`
		SELECT ar.id, ar.operation_id, ar.agent_name, ar.params_json, ar.reason,
			ar.status, ar.created_at,
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
			ar.status, ar.created_at,
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

func scanRequests(rows *sql.Rows) ([]Request, error) {
	var result []Request
	for rows.Next() {
		var r Request
		if err := rows.Scan(
			&r.ID, &r.OperationID, &r.AgentName, &r.ParamsJSON, &r.Reason,
			&r.Status, &r.CreatedAt,
			&r.Summary, &r.Description, &r.Method, &r.Path,
		); err != nil {
			return nil, fmt.Errorf("scan request: %w", err)
		}
		result = append(result, r)
	}
	return result, rows.Err()
}
