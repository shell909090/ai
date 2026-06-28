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

// Trello API: list cards in a list.
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

// Trello API: add a label (by ID) to a card.
func (s *Server) trelloAddLabel(ctx context.Context, cardID, labelID string) error {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s/idLabels?key=%s&token=%s",
		cardID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	body, _ := json.Marshal(map[string]string{"value": labelID})
	return s.trelloRequest(ctx, http.MethodPost, u, body)
}

// Trello API: list all labels on a board.
func (s *Server) trelloListBoardLabels(ctx context.Context, boardID string) ([]trelloLabel, error) {
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

// Opencode API: abort a session.
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

// Opencode API: create a new session using the given working directory.
func (s *Server) ocCreateSession(ctx context.Context, model ModelRef, workdir string) (string, error) {
	u := s.cfg.OpenCodeBaseURL + "/session"
	if workdir != "" {
		u += "?directory=" + url.QueryEscape(workdir)
	}
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, strings.NewReader("{}"))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(s.cfg.OpenCodeUser, s.cfg.OpenCodePass)
	resp, err := s.httpc.Do(req)
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

// Opencode API: send a prompt to a session asynchronously.
func (s *Server) ocSendPrompt(ctx context.Context, sessionID string, model ModelRef, prompt string) error {
	u := fmt.Sprintf("%s/session/%s/prompt_async", s.cfg.OpenCodeBaseURL, sessionID)
	body, _ := json.Marshal(map[string]any{
		"model": map[string]string{
			"providerID": model.ProviderID,
			"modelID":    model.ModelID,
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

// Opencode API: return the last message of a session, or nil if empty.
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
