package kanban

import (
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// ModelRef identifies an opencode model as a (provider, model) pair.
// Both fields are non-empty.
type ModelRef struct {
	ProviderID string
	ModelID    string
}

// AllowedModel is one entry in cfg.AllowedModels: a card's "model:X"
// label can pick this entry if X matches Label.
type AllowedModel struct {
	Label      string
	ProviderID string
	ModelID    string
}

// AllowedPath is one entry in cfg.AllowedPaths: a card's "proj:X"
// label can pick this entry if X matches Label.
type AllowedPath struct {
	Label string
	Path  string
}

// Config holds the runtime configuration. Fields are exported because
// callers (cmd/kanband) assemble the struct from flags + LoadConfig().
// Secrets (Trello / opencode credentials) come from .env via
// readDotenv; non-sensitive binding config comes from config.yaml via
// LoadYAMLConfig.
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

	// DefaultModel is the binding's default opencode model, used when
	// a card has no "model:X" label. Required; check-config fails if
	// ProviderID or ModelID is empty.
	DefaultModel ModelRef
	// AllowedModels is the allowlist of models a card can pick via
	// "model:X" label. Optional; when empty, cards cannot override.
	AllowedModels []AllowedModel
	// AllowedPaths is the allowlist of repo paths a card can pick
	// via "proj:X" label. Optional; when empty, cards cannot override
	// the binding default.
	AllowedPaths []AllowedPath
	// TrelloLists maps the binding's logical list names (icebox /
	// todo / doing / done / archived) to Trello list IDs. Required
	// for every key.
	TrelloLists map[string]string
	// TrelloLabels maps the binding's logical label names
	// (human-task / no-worktree / needs-attention /
	// needs-integration-test) to Trello label IDs. Optional; absent
	// entries fall back to "find or create by name" behaviour.
	TrelloLabels map[string]string
}

// LoadConfig reads ./.env (if present) and ./config.yaml (if present),
// then returns a Config populated from both. Secrets only come from
// .env; non-sensitive binding config only comes from config.yaml.
// Defaults are applied for intervals, the listen address, and the
// cap. The caller is expected to override WorkDir (typically via a
// -workdir flag) before calling New.
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
		return c, fmt.Errorf("TRELLO_API_KEY or TRELLO_TOKEN missing in .env")
	}
	if c.OpenCodeUser == "" || c.OpenCodePass == "" {
		return c, fmt.Errorf("OPENCODE_SERVER_USERNAME or OPENCODE_SERVER_PASSWORD missing in .env")
	}
	if c.OpenCodeBaseURL == "" {
		c.OpenCodeBaseURL = "http://127.0.0.1:4096"
	}
	yamlCfg, err := loadYAMLConfig("config.yaml")
	if err != nil {
		return c, fmt.Errorf("read config.yaml: %w", err)
	}
	mergeYAMLIntoConfig(&c, yamlCfg)
	return c, nil
}

// yamlConfig mirrors the on-disk config.yaml structure. Field names
// use snake_case to match the YAML; the mapping into Config happens
// in mergeYAMLIntoConfig. Lives in this file so the disk format and
// the merge step are reviewed together.
type yamlConfig struct {
	Trello struct {
		BoardID   string            `yaml:"board_id"`
		BoardName string            `yaml:"board_name"`
		APIKeyEnv string            `yaml:"api_key_env"`
		TokenEnv  string            `yaml:"token_env"`
		Lists     map[string]string `yaml:"lists"`
		Labels    map[string]string `yaml:"labels"`
	} `yaml:"trello"`
	Opencode struct {
		BaseURL       string         `yaml:"base_url"`
		UsernameEnv   string         `yaml:"username_env"`
		PasswordEnv   string         `yaml:"password_env"`
		DefaultModel  yamlModel      `yaml:"default_model"`
		AllowedModels []yamlModelRow `yaml:"allowed_models"`
	} `yaml:"opencode"`
	Repo struct {
		MainPath     string        `yaml:"main_path"`
		MainBranch   string        `yaml:"main_branch"`
		WorktreeRoot string        `yaml:"worktree_root"`
		AllowedPaths []yamlPathRow `yaml:"allowed_paths"`
	} `yaml:"repo"`
}

type yamlModel struct {
	ProviderID string `yaml:"providerID"`
	ModelID    string `yaml:"modelID"`
}

type yamlModelRow struct {
	Label      string `yaml:"label"`
	ProviderID string `yaml:"providerID"`
	ModelID    string `yaml:"modelID"`
}

type yamlPathRow struct {
	Label string `yaml:"label"`
	Path  string `yaml:"path"`
}

// loadYAMLConfig reads ./config.yaml if present, returning an empty
// yamlConfig when the file is missing. Other read errors are
// returned. Decoded fields not in the file remain zero-valued.
func loadYAMLConfig(path string) (yamlConfig, error) {
	var yc yamlConfig
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return yc, nil
		}
		return yc, err
	}
	if err := yaml.Unmarshal(data, &yc); err != nil {
		return yc, fmt.Errorf("unmarshal: %w", err)
	}
	return yc, nil
}

// mergeYAMLIntoConfig copies non-secret binding values from the YAML
// representation into the runtime Config. Secret-related fields in
// the YAML (api_key_env, token_env, username_env, password_env) are
// intentionally not consumed here — secrets only flow through .env.
func mergeYAMLIntoConfig(c *Config, yc yamlConfig) {
	c.TrelloLists = yc.Trello.Lists
	c.TrelloLabels = yc.Trello.Labels
	c.DefaultModel = ModelRef{
		ProviderID: yc.Opencode.DefaultModel.ProviderID,
		ModelID:    yc.Opencode.DefaultModel.ModelID,
	}
	for _, m := range yc.Opencode.AllowedModels {
		c.AllowedModels = append(c.AllowedModels, AllowedModel{
			Label:      m.Label,
			ProviderID: m.ProviderID,
			ModelID:    m.ModelID,
		})
	}
	for _, p := range yc.Repo.AllowedPaths {
		c.AllowedPaths = append(c.AllowedPaths, AllowedPath{
			Label: p.Label,
			Path:  p.Path,
		})
	}
}

// Validate enforces the requirements documented in design.md §3 and
// req.md §11.2: a working Config must have a DefaultModel, sensible
// TrelloLists, and well-formed allowlist entries. Returns the first
// violation found; callers should fail-fast at startup.
func (c Config) Validate() error {
	if c.DefaultModel.ProviderID == "" || c.DefaultModel.ModelID == "" {
		return fmt.Errorf("config: opencode.default_model is required (providerID + modelID)")
	}
	for _, l := range []string{"icebox", "todo", "doing", "done", "archived"} {
		if c.TrelloLists[l] == "" {
			return fmt.Errorf("config: trello.lists.%s is required", l)
		}
	}
	for i, m := range c.AllowedModels {
		if m.Label == "" {
			return fmt.Errorf("config: opencode.allowed_models[%d].label is required", i)
		}
		if m.ProviderID == "" || m.ModelID == "" {
			return fmt.Errorf("config: opencode.allowed_models[%d] (%s) needs providerID + modelID", i, m.Label)
		}
	}
	for i, p := range c.AllowedPaths {
		if p.Label == "" {
			return fmt.Errorf("config: repo.allowed_paths[%d].label is required", i)
		}
		abs, err := filepath.Abs(p.Path)
		if err != nil {
			return fmt.Errorf("config: repo.allowed_paths[%d] (%s) abs: %w", i, p.Label, err)
		}
		info, err := os.Stat(abs)
		if err != nil {
			return fmt.Errorf("config: repo.allowed_paths[%d] (%s) stat %s: %w", i, p.Label, abs, err)
		}
		if !info.IsDir() {
			return fmt.Errorf("config: repo.allowed_paths[%d] (%s) %s is not a directory", i, p.Label, abs)
		}
	}
	return nil
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
