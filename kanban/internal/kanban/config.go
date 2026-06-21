package kanban

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config holds the runtime configuration. Fields are exported because
// callers (cmd/kanband) assemble the struct from flags + LoadConfig().
type Config struct {
	TrelloKey       string
	TrelloToken     string
	OpenCodeUser    string
	OpenCodePass    string
	OpenCodeBaseURL string
	WorkDir         string
	PollInterval    time.Duration
	HTTPTimeout     time.Duration
	HTTPListen      string
	IdleInterval    time.Duration

	// MaxDoingTotal is the global cap on cards in doing across all
	// projects. Auto-promotion from todo stops when this is reached.
	MaxDoingTotal int
	// MaxDoingPerProject is the per-project cap. Project is read from
	// the card's "proj:X" label (X is the project name; "default" if
	// no such label). Auto-promotion stops when the target project's
	// count reaches this.
	MaxDoingPerProject int
}

// LoadConfig reads ./.env (if present) and returns a Config populated
// with the relevant variables. Defaults are applied for intervals and
// the listen address. The caller is expected to override WorkDir
// (typically via a -workdir flag) and concurrency limits (typically
// via -max-total / -max-per-project flags) before calling New.
func LoadConfig() (Config, error) {
	c := Config{
		OpenCodeBaseURL:    envOr("KANBAN_OPENCODE_URL", "http://127.0.0.1:4096"),
		WorkDir:            os.Getenv("KANBAN_WORKDIR"),
		HTTPTimeout:        15 * time.Second,
		PollInterval:       5 * time.Second,
		HTTPListen:         "127.0.0.1:8087",
		IdleInterval:       10 * time.Second,
		MaxDoingTotal:      envInt("KANBAN_MAX_DOING_TOTAL", 2),
		MaxDoingPerProject: envInt("KANBAN_MAX_DOING_PER_PROJECT", 1),
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
		return c, fmt.Errorf("TRELLO_API_KEY or TRELLO_TOKEN missing")
	}
	if c.OpenCodeUser == "" || c.OpenCodePass == "" {
		return c, fmt.Errorf("OPENCODE_SERVER_USERNAME or OPENCODE_SERVER_PASSWORD missing")
	}
	return c, nil
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
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
		out[strings.TrimSpace(line[:eq])] = strings.TrimSpace(line[eq+1:])
	}
	return out, nil
}
