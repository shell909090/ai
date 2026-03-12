package web

import (
	"context"
	"crypto/rand"
	"crypto/subtle"
	"database/sql"
	"embed"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"html/template"
	"io"
	"net/http"
	"strconv"

	"errors"
	"log"

	"github.com/shell909090/ai/HITL-proxy/internal/approval"
	"github.com/shell909090/ai/HITL-proxy/internal/auth"
	"github.com/shell909090/ai/HITL-proxy/internal/openapi"
	"github.com/shell909090/ai/HITL-proxy/internal/search"
)

//go:embed templates/*.html
var templateFS embed.FS

// Handler serves the web UI for approval management and spec import.
type Handler struct {
	engine        *approval.Engine
	db            *sql.DB
	searcher      search.Searcher
	hub           *approval.SSEHub
	authenticator *auth.Authenticator
	adminPassword string
	// tmpls holds one template set per page to avoid {{define "content"}} collisions.
	tmpls map[string]*template.Template
}

func NewHandler(engine *approval.Engine, db *sql.DB, searcher search.Searcher, hub *approval.SSEHub, authenticator *auth.Authenticator, adminPassword string) (*Handler, error) {
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

	pages := []string{"pending", "detail", "apikeys"}
	tmpls := make(map[string]*template.Template, len(pages))
	for _, page := range pages {
		t, err := template.New("").Funcs(funcMap).ParseFS(
			templateFS,
			"templates/layout.html",
			"templates/"+page+".html",
		)
		if err != nil {
			return nil, fmt.Errorf("parse template %s: %w", page, err)
		}
		tmpls[page] = t
	}

	return &Handler{
		engine:        engine,
		db:            db,
		searcher:      searcher,
		hub:           hub,
		authenticator: authenticator,
		adminPassword: adminPassword,
		tmpls:         tmpls,
	}, nil
}

// basicAuth wraps a handler with HTTP Basic Auth. Username must be "admin".
func (h *Handler) basicAuth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		username, password, ok := r.BasicAuth()
		userOK := subtle.ConstantTimeCompare([]byte(username), []byte("admin"))
		passOK := subtle.ConstantTimeCompare([]byte(password), []byte(h.adminPassword))
		if !ok || userOK != 1 || passOK != 1 {
			w.Header().Set("WWW-Authenticate", `Basic realm="HITL-proxy Admin"`)
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}
		next(w, r)
	}
}

// RegisterRoutes registers HTTP routes on the given mux.
func (h *Handler) RegisterRoutes(mux *http.ServeMux) {
	mux.HandleFunc("GET /{$}", h.basicAuth(h.handlePending))
	mux.HandleFunc("GET /approval/{id}", h.basicAuth(h.handleDetail))
	mux.HandleFunc("POST /approval/{id}/approve", h.basicAuth(h.handleApprove))
	mux.HandleFunc("POST /approval/{id}/reject", h.basicAuth(h.handleReject))
	mux.HandleFunc("POST /specs/import", h.basicAuth(h.handleImportSpec))
	mux.HandleFunc("GET /events", h.basicAuth(h.handleSSE))
	mux.HandleFunc("GET /admin/apikeys", h.basicAuth(h.handleListAPIKeys))
	mux.HandleFunc("POST /admin/apikeys", h.basicAuth(h.handleCreateAPIKey))
	mux.HandleFunc("POST /admin/apikeys/{id}/delete", h.basicAuth(h.handleDeleteAPIKey))
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

	if err := h.tmpls["pending"].ExecuteTemplate(w, "pending.html", map[string]any{
		"Requests": pending,
	}); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
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

	if err := h.tmpls["detail"].ExecuteTemplate(w, "detail.html", map[string]any{
		"Request": req,
	}); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
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

	// Parse spec before starting transaction
	// (use specID=0 temporarily; we update it after INSERT)
	ops, deps, schemesJSON, globalSecJSON, err := openapi.ParseSpec(context.Background(), 0, body)
	if err != nil {
		http.Error(w, "parse spec: "+err.Error(), http.StatusBadRequest)
		return
	}

	// Begin atomic transaction for the entire import
	tx, err := h.db.Begin()
	if err != nil {
		http.Error(w, "begin tx: "+err.Error(), http.StatusInternalServerError)
		return
	}
	defer func() { _ = tx.Rollback() }()

	// Insert spec into DB
	result, err := tx.Exec(
		`INSERT INTO specs (name, raw_json, security_schemes_json, global_security_json) VALUES (?, ?, ?, ?)`,
		name, string(body), schemesJSON, globalSecJSON,
	)
	if err != nil {
		http.Error(w, "insert spec: "+err.Error(), http.StatusInternalServerError)
		return
	}
	specID, _ := result.LastInsertId()

	// Update specID in parsed operations
	for i := range ops {
		ops[i].SpecID = specID
	}

	// Index operations within the same transaction
	prefixed, err := h.searcher.IndexTx(tx, ops, deps, specID, name)
	if err != nil {
		http.Error(w, "index operations: "+err.Error(), http.StatusInternalServerError)
		return
	}

	if err := tx.Commit(); err != nil {
		http.Error(w, "commit: "+err.Error(), http.StatusInternalServerError)
		return
	}

	// After commit: generate and store embeddings if the searcher supports it.
	// Embedding failure is non-fatal: FTS5 search still works; report as a warning field.
	var embeddingWarning string
	if vi, ok := h.searcher.(search.VectorIndexer); ok {
		if err := vi.IndexEmbeddings(r.Context(), ops, specID); err != nil {
			log.Printf("warn: index embeddings for spec %d (%s): %v", specID, name, err)
			embeddingWarning = err.Error()
		}
	}

	resp := map[string]any{
		"spec_id":    specID,
		"operations": len(ops),
		"deps":       len(deps),
	}
	if prefixed {
		resp["prefix"] = name + "."
	}
	if embeddingWarning != "" {
		resp["embedding_warning"] = embeddingWarning
	}

	w.Header().Set("Content-Type", "application/json")
	if err := json.NewEncoder(w).Encode(resp); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
}

func (h *Handler) handleListAPIKeys(w http.ResponseWriter, r *http.Request) {
	keys, err := h.authenticator.ListKeys()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	if err := h.tmpls["apikeys"].ExecuteTemplate(w, "apikeys.html", map[string]any{
		"Keys": keys,
	}); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
}

func (h *Handler) handleCreateAPIKey(w http.ResponseWriter, r *http.Request) {
	agentName := r.FormValue("agent_name")
	if agentName == "" {
		http.Error(w, "agent_name required", http.StatusBadRequest)
		return
	}

	raw := make([]byte, 24)
	if _, err := rand.Read(raw); err != nil {
		http.Error(w, "generate key: "+err.Error(), http.StatusInternalServerError)
		return
	}
	newKey := "sk-" + hex.EncodeToString(raw)

	if err := h.authenticator.CreateKey(newKey, agentName); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	keys, err := h.authenticator.ListKeys()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	w.Header().Set("Cache-Control", "no-store")
	if err := h.tmpls["apikeys"].ExecuteTemplate(w, "apikeys.html", map[string]any{
		"Keys":         keys,
		"NewKey":       newKey,
		"NewAgentName": agentName,
	}); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
}

func (h *Handler) handleDeleteAPIKey(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		http.Error(w, "invalid id", http.StatusBadRequest)
		return
	}

	if err := h.authenticator.DeleteKey(id); err != nil {
		if errors.Is(err, auth.ErrNotFound) {
			http.Error(w, err.Error(), http.StatusNotFound)
		} else {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
		return
	}

	http.Redirect(w, r, "/admin/apikeys", http.StatusSeeOther)
}

// handleSSE streams server-sent events to browser clients for real-time updates.
func (h *Handler) handleSSE(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		http.Error(w, "streaming not supported", http.StatusInternalServerError)
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	ch := h.hub.Subscribe()
	defer h.hub.Unsubscribe(ch)

	for {
		select {
		case <-r.Context().Done():
			return
		case event := <-ch:
			fmt.Fprintf(w, "event: %s\ndata: {\"id\":%d}\n\n", event.Type, event.ID)
			flusher.Flush()
		}
	}
}
