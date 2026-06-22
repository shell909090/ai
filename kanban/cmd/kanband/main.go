// kanband is a thin CLI wrapper around the internal/kanban scheduler
// library. All business logic lives in the library; this file does
// only flag parsing, config wiring, signal handling and a fatal exit helper.
package main

import (
	"context"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/shell909090/kanban/internal/kanban"
)

func main() {
	pollStr := flag.String("poll", "", "timer interval (e.g. 5s, 10s); overrides config.yaml")
	logPath := flag.String("log", "", "log file path (default stderr)")
	httpListen := flag.String("http", "", "HTTP listen address for /health (default 127.0.0.1:8087)")
	maxTotal := flag.Int("max-total", -1, "max concurrent tasks globally (overrides config; default 3)")
	maxPerProject := flag.Int("max-per-project", -1, "max concurrent tasks per project (overrides config; default 1)")
	flag.Parse()

	cfg, err := kanban.LoadConfig()
	if err != nil {
		die("config: %v", err)
	}
	if *httpListen != "" {
		cfg.HTTPListen = *httpListen
	}
	if *pollStr != "" {
		if d, err := time.ParseDuration(*pollStr); err != nil {
			die("parse -poll: %v", err)
		} else {
			cfg.PollInterval = d
		}
	}
	if *maxTotal > 0 {
		cfg.MaxDoingTotal = *maxTotal
	}
	if *maxPerProject > 0 {
		cfg.MaxDoingPerProject = *maxPerProject
	}
	if err := cfg.Validate(); err != nil {
		die("validate: %v", err)
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
