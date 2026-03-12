package mcp

import (
	"context"
	"net/http"

	"github.com/mark3labs/mcp-go/mcp"
	"github.com/mark3labs/mcp-go/server"

	"github.com/shell909090/ai/HITL-proxy/internal/audit"
	"github.com/shell909090/ai/HITL-proxy/internal/auth"
	"github.com/shell909090/ai/HITL-proxy/internal/proxy"
	"github.com/shell909090/ai/HITL-proxy/internal/search"
)

// Approver checks whether an operation needs approval and blocks until resolved.
type Approver interface {
	CheckAndWait(ctx context.Context, operationID, agentName, paramsJSON, reason string) (approved bool, err error)
}

// Authorizer checks whether an agent is allowed to call an operation.
type Authorizer interface {
	Check(agentName, operationID string) (bool, error)
}

// Server wraps the MCP server and its dependencies.
type Server struct {
	mcp  *server.MCPServer
	sse  *server.SSEServer
	auth *auth.Authenticator

	searcher    search.Searcher
	proxyClient *proxy.Client
	auditLog    *audit.Logger
	approver    Approver
	authorizer  Authorizer
}

// NewServer creates a new MCP server with all tools registered.
func NewServer(authenticator *auth.Authenticator, searcher search.Searcher, proxyClient *proxy.Client, auditLog *audit.Logger, approver Approver, authorizer Authorizer, baseURL string) *Server {
	s := &Server{
		auth:        authenticator,
		searcher:    searcher,
		proxyClient: proxyClient,
		auditLog:    auditLog,
		approver:    approver,
		authorizer:  authorizer,
	}

	s.mcp = server.NewMCPServer(
		"hitl-proxy",
		"0.1.0",
		server.WithToolCapabilities(true),
	)

	s.registerTools()

	// SSEContextFunc propagates agent identity from the HTTP middleware
	// into the MCP tool handler context.
	contextFunc := func(ctx context.Context, r *http.Request) context.Context {
		if agentName, ok := auth.AgentFromContext(r.Context()); ok {
			return auth.ContextWithAgent(ctx, agentName)
		}
		return ctx
	}

	s.sse = server.NewSSEServer(
		s.mcp,
		server.WithBaseURL(baseURL),
		server.WithStaticBasePath("/mcp"),
		server.WithSSEContextFunc(contextFunc),
	)

	return s
}

// AuthMiddleware returns the HTTP authentication middleware for MCP routes.
func (s *Server) AuthMiddleware() func(http.Handler) http.Handler {
	return s.auth.Middleware
}

func (s *Server) registerTools() {
	searchTool := mcp.NewTool("search_tools",
		mcp.WithDescription("Search available API operations by natural language query. Returns matching operations with their descriptions and dependencies."),
		mcp.WithString("query",
			mcp.Description("Natural language search query (e.g. 'list repositories', 'create issue')"),
			mcp.Required(),
		),
		mcp.WithNumber("limit",
			mcp.Description("Maximum number of results to return (default 10)"),
		),
	)
	s.mcp.AddTool(searchTool, s.handleSearchTools)

	callTool := mcp.NewTool("call_api",
		mcp.WithDescription("Call a target API operation. Requires operationId and parameters. May block for human approval depending on the operation."),
		mcp.WithString("operation_id",
			mcp.Description("The operationId of the API operation to call"),
			mcp.Required(),
		),
		mcp.WithObject("params",
			mcp.Description("Parameters for the API call (path params, query params, body fields)"),
		),
		mcp.WithString("reason",
			mcp.Description("Explanation of why this API call is being made"),
		),
	)
	s.mcp.AddTool(callTool, s.handleCallAPI)
}

// SSEServer returns the underlying SSE server for HTTP mounting.
func (s *Server) SSEServer() *server.SSEServer {
	return s.sse
}

// MCPServer returns the underlying MCP server.
func (s *Server) MCPServer() *server.MCPServer {
	return s.mcp
}
