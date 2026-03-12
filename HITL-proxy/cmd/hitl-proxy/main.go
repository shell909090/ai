package main

import (
	"encoding/hex"
	"flag"
	"log"
	"net/http"
	"os"

	"github.com/shell909090/ai/HITL-proxy/internal/approval"
	"github.com/shell909090/ai/HITL-proxy/internal/audit"
	"github.com/shell909090/ai/HITL-proxy/internal/auth"
	"github.com/shell909090/ai/HITL-proxy/internal/authz"
	"github.com/shell909090/ai/HITL-proxy/internal/config"
	"github.com/shell909090/ai/HITL-proxy/internal/cred"
	"github.com/shell909090/ai/HITL-proxy/internal/database"
	mcpserver "github.com/shell909090/ai/HITL-proxy/internal/mcp"
	"github.com/shell909090/ai/HITL-proxy/internal/proxy"
	"github.com/shell909090/ai/HITL-proxy/internal/search"
	"github.com/shell909090/ai/HITL-proxy/internal/web"
)

func main() {
	configPath := flag.String("config", "config.yaml", "path to config file")
	flag.Parse()

	cfg, err := config.Load(*configPath)
	if err != nil {
		log.Fatalf("load config: %v", err)
	}

	db, err := database.Open(cfg.Database.Path)
	if err != nil {
		log.Fatalf("open database: %v", err)
	}
	defer db.Close()

	// Credential store
	credKey := os.Getenv("HITL_CRED_KEY")
	if credKey == "" {
		credKey = "0000000000000000000000000000000000000000000000000000000000000000" // dev default
		log.Println("WARNING: using default credential encryption key, set HITL_CRED_KEY in production")
	}
	keyBytes, err := hex.DecodeString(credKey)
	if err != nil {
		log.Fatalf("decode HITL_CRED_KEY: %v", err)
	}
	credStore, err := cred.NewStore(cfg.Cred.File, keyBytes)
	if err != nil {
		log.Fatalf("create credential store: %v", err)
	}

	// Components
	searcher := search.NewFTS5Searcher(db)
	auditLog := audit.NewLogger(db)
	approvalEngine := approval.NewEngine(db)
	authzChecker := authz.NewChecker(db, true)
	proxyClient := proxy.NewClient(db, credStore)

	// Authentication
	authenticator := auth.NewAuthenticator(db)

	// MCP server
	baseURL := "http://localhost" + cfg.Listen
	mcpSrv := mcpserver.NewServer(authenticator, searcher, proxyClient, auditLog, approvalEngine, authzChecker, baseURL)

	// Web UI
	webHandler, err := web.NewHandler(approvalEngine, db, searcher)
	if err != nil {
		log.Fatalf("create web handler: %v", err)
	}

	// HTTP routing
	mux := http.NewServeMux()

	// Static files
	mux.Handle("GET /static/", http.StripPrefix("/static/", http.FileServer(http.Dir("static"))))

	// Web UI routes
	webHandler.RegisterRoutes(mux)

	// MCP SSE routes (wrapped with auth middleware)
	sseSrv := mcpSrv.SSEServer()
	mux.Handle("/mcp/", mcpSrv.AuthMiddleware()(sseSrv))

	log.Printf("HITL-proxy listening on %s", cfg.Listen)
	if err := http.ListenAndServe(cfg.Listen, mux); err != nil {
		log.Fatalf("server error: %v", err)
	}
}
