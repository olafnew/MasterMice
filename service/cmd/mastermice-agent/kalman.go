package main

// KalmanFilter2D implements a simple 2D Kalman filter for mouse gesture data.
// State: [vx, vy] (velocity in X and Y axes)
// Measurement: [dx, dy] (raw sensor delta per sample)
//
// The filter smooths noisy gesture input by:
// 1. Predicting the next velocity from the current estimate
// 2. Updating with the actual measurement (dx, dy)
// 3. Outputting a filtered velocity that rejects jitter and outliers
//
// Tuning parameters:
//   processNoise (Q): how much we expect velocity to change between samples
//     Higher = trusts measurements more (more responsive, less smooth)
//     Lower = trusts prediction more (smoother, slower to react)
//   measurementNoise (R): how noisy we expect the sensor to be
//     Higher = trusts prediction more (more filtering)
//     Lower = trusts measurements more (less filtering)
type KalmanFilter2D struct {
	// State estimate
	vx, vy float64

	// Error covariance (diagonal — assume X and Y are independent)
	px, py float64

	// Tuning parameters
	processNoise     float64 // Q: process noise variance
	measurementNoise float64 // R: measurement noise variance

	initialized bool
}

// NewKalmanFilter2D creates a filter tuned for MX Master gesture data.
// The sensor runs at ~143 Hz (7ms between samples), with typical deltas of 5-50
// for normal movement and 100-1000+ for noise spikes.
func NewKalmanFilter2D() *KalmanFilter2D {
	return &KalmanFilter2D{
		processNoise:     8.0,  // Q: velocity changes significantly between samples (mouse is fast)
		measurementNoise: 12.0, // R: moderate noise filtering — responsive but smooth
		px:               50.0, // initial uncertainty
		py:               50.0,
	}
	// Converged Kalman gain: K ≈ Q/(Q+R) = 8/(8+12) = 0.4
	// Trusts measurement 40%, prediction 60% — good balance for gesture detection
}

// Update processes a new raw measurement (dx, dy) and returns the filtered output.
// Call this for every gesture_move event.
func (kf *KalmanFilter2D) Update(dx, dy float64) (filteredDX, filteredDY float64) {
	if !kf.initialized {
		// First measurement — initialize state directly
		// BUT clamp to avoid the massive first-sample noise spike
		kf.vx = clamp(dx, -50, 50)
		kf.vy = clamp(dy, -50, 50)
		kf.initialized = true
		return kf.vx, kf.vy
	}

	// ── PREDICT ──
	// State prediction: velocity stays the same (constant velocity model)
	// vx_predicted = vx (no change — we assume steady motion)
	// Covariance grows by process noise
	kf.px += kf.processNoise
	kf.py += kf.processNoise

	// ── UPDATE (X axis) ──
	// Kalman gain: K = P / (P + R)
	kx := kf.px / (kf.px + kf.measurementNoise)
	// Update state: v = v + K * (measurement - prediction)
	kf.vx = kf.vx + kx*(dx-kf.vx)
	// Update covariance: P = (1 - K) * P
	kf.px = (1 - kx) * kf.px

	// ── UPDATE (Y axis) ──
	ky := kf.py / (kf.py + kf.measurementNoise)
	kf.vy = kf.vy + ky*(dy-kf.vy)
	kf.py = (1 - ky) * kf.py

	return kf.vx, kf.vy
}

// Reset clears the filter state. Call on gesture button release.
func (kf *KalmanFilter2D) Reset() {
	kf.vx = 0
	kf.vy = 0
	kf.px = 100.0
	kf.py = 100.0
	kf.initialized = false
}

func clamp(v, minV, maxV float64) float64 {
	if v < minV {
		return minV
	}
	if v > maxV {
		return maxV
	}
	return v
}
