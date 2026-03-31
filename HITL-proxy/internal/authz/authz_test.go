package authz

import (
	"path/filepath"
	"testing"

	"github.com/shell909090/ai/HITL-proxy/internal/database"
)

func newTestChecker(t *testing.T, defaultAllow bool) *Checker {
	t.Helper()
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })
	return NewChecker(db, defaultAllow)
}

func TestCheck_NoRule_DefaultAllow(t *testing.T) {
	c := newTestChecker(t, true)

	allowed, err := c.Check("agentA", "listPets")
	if err != nil {
		t.Fatalf("check: %v", err)
	}
	if !allowed {
		t.Error("expected allowed=true with defaultAllow=true and no rule")
	}
}

func TestCheck_NoRule_DefaultDeny(t *testing.T) {
	c := newTestChecker(t, false)

	allowed, err := c.Check("agentA", "listPets")
	if err != nil {
		t.Fatalf("check: %v", err)
	}
	if allowed {
		t.Error("expected allowed=false with defaultAllow=false and no rule")
	}
}

func TestSetRule_ExplicitAllow_OverridesDefaultDeny(t *testing.T) {
	c := newTestChecker(t, false)

	if err := c.SetRule("agentA", "listPets", true); err != nil {
		t.Fatalf("set rule: %v", err)
	}

	allowed, err := c.Check("agentA", "listPets")
	if err != nil {
		t.Fatalf("check: %v", err)
	}
	if !allowed {
		t.Error("expected allowed=true after explicit allow rule")
	}
}

func TestSetRule_ExplicitDeny_OverridesDefaultAllow(t *testing.T) {
	c := newTestChecker(t, true)

	if err := c.SetRule("agentB", "deletePet", false); err != nil {
		t.Fatalf("set rule: %v", err)
	}

	allowed, err := c.Check("agentB", "deletePet")
	if err != nil {
		t.Fatalf("check: %v", err)
	}
	if allowed {
		t.Error("expected allowed=false after explicit deny rule")
	}
}

func TestSetRule_Upsert(t *testing.T) {
	c := newTestChecker(t, false)

	// First set to allow.
	if err := c.SetRule("agentC", "createPet", true); err != nil {
		t.Fatalf("set rule (allow): %v", err)
	}
	allowed, err := c.Check("agentC", "createPet")
	if err != nil {
		t.Fatalf("check after allow: %v", err)
	}
	if !allowed {
		t.Error("expected allowed=true")
	}

	// Then update to deny.
	if err := c.SetRule("agentC", "createPet", false); err != nil {
		t.Fatalf("set rule (deny): %v", err)
	}
	allowed, err = c.Check("agentC", "createPet")
	if err != nil {
		t.Fatalf("check after deny: %v", err)
	}
	if allowed {
		t.Error("expected allowed=false after upsert to deny")
	}
}

func TestCheck_RuleIsolatedPerAgent(t *testing.T) {
	c := newTestChecker(t, false)

	if err := c.SetRule("agentX", "listPets", true); err != nil {
		t.Fatalf("set rule: %v", err)
	}

	// agentY has no rule — should fall back to defaultAllow=false.
	allowed, err := c.Check("agentY", "listPets")
	if err != nil {
		t.Fatalf("check agentY: %v", err)
	}
	if allowed {
		t.Error("expected agentY denied when only agentX has explicit allow")
	}
}
