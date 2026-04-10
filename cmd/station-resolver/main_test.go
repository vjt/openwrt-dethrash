package main

import (
	"os"
	"testing"
)

func TestExtractMAC(t *testing.T) {
	tests := []struct {
		name string
		msg  string
		want string
	}{
		{
			name: "connected with auth",
			msg:  `phy1-ap0: AP-STA-CONNECTED 6c:3a:ff:3d:ea:f0 auth_alg=ft`,
			want: "6c:3a:ff:3d:ea:f0",
		},
		{
			name: "disconnected",
			msg:  `phy1-ap0: AP-STA-DISCONNECTED 6c:3a:ff:3d:ea:f0`,
			want: "6c:3a:ff:3d:ea:f0",
		},
		{
			name: "uppercase MAC",
			msg:  `phy1-ap0: AP-STA-CONNECTED E0:85:4D:B3:BC:C0 auth_alg=open`,
			want: "E0:85:4D:B3:BC:C0",
		},
		{
			name: "no match",
			msg:  `some other syslog message`,
			want: "",
		},
		{
			name: "poll ok ignored",
			msg:  `phy1-ap0: AP-STA-POLL-OK 6c:3a:ff:3d:ea:f0`,
			want: "",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := extractMAC(tt.msg)
			if got != tt.want {
				t.Errorf("extractMAC(%q) = %q, want %q", tt.msg, got, tt.want)
			}
		})
	}
}

func TestProcessLine(t *testing.T) {
	r := &resolver{
		names: map[string]string{
			"6c:3a:ff:3d:ea:f0": "sara-iphone",
			"e0:85:4d:b3:bc:c0": "tv",
		},
		ips: map[string]string{
			"6c:3a:ff:3d:ea:f0": "192.168.42.100",
			"e0:85:4d:b3:bc:c0": "192.168.42.101",
		},
	}

	tests := []struct {
		name string
		line string
		want string
	}{
		{
			name: "enriches connected event with hostname and IP",
			line: `syslog,appname=hostapd,hostname=golem message="phy1-ap0: AP-STA-CONNECTED 6c:3a:ff:3d:ea:f0 auth_alg=ft" 1700000000000000000`,
			want: `syslog,appname=hostapd,hostname=golem message="phy1-ap0: AP-STA-CONNECTED 6c:3a:ff:3d:ea:f0 auth_alg=ft",station="sara-iphone",station_ip="192.168.42.100" 1700000000000000000`,
		},
		{
			name: "enriches uppercase MAC with hostname and IP",
			line: `syslog,appname=hostapd,hostname=albert message="phy1-ap0: AP-STA-CONNECTED E0:85:4D:B3:BC:C0 auth_alg=open" 1700000000000000000`,
			want: `syslog,appname=hostapd,hostname=albert message="phy1-ap0: AP-STA-CONNECTED E0:85:4D:B3:BC:C0 auth_alg=open",station="tv",station_ip="192.168.42.101" 1700000000000000000`,
		},
		{
			name: "passes through unknown MAC",
			line: `syslog,appname=hostapd,hostname=golem message="phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:ff auth_alg=open" 1700000000000000000`,
			want: `syslog,appname=hostapd,hostname=golem message="phy1-ap0: AP-STA-CONNECTED aa:bb:cc:dd:ee:ff auth_alg=open" 1700000000000000000`,
		},
		{
			name: "passes through non-hostapd",
			line: `cpu,host=server usage=42.0 1700000000000000000`,
			want: `cpu,host=server usage=42.0 1700000000000000000`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := processLine(tt.line, r)
			if got != tt.want {
				t.Errorf("processLine() =\n  %q\nwant\n  %q", got, tt.want)
			}
		})
	}
}

func TestProcessLineNoIP(t *testing.T) {
	// Station with hostname but no IP — should only emit hostname field
	r := &resolver{
		names: map[string]string{
			"6c:3a:ff:3d:ea:f0": "sara-iphone",
		},
		ips: map[string]string{},
	}

	line := `syslog,appname=hostapd,hostname=golem message="phy1-ap0: AP-STA-CONNECTED 6c:3a:ff:3d:ea:f0 auth_alg=ft" 1700000000000000000`
	got := processLine(line, r)
	want := `syslog,appname=hostapd,hostname=golem message="phy1-ap0: AP-STA-CONNECTED 6c:3a:ff:3d:ea:f0 auth_alg=ft",station="sara-iphone" 1700000000000000000`
	if got != want {
		t.Errorf("processLine() no IP:\n  got  %q\n  want %q", got, want)
	}
}

func TestStationFieldOverride(t *testing.T) {
	r := &resolver{
		names: map[string]string{
			"6c:3a:ff:3d:ea:f0": "sara-iphone",
		},
		ips: map[string]string{
			"6c:3a:ff:3d:ea:f0": "192.168.42.100",
		},
	}

	line := `syslog,appname=hostapd,hostname=golem message="phy1-ap0: AP-STA-CONNECTED 6c:3a:ff:3d:ea:f0 auth_alg=ft" 1700000000000000000`

	// Default: fields are "station" and "station_ip"
	fieldName = "station"
	ipFieldName = "station_ip"
	got := processLine(line, r)
	want := `syslog,appname=hostapd,hostname=golem message="phy1-ap0: AP-STA-CONNECTED 6c:3a:ff:3d:ea:f0 auth_alg=ft",station="sara-iphone",station_ip="192.168.42.100" 1700000000000000000`
	if got != want {
		t.Errorf("default fieldNames:\n  got  %q\n  want %q", got, want)
	}

	// Override both fields
	os.Setenv("STATION_FIELD", "client_host")
	os.Setenv("STATION_IP_FIELD", "client_ip")
	fieldName = envOrDefault("STATION_FIELD", "station")
	ipFieldName = envOrDefault("STATION_IP_FIELD", "station_ip")
	got = processLine(line, r)
	want = `syslog,appname=hostapd,hostname=golem message="phy1-ap0: AP-STA-CONNECTED 6c:3a:ff:3d:ea:f0 auth_alg=ft",client_host="sara-iphone",client_ip="192.168.42.100" 1700000000000000000`
	if got != want {
		t.Errorf("STATION_FIELD=client_host, STATION_IP_FIELD=client_ip:\n  got  %q\n  want %q", got, want)
	}

	// Cleanup
	os.Unsetenv("STATION_FIELD")
	os.Unsetenv("STATION_IP_FIELD")
	fieldName = "station"
	ipFieldName = "station_ip"
}
