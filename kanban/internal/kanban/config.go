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

// AllowedProject is one entry in AllowedProjects: a card's "proj:X"
// label can pick this entry if X matches Label.
type AllowedProject struct {
	Label        string
	Name         string
	Root         string // absolute path to the project root directory
	KanbanConfig string // path to .kanban.yml relative to Root; defaults to ".kanban.yml"
}

// findProject returns the AllowedProject with the given resolved project name.
func findProject(projName string, cfg Config) (AllowedProject, bool) {
	for _, p := range cfg.AllowedProjects {
		if p.Name == projName {
			return p, true
		}
	}
	return AllowedProject{}, false
}

// Config holds the runtime configuration. Secrets come from .env;
// non-sensitive binding config comes from config.yaml.
type Config struct {
	TrelloKey          string
	TrelloToken        string
	TrelloBoardID      string
	PollInterval       time.Duration
	HTTPTimeout        time.Duration
	HTTPListen         string
	MaxDoingTotal      int
	MaxDoingPerProject int
	AbortTimeout       time.Duration
	SummaryTimeout     time.Duration
	HookDefaultTimeout time.Duration
	HookMaxOutputBytes int
	ControlToken       string // resolved token value (from ControlTokenEnv at load time)
	ControlTokenEnv    string // env var name that holds the token
	DefaultAgent       string
	Agents             map[string]AgentConfig
	AllowedProjects    []AllowedProject
	// TrelloLists maps logical list names (todo/doing/done) to Trello list IDs.
	TrelloLists map[string]string
	// TrelloLabels maps logical label keys (attention) to Trello label names.
	TrelloLabels map[string]string
}

// LoadConfig reads ./.env and ./config.yaml, returning a merged Config and the env map.
func LoadConfig() (Config, map[string]string, error) {
	c := Config{
		HTTPTimeout:        15 * time.Second,
		PollInterval:       5 * time.Second,
		HTTPListen:         "127.0.0.1:8087",
		AbortTimeout:       60 * time.Second,
		SummaryTimeout:     60 * time.Second,
		MaxDoingTotal:      envInt("KANBAN_MAX_DOING_TOTAL", 3),
		MaxDoingPerProject: envInt("KANBAN_MAX_DOING_PER_PROJECT", 1),
	}
	env, err := readDotenv(".env")
	if err != nil {
		return c, nil, fmt.Errorf("read .env: %w", err)
	}
	c.TrelloKey = env["TRELLO_API_KEY"]
	c.TrelloToken = env["TRELLO_TOKEN"]
	if c.TrelloKey == "" || c.TrelloToken == "" {
		return c, nil, fmt.Errorf("TRELLO_API_KEY or TRELLO_TOKEN missing in .env")
	}
	yamlCfg, err := loadYAMLConfig("config.yaml")
	if err != nil {
		return c, nil, fmt.Errorf("read config.yaml: %w", err)
	}
	mergeYAMLIntoConfig(&c, yamlCfg)
	// Resolve control token: .env takes precedence over real env so that users
	// can keep all secrets in one place. os.Getenv fallback (done in
	// mergeYAMLIntoConfig) supports deployments that inject secrets as real env vars.
	if c.ControlTokenEnv != "" && c.ControlToken == "" {
		if v := env[c.ControlTokenEnv]; v != "" {
			c.ControlToken = v
		}
	}
	return c, env, nil
}

// yamlConfig mirrors the on-disk config.yaml structure.
type yamlConfig struct {
	Trello struct {
		BoardID string            `yaml:"board_id"`
		Lists   map[string]string `yaml:"lists"`
		Labels  map[string]string `yaml:"labels"`
	} `yaml:"trello"`
	// Opencode is kept for backward compatibility with old configs.
	Opencode struct {
		BaseURL       string         `yaml:"base_url"`
		WorkDir       string         `yaml:"workdir"`
		UsernameEnv   string         `yaml:"username_env"`
		PasswordEnv   string         `yaml:"password_env"`
		DefaultModel  yamlModel      `yaml:"default_model"`
		AllowedModels []yamlModelRow `yaml:"allowed_models"`
	} `yaml:"opencode"`
	Kanban struct {
		DefaultAgent string `yaml:"default_agent"`
	} `yaml:"kanban"`
	Agents   map[string]map[string]any `yaml:"agents"`
	Projects struct {
		Allowed []yamlProjRow `yaml:"allowed"`
	} `yaml:"projects"`
	Capacity struct {
		Total      int `yaml:"total"`
		PerProject int `yaml:"per_project"`
	} `yaml:"capacity"`
	Timer struct {
		Interval       string `yaml:"interval"`
		AbortTimeout   string `yaml:"abort_timeout"`
		SummaryTimeout string `yaml:"summary_timeout"`
	} `yaml:"timer"`
	Hooks struct {
		DefaultTimeout string `yaml:"default_timeout"`
		MaxOutputBytes int    `yaml:"max_output_bytes"`
	} `yaml:"hooks"`
	Control struct {
		TokenEnv string `yaml:"token_env"`
	} `yaml:"control"`
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

type yamlProjRow struct {
	Label        string `yaml:"label"`
	Name         string `yaml:"name"`
	Root         string `yaml:"root"`
	KanbanConfig string `yaml:"kanban_config"`
}

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

func mergeYAMLIntoConfig(c *Config, yc yamlConfig) {
	if yc.Trello.BoardID != "" {
		c.TrelloBoardID = yc.Trello.BoardID
	}
	if len(yc.Trello.Lists) > 0 {
		c.TrelloLists = yc.Trello.Lists
	}
	if len(yc.Trello.Labels) > 0 {
		c.TrelloLabels = yc.Trello.Labels
	}

	// New kanban.default_agent / agents config.
	if yc.Kanban.DefaultAgent != "" {
		c.DefaultAgent = yc.Kanban.DefaultAgent
	}
	if len(yc.Agents) > 0 {
		c.Agents = make(map[string]AgentConfig, len(yc.Agents))
		for name, raw := range yc.Agents {
			agentType, _ := raw["type"].(string)
			c.Agents[name] = AgentConfig{Type: agentType, Raw: raw}
		}
	}

	// Backward compatibility: if no agents configured and old opencode section present,
	// synthesize an "opencode-default" agent entry.
	if len(c.Agents) == 0 && (yc.Opencode.BaseURL != "" || yc.Opencode.DefaultModel.ProviderID != "") {
		raw := map[string]any{
			"type":         "opencode",
			"base_url":     yc.Opencode.BaseURL,
			"workdir":      yc.Opencode.WorkDir,
			"username_env": yc.Opencode.UsernameEnv,
			"password_env": yc.Opencode.PasswordEnv,
		}
		if yc.Opencode.DefaultModel.ProviderID != "" {
			raw["default_model"] = map[string]any{
				"providerID": yc.Opencode.DefaultModel.ProviderID,
				"modelID":    yc.Opencode.DefaultModel.ModelID,
			}
		}
		if len(yc.Opencode.AllowedModels) > 0 {
			var models []any
			for _, m := range yc.Opencode.AllowedModels {
				models = append(models, map[string]any{
					"label": m.Label, "providerID": m.ProviderID, "modelID": m.ModelID,
				})
			}
			raw["allowed_models"] = models
		}
		// Use the user-specified default_agent name if set, otherwise use "opencode-default".
		agentKey := c.DefaultAgent
		if agentKey == "" {
			agentKey = "opencode-default"
			c.DefaultAgent = agentKey
		}
		c.Agents = map[string]AgentConfig{
			agentKey: {Type: "opencode", Raw: raw},
		}
	}

	for _, p := range yc.Projects.Allowed {
		kc := p.KanbanConfig
		if kc == "" {
			kc = ".kanban.yml"
		}
		c.AllowedProjects = append(c.AllowedProjects, AllowedProject{
			Label:        p.Label,
			Name:         p.Name,
			Root:         p.Root,
			KanbanConfig: kc,
		})
	}
	if d, err := time.ParseDuration(yc.Hooks.DefaultTimeout); err == nil && d > 0 {
		c.HookDefaultTimeout = d
	}
	if yc.Hooks.MaxOutputBytes > 0 {
		c.HookMaxOutputBytes = yc.Hooks.MaxOutputBytes
	}
	if yc.Control.TokenEnv != "" {
		c.ControlTokenEnv = yc.Control.TokenEnv
		c.ControlToken = os.Getenv(yc.Control.TokenEnv)
	}
	if yc.Capacity.Total > 0 {
		c.MaxDoingTotal = yc.Capacity.Total
	}
	if yc.Capacity.PerProject > 0 {
		c.MaxDoingPerProject = yc.Capacity.PerProject
	}
	if d, err := time.ParseDuration(yc.Timer.Interval); err == nil && d > 0 {
		c.PollInterval = d
	}
	if d, err := time.ParseDuration(yc.Timer.AbortTimeout); err == nil && d > 0 {
		c.AbortTimeout = d
	}
	if d, err := time.ParseDuration(yc.Timer.SummaryTimeout); err == nil && d > 0 {
		c.SummaryTimeout = d
	}
}

// Validate enforces config requirements at startup.
func (c Config) Validate() error {
	if c.DefaultAgent == "" {
		return fmt.Errorf("config: kanban.default_agent is required")
	}
	if c.Agents == nil {
		return fmt.Errorf("config: default agent %q not found in agents", c.DefaultAgent)
	}
	if _, ok := c.Agents[c.DefaultAgent]; !ok {
		return fmt.Errorf("config: default agent %q not found in agents", c.DefaultAgent)
	}
	for name, ac := range c.Agents {
		if ac.Type == "" {
			return fmt.Errorf("config: agent %q missing type", name)
		}
	}
	if c.TrelloBoardID == "" {
		return fmt.Errorf("config: trello.board_id is required")
	}
	for _, l := range []string{"todo", "doing", "done"} {
		if c.TrelloLists[l] == "" {
			return fmt.Errorf("config: trello.lists.%s is required", l)
		}
	}
	if c.TrelloLabels["attention"] == "" {
		return fmt.Errorf("config: trello.labels.attention is required")
	}
	for i, p := range c.AllowedProjects {
		if p.Label == "" {
			return fmt.Errorf("config: projects.allowed[%d].label is required", i)
		}
		if p.Name == "" {
			return fmt.Errorf("config: projects.allowed[%d] (%s).name is required", i, p.Label)
		}
		if p.Root == "" {
			return fmt.Errorf("config: projects.allowed[%d] (%s).root is required", i, p.Label)
		}
		if !filepath.IsAbs(p.Root) {
			return fmt.Errorf("config: projects.allowed[%d] (%s).root must be an absolute path, got %q", i, p.Label, p.Root)
		}
	}
	return nil
}

// parseAgent extracts the agent name from a card's agent:* label.
// Returns (defaultAgent, nil) if no agent:* label is present.
// Returns ("", error) if parsing fails (multiple or unknown label).
func parseAgent(card CardSnapshot, cfg Config) (string, error) {
	var matches []string
	for _, l := range card.Labels {
		if strings.HasPrefix(l, "agent:") {
			matches = append(matches, l)
		}
	}
	if len(matches) == 0 {
		if cfg.DefaultAgent == "" {
			return "", fmt.Errorf("no agent:* label and no default agent configured")
		}
		if _, ok := cfg.Agents[cfg.DefaultAgent]; !ok {
			return "", fmt.Errorf("default agent %q not found in agents config", cfg.DefaultAgent)
		}
		return cfg.DefaultAgent, nil
	}
	if len(matches) > 1 {
		return "", fmt.Errorf("multiple agent:* labels: %s", strings.Join(matches, ", "))
	}
	name := strings.TrimPrefix(matches[0], "agent:")
	if _, ok := cfg.Agents[name]; !ok {
		return "", fmt.Errorf("unknown agent label: %s", matches[0])
	}
	return name, nil
}

// hasProjLabel reports whether a card has at least one proj:* label.
// Cards without a proj:* label are not AI-managed and must be ignored by the scheduler.
func hasProjLabel(card CardSnapshot) bool {
	for _, l := range card.Labels {
		if strings.HasPrefix(l, "proj:") {
			return true
		}
	}
	return false
}

// parseProj extracts the project name from a card's proj:* label.
// Callers must check hasProjLabel first; cards without a proj:* label are not AI-managed.
// Returns ("", error) if no proj:* label is present, or if there are multiple or unknown labels.
func parseProj(card CardSnapshot, cfg Config) (string, error) {
	var matches []string
	for _, l := range card.Labels {
		if strings.HasPrefix(l, "proj:") {
			matches = append(matches, l)
		}
	}
	if len(matches) == 0 {
		return "", fmt.Errorf("no proj:* label")
	}
	if len(matches) > 1 {
		return "", fmt.Errorf("multiple proj labels: %s", strings.Join(matches, ", "))
	}
	labelName := matches[0]
	for _, p := range cfg.AllowedProjects {
		if p.Label == labelName {
			return p.Name, nil
		}
	}
	return "", fmt.Errorf("unknown proj label: %s", labelName)
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
