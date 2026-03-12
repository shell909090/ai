package search

import (
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

	if err := searcher.Index(ops, deps, specID); err != nil {
		t.Fatalf("index: %v", err)
	}

	// Search for repositories
	results, err := searcher.Search("repository", 10)
	if err != nil {
		t.Fatalf("search: %v", err)
	}

	if len(results) < 2 {
		t.Fatalf("expected at least 2 results, got %d", len(results))
	}

	// Search for issues
	results, err = searcher.Search("issue", 10)
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
	results, err = searcher.Search("specific repository", 10)
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
