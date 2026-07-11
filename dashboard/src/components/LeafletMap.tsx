"use client";

import React, { useEffect, useRef, useCallback, useState } from "react";
import type { Map as LMap, Marker } from "leaflet";

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
  inputMode: "named" | "draw" | "coords";
  onDrawComplete?: (bbox: [number, number, number, number] | null) => void;
  drawnBbox?: [number, number, number, number] | null;
}

function gradeColor(g: string): string {
  if (g === "F") return "#dc2626";   // Critical — red
  if (g === "D") return "#f97316";   // High Risk — orange
  if (g === "C") return "#f59e0b";   // Elevated — amber
  if (g === "B") return "#38bdf8";   // Stable Buffer — sky
  return "#10b981";                  // Healthy (A) — emerald-500
}

function gradeBrightColor(g: string): string {
  if (g === "F") return "#f87171";   // light red
  if (g === "D") return "#fb923c";   // light orange
  if (g === "C") return "#fbbf24";   // light amber
  if (g === "B") return "#7dd3fc";   // light sky
  return "#34d399";                  // light emerald (A)
}

export default function LeafletMap({
  zones,
  selectedZoneKey,
  onSelectZone,
  inputMode,
  onDrawComplete,
  drawnBbox,
}: LeafletMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const LRef = useRef<any>(null); // holds dynamic import of whole leaflet namespace
  const mapInstanceRef = useRef<LMap | null>(null);
  const markersRef = useRef<globalThis.Map<string, Marker>>(new globalThis.Map());
  const onSelectRef = useRef(onSelectZone);
  useEffect(() => {
    onSelectRef.current = onSelectZone;
  }, [onSelectZone]);
  const initedRef = useRef(false);

  const [mapLoaded, setMapLoaded] = useState(false);
  const onDrawCompleteRef = useRef(onDrawComplete);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const drawRectangleRef = useRef<any>(null);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const hoverBboxRef = useRef<any>(null);

  useEffect(() => {
    onDrawCompleteRef.current = onDrawComplete;
  }, [onDrawComplete]);

  // ---------- Drawing functionality for custom bbox ----------
  useEffect(() => {
    const map = mapInstanceRef.current;
    const L = LRef.current;
    if (!map || !L || !mapLoaded) return;

    if (inputMode === "draw") {
      // Disable dragging and zoom while drawing a custom bbox
      map.dragging.disable();
      map.touchZoom.disable();
      map.doubleClickZoom.disable();
      map.scrollWheelZoom.disable();
      map.boxZoom.disable();
      map.keyboard.disable();

      let isDrawing = false;
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      let startLatLng: any = null;

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const onMouseDown = (e: any) => {
        isDrawing = true;
        startLatLng = e.latlng;
        if (drawRectangleRef.current) {
          drawRectangleRef.current.remove();
        }
        drawRectangleRef.current = L.rectangle([startLatLng, startLatLng], {
          color: "#059669",
          weight: 2,
          fillColor: "#059669",
          fillOpacity: 0.12,
        }).addTo(map);
      };

      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const onMouseMove = (e: any) => {
        if (!isDrawing || !startLatLng || !drawRectangleRef.current) return;
        drawRectangleRef.current.setBounds([startLatLng, e.latlng]);
      };

      const onMouseUp = () => {
        if (!isDrawing) return;
        isDrawing = false;
        if (drawRectangleRef.current) {
          const bounds = drawRectangleRef.current.getBounds();
          const southWest = bounds.getSouthWest();
          const northEast = bounds.getNorthEast();
          const bbox: [number, number, number, number] = [
            southWest.lng,
            southWest.lat,
            northEast.lng,
            northEast.lat,
          ];
          onDrawCompleteRef.current?.(bbox);
        }
      };

      map.on("mousedown", onMouseDown);
      map.on("mousemove", onMouseMove);
      map.on("mouseup", onMouseUp);

      return () => {
        map.off("mousedown", onMouseDown);
        map.off("mousemove", onMouseMove);
        map.off("mouseup", onMouseUp);
      };
    } else {
      // Re-enable interactions when not in drawing mode
      map.dragging.enable();
      map.touchZoom.enable();
      map.doubleClickZoom.enable();
      map.scrollWheelZoom.enable();
      map.boxZoom.enable();
      map.keyboard.enable();
    }
  }, [inputMode, mapLoaded]);

  // ---------- Render pre-drawn bbox on map ----------
  useEffect(() => {
    const map = mapInstanceRef.current;
    const L = LRef.current;
    if (!map || !L || !mapLoaded) return;

    if (drawnBbox && inputMode !== "draw") {
      if (drawRectangleRef.current) {
        drawRectangleRef.current.remove();
      }
      const bounds = L.latLngBounds(
        [drawnBbox[1], drawnBbox[0]],
        [drawnBbox[3], drawnBbox[2]]
      );
      drawRectangleRef.current = L.rectangle(bounds, {
        color: "#059669",
        weight: 2,
        fillColor: "#059669",
        fillOpacity: 0.12,
      }).addTo(map);
      map.fitBounds(bounds, { padding: [20, 20] });
    } else if (!drawnBbox && inputMode !== "draw") {
      if (drawRectangleRef.current) {
        drawRectangleRef.current.remove();
        drawRectangleRef.current = null;
      }
    }
  }, [drawnBbox, inputMode, mapLoaded]);

  // ---------- Marker HTML ----------
  const buildMarkerHtml = useCallback((zone: ZoneData, selected: boolean) => {
    const color = gradeColor(zone.latest_grade);
    const bright = gradeBrightColor(zone.latest_grade);
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
      <div class="map-marker-container ${selected ? "selected" : ""}"
           style="position:relative;display:flex;align-items:center;justify-content:center;
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
                      width:3px;height:3px;border-radius:50%;background:#fafaf9;opacity:0.9;"></div>
        </div>
        <div class="map-marker-label"
             style="position:absolute;left:${Math.round(sz / 2) + 6}px;top:50%;
                    transform:translateY(-50%) scale(${selected ? 1 : 0.85});
                    transform-origin:left center;
                    opacity:${selected ? 1 : 0};
                    transition:opacity 0.22s cubic-bezier(0.34, 1.56, 0.64, 1), transform 0.22s cubic-bezier(0.34, 1.56, 0.64, 1);
                    white-space:nowrap;
                    background:${selected ? color : "#fafaf9"};
                    border:1px solid ${selected ? color : "var(--border-dim)"};
                    border-radius:5px;
                    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03);
                    padding:5px 9px;pointer-events:none;">
          <div style="font-size:8.5px;font-family:monospace;font-weight:800;
                      color:${selected ? "#fff" : "var(--text-primary)"};letter-spacing:0.06em;
                      text-transform:uppercase;margin-bottom:2px;">${shortName}</div>
          <div style="font-size:7.5px;font-family:monospace;
                      color:${selected ? "rgba(255,255,255,0.8)" : "var(--text-secondary)"};">
            <span style="background:${gc}15;color:${gc};border:1px solid ${gc}44;
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

    if (hoverBboxRef.current) {
      hoverBboxRef.current.remove();
      hoverBboxRef.current = null;
    }

    markersRef.current.forEach(m => m.remove());
    markersRef.current.clear();

    zones.forEach(zone => {
      const [lat, lon] = zone.center;
      const selected = zone.key === selKey;
      const sz = selected ? 42 : 30;

      const icon = L.divIcon({
        className: "",
        html: buildMarkerHtml(zone, selected),
        iconSize: [sz, sz],
        iconAnchor: [Math.round(sz / 2), Math.round(sz / 2)],
      });

      const marker: Marker = L.marker([lat, lon], { icon, zIndexOffset: selected ? 1000 : 0 });
      marker.on("click", () => onSelectRef.current(zone.key));

      // Inline hover animation listeners
      marker.on("mouseover", () => {
        const el = marker.getElement();
        if (el) {
          const labelEl = el.querySelector(".map-marker-label") as HTMLElement;
          if (labelEl && !selected) {
            labelEl.style.opacity = "1";
            labelEl.style.transform = "translateY(-50%) scale(1)";
          }
          // Elevate marker on hover
          el.style.zIndex = "9999";
        }

        // Draw animated area box
        if (zone.bbox && zone.bbox.length === 4) {
          if (hoverBboxRef.current) {
            hoverBboxRef.current.remove();
          }
          const [lon_min, lat_min, lon_max, lat_max] = zone.bbox;
          const color = gradeColor(zone.latest_grade);
          hoverBboxRef.current = L.rectangle(
            [[lat_min, lon_min], [lat_max, lon_max]],
            {
              color: color,
              weight: 1.5,
              fillColor: color,
              fillOpacity: 0.04,
              opacity: 0.8,
              className: "animated-zone-bbox",
              interactive: false,
            }
          ).addTo(map);
        }
      });

      marker.on("mouseout", () => {
        const el = marker.getElement();
        if (el) {
          const labelEl = el.querySelector(".map-marker-label") as HTMLElement;
          if (labelEl && !selected) {
            labelEl.style.opacity = "0";
            labelEl.style.transform = "translateY(-50%) scale(0.85)";
          }
          // Reset z-index
          el.style.zIndex = selected ? "1000" : "";
        }

        // Smoothly fade out and remove hover area box
        const rect = hoverBboxRef.current;
        if (rect) {
          rect.setStyle({ opacity: 0, fillOpacity: 0 });
          setTimeout(() => {
            if (hoverBboxRef.current === rect) {
              rect.remove();
              hoverBboxRef.current = null;
            }
          }, 250);
        }
      });

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
      const el = containerRef.current as HTMLDivElement & { _leaflet_id?: number };
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

      L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
        subdomains: "abcd",
        maxZoom: 19,
      }).addTo(map);

      L.control.attribution({ position: "bottomright", prefix: false })
        .addAttribution('© <a href="https://carto.com" style="color:var(--emerald-500)">CARTO</a> · <a href="https://openstreetmap.org" style="color:var(--emerald-500)">OSM</a>')
        .addTo(map);

      L.control.zoom({ position: "topright" }).addTo(map);

      mapInstanceRef.current = map;
      LRef.current = L;

      addMarkers(selectedZoneKey);
      setMapLoaded(true);
    });

    return () => {
      if (hoverBboxRef.current) {
        hoverBboxRef.current.remove();
        hoverBboxRef.current = null;
      }
      if (mapInstanceRef.current) {
        mapInstanceRef.current.remove();
        mapInstanceRef.current = null;
        LRef.current = null;
        markersRef.current.clear();
        initedRef.current = false;
        setMapLoaded(false);
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
      <div ref={containerRef} style={{ width: "100%", height: "100%" }} />

      {/* HUD top */}
      <div style={{
        position: "absolute", top: 52, left: 12, right: 12,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        pointerEvents: "none", zIndex: 500,
      }}>
        {inputMode === "draw" ? (
          <div className="glass-card" style={{ padding: "8px 16px", display: "flex", alignItems: "center", gap: 8, background: "rgba(5,150,105,0.2)", borderColor: "var(--emerald-400)" }}>
            <span className="dot-pulse emerald" />
            <span className="section-label" style={{ color: "var(--emerald-400)", fontWeight: 700 }}>
              Drawing Mode: Click &amp; Drag on Map to Select Bounding Box
            </span>
          </div>
        ) : (
          <div className="glass-card" style={{ padding: "5px 12px", display: "flex", alignItems: "center", gap: 6 }}>
            <span className="dot-pulse emerald" />
            <span className="section-label" style={{ color: "var(--emerald-400)" }}>Live Satellite View</span>
          </div>
        )}
        <div className="glass-card" style={{ padding: "5px 12px" }}>
          <span className="section-label">{zones.length} zones monitored · India</span>
        </div>
      </div>

      {/* Legend - Bottom Left */}
      <div style={{
        position: "absolute", bottom: 12, left: 12,
        zIndex: 500, pointerEvents: "auto",
      }}>
        <div className="glass-card" style={{
          padding: "10px 14px", display: "flex", flexDirection: "column", gap: 7,
          fontSize: 8.5, fontFamily: "monospace", letterSpacing: "0.06em",
          textTransform: "uppercase", color: "var(--text-primary)",
          width: 200, borderRadius: 6,
        }}>
          <div style={{
            fontSize: 7.5, fontWeight: 800, color: "var(--text-muted)",
            borderBottom: "1px solid var(--border-dim)", paddingBottom: 4, marginBottom: 2
          }}>
            Farmland Health Legend
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 14, height: 7, borderRadius: 1.5, background: "#10b981", display: "inline-block" }} />
            <span style={{ color: "var(--text-secondary)" }}>Grade A · Healthy</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 14, height: 7, borderRadius: 1.5, background: "#38bdf8", display: "inline-block" }} />
            <span style={{ color: "var(--text-secondary)" }}>Grade B · Stable Buffer</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 14, height: 7, borderRadius: 1.5, background: "#f59e0b", display: "inline-block" }} />
            <span style={{ color: "var(--text-secondary)" }}>Grade C · Elevated Risk</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 14, height: 7, borderRadius: 1.5, background: "#f97316", display: "inline-block" }} />
            <span style={{ color: "var(--text-secondary)" }}>Grade D · High Risk</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span style={{ width: 14, height: 7, borderRadius: 1.5, background: "#dc2626", display: "inline-block" }} />
            <span style={{ color: "var(--text-secondary)" }}>Grade F · Critical</span>
          </div>
        </div>
      </div>

      {/* Control Help Tips - Bottom Right */}
      <div style={{
        position: "absolute", bottom: 12, right: 12,
        pointerEvents: "none", zIndex: 500,
      }}>
        <div className="glass-card" style={{
          padding: "5px 12px",
          fontSize: 8.5, fontFamily: "monospace", letterSpacing: "0.06em",
          color: "var(--text-muted)", textTransform: "uppercase",
        }}>
          {inputMode === "draw" ? "Click & Drag to draw bbox" : "Scroll to zoom · Drag to pan · Click to audit"}
        </div>
      </div>
    </div>
  );
}
