package kanban

import (
	"strings"
	"testing"
)

// ---------- renderSummaryPrompt ----------

func TestRenderSummaryPromptContainsSensitiveInfoWarning(t *testing.T) {
	p := renderSummaryPrompt()
	for _, keyword := range []string{"密钥", "token", "密码", "私有 URL"} {
		if !strings.Contains(p, keyword) {
			t.Errorf("summary prompt missing %q; full text: %q", keyword, p)
		}
	}
	if !strings.Contains(p, "140") {
		t.Errorf("summary prompt should mention 140 char limit; got: %q", p)
	}
}

// ---------- renderInitialPrompt ----------

func testCard(id, title, desc, url string, labels ...string) CardSnapshot {
	return CardSnapshot{ID: CardID(id), Title: title, Description: desc, URL: url, Labels: labels}
}

func testProj(name, label string) AllowedProject {
	return AllowedProject{Name: name, Label: label}
}

func TestRenderInitialPromptDefault(t *testing.T) {
	card := testCard("c1", "Fix the bug", "Some description", "https://trello.com/c/c1", "proj:agent", "agent:test-agent")
	proj := testProj("agent", "proj:agent")
	pc := ProjectConfig{}

	result, err := renderInitialPrompt(card, proj, "test-agent", "opencode", pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}

	for _, want := range []string{
		"Fix the bug",
		"Some description",
		"https://trello.com/c/c1",
		"agent",
		"test-agent",
		"opencode",
	} {
		if !strings.Contains(result, want) {
			t.Errorf("prompt missing %q; got:\n%s", want, result)
		}
	}
}

func TestRenderInitialPromptTemplate(t *testing.T) {
	card := testCard("c1", "Build feature", "desc", "http://trello/c")
	proj := testProj("myproj", "proj:myproj")

	var pc ProjectConfig
	pc.Prompt.Template = "Card: {{.Card.Title}} | Project: {{.Project.Name}}"

	result, err := renderInitialPrompt(card, proj, "p", "opencode", pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	want := "Card: Build feature | Project: myproj"
	if result != want {
		t.Errorf("got %q, want %q", result, want)
	}
}

func TestRenderInitialPromptAddons(t *testing.T) {
	card := testCard("c1", "T", "d", "u")
	proj := testProj("p", "proj:p")

	var pc ProjectConfig
	pc.Prompt.Addons = []string{"Before starting, check git.", "Run tests."}

	result, err := renderInitialPrompt(card, proj, "prov", "opencode", pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.Contains(result, "Before starting, check git.") {
		t.Errorf("addon 1 missing; got:\n%s", result)
	}
	if !strings.Contains(result, "Run tests.") {
		t.Errorf("addon 2 missing; got:\n%s", result)
	}
	// Addons must appear after the base prompt (which contains the card title)
	titleIdx := strings.Index(result, "T")
	addonIdx := strings.Index(result, "Before starting")
	if addonIdx <= titleIdx {
		t.Errorf("addon should appear after card title in prompt")
	}
}

func TestRenderInitialPromptTemplateAndAddons(t *testing.T) {
	card := testCard("c1", "T", "d", "u")
	proj := testProj("p", "proj:p")

	var pc ProjectConfig
	pc.Prompt.Template = "Custom: {{.Card.Title}}"
	pc.Prompt.Addons = []string{"Addon text."}

	result, err := renderInitialPrompt(card, proj, "prov", "opencode", pc)
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if !strings.HasPrefix(result, "Custom: T") {
		t.Errorf("template not at start; got:\n%s", result)
	}
	if !strings.Contains(result, "Addon text.") {
		t.Errorf("addon missing; got:\n%s", result)
	}
}

func TestRenderInitialPromptBadTemplate(t *testing.T) {
	card := testCard("c1", "T", "d", "u")
	proj := testProj("p", "proj:p")

	var pc ProjectConfig
	pc.Prompt.Template = "{{.Card.Title" // malformed

	_, err := renderInitialPrompt(card, proj, "prov", "opencode", pc)
	if err == nil {
		t.Fatal("expected error for bad template")
	}
}
