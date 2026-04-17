-- wifi_dethrash.lua — prometheus-node-exporter-lua collector
-- Exports txpower, channel, 802.11r/k/v config, and usteer thresholds.
-- Deploy to /usr/lib/lua/prometheus-collectors/ on each OpenWrt AP.

local ubus = require "ubus"
local iwinfo = require "iwinfo"
local nixio = require "nixio"

-- Module-level reverse DNS cache: successful lookups cached permanently,
-- failures not cached so they're retried on next scrape.
local _rdns_cache = {}
local function resolve_ip(ip)
  if _rdns_cache[ip] then return _rdns_cache[ip] end
  local ok, name = pcall(nixio.getnameinfo, ip)
  if ok and name then
    _rdns_cache[ip] = name:match("^([%w%-]+)") or ip  -- strip domain
    return _rdns_cache[ip]
  end
  return ip  -- DNS failed; don't cache, retry next scrape
end

local function scrape()
  -- Phase 1: Radio metrics from iwinfo
  local metric_txpower = metric("wifi_radio_txpower_dbm", "gauge")
  local metric_txpower_offset = metric("wifi_radio_txpower_offset_dbm", "gauge")
  local metric_channel = metric("wifi_radio_channel", "gauge")
  local metric_frequency = metric("wifi_radio_frequency_mhz", "gauge")

  local u = ubus.connect()
  if not u then return end

  local status = u:call("network.wireless", "status", {})

  -- Map device -> list of {ifname, ssid} for joining with UCI later
  local iface_by_device = {}

  if status then
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
  end

  -- Phase 2: UCI wireless config
  local ucic  -- shared with Phase 4
  local ok_uci, cursor = pcall(function()
    local uci = require "uci"
    return uci.cursor()
  end)
  if ok_uci and cursor then ucic = cursor end

  if ucic then
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

  -- Phase 3: usteer runtime data (hearing map, roam events, load)
  pcall(function()
    local f = io.open("/proc/sys/kernel/hostname")
    local hostname = f and f:read("*l") or "unknown"
    if f then f:close() end

    -- Collect local + remote info, build node→{ssid, ap_label} map
    local node_map = {}  -- node_key → {ssid, ap_label}
    local local_info = u:call("usteer", "local_info", {})
    if local_info then
      for node_key, info in pairs(local_info) do
        local ssid = info.ssid or ""
        node_map[node_key] = {ssid = ssid, ap = hostname .. "/" .. ssid}
      end
    end

    -- Remote info used only for node_map (SSID resolution in hearing map),
    -- NOT for exporting metrics — each AP exports its own local_info.
    local remote_info = u:call("usteer", "remote_info", {})
    if remote_info then
      for node_key, info in pairs(remote_info) do
        local ssid = info.ssid or ""
        local ip = node_key:match("^(.+)#") or node_key
        node_map[node_key] = {ssid = ssid, ap = resolve_ip(ip) .. "/" .. ssid}
      end
    end

    -- Export roam events, load, clients from LOCAL info only
    local metric_roam_source = metric("wifi_usteer_roam_events_source", "gauge")
    local metric_roam_target = metric("wifi_usteer_roam_events_target", "gauge")
    local metric_load = metric("wifi_usteer_load", "gauge")
    local metric_assoc = metric("wifi_usteer_associated_clients", "gauge")

    if local_info then
      for node_key, info in pairs(local_info) do
        local nm = node_map[node_key] or {ap = node_key}
        local labels = {ap = nm.ap}
        local re = info.roam_events or {}
        metric_roam_source(labels, re.source or 0)
        metric_roam_target(labels, re.target or 0)
        metric_load(labels, info.load or 0)
        metric_assoc(labels, info.n_assoc or 0)
      end
    end

    -- Hearing map: signal per MAC per AP (uses node_map for labels)
    local clients = u:call("usteer", "get_clients", {})
    if clients then
      local metric_hearing = metric("wifi_usteer_hearing_signal_dbm", "gauge")
      local metric_connected = metric("wifi_usteer_hearing_connected", "gauge")

      for mac, nodes in pairs(clients) do
        for node_key, info in pairs(nodes) do
          local nm = node_map[node_key] or {ap = node_key}
          local labels = {mac = mac:upper(), ap = nm.ap}
          metric_hearing(labels, info.signal or 0)
          metric_connected(labels, info.connected and 1 or 0)
        end
      end
    end
  end)

  -- Phase 4: UCI usteer config
  if ucic then
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

  u:close()
end

return {scrape = scrape}
