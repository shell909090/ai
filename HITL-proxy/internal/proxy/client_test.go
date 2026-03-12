package proxy

import (
	"encoding/json"
	"io"
	"mime"
	"mime/multipart"
	"net/http"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"sort"
	"strings"
	"testing"

	"github.com/shell909090/ai/HITL-proxy/internal/cred"
	"github.com/shell909090/ai/HITL-proxy/internal/database"
)

// setupTestClient creates a Client backed by a real SQLite database with
// a spec and operation pre-inserted.
func setupTestClient(t *testing.T, targetURL string, op operationInfo) *Client {
	t.Helper()
	dir := t.TempDir()
	dbPath := filepath.Join(dir, "test.db")
	db, err := database.Open(dbPath)
	if err != nil {
		t.Fatalf("open db: %v", err)
	}
	t.Cleanup(func() { db.Close() })

	rawSpec := `{"openapi":"3.0.0","info":{"title":"test","version":"1"},"servers":[{"url":"` + targetURL + `"}],"paths":{}}`
	res, err := db.Exec(`INSERT INTO specs (name, version, raw_json) VALUES (?, ?, ?)`, "test-spec", "1", rawSpec)
	if err != nil {
		t.Fatalf("insert spec: %v", err)
	}
	specID, _ := res.LastInsertId()

	_, err = db.Exec(
		`INSERT INTO operations (spec_id, operation_id, method, path, parameters_json, request_body_json) VALUES (?, ?, ?, ?, ?, ?)`,
		specID, "test-op", op.Method, op.Path, op.ParametersJSON, op.RequestBodyJSON,
	)
	if err != nil {
		t.Fatalf("insert operation: %v", err)
	}

	key := make([]byte, 32) // all-zero key for testing
	credStore, err := cred.NewStore(filepath.Join(dir, "creds.enc"), key)
	if err != nil {
		t.Fatalf("new cred store: %v", err)
	}
	return NewClient(db, credStore)
}

// --- parseParamDefs tests ---

func TestParseParamDefs_Direct(t *testing.T) {
	input := `[{"name":"owner","in":"path","required":true},{"name":"page","in":"query"}]`
	got := parseParamDefs(input)
	if got["owner"].In != "path" {
		t.Errorf("owner.In: got %q, want %q", got["owner"].In, "path")
	}
	if !got["owner"].Required {
		t.Error("owner.Required: got false, want true")
	}
	if got["page"].In != "query" {
		t.Errorf("page.In: got %q, want %q", got["page"].In, "query")
	}
	if got["page"].Required {
		t.Error("page.Required: got true, want false")
	}
}

func TestParseParamDefs_Wrapped(t *testing.T) {
	input := `[{"value":{"name":"id","in":"path","required":true}},{"value":{"name":"q","in":"header"}}]`
	got := parseParamDefs(input)
	if got["id"].In != "path" {
		t.Errorf("id.In: got %q, want %q", got["id"].In, "path")
	}
	if !got["id"].Required {
		t.Error("id.Required: got false, want true")
	}
	if got["q"].In != "header" {
		t.Errorf("q.In: got %q, want %q", got["q"].In, "header")
	}
}

func TestParseParamDefs_StyleExplode(t *testing.T) {
	explodeFalse := false
	input := `[{"name":"color","in":"query","style":"form","explode":false}]`
	got := parseParamDefs(input)
	if got["color"].Style != "form" {
		t.Errorf("color.Style: got %q, want %q", got["color"].Style, "form")
	}
	if got["color"].Explode == nil || *got["color"].Explode != explodeFalse {
		t.Errorf("color.Explode: got %v, want %v", got["color"].Explode, &explodeFalse)
	}
}

func TestParseParamDefs_Empty(t *testing.T) {
	for _, input := range []string{"", "[]", "null"} {
		got := parseParamDefs(input)
		if len(got) != 0 {
			t.Errorf("input %q: expected empty map, got %v", input, got)
		}
	}
}

// --- detectBodyContentType tests ---

func TestDetectBodyContentType_JSON(t *testing.T) {
	input := `{"content":{"application/json":{"schema":{}}}}`
	got := detectBodyContentType(input)
	if got != "application/json" {
		t.Errorf("got %q, want %q", got, "application/json")
	}
}

func TestDetectBodyContentType_FormURLEncoded(t *testing.T) {
	input := `{"content":{"application/x-www-form-urlencoded":{"schema":{}}}}`
	got := detectBodyContentType(input)
	if got != "application/x-www-form-urlencoded" {
		t.Errorf("got %q, want %q", got, "application/x-www-form-urlencoded")
	}
}

func TestDetectBodyContentType_MultipartFormData(t *testing.T) {
	input := `{"content":{"multipart/form-data":{"schema":{}}}}`
	got := detectBodyContentType(input)
	if got != "multipart/form-data" {
		t.Errorf("got %q, want %q", got, "multipart/form-data")
	}
}

func TestDetectBodyContentType_FormPreferredOverJSON(t *testing.T) {
	input := `{"content":{"application/json":{},"application/x-www-form-urlencoded":{}}}`
	got := detectBodyContentType(input)
	if got != "application/x-www-form-urlencoded" {
		t.Errorf("got %q, want %q", got, "application/x-www-form-urlencoded")
	}
}

func TestDetectBodyContentType_Wrapped(t *testing.T) {
	input := `{"value":{"content":{"application/x-www-form-urlencoded":{}}}}`
	got := detectBodyContentType(input)
	if got != "application/x-www-form-urlencoded" {
		t.Errorf("got %q, want %q", got, "application/x-www-form-urlencoded")
	}
}

func TestDetectBodyContentType_Empty(t *testing.T) {
	for _, input := range []string{"", "{}", "null"} {
		got := detectBodyContentType(input)
		if got != "application/json" {
			t.Errorf("input %q: got %q, want %q", input, got, "application/json")
		}
	}
}

// --- toStringSlice tests ---

func TestToStringSlice(t *testing.T) {
	arr, ok := toStringSlice([]any{"a", "b", "c"})
	if !ok || len(arr) != 3 || arr[0] != "a" {
		t.Errorf("[]any: got %v, %v", arr, ok)
	}

	arr, ok = toStringSlice([]string{"x", "y"})
	if !ok || len(arr) != 2 || arr[0] != "x" {
		t.Errorf("[]string: got %v, %v", arr, ok)
	}

	_, ok = toStringSlice("scalar")
	if ok {
		t.Error("scalar should return false")
	}
}

// --- Call integration tests ---

func TestCall_PathAndQueryParams(t *testing.T) {
	var gotPath, gotQuery string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.Path
		gotQuery = r.URL.RawQuery
		w.WriteHeader(200)
		_, _ = w.Write([]byte(`{"ok":true}`))
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "GET",
		Path:            "/repos/{owner}/{repo}/issues",
		ParametersJSON:  `[{"name":"owner","in":"path","required":true},{"name":"repo","in":"path","required":true},{"name":"page","in":"query"},{"name":"per_page","in":"query"}]`,
		RequestBodyJSON: "{}",
	})

	result, err := client.Call("test-op", map[string]any{
		"owner":    "octocat",
		"repo":     "hello-world",
		"page":     1,
		"per_page": 30,
	})
	if err != nil {
		t.Fatalf("Call: %v", err)
	}
	if result.StatusCode != 200 {
		t.Errorf("status: got %d, want 200", result.StatusCode)
	}
	if gotPath != "/repos/octocat/hello-world/issues" {
		t.Errorf("path: got %q, want %q", gotPath, "/repos/octocat/hello-world/issues")
	}

	q, _ := url.ParseQuery(gotQuery)
	if q.Get("page") != "1" {
		t.Errorf("page: got %q, want %q", q.Get("page"), "1")
	}
	if q.Get("per_page") != "30" {
		t.Errorf("per_page: got %q, want %q", q.Get("per_page"), "30")
	}
}

func TestCall_PathEscaping(t *testing.T) {
	var gotPath string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotPath = r.URL.RawPath
		if gotPath == "" {
			gotPath = r.URL.Path
		}
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "GET",
		Path:            "/users/{name}",
		ParametersJSON:  `[{"name":"name","in":"path","required":true}]`,
		RequestBodyJSON: "{}",
	})

	_, _ = client.Call("test-op", map[string]any{"name": "hello world/foo"})
	if gotPath != "/users/hello%20world%2Ffoo" {
		t.Errorf("escaped path: got %q, want %q", gotPath, "/users/hello%20world%2Ffoo")
	}
}

func TestCall_HeaderAndCookieParams(t *testing.T) {
	var gotHeader, gotCookie string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotHeader = r.Header.Get("X-Request-Id")
		gotCookie = r.Header.Get("Cookie")
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "GET",
		Path:            "/test",
		ParametersJSON:  `[{"name":"X-Request-Id","in":"header"},{"name":"session","in":"cookie"}]`,
		RequestBodyJSON: "{}",
	})

	_, _ = client.Call("test-op", map[string]any{
		"X-Request-Id": "abc-123",
		"session":      "tok_xyz",
	})
	if gotHeader != "abc-123" {
		t.Errorf("header: got %q, want %q", gotHeader, "abc-123")
	}
	if gotCookie != "session=tok_xyz" {
		t.Errorf("cookie: got %q, want %q", gotCookie, "session=tok_xyz")
	}
}

func TestCall_JSONBody(t *testing.T) {
	var gotCT string
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotCT = r.Header.Get("Content-Type")
		b, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(b, &gotBody)
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "POST",
		Path:            "/items",
		ParametersJSON:  "[]",
		RequestBodyJSON: `{"content":{"application/json":{"schema":{}}}}`,
	})

	_, _ = client.Call("test-op", map[string]any{"name": "widget", "count": 5})
	if gotCT != "application/json" {
		t.Errorf("content-type: got %q, want %q", gotCT, "application/json")
	}
	if gotBody["name"] != "widget" {
		t.Errorf("body.name: got %v, want %q", gotBody["name"], "widget")
	}
}

func TestCall_FormURLEncodedBody(t *testing.T) {
	var gotCT string
	var gotBody string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotCT = r.Header.Get("Content-Type")
		b, _ := io.ReadAll(r.Body)
		gotBody = string(b)
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "POST",
		Path:            "/login",
		ParametersJSON:  "[]",
		RequestBodyJSON: `{"content":{"application/x-www-form-urlencoded":{"schema":{}}}}`,
	})

	_, _ = client.Call("test-op", map[string]any{"username": "admin", "password": "s3cret"})
	if gotCT != "application/x-www-form-urlencoded" {
		t.Errorf("content-type: got %q, want %q", gotCT, "application/x-www-form-urlencoded")
	}
	vals, err := url.ParseQuery(gotBody)
	if err != nil {
		t.Fatalf("parse form body: %v", err)
	}
	if vals.Get("username") != "admin" {
		t.Errorf("username: got %q, want %q", vals.Get("username"), "admin")
	}
	if vals.Get("password") != "s3cret" {
		t.Errorf("password: got %q, want %q", vals.Get("password"), "s3cret")
	}
}

func TestCall_MultipartFormDataBody(t *testing.T) {
	var gotCT string
	gotFields := make(map[string]string)
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotCT = r.Header.Get("Content-Type")
		mediaType, params, err := mime.ParseMediaType(gotCT)
		if err != nil || mediaType != "multipart/form-data" {
			w.WriteHeader(400)
			return
		}
		reader := multipart.NewReader(r.Body, params["boundary"])
		for {
			part, err := reader.NextPart()
			if err != nil {
				break
			}
			b, _ := io.ReadAll(part)
			gotFields[part.FormName()] = string(b)
			part.Close()
		}
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "POST",
		Path:            "/upload",
		ParametersJSON:  "[]",
		RequestBodyJSON: `{"content":{"multipart/form-data":{"schema":{}}}}`,
	})

	result, err := client.Call("test-op", map[string]any{"filename": "test.txt", "description": "a file"})
	if err != nil {
		t.Fatalf("Call: %v", err)
	}
	if result.StatusCode != 200 {
		t.Errorf("status: got %d, want 200", result.StatusCode)
	}
	if gotFields["filename"] != "test.txt" {
		t.Errorf("filename: got %q, want %q", gotFields["filename"], "test.txt")
	}
	if gotFields["description"] != "a file" {
		t.Errorf("description: got %q, want %q", gotFields["description"], "a file")
	}
}

func TestCall_FallbackUndefinedParams(t *testing.T) {
	var gotBody map[string]any
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(b, &gotBody)
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "POST",
		Path:            "/items",
		ParametersJSON:  "[]",
		RequestBodyJSON: "{}",
	})

	_, _ = client.Call("test-op", map[string]any{"title": "test"})
	if gotBody["title"] != "test" {
		t.Errorf("body.title: got %v, want %q", gotBody["title"], "test")
	}
}

func TestCall_FallbackGETUndefinedParams(t *testing.T) {
	var gotQuery string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.RawQuery
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "GET",
		Path:            "/search",
		ParametersJSON:  "[]",
		RequestBodyJSON: "{}",
	})

	_, _ = client.Call("test-op", map[string]any{"q": "hello"})
	q, _ := url.ParseQuery(gotQuery)
	if q.Get("q") != "hello" {
		t.Errorf("q: got %q, want %q", q.Get("q"), "hello")
	}
}

func TestCall_RequiredParamMissing(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "GET",
		Path:            "/users/{id}",
		ParametersJSON:  `[{"name":"id","in":"path","required":true}]`,
		RequestBodyJSON: "{}",
	})

	_, err := client.Call("test-op", map[string]any{})
	if err == nil {
		t.Fatal("expected error for missing required param, got nil")
	}
	if !strings.Contains(err.Error(), "missing required parameter: id") {
		t.Errorf("error message: got %q, want to contain %q", err.Error(), "missing required parameter: id")
	}
}

func TestCall_QueryArrayExplodeTrue(t *testing.T) {
	var gotQuery string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.RawQuery
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "GET",
		Path:            "/items",
		ParametersJSON:  `[{"name":"color","in":"query","style":"form"}]`,
		RequestBodyJSON: "{}",
	})

	_, _ = client.Call("test-op", map[string]any{"color": []any{"blue", "green", "red"}})
	q, _ := url.ParseQuery(gotQuery)
	colors := q["color"]
	sort.Strings(colors)
	if len(colors) != 3 || colors[0] != "blue" || colors[1] != "green" || colors[2] != "red" {
		t.Errorf("colors: got %v, want [blue green red]", colors)
	}
}

func TestCall_QueryArrayExplodeFalse(t *testing.T) {
	var gotQuery string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotQuery = r.URL.RawQuery
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "GET",
		Path:            "/items",
		ParametersJSON:  `[{"name":"color","in":"query","style":"form","explode":false}]`,
		RequestBodyJSON: "{}",
	})

	_, _ = client.Call("test-op", map[string]any{"color": []any{"blue", "green"}})
	q, _ := url.ParseQuery(gotQuery)
	if q.Get("color") != "blue,green" {
		t.Errorf("color: got %q, want %q", q.Get("color"), "blue,green")
	}
}

func TestCall_HeaderArrayCommaSeparated(t *testing.T) {
	var gotHeader string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		gotHeader = r.Header.Get("X-Tags")
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "GET",
		Path:            "/test",
		ParametersJSON:  `[{"name":"X-Tags","in":"header"}]`,
		RequestBodyJSON: "{}",
	})

	_, _ = client.Call("test-op", map[string]any{"X-Tags": []any{"a", "b", "c"}})
	if gotHeader != "a,b,c" {
		t.Errorf("X-Tags: got %q, want %q", gotHeader, "a,b,c")
	}
}

func TestCall_FormBodyWithArray(t *testing.T) {
	var gotBody string
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		gotBody = string(b)
		w.WriteHeader(200)
	}))
	defer srv.Close()

	client := setupTestClient(t, srv.URL, operationInfo{
		Method:          "POST",
		Path:            "/submit",
		ParametersJSON:  "[]",
		RequestBodyJSON: `{"content":{"application/x-www-form-urlencoded":{"schema":{}}}}`,
	})

	_, _ = client.Call("test-op", map[string]any{"tags": []any{"go", "rust"}})
	vals, err := url.ParseQuery(gotBody)
	if err != nil {
		t.Fatalf("parse form: %v", err)
	}
	tags := vals["tags"]
	sort.Strings(tags)
	if len(tags) != 2 || tags[0] != "go" || tags[1] != "rust" {
		t.Errorf("tags: got %v, want [go rust]", tags)
	}
}
