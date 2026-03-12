package main

import (
	"context"
	"encoding/hex"
	"flag"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"

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

	// Vector search: enabled when OPENAI_BASE_URL is set.
	var vecSearcher *search.VectorSearcher
	if baseURLEnv := os.Getenv("OPENAI_BASE_URL"); baseURLEnv != "" {
		embedder := search.NewHTTPEmbedder(
			baseURLEnv,
			os.Getenv("OPENAI_API_KEY"),
			cfg.Embedding.Model,
		)
		store, err := search.NewChromemStore(cfg.Vector.Path)
		if err != nil {
			log.Fatalf("open vector store: %v", err)
		}
		vecSearcher = search.NewVectorSearcher(embedder, store)
		log.Printf("vector search enabled: model=%s base=%s", cfg.Embedding.Model, baseURLEnv)
	} else {
		log.Println("vector search disabled: set OPENAI_BASE_URL to enable")
	}

	// Components
	searcher := search.NewHybridSearcher(db, vecSearcher)
	auditLog := audit.NewLogger(db)
	hub := approval.NewSSEHub()
	approvalEngine := approval.NewEngine(
		db,
		cfg.Approval.TimeoutDuration(),
		cfg.Approval.PollIntervalDuration(),
		hub,
	)

	// Cleanup orphaned pending requests from previous run
	if err := approvalEngine.CleanupOrphans(); err != nil {
		log.Fatalf("cleanup orphans: %v", err)
	}

	// Background context for timer goroutine
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	// Start background expiry scanner
	approvalEngine.StartBackgroundTimer(ctx, cfg.Approval.ScanIntervalDuration())

	// Handle shutdown signals
	go func() {
		sigCh := make(chan os.Signal, 1)
		signal.Notify(sigCh, syscall.SIGINT, syscall.SIGTERM)
		<-sigCh
		log.Println("shutting down...")
		cancel()
		os.Exit(0)
	}()

	authzChecker := authz.NewChecker(db, true)
	proxyClient := proxy.NewClient(db, credStore)

	// Authentication
	authenticator := auth.NewAuthenticator(db)

	// MCP server
	listenAddr := cfg.Listen
	if listenAddr[0] == ':' {
		listenAddr = "localhost" + listenAddr
	}
	baseURL := "http://" + listenAddr
	mcpSrv := mcpserver.NewServer(authenticator, searcher, proxyClient, auditLog, approvalEngine, authzChecker, baseURL)

	// Admin password for Web UI
	adminPassword := os.Getenv("HITL_ADMIN_PASSWORD")
	if adminPassword == "" {
		log.Fatal("HITL_ADMIN_PASSWORD must be set")
	}

	// Web UI
	webHandler, err := web.NewHandler(approvalEngine, db, searcher, hub, authenticator, credStore, adminPassword)
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
