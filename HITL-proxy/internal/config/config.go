package config

import (
	"fmt"
	"os"
	"time"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Listen    string          `yaml:"listen"`
	Database  DatabaseConfig  `yaml:"database"`
	Cred      CredConfig      `yaml:"cred"`
	Approval  ApprovalConfig  `yaml:"approval"`
	Embedding EmbeddingConfig `yaml:"embedding"`
	Vector    VectorConfig    `yaml:"vector"`
}

type DatabaseConfig struct {
	Path string `yaml:"path"`
}

type CredConfig struct {
	File string `yaml:"file"`
}

// EmbeddingConfig configures the OpenAI-compatible embedding API.
// BaseURL and APIKey are read from OPENAI_BASE_URL and OPENAI_API_KEY
// environment variables; the yaml fields serve as fallbacks.
type EmbeddingConfig struct {
	Model string `yaml:"model"` // e.g. "text-embedding-3-small" or "nomic-embed-text"
}

// VectorConfig configures the vector store.
type VectorConfig struct {
	Path string `yaml:"path"` // chromem-go persistence directory, default "vector.db"
}

type ApprovalConfig struct {
	Timeout      string `yaml:"timeout"`       // default "5m"
	PollInterval string `yaml:"poll_interval"` // default "1s"
	ScanInterval string `yaml:"scan_interval"` // default "10s"
}

func (a ApprovalConfig) TimeoutDuration() time.Duration {
	d, err := time.ParseDuration(a.Timeout)
	if err != nil {
		return 5 * time.Minute
	}
	return d
}

func (a ApprovalConfig) PollIntervalDuration() time.Duration {
	d, err := time.ParseDuration(a.PollInterval)
	if err != nil {
		return 1 * time.Second
	}
	return d
}

func (a ApprovalConfig) ScanIntervalDuration() time.Duration {
	d, err := time.ParseDuration(a.ScanInterval)
	if err != nil {
		return 10 * time.Second
	}
	return d
}

func Load(path string) (*Config, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, fmt.Errorf("read config: %w", err)
	}

	cfg := &Config{
		Listen: ":8080",
		Database: DatabaseConfig{
			Path: "hitl.db",
		},
		Cred: CredConfig{
			File: "credentials.enc",
		},
		Approval: ApprovalConfig{
			Timeout:      "5m",
			PollInterval: "1s",
			ScanInterval: "10s",
		},
		Embedding: EmbeddingConfig{
			Model: "text-embedding-3-small",
		},
		Vector: VectorConfig{
			Path: "vector.db",
		},
	}

	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	return cfg, nil
}
