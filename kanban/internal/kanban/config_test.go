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
	os.Chdir(dir)
	defer os.Chdir(prev)
	_, err := LoadConfig()
	if err == nil {
		t.Fatal("expected error when .env missing")
	}
}

func TestLoadConfigWithYAML(t *testing.T) {
	dir := t.TempDir()
	prev, _ := os.Getwd()
	os.Chdir(dir)
	defer os.Chdir(prev)
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
  board_id: "B"
  lists:
    icebox: "L1"
    todo: "L2"
    doing: "L3"
    done: "L4"
    archived: "L5"
  labels:
    human_task: "human-task"
    no_worktree: "no-worktree"
    needs_attention: "needs-attention"
    needs_integration_test: "needs-integration-test"
    ai_task: "ai-task"
opencode:
  base_url: "http://127.0.0.1:8567"
  default_model:
    providerID: "opencode-go"
    modelID: "minimax-m3"
  allowed_models:
    - label: "model:minimax-m3"
      providerID: "opencode-go"
      modelID: "minimax-m3"
repo:
  main_path: "/tmp"
  main_branch: "main"
  allowed_paths:
    - label: "proj:agent"
      path: "/tmp"
`), 0644))
	cfg, err := LoadConfig()
	if err != nil {
		t.Fatal(err)
	}
	if cfg.DefaultModel.ProviderID != "opencode-go" || cfg.DefaultModel.ModelID != "minimax-m3" {
		t.Errorf("DefaultModel=%+v", cfg.DefaultModel)
	}
	if len(cfg.AllowedModels) != 1 || cfg.AllowedModels[0].Label != "model:minimax-m3" {
		t.Errorf("AllowedModels=%+v", cfg.AllowedModels)
	}
	if cfg.TrelloLists["todo"] != "L2" {
		t.Errorf("TrelloLists[todo]=%q", cfg.TrelloLists["todo"])
	}
	if cfg.TrelloLists["archived"] != "L5" {
		t.Errorf("TrelloLists[archived]=%q", cfg.TrelloLists["archived"])
	}
	if err := cfg.Validate(); err != nil {
		t.Errorf("Validate: %v", err)
	}
}

func TestValidateMissingDefaultModel(t *testing.T) {
	c := Config{
		TrelloLists: map[string]string{
			"icebox": "L1", "todo": "L2", "doing": "L3", "done": "L4", "archived": "L5",
		},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for missing DefaultModel")
	}
}

func TestValidateMissingTrelloList(t *testing.T) {
	c := Config{
		DefaultModel: ModelRef{ProviderID: "p", ModelID: "m"},
		TrelloLists:  map[string]string{"icebox": "L1", "todo": "L2", "doing": "L3", "done": "L4"},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for missing archived list")
	}
}

func TestValidateAllowedPathNotDir(t *testing.T) {
	c := Config{
		DefaultModel: ModelRef{ProviderID: "p", ModelID: "m"},
		TrelloLists: map[string]string{
			"icebox": "L1", "todo": "L2", "doing": "L3", "done": "L4", "archived": "L5",
		},
		AllowedPaths: []AllowedPath{{Label: "proj:x", Path: "/nonexistent/path/xyz"}},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for nonexistent allowed path")
	}
}

func TestValidateAllowedModelEmpty(t *testing.T) {
	c := Config{
		DefaultModel: ModelRef{ProviderID: "p", ModelID: "m"},
		TrelloLists: map[string]string{
			"icebox": "L1", "todo": "L2", "doing": "L3", "done": "L4", "archived": "L5",
		},
		AllowedModels: []AllowedModel{{Label: "model:x", ProviderID: "", ModelID: "m"}},
	}
	if err := c.Validate(); err == nil {
		t.Fatal("expected error for allowed model missing providerID")
	}
}

func TestLoadConfigOK(t *testing.T) {
	dir := t.TempDir()
	prev, _ := os.Getwd()
	os.Chdir(dir)
	defer os.Chdir(prev)
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

func TestNewRejectsEmptyWorkdir(t *testing.T) {
	if _, err := New(Config{}); err == nil {
		t.Fatal("expected error for empty workdir")
	}
}

func TestNewAppliesDefaults(t *testing.T) {
	s, err := New(Config{WorkDir: "/tmp"})
	if err != nil {
		t.Fatal(err)
	}
	if s.cfg.PollInterval != 5*time.Second {
		t.Errorf("PollInterval=%v", s.cfg.PollInterval)
	}
	if s.cfg.IdleInterval != 10*time.Second {
		t.Errorf("IdleInterval=%v", s.cfg.IdleInterval)
	}
	if s.cfg.HTTPTimeout != 15*time.Second {
		t.Errorf("HTTPTimeout=%v", s.cfg.HTTPTimeout)
	}
	if s.cfg.HTTPListen != "127.0.0.1:8087" {
		t.Errorf("HTTPListen=%v", s.cfg.HTTPListen)
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
