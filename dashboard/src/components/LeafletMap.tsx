"use client";

import React, { useEffect, useRef, useCallback } from "react";

interface ZoneData {
  key: string;
  name: string;
  bbox: number[];
  center: number[];
  latest_grade: string;
  latest_abi: number;
  overall_abi_change_pct: number;
  cropland_loss_ha: number;
  encroachment_alert: boolean;
}

interface LeafletMapProps {
  zones: ZoneData[];
  selectedZoneKey: string | null;
  onSelectZone: (key: string) => void;
}

function gradeColor(g: string): string {
  if (g === "F") return "#dc2626";
  if (g === "C") return "#f59e0b";
  if (g === "B") return "#38bdf8";
  return "#34d399";
}

export default function LeafletMap({ zones, selectedZoneKey, onSelectZone }: LeafletMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const mapInstanceRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const LRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const markersRef = useRef<Map<string, any>>(new Map());
  const onSelectRef = useRef(onSelectZone);
  onSelectRef.current = onSelectZone;
  const initedRef = useRef(false);

  // ---------- Marker HTML ----------
  const buildMarkerHtml = useCallback((zone: ZoneData, selected: boolean) => {
    const isHighRisk = zone.latest_grade === "F" || zone.latest_grade === "C";
    const color = isHighRisk ? "#dc2626" : "#059669";
    const bright = isHighRisk ? "#f87171" : "#34d399";
    const gc = gradeColor(zone.latest_grade);
    const shortName = zone.name
      .replace(" Agricultural Zone", "")
      .replace(" Agricultural Buffer Zone", "")
      .replace(" Peripheral", "")
      .replace(" Farmland", "");
    const pct = zone.overall_abi_change_pct;
    const pctStr = `${pct > 0 ? "+" : ""}${pct}%`;
    const sz = selected ? 42 : 30;
    const dotSz = selected ? 11 : 8;

    return `
      <div style="position:relative;display:flex;align-items:center;justify-content:center;
                  width:${sz}px;height:${sz}px;cursor:pointer;">
        <div style="position:absolute;width:${sz}px;height:${sz}px;border-radius:50%;
                    border:1.5px solid ${color};animation:fgPulse 2s ease-in-out infinite;
                    opacity:0.35;"></div>
        <div style="position:absolute;width:${Math.round(sz * 0.65)}px;height:${Math.round(sz * 0.65)}px;
                    border-radius:50%;border:1.5px solid ${color};
                    animation:fgPulse 2s ease-in-out infinite 0.45s;opacity:0.6;"></div>
        <div style="width:${dotSz}px;height:${dotSz}px;border-radius:50%;
                    background:${selected ? bright : color};
                    border:${selected ? "2px" : "1.5px"} solid ${bright};
                    box-shadow:0 0 ${selected ? 16 : 9}px ${color};
                    position:relative;z-index:2;">
          <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                      width:3px;height:3px;border-radius:50%;background:#fff;opacity:0.9;"></div>
        </div>
        <div style="position:absolute;left:${Math.round(sz / 2) + 6}px;top:50%;
                    transform:translateY(-50%);white-space:nowrap;
                    background:${selected ? color : "rgba(5,12,20,0.92)"};
                    border:1px solid ${color};border-radius:5px;
                    padding:5px 9px;pointer-events:none;">
          <div style="font-size:8.5px;font-family:monospace;font-weight:800;
                      color:${selected ? "#fff" : bright};letter-spacing:0.06em;
                      text-transform:uppercase;margin-bottom:2px;">${shortName}</div>
          <div style="font-size:7.5px;font-family:monospace;
                      color:${selected ? "rgba(255,255,255,0.75)" : "rgba(148,168,192,0.85)"};">
            <span style="background:${gc}22;color:${gc};border:1px solid ${gc}55;
                         border-radius:3px;padding:0 4px;margin-right:4px;font-weight:700;">
              ${zone.latest_grade}</span>
            ABI&nbsp;${zone.latest_abi.toFixed(2)}&nbsp;·&nbsp;${pctStr}
          </div>
        </div>
      </div>`;
  }, []);

  // ---------- Add / refresh markers ----------
  const addMarkers = useCallback((selKey: string | null) => {
    const map = mapInstanceRef.current;
    const L = LRef.current;
    if (!map || !L) return;

    markersRef.current.forEach(m => m.remove());
    markersRef.current.clear();

    zones.forEach(zone => {
      const [lat, lon] = zone.center;
      const selected = zone.key === selKey;
      const sz = selected ? 42 : 30;

      const icon = L.divIcon({
        className: "",
        html: buildMarkerHtml(zone, selected),
        iconSize: [sz + 180, sz],
        iconAnchor: [Math.round(sz / 2), Math.round(sz / 2)],
      });

      const marker = L.marker([lat, lon], { icon, zIndexOffset: selected ? 1000 : 0 });
      marker.on("click", () => onSelectRef.current(zone.key));
      marker.addTo(map);
      markersRef.current.set(zone.key, marker);
    });
  }, [zones, buildMarkerHtml]);

  // ---------- Init Leaflet once ----------
  useEffect(() => {
    if (initedRef.current || !containerRef.current) return;
    initedRef.current = true;

    import("leaflet").then(L => {
      // If container was unmounted between the import starting and resolving, bail
      if (!containerRef.current) return;

      // If Leaflet already owns this div (HMR / strict mode race), clear it first
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const el = containerRef.current as any;
      if (el._leaflet_id != null) {
        delete el._leaflet_id;
      }

      const initialZone = selectedZoneKey ? zones.find(z => z.key === selectedZoneKey) : null;
      const map = L.map(containerRef.current, {
        center: initialZone ? [initialZone.center[0], initialZone.center[1]] : [20.5, 79.0],
        zoom: initialZone ? 11 : 5,
        zoomControl: false,
        attributionControl: false,
      });

      L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        subdomains: "abcd",
        maxZoom: 19,
      }).addTo(map);

      L.control.attribution({ position: "bottomright", prefix: false })
        .addAttribution('© <a href="https://carto.com" style="color:#34d399">CARTO</a> · <a href="https://openstreetmap.org" style="color:#34d399">OSM</a>')
        .addTo(map);

      L.control.zoom({ position: "topright" }).addTo(map);

      mapInstanceRef.current = map;
      LRef.current = L;

      addMarkers(selectedZoneKey);
    });

    return () => {
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
        LRef.current = null;
        markersRef.current.clear();
        initedRef.current = false;
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ---------- Re-add markers on zone/selection change ----------
  useEffect(() => {
    addMarkers(selectedZoneKey);
  }, [selectedZoneKey, zones, addMarkers]);

  // ---------- Fly to selected zone ----------
  useEffect(() => {
    const map = mapInstanceRef.current;
    if (!map) return;
    if (selectedZoneKey) {
      const zone = zones.find(z => z.key === selectedZoneKey);
      if (zone) map.flyTo([zone.center[0], zone.center[1]], 11, { duration: 1.4, easeLinearity: 0.25 });
    } else {
      map.flyTo([20.5, 79.0], 5, { duration: 1.2 });
    }
  }, [selectedZoneKey, zones]);

  return (
    <div style={{ position: "relative", width: "100%", height: "100%" }}>
      <style>{`
        @keyframes fgPulse {
          0%   { transform: scale(0.8);  opacity: 0.5; }
          50%  { transform: scale(1.2);  opacity: 0.1; }
          100% { transform: scale(0.8);  opacity: 0.5; }
        }
        .leaflet-control-zoom a {
          background: rgba(5,12,20,0.92) !important;
          color: #94a8c0 !important;
          border-color: rgba(51,90,130,0.35) !important;
          font-size: 16px !important;
          width: 28px !important; height: 28px !important;
          line-height: 28px !important;
        }
        .leaflet-control-zoom a:hover {
          background: rgba(5,150,105,0.15) !important;
          color: #34d399 !important;
          border-color: rgba(5,150,105,0.4) !important;
        }
        .leaflet-bar { border: 1px solid rgba(51,90,130,0.35) !important; box-shadow: none !important; }
        .leaflet-control-attribution {
          background: rgba(5,12,20,0.8) !important;
          color: rgba(51,90,130,0.7) !important;
          font-size: 9px !important;
          backdrop-filter: blur(4px);
          border-radius: 4px 0 0 0 !important;
        }
        .leaflet-control-attribution a { color: #34d399 !important; }
        .leaflet-container { background: #050c14 !important; }
        .leaflet-tile-pane { opacity: 0.92; }
      `}</style>

      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

      {/* HUD top */}
      <div style={{
        position: "absolute", top: 52, left: 12, right: 12,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        pointerEvents: "none", zIndex: 500,
      }}>
        <div className="glass-card" style={{ padding: "5px 12px", display: "flex", alignItems: "center", gap: 6 }}>
          <span className="dot-pulse emerald" />
          <span className="section-label" style={{ color: "var(--emerald-400)" }}>Live Satellite View</span>
        </div>
        <div className="glass-card" style={{ padding: "5px 12px" }}>
          <span className="section-label">{zones.length} zones monitored · India</span>
        </div>
      </div>

      {/* Legend */}
      <div style={{
        position: "absolute", bottom: 24, left: 0, right: 0,
        display: "flex", justifyContent: "center",
        pointerEvents: "none", zIndex: 500,
      }}>
        <div className="glass-card" style={{
          padding: "5px 14px", display: "flex", alignItems: "center", gap: 16,
          fontSize: 9, fontFamily: "monospace", letterSpacing: "0.08em",
          textTransform: "uppercase", color: "var(--text-muted)",
        }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#dc2626", display: "inline-block" }} />
            Grade F / C (High Risk)
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#059669", display: "inline-block" }} />
            Grade A / B (Stable)
          </span>
          <span>Scroll to zoom · Drag to pan · Click to audit</span>
        </div>
      </div>
    </div>
  );
}
