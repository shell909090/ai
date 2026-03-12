package search

import (
	"database/sql"

	"github.com/shell909090/ai/HITL-proxy/internal/openapi"
)

// SearchResult holds a matched operation with its relevance rank and dependencies.
type SearchResult struct {
	Operation    openapi.Operation    `json:"operation"`
	Rank         float64              `json:"rank"`
	Dependencies []openapi.Dependency `json:"dependencies,omitempty"`
}

// Searcher is the interface for searching operations.
// MVP uses FTS5; future implementations may use vector search.
type Searcher interface {
	Index(ops []openapi.Operation, deps []openapi.Dependency, specID int64, specName string) (bool, error)
	IndexTx(tx *sql.Tx, ops []openapi.Operation, deps []openapi.Dependency, specID int64, specName string) (bool, error)
	Search(query string, limit int) ([]SearchResult, error)
}
