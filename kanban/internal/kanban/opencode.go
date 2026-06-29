package kanban

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
)

// openCodeDriver implements AgentDriver for the opencode backend.
type openCodeDriver struct {
	httpc        *http.Client
	baseURL      string
	user         string
	pass         string
	defaultModel ocModelRef
	labelModels  map[string]ocModelRef // "model:<label>" → model
}

// ocModelRef identifies an opencode model as a (provider, model) pair.
type ocModelRef struct {
	ProviderID string
	ModelID    string
}

// newOpenCodeDriver constructs an openCodeDriver from raw config.
func newOpenCodeDriver(raw map[string]any, envLookup func(string) string, httpc *http.Client) (*openCodeDriver, error) {
	d := &openCodeDriver{
		httpc:       httpc,
		baseURL:     "http://127.0.0.1:4096",
		labelModels: make(map[string]ocModelRef),
	}

	if v, ok := raw["base_url"].(string); ok && v != "" {
		d.baseURL = v
	}
	if v, ok := raw["username_env"].(string); ok && v != "" {
		d.user = envLookup(v)
	}
	if v, ok := raw["password_env"].(string); ok && v != "" {
		d.pass = envLookup(v)
	}

	if dm, ok := raw["default_model"].(map[string]any); ok {
		if pid, ok := dm["providerID"].(string); ok {
			d.defaultModel.ProviderID = pid
		}
		if mid, ok := dm["modelID"].(string); ok {
			d.defaultModel.ModelID = mid
		}
	}

	if am, ok := raw["allowed_models"].([]any); ok {
		for _, item := range am {
			m, ok := item.(map[string]any)
			if !ok {
				continue
			}
			label, _ := m["label"].(string)
			pid, _ := m["providerID"].(string)
			mid, _ := m["modelID"].(string)
			if label != "" {
				d.labelModels[label] = ocModelRef{ProviderID: pid, ModelID: mid}
			}
		}
	}

	return d, nil
}

// selectModel picks the model for the given card labels.
// It scans labels for a "model:*" key in labelModels, falling back to defaultModel.
func (d *openCodeDriver) selectModel(labels []string) ocModelRef {
	for _, l := range labels {
		if strings.HasPrefix(l, "model:") {
			if m, ok := d.labelModels[l]; ok {
				return m
			}
		}
	}
	return d.defaultModel
}

// CreateSession creates a new opencode session with the given working directory.
func (d *openCodeDriver) CreateSession(ctx context.Context, workdir string, labels []string) (string, error) {
	u := d.baseURL + "/session"
	if workdir != "" {
		u += "?directory=" + url.QueryEscape(workdir)
	}
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, strings.NewReader("{}"))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(d.user, d.pass)
	resp, err := d.httpc.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return "", fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var sess ocSession
	if err := json.NewDecoder(resp.Body).Decode(&sess); err != nil {
		return "", err
	}
	if !strings.HasPrefix(sess.ID, "ses_") {
		return "", fmt.Errorf("unexpected session id=%q", sess.ID)
	}
	return sess.ID, nil
}

// AbortSession sends an abort request for the given session.
func (d *openCodeDriver) AbortSession(ctx context.Context, sessionID string) error {
	u := fmt.Sprintf("%s/session/%s/abort", d.baseURL, sessionID)
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, nil)
	req.SetBasicAuth(d.user, d.pass)
	resp, err := d.httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}

// SendPrompt sends a prompt to the session asynchronously.
func (d *openCodeDriver) SendPrompt(ctx context.Context, sessionID, prompt string, labels []string) error {
	model := d.selectModel(labels)
	u := fmt.Sprintf("%s/session/%s/prompt_async", d.baseURL, sessionID)
	body, _ := json.Marshal(map[string]any{
		"model": map[string]string{
			"providerID": model.ProviderID,
			"modelID":    model.ModelID,
		},
		"parts": []map[string]string{{"type": "text", "text": prompt}},
	})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(d.user, d.pass)
	resp, err := d.httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 204 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}

// SessionState queries the last message of a session and returns a normalized AgentState.
func (d *openCodeDriver) SessionState(ctx context.Context, sessionID string) (AgentState, error) {
	u := fmt.Sprintf("%s/session/%s/message?limit=1", d.baseURL, sessionID)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	req.SetBasicAuth(d.user, d.pass)
	resp, err := d.httpc.Do(req)
	if err != nil {
		return AgentState{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return AgentState{}, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var msgs []map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&msgs); err != nil {
		return AgentState{}, err
	}

	var last map[string]any
	if len(msgs) > 0 {
		last = msgs[len(msgs)-1]
	}

	finish := extractFinish(last)
	text := ExtractSummaryText(last, summaryCharLimit)

	var kind string
	switch finish {
	case "", "tool-calls":
		kind = "running"
	case "stop":
		kind = "finished"
	default:
		kind = "failed"
	}

	return AgentState{
		Kind:      kind,
		Text:      text,
		RawFinish: finish,
	}, nil
}

// BuildDrivers constructs the driver map from the config.
// It returns an error if any agent has an unknown type.
func BuildDrivers(cfg Config, envLookup func(string) string, httpc *http.Client) (map[string]AgentDriver, error) {
	drivers := make(map[string]AgentDriver, len(cfg.Agents))
	for name, ac := range cfg.Agents {
		switch ac.Type {
		case "opencode":
			drv, err := newOpenCodeDriver(ac.Raw, envLookup, httpc)
			if err != nil {
				return nil, fmt.Errorf("agent %q: %w", name, err)
			}
			drivers[name] = drv
		default:
			return nil, fmt.Errorf("agent %q: unknown type %q", name, ac.Type)
		}
	}
	return drivers, nil
}
