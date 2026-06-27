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
	_, err := LoadConfig()
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
		"OPENCODE_SERVER_USERNAME=u",
		"OPENCODE_SERVER_PASSWORD=p",
	}, "\n")), 0644))
	must(os.WriteFile("config.yaml", []byte(`
trello:
  board_id: "B1"
  lists:
    todo: "L1"
    doing: "L2"
    done: "L3"
  labels:
    attention: "attention"
opencode:
  base_url: "http://127.0.0.1:8567"
  default_model:
    providerID: "test-provider"
    modelID: "test-model"
  allowed_models:
    - label: "model:test"
      providerID: "test-provider"
      modelID: "test-model"
projects:
  allowed:
    - label: "proj:agent"
      name: "agent"
capacity:
  total: 5
  per_project: 2
timer:
  interval: 10s
  abort_timeout: 120s
  summary_timeout: 90s
`), 0644))
	cfg, err := LoadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.DefaultModel.ProviderID != "test-provider" || cfg.DefaultModel.ModelID != "test-model" {
		t.Errorf("DefaultModel=%+v", cfg.DefaultModel)
	}
	if len(cfg.AllowedModels) != 1 || cfg.AllowedModels[0].Label != "model:test" {
		t.Errorf("AllowedModels=%+v", cfg.AllowedModels)
	}
	if cfg.TrelloLists["todo"] != "L1" {
		t.Errorf("TrelloLists[todo]=%q", cfg.TrelloLists["todo"])
	}
	if cfg.TrelloBoardID != "B1" {
		t.Errorf("TrelloBoardID=%q, want B1", cfg.TrelloBoardID)
	}
	if len(cfg.AllowedProjects) != 1 || cfg.AllowedProjects[0].Name != "agent" {
		t.Errorf("AllowedProjects=%+v", cfg.AllowedProjects)
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

func TestValidateMissingDefaultModel(t *testing.T) {
	c := Config{
		TrelloLists: map[string]string{"todo": "L1", "doing": "L2", "done": "L3"},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for missing DefaultModel")
	}
}

func TestValidateMissingTrelloList(t *testing.T) {
	c := Config{
		DefaultModel: ModelRef{ProviderID: "p", ModelID: "m"},
		TrelloLists:  map[string]string{"todo": "L1", "doing": "L2"},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for missing done list")
	}
}

func TestValidateAllowedModelEmpty(t *testing.T) {
	c := Config{
		DefaultModel:  ModelRef{ProviderID: "p", ModelID: "m"},
		TrelloLists:   map[string]string{"todo": "L1", "doing": "L2", "done": "L3"},
		AllowedModels: []AllowedModel{{Label: "model:x", ProviderID: "", ModelID: "m"}},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for allowed model missing providerID")
	}
}

func TestValidateAllowedProjectMissingName(t *testing.T) {
	c := Config{
		DefaultModel:    ModelRef{ProviderID: "p", ModelID: "m"},
		TrelloLists:     map[string]string{"todo": "L1", "doing": "L2", "done": "L3"},
		AllowedProjects: []AllowedProject{{Label: "proj:x", Name: ""}},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for allowed project missing name")
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
		"OPENCODE_SERVER_USERNAME=u",
		"OPENCODE_SERVER_PASSWORD=p",
	}, "\n")), 0644))
	cfg, err := LoadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.TrelloKey != "ABC" {
		t.Errorf("TrelloKey=%q", cfg.TrelloKey)
	}
	if cfg.OpenCodeUser != "u" {
		t.Errorf("OpenCodeUser=%q", cfg.OpenCodeUser)
	}
	if cfg.HTTPListen != "127.0.0.1:8087" {
		t.Errorf("HTTPListen=%q (default missing)", cfg.HTTPListen)
	}
	if cfg.OpenCodeBaseURL == "" {
		t.Error("OpenCodeBaseURL should default")
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

// ---------- hasProjLabel tests ----------

func TestHasProjLabel(t *testing.T) {
	cases := []struct {
		name   string
		labels []trelloLabel
		want   bool
	}{
		{"no labels", nil, false},
		{"attention only", []trelloLabel{{Name: "attention"}}, false},
		{"proj:agent", []trelloLabel{{Name: "proj:agent"}}, true},
		{"proj:agent + attention", []trelloLabel{{Name: "proj:agent"}, {Name: "attention"}}, true},
		{"multiple proj", []trelloLabel{{Name: "proj:a"}, {Name: "proj:b"}}, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			card := trelloCard{Labels: c.labels}
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
		labels  []trelloLabel
		want    string
		wantErr bool
	}{
		{
			name:    "no proj label is error",
			wantErr: true,
		},
		{
			name:   "known proj:agent",
			labels: []trelloLabel{{Name: "proj:agent"}},
			want:   "agent",
		},
		{
			name:    "unrelated label is error (no proj:*)",
			labels:  []trelloLabel{{Name: "attention"}},
			wantErr: true,
		},
		{
			name:    "unknown proj label",
			labels:  []trelloLabel{{Name: "proj:unknown"}},
			wantErr: true,
		},
		{
			name:    "multiple proj labels",
			labels:  []trelloLabel{{Name: "proj:agent"}, {Name: "proj:ai"}},
			wantErr: true,
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			card := trelloCard{Labels: c.labels}
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

// ---------- parse_model tests ----------

func TestParseModel(t *testing.T) {
	defaultModel := ModelRef{ProviderID: "test", ModelID: "default-model"}
	cfg := Config{
		DefaultModel: defaultModel,
		AllowedModels: []AllowedModel{
			{Label: "model:sonnet", ProviderID: "anthropic", ModelID: "claude-sonnet-4"},
			{Label: "model:gpt", ProviderID: "openai", ModelID: "gpt-5"},
		},
	}
	cases := []struct {
		name    string
		labels  []trelloLabel
		want    ModelRef
		wantErr bool
	}{
		{
			name: "no model label uses default",
			want: defaultModel,
		},
		{
			name:   "known model:sonnet",
			labels: []trelloLabel{{Name: "model:sonnet"}},
			want:   ModelRef{ProviderID: "anthropic", ModelID: "claude-sonnet-4"},
		},
		{
			name:   "unrelated label uses default",
			labels: []trelloLabel{{Name: "proj:agent"}},
			want:   defaultModel,
		},
		{
			name:    "unknown model label",
			labels:  []trelloLabel{{Name: "model:unknown"}},
			wantErr: true,
		},
		{
			name:    "multiple model labels",
			labels:  []trelloLabel{{Name: "model:sonnet"}, {Name: "model:gpt"}},
			wantErr: true,
		},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			card := trelloCard{Labels: c.labels}
			got, err := parseModel(card, cfg)
			if c.wantErr {
				if err == nil {
					t.Errorf("expected error, got model=%+v", got)
				}
				return
			}
			if err != nil {
				t.Errorf("unexpected error: %v", err)
			}
			if got != c.want {
				t.Errorf("parseModel = %+v, want %+v", got, c.want)
			}
		})
	}
}
