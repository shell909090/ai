package proxy

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"net/url"
	"sort"
	"strings"
	"time"

	"github.com/shell909090/ai/HITL-proxy/internal/cred"
)

// Client executes HTTP requests to target APIs.
type Client struct {
	db         *sql.DB
	credStore  *cred.Store
	httpClient *http.Client
}

func NewClient(db *sql.DB, credStore *cred.Store) *Client {
	return &Client{
		db:        db,
		credStore: credStore,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
	}
}

// CallResult holds the result of an API call.
type CallResult struct {
	StatusCode int    `json:"status_code"`
	Body       string `json:"body"`
}

// operationInfo is fetched from the database for building the request.
type operationInfo struct {
	SpecID          int64
	Method          string
	Path            string
	ParametersJSON  string
	RequestBodyJSON string
}

type specInfo struct {
	Name    string
	RawJSON string
}

// Call executes an API call for the given operationId with the provided parameters.
func (c *Client) Call(operationID string, params map[string]any) (*CallResult, error) {
	// Look up the operation
	opInfo, err := c.getOperation(operationID)
	if err != nil {
		return nil, fmt.Errorf("get operation: %w", err)
	}

	// Look up spec to get base URL
	spec, err := c.getSpec(opInfo.SpecID)
	if err != nil {
		return nil, fmt.Errorf("get spec: %w", err)
	}

	baseURL, err := extractBaseURL(spec.RawJSON)
	if err != nil {
		return nil, fmt.Errorf("extract base URL: %w", err)
	}

	// Parse parameter definitions from OpenAPI spec
	paramDefs := parseParamDefs(opInfo.ParametersJSON)

	// Validate required parameters
	for name, def := range paramDefs {
		if def.Required {
			if _, ok := params[name]; !ok {
				return nil, fmt.Errorf("missing required parameter: %s", name)
			}
		}
	}

	// Route parameters according to OpenAPI "in" field
	path := opInfo.Path
	queryValues := make(url.Values)
	headerParams := make(map[string]string)
	var cookieParts []string
	bodyParams := make(map[string]any)

	for k, v := range params {
		def, defined := paramDefs[k]
		loc := def.In
		if !defined {
			// Fallback: path placeholder > GET/HEAD query > body
			placeholder := "{" + k + "}"
			if strings.Contains(path, placeholder) {
				loc = "path"
			} else if opInfo.Method == "GET" || opInfo.Method == "HEAD" {
				loc = "query"
			} else {
				bodyParams[k] = v
				continue
			}
		}
		switch loc {
		case "path":
			path = strings.ReplaceAll(path, "{"+k+"}", formatPathValue(k, v, def))
		case "query":
			addQueryValues(queryValues, k, v, def)
		case "header":
			headerParams[k] = formatHeaderValue(k, v, def)
		case "cookie":
			cookieParts = append(cookieParts, formatCookieParts(k, v, def)...)
		default:
			bodyParams[k] = v
		}
	}

	reqURL := strings.TrimRight(baseURL, "/") + path
	if len(queryValues) > 0 {
		reqURL += "?" + queryValues.Encode()
	}

	// Build request body according to the OpenAPI requestBody content type
	var bodyReader io.Reader
	contentType := detectBodyContentType(opInfo.RequestBodyJSON)
	if len(bodyParams) > 0 {
		switch contentType {
		case "application/x-www-form-urlencoded":
			form := make(url.Values)
			for k, v := range bodyParams {
				addFormValues(form, k, v, paramDef{Style: "form"})
			}
			bodyReader = strings.NewReader(form.Encode())
		case "multipart/form-data":
			var buf bytes.Buffer
			writer := multipart.NewWriter(&buf)
			for k, v := range bodyParams {
				if err := addMultipartFields(writer, k, v); err != nil {
					return nil, fmt.Errorf("write multipart field %s: %w", k, err)
				}
			}
			if err := writer.Close(); err != nil {
				return nil, fmt.Errorf("close multipart writer: %w", err)
			}
			bodyReader = &buf
			contentType = writer.FormDataContentType()
		default: // application/json or unspecified
			bodyBytes, err := json.Marshal(bodyParams)
			if err != nil {
				return nil, fmt.Errorf("marshal body: %w", err)
			}
			bodyReader = strings.NewReader(string(bodyBytes))
			contentType = "application/json"
		}
	}

	req, err := http.NewRequest(opInfo.Method, reqURL, bodyReader)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	if bodyReader != nil {
		req.Header.Set("Content-Type", contentType)
	}

	for k, v := range headerParams {
		req.Header.Set(k, v)
	}
	if len(cookieParts) > 0 {
		req.Header.Set("Cookie", strings.Join(cookieParts, "; "))
	}

	// Inject credentials
	if creds, ok := c.credStore.Get(spec.Name); ok {
		for k, v := range creds {
			req.Header.Set(k, v)
		}
	}

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("execute request: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, fmt.Errorf("read response: %w", err)
	}

	return &CallResult{
		StatusCode: resp.StatusCode,
		Body:       string(body),
	}, nil
}

func (c *Client) getOperation(operationID string) (*operationInfo, error) {
	var info operationInfo
	err := c.db.QueryRow(
		`SELECT spec_id, method, path, parameters_json, request_body_json FROM operations WHERE operation_id = ?`,
		operationID,
	).Scan(&info.SpecID, &info.Method, &info.Path, &info.ParametersJSON, &info.RequestBodyJSON)
	if err != nil {
		return nil, err
	}
	return &info, nil
}

func (c *Client) getSpec(specID int64) (*specInfo, error) {
	var info specInfo
	err := c.db.QueryRow(
		`SELECT name, raw_json FROM specs WHERE id = ?`,
		specID,
	).Scan(&info.Name, &info.RawJSON)
	if err != nil {
		return nil, err
	}
	return &info, nil
}

func formatPathValue(key string, value any, def paramDef) string {
	style := def.Style
	if style == "" {
		style = "simple"
	}

	if obj, ok := toStringMap(value); ok {
		switch style {
		case "label":
			if def.shouldExplode() {
				return "." + joinMapWithEquals(obj, ".")
			}
			return "." + joinEscapedMap(obj, ",")
		case "matrix":
			if def.shouldExplode() {
				parts := make([]string, 0, len(obj))
				for _, objKey := range sortedKeys(obj) {
					parts = append(parts, ";"+url.PathEscape(objKey)+"="+url.PathEscape(obj[objKey]))
				}
				return strings.Join(parts, "")
			}
			return ";" + url.PathEscape(key) + "=" + joinEscapedMap(obj, ",")
		default: // simple
			if def.shouldExplode() {
				return joinEscapedMapWithEquals(obj, ",")
			}
			return joinEscapedMap(obj, ",")
		}
	}

	if arr, ok := toStringSlice(value); ok {
		escaped := make([]string, len(arr))
		for i, item := range arr {
			escaped[i] = url.PathEscape(item)
		}
		switch style {
		case "label":
			if def.shouldExplode() {
				return "." + strings.Join(escaped, ".")
			}
			return "." + strings.Join(escaped, ",")
		case "matrix":
			if def.shouldExplode() {
				parts := make([]string, 0, len(escaped))
				for _, item := range escaped {
					parts = append(parts, ";"+url.PathEscape(key)+"="+item)
				}
				return strings.Join(parts, "")
			}
			return ";" + url.PathEscape(key) + "=" + strings.Join(escaped, ",")
		default: // simple
			return strings.Join(escaped, ",")
		}
	}

	switch style {
	case "label":
		return "." + url.PathEscape(fmt.Sprintf("%v", value))
	case "matrix":
		return ";" + url.PathEscape(key) + "=" + url.PathEscape(fmt.Sprintf("%v", value))
	default:
		return url.PathEscape(fmt.Sprintf("%v", value))
	}
}

// paramDef holds the parsed OpenAPI parameter definition.
type paramDef struct {
	In       string
	Required bool
	Style    string // "form", "simple", "label", "matrix"; empty = default
	Explode  *bool  // nil = use default (true for form, false for simple)
}

// shouldExplode returns whether the parameter should be exploded.
// OpenAPI defaults: explode=true for style=form, false otherwise.
func (p paramDef) shouldExplode() bool {
	if p.Explode != nil {
		return *p.Explode
	}
	return p.Style == "" || p.Style == "form"
}

// parseParamDefs extracts parameter definitions from the serialized
// OpenAPI parameters JSON. It handles both direct format
// [{"name":"x","in":"query",...}] and ref-wrapped format
// [{"value":{"name":"x","in":"query",...}}].
func parseParamDefs(parametersJSON string) map[string]paramDef {
	result := make(map[string]paramDef)
	if parametersJSON == "" || parametersJSON == "[]" || parametersJSON == "null" {
		return result
	}

	type rawParam struct {
		Name     string `json:"name"`
		In       string `json:"in"`
		Required bool   `json:"required"`
		Style    string `json:"style"`
		Explode  *bool  `json:"explode"`
	}

	// Try direct format first: [{"name":"x","in":"query",...}]
	var direct []rawParam
	if err := json.Unmarshal([]byte(parametersJSON), &direct); err == nil {
		for _, p := range direct {
			if p.Name != "" && p.In != "" {
				result[p.Name] = paramDef{In: p.In, Required: p.Required, Style: p.Style, Explode: p.Explode}
			}
		}
		if len(result) > 0 {
			return result
		}
	}

	// Try ref-wrapped format: [{"value":{"name":"x","in":"query",...}}]
	var wrapped []struct {
		Value rawParam `json:"value"`
	}
	if err := json.Unmarshal([]byte(parametersJSON), &wrapped); err == nil {
		for _, p := range wrapped {
			if p.Value.Name != "" && p.Value.In != "" {
				result[p.Value.Name] = paramDef{In: p.Value.In, Required: p.Value.Required, Style: p.Value.Style, Explode: p.Value.Explode}
			}
		}
	}

	return result
}

// addQueryValues adds a parameter value to url.Values, handling arrays
// according to the OpenAPI style/explode settings.
// Default (style=form, explode=true): repeated keys ?color=blue&color=green
// style=form, explode=false: comma-separated ?color=blue,green
func addQueryValues(q url.Values, key string, value any, def paramDef) {
	if obj, ok := toStringMap(value); ok {
		if def.Style == "deepObject" {
			for _, objKey := range sortedKeys(obj) {
				q.Set(key+"["+objKey+"]", obj[objKey])
			}
			return
		}
		if def.shouldExplode() {
			for _, objKey := range sortedKeys(obj) {
				q.Set(objKey, obj[objKey])
			}
		} else {
			q.Set(key, joinMap(obj, ","))
		}
		return
	}
	if arr, ok := toStringSlice(value); ok {
		if def.shouldExplode() {
			for _, item := range arr {
				q.Add(key, item)
			}
		} else {
			q.Set(key, strings.Join(arr, ","))
		}
		return
	}
	q.Set(key, fmt.Sprintf("%v", value))
}

// addFormValues adds a parameter value to form url.Values, expanding arrays.
func addFormValues(form url.Values, key string, value any, def paramDef) {
	if obj, ok := toStringMap(value); ok {
		if def.shouldExplode() {
			for _, objKey := range sortedKeys(obj) {
				form.Set(objKey, obj[objKey])
			}
		} else {
			form.Set(key, joinMap(obj, ","))
		}
		return
	}
	if arr, ok := toStringSlice(value); ok {
		if def.shouldExplode() {
			for _, item := range arr {
				form.Add(key, item)
			}
		} else {
			form.Set(key, strings.Join(arr, ","))
		}
		return
	}
	form.Set(key, fmt.Sprintf("%v", value))
}

// formatHeaderValue formats a value for use in an HTTP header.
// Arrays are comma-separated per OpenAPI style=simple default.
func formatHeaderValue(_ string, value any, def paramDef) string {
	if obj, ok := toStringMap(value); ok {
		if def.shouldExplode() {
			return joinMapWithEquals(obj, ",")
		}
		return joinMap(obj, ",")
	}
	if arr, ok := toStringSlice(value); ok {
		return strings.Join(arr, ",")
	}
	return fmt.Sprintf("%v", value)
}

func formatCookieParts(key string, value any, def paramDef) []string {
	if obj, ok := toStringMap(value); ok {
		if def.shouldExplode() {
			parts := make([]string, 0, len(obj))
			for _, objKey := range sortedKeys(obj) {
				parts = append(parts, objKey+"="+obj[objKey])
			}
			return parts
		}
		return []string{key + "=" + joinMap(obj, ",")}
	}
	if arr, ok := toStringSlice(value); ok {
		if def.shouldExplode() {
			parts := make([]string, 0, len(arr))
			for _, item := range arr {
				parts = append(parts, key+"="+item)
			}
			return parts
		}
		return []string{key + "=" + strings.Join(arr, ",")}
	}
	return []string{key + "=" + fmt.Sprintf("%v", value)}
}

func addMultipartFields(writer *multipart.Writer, key string, value any) error {
	if obj, ok := toStringMap(value); ok {
		for _, objKey := range sortedKeys(obj) {
			if err := writer.WriteField(objKey, obj[objKey]); err != nil {
				return err
			}
		}
		return nil
	}
	if arr, ok := toStringSlice(value); ok {
		for _, item := range arr {
			if err := writer.WriteField(key, item); err != nil {
				return err
			}
		}
		return nil
	}
	return writer.WriteField(key, fmt.Sprintf("%v", value))
}

// toStringSlice converts a []any value to []string. Returns false if
// the value is not a slice.
func toStringSlice(v any) ([]string, bool) {
	switch arr := v.(type) {
	case []any:
		result := make([]string, len(arr))
		for i, item := range arr {
			result[i] = fmt.Sprintf("%v", item)
		}
		return result, true
	case []string:
		return arr, true
	}
	return nil, false
}

func toStringMap(v any) (map[string]string, bool) {
	switch m := v.(type) {
	case map[string]any:
		result := make(map[string]string, len(m))
		for k, item := range m {
			result[k] = fmt.Sprintf("%v", item)
		}
		return result, true
	case map[string]string:
		result := make(map[string]string, len(m))
		for k, item := range m {
			result[k] = item
		}
		return result, true
	}
	return nil, false
}

func joinMap(m map[string]string, sep string) string {
	parts := make([]string, 0, len(m)*2)
	for _, key := range sortedKeys(m) {
		parts = append(parts, key, m[key])
	}
	return strings.Join(parts, sep)
}

func joinMapWithEquals(m map[string]string, sep string) string {
	parts := make([]string, 0, len(m))
	for _, key := range sortedKeys(m) {
		parts = append(parts, key+"="+m[key])
	}
	return strings.Join(parts, sep)
}

func joinEscapedMap(m map[string]string, sep string) string {
	parts := make([]string, 0, len(m)*2)
	for _, key := range sortedKeys(m) {
		parts = append(parts, url.PathEscape(key), url.PathEscape(m[key]))
	}
	return strings.Join(parts, sep)
}

func joinEscapedMapWithEquals(m map[string]string, sep string) string {
	parts := make([]string, 0, len(m))
	for _, key := range sortedKeys(m) {
		parts = append(parts, url.PathEscape(key)+"="+url.PathEscape(m[key]))
	}
	return strings.Join(parts, sep)
}

func sortedKeys(m map[string]string) []string {
	keys := make([]string, 0, len(m))
	for key := range m {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

// detectBodyContentType extracts the preferred content type from the
// serialized OpenAPI requestBody JSON. It looks for the "content" map keys.
// Returns "application/json" as default if nothing is found.
// Handles both direct {"content":{"application/json":...}} and
// ref-wrapped {"value":{"content":...}} formats.
func detectBodyContentType(requestBodyJSON string) string {
	if requestBodyJSON == "" || requestBodyJSON == "{}" || requestBodyJSON == "null" {
		return "application/json"
	}

	// Try direct format: {"content":{"media-type":{...}}}
	var direct struct {
		Content map[string]any `json:"content"`
	}
	if err := json.Unmarshal([]byte(requestBodyJSON), &direct); err == nil && len(direct.Content) > 0 {
		return pickContentType(direct.Content)
	}

	// Try ref-wrapped format: {"value":{"content":{"media-type":{...}}}}
	var wrapped struct {
		Value struct {
			Content map[string]any `json:"content"`
		} `json:"value"`
	}
	if err := json.Unmarshal([]byte(requestBodyJSON), &wrapped); err == nil && len(wrapped.Value.Content) > 0 {
		return pickContentType(wrapped.Value.Content)
	}

	return "application/json"
}

// pickContentType selects the best content type from a media type map.
// Prefers form-urlencoded over JSON when both are present, since JSON
// is the default fallback. If only one type exists, returns that.
func pickContentType(content map[string]any) string {
	// Priority order for non-JSON types that need special encoding
	for _, ct := range []string{
		"multipart/form-data",
		"application/x-www-form-urlencoded",
	} {
		if _, ok := content[ct]; ok {
			return ct
		}
	}
	// Fall back to first available, or default JSON
	for ct := range content {
		return ct
	}
	return "application/json"
}

func extractBaseURL(rawJSON string) (string, error) {
	var doc struct {
		Servers []struct {
			URL string `json:"url"`
		} `json:"servers"`
	}
	if err := json.Unmarshal([]byte(rawJSON), &doc); err != nil {
		return "", err
	}
	if len(doc.Servers) > 0 {
		return doc.Servers[0].URL, nil
	}
	return "", fmt.Errorf("no servers defined in spec")
}
