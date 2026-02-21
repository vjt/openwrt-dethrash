# OpenWrt Custom Package Feed Server

Design document for a self-hosted opkg package feed that distributes
custom-built `.ipk` packages to OpenWrt APs alongside the official repos.

## Goals

- Host multiple custom `.ipk` packages (Lua collectors, config helpers, etc.)
- Coexist with `owut` firmware upgrades and official OpenWrt feeds
- Rebuild the package index automatically when packages are added
- Run as a Docker container on an internal server

## Architecture

```
┌──────────────┐     opkg update/install      ┌──────────────────┐
│  OpenWrt AP  │ ───────────────────────────>  │  Feed Server     │
│              │                               │  (nginx)         │
│  customfeeds │                               │                  │
│  .conf ──────┤                               │  /feed/all/      │
│              │                               │    *.ipk         │
│  official    │                               │    Packages.gz   │
│  repos ──────┤──> downloads.openwrt.org      └──────────────────┘
└──────────────┘
```

The feed server is a plain HTTP file server. opkg on each AP is
configured with an additional feed pointing at it. Official feeds
remain untouched — `owut` upgrades and standard packages keep working.

## Package lifecycle

1. **Build** — each package repo has a `build-ipk.sh` (or uses the
   OpenWrt SDK for compiled packages). Output is a single `.ipk` file.

2. **Publish** — copy the `.ipk` into the feed server's volume.
   The server regenerates `Packages` and `Packages.gz` index files
   automatically (via inotifywait or a cron/on-demand script).

3. **Install** — on each AP:
   ```
   opkg update
   opkg install wifi-dethrash-collector
   ```

4. **Upgrade** — build a new version, copy to feed, APs pick it up
   on next `opkg update && opkg upgrade`.

## Feed directory layout

```
/feed/
└── all/                          # architecture: "all" for pure Lua/config
    ├── wifi-dethrash-collector_0.1.0-1_all.ipk
    ├── another-package_1.0.0-1_all.ipk
    ├── Packages                  # plain-text index
    └── Packages.gz               # gzipped index
```

If compiled (C) packages are added later, add per-architecture dirs:

```
/feed/
├── all/
├── aarch64_cortex-a53/           # matches target in /etc/opkg/distfeeds.conf
└── mipsel_24kc/
```

## Docker container

**Image**: nginx (alpine) with a reindex script.

**Compose**:
```yaml
services:
  opkg-feed:
    build: .
    ports:
      - "8080:80"
    volumes:
      - ./packages:/feed
```

**Dockerfile**:
- Base: `nginx:alpine`
- Install `bash`, `coreutils` (for `sha256sum`)
- Copy a `reindex.sh` script that generates `Packages`/`Packages.gz`
  from all `.ipk` files in each subdirectory
- Copy nginx config serving `/feed/` as autoindex
- Entrypoint: run `reindex.sh`, then start nginx

**reindex.sh** logic:
- For each subdirectory under `/feed/` (e.g. `all/`, `aarch64_cortex-a53/`):
  - For each `.ipk` file, extract `control.tar.gz`, read `control` metadata
  - Append to `Packages` with `Filename`, `Size`, `SHA256sum` fields
  - Gzip to `Packages.gz`
- Can be triggered manually (`docker exec feed reindex.sh`) or on a
  schedule/inotify watch

## AP configuration

One-time setup per AP:

```bash
echo "src/gz custom http://<server>:8080/all" >> /etc/opkg/customfeeds.conf
```

This survives `owut` sysupgrades if `/etc/opkg/customfeeds.conf` is
listed in `/etc/sysupgrade.conf` (it is by default on OpenWrt 24.10).

To reinstall custom packages after a firmware upgrade:

```bash
opkg update
opkg install wifi-dethrash-collector  # re-adds the collector
```

Or preserve the package list before upgrading:

```bash
opkg list-installed | grep -v "^base-" > /etc/backup/custom-packages.txt
# after sysupgrade:
opkg update
xargs opkg install < /etc/backup/custom-packages.txt
```

## owut compatibility

`owut` and custom feeds are independent:

| Concern | owut | Custom feed |
|---------|------|-------------|
| What it manages | Firmware image (kernel + base) | Individual packages |
| Update mechanism | Sysupgrade (full flash) | `opkg upgrade` (file-level) |
| Config preserved? | Via sysupgrade.conf | Packages must be reinstalled |
| Feed URL | Built into firmware | `/etc/opkg/customfeeds.conf` |

No conflicts. `owut` never touches custom feed config or packages.

## Future: compiled packages

For packages with C code (e.g. custom hostapd patches), the build
step requires the OpenWrt SDK matching the target architecture:

```bash
# Download SDK for your target
wget https://downloads.openwrt.org/releases/24.10.0/targets/mediatek/filogic/openwrt-sdk-*.tar.xz

# Place package Makefile in SDK, build
make package/my-package/compile V=s

# Output .ipk lands in bin/packages/<arch>/
```

The feed server doesn't care how the `.ipk` was built — it just
serves whatever is in the volume. The SDK step can run on a CI
server or in a dedicated builder container.
