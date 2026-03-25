// Package logging provides a shared log file writer for all MasterMice Go binaries.
// All components (service, agent) write to the same log file at
// %APPDATA%\MasterMice\mastermice.log — the same file the Python UI reads.
//
// The log file is opened in append mode with shared write access so
// multiple processes can write concurrently. Each line is prefixed with
// a timestamp and the component name.
//
// Usage:
//
//	logging.Init("mastermice-svc")
//	logging.Info("Device connected: %s", name)
//	logging.Error("Failed: %v", err)
package logging

import (
	"fmt"
	"os"
	"path/filepath"
	"sync"
	"time"
)

var (
	logFile   *os.File
	logMu     sync.Mutex
	component string
)

// Init opens the shared log file and sets the component name prefix.
// Safe to call multiple times (re-opens if already open).
func Init(componentName string) error {
	logMu.Lock()
	defer logMu.Unlock()

	component = componentName

	logPath := LogFilePath()
	dir := filepath.Dir(logPath)
	if err := os.MkdirAll(dir, 0755); err != nil {
		return fmt.Errorf("create log dir: %w", err)
	}

	f, err := os.OpenFile(logPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return fmt.Errorf("open log file: %w", err)
	}

	if logFile != nil {
		logFile.Close()
	}
	logFile = f
	return nil
}

// LogFilePath returns the path to the shared log file.
func LogFilePath() string {
	appData := os.Getenv("APPDATA")
	if appData == "" {
		home, _ := os.UserHomeDir()
		appData = home
	}
	return filepath.Join(appData, "MasterMice", "mastermice.log")
}

// Close closes the log file. Called on shutdown.
func Close() {
	logMu.Lock()
	defer logMu.Unlock()
	if logFile != nil {
		logFile.Close()
		logFile = nil
	}
}

// write formats and writes a log line to both the file and stdout.
func write(level, format string, args ...interface{}) {
	msg := fmt.Sprintf(format, args...)
	ts := time.Now().Format("2006-01-02 15:04:05")
	line := fmt.Sprintf("%s [%s] %s: %s\n", ts, component, level, msg)

	// Always print to stdout (visible in console/debug mode)
	fmt.Print(line)

	// Write to shared log file
	logMu.Lock()
	defer logMu.Unlock()
	if logFile != nil {
		logFile.WriteString(line)
		logFile.Sync() // flush immediately so UI sees it
	}
}

// Info logs an informational message.
func Info(format string, args ...interface{}) {
	write("INFO", format, args...)
}

// Error logs an error message.
func Error(format string, args ...interface{}) {
	write("ERROR", format, args...)
}

// Warn logs a warning message.
func Warn(format string, args ...interface{}) {
	write("WARN", format, args...)
}

// Printf is a drop-in replacement for fmt.Printf that also writes to the log file.
// Use this for backward compatibility with existing code.
func Printf(format string, args ...interface{}) {
	msg := fmt.Sprintf(format, args...)
	// Print to stdout as-is (backward compat)
	fmt.Print(msg)

	// Also write to log file
	logMu.Lock()
	defer logMu.Unlock()
	if logFile != nil {
		logFile.WriteString(msg)
		logFile.Sync()
	}
}

// Println is a drop-in replacement for fmt.Println.
func Println(args ...interface{}) {
	msg := fmt.Sprintln(args...)
	fmt.Print(msg)

	logMu.Lock()
	defer logMu.Unlock()
	if logFile != nil {
		logFile.WriteString(msg)
		logFile.Sync()
	}
}
