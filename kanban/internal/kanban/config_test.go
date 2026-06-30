package kanban

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestReadDotenv(t *testing.T) {
	dir := t.TempDir()
	path := filepath.Join(dir, ".env")
	must := func(err error) {
		t.Helper()
		if err != nil {
			t.Fatal(err)
		}
	}
	must(os.WriteFile(path, []byte(strings.Join([]string{
		"# a comment",
		"",
		"FOO=bar",
		"EMPTY=",
		"QUOTED = \"hello world\"",
		"BADLINE_NO_EQUALS",
		"KEY=value",
	}, "\n")), 0644))
	got, err := readDotenv(path)
	if err != nil {
		t.Fatal(err)
	}
	if got["FOO"] != "bar" {
		t.Errorf("FOO=%q, want bar", got["FOO"])
	}
	if got["EMPTY"] != "" {
		t.Errorf("EMPTY=%q, want empty", got["EMPTY"])
	}
	if got["QUOTED"] != "\"hello world\"" {
		t.Errorf("QUOTED=%q", got["QUOTED"])
	}
	if got["KEY"] != "value" {
		t.Errorf("KEY=%q", got["KEY"])
	}
	if _, ok := got["BADLINE_NO_EQUALS"]; ok {
		t.Error("malformed line should be skipped")
	}
}

func TestReadDotenvMissing(t *testing.T) {
	_, err := readDotenv("/nonexistent/.env")
	if err == nil {
		t.Fatal("expected error on missing file")
	}
}

func TestEnvOr(t *testing.T) {
	key := "KANBAN_TEST_ENVOR"
	os.Unsetenv(key)
	if got := envOr(key, "def"); got != "def" {
		t.Errorf("unset env: got %q, want def", got)
	}
	os.Setenv(key, "real")
	defer os.Unsetenv(key)
	if got := envOr(key, "def"); got != "real" {
		t.Errorf("set env: got %q, want real", got)
	}
}

func TestLoadConfigMissingEnv(t *testing.T) {
	dir := t.TempDir()
	prev, _ := os.Getwd()
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	defer os.Chdir(prev) //nolint:errcheck
	_, _, err := LoadConfig()
	if err == nil {
		t.Fatal("expected error when .env missing")
	}
}

func TestLoadConfigWithYAML(t *testing.T) {
	dir := t.TempDir()
	prev, _ := os.Getwd()
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	defer os.Chdir(prev) //nolint:errcheck
	must := func(err error) {
		t.Helper()
		if err != nil {
			t.Fatal(err)
		}
	}
	must(os.WriteFile(".env", []byte(strings.Join([]string{
		"TRELLO_API_KEY=ABC",
		"TRELLO_TOKEN=DEF",
	}, "\n")), 0644))
	// New format: kanban.default_agent + agents section
	must(os.WriteFile("config.yaml", []byte(`
trello:
  board_id: "B1"
  lists:
    todo: "L1"
    doing: "L2"
    done: "L3"
  labels:
    attention: "attention"
kanban:
  default_agent: "my-agent"
agents:
  my-agent:
    type: opencode
    base_url: "http://127.0.0.1:8567"
    default_model:
      providerID: "test-provider"
      modelID: "test-model"
projects:
  allowed:
    - label: "proj:agent"
      name: "agent"
      root: "/repo/agent"
      kanban_config: ".kanban.yml"
capacity:
  total: 5
  per_project: 2
timer:
  interval: 10s
  abort_timeout: 120s
  summary_timeout: 90s
hooks:
  default_timeout: 90s
  max_output_bytes: 4096
`), 0644))
	cfg, _, err := LoadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.DefaultAgent != "my-agent" {
		t.Errorf("DefaultAgent=%q, want my-agent", cfg.DefaultAgent)
	}
	if _, ok := cfg.Agents["my-agent"]; !ok {
		t.Errorf("Agents[my-agent] not found, Agents=%v", cfg.Agents)
	}
	if cfg.TrelloLists["todo"] != "L1" {
		t.Errorf("TrelloLists[todo]=%q", cfg.TrelloLists["todo"])
	}
	if cfg.TrelloBoardID != "B1" {
		t.Errorf("TrelloBoardID=%q, want B1", cfg.TrelloBoardID)
	}
	if cfg.HookDefaultTimeout != 90*time.Second {
		t.Errorf("HookDefaultTimeout=%v, want 90s", cfg.HookDefaultTimeout)
	}
	if cfg.HookMaxOutputBytes != 4096 {
		t.Errorf("HookMaxOutputBytes=%d, want 4096", cfg.HookMaxOutputBytes)
	}
	if len(cfg.AllowedProjects) != 1 || cfg.AllowedProjects[0].Name != "agent" {
		t.Errorf("AllowedProjects=%+v", cfg.AllowedProjects)
	}
	if cfg.AllowedProjects[0].Root != "/repo/agent" {
		t.Errorf("AllowedProjects[0].Root=%q, want /repo/agent", cfg.AllowedProjects[0].Root)
	}
	if cfg.AllowedProjects[0].KanbanConfig != ".kanban.yml" {
		t.Errorf("AllowedProjects[0].KanbanConfig=%q, want .kanban.yml", cfg.AllowedProjects[0].KanbanConfig)
	}
	if cfg.MaxDoingTotal != 5 {
		t.Errorf("MaxDoingTotal=%d, want 5", cfg.MaxDoingTotal)
	}
	if cfg.MaxDoingPerProject != 2 {
		t.Errorf("MaxDoingPerProject=%d, want 2", cfg.MaxDoingPerProject)
	}
	if cfg.PollInterval != 10*time.Second {
		t.Errorf("PollInterval=%v, want 10s", cfg.PollInterval)
	}
	if cfg.AbortTimeout != 120*time.Second {
		t.Errorf("AbortTimeout=%v, want 120s", cfg.AbortTimeout)
	}
	if cfg.SummaryTimeout != 90*time.Second {
		t.Errorf("SummaryTimeout=%v, want 90s", cfg.SummaryTimeout)
	}
}

// TestLoadConfigWithYAMLBackwardCompat verifies the old opencode: section still works.
func TestLoadConfigWithYAMLBackwardCompat(t *testing.T) {
	dir := t.TempDir()
	prev, _ := os.Getwd()
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	defer os.Chdir(prev) //nolint:errcheck
	must := func(err error) {
		t.Helper()
		if err != nil {
			t.Fatal(err)
		}
	}
	must(os.WriteFile(".env", []byte("TRELLO_API_KEY=ABC\nTRELLO_TOKEN=DEF\n"), 0644))
	// Old format: opencode section → synthesizes opencode-default agent
	must(os.WriteFile("config.yaml", []byte(`
trello:
  board_id: "B1"
  lists:
    todo: "L1"
    doing: "L2"
    done: "L3"
opencode:
  base_url: "http://127.0.0.1:8567"
  default_model:
    providerID: "test-provider"
    modelID: "test-model"
`), 0644))
	cfg, _, err := LoadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.DefaultAgent != "opencode-default" {
		t.Errorf("DefaultAgent=%q, want opencode-default", cfg.DefaultAgent)
	}
	if _, ok := cfg.Agents["opencode-default"]; !ok {
		t.Errorf("Agents[opencode-default] not found")
	}
}

func TestLoadConfigWithYAMLBackwardCompatCustomDefaultAgent(t *testing.T) {
	// If the user sets kanban.default_agent but uses the legacy opencode: section
	// (no agents: block), the synthesized agent must use the user-specified name.
	dir := t.TempDir()
	prev, _ := os.Getwd()
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	defer os.Chdir(prev) //nolint:errcheck
	must := func(err error) {
		t.Helper()
		if err != nil {
			t.Fatal(err)
		}
	}
	must(os.WriteFile(".env", []byte("TRELLO_API_KEY=ABC\nTRELLO_TOKEN=DEF\n"), 0644))
	must(os.WriteFile("config.yaml", []byte(`
trello:
  board_id: "B1"
  lists:
    todo: "L1"
    doing: "L2"
    done: "L3"
kanban:
  default_agent: "my-oc"
opencode:
  base_url: "http://127.0.0.1:8567"
  default_model:
    providerID: "test-provider"
    modelID: "test-model"
`), 0644))
	cfg, _, err := LoadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.DefaultAgent != "my-oc" {
		t.Errorf("DefaultAgent=%q, want my-oc", cfg.DefaultAgent)
	}
	if _, ok := cfg.Agents["my-oc"]; !ok {
		t.Errorf("Agents[my-oc] not found; Agents=%v", cfg.Agents)
	}
	if err := cfg.Validate(); err != nil {
		t.Errorf("Validate() unexpected error: %v", err)
	}
}

func TestValidateMissingDefaultAgent(t *testing.T) {
	c := Config{
		TrelloLists: map[string]string{"todo": "L1", "doing": "L2", "done": "L3"},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for missing DefaultAgent")
	}
}

func TestValidateMissingTrelloList(t *testing.T) {
	c := Config{
		DefaultAgent: "a",
		Agents:       map[string]AgentConfig{"a": {Type: "opencode"}},
		TrelloLists:  map[string]string{"todo": "L1", "doing": "L2"},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for missing done list")
	}
}

func TestValidateAllowedProjectMissingName(t *testing.T) {
	c := Config{
		DefaultAgent:    "a",
		Agents:          map[string]AgentConfig{"a": {Type: "opencode"}},
		TrelloLists:     map[string]string{"todo": "L1", "doing": "L2", "done": "L3"},
		AllowedProjects: []AllowedProject{{Label: "proj:x", Name: ""}},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for allowed project missing name")
	}
}

func TestValidateAllowedProjectMissingRoot(t *testing.T) {
	c := Config{
		DefaultAgent:    "a",
		Agents:          map[string]AgentConfig{"a": {Type: "opencode"}},
		TrelloLists:     map[string]string{"todo": "L1", "doing": "L2", "done": "L3"},
		AllowedProjects: []AllowedProject{{Label: "proj:x", Name: "x", Root: ""}},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for allowed project missing root")
	}
}

func TestValidateAllowedProjectRelativeRoot(t *testing.T) {
	c := Config{
		DefaultAgent:    "a",
		Agents:          map[string]AgentConfig{"a": {Type: "opencode"}},
		TrelloLists:     map[string]string{"todo": "L1", "doing": "L2", "done": "L3"},
		AllowedProjects: []AllowedProject{{Label: "proj:x", Name: "x", Root: "relative/path"}},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for relative root path")
	}
}

func TestValidateAllowedProjectAbsoluteRootOK(t *testing.T) {
	c := Config{
		DefaultAgent:    "a",
		Agents:          map[string]AgentConfig{"a": {Type: "opencode"}},
		TrelloLists:     map[string]string{"todo": "L1", "doing": "L2", "done": "L3"},
		AllowedProjects: []AllowedProject{{Label: "proj:x", Name: "x", Root: "/abs/path"}},
	}
	if err := c.Validate(); err != nil {
		t.Fatalf("unexpected error for valid project: %v", err)
	}
}

func TestLoadConfigControlTokenFromDotenv(t *testing.T) {
	// Token placed in .env (not exported as real env var) must be picked up.
	dir := t.TempDir()
	prev, _ := os.Getwd()
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	defer os.Chdir(prev) //nolint:errcheck
	must := func(err error) {
		t.Helper()
		if err != nil {
			t.Fatal(err)
		}
	}
	must(os.WriteFile(".env", []byte(strings.Join([]string{
		"TRELLO_API_KEY=ABC",
		"TRELLO_TOKEN=DEF",
		"MY_CONTROL_TOKEN=secret123",
	}, "\n")), 0644))
	must(os.WriteFile("config.yaml", []byte(`
trello:
  board_id: "B1"
  lists:
    todo: "L1"
    doing: "L2"
    done: "L3"
opencode:
  base_url: "http://127.0.0.1:4096"
  default_model:
    providerID: "p"
    modelID: "m"
control:
  token_env: MY_CONTROL_TOKEN
`), 0644))
	// Ensure the token is NOT in the real process environment.
	os.Unsetenv("MY_CONTROL_TOKEN")

	cfg, _, err := LoadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.ControlToken != "secret123" {
		t.Errorf("ControlToken=%q, want secret123 (should be loaded from .env)", cfg.ControlToken)
	}
}

func TestLoadConfigOK(t *testing.T) {
	dir := t.TempDir()
	prev, _ := os.Getwd()
	if err := os.Chdir(dir); err != nil {
		t.Fatal(err)
	}
	defer os.Chdir(prev) //nolint:errcheck
	must := func(err error) {
		t.Helper()
		if err != nil {
			t.Fatal(err)
		}
	}
	must(os.WriteFile(".env", []byte(strings.Join([]string{
		"TRELLO_API_KEY=ABC",
		"TRELLO_TOKEN=DEF",
	}, "\n")), 0644))
	cfg, _, err := LoadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.TrelloKey != "ABC" {
		t.Errorf("TrelloKey=%q", cfg.TrelloKey)
	}
	if cfg.HTTPListen != "127.0.0.1:8087" {
		t.Errorf("HTTPListen=%q (default missing)", cfg.HTTPListen)
	}
}

func TestNewAppliesDefaults(t *testing.T) {
	s, err := New(Config{})
	if err != nil {
		t.Fatal(err)
	}
	if s.cfg.PollInterval != 5*time.Second {
		t.Errorf("PollInterval=%v", s.cfg.PollInterval)
	}
	if s.cfg.HTTPTimeout != 15*time.Second {
		t.Errorf("HTTPTimeout=%v", s.cfg.HTTPTimeout)
	}
	if s.cfg.HTTPListen != "127.0.0.1:8087" {
		t.Errorf("HTTPListen=%v", s.cfg.HTTPListen)
	}
	if s.cfg.AbortTimeout != 60*time.Second {
		t.Errorf("AbortTimeout=%v", s.cfg.AbortTimeout)
	}
	if s.cfg.SummaryTimeout != 60*time.Second {
		t.Errorf("SummaryTimeout=%v", s.cfg.SummaryTimeout)
	}
	if s.cfg.MaxDoingTotal != 3 {
		t.Errorf("MaxDoingTotal=%d, want 3", s.cfg.MaxDoingTotal)
	}
}

func TestWriteJSON(t *testing.T) {
	w := httptest.NewRecorder()
	writeJSON(w, http.StatusTeapot, map[string]string{"k": "v"})
	if w.Code != http.StatusTeapot {
		t.Errorf("code=%d, want 418", w.Code)
	}
	if !strings.Contains(w.Body.String(), `"k":"v"`) {
		t.Errorf("body=%q", w.Body.String())
	}
}

// ---------- findProject tests ----------

func TestFindProject(t *testing.T) {
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:agent", Name: "agent", Root: "/repo/agent"},
			{Label: "proj:kanban", Name: "kanban", Root: "/repo/kanban"},
		},
	}

	p, ok := findProject("agent", cfg)
	if !ok || p.Root != "/repo/agent" {
		t.Errorf("findProject(agent) = %+v, %v", p, ok)
	}

	_, ok = findProject("unknown", cfg)
	if ok {
		t.Error("findProject(unknown) should return false")
	}
}

// ---------- hasProjLabel tests ----------

func TestHasProjLabel(t *testing.T) {
	cases := []struct {
		name   string
		labels []string
		want   bool
	}{
		{"no labels", nil, false},
		{"attention only", []string{"attention"}, false},
		{"proj:agent", []string{"proj:agent"}, true},
		{"proj:agent + attention", []string{"proj:agent", "attention"}, true},
		{"multiple proj", []string{"proj:a", "proj:b"}, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			card := CardSnapshot{Labels: c.labels}
			if got := hasProjLabel(card); got != c.want {
				t.Errorf("hasProjLabel = %v, want %v", got, c.want)
			}
		})
	}
}

// ---------- parse_proj tests ----------

func TestParseProj(t *testing.T) {
	cfg := Config{
		AllowedProjects: []AllowedProject{
			{Label: "proj:agent", Name: "agent"},
			{Label: "proj:ai", Name: "ai"},
		},
	}
	cases := []struct {
		name    string
		labels  []string
		want    string
		wantErr bool
	}{
		{
			name:    "no proj label is error",
			wantErr: true,
		},
		{
			name:   "known proj:agent",
			labels: []string{"proj:agent"},
			want:   "agent",
		},
		{
			name:    "unrelated label is error (no proj:*)",
			labels:  []string{"attention"},
			wantErr: true,
		},
		{
			name:    "unknown proj label",
			labels:  []string{"proj:unknown"},
			wantErr: true,
		},
		{
			name:    "multiple proj labels",
			labels:  []string{"proj:agent", "proj:ai"},
			wantErr: true,
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			card := CardSnapshot{Labels: c.labels}
			got, err := parseProj(card, cfg)
			if c.wantErr {
				if err == nil {
					t.Errorf("expected error, got proj=%q", got)
				}
				return
			}
			if err != nil {
				t.Errorf("unexpected error: %v", err)
			}
			if got != c.want {
				t.Errorf("parseProj = %q, want %q", got, c.want)
			}
		})
	}
}

// ---------- parseAgent tests ----------

func TestParseAgent(t *testing.T) {
	cfg := Config{
		DefaultAgent: "test-agent",
		Agents: map[string]AgentConfig{
			"test-agent":  {Type: "opencode"},
			"other-agent": {Type: "opencode"},
		},
	}
	cases := []struct {
		name    string
		labels  []string
		want    string
		wantErr bool
	}{
		{
			name: "no agent label uses default",
			want: "test-agent",
		},
		{
			name:   "known agent:other-agent",
			labels: []string{"agent:other-agent"},
			want:   "other-agent",
		},
		{
			name:    "unknown agent label",
			labels:  []string{"agent:unknown"},
			wantErr: true,
		},
		{
			name:    "multiple agent labels",
			labels:  []string{"agent:test-agent", "agent:other-agent"},
			wantErr: true,
		},
		{
			name: "no default configured",
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			useCfg := cfg
			if c.name == "no default configured" {
				useCfg = Config{
					Agents: map[string]AgentConfig{"test-agent": {Type: "opencode"}},
				}
			}
			card := CardSnapshot{Labels: c.labels}
			got, err := parseAgent(card, useCfg)
			if c.wantErr || c.name == "no default configured" {
				if err == nil {
					t.Errorf("expected error, got agent=%q", got)
				}
				return
			}
			if err != nil {
				t.Errorf("unexpected error: %v", err)
			}
			if got != c.want {
				t.Errorf("parseAgent = %q, want %q", got, c.want)
			}
		})
	}
}
