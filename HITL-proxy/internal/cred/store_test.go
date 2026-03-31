package cred

import (
	"path/filepath"
	"sync"
	"testing"
)

var testKey = []byte("12345678901234567890123456789012") // 32 bytes

func TestNewStore_KeyTooShort(t *testing.T) {
	dir := t.TempDir()
	_, err := NewStore(filepath.Join(dir, "creds.enc"), []byte("short"))
	if err == nil {
		t.Fatal("expected error for short key, got nil")
	}
}

func TestNewStore_KeyTooLong(t *testing.T) {
	dir := t.TempDir()
	// 32 bytes exactly is valid — make a genuinely 33-byte key.
	longKey := make([]byte, 33)
	_, err := NewStore(filepath.Join(dir, "creds.enc"), longKey)
	if err == nil {
		t.Fatal("expected error for 33-byte key, got nil")
	}
}

func TestSetGet(t *testing.T) {
	dir := t.TempDir()
	s, err := NewStore(filepath.Join(dir, "creds.enc"), testKey)
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}

	creds := map[string]string{"Authorization": "Bearer tok123", "X-Api-Version": "v2"}
	if err := s.Set("myspec", creds); err != nil {
		t.Fatalf("Set: %v", err)
	}

	got, ok := s.Get("myspec")
	if !ok {
		t.Fatal("Get: expected ok=true")
	}
	for k, want := range creds {
		if got[k] != want {
			t.Errorf("cred[%q]: want %q, got %q", k, want, got[k])
		}
	}
}

func TestGet_Missing(t *testing.T) {
	dir := t.TempDir()
	s, err := NewStore(filepath.Join(dir, "creds.enc"), testKey)
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}

	_, ok := s.Get("nonexistent")
	if ok {
		t.Error("expected ok=false for missing spec")
	}
}

func TestSetDeleteGet(t *testing.T) {
	dir := t.TempDir()
	s, err := NewStore(filepath.Join(dir, "creds.enc"), testKey)
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}

	creds := map[string]string{"key": "value"}
	if err := s.Set("spec1", creds); err != nil {
		t.Fatalf("Set: %v", err)
	}
	if err := s.Delete("spec1"); err != nil {
		t.Fatalf("Delete: %v", err)
	}

	_, ok := s.Get("spec1")
	if ok {
		t.Error("expected ok=false after Delete")
	}
}

func TestPersistence(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, "creds.enc")

	// Write with first store instance.
	s1, err := NewStore(path, testKey)
	if err != nil {
		t.Fatalf("NewStore (s1): %v", err)
	}
	creds := map[string]string{"token": "secret-value"}
	if err := s1.Set("persistent-spec", creds); err != nil {
		t.Fatalf("Set: %v", err)
	}

	// Open a new store from the same file.
	s2, err := NewStore(path, testKey)
	if err != nil {
		t.Fatalf("NewStore (s2): %v", err)
	}

	got, ok := s2.Get("persistent-spec")
	if !ok {
		t.Fatal("Get after reopen: expected ok=true")
	}
	if got["token"] != "secret-value" {
		t.Errorf("token: want %q, got %q", "secret-value", got["token"])
	}
}

func TestConcurrentAccess(t *testing.T) {
	dir := t.TempDir()
	s, err := NewStore(filepath.Join(dir, "creds.enc"), testKey)
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}

	const goroutines = 20
	var wg sync.WaitGroup
	wg.Add(goroutines)

	for i := 0; i < goroutines; i++ {
		go func(i int) {
			defer wg.Done()
			creds := map[string]string{"k": "v"}
			// Alternate between Set and Get.
			if i%2 == 0 {
				_ = s.Set("spec", creds)
			} else {
				_, _ = s.Get("spec")
			}
		}(i)
	}

	wg.Wait()
	// No panic or data race — success.
}

func TestSet_IsolatesSpecs(t *testing.T) {
	dir := t.TempDir()
	s, err := NewStore(filepath.Join(dir, "creds.enc"), testKey)
	if err != nil {
		t.Fatalf("NewStore: %v", err)
	}

	if err := s.Set("spec-a", map[string]string{"header": "valueA"}); err != nil {
		t.Fatalf("Set spec-a: %v", err)
	}
	if err := s.Set("spec-b", map[string]string{"header": "valueB"}); err != nil {
		t.Fatalf("Set spec-b: %v", err)
	}

	a, okA := s.Get("spec-a")
	b, okB := s.Get("spec-b")
	if !okA || !okB {
		t.Fatal("expected both specs to be present")
	}
	if a["header"] != "valueA" {
		t.Errorf("spec-a header: want valueA, got %q", a["header"])
	}
	if b["header"] != "valueB" {
		t.Errorf("spec-b header: want valueB, got %q", b["header"])
	}
}
