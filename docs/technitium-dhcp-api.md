# Technitium DHCP API Reference

Station-resolver queries reserved leases from the Technitium DNS Server
DHCP API to build MAC→hostname and MAC→IP mappings.

## Endpoint

```
GET /api/dhcp/scopes/get?token=<token>&name=<scope>
```

## Reserved Lease Fields

```json
{
  "status": "ok",
  "response": {
    "reservedLeases": [
      {
        "hardwareAddress": "AA-BB-CC-DD-EE-FF",
        "hostName": "device.local",
        "address": "192.168.42.100",
        "comments": "optional"
      }
    ]
  }
}
```

| Field | Type | Notes |
|-------|------|-------|
| `hardwareAddress` | string | MAC, dash-separated. Station-resolver normalizes to lowercase colon-separated. |
| `hostName` | string | FQDN. Station-resolver strips domain (first `.` onwards). |
| `address` | string | IPv4 address of the reservation. |
| `comments` | string | Not used by station-resolver. |

## Design Decisions

- **Reserved leases only** — station-resolver never queries dynamic/active
  leases. Unknown MACs are intentionally left unresolved as a security
  signal (unknown device on the network).
- Mapping refreshed every `REFRESH_INTERVAL` (default 1m).

Source: [`WebServiceDhcpApi.cs`](https://github.com/TechnitiumSoftware/DnsServer/blob/master/DnsServerCore/WebServiceDhcpApi.cs)
in the Technitium DNS Server repo.
