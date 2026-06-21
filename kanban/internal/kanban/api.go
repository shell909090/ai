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

// Trello API: list cards in a list. Includes the labels field so the
// caller can extract proj:* / model:* labels for routing.
func (s *Server) trelloListCards(ctx context.Context, listID string) ([]trelloCard, error) {
	u := fmt.Sprintf("https://api.trello.com/1/lists/%s/cards?key=%s&token=%s&fields=name,desc,idList,url,labels",
		listID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	return s.trelloGetCards(ctx, u)
}

// Trello API: post a comment on a card.
func (s *Server) trelloAddComment(ctx context.Context, cardID, text string) error {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s/actions/comments?key=%s&token=%s",
		cardID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	body, _ := json.Marshal(map[string]string{"text": text})
	return s.trelloRequest(ctx, http.MethodPost, u, body)
}

// Trello API: move a card to a different list.
func (s *Server) trelloMoveCard(ctx context.Context, cardID, listID string) error {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s?key=%s&token=%s",
		cardID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	body, _ := json.Marshal(map[string]string{"idList": listID})
	return s.trelloRequest(ctx, http.MethodPut, u, body)
}

// Trello API: add a label to a card.
func (s *Server) trelloAddLabel(ctx context.Context, cardID, labelID string) error {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s/idLabels?key=%s&token=%s",
		cardID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	body, _ := json.Marshal(map[string]string{"value": labelID})
	return s.trelloRequest(ctx, http.MethodPost, u, body)
}

func (s *Server) trelloListLabels(ctx context.Context) ([]trelloLabel, error) {
	u := fmt.Sprintf("https://api.trello.com/1/boards/%s/labels?key=%s&token=%s&fields=name,color",
		boardID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return nil, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var labels []trelloLabel
	if err := json.NewDecoder(resp.Body).Decode(&labels); err != nil {
		return nil, err
	}
	return labels, nil
}

func (s *Server) trelloCreateLabel(ctx context.Context, name, color string) (string, error) {
	u := fmt.Sprintf("https://api.trello.com/1/labels?key=%s&token=%s",
		s.cfg.TrelloKey, s.cfg.TrelloToken)
	body, _ := json.Marshal(map[string]string{"name": name, "color": color, "idBoard": boardID})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.httpc.Do(req)
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return "", fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var lbl trelloLabel
	if err := json.NewDecoder(resp.Body).Decode(&lbl); err != nil {
		return "", err
	}
	return lbl.ID, nil
}

// loadLabels populates s.labels with the IDs of the labels the
// scheduler needs. Known: needs-attention, no-worktree.
func (s *Server) loadLabels(ctx context.Context) error {
	known := []struct{ name, color string }{
		{"needs-attention", "red"},
		{"no-worktree", "yellow"},
	}
	labels, err := s.trelloListLabels(ctx)
	if err != nil {
		return fmt.Errorf("list: %w", err)
	}
	byName := make(map[string]string)
	for _, l := range labels {
		if l.Name != "" {
			byName[l.Name] = l.ID
		}
	}
	for _, k := range known {
		if id, ok := byName[k.name]; ok {
			s.labels[k.name] = id
			continue
		}
		id, err := s.trelloCreateLabel(ctx, k.name, k.color)
		if err != nil {
			return fmt.Errorf("create %s: %w", k.name, err)
		}
		s.labels[k.name] = id
	}
	return nil
}

// trelloGetCards is a small wrapper used only by trelloListCards.
func (s *Server) trelloGetCards(ctx context.Context, u string) ([]trelloCard, error) {
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return nil, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var cards []trelloCard
	if err := json.NewDecoder(resp.Body).Decode(&cards); err != nil {
		return nil, err
	}
	return cards, nil
}

func (s *Server) trelloRequest(ctx context.Context, method, u string, body []byte) error {
	req, _ := http.NewRequestWithContext(ctx, method, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}

// Opencode API: abort a session. Best-effort; failures are logged
// at the call site. Used when a card leaves doing before the model
// finished, so opencode stops generating.
func (s *Server) ocAbortSession(ctx context.Context, sessionID string) error {
	u := fmt.Sprintf("%s/session/%s/abort", s.cfg.OpenCodeBaseURL, sessionID)
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, nil)
	req.SetBasicAuth(s.cfg.OpenCodeUser, s.cfg.OpenCodePass)
	resp, err := s.httpc.Do(req)
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

// Opencode API: create a new session in cfg.WorkDir.
func (s *Server) ocCreateSession(ctx context.Context) (ocSession, error) {
	u := s.cfg.OpenCodeBaseURL + "/session?directory=" + url.QueryEscape(s.cfg.WorkDir)
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, strings.NewReader("{}"))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(s.cfg.OpenCodeUser, s.cfg.OpenCodePass)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return ocSession{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return ocSession{}, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var sess ocSession
	if err := json.NewDecoder(resp.Body).Decode(&sess); err != nil {
		return ocSession{}, err
	}
	if !strings.HasPrefix(sess.ID, "ses_") {
		return sess, fmt.Errorf("unexpected id=%q", sess.ID)
	}
	return sess, nil
}

// Opencode API: async-send a prompt to an existing session. The
// model is read from cfg.DefaultModel (validated at startup; see
// design.md §3 + req.md §11.2). Future work: per-card override via
// the "model:X" label; for v1 every card uses the binding default.
func (s *Server) ocSendPromptAsync(ctx context.Context, sessionID, prompt string) error {
	u := fmt.Sprintf("%s/session/%s/prompt_async?directory=%s",
		s.cfg.OpenCodeBaseURL, sessionID, url.QueryEscape(s.cfg.WorkDir))
	body, _ := json.Marshal(map[string]any{
		"model": map[string]string{
			"providerID": s.cfg.DefaultModel.ProviderID,
			"modelID":    s.cfg.DefaultModel.ModelID,
		},
		"parts": []map[string]string{{"type": "text", "text": prompt}},
	})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(s.cfg.OpenCodeUser, s.cfg.OpenCodePass)
	resp, err := s.httpc.Do(req)
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

// Opencode API: rename a session by setting its title via
// PATCH /session/{id}?directory={workdir}. The title is best-effort:
// the caller logs and continues on error rather than treating a
// rename failure as fatal. The directory query parameter is required
// by opencode's session router even for PATCH.
func (s *Server) ocRenameSession(ctx context.Context, sessionID, title string) error {
	u := fmt.Sprintf("%s/session/%s?directory=%s",
		s.cfg.OpenCodeBaseURL, sessionID, url.QueryEscape(s.cfg.WorkDir))
	body, _ := json.Marshal(map[string]string{"title": title})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPatch, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(s.cfg.OpenCodeUser, s.cfg.OpenCodePass)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode >= 300 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	return nil
}

// Opencode API: return the last message of a session, or nil if the
// session has no messages. Used by the finish watcher.
func (s *Server) ocGetLastMessage(ctx context.Context, sessionID string) (map[string]any, error) {
	u := fmt.Sprintf("%s/session/%s/message?limit=1", s.cfg.OpenCodeBaseURL, sessionID)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	req.SetBasicAuth(s.cfg.OpenCodeUser, s.cfg.OpenCodePass)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return nil, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var msgs []map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&msgs); err != nil {
		return nil, err
	}
	if len(msgs) == 0 {
		return nil, nil
	}
	return msgs[len(msgs)-1], nil
}
