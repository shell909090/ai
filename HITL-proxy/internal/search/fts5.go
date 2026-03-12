package search

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"strings"

	"github.com/shell909090/ai/HITL-proxy/internal/openapi"
)

// FTS5Searcher implements Searcher using SQLite FTS5.
type FTS5Searcher struct {
	db *sql.DB
}

func NewFTS5Searcher(db *sql.DB) *FTS5Searcher {
	return &FTS5Searcher{db: db}
}

func (s *FTS5Searcher) Index(ops []openapi.Operation, deps []openapi.Dependency, specID int64) error {
	tx, err := s.db.Begin()
	if err != nil {
		return fmt.Errorf("begin tx: %w", err)
	}
	defer tx.Rollback()

	stmt, err := tx.Prepare(`INSERT OR REPLACE INTO operations
		(spec_id, operation_id, method, path, summary, description, parameters_json, request_body_json, tags)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`)
	if err != nil {
		return fmt.Errorf("prepare insert: %w", err)
	}
	defer stmt.Close()

	for _, op := range ops {
		_, err := stmt.Exec(op.SpecID, op.OperationID, op.Method, op.Path,
			op.Summary, op.Description, op.ParametersJSON, op.RequestBodyJSON, op.Tags)
		if err != nil {
			return fmt.Errorf("insert operation %s: %w", op.OperationID, err)
		}
	}

	depStmt, err := tx.Prepare(`INSERT OR REPLACE INTO operation_deps
		(operation_id, depends_on_id, reason, spec_id) VALUES (?, ?, ?, ?)`)
	if err != nil {
		return fmt.Errorf("prepare dep insert: %w", err)
	}
	defer depStmt.Close()

	for _, dep := range deps {
		if _, err := depStmt.Exec(dep.OperationID, dep.DependsOnID, dep.Reason, specID); err != nil {
			return fmt.Errorf("insert dep %s→%s: %w", dep.OperationID, dep.DependsOnID, err)
		}
	}

	return tx.Commit()
}

func (s *FTS5Searcher) Search(query string, limit int) ([]SearchResult, error) {
	if limit <= 0 {
		limit = 10
	}

	// Tokenize and add wildcard for better matching
	ftsQuery := buildFTSQuery(query)

	rows, err := s.db.Query(`
		SELECT o.spec_id, o.operation_id, o.method, o.path, o.summary, o.description,
			o.parameters_json, o.request_body_json, o.tags, f.rank
		FROM operations_fts f
		JOIN operations o ON o.id = f.rowid
		WHERE operations_fts MATCH ?
		ORDER BY f.rank
		LIMIT ?
	`, ftsQuery, limit)
	if err != nil {
		return nil, fmt.Errorf("fts5 search: %w", err)
	}
	defer rows.Close()

	var results []SearchResult
	for rows.Next() {
		var r SearchResult
		if err := rows.Scan(
			&r.Operation.SpecID, &r.Operation.OperationID, &r.Operation.Method,
			&r.Operation.Path, &r.Operation.Summary, &r.Operation.Description,
			&r.Operation.ParametersJSON, &r.Operation.RequestBodyJSON, &r.Operation.Tags,
			&r.Rank,
		); err != nil {
			return nil, fmt.Errorf("scan result: %w", err)
		}
		results = append(results, r)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate results: %w", err)
	}

	// Fetch dependencies for matched operations
	if err := s.loadDependencies(results); err != nil {
		return nil, err
	}

	return results, nil
}

func (s *FTS5Searcher) loadDependencies(results []SearchResult) error {
	for i, r := range results {
		rows, err := s.db.Query(
			`SELECT operation_id, depends_on_id, reason FROM operation_deps WHERE operation_id = ?`,
			r.Operation.OperationID,
		)
		if err != nil {
			return fmt.Errorf("query deps: %w", err)
		}

		var deps []openapi.Dependency
		for rows.Next() {
			var d openapi.Dependency
			if err := rows.Scan(&d.OperationID, &d.DependsOnID, &d.Reason); err != nil {
				rows.Close()
				return fmt.Errorf("scan dep: %w", err)
			}
			deps = append(deps, d)
		}
		rows.Close()
		if err := rows.Err(); err != nil {
			return fmt.Errorf("iterate deps: %w", err)
		}
		results[i].Dependencies = deps
	}
	return nil
}

// MarshalResults converts search results to JSON for MCP response.
func MarshalResults(results []SearchResult) (string, error) {
	data, err := json.MarshalIndent(results, "", "  ")
	if err != nil {
		return "", err
	}
	return string(data), nil
}

func buildFTSQuery(query string) string {
	words := strings.Fields(query)
	parts := make([]string, 0, len(words))
	for _, w := range words {
		w = strings.TrimFunc(w, func(r rune) bool {
			return !((r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '_')
		})
		if w != "" {
			parts = append(parts, w+"*")
		}
	}
	if len(parts) == 0 {
		return query
	}
	return strings.Join(parts, " OR ")
}
