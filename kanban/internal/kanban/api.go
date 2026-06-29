package kanban

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
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
	var reqBody io.Reader
	if body != nil {
		reqBody = bytes.NewReader(body)
	}
	req, _ := http.NewRequestWithContext(ctx, method, u, reqBody)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
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

// Trello API: fetch a single card by ID.
func (s *Server) trelloGetCard(ctx context.Context, cardID string) (trelloCard, error) {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s?key=%s&token=%s&fields=name,desc,idList,url,labels",
		cardID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	resp, err := s.httpc.Do(req)
	if err != nil {
		return trelloCard{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return trelloCard{}, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var card trelloCard
	if err := json.NewDecoder(resp.Body).Decode(&card); err != nil {
		return trelloCard{}, err
	}
	return card, nil
}

// Trello API: create a card in the given list with optional label IDs.
func (s *Server) trelloCreateCard(ctx context.Context, listID, title, desc string, labelIDs []string) (trelloCard, error) {
	u := fmt.Sprintf("https://api.trello.com/1/cards?key=%s&token=%s", s.cfg.TrelloKey, s.cfg.TrelloToken)
	body, _ := json.Marshal(map[string]any{
		"name":     title,
		"desc":     desc,
		"idList":   listID,
		"idLabels": strings.Join(labelIDs, ","),
	})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := s.httpc.Do(req)
	if err != nil {
		return trelloCard{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return trelloCard{}, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var card trelloCard
	if err := json.NewDecoder(resp.Body).Decode(&card); err != nil {
		return trelloCard{}, err
	}
	return card, nil
}

// Trello API: remove a label (by ID) from a card.
func (s *Server) trelloRemoveLabel(ctx context.Context, cardID, labelID string) error {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s/idLabels/%s?key=%s&token=%s",
		cardID, labelID, s.cfg.TrelloKey, s.cfg.TrelloToken)
	return s.trelloRequest(ctx, http.MethodDelete, u, nil)
}
