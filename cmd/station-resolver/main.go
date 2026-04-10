// station-resolver is a Telegraf execd processor that enriches hostapd
// syslog events with station hostnames and IP addresses from Technitium
// DHCP reservations.
//
// It reads influx line protocol on stdin, adds "<field>=<hostname>" and
// "<ip_field>=<ip>" fields (defaults "station"/"station_ip", configurable
// via STATION_FIELD/STATION_IP_FIELD env vars) to hostapd
// AP-STA-CONNECTED/DISCONNECTED metrics, and writes the result
// to stdout.
//
// MAC→hostname and MAC→IP mappings are fetched from the Technitium DHCP
// API on startup and refreshed periodically.
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
	fieldName       = envOrDefault("STATION_FIELD", "station")
	ipFieldName     = envOrDefault("STATION_IP_FIELD", "station_ip")
)

func envOrDefault(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

// resolver holds the MAC→hostname and MAC→IP mappings and refreshes them periodically.
type resolver struct {
	mu    sync.RWMutex
	names map[string]string // lowercase colon-separated MAC → hostname
	ips   map[string]string // lowercase colon-separated MAC → IP address
}

// scopeResponse is the API response for /api/dhcp/scopes/get.
type scopeResponse struct {
	Status   string `json:"status"`
	Response struct {
		ReservedLeases []struct {
			HardwareAddress string `json:"hardwareAddress"`
			HostName        string `json:"hostName"`
			Address         string `json:"address"`
		} `json:"reservedLeases"`
	} `json:"response"`
}

func (r *resolver) refresh() error {
	url := fmt.Sprintf("%s/api/dhcp/scopes/get?token=%s&name=%s",
		technitiumURL, technitiumToken, dhcpScope)

	client := &http.Client{
		Timeout: 10 * time.Second,
		Transport: &http.Transport{
			TLSClientConfig: &tls.Config{InsecureSkipVerify: false},
		},
	}

	resp, err := client.Get(url)
	if err != nil {
		return fmt.Errorf("technitium API: %w", err)
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return fmt.Errorf("reading response: %w", err)
	}

	var data scopeResponse
	if err := json.Unmarshal(body, &data); err != nil {
		return fmt.Errorf("parsing JSON: %w", err)
	}

	if data.Status != "ok" {
		return fmt.Errorf("API status: %s", data.Status)
	}

	names := make(map[string]string, len(data.Response.ReservedLeases))
	ips := make(map[string]string, len(data.Response.ReservedLeases))
	for _, lease := range data.Response.ReservedLeases {
		mac := strings.ToLower(strings.ReplaceAll(lease.HardwareAddress, "-", ":"))
		host := lease.HostName
		if idx := strings.Index(host, "."); idx > 0 {
			host = host[:idx]
		}
		names[mac] = host
		if lease.Address != "" {
			ips[mac] = lease.Address
		}
	}

	r.mu.Lock()
	r.names = names
	r.ips = ips
	r.mu.Unlock()

	log.Printf("refreshed %d MAC→hostname mappings from Technitium", len(names))
	return nil
}

func (r *resolver) lookup(mac string) (name, ip string) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	lower := strings.ToLower(mac)
	return r.names[lower], r.ips[lower]
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

	name, ip := r.lookup(mac)
	if name == "" {
		return line
	}

	// Build the extra fields to inject
	extra := fmt.Sprintf(",%s=%q", fieldName, name)
	if ip != "" {
		extra += fmt.Sprintf(",%s=%q", ipFieldName, ip)
	}

	// Influx line protocol: measurement,tags fields timestamp
	// The "message" field contains the syslog message.
	// We need to add our fields to the fields section.
	//
	// Find the field set boundary: first space after tags (tags contain no spaces
	// unless escaped, but syslog measurement has no tags with spaces).
	// Strategy: find the LAST space — that separates fields from timestamp.
	// Then insert our fields before the timestamp.
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
		// Insert fields before timestamp
		return line[:lastSpace] + extra + line[lastSpace:]
	}

	// No timestamp — append fields at the end
	return line + extra
}

// metricsHandler serves Prometheus metrics with MAC→hostname mapping.
func metricsHandler(r *resolver) http.HandlerFunc {
	return func(w http.ResponseWriter, req *http.Request) {
		r.mu.RLock()
		defer r.mu.RUnlock()

		w.Header().Set("Content-Type", "text/plain; version=0.0.4")
		fmt.Fprintln(w, "# HELP wifi_station_name MAC to hostname and IP mapping from DHCP reservations")
		fmt.Fprintln(w, "# TYPE wifi_station_name gauge")
		for mac, name := range r.names {
			// MAC in uppercase colon-separated to match Prometheus labels
			upper := strings.ToUpper(mac)
			ip := r.ips[mac]
			fmt.Fprintf(w, "wifi_station_name{mac=%q,station=%q,ip=%q} 1\n", upper, name, ip)
		}
	}
}

var metricsAddr = envOrDefault("METRICS_ADDR", ":9101")

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

	// Serve MAC→hostname mapping as Prometheus metrics
	go func() {
		mux := http.NewServeMux()
		mux.Handle("/metrics", metricsHandler(r))
		log.Printf("serving metrics on %s/metrics", metricsAddr)
		if err := http.ListenAndServe(metricsAddr, mux); err != nil {
			log.Fatalf("metrics server: %v", err)
		}
	}()

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
