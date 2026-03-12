package mcp

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	"github.com/mark3labs/mcp-go/mcp"

	"github.com/shell909090/ai/HITL-proxy/internal/audit"
	"github.com/shell909090/ai/HITL-proxy/internal/auth"
	"github.com/shell909090/ai/HITL-proxy/internal/search"
)

func (s *Server) handleSearchTools(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	query, ok := request.GetArguments()["query"].(string)
	if !ok || query == "" {
		return &mcp.CallToolResult{
			Content: []mcp.Content{mcp.TextContent{Type: "text", Text: "query parameter is required"}},
			IsError: true,
		}, nil
	}

	limit := 10
	if l, ok := request.GetArguments()["limit"].(float64); ok && l > 0 {
		limit = int(l)
	}

	results, err := s.searcher.Search(query, limit)
	if err != nil {
		return &mcp.CallToolResult{
			Content: []mcp.Content{mcp.TextContent{Type: "text", Text: fmt.Sprintf("search error: %v", err)}},
			IsError: true,
		}, nil
	}

	text, err := search.MarshalResults(results)
	if err != nil {
		return nil, fmt.Errorf("marshal results: %w", err)
	}

	return &mcp.CallToolResult{
		Content: []mcp.Content{mcp.TextContent{Type: "text", Text: text}},
	}, nil
}

func (s *Server) handleCallAPI(ctx context.Context, request mcp.CallToolRequest) (*mcp.CallToolResult, error) {
	args := request.GetArguments()

	operationID, ok := args["operation_id"].(string)
	if !ok || operationID == "" {
		return &mcp.CallToolResult{
			Content: []mcp.Content{mcp.TextContent{Type: "text", Text: "operation_id is required"}},
			IsError: true,
		}, nil
	}

	params := make(map[string]any)
	if p, ok := args["params"].(map[string]any); ok {
		params = p
	}

	reason, _ := args["reason"].(string)

	paramsJSON, _ := json.Marshal(params)

	agentName, ok := auth.AgentFromContext(ctx)
	if !ok {
		return &mcp.CallToolResult{
			Content: []mcp.Content{mcp.TextContent{Type: "text", Text: "authentication required: no agent identity in context"}},
			IsError: true,
		}, nil
	}

	// Authorization check
	if s.authorizer != nil {
		allowed, err := s.authorizer.Check(agentName, operationID)
		if err != nil {
			return &mcp.CallToolResult{
				Content: []mcp.Content{mcp.TextContent{Type: "text", Text: fmt.Sprintf("authorization error: %v", err)}},
				IsError: true,
			}, nil
		}
		if !allowed {
			if err := s.auditLog.Log(audit.Entry{
				AgentName:      agentName,
				OperationID:    operationID,
				ParamsJSON:     string(paramsJSON),
				Reason:         reason,
				ApprovalStatus: "denied",
				ErrorMessage:   "not authorized",
			}); err != nil {
				log.Printf("audit log error: %v", err)
			}
			return &mcp.CallToolResult{
				Content: []mcp.Content{mcp.TextContent{Type: "text", Text: "not authorized to call this operation"}},
				IsError: true,
			}, nil
		}
	}

	// Approval check
	if s.approver != nil {
		approved, err := s.approver.CheckAndWait(ctx, operationID, agentName, string(paramsJSON), reason)
		if err != nil {
			return &mcp.CallToolResult{
				Content: []mcp.Content{mcp.TextContent{Type: "text", Text: fmt.Sprintf("approval error: %v", err)}},
				IsError: true,
			}, nil
		}
		if !approved {
			if err := s.auditLog.Log(audit.Entry{
				AgentName:      agentName,
				OperationID:    operationID,
				ParamsJSON:     string(paramsJSON),
				Reason:         reason,
				ApprovalStatus: "rejected",
			}); err != nil {
				log.Printf("audit log error: %v", err)
			}
			return &mcp.CallToolResult{
				Content: []mcp.Content{mcp.TextContent{Type: "text", Text: "request rejected by approver"}},
				IsError: true,
			}, nil
		}
	}

	// Execute the API call
	result, err := s.proxyClient.Call(operationID, params)
	if err != nil {
		if logErr := s.auditLog.Log(audit.Entry{
			AgentName:      agentName,
			OperationID:    operationID,
			ParamsJSON:     string(paramsJSON),
			Reason:         reason,
			ApprovalStatus: "approved",
			ErrorMessage:   err.Error(),
		}); logErr != nil {
			log.Printf("audit log error: %v", logErr)
		}
		return &mcp.CallToolResult{
			Content: []mcp.Content{mcp.TextContent{Type: "text", Text: fmt.Sprintf("API call failed: %v", err)}},
			IsError: true,
		}, nil
	}

	if err := s.auditLog.Log(audit.Entry{
		AgentName:      agentName,
		OperationID:    operationID,
		ParamsJSON:     string(paramsJSON),
		Reason:         reason,
		ResponseStatus: result.StatusCode,
		ResponseBody:   result.Body,
		ApprovalStatus: "approved",
	}); err != nil {
		log.Printf("audit log error: %v", err)
	}

	resultJSON, _ := json.Marshal(result)
	return &mcp.CallToolResult{
		Content: []mcp.Content{mcp.TextContent{Type: "text", Text: string(resultJSON)}},
	}, nil
}
