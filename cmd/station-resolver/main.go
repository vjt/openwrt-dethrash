// station-resolver is a Telegraf execd processor that enriches hostapd
// syslog events with station hostnames from Technitium DHCP reservations.
//
// It reads influx line protocol on stdin, adds a "station=<hostname>" field
// to hostapd AP-STA-CONNECTED/DISCONNECTED metrics, and writes the result
// to stdout.
//
// MAC→hostname mapping is fetched from the Technitium DHCP API on startup
// and refreshed periodically.
package main

import (
	"bufio"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"
)

// Config from environment variables.
var (
	technitiumURL   = envOrDefault("TECHNITIUM_URL", "https://ns1.bad.ass")
	technitiumToken = envOrDefault("TECHNITIUM_TOKEN", "")
	dhcpScope       = envOrDefault("DHCP_SCOPE", "Default")
	refreshInterval = envOrDefault("REFRESH_INTERVAL", "1m")
)

func envOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// resolver holds the MAC→hostname mapping and refreshes it periodically.
type resolver struct {
	mu    sync.RWMutex
	names map[string]string // lowercase colon-separated MAC → hostname
}

// lease represents a DHCP lease entry from Technitium.
type lease struct {
	HardwareAddress string `json:"hardwareAddress"`
	HostName        string `json:"hostName"`
	Type            string `json:"type"` // "Reserved" or "Dynamic"
}

// scopeResponse is the API response for /api/dhcp/scopes/get (reserved leases).
type scopeResponse struct {
	Status   string `json:"status"`
	Response struct {
		ReservedLeases []lease `json:"reservedLeases"`
	} `json:"response"`
}

// leasesResponse is the API response for /api/dhcp/leases/list (active leases).
type leasesResponse struct {
	Status   string `json:"status"`
	Response struct {
		Leases []lease `json:"leases"`
	} `json:"response"`
}

func (r *resolver) apiGet(path string, result any) error {
	url := fmt.Sprintf("%s%s?token=%s&name=%s", technitiumURL, path, technitiumToken, dhcpScope)

	client := &http.Client{
		Timeout: 10 * time.Second,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: false},
		},
	}

	resp, err := client.Get(url)
	if err != nil {
		return fmt.Errorf("technitium API %s: %w", path, err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("reading response: %w", err)
	}

	return json.Unmarshal(body, result)
}

func normalizeLease(l lease) (mac, host string) {
	mac = strings.ToLower(strings.ReplaceAll(l.HardwareAddress, "-", ":"))
	host = l.HostName
	if idx := strings.Index(host, "."); idx > 0 {
		host = host[:idx]
	}
	return
}

func (r *resolver) refresh() error {
	// 1. Reserved leases (static reservations — authoritative names)
	var scope scopeResponse
	if err := r.apiGet("/api/dhcp/scopes/get", &scope); err != nil {
		return err
	}
	if scope.Status != "ok" {
		return fmt.Errorf("scopes API status: %s", scope.Status)
	}

	// 2. Active leases (dynamic — guests, new devices)
	var active leasesResponse
	if err := r.apiGet("/api/dhcp/leases/list", &active); err != nil {
		log.Printf("warning: could not fetch active leases: %v", err)
		// Non-fatal — reserved leases are enough
	}

	// Dynamic leases first, then reserved override (reserved wins)
	names := make(map[string]string)
	if active.Status == "ok" {
		for _, l := range active.Response.Leases {
			mac, host := normalizeLease(l)
			if host != "" {
				names[mac] = host
			}
		}
	}
	for _, l := range scope.Response.ReservedLeases {
		mac, host := normalizeLease(l)
		if host != "" {
			names[mac] = host
		}
		names[mac] = host
	}

	r.mu.Lock()
	r.names = names
	r.mu.Unlock()

	log.Printf("refreshed %d MAC→hostname mappings from Technitium", len(names))
	return nil
}

func (r *resolver) lookup(mac string) string {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return r.names[strings.ToLower(mac)]
}

func (r *resolver) runRefreshLoop(interval time.Duration) {
	for {
		time.Sleep(interval)
		if err := r.refresh(); err != nil {
			log.Printf("refresh error: %v", err)
		}
	}
}


// extractMAC finds the 17-char MAC address after AP-STA-CONNECTED or
// AP-STA-DISCONNECTED in a syslog message field.
func extractMAC(msg string) string {
	for _, marker := range []string{"AP-STA-CONNECTED ", "AP-STA-DISCONNECTED "} {
		idx := strings.Index(msg, marker)
		if idx < 0 {
			continue
		}
		start := idx + len(marker)
		if start+17 > len(msg) {
			continue
		}
		mac := msg[start : start+17]
		// Validate it looks like a MAC
		if len(mac) == 17 && mac[2] == ':' && mac[5] == ':' {
			return mac
		}
	}
	return ""
}

// processLine reads an influx line protocol line, enriches hostapd metrics,
// and writes the result.
func processLine(line string, r *resolver) string {
	// Quick filter: only process lines containing AP-STA-
	if !strings.Contains(line, "AP-STA-") {
		return line
	}

	mac := extractMAC(line)
	if mac == "" {
		return line
	}

	name := r.lookup(mac)
	if name == "" {
		return line
	}

	// Influx line protocol: measurement,tags fields timestamp
	// The "message" field contains the syslog message.
	// We need to add station="hostname" to the fields section.
	//
	// Find the field set boundary: first space after tags (tags contain no spaces
	// unless escaped, but syslog measurement has no tags with spaces).
	// Strategy: find the LAST space — that separates fields from timestamp.
	// Then insert our field before the timestamp.
	lastSpace := strings.LastIndex(line, " ")
	if lastSpace <= 0 {
		return line
	}

	// Check if what's after the last space is a timestamp (all digits)
	tail := line[lastSpace+1:]
	isTimestamp := true
	for _, c := range tail {
		if c < '0' || c > '9' {
			isTimestamp = false
			break
		}
	}

	if isTimestamp {
		// Insert station field before timestamp
		return line[:lastSpace] + fmt.Sprintf(",station=%q", name) + line[lastSpace:]
	}

	// No timestamp — append field at the end
	return line + fmt.Sprintf(",station=%q", name)
}

func main() {
	if technitiumToken == "" {
		log.Fatal("TECHNITIUM_TOKEN environment variable is required")
	}

	interval, err := time.ParseDuration(refreshInterval)
	if err != nil {
		log.Fatalf("invalid REFRESH_INTERVAL: %v", err)
	}

	r := &resolver{}
	if err := r.refresh(); err != nil {
		log.Fatalf("initial refresh failed: %v", err)
	}

	go r.runRefreshLoop(interval)

	scanner := bufio.NewScanner(os.Stdin)
	// Increase buffer for long lines
	scanner.Buffer(make([]byte, 0, 256*1024), 256*1024)

	for scanner.Scan() {
		line := scanner.Text()
		fmt.Println(processLine(line, r))
	}

	if err := scanner.Err(); err != nil {
		log.Fatalf("stdin read error: %v", err)
	}
}
