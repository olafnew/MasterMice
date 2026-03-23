package service

import (
	"fmt"
	"io"
	"log"
	"os"
	"path/filepath"
	"sync"
)

// RotatingLog writes to a file with size cap. When the file exceeds maxBytes,
// it truncates the first half (keeping recent entries).
type RotatingLog struct {
	path     string
	maxBytes int64
	mu       sync.Mutex
	file     *os.File
}

// NewRotatingLog opens or creates a log file with rotation.
func NewRotatingLog(path string, maxKB int) (*RotatingLog, error) {
	dir := filepath.Dir(path)
	os.MkdirAll(dir, 0755)

	f, err := os.OpenFile(path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
	if err != nil {
		return nil, fmt.Errorf("cannot open log %s: %w", path, err)
	}

	return &RotatingLog{
		path:     path,
		maxBytes: int64(maxKB) * 1024,
		file:     f,
	}, nil
}

// Write implements io.Writer. Checks size after each write.
func (r *RotatingLog) Write(p []byte) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()

	n, err := r.file.Write(p)
	if err != nil {
		return n, err
	}

	// Check if rotation needed
	info, err := r.file.Stat()
	if err == nil && info.Size() > r.maxBytes {
		r.rotate()
	}

	return n, nil
}

// rotate keeps the last half of the file.
func (r *RotatingLog) rotate() {
	r.file.Close()

	data, err := os.ReadFile(r.path)
	if err != nil {
		// Can't read — just truncate
		r.file, _ = os.OpenFile(r.path, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
		return
	}

	// Keep the second half
	half := len(data) / 2
	// Find first newline after half to avoid cutting a line
	for half < len(data) && data[half] != '\n' {
		half++
	}
	if half < len(data) {
		half++ // skip the newline
	}

	f, err := os.OpenFile(r.path, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0644)
	if err != nil {
		return
	}
	f.Write([]byte("--- log rotated ---\n"))
	f.Write(data[half:])
	r.file = f
}

// Close closes the log file.
func (r *RotatingLog) Close() {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.file != nil {
		r.file.Close()
	}
}

// SetupLogging configures log output to both console and a rotating file.
// Returns a cleanup function.
func SetupLogging(logPath string, maxKB int) func() {
	rotLog, err := NewRotatingLog(logPath, maxKB)
	if err != nil {
		fmt.Printf("[WARN] Cannot open log file %s: %v\n", logPath, err)
		return func() {}
	}

	// Write to both stdout and the log file
	multi := io.MultiWriter(os.Stdout, rotLog)
	log.SetOutput(multi)
	// Redirect fmt.Printf via os.Stdout won't work, but log.* will go to both

	return func() {
		rotLog.Close()
	}
}
