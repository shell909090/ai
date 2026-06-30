package kanban

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
)

// ErrUnknownLabel is returned by BoardGateway when a label name cannot be resolved.
var ErrUnknownLabel = errors.New("unknown label")

// trelloCard is the Trello REST API card shape.
type trelloCard struct {
	ID     string        `json:"id"`
	Name   string        `json:"name"`
	Desc   string        `json:"desc"`
	IDList string        `json:"idList"`
	URL    string        `json:"url"`
	Labels []trelloLabel `json:"labels"`
}

// trelloLabel is the Trello REST API label shape.
type trelloLabel struct {
	ID      string `json:"id"`
	Name    string `json:"name"`
	Color   string `json:"color"`
	IDBoard string `json:"idBoard"`
}

// TrelloGateway implements BoardGateway against the Trello REST API.
// List names ("todo", "doing", "done") and label names are translated
// to Trello IDs internally; callers use only logical names.
type TrelloGateway struct {
	key      string
	token    string
	boardID  string
	lists    map[string]string // logical name → Trello list ID
	labels   map[string]string // logical label key → Trello label name
	httpc    *http.Client
	mu       sync.Mutex
	labelIDs map[string]string // Trello label name → Trello label ID (cached)
}

// NewTrelloGateway constructs a TrelloGateway from the provided config and HTTP client.
func NewTrelloGateway(cfg Config, httpc *http.Client) *TrelloGateway {
	return &TrelloGateway{
		key:      cfg.TrelloKey,
		token:    cfg.TrelloToken,
		boardID:  cfg.TrelloBoardID,
		lists:    cfg.TrelloLists,
		labels:   cfg.TrelloLabels,
		httpc:    httpc,
		labelIDs: make(map[string]string),
	}
}

func (g *TrelloGateway) listIDFor(name string) string {
	return g.lists[name]
}

func (g *TrelloGateway) listNameFor(id string) string {
	for name, lid := range g.lists {
		if lid == id {
			return name
		}
	}
	return ""
}

// toSnapshot converts a Trello-specific card to a board-neutral CardSnapshot.
func (g *TrelloGateway) toSnapshot(tc trelloCard) CardSnapshot {
	labels := make([]string, 0, len(tc.Labels))
	for _, l := range tc.Labels {
		labels = append(labels, l.Name)
	}
	return CardSnapshot{
		ID:          CardID(tc.ID),
		Title:       tc.Name,
		Description: tc.Desc,
		URL:         tc.URL,
		List:        g.listNameFor(tc.IDList),
		Labels:      labels,
	}
}

// ListCards lists all cards in the given logical list.
func (g *TrelloGateway) ListCards(ctx context.Context, listName string) ([]CardSnapshot, error) {
	listID := g.listIDFor(listName)
	if listID == "" {
		return nil, fmt.Errorf("unknown list: %s", listName)
	}
	u := fmt.Sprintf("https://api.trello.com/1/lists/%s/cards?key=%s&token=%s&fields=name,desc,idList,url,labels",
		listID, g.key, g.token)
	cards, err := g.getCards(ctx, u)
	if err != nil {
		return nil, err
	}
	snaps := make([]CardSnapshot, 0, len(cards))
	for _, c := range cards {
		snaps = append(snaps, g.toSnapshot(c))
	}
	return snaps, nil
}

// GetCard fetches a single card by ID.
func (g *TrelloGateway) GetCard(ctx context.Context, id CardID) (CardSnapshot, error) {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s?key=%s&token=%s&fields=name,desc,idList,url,labels",
		string(id), g.key, g.token)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	resp, err := g.httpc.Do(req)
	if err != nil {
		return CardSnapshot{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return CardSnapshot{}, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var tc trelloCard
	if err := json.NewDecoder(resp.Body).Decode(&tc); err != nil {
		return CardSnapshot{}, err
	}
	return g.toSnapshot(tc), nil
}

// MoveCard moves a card to the given logical list.
func (g *TrelloGateway) MoveCard(ctx context.Context, id CardID, listName string) error {
	listID := g.listIDFor(listName)
	if listID == "" {
		return fmt.Errorf("unknown list: %s", listName)
	}
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s?key=%s&token=%s", string(id), g.key, g.token)
	body, _ := json.Marshal(map[string]string{"idList": listID})
	return g.doRequest(ctx, http.MethodPut, u, body)
}

// AddComment adds a comment to a card.
func (g *TrelloGateway) AddComment(ctx context.Context, id CardID, text string) error {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s/actions/comments?key=%s&token=%s",
		string(id), g.key, g.token)
	body, _ := json.Marshal(map[string]string{"text": text})
	return g.doRequest(ctx, http.MethodPost, u, body)
}

// AddLabel adds a label (by name) to a card, resolving the name to a Trello label ID.
func (g *TrelloGateway) AddLabel(ctx context.Context, id CardID, labelName string) error {
	labelID, err := g.resolveLabelID(ctx, labelName)
	if err != nil {
		return fmt.Errorf("%w: %s", ErrUnknownLabel, labelName)
	}
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s/idLabels?key=%s&token=%s", string(id), g.key, g.token)
	body, _ := json.Marshal(map[string]string{"value": labelID})
	return g.doRequest(ctx, http.MethodPost, u, body)
}

// RemoveLabel removes a label (by name) from a card, resolving the name to a Trello label ID.
func (g *TrelloGateway) RemoveLabel(ctx context.Context, id CardID, labelName string) error {
	labelID, err := g.resolveLabelID(ctx, labelName)
	if err != nil {
		return fmt.Errorf("%w: %s", ErrUnknownLabel, labelName)
	}
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s/idLabels/%s?key=%s&token=%s",
		string(id), labelID, g.key, g.token)
	return g.doRequest(ctx, http.MethodDelete, u, nil)
}

// CreateCard creates a new card in the given logical list with the given label names.
func (g *TrelloGateway) CreateCard(ctx context.Context, listName, title, description string, labelNames []string) (CardSnapshot, error) {
	listID := g.listIDFor(listName)
	if listID == "" {
		return CardSnapshot{}, fmt.Errorf("unknown list: %s", listName)
	}
	var labelIDs []string
	for _, name := range labelNames {
		id, err := g.resolveLabelID(ctx, name)
		if err != nil {
			return CardSnapshot{}, fmt.Errorf("%w: %s", ErrUnknownLabel, name)
		}
		labelIDs = append(labelIDs, id)
	}
	u := fmt.Sprintf("https://api.trello.com/1/cards?key=%s&token=%s", g.key, g.token)
	body, _ := json.Marshal(map[string]any{
		"name":     title,
		"desc":     description,
		"idList":   listID,
		"idLabels": strings.Join(labelIDs, ","),
	})
	req, _ := http.NewRequestWithContext(ctx, http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := g.httpc.Do(req)
	if err != nil {
		return CardSnapshot{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return CardSnapshot{}, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var tc trelloCard
	if err := json.NewDecoder(resp.Body).Decode(&tc); err != nil {
		return CardSnapshot{}, err
	}
	return g.toSnapshot(tc), nil
}

// resolveLabelID returns the Trello label ID for a label name, using a cached lookup.
func (g *TrelloGateway) resolveLabelID(ctx context.Context, name string) (string, error) {
	g.mu.Lock()
	if id, ok := g.labelIDs[name]; ok {
		g.mu.Unlock()
		return id, nil
	}
	g.mu.Unlock()

	if g.boardID == "" {
		return "", fmt.Errorf("board_id not configured, cannot resolve label %q", name)
	}

	labels, err := g.listBoardLabels(ctx)
	if err != nil {
		return "", fmt.Errorf("list board labels: %w", err)
	}

	g.mu.Lock()
	for _, l := range labels {
		if l.Name != "" {
			g.labelIDs[l.Name] = l.ID
		}
	}
	id := g.labelIDs[name]
	g.mu.Unlock()

	if id == "" {
		return "", fmt.Errorf("label %q not found on board", name)
	}
	return id, nil
}

// listBoardLabels fetches all labels from the configured Trello board.
func (g *TrelloGateway) listBoardLabels(ctx context.Context) ([]trelloLabel, error) {
	u := fmt.Sprintf("https://api.trello.com/1/boards/%s/labels?key=%s&token=%s&fields=name,color",
		g.boardID, g.key, g.token)
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	resp, err := g.httpc.Do(req)
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

// getCards fetches cards from the given Trello URL.
func (g *TrelloGateway) getCards(ctx context.Context, u string) ([]trelloCard, error) {
	req, _ := http.NewRequestWithContext(ctx, http.MethodGet, u, nil)
	resp, err := g.httpc.Do(req)
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

// doRequest performs an HTTP request with an optional JSON body.
func (g *TrelloGateway) doRequest(ctx context.Context, method, u string, body []byte) error {
	var reqBody io.Reader
	if body != nil {
		reqBody = bytes.NewReader(body)
	}
	req, _ := http.NewRequestWithContext(ctx, method, u, reqBody)
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	resp, err := g.httpc.Do(req)
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
