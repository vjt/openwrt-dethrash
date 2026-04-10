# OpenWrt SDK package Makefile for wifi-dethrash-collector
# Use with: make package/wifi-dethrash-collector/compile V=s

include $(TOPDIR)/rules.mk

PKG_NAME:=wifi-dethrash-collector
PKG_VERSION:=0.4.0
PKG_RELEASE:=1

include $(INCLUDE_DIR)/package.mk

define Package/wifi-dethrash-collector
  SECTION:=utils
  CATEGORY:=Utilities
  TITLE:=WiFi Dethrash Prometheus Collector
  DEPENDS:=+prometheus-node-exporter-lua +libuci-lua +luci-lib-nixio
  PKGARCH:=all
endef

define Package/wifi-dethrash-collector/description
  Custom prometheus-node-exporter-lua collector that exports WiFi radio
  txpower, channel, 802.11r/k/v config, usteer thresholds, and usteer
  runtime data (hearing map, roam events, channel load).
endef

define Build/Compile
endef

define Package/wifi-dethrash-collector/install
	$(INSTALL_DIR) $(1)/usr/lib/lua/prometheus-collectors
	$(INSTALL_DATA) ./files/usr/lib/lua/prometheus-collectors/wifi_dethrash.lua \
		$(1)/usr/lib/lua/prometheus-collectors/
endef

define Package/wifi-dethrash-collector/postinst
#!/bin/sh
/etc/init.d/prometheus-node-exporter-lua restart 2>/dev/null || true
endef

$(eval $(call BuildPackage,wifi-dethrash-collector))
