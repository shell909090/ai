package cred

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"sync"
)

// Store manages encrypted credentials for target APIs.
type Store struct {
	mu   sync.RWMutex
	path string
	key  []byte                       // 32-byte AES-256 key
	data map[string]map[string]string // specName → {header: value, ...}
}

// NewStore creates a credential store. The encryption key must be 32 bytes (AES-256).
func NewStore(path string, key []byte) (*Store, error) {
	if len(key) != 32 {
		return nil, fmt.Errorf("encryption key must be 32 bytes, got %d", len(key))
	}

	s := &Store{
		path: path,
		key:  key,
		data: make(map[string]map[string]string),
	}

	if _, err := os.Stat(path); err == nil {
		if err := s.load(); err != nil {
			return nil, fmt.Errorf("load credentials: %w", err)
		}
	}

	return s, nil
}

// Get returns a copy of credentials for a spec.
func (s *Store) Get(specName string) (map[string]string, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	creds, ok := s.data[specName]
	if !ok {
		return nil, false
	}
	cp := make(map[string]string, len(creds))
	for k, v := range creds {
		cp[k] = v
	}
	return cp, true
}

// Set stores a copy of credentials for a spec and persists to disk.
func (s *Store) Set(specName string, creds map[string]string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	cp := make(map[string]string, len(creds))
	for k, v := range creds {
		cp[k] = v
	}
	s.data[specName] = cp
	return s.save()
}

func (s *Store) load() error {
	ciphertext, err := os.ReadFile(s.path)
	if err != nil {
		return err
	}

	plaintext, err := s.decrypt(ciphertext)
	if err != nil {
		return fmt.Errorf("decrypt: %w", err)
	}

	return json.Unmarshal(plaintext, &s.data)
}

func (s *Store) save() error {
	plaintext, err := json.Marshal(s.data)
	if err != nil {
		return err
	}

	ciphertext, err := s.encrypt(plaintext)
	if err != nil {
		return fmt.Errorf("encrypt: %w", err)
	}

	return os.WriteFile(s.path, ciphertext, 0600)
}

func (s *Store) encrypt(plaintext []byte) ([]byte, error) {
	block, err := aes.NewCipher(s.key)
	if err != nil {
		return nil, err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}

	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return nil, err
	}

	return gcm.Seal(nonce, nonce, plaintext, nil), nil
}

func (s *Store) decrypt(ciphertext []byte) ([]byte, error) {
	block, err := aes.NewCipher(s.key)
	if err != nil {
		return nil, err
	}

	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}

	nonceSize := gcm.NonceSize()
	if len(ciphertext) < nonceSize {
		return nil, fmt.Errorf("ciphertext too short")
	}

	nonce, ciphertext := ciphertext[:nonceSize], ciphertext[nonceSize:]
	return gcm.Open(nil, nonce, ciphertext, nil)
}
