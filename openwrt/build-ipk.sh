#!/usr/bin/env bash
# Build an .ipk package for wifi-dethrash-collector without the OpenWrt SDK.
# Usage: ./build-ipk.sh [output_dir]
#
# The .ipk is a standard ar archive containing debian-binary, control.tar.gz,
# and data.tar.gz — the same format opkg expects.

set -euo pipefail

PKG_NAME="wifi-dethrash-collector"
PKG_VERSION="0.1.0"
PKG_RELEASE="1"
PKG_ARCH="all"
PKG_DEPENDS="prometheus-node-exporter-lua"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUTPUT_DIR="${1:-${SCRIPT_DIR}/dist}"
WORK_DIR=$(mktemp -d)

cleanup() { rm -rf "$WORK_DIR"; }
trap cleanup EXIT

IPK_NAME="${PKG_NAME}_${PKG_VERSION}-${PKG_RELEASE}_${PKG_ARCH}.ipk"

# -- data.tar.gz: the actual files to install --
DATA_DIR="${WORK_DIR}/data"
mkdir -p "${DATA_DIR}/usr/lib/lua/prometheus-collectors"
cp "${SCRIPT_DIR}/usr/lib/lua/prometheus-collectors/wifi_dethrash.lua" \
   "${DATA_DIR}/usr/lib/lua/prometheus-collectors/"

tar czf "${WORK_DIR}/data.tar.gz" -C "${DATA_DIR}" .

# -- control.tar.gz: package metadata --
CONTROL_DIR="${WORK_DIR}/control"
mkdir -p "${CONTROL_DIR}"

cat > "${CONTROL_DIR}/control" <<EOF
Package: ${PKG_NAME}
Version: ${PKG_VERSION}-${PKG_RELEASE}
Depends: ${PKG_DEPENDS}
Architecture: ${PKG_ARCH}
Maintainer: wifi-dethrash
Section: utils
Description: WiFi Dethrash Prometheus Collector
 Custom prometheus-node-exporter-lua collector that exports WiFi radio
 txpower, channel, 802.11r/k/v config, and usteer thresholds.
EOF

cat > "${CONTROL_DIR}/postinst" <<'EOF'
#!/bin/sh
/etc/init.d/prometheus-node-exporter-lua restart 2>/dev/null || true
EOF
chmod 755 "${CONTROL_DIR}/postinst"

tar czf "${WORK_DIR}/control.tar.gz" -C "${CONTROL_DIR}" .

# -- debian-binary --
echo "2.0" > "${WORK_DIR}/debian-binary"

# -- assemble the .ipk (ar archive) --
mkdir -p "${OUTPUT_DIR}"
(
  cd "${WORK_DIR}"
  ar cr "${OUTPUT_DIR}/${IPK_NAME}" debian-binary control.tar.gz data.tar.gz
)

echo "Built: ${OUTPUT_DIR}/${IPK_NAME}"

# -- generate Packages index if requested --
if [ "${GENERATE_INDEX:-1}" = "1" ]; then
  IPK_SIZE=$(wc -c < "${OUTPUT_DIR}/${IPK_NAME}" | tr -d ' ')
  IPK_SHA256=$(shasum -a 256 "${OUTPUT_DIR}/${IPK_NAME}" | cut -d' ' -f1)

  cat > "${OUTPUT_DIR}/Packages" <<EOF
Package: ${PKG_NAME}
Version: ${PKG_VERSION}-${PKG_RELEASE}
Depends: ${PKG_DEPENDS}
Architecture: ${PKG_ARCH}
Filename: ${IPK_NAME}
Size: ${IPK_SIZE}
SHA256sum: ${IPK_SHA256}
Description: WiFi Dethrash Prometheus Collector
EOF

  gzip -kf "${OUTPUT_DIR}/Packages"
  echo "Index: ${OUTPUT_DIR}/Packages{,.gz}"
fi
