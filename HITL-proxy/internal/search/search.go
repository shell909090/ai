package search

import (
	"context"
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
// FTS5Searcher implements keyword search.
// HybridSearcher implements FTS5 + vector search with RRF fusion.
type Searcher interface {
	Index(ops []openapi.Operation, deps []openapi.Dependency, specID int64, specName string) (bool, error)
	IndexTx(tx *sql.Tx, ops []openapi.Operation, deps []openapi.Dependency, specID int64, specName string) (bool, error)
	Search(ctx context.Context, query string, limit int) ([]SearchResult, error)
}

// VectorIndexer is an optional interface for searchers that support vector
// embedding indexing. It is called after the SQLite transaction commits so
// that embedding generation does not block the atomic import.
type VectorIndexer interface {
	IndexEmbeddings(ctx context.Context, ops []openapi.Operation, specID int64) error
	DeleteSpecEmbeddings(ctx context.Context, specID int64) error
}
