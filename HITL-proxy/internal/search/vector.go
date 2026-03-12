package search

import (
	"context"
	"fmt"
	"strconv"

	chromem "github.com/philippgille/chromem-go"
)

// VectorStore stores and retrieves operation embeddings for semantic search.
// Current implementation: chromem-go (in-memory + disk persistence).
// Future: Qdrant.
type VectorStore interface {
	Upsert(ctx context.Context, items []VectorItem) error
	DeleteBySpec(ctx context.Context, specID int64) error
	Search(ctx context.Context, queryVec []float32, limit int) ([]VectorResult, error)
}

// VectorItem is a single operation embedding to index.
type VectorItem struct {
	OperationID string
	SpecID      int64
	Embedding   []float32
}

// VectorResult is a single result from a vector similarity search.
type VectorResult struct {
	OperationID string
	Score       float32 // cosine similarity, 0..1
}

// ChromemStore implements VectorStore using chromem-go.
type ChromemStore struct {
	coll *chromem.Collection
}

// NewChromemStore opens a persistent chromem-go database at path and returns
// a VectorStore backed by the "operations" collection.
func NewChromemStore(path string) (*ChromemStore, error) {
	db, err := chromem.NewPersistentDB(path, false)
	if err != nil {
		return nil, fmt.Errorf("open chromem db: %w", err)
	}
	// Pass nil embedding function: we supply pre-computed embeddings ourselves.
	coll, err := db.GetOrCreateCollection("operations", nil, nil)
	if err != nil {
		return nil, fmt.Errorf("get collection: %w", err)
	}
	return &ChromemStore{coll: coll}, nil
}

// Upsert adds or replaces embeddings for the given operations.
func (s *ChromemStore) Upsert(ctx context.Context, items []VectorItem) error {
	docs := make([]chromem.Document, len(items))
	for i, item := range items {
		docs[i] = chromem.Document{
			ID: item.OperationID,
			Metadata: map[string]string{
				"spec_id": strconv.FormatInt(item.SpecID, 10),
			},
			Embedding: item.Embedding,
		}
	}
	return s.coll.AddDocuments(ctx, docs, 1)
}

// DeleteBySpec removes all embeddings belonging to the given spec.
func (s *ChromemStore) DeleteBySpec(ctx context.Context, specID int64) error {
	where := map[string]string{"spec_id": strconv.FormatInt(specID, 10)}
	return s.coll.Delete(ctx, where, nil)
}

// Search returns the top-limit most similar operations to queryVec.
func (s *ChromemStore) Search(ctx context.Context, queryVec []float32, limit int) ([]VectorResult, error) {
	count := s.coll.Count()
	if count == 0 {
		return nil, nil
	}
	if limit > count {
		limit = count
	}
	results, err := s.coll.QueryEmbedding(ctx, queryVec, limit, nil, nil)
	if err != nil {
		return nil, fmt.Errorf("chromem query: %w", err)
	}
	out := make([]VectorResult, len(results))
	for i, r := range results {
		out[i] = VectorResult{OperationID: r.ID, Score: r.Similarity}
	}
	return out, nil
}
