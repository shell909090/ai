package kanban

import (
	"strings"
)

// summaryCharLimit is the maximum number of runes in a summary.
const summaryCharLimit = 140

// summaryFallbackEmpty is returned when no text is found in a message.
const summaryFallbackEmpty = "（本次会话未产生可读总结）"

// ExtractFinish returns the info.finish value from the last opencode
// message, or "" if the field is absent or the message is nil.
func ExtractFinish(last map[string]any) string {
	return extractFinish(last)
}

func extractFinish(last map[string]any) string {
	if last == nil {
		return ""
	}
	info, _ := last["info"].(map[string]any)
	v, ok := info["finish"]
	if !ok {
		return ""
	}
	s, _ := v.(string)
	return s
}

// IsAbnormalFinish reports whether the finish value indicates the
// session ended abnormally. Only "stop" is a clean completion.
// Empty string and "tool-calls" indicate the session is still active.
func IsAbnormalFinish(finish string) bool {
	switch finish {
	case "", "stop", "tool-calls":
		return false
	default:
		return true
	}
}

// ExtractSummaryText returns text from the last opencode message,
// truncated to charLimit runes. If charLimit <= 0, summaryCharLimit is
// used. Returns summaryFallbackEmpty if no text is found.
func ExtractSummaryText(last map[string]any, charLimit int) string {
	if charLimit <= 0 {
		charLimit = summaryCharLimit
	}
	if last == nil {
		return summaryFallbackEmpty
	}
	parts, _ := last["parts"].([]any)
	var sb strings.Builder
	for _, p := range parts {
		pm, ok := p.(map[string]any)
		if !ok {
			continue
		}
		if t, _ := pm["type"].(string); t != "text" {
			continue
		}
		if txt, ok := pm["text"].(string); ok {
			sb.WriteString(txt)
		}
	}
	trimmed := strings.TrimSpace(sb.String())
	if trimmed == "" {
		return summaryFallbackEmpty
	}
	runes := []rune(trimmed)
	if len(runes) > charLimit {
		return string(runes[:charLimit]) + "…"
	}
	return trimmed
}
