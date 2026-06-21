// kanband is a thin CLI wrapper around the internal/kanban scheduler
// library. All business logic lives in the library; this file does
// only flag parsing, config wiring, signal handling and a fatal
// exit helper.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"path/filepath"
	"syscall"
	"time"

	"github.com/shell909090/kanban/internal/kanban"
)

func main() {
	pollStr := flag.String("poll", "5s", "poll interval (e.g. 5s, 10s)")
	idleStr := flag.String("idle", "10s", "finish-watcher interval (e.g. 5s, 30s)")
	workdir := flag.String("workdir", "", "workdir for opencode session (default $KANBAN_WORKDIR; must be absolute)")
	logPath := flag.String("log", "", "log file path (default stderr)")
	httpListen := flag.String("http", "127.0.0.1:8087", "HTTP listen address for /health")
	maxTotal := flag.Int("max-total", -1, "max cards in doing across all projects (overrides env; default 2)")
	maxPerProject := flag.Int("max-per-project", -1, "max cards in doing per project (overrides env; default 1)")
	flag.Parse()

	cfg, err := kanban.LoadConfig()
	if err != nil {
		die("config: %v", err)
	}
	cfg.HTTPListen = *httpListen
	if *workdir != "" {
		cfg.WorkDir = *workdir
	}
	if cfg.WorkDir == "" {
		die("workdir is required: pass -workdir <abs-path> or set KANBAN_WORKDIR")
	}
	abs, err := filepath.Abs(cfg.WorkDir)
	if err != nil {
		die("resolve workdir: %v", err)
	}
	if info, err := os.Stat(abs); err != nil {
		die("workdir not accessible: %v", err)
	} else if !info.IsDir() {
		die("workdir is not a directory: %s", abs)
	}
	cfg.WorkDir = abs
	if d, err := time.ParseDuration(*pollStr); err != nil {
		die("parse -poll: %v", err)
	} else {
		cfg.PollInterval = d
	}
	if d, err := time.ParseDuration(*idleStr); err != nil {
		die("parse -idle: %v", err)
	} else {
		cfg.IdleInterval = d
	}
	if *maxTotal > 0 {
		cfg.MaxDoingTotal = *maxTotal
	}
	if *maxPerProject > 0 {
		cfg.MaxDoingPerProject = *maxPerProject
	}
	if *logPath != "" {
		f, err := os.Create(*logPath)
		if err != nil {
			die("open log: %v", err)
		}
		kanban.SetLogWriter(f)
		defer f.Close()
	}

	srv, err := kanban.New(cfg)
	if err != nil {
		die("init: %v", err)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	if err := srv.Run(ctx); err != nil {
		die("run: %v", err)
	}
}

func die(format string, args ...any) {
	fmt.Fprintf(os.Stderr, "FATAL: "+format+"\n", args...)
	os.Exit(2)
}
