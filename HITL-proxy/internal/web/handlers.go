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
	"strings"
	"time"

	"errors"
	"log"

	"github.com/shell909090/ai/HITL-proxy/internal/approval"
	"github.com/shell909090/ai/HITL-proxy/internal/auth"
	"github.com/shell909090/ai/HITL-proxy/internal/cred"
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
	credStore     *cred.Store
	adminPassword string
	// tmpls holds one template set per page to avoid {{define "content"}} collisions.
	tmpls map[string]*template.Template
}

func NewHandler(engine *approval.Engine, db *sql.DB, searcher search.Searcher, hub *approval.SSEHub, authenticator *auth.Authenticator, credStore *cred.Store, adminPassword string) (*Handler, error) {
	funcMap := template.FuncMap{
		// safeID converts a string to a CSS-selector-safe id by replacing any
		// character that is not alphanumeric or '-' with '_'.
		"safeID": func(s string) string {
			return strings.Map(func(r rune) rune {
				if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '-' {
					return r
				}
				return '_'
			}, s)
		},
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

	pages := []string{"pending", "detail", "apikeys", "specs", "rules", "creds"}
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
		credStore:     credStore,
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
	mux.HandleFunc("GET /admin/specs", h.basicAuth(h.handleListSpecs))
	mux.HandleFunc("POST /admin/specs/import", h.basicAuth(h.handleImportSpecForm))
	mux.HandleFunc("POST /admin/specs/{id}/delete", h.basicAuth(h.handleDeleteSpec))
	mux.HandleFunc("GET /admin/rules", h.basicAuth(h.handleListRules))
	mux.HandleFunc("POST /admin/rules", h.basicAuth(h.handleSetRule))
	mux.HandleFunc("GET /admin/creds", h.basicAuth(h.handleListCreds))
	mux.HandleFunc("POST /admin/creds", h.basicAuth(h.handleSetCreds))
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

// importSpecBody parses and imports a spec into the DB. Returns import result info.
func (h *Handler) importSpecBody(ctx context.Context, name string, body []byte) (specID int64, opCount, depCount int, prefixed bool, embeddingWarning string, err error) {
	ops, deps, schemesJSON, globalSecJSON, err := openapi.ParseSpec(ctx, 0, body)
	if err != nil {
		return 0, 0, 0, false, "", fmt.Errorf("parse spec: %w", err)
	}

	tx, err := h.db.Begin()
	if err != nil {
		return 0, 0, 0, false, "", fmt.Errorf("begin tx: %w", err)
	}
	defer func() { _ = tx.Rollback() }()

	result, err := tx.Exec(
		`INSERT INTO specs (name, raw_json, security_schemes_json, global_security_json) VALUES (?, ?, ?, ?)`,
		name, string(body), schemesJSON, globalSecJSON,
	)
	if err != nil {
		return 0, 0, 0, false, "", fmt.Errorf("insert spec: %w", err)
	}
	specID, _ = result.LastInsertId()

	for i := range ops {
		ops[i].SpecID = specID
	}

	prefixed, err = h.searcher.IndexTx(tx, ops, deps, specID, name)
	if err != nil {
		return 0, 0, 0, false, "", fmt.Errorf("index operations: %w", err)
	}

	if err = tx.Commit(); err != nil {
		return 0, 0, 0, false, "", fmt.Errorf("commit: %w", err)
	}

	if vi, ok := h.searcher.(search.VectorIndexer); ok {
		if err := vi.IndexEmbeddings(ctx, ops, specID); err != nil {
			log.Printf("warn: index embeddings for spec %d (%s): %v", specID, name, err)
			embeddingWarning = err.Error()
		}
	}

	return specID, len(ops), len(deps), prefixed, embeddingWarning, nil
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

	specID, opCount, depCount, prefixed, embeddingWarning, err := h.importSpecBody(r.Context(), name, body)
	if err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	resp := map[string]any{
		"spec_id":    specID,
		"operations": opCount,
		"deps":       depCount,
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

// specRow holds a spec summary row for the specs admin page.
type specRow struct {
	ID        int64
	Name      string
	CreatedAt time.Time
	OpCount   int
}

func (h *Handler) handleListSpecs(w http.ResponseWriter, r *http.Request) {
	rows, err := h.db.Query(`
		SELECT s.id, s.name, s.created_at, COUNT(o.id) as op_count
		FROM specs s
		LEFT JOIN operations o ON o.spec_id = s.id
		GROUP BY s.id
		ORDER BY s.created_at DESC
	`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var specs []specRow
	for rows.Next() {
		var s specRow
		if err := rows.Scan(&s.ID, &s.Name, &s.CreatedAt, &s.OpCount); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		specs = append(specs, s)
	}
	if err := rows.Err(); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	if err := h.tmpls["specs"].ExecuteTemplate(w, "specs.html", map[string]any{
		"Specs": specs,
	}); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
}

func (h *Handler) handleImportSpecForm(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseMultipartForm(32 << 20); err != nil {
		http.Error(w, "parse form: "+err.Error(), http.StatusBadRequest)
		return
	}

	name := r.FormValue("name")
	if name == "" {
		name = "imported"
	}

	file, _, err := r.FormFile("file")
	if err != nil {
		http.Error(w, "file required: "+err.Error(), http.StatusBadRequest)
		return
	}
	defer file.Close()

	body, err := io.ReadAll(file)
	if err != nil {
		http.Error(w, "read file: "+err.Error(), http.StatusBadRequest)
		return
	}

	if _, _, _, _, _, err := h.importSpecBody(r.Context(), name, body); err != nil {
		http.Error(w, err.Error(), http.StatusBadRequest)
		return
	}

	http.Redirect(w, r, "/admin/specs", http.StatusSeeOther)
}

func (h *Handler) handleDeleteSpec(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.ParseInt(r.PathValue("id"), 10, 64)
	if err != nil {
		http.Error(w, "invalid id", http.StatusBadRequest)
		return
	}

	// Fetch spec name before deletion (for credStore cleanup)
	var specName string
	if err := h.db.QueryRow(`SELECT name FROM specs WHERE id = ?`, id).Scan(&specName); err != nil {
		if err == sql.ErrNoRows {
			http.Error(w, "spec not found", http.StatusNotFound)
		} else {
			http.Error(w, err.Error(), http.StatusInternalServerError)
		}
		return
	}

	// Delete DB records in dependency order
	tx, err := h.db.Begin()
	if err != nil {
		http.Error(w, "begin tx: "+err.Error(), http.StatusInternalServerError)
		return
	}
	defer func() { _ = tx.Rollback() }()

	// Delete approval and authz rules for this spec's operations
	if _, err := tx.Exec(`
		DELETE FROM approval_rules WHERE operation_id IN (
			SELECT operation_id FROM operations WHERE spec_id = ?
		)`, id); err != nil {
		http.Error(w, "delete approval rules: "+err.Error(), http.StatusInternalServerError)
		return
	}
	if _, err := tx.Exec(`
		DELETE FROM authz_rules WHERE operation_id IN (
			SELECT operation_id FROM operations WHERE spec_id = ?
		)`, id); err != nil {
		http.Error(w, "delete authz rules: "+err.Error(), http.StatusInternalServerError)
		return
	}

	if _, err := tx.Exec(`DELETE FROM operation_deps WHERE spec_id = ?`, id); err != nil {
		http.Error(w, "delete deps: "+err.Error(), http.StatusInternalServerError)
		return
	}
	if _, err := tx.Exec(`DELETE FROM operations WHERE spec_id = ?`, id); err != nil {
		http.Error(w, "delete operations: "+err.Error(), http.StatusInternalServerError)
		return
	}
	if _, err := tx.Exec(`DELETE FROM specs WHERE id = ?`, id); err != nil {
		http.Error(w, "delete spec: "+err.Error(), http.StatusInternalServerError)
		return
	}

	if err := tx.Commit(); err != nil {
		http.Error(w, "commit: "+err.Error(), http.StatusInternalServerError)
		return
	}

	// Delete vector embeddings after successful DB commit (non-fatal)
	if vi, ok := h.searcher.(search.VectorIndexer); ok {
		if err := vi.DeleteSpecEmbeddings(r.Context(), id); err != nil {
			log.Printf("warn: delete embeddings for spec %d: %v", id, err)
		}
	}

	// Clean up credentials for this spec (non-fatal)
	if err := h.credStore.Delete(specName); err != nil {
		log.Printf("warn: delete creds for spec %s: %v", specName, err)
	}

	http.Redirect(w, r, "/admin/specs", http.StatusSeeOther)
}

func (h *Handler) handleListRules(w http.ResponseWriter, r *http.Request) {
	rules, err := h.engine.ListRules()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	if err := h.tmpls["rules"].ExecuteTemplate(w, "rules.html", map[string]any{
		"Rules": rules,
	}); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
}

func (h *Handler) handleSetRule(w http.ResponseWriter, r *http.Request) {
	operationID := r.FormValue("operation_id")
	if operationID == "" {
		http.Error(w, "operation_id required", http.StatusBadRequest)
		return
	}
	required := r.FormValue("required") == "1"

	if err := h.engine.SetRule(operationID, required); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	// Fetch the updated row to return an updated HTML fragment
	rules, err := h.engine.ListRules()
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	var row *approval.RuleRow
	for i := range rules {
		if rules[i].OperationID == operationID {
			row = &rules[i]
			break
		}
	}
	if row == nil {
		http.Error(w, "operation not found", http.StatusNotFound)
		return
	}

	// Return a single rule row HTML fragment for htmx swap, using the template
	// to ensure all output is properly escaped.
	if err := h.tmpls["rules"].ExecuteTemplate(w, "rule-row", row); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
}

// credScheme holds a scheme name and whether a credential is already set.
type credScheme struct {
	Name  string
	IsSet bool
}

// credSpecRow holds spec info plus parsed security schemes for the creds page.
// IsRaw is true when the spec has no securitySchemes; credentials are injected
// as raw headers and the user can add arbitrary key/value pairs.
type credSpecRow struct {
	ID      int64
	Name    string
	Schemes []credScheme
	IsRaw   bool
}

func (h *Handler) handleListCreds(w http.ResponseWriter, r *http.Request) {
	rows, err := h.db.Query(`SELECT id, name, COALESCE(security_schemes_json, '{}') FROM specs ORDER BY name`)
	if err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}
	defer rows.Close()

	var specs []credSpecRow
	for rows.Next() {
		var id int64
		var name, schemesJSON string
		if err := rows.Scan(&id, &name, &schemesJSON); err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}

		var schemesMap map[string]any
		_ = json.Unmarshal([]byte(schemesJSON), &schemesMap)

		existingCreds, _ := h.credStore.Get(name)
		isRaw := len(schemesMap) == 0
		schemes := make([]credScheme, 0)
		if isRaw {
			// No security schemes: show existing raw header entries for editing.
			for k := range existingCreds {
				schemes = append(schemes, credScheme{Name: k, IsSet: true})
			}
		} else {
			for k := range schemesMap {
				_, set := existingCreds[k]
				schemes = append(schemes, credScheme{Name: k, IsSet: set})
			}
		}

		specs = append(specs, credSpecRow{
			ID:      id,
			Name:    name,
			Schemes: schemes,
			IsRaw:   isRaw,
		})
	}
	if err := rows.Err(); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
		return
	}

	if err := h.tmpls["creds"].ExecuteTemplate(w, "creds.html", map[string]any{
		"Specs": specs,
	}); err != nil {
		http.Error(w, err.Error(), http.StatusInternalServerError)
	}
}

func (h *Handler) handleSetCreds(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseForm(); err != nil {
		http.Error(w, "parse form: "+err.Error(), http.StatusBadRequest)
		return
	}

	specName := r.FormValue("spec_name")
	if specName == "" {
		http.Error(w, "spec_name required", http.StatusBadRequest)
		return
	}

	// Load existing creds so empty fields don't wipe existing values
	existing, _ := h.credStore.Get(specName)
	if existing == nil {
		existing = make(map[string]string)
	}

	newKey := strings.TrimSpace(r.FormValue("__new_key"))
	newVal := r.FormValue("__new_val")
	for k, vs := range r.Form {
		if k == "spec_name" || k == "__new_key" || k == "__new_val" {
			continue
		}
		if len(vs) > 0 && vs[0] != "" {
			existing[k] = vs[0]
		}
	}
	if newKey != "" {
		existing[newKey] = newVal
	}

	if err := h.credStore.Set(specName, existing); err != nil {
		http.Error(w, "save creds: "+err.Error(), http.StatusInternalServerError)
		return
	}

	http.Redirect(w, r, "/admin/creds", http.StatusSeeOther)
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
