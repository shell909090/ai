package kanban

import "context"

// AgentState is the normalized session state returned by an AgentDriver.
type AgentState struct {
	Kind      string // "running", "finished", or "failed"
	Text      string // readable result text; used as summary comment when finished
	RawFinish string // driver-specific status string, for comments and debug
}

// AgentDriver wraps a specific AI agent backend (e.g. opencode, codex).
type AgentDriver interface {
	CreateSession(ctx context.Context, workdir string, labels []string) (string, error)
	AbortSession(ctx context.Context, sessionID string) error
	SendPrompt(ctx context.Context, sessionID, prompt string, labels []string) error
	SessionState(ctx context.Context, sessionID string) (AgentState, error)
}

// AgentConfig holds the raw configuration for one named agent entry.
type AgentConfig struct {
	Type string
	Raw  map[string]any
}
