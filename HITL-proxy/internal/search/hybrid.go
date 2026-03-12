package search

import (
	"context"
	"database/sql"
	"fmt"
	"log"
	"sort"
	"strings"

	"github.com/shell909090/ai/HITL-proxy/internal/openapi"
)

const rrfK = 60

// VectorSearcher pairs an Embedder with a VectorStore.
type VectorSearcher struct {
	embedder Embedder
	store    VectorStore
}

// NewVectorSearcher creates a VectorSearcher from an Embedder and VectorStore.
func NewVectorSearcher(embedder Embedder, store VectorStore) *VectorSearcher {
	return &VectorSearcher{embedder: embedder, store: store}
}

// HybridSearcher combines FTS5 keyword search and vector semantic search,
// merging results with Reciprocal Rank Fusion (RRF).
// It implements Searcher and VectorIndexer.
type HybridSearcher struct {
	fts5 *FTS5Searcher
	vec  *VectorSearcher // nil → FTS5-only mode
	db   *sql.DB
}

// NewHybridSearcher creates a HybridSearcher.
// vec may be nil; in that case it behaves identically to FTS5Searcher.
func NewHybridSearcher(db *sql.DB, vec *VectorSearcher) *HybridSearcher {
	return &HybridSearcher{
		fts5: NewFTS5Searcher(db),
		vec:  vec,
		db:   db,
	}
}

// Index delegates to FTS5Searcher (conflict detection + SQL writes).
func (h *HybridSearcher) Index(ops []openapi.Operation, deps []openapi.Dependency, specID int64, specName string) (bool, error) {
	return h.fts5.Index(ops, deps, specID, specName)
}

// IndexTx delegates to FTS5Searcher for transactional SQL writes.
func (h *HybridSearcher) IndexTx(tx *sql.Tx, ops []openapi.Operation, deps []openapi.Dependency, specID int64, specName string) (bool, error) {
	return h.fts5.IndexTx(tx, ops, deps, specID, specName)
}

// IndexEmbeddings generates embeddings and stores them in the vector store.
// Must be called after the SQLite transaction commits. Implements VectorIndexer.
func (h *HybridSearcher) IndexEmbeddings(ctx context.Context, ops []openapi.Operation, specID int64) error {
	if h.vec == nil {
		return nil
	}
	items := make([]VectorItem, 0, len(ops))
	for _, op := range ops {
		vec, err := h.vec.embedder.Embed(ctx, operationText(op))
		if err != nil {
			return fmt.Errorf("embed %s: %w", op.OperationID, err)
		}
		items = append(items, VectorItem{
			OperationID: op.OperationID,
			SpecID:      specID,
			Embedding:   vec,
		})
	}
	return h.vec.store.Upsert(ctx, items)
}

// DeleteSpecEmbeddings removes all embeddings for the given spec. Implements VectorIndexer.
func (h *HybridSearcher) DeleteSpecEmbeddings(ctx context.Context, specID int64) error {
	if h.vec == nil {
		return nil
	}
	return h.vec.store.DeleteBySpec(ctx, specID)
}

// Search runs FTS5 and vector search concurrently, merges with RRF, then
// fetches full operation data from SQLite for the merged top-limit results.
func (h *HybridSearcher) Search(ctx context.Context, query string, limit int) ([]SearchResult, error) {
	if h.vec == nil {
		return h.fts5.Search(ctx, query, limit)
	}

	type ftsOut struct {
		results []SearchResult
		err     error
	}
	type vecOut struct {
		results []VectorResult
		err     error
	}

	ftsCh := make(chan ftsOut, 1)
	vecCh := make(chan vecOut, 1)

	go func() {
		r, err := h.fts5.Search(ctx, query, limit*2)
		ftsCh <- ftsOut{r, err}
	}()

	go func() {
		vec, err := h.vec.embedder.Embed(ctx, query)
		if err != nil {
			vecCh <- vecOut{nil, err}
			return
		}
		r, err := h.vec.store.Search(ctx, vec, limit*2)
		vecCh <- vecOut{r, err}
	}()

	fts := <-ftsCh
	vec := <-vecCh

	if fts.err != nil {
		log.Printf("fts5 search error: %v", fts.err)
	}
	if vec.err != nil {
		log.Printf("vector search error: %v", vec.err)
	}

	// If vector search failed or returned nothing, fall back to FTS5 results.
	if vec.err != nil || len(vec.results) == 0 {
		if len(fts.results) > limit {
			fts.results = fts.results[:limit]
		}
		return fts.results, fts.err
	}

	// RRF merge: score = Σ 1/(rrfK + rank+1) across both result lists.
	scores := make(map[string]float64, len(fts.results)+len(vec.results))
	for rank, r := range fts.results {
		scores[r.Operation.OperationID] += 1.0 / float64(rrfK+rank+1)
	}
	for rank, r := range vec.results {
		scores[r.OperationID] += 1.0 / float64(rrfK+rank+1)
	}

	type scored struct {
		id    string
		score float64
	}
	merged := make([]scored, 0, len(scores))
	for id, s := range scores {
		merged = append(merged, scored{id, s})
	}
	sort.Slice(merged, func(i, j int) bool {
		return merged[i].score > merged[j].score
	})
	if len(merged) > limit {
		merged = merged[:limit]
	}

	// Fetch full operation data from SQLite for the top results.
	ids := make([]string, len(merged))
	for i, m := range merged {
		ids[i] = m.id
	}
	ops, err := fetchOperationsByIDs(h.db, ids)
	if err != nil {
		return nil, fmt.Errorf("fetch operations: %w", err)
	}

	opMap := make(map[string]openapi.Operation, len(ops))
	for _, op := range ops {
		opMap[op.OperationID] = op
	}

	results := make([]SearchResult, 0, len(merged))
	for _, m := range merged {
		op, ok := opMap[m.id]
		if !ok {
			continue
		}
		results = append(results, SearchResult{Operation: op, Rank: m.score})
	}

	if err := h.fts5.loadDependencies(results); err != nil {
		return nil, err
	}
	return results, nil
}

// operationText builds the searchable text blob for embedding an operation.
func operationText(op openapi.Operation) string {
	return strings.Join([]string{op.OperationID, op.Summary, op.Description, op.Tags}, " ")
}

// fetchOperationsByIDs fetches full operation rows from SQLite by operation_id.
func fetchOperationsByIDs(db *sql.DB, ids []string) ([]openapi.Operation, error) {
	if len(ids) == 0 {
		return nil, nil
	}
	placeholders := make([]string, len(ids))
	args := make([]any, len(ids))
	for i, id := range ids {
		placeholders[i] = "?"
		args[i] = id
	}
	query := fmt.Sprintf(
		`SELECT spec_id, operation_id, method, path, summary, description,
		        parameters_json, request_body_json, tags, security_json
		 FROM operations WHERE operation_id IN (%s)`,
		strings.Join(placeholders, ","),
	)
	rows, err := db.Query(query, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	var ops []openapi.Operation
	for rows.Next() {
		var op openapi.Operation
		if err := rows.Scan(
			&op.SpecID, &op.OperationID, &op.Method, &op.Path,
			&op.Summary, &op.Description, &op.ParametersJSON,
			&op.RequestBodyJSON, &op.Tags, &op.SecurityJSON,
		); err != nil {
			return nil, err
		}
		ops = append(ops, op)
	}
	return ops, rows.Err()
}
