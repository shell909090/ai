package audit

import (
	"database/sql"
	"fmt"
)

// Logger writes audit entries to SQLite.
type Logger struct {
	db *sql.DB
}

func NewLogger(db *sql.DB) *Logger {
	return &Logger{db: db}
}

// Entry represents an audit log entry.
type Entry struct {
	AgentName      string
	OperationID    string
	ParamsJSON     string
	Reason         string
	ResponseStatus int
	ResponseBody   string
	ApprovalStatus string
	ErrorMessage   string
}

// Log writes an audit entry.
func (l *Logger) Log(e Entry) error {
	_, err := l.db.Exec(`INSERT INTO audit_log
		(agent_name, operation_id, params_json, reason, response_status, response_body, approval_status, error_message)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
		e.AgentName, e.OperationID, e.ParamsJSON, e.Reason,
		e.ResponseStatus, e.ResponseBody, e.ApprovalStatus, e.ErrorMessage,
	)
	if err != nil {
		return fmt.Errorf("write audit log: %w", err)
	}
	return nil
}
