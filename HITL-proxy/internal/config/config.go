package config

import (
	"fmt"
	"os"

	"gopkg.in/yaml.v3"
)

type Config struct {
	Listen   string         `yaml:"listen"`
	Database DatabaseConfig `yaml:"database"`
	Cred     CredConfig     `yaml:"cred"`
}

type DatabaseConfig struct {
	Path string `yaml:"path"`
}

type CredConfig struct {
	File string `yaml:"file"`
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
	}

	if err := yaml.Unmarshal(data, cfg); err != nil {
		return nil, fmt.Errorf("parse config: %w", err)
	}

	return cfg, nil
}
