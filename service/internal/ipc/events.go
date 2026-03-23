package ipc

import (
	"net"
	"sync"
)

// Broadcaster fans out events to all connected pipe clients.
type Broadcaster struct {
	mu      sync.Mutex
	clients map[net.Conn]struct{}
}

// NewBroadcaster creates a new event broadcaster.
func NewBroadcaster() *Broadcaster {
	return &Broadcaster{
		clients: make(map[net.Conn]struct{}),
	}
}

// Add registers a client connection for event broadcasting.
func (b *Broadcaster) Add(conn net.Conn) {
	b.mu.Lock()
	b.clients[conn] = struct{}{}
	b.mu.Unlock()
}

// Remove unregisters a client connection.
func (b *Broadcaster) Remove(conn net.Conn) {
	b.mu.Lock()
	delete(b.clients, conn)
	b.mu.Unlock()
}

// Broadcast sends an event to all connected clients.
// Removes clients that fail to write.
func (b *Broadcaster) Broadcast(evt *Event) {
	data, err := Encode(evt)
	if err != nil {
		return
	}

	b.mu.Lock()
	var failed []net.Conn
	for conn := range b.clients {
		_, werr := conn.Write(data)
		if werr != nil {
			failed = append(failed, conn)
		}
	}
	for _, conn := range failed {
		delete(b.clients, conn)
	}
	b.mu.Unlock()

	// Close failed connections outside the lock
	for _, conn := range failed {
		conn.Close()
	}
}

// ClientCount returns the number of connected clients.
func (b *Broadcaster) ClientCount() int {
	b.mu.Lock()
	defer b.mu.Unlock()
	return len(b.clients)
}
