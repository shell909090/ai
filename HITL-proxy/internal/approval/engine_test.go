package approval

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/shell909090/ai/HITL-proxy/internal/database"
)

func newTestEngine(t *testing.T) *Engine {
	t.Helper()
	db, err := database.Open(filepath.Join(t.TempDir(), "approval_test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })

	hub := NewSSEHub()
	// Use short poll interval for tests; long default timeout so tests control decisions
	return NewEngine(db, 5*time.Minute, 10*time.Millisecond, hub)
}

// TestCheckAndWait_NotRequired verifies that when no rule is set (or required=false),
// CheckAndWait returns immediately with true.
func TestCheckAndWait_NotRequired(t *testing.T) {
	e := newTestEngine(t)

	if err := e.SetRule("op-no-approval", false); err != nil {
		t.Fatalf("SetRule: %v", err)
	}

	approved, err := e.CheckAndWait(context.Background(), "op-no-approval", "agent1", "{}", "test")
	if err != nil {
		t.Fatalf("CheckAndWait: %v", err)
	}
	if !approved {
		t.Error("expected immediate approval when required=false")
	}
}

// TestCheckAndWait_NoRule verifies that an operation with no rule at all
// also returns immediately with true (default not-required behavior).
func TestCheckAndWait_NoRule(t *testing.T) {
	e := newTestEngine(t)

	approved, err := e.CheckAndWait(context.Background(), "op-unknown", "agent1", "{}", "test")
	if err != nil {
		t.Fatalf("CheckAndWait: %v", err)
	}
	if !approved {
		t.Error("expected immediate approval when no rule exists")
	}
}

// TestCheckAndWait_RequiredThenApprove verifies the blocking/approve path.
func TestCheckAndWait_RequiredThenApprove(t *testing.T) {
	e := newTestEngine(t)

	if err := e.SetRule("op-approve", true); err != nil {
		t.Fatalf("SetRule: %v", err)
	}

	type result struct {
		approved bool
		err      error
	}
	ch := make(chan result, 1)

	go func() {
		approved, err := e.CheckAndWait(context.Background(), "op-approve", "agent1", "{}", "reason")
		ch <- result{approved, err}
	}()

	// Give the goroutine time to create the pending request
	time.Sleep(50 * time.Millisecond)

	pending, err := e.GetPending()
	if err != nil {
		t.Fatalf("GetPending: %v", err)
	}
	if len(pending) == 0 {
		t.Fatal("expected a pending request")
	}

	reqID := pending[0].ID
	if err := e.Decide(reqID, true, "tester"); err != nil {
		t.Fatalf("Decide approve: %v", err)
	}

	select {
	case r := <-ch:
		if r.err != nil {
			t.Fatalf("CheckAndWait error: %v", r.err)
		}
		if !r.approved {
			t.Error("expected approved=true after Decide approve")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for CheckAndWait to return")
	}
}

// TestCheckAndWait_RequiredThenReject verifies the blocking/reject path.
func TestCheckAndWait_RequiredThenReject(t *testing.T) {
	e := newTestEngine(t)

	if err := e.SetRule("op-reject", true); err != nil {
		t.Fatalf("SetRule: %v", err)
	}

	type result struct {
		approved bool
		err      error
	}
	ch := make(chan result, 1)

	go func() {
		approved, err := e.CheckAndWait(context.Background(), "op-reject", "agent1", "{}", "reason")
		ch <- result{approved, err}
	}()

	time.Sleep(50 * time.Millisecond)

	pending, err := e.GetPending()
	if err != nil {
		t.Fatalf("GetPending: %v", err)
	}
	if len(pending) == 0 {
		t.Fatal("expected a pending request")
	}

	reqID := pending[0].ID
	if err := e.Decide(reqID, false, "tester"); err != nil {
		t.Fatalf("Decide reject: %v", err)
	}

	select {
	case r := <-ch:
		if r.err != nil {
			t.Fatalf("CheckAndWait error: %v", r.err)
		}
		if r.approved {
			t.Error("expected approved=false after Decide reject")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for CheckAndWait to return")
	}
}

// TestDecide_NotFoundError verifies Decide returns an error for a non-existent ID.
func TestDecide_NotFoundError(t *testing.T) {
	e := newTestEngine(t)

	err := e.Decide(99999, true, "tester")
	if err == nil {
		t.Error("expected error for non-existent request ID")
	}
}

// TestDecide_AlreadyDecidedError verifies Decide returns an error when called twice.
func TestDecide_AlreadyDecidedError(t *testing.T) {
	e := newTestEngine(t)

	if err := e.SetRule("op-double-decide", true); err != nil {
		t.Fatalf("SetRule: %v", err)
	}

	ch := make(chan struct{}, 1)
	go func() {
		_, _ = e.CheckAndWait(context.Background(), "op-double-decide", "agent1", "{}", "")
		ch <- struct{}{}
	}()

	time.Sleep(50 * time.Millisecond)

	pending, err := e.GetPending()
	if err != nil || len(pending) == 0 {
		t.Fatal("expected pending request")
	}
	reqID := pending[0].ID

	// First decision should succeed
	if err := e.Decide(reqID, true, "tester"); err != nil {
		t.Fatalf("first Decide: %v", err)
	}
	<-ch

	// Second decision should fail
	if err := e.Decide(reqID, true, "tester"); err == nil {
		t.Error("expected error for already-decided request")
	}
}

// TestGetPending verifies that GetPending returns the pending requests.
func TestGetPending_ReturnsPendingList(t *testing.T) {
	e := newTestEngine(t)

	// With required=true, CheckAndWait will block and leave a pending record
	if err := e.SetRule("op-pending", true); err != nil {
		t.Fatalf("SetRule: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{}, 1)
	go func() {
		_, _ = e.CheckAndWait(ctx, "op-pending", "agentX", `{"key":"val"}`, "testing pending")
		done <- struct{}{}
	}()

	time.Sleep(50 * time.Millisecond)

	pending, err := e.GetPending()
	if err != nil {
		t.Fatalf("GetPending: %v", err)
	}
	if len(pending) == 0 {
		t.Fatal("expected at least one pending request")
	}

	found := false
	for _, r := range pending {
		if r.OperationID == "op-pending" && r.Status == "pending" {
			found = true
			break
		}
	}
	if !found {
		t.Errorf("pending request for op-pending not found; got %+v", pending)
	}

	// Cancel to unblock the goroutine
	cancel()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for goroutine cleanup")
	}
}

// TestCleanupOrphans verifies that pending requests are marked expired.
func TestCleanupOrphans(t *testing.T) {
	e := newTestEngine(t)

	if err := e.SetRule("op-orphan", true); err != nil {
		t.Fatalf("SetRule: %v", err)
	}

	ctx, cancel := context.WithCancel(context.Background())
	done := make(chan struct{}, 1)
	go func() {
		_, _ = e.CheckAndWait(ctx, "op-orphan", "agentY", "{}", "orphan test")
		done <- struct{}{}
	}()

	time.Sleep(50 * time.Millisecond)

	// Cancel to release the goroutine before CleanupOrphans
	cancel()
	select {
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("timed out waiting for goroutine cleanup")
	}

	// Insert a fresh pending request directly to simulate an orphan
	_, err := e.db.Exec(
		`INSERT INTO approval_requests (operation_id, agent_name, params_json, reason, status)
		 VALUES ('op-orphan', 'agentZ', '{}', 'orphan', 'pending')`,
	)
	if err != nil {
		t.Fatalf("insert orphan: %v", err)
	}

	if err := e.CleanupOrphans(); err != nil {
		t.Fatalf("CleanupOrphans: %v", err)
	}

	pending, err := e.GetPending()
	if err != nil {
		t.Fatalf("GetPending after cleanup: %v", err)
	}
	for _, r := range pending {
		if r.OperationID == "op-orphan" {
			t.Errorf("expected op-orphan to be cleaned up, but it is still pending: %+v", r)
		}
	}
}

// TestListRules verifies ListRules returns the correct rule state when operations exist.
func TestListRules_WithOperations(t *testing.T) {
	e := newTestEngine(t)

	// Insert a spec and operation so ListRules can return something
	res, err := e.db.Exec(`INSERT INTO specs (name, raw_json) VALUES ('svc', '{}')`)
	if err != nil {
		t.Fatalf("insert spec: %v", err)
	}
	specID, _ := res.LastInsertId()

	_, err = e.db.Exec(
		`INSERT INTO operations (spec_id, operation_id, method, path, summary) VALUES (?, 'doThing', 'POST', '/things', 'Do a thing')`,
		specID,
	)
	if err != nil {
		t.Fatalf("insert operation: %v", err)
	}

	// Set an approval rule for it
	if err := e.SetRule("doThing", true); err != nil {
		t.Fatalf("SetRule: %v", err)
	}

	rules, err := e.ListRules()
	if err != nil {
		t.Fatalf("ListRules: %v", err)
	}
	if len(rules) == 0 {
		t.Fatal("expected at least one rule")
	}

	found := false
	for _, r := range rules {
		if r.OperationID == "doThing" {
			found = true
			if !r.Required {
				t.Error("expected Required=true for doThing")
			}
			if r.Method != "POST" {
				t.Errorf("expected Method=POST, got %s", r.Method)
			}
			if r.SpecName != "svc" {
				t.Errorf("expected SpecName=svc, got %s", r.SpecName)
			}
		}
	}
	if !found {
		t.Errorf("doThing not found in ListRules: %+v", rules)
	}
}

// TestListRules_NoOperations verifies ListRules returns empty slice when no operations exist.
func TestListRules_NoOperations(t *testing.T) {
	e := newTestEngine(t)

	rules, err := e.ListRules()
	if err != nil {
		t.Fatalf("ListRules: %v", err)
	}
	if len(rules) != 0 {
		t.Errorf("expected 0 rules with no operations, got %d", len(rules))
	}
}

// TestSetRule_UpdateExisting verifies that SetRule updates an existing rule.
func TestSetRule_UpdateExisting(t *testing.T) {
	e := newTestEngine(t)

	if err := e.SetRule("op-update", true); err != nil {
		t.Fatalf("SetRule true: %v", err)
	}

	// Confirm it's required
	required, err := e.isRequired("op-update")
	if err != nil {
		t.Fatalf("isRequired: %v", err)
	}
	if !required {
		t.Error("expected required=true")
	}

	// Now set to false
	if err := e.SetRule("op-update", false); err != nil {
		t.Fatalf("SetRule false: %v", err)
	}

	required, err = e.isRequired("op-update")
	if err != nil {
		t.Fatalf("isRequired after update: %v", err)
	}
	if required {
		t.Error("expected required=false after update")
	}
}
