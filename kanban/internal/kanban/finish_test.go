package kanban

import (
	"strings"
	"testing"
)

func TestExtractFinish(t *testing.T) {
	cases := []struct {
		name string
		in   map[string]any
		want string
	}{
		{"nil", nil, ""},
		{"empty", map[string]any{}, ""},
		{"no info", map[string]any{"role": "assistant"}, ""},
		{"info no finish", map[string]any{"info": map[string]any{"role": "assistant"}}, ""},
		{"finish stop", map[string]any{"info": map[string]any{"finish": "stop"}}, "stop"},
		{"finish tool-calls", map[string]any{"info": map[string]any{"finish": "tool-calls"}}, "tool-calls"},
		{"finish length", map[string]any{"info": map[string]any{"finish": "length"}}, "length"},
		{"finish error", map[string]any{"info": map[string]any{"finish": "error"}}, "error"},
		{"finish non-string", map[string]any{"info": map[string]any{"finish": 42}}, ""},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := ExtractFinish(c.in); got != c.want {
				t.Errorf("ExtractFinish(%v) = %q, want %q", c.in, got, c.want)
			}
		})
	}
}

func TestIsAbnormalFinish(t *testing.T) {
	// Per new design (events.md): empty and tool-calls mean "still active",
	// not abnormal. Only length/content-filter/error/unknown are abnormal.
	cases := []struct {
		finish string
		want   bool
	}{
		{"", false},
		{"stop", false},
		{"tool-calls", false}, // still in tool call cycle → not abnormal
		{"length", true},
		{"content-filter", true},
		{"error", true},
		{"unknown", true},
	}
	for _, c := range cases {
		if got := IsAbnormalFinish(c.finish); got != c.want {
			t.Errorf("IsAbnormalFinish(%q) = %v, want %v", c.finish, got, c.want)
		}
	}
}

func TestExtractSummaryText(t *testing.T) {
	shortText := "我修了 bug。"
	longText := strings.Repeat("修", 150)
	exactText := strings.Repeat("改", 140)

	cases := []struct {
		name      string
		in        map[string]any
		charLimit int
		want      string
	}{
		{"nil map", nil, 140, summaryFallbackEmpty},
		{"empty parts", map[string]any{"parts": []any{}}, 140, summaryFallbackEmpty},
		{"no parts field", map[string]any{"info": map[string]any{}}, 140, summaryFallbackEmpty},
		{"single text", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": shortText}},
		}, 140, shortText},
		{"multiple text concat", map[string]any{
			"parts": []any{
				map[string]any{"type": "text", "text": "第一段。"},
				map[string]any{"type": "step-start"},
				map[string]any{"type": "text", "text": "第二段。"},
			},
		}, 140, "第一段。第二段。"},
		{"whitespace trimmed", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": "  \n  " + shortText + "\n\t  "}},
		}, 140, shortText},
		{"long text truncated with ellipsis", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": longText}},
		}, 140, string([]rune(longText)[:140]) + "…"},
		{"exact 140 runes unchanged", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": exactText}},
		}, 140, exactText},
		{"rune boundary", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": "abcde"}},
		}, 3, "abc…"},
		{"charLimit zero uses default", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": longText}},
		}, 0, string([]rune(longText)[:summaryCharLimit]) + "…"},
		{"only non-text parts", map[string]any{
			"parts": []any{
				map[string]any{"type": "step-start"},
				map[string]any{"type": "tool-call", "id": "x"},
			},
		}, 140, summaryFallbackEmpty},
		{"empty text part", map[string]any{
			"parts": []any{map[string]any{"type": "text", "text": ""}},
		}, 140, summaryFallbackEmpty},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := ExtractSummaryText(c.in, c.charLimit); got != c.want {
				t.Errorf("ExtractSummaryText(_, %d) = %q, want %q", c.charLimit, got, c.want)
			}
		})
	}
}
