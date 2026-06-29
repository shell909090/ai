package kanban

import (
	"strings"
	"text/template"
)

// summaryPromptText is the fixed prompt sent to request a task summary.
// It explicitly prohibits writing sensitive information.
const summaryPromptText = "请用 140 个字以内总结本次运行的结果。只输出总结本身，不要前缀、解释或 Markdown。不要包含密钥、token、密码、私有 URL 或其他敏感信息。"

// defaultPromptTemplate is used when no project-level template is configured.
const defaultPromptTemplate = `Card: {{.Card.Title}}
URL: {{.Card.URL}}
Project: {{.Project.Name}}
Agent: {{.Agent.Name}} ({{.Agent.Type}})

Description:
{{.Card.Description}}

Labels: {{range .Card.Labels}}{{.}} {{end}}`

// promptContext is passed to prompt templates.
type promptContext struct {
	Card    promptCard
	Project promptProject
	Agent   promptAgent
}

type promptCard struct {
	ID          string
	Title       string
	Description string
	URL         string
	Labels      []string
}

type promptProject struct {
	Name  string
	Label string
}

type promptAgent struct {
	Name string
	Type string
}

// renderInitialPrompt builds the initial prompt for an agent session.
// It uses pc.Prompt.Template if set, otherwise the built-in default template.
// pc.Prompt.Addons are appended after the base prompt.
func renderInitialPrompt(card trelloCard, proj AllowedProject, agentName, agentType string, pc ProjectConfig) (string, error) {
	labelNames := make([]string, 0, len(card.Labels))
	for _, l := range card.Labels {
		labelNames = append(labelNames, l.Name)
	}
	ctx := promptContext{
		Card: promptCard{
			ID:          card.ID,
			Title:       card.Name,
			Description: card.Desc,
			URL:         card.URL,
			Labels:      labelNames,
		},
		Project: promptProject{
			Name:  proj.Name,
			Label: proj.Label,
		},
		Agent: promptAgent{
			Name: agentName,
			Type: agentType,
		},
	}

	tmplText := pc.Prompt.Template
	if tmplText == "" {
		tmplText = defaultPromptTemplate
	}

	tmpl, err := template.New("prompt").Parse(tmplText)
	if err != nil {
		return "", err
	}

	var sb strings.Builder
	if err := tmpl.Execute(&sb, ctx); err != nil {
		return "", err
	}

	for _, addon := range pc.Prompt.Addons {
		sb.WriteString("\n\n")
		sb.WriteString(addon)
	}

	return sb.String(), nil
}

// renderSummaryPrompt returns the fixed summary prompt text.
func renderSummaryPrompt() string {
	return summaryPromptText
}
