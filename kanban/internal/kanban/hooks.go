package kanban

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"time"

	"gopkg.in/yaml.v3"
)

// ProjectConfig holds the parsed content of a project's .kanban.yml.
// File absence yields an empty config with no error.
type ProjectConfig struct {
	Prompt struct {
		Template string   `yaml:"template"`
		Addons   []string `yaml:"addons"`
	} `yaml:"prompt"`
	Hooks struct {
		SessionNew    hookConfig `yaml:"session_new"`
		SessionFinish hookConfig `yaml:"session_finish"`
		SessionAbort  hookConfig `yaml:"session_abort"`
	} `yaml:"hooks"`
}

type hookConfig struct {
	Command []string `yaml:"command"`
	Timeout string   `yaml:"timeout"` // e.g. "180s"; 0/absent means use HookDefaultTimeout
}

func (hc hookConfig) parsedTimeout() time.Duration {
	if d, err := time.ParseDuration(hc.Timeout); err == nil && d > 0 {
		return d
	}
	return 0
}

// HookResult is the structured payload written by a hook script to fd 3.
type HookResult struct {
	Workdir string `json:"workdir,omitempty"`
	Comment string `json:"comment,omitempty"`
}

// HookRunner executes a lifecycle hook for a given event.
type HookRunner interface {
	RunHook(ctx context.Context, event string, task *Task, card trelloCard,
		proj AllowedProject, model ModelRef, workdir string,
		pc ProjectConfig) (HookResult, error)
}

// cappedWriter is an io.Writer that discards data past a byte limit.
type cappedWriter struct {
	w   io.Writer
	n   int
	max int
}

func (c *cappedWriter) Write(p []byte) (int, error) {
	remaining := c.max - c.n
	if remaining <= 0 {
		return len(p), nil
	}
	if len(p) > remaining {
		p = p[:remaining]
	}
	n, err := c.w.Write(p)
	c.n += n
	return len(p), err
}

// loadProjectConfig reads and parses a project's .kanban.yml.
// Returns an empty config without error when the file does not exist.
// Returns an error only on parse failure.
func loadProjectConfig(proj AllowedProject) (ProjectConfig, error) {
	var pc ProjectConfig
	if proj.Root == "" {
		return pc, nil
	}
	kanbanConfig := proj.KanbanConfig
	if kanbanConfig == "" {
		kanbanConfig = ".kanban.yml"
	}
	path := filepath.Join(proj.Root, kanbanConfig)
	data, err := os.ReadFile(path)
	if err != nil {
		if os.IsNotExist(err) {
			return pc, nil
		}
		return pc, fmt.Errorf("read %s: %w", path, err)
	}
	if err := yaml.Unmarshal(data, &pc); err != nil {
		return pc, fmt.Errorf("parse %s: %w", path, err)
	}
	return pc, nil
}

// hookConfigForEvent returns the HookConfig for the given event name.
func hookConfigForEvent(event string, pc ProjectConfig) hookConfig {
	switch event {
	case "session_new":
		return pc.Hooks.SessionNew
	case "session_finish":
		return pc.Hooks.SessionFinish
	case "session_abort":
		return pc.Hooks.SessionAbort
	default:
		return hookConfig{}
	}
}

// realHookRunner is the production HookRunner that runs subprocesses.
type realHookRunner struct {
	defaultTimeout time.Duration
	maxOutputBytes int
}

// RunHook executes the hook for the given event.
// Returns (HookResult{}, nil) when no command is configured for the event.
func (r realHookRunner) RunHook(ctx context.Context, event string, task *Task, card trelloCard,
	proj AllowedProject, model ModelRef, workdir string, pc ProjectConfig) (HookResult, error) {

	hc := hookConfigForEvent(event, pc)
	if len(hc.Command) == 0 {
		return HookResult{}, nil
	}

	timeout := hc.parsedTimeout()
	if timeout == 0 {
		timeout = r.defaultTimeout
	}
	ctx, cancel := context.WithTimeout(ctx, timeout)
	defer cancel()

	// Result pipe: fd 3 in child process.
	pr, pw, err := os.Pipe()
	if err != nil {
		return HookResult{}, fmt.Errorf("create result pipe: %w", err)
	}

	cmd := exec.CommandContext(ctx, hc.Command[0], hc.Command[1:]...)
	cmd.ExtraFiles = []*os.File{pw}

	// Capture stdout+stderr into a capped buffer for debug logging.
	var outBuf bytes.Buffer
	lw := &cappedWriter{w: &outBuf, max: r.maxOutputBytes}
	cmd.Stdout = lw
	cmd.Stderr = lw

	// Collect label names for the env var.
	var labelNames []string
	for _, l := range card.Labels {
		labelNames = append(labelNames, l.Name)
	}
	cmd.Env = append(os.Environ(),
		"KANBAN_EVENT="+event,
		"KANBAN_CARD_ID="+card.ID,
		"KANBAN_CARD_TITLE="+card.Name,
		"KANBAN_CARD_URL="+card.URL,
		"KANBAN_PROJECT="+proj.Name,
		"KANBAN_PROJECT_LABEL="+proj.Label,
		"KANBAN_MODEL_PROVIDER="+model.ProviderID,
		"KANBAN_MODEL_NAME="+model.ModelID,
		"KANBAN_SESSION_ID="+task.SessionID,
		"KANBAN_WORKDIR="+workdir,
		"KANBAN_HOOK_RESULT_FD=3",
		"KANBAN_CARD_LABELS="+strings.Join(labelNames, ","),
	)

	if err := cmd.Start(); err != nil {
		pw.Close()
		pr.Close()
		return HookResult{}, fmt.Errorf("start hook: %w", err)
	}
	pw.Close() // parent must close write end so read can reach EOF

	// Read result from fd 3 with size guard.
	resultData, readErr := io.ReadAll(io.LimitReader(pr, int64(r.maxOutputBytes)+1))
	pr.Close()

	waitErr := cmd.Wait()

	// Log debug output (not sent to Trello).
	if outBuf.Len() > 0 {
		_ = json.NewEncoder(defaultLogWriter).Encode(logRec{
			Time:   time.Now().Format(time.RFC3339),
			Event:  "hook.output." + event,
			Detail: outBuf.String(),
		})
	}

	if readErr != nil {
		return HookResult{}, fmt.Errorf("read hook result: %w", readErr)
	}
	if len(resultData) > r.maxOutputBytes {
		return HookResult{}, fmt.Errorf("hook result fd3 exceeded max size %d bytes", r.maxOutputBytes)
	}

	if waitErr != nil {
		if ctx.Err() != nil {
			return HookResult{}, fmt.Errorf("hook timed out after %v", timeout)
		}
		return HookResult{}, fmt.Errorf("hook exited with error: %w", waitErr)
	}

	resultData = bytes.TrimSpace(resultData)
	if len(resultData) == 0 {
		return HookResult{}, nil
	}

	var result HookResult
	if err := json.Unmarshal(resultData, &result); err != nil {
		return HookResult{}, fmt.Errorf("parse hook result JSON: %w", err)
	}

	if result.Workdir != "" && !filepath.IsAbs(result.Workdir) {
		return HookResult{}, fmt.Errorf("hook returned non-absolute workdir: %q", result.Workdir)
	}

	return result, nil
}
