-- wifi_dethrash.lua — prometheus-node-exporter-lua collector
-- Exports txpower, channel, 802.11r/k/v config, and usteer thresholds.
-- Deploy to /usr/lib/lua/prometheus-collectors/ on each OpenWrt AP.

local ubus = require "ubus"
local iwinfo = require "iwinfo"

local function scrape()
  -- Phase 1: Radio metrics from iwinfo
  local metric_txpower = metric("wifi_radio_txpower_dbm", "gauge")
  local metric_txpower_offset = metric("wifi_radio_txpower_offset_dbm", "gauge")
  local metric_channel = metric("wifi_radio_channel", "gauge")
  local metric_frequency = metric("wifi_radio_frequency_mhz", "gauge")

  local u = ubus.connect()
  if not u then return end

  local status = u:call("network.wireless", "status", {})
  u:close()

  if not status then return end

  -- Map device -> list of {ifname, ssid} for joining with UCI later
  local iface_by_device = {}

  for dev, dev_table in pairs(status) do
    iface_by_device[dev] = {}
    for _, intf in ipairs(dev_table["interfaces"] or {}) do
      local ifname = intf["ifname"]
      if ifname then
        local iw = iwinfo[iwinfo.type(ifname)]
        if iw then
          local ssid = iw.ssid(ifname) or ""
          local labels = {device = dev, ifname = ifname, ssid = ssid}

          table.insert(iface_by_device[dev], {ifname = ifname, ssid = ssid})

          local txp = iw.txpower(ifname)
          if txp then metric_txpower(labels, txp) end

          local txp_off = iw.txpower_offset(ifname)
          if txp_off then metric_txpower_offset(labels, txp_off) end

          local ch = iw.channel(ifname)
          if ch then metric_channel(labels, ch) end

          local freq = iw.frequency(ifname)
          if freq then metric_frequency(labels, freq) end
        end
      end
    end
  end

  -- Phase 2: UCI wireless config
  local ok, ucic = pcall(function()
    local uci = require "uci"
    return uci.cursor()
  end)

  if ok and ucic then
    local metric_configured_txpower = metric("wifi_radio_configured_txpower", "gauge")
    local metric_80211r = metric("wifi_iface_ieee80211r_enabled", "gauge")
    local metric_80211k = metric("wifi_iface_ieee80211k_enabled", "gauge")
    local metric_80211v = metric("wifi_iface_ieee80211v_enabled", "gauge")

    ucic:foreach("wireless", "wifi-device", function(s)
      local txp = tonumber(s.txpower)
      if txp then
        metric_configured_txpower({device = s[".name"]}, txp)
      end
    end)

    ucic:foreach("wireless", "wifi-iface", function(s)
      local dev = s.device or ""
      local ssid = s.ssid or ""

      -- Find runtime ifname from ubus data for this device+ssid
      local ifname = ""
      local ifaces = iface_by_device[dev]
      if ifaces then
        for _, iface in ipairs(ifaces) do
          if iface.ssid == ssid then
            ifname = iface.ifname
            break
          end
        end
      end

      local labels = {device = dev, ifname = ifname, ssid = ssid}
      metric_80211r(labels, (s.ieee80211r == "1") and 1 or 0)
      metric_80211k(labels, (s.ieee80211k == "1") and 1 or 0)

      local v_enabled = (s.ieee80211v == "1") or (s.bss_transition == "1")
      metric_80211v(labels, v_enabled and 1 or 0)
    end)
  end

  -- Phase 3: UCI usteer config
  pcall(function()
    local metric_min_connect_snr = metric("wifi_usteer_min_connect_snr", "gauge")
    local metric_min_snr = metric("wifi_usteer_min_snr", "gauge")
    local metric_roam_scan_snr = metric("wifi_usteer_roam_scan_snr", "gauge")
    local metric_roam_trigger_snr = metric("wifi_usteer_roam_trigger_snr", "gauge")
    local metric_signal_diff = metric("wifi_usteer_signal_diff_threshold", "gauge")
    local metric_load_kick_enabled = metric("wifi_usteer_load_kick_enabled", "gauge")
    local metric_load_kick_threshold = metric("wifi_usteer_load_kick_threshold", "gauge")
    local metric_band_steer_snr = metric("wifi_usteer_band_steering_min_snr", "gauge")

    local opts = {
      {metric_min_connect_snr, "min_connect_snr"},
      {metric_min_snr, "min_snr"},
      {metric_roam_scan_snr, "roam_scan_snr"},
      {metric_roam_trigger_snr, "roam_trigger_snr"},
      {metric_signal_diff, "signal_diff_threshold"},
      {metric_load_kick_enabled, "load_kick_enabled"},
      {metric_load_kick_threshold, "load_kick_threshold"},
      {metric_band_steer_snr, "band_steering_min_snr"},
    }

    for _, pair in ipairs(opts) do
      local val = tonumber(ucic:get("usteer", "@usteer[0]", pair[2]))
      if val then
        pair[1]({}, val)
      end
    end
  end)
end

return {scrape = scrape}
