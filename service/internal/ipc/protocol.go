// Package ipc implements named pipe IPC for the MasterMice service.
// Protocol: JSON-lines over \\.\pipe\MasterMice
package ipc

import "encoding/json"

const PipeName = `\\.\pipe\MasterMice`

// Request is a command from the Python client to the Go service.
type Request struct {
	ID     int                    `json:"id"`
	Cmd    string                 `json:"cmd"`
	Params map[string]interface{} `json:"params,omitempty"`
}

// Response is the service's reply to a Request.
type Response struct {
	ID   int                    `json:"id"`
	OK   bool                   `json:"ok"`
	Data map[string]interface{} `json:"data,omitempty"`
	Err  string                 `json:"error,omitempty"`
}

// Event is an unsolicited notification from the service to connected clients.
type Event struct {
	Event string                 `json:"event"`
	Data  map[string]interface{} `json:"data,omitempty"`
}

// Encode serializes any message to a JSON line (with trailing newline).
func Encode(v interface{}) ([]byte, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return nil, err
	}
	return append(b, '\n'), nil
}

// DecodeRequest parses a JSON line into a Request.
func DecodeRequest(line []byte) (*Request, error) {
	var req Request
	if err := json.Unmarshal(line, &req); err != nil {
		return nil, err
	}
	return &req, nil
}

// helper to get a string param with default
func ParamString(params map[string]interface{}, key, def string) string {
	if v, ok := params[key]; ok {
		if s, ok := v.(string); ok {
			return s
		}
	}
	return def
}

// helper to get an int param with default (JSON numbers are float64)
func ParamInt(params map[string]interface{}, key string, def int) int {
	if v, ok := params[key]; ok {
		switch n := v.(type) {
		case float64:
			return int(n)
		case int:
			return n
		}
	}
	return def
}

// helper to get a bool param with default
func ParamBool(params map[string]interface{}, key string, def bool) bool {
	if v, ok := params[key]; ok {
		if b, ok := v.(bool); ok {
			return b
		}
	}
	return def
}
