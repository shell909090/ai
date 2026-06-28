package kanban

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// ModelRef identifies an opencode model as a (provider, model) pair.
type ModelRef struct {
	ProviderID string
	ModelID    string
}

// AllowedModel is one entry in AllowedModels: a card's "model:X" label
// can pick this entry if X matches Label.
type AllowedModel struct {
	Label      string
	ProviderID string
	ModelID    string
}

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
	OpenCodeUser       string
	OpenCodePass       string
	OpenCodeBaseURL    string
	WorkDir            string
	PollInterval       time.Duration
	HTTPTimeout        time.Duration
	HTTPListen         string
	MaxDoingTotal      int
	MaxDoingPerProject int
	AbortTimeout       time.Duration
	SummaryTimeout     time.Duration
	HookDefaultTimeout time.Duration
	HookMaxOutputBytes int
	DefaultModel       ModelRef
	AllowedModels      []AllowedModel
	AllowedProjects    []AllowedProject
	// TrelloLists maps logical list names (todo/doing/done) to Trello list IDs.
	TrelloLists map[string]string
	// TrelloLabels maps logical label keys (attention) to Trello label names.
	TrelloLabels map[string]string
}

// LoadConfig reads ./.env and ./config.yaml, returning a merged Config.
func LoadConfig() (Config, error) {
	c := Config{
		OpenCodeBaseURL:    envOr("KANBAN_OPENCODE_URL", "http://127.0.0.1:4096"),
		WorkDir:            os.Getenv("KANBAN_WORKDIR"),
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
	yamlCfg, err := loadYAMLConfig("config.yaml")
	if err != nil {
		return c, fmt.Errorf("read config.yaml: %w", err)
	}
	mergeYAMLIntoConfig(&c, yamlCfg)
	return c, nil
}

// yamlConfig mirrors the on-disk config.yaml structure.
type yamlConfig struct {
	Trello struct {
		BoardID string            `yaml:"board_id"`
		Lists   map[string]string `yaml:"lists"`
		Labels  map[string]string `yaml:"labels"`
	} `yaml:"trello"`
	Opencode struct {
		BaseURL       string         `yaml:"base_url"`
		WorkDir       string         `yaml:"workdir"`
		UsernameEnv   string         `yaml:"username_env"`
		PasswordEnv   string         `yaml:"password_env"`
		DefaultModel  yamlModel      `yaml:"default_model"`
		AllowedModels []yamlModelRow `yaml:"allowed_models"`
	} `yaml:"opencode"`
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
	if yc.Opencode.BaseURL != "" {
		c.OpenCodeBaseURL = yc.Opencode.BaseURL
	}
	if yc.Opencode.WorkDir != "" {
		c.WorkDir = yc.Opencode.WorkDir
	}
	if yc.Opencode.DefaultModel.ProviderID != "" {
		c.DefaultModel = ModelRef{
			ProviderID: yc.Opencode.DefaultModel.ProviderID,
			ModelID:    yc.Opencode.DefaultModel.ModelID,
		}
	}
	for _, m := range yc.Opencode.AllowedModels {
		c.AllowedModels = append(c.AllowedModels, AllowedModel{
			Label:      m.Label,
			ProviderID: m.ProviderID,
			ModelID:    m.ModelID,
		})
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
	if c.DefaultModel.ProviderID == "" || c.DefaultModel.ModelID == "" {
		return fmt.Errorf("config: opencode.default_model is required (providerID + modelID)")
	}
	for _, l := range []string{"todo", "doing", "done"} {
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
	for i, p := range c.AllowedProjects {
		if p.Label == "" {
			return fmt.Errorf("config: projects.allowed[%d].label is required", i)
		}
		if p.Name == "" {
			return fmt.Errorf("config: projects.allowed[%d] (%s).name is required", i, p.Label)
		}
	}
	return nil
}

// hasProjLabel reports whether a card has at least one proj:* label.
// Cards without a proj:* label are not AI-managed and must be ignored by the scheduler.
func hasProjLabel(card trelloCard) bool {
	for _, l := range card.Labels {
		if strings.HasPrefix(l.Name, "proj:") {
			return true
		}
	}
	return false
}

// parseProj extracts the project name from a card's proj:* label.
// Callers must check hasProjLabel first; cards without a proj:* label are not AI-managed.
// Returns ("", error) if no proj:* label is present, or if there are multiple or unknown labels.
func parseProj(card trelloCard, cfg Config) (string, error) {
	var matches []string
	for _, l := range card.Labels {
		if strings.HasPrefix(l.Name, "proj:") {
			matches = append(matches, l.Name)
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

// parseModel extracts the model from a card's labels.
// Returns (defaultModel, nil) if no model:* label is present.
// Returns (ModelRef{}, error) if parsing fails (multiple or unknown label).
func parseModel(card trelloCard, cfg Config) (ModelRef, error) {
	var matches []string
	for _, l := range card.Labels {
		if strings.HasPrefix(l.Name, "model:") {
			matches = append(matches, l.Name)
		}
	}
	if len(matches) == 0 {
		return cfg.DefaultModel, nil
	}
	if len(matches) > 1 {
		return ModelRef{}, fmt.Errorf("multiple model labels: %s", strings.Join(matches, ", "))
	}
	labelName := matches[0]
	for _, m := range cfg.AllowedModels {
		if m.Label == labelName {
			return ModelRef{ProviderID: m.ProviderID, ModelID: m.ModelID}, nil
		}
	}
	return ModelRef{}, fmt.Errorf("unknown model label: %s", labelName)
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
