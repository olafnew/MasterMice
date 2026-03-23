package service

import (
	"context"
	"fmt"
	"runtime"
	"time"
)

// MemoryWatchdog monitors the process working set and logs warnings
// if memory exceeds the threshold. In a service, this can trigger a
// graceful restart.
type MemoryWatchdog struct {
	ThresholdMB float64
	IntervalSec int
	OnExceed    func(allocMB, sysMB float64) // optional callback
}

// DefaultWatchdog creates a watchdog with 50 MB threshold, 60s interval.
func DefaultWatchdog() *MemoryWatchdog {
	return &MemoryWatchdog{
		ThresholdMB: 50.0,
		IntervalSec: 60,
	}
}

// Run starts the watchdog loop. Blocks until ctx is cancelled.
func (w *MemoryWatchdog) Run(ctx context.Context) {
	ticker := time.NewTicker(time.Duration(w.IntervalSec) * time.Second)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			var mem runtime.MemStats
			runtime.ReadMemStats(&mem)

			allocMB := float64(mem.Alloc) / 1024 / 1024
			sysMB := float64(mem.Sys) / 1024 / 1024

			if allocMB > w.ThresholdMB {
				fmt.Printf("[WATCHDOG] Memory exceeds threshold: alloc=%.1fMB sys=%.1fMB (limit=%.0fMB)\n",
					allocMB, sysMB, w.ThresholdMB)
				if w.OnExceed != nil {
					w.OnExceed(allocMB, sysMB)
				}
			}
		}
	}
}
