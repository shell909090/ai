package audit

import (
	"path/filepath"
	"testing"

	"github.com/shell909090/ai/HITL-proxy/internal/database"
)

func TestLog_WritesRecord(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	l := NewLogger(db)

	entry := Entry{
		AgentName:      "agent1",
		OperationID:    "listPets",
		ParamsJSON:     `{"limit":10}`,
		Reason:         "test reason",
		ResponseStatus: 200,
		ResponseBody:   `[{"id":1}]`,
		ApprovalStatus: "approved",
		ErrorMessage:   "",
	}

	if err := l.Log(entry); err != nil {
		t.Fatalf("Log: %v", err)
	}

	// Verify the record is in the database.
	var (
		agentName      string
		operationID    string
		paramsJSON     string
		reason         string
		responseStatus int
		responseBody   string
		approvalStatus string
		errorMessage   string
	)
	row := db.QueryRow(`SELECT agent_name, operation_id, params_json, reason,
		response_status, response_body, approval_status, error_message
		FROM audit_log LIMIT 1`)
	if err := row.Scan(&agentName, &operationID, &paramsJSON, &reason,
		&responseStatus, &responseBody, &approvalStatus, &errorMessage); err != nil {
		t.Fatalf("scan audit_log: %v", err)
	}

	if agentName != entry.AgentName {
		t.Errorf("agent_name: want %q, got %q", entry.AgentName, agentName)
	}
	if operationID != entry.OperationID {
		t.Errorf("operation_id: want %q, got %q", entry.OperationID, operationID)
	}
	if paramsJSON != entry.ParamsJSON {
		t.Errorf("params_json: want %q, got %q", entry.ParamsJSON, paramsJSON)
	}
	if reason != entry.Reason {
		t.Errorf("reason: want %q, got %q", entry.Reason, reason)
	}
	if responseStatus != entry.ResponseStatus {
		t.Errorf("response_status: want %d, got %d", entry.ResponseStatus, responseStatus)
	}
	if responseBody != entry.ResponseBody {
		t.Errorf("response_body: want %q, got %q", entry.ResponseBody, responseBody)
	}
	if approvalStatus != entry.ApprovalStatus {
		t.Errorf("approval_status: want %q, got %q", entry.ApprovalStatus, approvalStatus)
	}
	if errorMessage != entry.ErrorMessage {
		t.Errorf("error_message: want %q, got %q", entry.ErrorMessage, errorMessage)
	}
}

func TestLog_MultipleEntries(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	l := NewLogger(db)

	for i := 0; i < 3; i++ {
		e := Entry{
			AgentName:      "agent",
			OperationID:    "op",
			ResponseStatus: 200,
			ApprovalStatus: "auto",
		}
		if err := l.Log(e); err != nil {
			t.Fatalf("Log entry %d: %v", i, err)
		}
	}

	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM audit_log`).Scan(&count); err != nil {
		t.Fatalf("count: %v", err)
	}
	if count != 3 {
		t.Errorf("expected 3 audit_log rows, got %d", count)
	}
}
