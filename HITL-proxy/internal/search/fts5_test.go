package search

import (
	"context"
	"path/filepath"
	"testing"

	"github.com/shell909090/ai/HITL-proxy/internal/database"
	"github.com/shell909090/ai/HITL-proxy/internal/openapi"
)

func TestFTS5SearcherIndexAndSearch(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	// Insert a spec first
	result, err := db.Exec(`INSERT INTO specs (name, raw_json) VALUES ('test', '{}')`)
	if err != nil {
		t.Fatalf("insert spec: %v", err)
	}
	specID, _ := result.LastInsertId()

	searcher := NewFTS5Searcher(db)

	ops := []openapi.Operation{
		{
			SpecID:          specID,
			OperationID:     "listRepos",
			Method:          "GET",
			Path:            "/repos",
			Summary:         "List all repositories",
			Description:     "Returns a list of repositories for the authenticated user",
			ParametersJSON:  "[]",
			RequestBodyJSON: "{}",
			Tags:            "repos",
		},
		{
			SpecID:          specID,
			OperationID:     "getRepo",
			Method:          "GET",
			Path:            "/repos/{owner}/{repo}",
			Summary:         "Get a repository",
			Description:     "Returns details of a specific repository",
			ParametersJSON:  "[]",
			RequestBodyJSON: "{}",
			Tags:            "repos",
		},
		{
			SpecID:          specID,
			OperationID:     "createIssue",
			Method:          "POST",
			Path:            "/repos/{owner}/{repo}/issues",
			Summary:         "Create an issue",
			Description:     "Creates a new issue in the specified repository",
			ParametersJSON:  "[]",
			RequestBodyJSON: "{}",
			Tags:            "issues",
		},
	}

	deps := []openapi.Dependency{
		{OperationID: "getRepo", DependsOnID: "listRepos", Reason: "needs repo from list"},
	}

	prefixed, err := searcher.Index(ops, deps, specID, "test")
	if err != nil {
		t.Fatalf("index: %v", err)
	}
	if prefixed {
		t.Error("expected no prefix for first import")
	}

	// Search for repositories
	results, err := searcher.Search(context.Background(), "repository", 10)
	if err != nil {
		t.Fatalf("search: %v", err)
	}

	if len(results) < 2 {
		t.Fatalf("expected at least 2 results, got %d", len(results))
	}

	// Search for issues
	results, err = searcher.Search(context.Background(), "issue", 10)
	if err != nil {
		t.Fatalf("search issues: %v", err)
	}

	if len(results) == 0 {
		t.Fatal("expected results for 'issue' query")
	}

	found := false
	for _, r := range results {
		if r.Operation.OperationID == "createIssue" {
			found = true
			break
		}
	}
	if !found {
		t.Error("expected to find createIssue in results")
	}

	// Check dependencies were loaded for getRepo
	results, err = searcher.Search(context.Background(), "specific repository", 10)
	if err != nil {
		t.Fatalf("search specific: %v", err)
	}
	for _, r := range results {
		if r.Operation.OperationID == "getRepo" {
			if len(r.Dependencies) == 0 {
				t.Error("expected dependencies for getRepo")
			}
		}
	}
}

func TestFTS5SearcherConflictPrefix(t *testing.T) {
	dir := t.TempDir()
	db, err := database.Open(filepath.Join(dir, "test.db"))
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	defer db.Close()

	searcher := NewFTS5Searcher(db)

	// Import first spec with "listRepos" operation
	res1, err := db.Exec(`INSERT INTO specs (name, raw_json) VALUES ('github', '{}')`)
	if err != nil {
		t.Fatalf("insert spec1: %v", err)
	}
	specID1, _ := res1.LastInsertId()

	ops1 := []openapi.Operation{
		{
			SpecID:          specID1,
			OperationID:     "listRepos",
			Method:          "GET",
			Path:            "/repos",
			Summary:         "List repos",
			Description:     "List all repos",
			ParametersJSON:  "[]",
			RequestBodyJSON: "{}",
			Tags:            "repos",
		},
	}

	prefixed, err := searcher.Index(ops1, nil, specID1, "github")
	if err != nil {
		t.Fatalf("index spec1: %v", err)
	}
	if prefixed {
		t.Error("first import should not be prefixed")
	}

	// Import second spec with the same "listRepos" operation_id
	res2, err := db.Exec(`INSERT INTO specs (name, raw_json) VALUES ('gitlab', '{}')`)
	if err != nil {
		t.Fatalf("insert spec2: %v", err)
	}
	specID2, _ := res2.LastInsertId()

	ops2 := []openapi.Operation{
		{
			SpecID:          specID2,
			OperationID:     "listRepos",
			Method:          "GET",
			Path:            "/projects",
			Summary:         "List projects",
			Description:     "List all projects",
			ParametersJSON:  "[]",
			RequestBodyJSON: "{}",
			Tags:            "projects",
		},
		{
			SpecID:          specID2,
			OperationID:     "getProject",
			Method:          "GET",
			Path:            "/projects/{id}",
			Summary:         "Get project",
			Description:     "Get a single project",
			ParametersJSON:  "[]",
			RequestBodyJSON: "{}",
			Tags:            "projects",
		},
	}

	deps2 := []openapi.Dependency{
		{OperationID: "getProject", DependsOnID: "listRepos", Reason: "needs project id"},
	}

	prefixed, err = searcher.Index(ops2, deps2, specID2, "gitlab")
	if err != nil {
		t.Fatalf("index spec2: %v", err)
	}
	if !prefixed {
		t.Fatal("second import with conflicting operation_id should be prefixed")
	}

	// Verify the operations were prefixed
	var count int
	err = db.QueryRow(`SELECT COUNT(*) FROM operations WHERE operation_id = 'gitlab.listRepos'`).Scan(&count)
	if err != nil {
		t.Fatalf("query prefixed op: %v", err)
	}
	if count != 1 {
		t.Errorf("expected 1 row with gitlab.listRepos, got %d", count)
	}

	// Non-conflicting op should also be prefixed (whole spec gets prefix)
	err = db.QueryRow(`SELECT COUNT(*) FROM operations WHERE operation_id = 'gitlab.getProject'`).Scan(&count)
	if err != nil {
		t.Fatalf("query prefixed non-conflict op: %v", err)
	}
	if count != 1 {
		t.Errorf("expected 1 row with gitlab.getProject, got %d", count)
	}

	// Deps should also be prefixed
	var depOpID, depOnID string
	err = db.QueryRow(`SELECT operation_id, depends_on_id FROM operation_deps WHERE spec_id = ?`, specID2).Scan(&depOpID, &depOnID)
	if err != nil {
		t.Fatalf("query dep: %v", err)
	}
	if depOpID != "gitlab.getProject" {
		t.Errorf("expected dep operation_id=gitlab.getProject, got %s", depOpID)
	}
	if depOnID != "gitlab.listRepos" {
		t.Errorf("expected dep depends_on_id=gitlab.listRepos, got %s", depOnID)
	}

	// Original spec's operations should be untouched
	err = db.QueryRow(`SELECT COUNT(*) FROM operations WHERE operation_id = 'listRepos' AND spec_id = ?`, specID1).Scan(&count)
	if err != nil {
		t.Fatalf("query original op: %v", err)
	}
	if count != 1 {
		t.Errorf("original listRepos should still exist, got count %d", count)
	}
}
