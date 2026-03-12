package approval

import "time"

// Request represents an approval request.
type Request struct {
	ID          int64      `json:"id"`
	OperationID string     `json:"operation_id"`
	AgentName   string     `json:"agent_name"`
	ParamsJSON  string     `json:"params_json"`
	Reason      string     `json:"reason"`
	Status      string     `json:"status"`
	DecidedAt   *time.Time `json:"decided_at,omitempty"`
	DecidedBy   string     `json:"decided_by,omitempty"`
	CreatedAt   time.Time  `json:"created_at"`
	TimeoutAt   *time.Time `json:"timeout_at,omitempty"`

	// Enriched fields from OpenAPI spec (for display)
	Summary     string `json:"summary,omitempty"`
	Description string `json:"description,omitempty"`
	Method      string `json:"method,omitempty"`
	Path        string `json:"path,omitempty"`
}
