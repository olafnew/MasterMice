package ipc

import (
	"bufio"
	"context"
	"fmt"
	mlog "github.com/olafnew/mastermice-svc/internal/logging"
	"net"

	winio "github.com/Microsoft/go-winio"
)

// Server listens on a named pipe and handles client connections.
type Server struct {
	handler     *Handler
	broadcaster *Broadcaster
}

// NewServer creates a pipe server with the given command handler.
func NewServer(handler *Handler, broadcaster *Broadcaster) *Server {
	return &Server{
		handler:     handler,
		broadcaster: broadcaster,
	}
}

// Run starts the named pipe server. Blocks until ctx is cancelled.
func (s *Server) Run(ctx context.Context) error {
	cfg := &winio.PipeConfig{
		// Allow interactive users + admins
		SecurityDescriptor: "D:(A;;GA;;;IU)(A;;GA;;;BA)",
		InputBufferSize:    4096,
		OutputBufferSize:   4096,
	}

	listener, err := winio.ListenPipe(PipeName, cfg)
	if err != nil {
		return fmt.Errorf("ipc: failed to create pipe %s: %w", PipeName, err)
	}

	mlog.Printf("[IPC] Listening on %s\n", PipeName)

	// Close listener when context is done
	go func() {
		<-ctx.Done()
		listener.Close()
	}()

	for {
		conn, err := listener.Accept()
		if err != nil {
			select {
			case <-ctx.Done():
				return nil // clean shutdown
			default:
				mlog.Printf("[IPC] Accept error: %v\n", err)
				continue
			}
		}

		mlog.Printf("[IPC] Client connected (%d total)\n", s.broadcaster.ClientCount()+1)
		s.broadcaster.Add(conn)
		go s.handleClient(conn)
	}
}

// handleClient reads JSON-line requests from a client and sends responses.
func (s *Server) handleClient(conn net.Conn) {
	defer func() {
		s.broadcaster.Remove(conn)
		conn.Close()
		mlog.Printf("[IPC] Client disconnected (%d remaining)\n", s.broadcaster.ClientCount())
	}()

	scanner := bufio.NewScanner(conn)
	// Allow up to 64KB per line (generous for JSON commands)
	scanner.Buffer(make([]byte, 0, 65536), 65536)

	for scanner.Scan() {
		line := scanner.Bytes()
		if len(line) == 0 {
			continue
		}

		req, err := DecodeRequest(line)
		if err != nil {
			resp := &Response{ID: 0, OK: false, Err: fmt.Sprintf("invalid JSON: %v", err)}
			if data, encErr := Encode(resp); encErr == nil {
				conn.Write(data)
			}
			continue
		}

		resp := s.handler.Handle(req)
		data, err := Encode(resp)
		if err != nil {
			errData, _ := Encode(&Response{ID: req.ID, OK: false, Err: "response encoding failed"})
			conn.Write(errData)
			continue
		}
		if _, err := conn.Write(data); err != nil {
			return // client disconnected
		}
	}
}
