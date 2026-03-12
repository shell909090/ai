package auth

import (
	"net/http"
	"strings"
)

// Middleware returns an HTTP middleware that validates Bearer tokens
// and injects the agent name into the request context.
func (a *Authenticator) Middleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hdr := r.Header.Get("Authorization")
		if !strings.HasPrefix(hdr, "Bearer ") {
			http.Error(w, "missing or invalid Authorization header", http.StatusUnauthorized)
			return
		}
		apiKey := strings.TrimPrefix(hdr, "Bearer ")

		agentName, err := a.Validate(apiKey)
		if err != nil {
			http.Error(w, "invalid API key", http.StatusUnauthorized)
			return
		}

		ctx := ContextWithAgent(r.Context(), agentName)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}
