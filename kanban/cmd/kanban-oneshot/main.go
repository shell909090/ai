// kanban-oneshot is a one-shot end-to-end smoke test for T012.
//
// Reads .env, pulls the first card in the "doing" list of the configured
// Trello board, creates an opencode session in this directory, posts a
// "▶️ Started" comment to the card, sends the card description as an
// async prompt, then exits. Does not poll, does not wait for completion.
package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	// "strconv"
	"strings"
	"time"
)

const (
	boardID = "6a369a37d68f530666bce32e"
	doingID = "6a36a4625fe4a561ecc34bc6"
)

type config struct {
	TrelloKey       string
	TrelloToken     string
	OpenCodeUser    string
	OpenCodePass    string
	OpenCodeBaseURL string
	WorkDir         string
	HTTPTimeout     time.Duration
}

type trelloCard struct {
	ID     string `json:"id"`
	Name   string `json:"name"`
	Desc   string `json:"desc"`
	IDList string `json:"idList"`
	URL    string `json:"url"`
}

type ocSession struct {
	ID        string `json:"id"`
	Slug      string `json:"slug"`
	Directory string `json:"directory"`
	ProjectID string `json:"projectID"`
}

type report struct {
	Step   string `json:"step"`
	Result string `json:"result"`
	Detail string `json:"detail,omitempty"`
}

func main() {
	cfg, err := loadConfig()
	if err != nil {
		die("config: %v", err)
	}
	w := os.Stdout
	logf(w, "config.loaded", "PASS", "board=%s doing=%s workdir=%s model=opencode-go/minimax-m3", boardID, doingID, cfg.WorkDir)

	cards, err := trelloListCards(cfg, doingID)
	if err != nil {
		die("trello.listCards: %v", err)
	}
	if len(cards) == 0 {
		logf(w, "trello.cards", "SKIPPED", "no card in doing list")
		return
	}
	card := cards[0]
	logf(w, "trello.cards", "PASS", "id=%s name=%q", card.ID, card.Name)
	if card.Desc == "" {
		logf(w, "prompt.source", "WARN", "card has empty desc, using name as prompt")
	}

	sess, err := ocCreateSession(cfg, cfg.WorkDir)
	if err != nil {
		die("opencode.createSession: %v", err)
	}
	logf(w, "opencode.session", "PASS", "id=%s directory=%s", sess.ID, sess.Directory)

	comment := fmt.Sprintf("▶️ Started session %s\nWorkspace: %s\nModel: opencode-go/minimax-m3", sess.ID, sess.Directory)
	if err := trelloAddComment(cfg, card.ID, comment); err != nil {
		logf(w, "trello.comment", "FAIL", "%v", err)
	} else {
		logf(w, "trello.comment", "PASS", "started-session comment posted")
	}

	prompt := card.Desc
	if prompt == "" {
		prompt = card.Name
	}
	if err := ocSendPromptAsync(cfg, sess.ID, cfg.WorkDir, prompt); err != nil {
		die("opencode.prompt: %v", err)
	}
	logf(w, "opencode.prompt", "PASS", "session=%s body_len=%d", sess.ID, len(prompt))

	logf(w, "summary", "PASS", "card=%s session=%s", card.ID, sess.ID)
}

func loadConfig() (config, error) {
	c := config{
		OpenCodeBaseURL: envOr("KANBAN_OPENCODE_URL", "http://127.0.0.1:8567"),
		WorkDir:         envOr("KANBAN_WORKDIR", "/home/shell/tmp/kanban"),
		HTTPTimeout:     15 * time.Second,
	}
	env, err := readDotenv(".env")
	if err != nil {
		return c, fmt.Errorf("read .env: %w", err)
	}
	c.TrelloKey = env["TRELLO_API_KEY"]
	c.TrelloToken = env["TRELLO_TOKEN"]
	c.OpenCodeUser = env["OPENCODE_SERVER_USERNAME"]
	c.OpenCodePass = env["OPENCODE_SERVER_PASSWORD"]
	if c.TrelloKey == "" || c.TrelloToken == "" {
		return c, fmt.Errorf("TRELLO_API_KEY or TRELLO_TOKEN missing in .env")
	}
	if c.OpenCodeUser == "" || c.OpenCodePass == "" {
		return c, fmt.Errorf("OPENCODE_SERVER_USERNAME or OPENCODE_SERVER_PASSWORD missing in .env")
	}
	return c, nil
}

func envOr(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func readDotenv(path string) (map[string]string, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	out := make(map[string]string)
	for _, line := range strings.Split(string(data), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		eq := strings.IndexByte(line, '=')
		if eq <= 0 {
			continue
		}
		k := strings.TrimSpace(line[:eq])
		v := strings.TrimSpace(line[eq+1:])
		out[k] = v
	}
	return out, nil
}

func die(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "FATAL: "+format+"\n", args...)
	os.Exit(2)
}

func logf(w io.Writer, step, result, format string, args ...any) {
	rec := report{Step: step, Result: result}
	if format != "" {
		rec.Detail = fmt.Sprintf(format, args...)
	}
	_ = json.NewEncoder(w).Encode(rec)
}

func trelloListCards(cfg config, listID string) ([]trelloCard, error) {
	u := fmt.Sprintf("https://api.trello.com/1/lists/%s/cards?key=%s&token=%s&fields=name,desc,idList,url",
		listID, cfg.TrelloKey, cfg.TrelloToken)
	req, _ := http.NewRequest(http.MethodGet, u, nil)
	resp, err := http.DefaultClient.Do(req)
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

func trelloAddComment(cfg config, cardID, text string) error {
	u := fmt.Sprintf("https://api.trello.com/1/cards/%s/actions/comments?key=%s&token=%s",
		cardID, cfg.TrelloKey, cfg.TrelloToken)
	body, _ := json.Marshal(map[string]string{"text": text})
	req, _ := http.NewRequest(http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
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

func ocCreateSession(cfg config, directory string) (ocSession, error) {
	u := cfg.OpenCodeBaseURL + "/session?directory=" + url.QueryEscape(directory)
	req, _ := http.NewRequest(http.MethodPost, u, strings.NewReader("{}"))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(cfg.OpenCodeUser, cfg.OpenCodePass)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return ocSession{}, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		b, _ := io.ReadAll(io.LimitReader(resp.Body, 1024))
		return ocSession{}, fmt.Errorf("status=%d body=%s", resp.StatusCode, string(b))
	}
	var s ocSession
	if err := json.NewDecoder(resp.Body).Decode(&s); err != nil {
		return ocSession{}, err
	}
	if !strings.HasPrefix(s.ID, "ses_") {
		return s, fmt.Errorf("unexpected id=%q", s.ID)
	}
	return s, nil
}

func ocSendPromptAsync(cfg config, sessionID, directory, prompt string) error {
	u := fmt.Sprintf("%s/session/%s/prompt_async?directory=%s",
		cfg.OpenCodeBaseURL, sessionID, url.QueryEscape(directory))
	body, _ := json.Marshal(map[string]any{
		"model": map[string]string{"providerID": "opencode-go", "modelID": "minimax-m3"},
		"parts": []map[string]string{{"type": "text", "text": prompt}},
	})
	req, _ := http.NewRequest(http.MethodPost, u, bytes.NewReader(body))
	req.Header.Set("Content-Type", "application/json")
	req.SetBasicAuth(cfg.OpenCodeUser, cfg.OpenCodePass)
	resp, err := http.DefaultClient.Do(req)
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

// unused but kept for future; suppress unused warning if go vet cares
