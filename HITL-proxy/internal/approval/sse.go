package approval

import "sync"

// SSEEvent represents an event to be sent to browser clients.
type SSEEvent struct {
	Type string // e.g. "new_request", "decided", "expired"
	ID   int64  // approval request ID, 0 if not applicable
}

// SSEHub is a fan-out broadcaster for SSE clients.
type SSEHub struct {
	mu      sync.Mutex
	clients map[chan SSEEvent]struct{}
}

func NewSSEHub() *SSEHub {
	return &SSEHub{
		clients: make(map[chan SSEEvent]struct{}),
	}
}

// Subscribe returns a buffered channel that receives events.
func (h *SSEHub) Subscribe() chan SSEEvent {
	ch := make(chan SSEEvent, 16)
	h.mu.Lock()
	h.clients[ch] = struct{}{}
	h.mu.Unlock()
	return ch
}

// Unsubscribe removes a client channel and closes it.
func (h *SSEHub) Unsubscribe(ch chan SSEEvent) {
	h.mu.Lock()
	delete(h.clients, ch)
	h.mu.Unlock()
	close(ch)
}

// Broadcast sends an event to all connected clients.
// Slow clients that have a full buffer will have the event dropped.
func (h *SSEHub) Broadcast(event SSEEvent) {
	h.mu.Lock()
	defer h.mu.Unlock()
	for ch := range h.clients {
		select {
		case ch <- event:
		default:
			// drop for slow client
		}
	}
}
