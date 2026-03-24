package config

import (
	"fmt"
	"path/filepath"
	"sync"
	"time"

	"github.com/fsnotify/fsnotify"
)

// Watcher monitors config.json for changes and notifies subscribers.
type Watcher struct {
	cfg       *Config
	callbacks []func(*Config)
	mu        sync.Mutex
	stop      chan struct{}
}

// NewWatcher creates a config file watcher.
func NewWatcher(cfg *Config) *Watcher {
	return &Watcher{
		cfg:  cfg,
		stop: make(chan struct{}),
	}
}

// OnChange registers a callback that fires when config changes on disk.
func (w *Watcher) OnChange(cb func(*Config)) {
	w.mu.Lock()
	defer w.mu.Unlock()
	w.callbacks = append(w.callbacks, cb)
}

// Start begins watching the config file. Non-blocking.
func (w *Watcher) Start() error {
	watcher, err := fsnotify.NewWatcher()
	if err != nil {
		return fmt.Errorf("fsnotify: %w", err)
	}

	path := w.cfg.filePath
	if path == "" {
		path = ConfigPath()
	}

	// Watch the directory (not the file) because editors often delete+recreate
	dir := ConfigDir()
	if err := watcher.Add(dir); err != nil {
		watcher.Close()
		return fmt.Errorf("watch %s: %w", dir, err)
	}

	go func() {
		defer watcher.Close()
		var debounce *time.Timer

		for {
			select {
			case <-w.stop:
				return
			case event, ok := <-watcher.Events:
				if !ok {
					return
				}
				// Only react to config.json writes
				if event.Op&(fsnotify.Write|fsnotify.Create) == 0 {
					continue
				}
				if filepath.Base(event.Name) != "config.json" {
					continue
				}
				// Debounce: wait 200ms before reloading (editors do multiple writes)
				if debounce != nil {
					debounce.Stop()
				}
				debounce = time.AfterFunc(200*time.Millisecond, func() {
					w.reload()
				})
			case err, ok := <-watcher.Errors:
				if !ok {
					return
				}
				fmt.Printf("[ConfigWatch] Error: %v\n", err)
			}
		}
	}()

	fmt.Printf("[ConfigWatch] Watching %s\n", dir)
	return nil
}

// Stop stops the watcher.
func (w *Watcher) Stop() {
	close(w.stop)
}

// GetConfig returns the current config (thread-safe).
func (w *Watcher) GetConfig() *Config {
	return w.cfg
}

func (w *Watcher) reload() {
	newCfg, err := Load()
	if err != nil {
		fmt.Printf("[ConfigWatch] Reload failed: %v\n", err)
		return
	}

	w.cfg = newCfg
	fmt.Println("[ConfigWatch] Config reloaded")

	w.mu.Lock()
	cbs := make([]func(*Config), len(w.callbacks))
	copy(cbs, w.callbacks)
	w.mu.Unlock()

	for _, cb := range cbs {
		cb(newCfg)
	}
}
