// pipe-test — Interactive test client for MasterMice service IPC.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"strconv"
	"strings"
	"time"

	winio "github.com/Microsoft/go-winio"
)

const pipeName = `\\.\pipe\MasterMice`

var (
	nextID = 1
	reader *bufio.Reader
)

func main() {
	fmt.Println("[pipe-test] Connecting to MasterMice service...")

	timeout := 5 * time.Second
	conn, err := winio.DialPipe(pipeName, &timeout)
	if err != nil {
		fmt.Printf("[ERROR] Cannot connect to %s: %v\n", pipeName, err)
		fmt.Println("        Is mastermice-svc.exe running?")
		os.Exit(1)
	}
	defer conn.Close()

	// Single reader for the entire session
	reader = bufio.NewReader(conn)

	fmt.Println("[OK] Connected")

	if len(os.Args) > 1 {
		cmd, params := parseInput(strings.Join(os.Args[1:], " "))
		resp := sendRequest(conn, cmd, params)
		out, _ := json.MarshalIndent(resp, "", "  ")
		fmt.Println(string(out))
		return
	}

	fmt.Println("[COMMANDS] health | status | battery | dpi | set_dpi <val> | smartshift | set_ss <val> | hires | smooth | quit")
	scanner := bufio.NewScanner(os.Stdin)
	for {
		fmt.Print("> ")
		if !scanner.Scan() {
			break
		}
		line := strings.TrimSpace(scanner.Text())
		if line == "" {
			continue
		}
		if line == "quit" || line == "exit" || line == "q" {
			break
		}
		cmd, params := parseInput(line)
		resp := sendRequest(conn, cmd, params)
		printResponse(resp)
	}
}

func parseInput(line string) (string, map[string]interface{}) {
	parts := strings.Fields(line)
	cmd := strings.ToLower(parts[0])
	var params map[string]interface{}

	switch cmd {
	case "set_dpi":
		if len(parts) > 1 {
			v, _ := strconv.Atoi(parts[1])
			params = map[string]interface{}{"value": v}
		}
	case "set_ss":
		cmd = "set_smartshift"
		if len(parts) > 1 {
			if parts[1] == "off" {
				params = map[string]interface{}{"threshold": 10, "enabled": false}
			} else {
				v, _ := strconv.Atoi(parts[1])
				params = map[string]interface{}{"threshold": v, "enabled": true}
			}
		}
	case "battery", "batt":
		cmd = "read_battery"
	case "dpi":
		cmd = "read_dpi"
	case "smartshift", "ss":
		cmd = "get_smartshift"
	case "hires":
		cmd = "get_hires_wheel"
	case "hires_on":
		cmd = "set_hires_wheel"
		params = map[string]interface{}{"hires": true}
	case "hires_off":
		cmd = "set_hires_wheel"
		params = map[string]interface{}{"hires": false}
	case "smooth":
		cmd = "get_smooth_scroll"
	case "smooth_on":
		cmd = "set_smooth_scroll"
		params = map[string]interface{}{"enabled": true}
	case "smooth_off":
		cmd = "set_smooth_scroll"
		params = map[string]interface{}{"enabled": false}
	case "status":
		cmd = "get_status"
	case "caps":
		cmd = "get_capabilities"
	}

	return cmd, params
}

func sendRequest(conn net.Conn, cmd string, params map[string]interface{}) map[string]interface{} {
	req := map[string]interface{}{
		"id":  nextID,
		"cmd": cmd,
	}
	if params != nil {
		req["params"] = params
	}
	nextID++

	data, _ := json.Marshal(req)
	data = append(data, '\n')

	_, err := conn.Write(data)
	if err != nil {
		fmt.Printf("[ERROR] Write failed: %v\n", err)
		return nil
	}

	// Read response using the shared reader
	line, err := reader.ReadBytes('\n')
	if err != nil {
		fmt.Printf("[ERROR] Read failed: %v\n", err)
		return nil
	}

	var resp map[string]interface{}
	json.Unmarshal(line, &resp)
	return resp
}

func printResponse(resp map[string]interface{}) {
	if resp == nil {
		fmt.Println("  [no response]")
		return
	}

	ok, _ := resp["ok"].(bool)
	if !ok {
		errMsg, _ := resp["error"].(string)
		fmt.Printf("  ERROR: %s\n", errMsg)
		return
	}

	data, _ := resp["data"].(map[string]interface{})
	if data == nil || len(data) == 0 {
		fmt.Println("  OK")
		return
	}

	for k, v := range data {
		fmt.Printf("  %s: %v\n", k, v)
	}
}
