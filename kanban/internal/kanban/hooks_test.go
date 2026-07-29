package kanban

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// ---------- loadProjectConfig ----------

func TestLoadProjectConfigMissingRoot(t *testing.T) {
	pc, err := loadProjectConfig(AllowedProject{})
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pc.Prompt.Template != "" || len(pc.Prompt.Addons) != 0 {
		t.Errorf("expected empty config, got %+v", pc)
	}
}

func TestLoadProjectConfigFileMissing(t *testing.T) {
	dir := t.TempDir()
	proj := AllowedProject{Root: dir, KanbanConfig: ".kanban.yml"}
	pc, err := loadProjectConfig(proj)
	if err != nil {
		t.Fatalf("expected no error for missing file, got %v", err)
	}
	if pc.Prompt.Template != "" {
		t.Errorf("expected empty config, got template=%q", pc.Prompt.Template)
	}
}

func TestLoadProjectConfigParseError(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, ".kanban.yml"), []byte(":\tinvalid yaml{{"), 0644); err != nil {
		t.Fatal(err)
	}
	proj := AllowedProject{Root: dir, KanbanConfig: ".kanban.yml"}
	_, err := loadProjectConfig(proj)
	if err == nil {
		t.Fatal("expected error for invalid YAML")
	}
}

func TestLoadProjectConfigFull(t *testing.T) {
	dir := t.TempDir()
	yaml := `
prompt:
  template: "Task: {{.Card.Title}}"
  addons:
    - "Run lint before finishing."
    - "Run tests."
hooks:
  session_new:
    command: ["./hook.sh", "new"]
    timeout: "180s"
  session_finish:
    command: ["./hook.sh", "finish"]
    timeout: "300s"
  session_abort:
    command: ["./hook.sh", "abort"]
`
	if err := os.WriteFile(filepath.Join(dir, ".kanban.yml"), []byte(yaml), 0644); err != nil {
		t.Fatal(err)
	}
	proj := AllowedProject{Root: dir, KanbanConfig: ".kanban.yml"}
	pc, err := loadProjectConfig(proj)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pc.Prompt.Template != "Task: {{.Card.Title}}" {
		t.Errorf("template=%q", pc.Prompt.Template)
	}
	if len(pc.Prompt.Addons) != 2 {
		t.Errorf("addons=%v", pc.Prompt.Addons)
	}
	if len(pc.Hooks.SessionNew.Command) != 2 || pc.Hooks.SessionNew.Command[0] != "./hook.sh" {
		t.Errorf("session_new.command=%v", pc.Hooks.SessionNew.Command)
	}
	if pc.Hooks.SessionNew.parsedTimeout() != 180*time.Second {
		t.Errorf("session_new.timeout=%v", pc.Hooks.SessionNew.parsedTimeout())
	}
	if len(pc.Hooks.SessionFinish.Command) != 2 {
		t.Errorf("session_finish.command=%v", pc.Hooks.SessionFinish.Command)
	}
}

func TestLoadProjectConfigDefaultKanbanConfigPath(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, ".kanban.yml"), []byte("prompt:\n  template: hello\n"), 0644); err != nil {
		t.Fatal(err)
	}
	// KanbanConfig="" should default to ".kanban.yml"
	proj := AllowedProject{Root: dir, KanbanConfig: ""}
	pc, err := loadProjectConfig(proj)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if pc.Prompt.Template != "hello" {
		t.Errorf("template=%q", pc.Prompt.Template)
	}
}

// ---------- realHookRunner ----------

func newTestHookRunner(t *testing.T) realHookRunner {
	t.Helper()
	return realHookRunner{
		defaultTimeout: 5 * time.Second,
		maxOutputBytes: 4096,
	}
}

func writeScript(t *testing.T, dir, name, content string) string {
	t.Helper()
	path := filepath.Join(dir, name)
	if err := os.WriteFile(path, []byte("#!/bin/sh\n"+content), 0755); err != nil {
		t.Fatal(err)
	}
	return path
}

func testTask() *Task {
	return &Task{
		CardID:    "card1",
		CardTitle: "Test card",
		CardURL:   "https://trello.com/c/test",
		SessionID: "__pending__",
		Proj:      "agent",
		Agent:     "test-agent",
		Workdir:   "/tmp",
	}
}

func TestRunHookNoCommand(t *testing.T) {
	r := newTestHookRunner(t)
	pc := ProjectConfig{}
	result, err := r.RunHook(context.Background(), "session_new", testTask(),
		CardSnapshot{ID: "c1"}, AllowedProject{}, "test-agent", "opencode", "/tmp", pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Workdir != "" || result.Comment != "" {
		t.Errorf("expected empty result, got %+v", result)
	}
}

func TestRunHookSuccess(t *testing.T) {
	dir := t.TempDir()
	workdir := t.TempDir()
	script := writeScript(t, dir, "hook.sh",
		`printf '{"workdir":"'`+workdir+`'","comment":"ready"}\n' >&3`)

	pc := ProjectConfig{}
	pc.Hooks.SessionNew.Command = []string{script}

	r := newTestHookRunner(t)
	result, err := r.RunHook(context.Background(), "session_new", testTask(),
		CardSnapshot{ID: "c1", Title: "T"}, AllowedProject{}, "test-agent", "opencode", "/tmp", pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Workdir != workdir {
		t.Errorf("workdir=%q, want %q", result.Workdir, workdir)
	}
	if result.Comment != "ready" {
		t.Errorf("comment=%q, want ready", result.Comment)
	}
}

func TestRunHookExitNonZero(t *testing.T) {
	dir := t.TempDir()
	script := writeScript(t, dir, "hook.sh", "exit 1")

	pc := ProjectConfig{}
	pc.Hooks.SessionNew.Command = []string{script}

	r := newTestHookRunner(t)
	_, err := r.RunHook(context.Background(), "session_new", testTask(),
		CardSnapshot{ID: "c1"}, AllowedProject{}, "test-agent", "opencode", "/tmp", pc)
	if err == nil {
		t.Fatal("expected error for non-zero exit")
	}
}

func TestRunHookTimeout(t *testing.T) {
	dir := t.TempDir()
	// Use a shell builtin loop — no child process is spawned, so the
	// timeout kill actually terminates the process holding fd 3.
	script := writeScript(t, dir, "hook.sh", "while true; do :; done")

	pc := ProjectConfig{}
	pc.Hooks.SessionNew.Command = []string{script}
	pc.Hooks.SessionNew.Timeout = "200ms"

	r := newTestHookRunner(t)
	_, err := r.RunHook(context.Background(), "session_new", testTask(),
		CardSnapshot{ID: "c1"}, AllowedProject{}, "test-agent", "opencode", "/tmp", pc)
	if err == nil {
		t.Fatal("expected timeout error")
	}
	if !strings.Contains(err.Error(), "timed out") {
		t.Errorf("err=%q, want contains 'timed out'", err.Error())
	}
}

func TestRunHookBadJSON(t *testing.T) {
	dir := t.TempDir()
	script := writeScript(t, dir, "hook.sh", `printf '{bad json\n' >&3`)

	pc := ProjectConfig{}
	pc.Hooks.SessionNew.Command = []string{script}

	r := newTestHookRunner(t)
	_, err := r.RunHook(context.Background(), "session_new", testTask(),
		CardSnapshot{ID: "c1"}, AllowedProject{}, "test-agent", "opencode", "/tmp", pc)
	if err == nil {
		t.Fatal("expected error for bad JSON")
	}
	if !strings.Contains(err.Error(), "JSON") {
		t.Errorf("err=%q, want contains 'JSON'", err.Error())
	}
}

func TestRunHookRelativeWorkdir(t *testing.T) {
	dir := t.TempDir()
	script := writeScript(t, dir, "hook.sh", `printf '{"workdir":"relative/path"}' >&3`)

	pc := ProjectConfig{}
	pc.Hooks.SessionNew.Command = []string{script}

	r := newTestHookRunner(t)
	_, err := r.RunHook(context.Background(), "session_new", testTask(),
		CardSnapshot{ID: "c1"}, AllowedProject{}, "test-agent", "opencode", "/tmp", pc)
	if err == nil {
		t.Fatal("expected error for relative workdir")
	}
	if !strings.Contains(err.Error(), "non-absolute") {
		t.Errorf("err=%q, want contains 'non-absolute'", err.Error())
	}
}

func TestRunHookEmptyFd3Result(t *testing.T) {
	dir := t.TempDir()
	// Script succeeds but writes nothing to fd 3.
	script := writeScript(t, dir, "hook.sh", "exit 0")

	pc := ProjectConfig{}
	pc.Hooks.SessionNew.Command = []string{script}

	r := newTestHookRunner(t)
	result, err := r.RunHook(context.Background(), "session_new", testTask(),
		CardSnapshot{ID: "c1"}, AllowedProject{}, "test-agent", "opencode", "/tmp", pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if result.Workdir != "" {
		t.Errorf("expected empty result, got workdir=%q", result.Workdir)
	}
}

func TestRunHookSetsEnvVars(t *testing.T) {
	dir := t.TempDir()
	outFile := filepath.Join(dir, "env.txt")
	script := writeScript(t, dir, "hook.sh",
		`echo "EVENT=$KANBAN_EVENT" > `+outFile+`
echo "CARD_ID=$KANBAN_CARD_ID" >> `+outFile+`
echo "PROJECT=$KANBAN_PROJECT" >> `+outFile+`
echo "WORKDIR=$KANBAN_WORKDIR" >> `+outFile+`
echo "AGENT=$KANBAN_AGENT" >> `+outFile+`
echo "AGENT_TYPE=$KANBAN_AGENT_TYPE" >> `+outFile)

	pc := ProjectConfig{}
	pc.Hooks.SessionNew.Command = []string{script}

	r := newTestHookRunner(t)
	card := CardSnapshot{ID: "card42", Title: "My Task", URL: "https://trello.com/c/test"}
	proj := AllowedProject{Name: "myproj", Label: "proj:myproj"}
	task := &Task{SessionID: "__pending__"}
	_, err := r.RunHook(context.Background(), "session_new", task, card, proj, "my-agent", "opencode", "/work", pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	data, err := os.ReadFile(outFile)
	if err != nil {
		t.Fatal(err)
	}
	out := string(data)
	if !strings.Contains(out, "EVENT=session_new") {
		t.Errorf("env KANBAN_EVENT not set correctly, got:\n%s", out)
	}
	if !strings.Contains(out, "CARD_ID=card42") {
		t.Errorf("env KANBAN_CARD_ID not set correctly, got:\n%s", out)
	}
	if !strings.Contains(out, "PROJECT=myproj") {
		t.Errorf("env KANBAN_PROJECT not set correctly, got:\n%s", out)
	}
	if !strings.Contains(out, "WORKDIR=/work") {
		t.Errorf("env KANBAN_WORKDIR not set correctly, got:\n%s", out)
	}
	if !strings.Contains(out, "AGENT=my-agent") {
		t.Errorf("env KANBAN_AGENT not set correctly, got:\n%s", out)
	}
	if !strings.Contains(out, "AGENT_TYPE=opencode") {
		t.Errorf("env KANBAN_AGENT_TYPE not set correctly, got:\n%s", out)
	}
}

func TestRunHookDoesNotLeakSensitiveEnv(t *testing.T) {
	// Sensitive vars must not reach the hook subprocess.
	t.Setenv("TRELLO_API_KEY", "secret-trello-key")
	t.Setenv("OPENCODE_SERVER_PASSWORD", "secret-oc-pass")
	t.Setenv("KANBAN_CONTROL_TOKEN", "secret-token")

	dir := t.TempDir()
	outFile := filepath.Join(dir, "leaked.txt")
	// Print all env vars to a file; we'll scan for the secrets.
	script := writeScript(t, dir, "hook.sh",
		`env > `+outFile)

	pc := ProjectConfig{}
	pc.Hooks.SessionNew.Command = []string{script}

	r := newTestHookRunner(t)
	_, err := r.RunHook(context.Background(), "session_new", testTask(),
		CardSnapshot{ID: "c1"}, AllowedProject{}, "test-agent", "opencode", "/tmp", pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	data, err := os.ReadFile(outFile)
	if err != nil {
		t.Fatal(err)
	}
	out := string(data)
	for _, secret := range []string{"secret-trello-key", "secret-oc-pass", "secret-token"} {
		if strings.Contains(out, secret) {
			t.Errorf("sensitive value %q leaked to hook subprocess env:\n%s", secret, out)
		}
	}
}

func TestRunHookFd3Overflow(t *testing.T) {
	dir := t.TempDir()
	// Write maxOutputBytes+1 bytes to fd 3.
	script := writeScript(t, dir, "hook.sh", `python3 -c "import sys; sys.stdout.buffer.write(b'x'*4097); sys.stdout.flush()" >&3`)

	pc := ProjectConfig{}
	pc.Hooks.SessionNew.Command = []string{script}

	r := realHookRunner{defaultTimeout: 5 * time.Second, maxOutputBytes: 4096}
	_, err := r.RunHook(context.Background(), "session_new", testTask(),
		CardSnapshot{ID: "c1"}, AllowedProject{}, "test-agent", "opencode", "/tmp", pc)
	if err == nil {
		t.Fatal("expected error for fd3 overflow")
	}
	if !strings.Contains(err.Error(), "exceeded max size") {
		t.Errorf("err=%q, want contains 'exceeded max size'", err.Error())
	}
}
