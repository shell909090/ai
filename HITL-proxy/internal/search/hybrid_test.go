package search

import (
	"context"
	"database/sql"
	"errors"
	"path/filepath"
	"testing"

	"github.com/shell909090/ai/HITL-proxy/internal/database"
	"github.com/shell909090/ai/HITL-proxy/internal/openapi"
)

// mockEmbedder returns a fixed vector for any input.
type mockEmbedder struct{ vec []float32 }

func (m *mockEmbedder) Embed(_ context.Context, _ string) ([]float32, error) {
	return m.vec, nil
}
func (m *mockEmbedder) Model() string { return "mock" }

// failEmbedder always returns an error.
type failEmbedder struct{}

func (f *failEmbedder) Embed(_ context.Context, _ string) ([]float32, error) {
	return nil, errors.New("embed error")
}
func (f *failEmbedder) Model() string { return "fail" }

// mockVectorStore stores items in memory and returns them for any query.
type mockVectorStore struct {
	items []VectorItem
}

func (m *mockVectorStore) Upsert(_ context.Context, items []VectorItem) error {
	m.items = append(m.items, items...)
	return nil
}

func (m *mockVectorStore) DeleteBySpec(_ context.Context, specID int64) error {
	filtered := m.items[:0]
	for _, it := range m.items {
		if it.SpecID != specID {
			filtered = append(filtered, it)
		}
	}
	m.items = filtered
	return nil
}

func (m *mockVectorStore) Search(_ context.Context, _ []float32, limit int) ([]VectorResult, error) {
	var results []VectorResult
	for i, it := range m.items {
		if i >= limit {
			break
		}
		results = append(results, VectorResult{OperationID: it.OperationID, Score: 0.9})
	}
	return results, nil
}

func TestHybridSearcher_NilVec_SearchDelegatesToFTS5(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	// Insert a spec
	res, err := db.Exec(`INSERT INTO specs (name, raw_json) VALUES ('test', '{}')`)
	if err != nil {
		t.Fatalf("insert spec: %v", err)
	}
	specID, _ := res.LastInsertId()

	fts := NewFTS5Searcher(db)
	ops := []openapi.Operation{
		{
			SpecID:          specID,
			OperationID:     "listUsers",
			Method:          "GET",
			Path:            "/users",
			Summary:         "List users",
			Description:     "Returns all users",
			ParametersJSON:  "[]",
			RequestBodyJSON: "{}",
			Tags:            "users",
		},
	}
	if _, err := fts.Index(ops, nil, specID, "test"); err != nil {
		t.Fatalf("fts index: %v", err)
	}

	hybrid := NewHybridSearcher(db, nil)

	ctx := context.Background()
	got, err := hybrid.Search(ctx, "users", 10)
	if err != nil {
		t.Fatalf("hybrid search: %v", err)
	}
	if len(got) == 0 {
		t.Fatal("expected at least one result from hybrid search with vec=nil")
	}
	if got[0].Operation.OperationID != "listUsers" {
		t.Errorf("expected listUsers, got %s", got[0].Operation.OperationID)
	}
}

func TestHybridSearcher_NilVec_IndexDelegatesToFTS5(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	res, err := db.Exec(`INSERT INTO specs (name, raw_json) VALUES ('myspec', '{}')`)
	if err != nil {
		t.Fatalf("insert spec: %v", err)
	}
	specID, _ := res.LastInsertId()

	hybrid := NewHybridSearcher(db, nil)

	ops := []openapi.Operation{
		{
			SpecID:          specID,
			OperationID:     "getWidget",
			Method:          "GET",
			Path:            "/widgets/{id}",
			Summary:         "Get widget",
			Description:     "Returns a single widget",
			ParametersJSON:  "[]",
			RequestBodyJSON: "{}",
			Tags:            "widgets",
		},
	}

	prefixed, err := hybrid.Index(ops, nil, specID, "myspec")
	if err != nil {
		t.Fatalf("hybrid index: %v", err)
	}
	if prefixed {
		t.Error("expected no prefix for first import")
	}

	// Verify the row was inserted into SQLite
	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM operations WHERE operation_id = 'getWidget'`).Scan(&count); err != nil {
		t.Fatalf("query: %v", err)
	}
	if count != 1 {
		t.Errorf("expected 1 row, got %d", count)
	}
}

func TestHybridSearcher_NilVec_IndexTxDelegatesToFTS5(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	res, err := db.Exec(`INSERT INTO specs (name, raw_json) VALUES ('txspec', '{}')`)
	if err != nil {
		t.Fatalf("insert spec: %v", err)
	}
	specID, _ := res.LastInsertId()

	hybrid := NewHybridSearcher(db, nil)

	tx, err := db.Begin()
	if err != nil {
		t.Fatalf("begin tx: %v", err)
	}

	ops := []openapi.Operation{
		{
			SpecID:          specID,
			OperationID:     "createWidget",
			Method:          "POST",
			Path:            "/widgets",
			Summary:         "Create widget",
			Description:     "Creates a new widget",
			ParametersJSON:  "[]",
			RequestBodyJSON: "{}",
			Tags:            "widgets",
		},
	}

	prefixed, err := hybrid.IndexTx(tx, ops, nil, specID, "txspec")
	if err != nil {
		t.Fatalf("hybrid IndexTx: %v", err)
	}
	if prefixed {
		t.Error("expected no prefix for first import")
	}

	if err := tx.Commit(); err != nil {
		t.Fatalf("commit: %v", err)
	}

	var count int
	if err := db.QueryRow(`SELECT COUNT(*) FROM operations WHERE operation_id = 'createWidget'`).Scan(&count); err != nil {
		t.Fatalf("query: %v", err)
	}
	if count != 1 {
		t.Errorf("expected 1 row, got %d", count)
	}
}

func TestHybridSearcher_NilVec_IndexEmbeddingsIsNoop(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	hybrid := NewHybridSearcher(db, nil)
	ops := []openapi.Operation{{OperationID: "op1"}}
	if err := hybrid.IndexEmbeddings(context.Background(), ops, 1); err != nil {
		t.Errorf("IndexEmbeddings with nil vec should be a no-op, got: %v", err)
	}
}

func TestHybridSearcher_NilVec_DeleteSpecEmbeddingsIsNoop(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	hybrid := NewHybridSearcher(db, nil)
	if err := hybrid.DeleteSpecEmbeddings(context.Background(), 42); err != nil {
		t.Errorf("DeleteSpecEmbeddings with nil vec should be a no-op, got: %v", err)
	}
}

func TestOperationText(t *testing.T) {
	op := openapi.Operation{
		OperationID: "listRepos",
		Summary:     "List repositories",
		Description: "Returns all repos",
		Tags:        "repos",
	}
	got := operationText(op)
	for _, want := range []string{"listRepos", "List repositories", "Returns all repos", "repos"} {
		if !containsStr(got, want) {
			t.Errorf("operationText missing %q in %q", want, got)
		}
	}
}

func containsStr(s, sub string) bool {
	return len(s) >= len(sub) && (s == sub || len(sub) == 0 ||
		func() bool {
			for i := 0; i <= len(s)-len(sub); i++ {
				if s[i:i+len(sub)] == sub {
					return true
				}
			}
			return false
		}())
}

func setupHybridWithOps(t *testing.T) (*sql.DB, int64) {
	t.Helper()
	db, err := database.Open(filepath.Join(t.TempDir(), "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })

	res, err := db.Exec(`INSERT INTO specs (name, raw_json) VALUES ('test', '{}')`)
	if err != nil {
		t.Fatalf("insert spec: %v", err)
	}
	specID, _ := res.LastInsertId()

	ops := []openapi.Operation{
		{
			SpecID: specID, OperationID: "listUsers", Method: "GET",
			Path: "/users", Summary: "List users", Description: "All users",
			ParametersJSON: "[]", RequestBodyJSON: "{}",
		},
	}
	fts := NewFTS5Searcher(db)
	if _, err := fts.Index(ops, nil, specID, "test"); err != nil {
		t.Fatalf("index: %v", err)
	}
	return db, specID
}

func TestHybridSearcher_WithVec_Search(t *testing.T) {
	db, specID := setupHybridWithOps(t)

	store := &mockVectorStore{}
	store.items = []VectorItem{{OperationID: "listUsers", SpecID: specID, Embedding: []float32{0.1}}}

	vec := NewVectorSearcher(&mockEmbedder{vec: []float32{0.1}}, store)
	hybrid := NewHybridSearcher(db, vec)

	results, err := hybrid.Search(context.Background(), "users", 10)
	if err != nil {
		t.Fatalf("Search: %v", err)
	}
	if len(results) == 0 {
		t.Fatal("expected results")
	}
	if results[0].Operation.OperationID != "listUsers" {
		t.Errorf("want listUsers, got %s", results[0].Operation.OperationID)
	}
}

func TestHybridSearcher_WithVec_EmbedFails_FallsBackToFTS5(t *testing.T) {
	db, _ := setupHybridWithOps(t)

	store := &mockVectorStore{}
	vec := NewVectorSearcher(&failEmbedder{}, store)
	hybrid := NewHybridSearcher(db, vec)

	results, err := hybrid.Search(context.Background(), "users", 10)
	if err != nil {
		t.Fatalf("Search should not error on embed failure: %v", err)
	}
	if len(results) == 0 {
		t.Fatal("expected fallback FTS5 results")
	}
}

func TestHybridSearcher_IndexEmbeddings_WithVec(t *testing.T) {
	db, specID := setupHybridWithOps(t)

	store := &mockVectorStore{}
	vec := NewVectorSearcher(&mockEmbedder{vec: []float32{0.5, 0.5}}, store)
	hybrid := NewHybridSearcher(db, vec)

	ops := []openapi.Operation{
		{SpecID: specID, OperationID: "listUsers", Summary: "List users"},
	}
	if err := hybrid.IndexEmbeddings(context.Background(), ops, specID); err != nil {
		t.Fatalf("IndexEmbeddings: %v", err)
	}
	if len(store.items) == 0 {
		t.Error("expected items in vector store after IndexEmbeddings")
	}
}

func TestHybridSearcher_DeleteSpecEmbeddings_WithVec(t *testing.T) {
	db, specID := setupHybridWithOps(t)

	store := &mockVectorStore{items: []VectorItem{
		{OperationID: "listUsers", SpecID: specID},
	}}
	vec := NewVectorSearcher(&mockEmbedder{vec: []float32{0.1}}, store)
	hybrid := NewHybridSearcher(db, vec)

	if err := hybrid.DeleteSpecEmbeddings(context.Background(), specID); err != nil {
		t.Fatalf("DeleteSpecEmbeddings: %v", err)
	}
	if len(store.items) != 0 {
		t.Errorf("expected empty store after delete, got %d items", len(store.items))
	}
}

func TestFetchOperationsByIDs_Empty(t *testing.T) {
	db, _ := setupHybridWithOps(t)
	ops, err := fetchOperationsByIDs(db, nil)
	if err != nil {
		t.Fatalf("fetchOperationsByIDs(nil): %v", err)
	}
	if ops != nil {
		t.Errorf("expected nil result for empty ids, got %v", ops)
	}
}

func TestFetchOperationsByIDs_Found(t *testing.T) {
	db, _ := setupHybridWithOps(t)
	ops, err := fetchOperationsByIDs(db, []string{"listUsers"})
	if err != nil {
		t.Fatalf("fetchOperationsByIDs: %v", err)
	}
	if len(ops) != 1 || ops[0].OperationID != "listUsers" {
		t.Errorf("expected listUsers, got %v", ops)
	}
}
