package proxy

import (
	"database/sql"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
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
	SpecID int64
	Method string
	Path   string
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

	// Build URL with path parameters substituted
	path := opInfo.Path
	queryParams := make(map[string]string)
	bodyParams := make(map[string]any)

	for k, v := range params {
		placeholder := "{" + k + "}"
		if strings.Contains(path, placeholder) {
			path = strings.ReplaceAll(path, placeholder, fmt.Sprintf("%v", v))
		} else if opInfo.Method == "GET" || opInfo.Method == "HEAD" {
			queryParams[k] = fmt.Sprintf("%v", v)
		} else {
			bodyParams[k] = v
		}
	}

	url := strings.TrimRight(baseURL, "/") + path

	// Build query string
	if len(queryParams) > 0 {
		parts := make([]string, 0, len(queryParams))
		for k, v := range queryParams {
			parts = append(parts, k+"="+v)
		}
		url += "?" + strings.Join(parts, "&")
	}

	// Build request body
	var bodyReader io.Reader
	if len(bodyParams) > 0 {
		bodyBytes, err := json.Marshal(bodyParams)
		if err != nil {
			return nil, fmt.Errorf("marshal body: %w", err)
		}
		bodyReader = strings.NewReader(string(bodyBytes))
	}

	req, err := http.NewRequest(opInfo.Method, url, bodyReader)
	if err != nil {
		return nil, fmt.Errorf("create request: %w", err)
	}

	if bodyReader != nil {
		req.Header.Set("Content-Type", "application/json")
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
		`SELECT spec_id, method, path FROM operations WHERE operation_id = ?`,
		operationID,
	).Scan(&info.SpecID, &info.Method, &info.Path)
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
