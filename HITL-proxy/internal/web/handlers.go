package web

import (
	"context"
	"database/sql"
	"embed"
	"encoding/json"
	"fmt"
	"html/template"
	"io"
	"net/http"
	"strconv"

	"github.com/shell909090/ai/HITL-proxy/internal/approval"
	"github.com/shell909090/ai/HITL-proxy/internal/openapi"
	"github.com/shell909090/ai/HITL-proxy/internal/search"
)

//go:embed templates/*.html
var templateFS embed.FS

// Handler serves the web UI for approval management and spec import.
type Handler struct {
	engine   *approval.Engine
	db       *sql.DB
	searcher search.Searcher
	tmpl     *template.Template
}

func NewHandler(engine *approval.Engine, db *sql.DB, searcher search.Searcher) (*Handler, error) {
	funcMap := template.FuncMap{
		"prettyJSON": func(s string) string {
			var v any
			if err := json.Unmarshal([]byte(s), &v); err != nil {
				return s
			}
			b, err := json.MarshalIndent(v, "", "  ")
			if err != nil {
				return s
			}
			return string(b)
		},
	}

	tmpl, err := template.New("").Funcs(funcMap).ParseFS(templateFS, "templates/*.html")
	if err != nil {
		return nil, fmt.Errorf("parse templates: %w", err)
	}

	return &Handler{
		engine:   engine,
		db:       db,
		searcher: searcher,
		tmpl:     tmpl,
	}, nil
}

// RegisterRoutes registers HTTP routes on the given mux.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /", h.handlePending)
	mux.HandleFunc("GET /approval/{id}", h.handleDetail)
	mux.HandleFunc("POST /approval/{id}/approve", h.handleApprove)
	mux.HandleFunc("POST /approval/{id}/reject", h.handleReject)
	mux.HandleFunc("POST /specs/import", h.handleImportSpec)
}

func (h *Handler) handlePending(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}

	pending, err := h.engine.GetPending()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	h.tmpl.ExecuteTemplate(w, "pending.html", map[string]any{
		"Requests": pending,
	})
}

func (h *Handler) handleDetail(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		http.Error(w, "invalid id", http.StatusBadRequest)
		return
	}

	req, err := h.engine.GetRequest(id)
	if err != nil {
		http.Error(w, err.Error(), http.StatusNotFound)
		return
	}

	h.tmpl.ExecuteTemplate(w, "detail.html", map[string]any{
		"Request": req,
	})
}

func (h *Handler) handleApprove(w http.ResponseWriter, r *http.Request) {
	h.handleDecision(w, r, true)
}

func (h *Handler) handleReject(w http.ResponseWriter, r *http.Request) {
	h.handleDecision(w, r, false)
}

func (h *Handler) handleDecision(w http.ResponseWriter, r *http.Request, approved bool) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		http.Error(w, "invalid id", http.StatusBadRequest)
		return
	}

	if err := h.engine.Decide(id, approved, "web-ui"); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// htmx: return updated status
	status := "Rejected"
	if approved {
		status = "Approved"
	}
	w.Header().Set("HX-Redirect", "/")
	fmt.Fprintf(w, "<span class='status-%s'>%s</span>", status, status)
}

func (h *Handler) handleImportSpec(w http.ResponseWriter, r *http.Request) {
	body, err := io.ReadAll(r.Body)
	if err != nil {
		http.Error(w, "read body: "+err.Error(), http.StatusBadRequest)
		return
	}

	name := r.URL.Query().Get("name")
	if name == "" {
		name = "imported"
	}

	// Insert spec into DB
	result, err := h.db.Exec(
		`INSERT INTO specs (name, raw_json) VALUES (?, ?)`, name, string(body),
	)
	if err != nil {
		http.Error(w, "insert spec: "+err.Error(), http.StatusInternalServerError)
		return
	}
	specID, _ := result.LastInsertId()

	// Parse spec
	ops, deps, err := openapi.ParseSpec(context.Background(), specID, body)
	if err != nil {
		http.Error(w, "parse spec: "+err.Error(), http.StatusBadRequest)
		return
	}

	// Index operations
	if err := h.searcher.Index(ops, deps, specID); err != nil {
		http.Error(w, "index operations: "+err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]any{
		"spec_id":    specID,
		"operations": len(ops),
		"deps":       len(deps),
	})
}
