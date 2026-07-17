"use client";

import React, { useEffect, useRef, useCallback, useState } from "react";
import type { Map as LMap, Marker } from "leaflet";

interface NominatimResult {
  place_id: number;
  display_name: string;
  lat: string;
  lon: string;
  type: string;
  class: string;
  boundingbox?: [string, string, string, string]; // [minlat, maxlat, minlon, maxlon]
}

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
  const LRef = useRef<any>(null);
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

  // ---------- Location search state ----------
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<NominatimResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchFocused, setSearchFocused] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const searchRef = useRef<HTMLDivElement>(null);

  // Debounced Nominatim geocode
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    const q = searchQuery.trim();
    if (q.length < 2) {
      setSearchResults([]);
      setSearchOpen(false);
      return;
    }
    debounceRef.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const res = await fetch(
          `https://nominatim.openstreetmap.org/search?q=${encodeURIComponent(q)}&format=json&limit=6&addressdetails=0`,
          { headers: { "Accept-Language": "en" } }
        );
        const data: NominatimResult[] = await res.json();
        setSearchResults(data);
        setSearchOpen(true);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 400);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [searchQuery]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setSearchOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleSelectResult = (result: NominatimResult) => {
    const map = mapInstanceRef.current;
    const L = LRef.current;
    if (!map || !L) return;
    setSearchQuery(result.display_name.split(",")[0]);
    setSearchOpen(false);
    setSearchFocused(false);
    if (result.boundingbox) {
      const [minLat, maxLat, minLon, maxLon] = result.boundingbox.map(Number);
      map.fitBounds([[minLat, minLon], [maxLat, maxLon]], { animate: true, duration: 1.2, padding: [40, 40] });
    } else {
      map.flyTo([parseFloat(result.lat), parseFloat(result.lon)], 13, { duration: 1.4, easeLinearity: 0.25 });
    }
  };


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
                    border:2px solid ${color};animation:fgPulse 2s ease-in-out infinite;
                    opacity:0.75;"></div>
        <div style="position:absolute;width:${Math.round(sz * 0.65)}px;height:${Math.round(sz * 0.65)}px;
                    border-radius:50%;border:2px solid ${color};
                    animation:fgPulse 2s ease-in-out infinite 0.45s;opacity:0.9;"></div>
        <div style="width:${dotSz}px;height:${dotSz}px;border-radius:50%;
                    background:${selected ? bright : color};
                    border:2px solid #ffffff;
                    box-shadow:0 0 14px 2px ${color}, 0 0 0 1px ${color};
                    position:relative;z-index:2;">
          <div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);
                      width:3px;height:3px;border-radius:50%;background:#ffffff;opacity:0.95;"></div>
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

      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 19,
      }).addTo(map);

      L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}", {
        maxZoom: 19,
      }).addTo(map);


      L.control.attribution({ position: "bottomright", prefix: false })
        .addAttribution('Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community')
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

      {/* HUD top — only shown during drawing mode */}
      {inputMode === "draw" && (
        <div style={{
          position: "absolute", top: 52, left: 12, right: 12,
          display: "flex", alignItems: "center", justifyContent: "space-between",
          pointerEvents: "none", zIndex: 500,
        }}>
          <div className="glass-card" style={{ padding: "8px 16px", display: "flex", alignItems: "center", gap: 8, background: "rgba(5,150,105,0.2)", borderColor: "var(--emerald-400)", pointerEvents: "auto" }}>
            <span className="dot-pulse emerald" />
            <span className="section-label" style={{ color: "var(--emerald-400)", fontWeight: 700 }}>
              Drawing Mode: Click &amp; Drag on Map to Select Bounding Box
            </span>
          </div>
        </div>
      )}

      {/* ── Location Search Bar ── */}
      {inputMode !== "draw" && (
        <div
          ref={searchRef}
          style={{
            position: "absolute",
            top: 12,
            left: 12,
            zIndex: 600,
            width: 280,
          }}
        >
          {/* Input */}
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: 8,
            background: "var(--bg-glass)",
            border: searchFocused ? "1px solid var(--emerald-500)" : "1px solid var(--border-bright)",
            borderRadius: searchOpen && searchResults.length > 0 ? "10px 10px 0 0" : 10,
            padding: "8px 12px",
            backdropFilter: "blur(12px)",
            boxShadow: "0 6px 20px -4px rgba(28, 25, 23, 0.08)",
            transition: "border-color 0.15s, border-radius 0.15s, box-shadow 0.15s",
          }}>
            {searchLoading ? (
              <div style={{
                width: 14, height: 14, borderRadius: "50%", flexShrink: 0,
                border: "1.5px solid var(--border-dim)",
                borderTopColor: "var(--emerald-400)",
                animation: "spin 0.8s linear infinite",
              }} />
            ) : (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke={searchFocused ? "var(--emerald-500)" : "var(--text-muted)"} strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, transition: "stroke 0.15s" }}>
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            )}
            <input
              type="text"
              placeholder="Search any place globally..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              onFocus={() => {
                setSearchFocused(true);
                if (searchResults.length > 0) setSearchOpen(true);
              }}
              onBlur={() => setSearchFocused(false)}
              onKeyDown={e => {
                if (e.key === "Escape") { setSearchOpen(false); setSearchQuery(""); }
                if (e.key === "Enter" && searchResults.length > 0) handleSelectResult(searchResults[0]);
              }}
              style={{
                flex: 1,
                background: "transparent",
                border: "none",
                outline: "none",
                color: "var(--text-primary)",
                fontSize: 11,
                fontFamily: "monospace",
                letterSpacing: "0.02em",
              }}
            />
            {searchQuery && (
              <button
                onClick={() => { setSearchQuery(""); setSearchResults([]); setSearchOpen(false); }}
                style={{
                  background: "none", border: "none", cursor: "pointer",
                  color: "var(--text-muted)", padding: 0, display: "flex", flexShrink: 0,
                  alignItems: "center",
                }}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            )}
          </div>

          {/* Dropdown results */}
          {searchOpen && (
            <div style={{
              background: "rgba(255, 255, 255, 0.95)",
              border: searchFocused ? "1px solid var(--emerald-500)" : "1px solid var(--border-bright)",
              borderTop: "none",
              borderRadius: "0 0 10px 10px",
              backdropFilter: "blur(12px)",
              boxShadow: "0 12px 30px rgba(28, 25, 23, 0.1)",
              overflow: "hidden",
              transition: "border-color 0.15s",
            }}>
              {searchResults.length === 0 && !searchLoading ? (
                <div style={{
                  padding: "10px 14px",
                  fontSize: 10, fontFamily: "monospace",
                  color: "var(--text-muted)",
                }}>
                  No results found
                </div>
              ) : (
                searchResults.map((r, i) => (
                  <button
                    key={r.place_id}
                    onMouseDown={(e) => {
                      // Prevent input blur before onClick fires
                      e.preventDefault();
                    }}
                    onClick={() => handleSelectResult(r)}
                    style={{
                      width: "100%",
                      background: "transparent",
                      border: "none",
                      borderTop: i > 0 ? "1px solid var(--border-dim)" : "none",
                      padding: "9px 14px",
                      cursor: "pointer",
                      textAlign: "left",
                      display: "flex",
                      flexDirection: "column",
                      gap: 3,
                      transition: "background 0.12s",
                    }}
                    onMouseEnter={e => (e.currentTarget.style.background = "var(--emerald-dim)")}
                    onMouseLeave={e => (e.currentTarget.style.background = "transparent")}
                  >
                    <span style={{ fontSize: 10.5, color: "var(--text-primary)", fontFamily: "monospace", lineHeight: 1.4 }}>
                      {r.display_name.length > 50 ? r.display_name.slice(0, 50) + "…" : r.display_name}
                    </span>
                    <span style={{
                      fontSize: 8.5, fontFamily: "monospace", letterSpacing: "0.05em",
                      textTransform: "uppercase",
                      color: "var(--emerald-600)",
                      background: "var(--emerald-dim)",
                      border: "1px solid rgba(5, 150, 105, 0.15)",
                      borderRadius: 3, padding: "1px 5px",
                      width: "fit-content",
                    }}>
                      {r.class} · {r.type}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      )}


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


    </div>
  );
}
