package ipc

import (
	"context"
	"encoding/json"
	"fmt"
	mlog "github.com/olafnew/mastermice-svc/internal/logging"
	"net"
	"sync"

	winio "github.com/Microsoft/go-winio"
)

const EventPipeName = `\\.\pipe\MasterMice-events`

// EventPipe is a push-based pipe server for real-time events to the agent.
// Unlike the main pipe (request-response), this pipe is write-only from
// the server's perspective. The agent connects and receives a stream of
// JSON-line events.
type EventPipe struct {
	clients map[net.Conn]bool
	mu      sync.Mutex
}

// NewEventPipe creates a new event pipe server.
func NewEventPipe() *EventPipe {
	return &EventPipe{
		clients: make(map[net.Conn]bool),
	}
}

// Run starts the event pipe listener. Blocks until context is cancelled.
func (ep *EventPipe) Run(ctx context.Context) error {
	cfg := &winio.PipeConfig{
		SecurityDescriptor: "D:P(A;;GA;;;WD)", // allow everyone
		MessageMode:        false,
	}

	l, err := winio.ListenPipe(EventPipeName, cfg)
	if err != nil {
		return fmt.Errorf("listen event pipe: %w", err)
	}
	defer l.Close()

	mlog.Printf("[EventPipe] Listening on %s\n", EventPipeName)

	go func() {
		<-ctx.Done()
		l.Close()
	}()

	for {
		conn, err := l.Accept()
		if err != nil {
			select {
			case <-ctx.Done():
				return nil
			default:
				mlog.Printf("[EventPipe] Accept error: %v\n", err)
				continue
			}
		}

		ep.mu.Lock()
		ep.clients[conn] = true
		count := len(ep.clients)
		ep.mu.Unlock()

		mlog.Printf("[EventPipe] Agent connected (%d total)\n", count)

		// Monitor for disconnect
		go func(c net.Conn) {
			buf := make([]byte, 1)
			c.Read(buf) // blocks until disconnect
			ep.mu.Lock()
			delete(ep.clients, c)
			remaining := len(ep.clients)
			ep.mu.Unlock()
			c.Close()
			mlog.Printf("[EventPipe] Agent disconnected (%d remaining)\n", remaining)
		}(conn)
	}
}

// Push sends an event to all connected agents. Non-blocking — drops
// events for slow/dead connections.
func (ep *EventPipe) Push(eventName string, data map[string]interface{}) {
	msg := map[string]interface{}{
		"event": eventName,
		"data":  data,
	}
	raw, err := json.Marshal(msg)
	if err != nil {
		return
	}
	raw = append(raw, '\n')

	ep.mu.Lock()
	defer ep.mu.Unlock()

	var dead []net.Conn
	for conn := range ep.clients {
		_, werr := conn.Write(raw)
		if werr != nil {
			dead = append(dead, conn)
		}
	}
	for _, conn := range dead {
		delete(ep.clients, conn)
		conn.Close()
	}
}

// HasClients returns true if at least one agent is connected.
func (ep *EventPipe) HasClients() bool {
	ep.mu.Lock()
	defer ep.mu.Unlock()
	return len(ep.clients) > 0
}
