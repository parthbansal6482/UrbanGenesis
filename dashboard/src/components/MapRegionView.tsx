"use client";

import React, { useState, useRef, useCallback } from "react";

// ============================================================
// TYPES
// ============================================================
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

interface MapRegionViewProps {
  zones: ZoneData[];
  selectedZoneKey: string | null;
  onSelectZone: (key: string) => void;
}

// ============================================================
// GEO → SVG COORDINATE MAPPING
// Viewport: 800 × 640 SVG units
// Bounds: Lon [67, 90], Lat [6, 37]
// ============================================================
const SVG_W = 800;
const SVG_H = 640;
const LON_MIN = 67, LON_MAX = 90;
const LAT_MIN = 6, LAT_MAX = 37;

function geoToSvg(lon: number, lat: number): [number, number] {
  const x = ((lon - LON_MIN) / (LON_MAX - LON_MIN)) * SVG_W;
  const y = (1 - (lat - LAT_MIN) / (LAT_MAX - LAT_MIN)) * SVG_H;
  return [x, y];
}

// ============================================================
// INDIA OUTLINE — simplified polygon (geo coordinates)
// ============================================================
const INDIA_OUTLINE: [number, number][] = [
  [68.1, 23.6], [68.8, 22.8], [69.5, 22.0], [70.2, 20.7], [71.2, 20.3],
  [72.0, 19.8], [72.5, 18.9], [72.7, 17.9], [73.0, 16.5], [73.5, 14.9],
  [74.3, 13.3], [75.2, 11.5], [76.3, 10.0], [77.1, 8.5], [77.6, 8.1],
  [78.2, 8.7], [79.0, 10.2], [79.8, 11.8], [80.2, 13.1], [80.3, 14.5],
  [80.2, 15.9], [80.8, 16.9], [81.8, 17.8], [83.0, 18.4], [84.2, 19.3],
  [85.0, 20.1], [86.4, 20.9], [87.1, 21.5], [87.5, 22.0], [88.3, 22.2],
  [88.5, 22.5], [87.5, 23.5], [85.0, 24.0], [84.0, 24.5], [81.5, 25.0],
  [80.0, 25.5], [78.0, 26.0], [76.0, 26.5], [74.0, 26.8], [72.5, 26.5],
  [71.0, 24.7], [69.5, 24.5], [68.5, 24.4], [68.1, 23.6],
];

// Kashmir region extra (rough)
const KASHMIR_OUTLINE: [number, number][] = [
  [74.0, 26.8], [74.5, 28.2], [75.0, 30.0], [76.0, 31.5],
  [77.5, 32.5], [78.5, 33.5], [80.0, 34.5], [81.5, 35.0],
  [82.5, 34.0], [80.0, 33.0], [79.0, 31.5], [77.0, 30.0],
  [76.0, 29.0], [75.5, 27.5], [74.5, 26.5],
];

// ============================================================
// COMPONENT
// ============================================================
export default function MapRegionView({ zones, selectedZoneKey, onSelectZone }: MapRegionViewProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [viewBox, setViewBox] = useState({ x: 0, y: 0, w: SVG_W, h: SVG_H });
  const [isGrabbing, setIsGrabbing] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const isPanning = useRef(false);
  const panStart = useRef({ mx: 0, my: 0, vx: 0, vy: 0 });

  // ---- Build SVG path strings ----
  const outlinePath = INDIA_OUTLINE.map((pt, i) => {
    const [x, y] = geoToSvg(pt[0], pt[1]);
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ") + " Z";

  const kashmirPath = KASHMIR_OUTLINE.map((pt, i) => {
    const [x, y] = geoToSvg(pt[0], pt[1]);
    return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ") + " Z";

  // ---- Scroll to zoom ----
  const onWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 1.12 : 0.88;
    const rect = svgRef.current!.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    // cursor in viewBox coords
    const cx = viewBox.x + (mx / rect.width) * viewBox.w;
    const cy = viewBox.y + (my / rect.height) * viewBox.h;
    const nw = Math.min(Math.max(viewBox.w * factor, 200), SVG_W);
    const nh = Math.min(Math.max(viewBox.h * factor, 160), SVG_H);
    setViewBox({
      x: Math.max(0, Math.min(SVG_W - nw, cx - (cx - viewBox.x) * (nw / viewBox.w))),
      y: Math.max(0, Math.min(SVG_H - nh, cy - (cy - viewBox.y) * (nh / viewBox.h))),
      w: nw, h: nh,
    });
  }, [viewBox]);

  // ---- Pan ----
  const onPointerDown = useCallback((e: React.PointerEvent) => {
    if ((e.target as Element).closest("[data-zone]")) return;
    isPanning.current = true;
    setIsGrabbing(true);
    panStart.current = { mx: e.clientX, my: e.clientY, vx: viewBox.x, vy: viewBox.y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }, [viewBox]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!isPanning.current || !svgRef.current) return;
    const rect = svgRef.current.getBoundingClientRect();
    const dx = ((panStart.current.mx - e.clientX) / rect.width) * viewBox.w;
    const dy = ((panStart.current.my - e.clientY) / rect.height) * viewBox.h;
    setViewBox(v => ({
      ...v,
      x: Math.max(0, Math.min(SVG_W - v.w, panStart.current.vx + dx)),
      y: Math.max(0, Math.min(SVG_H - v.h, panStart.current.vy + dy)),
    }));
  }, [viewBox.w, viewBox.h]);

  const onPointerUp = useCallback(() => {
    isPanning.current = false;
    setIsGrabbing(false);
  }, []);

  // Reset zoom
  const resetView = () => setViewBox({ x: 0, y: 0, w: SVG_W, h: SVG_H });

  // ---- Coordinate grid lines ----
  const gridLons = [70, 74, 78, 82, 86, 90];
  const gridLats = [10, 14, 18, 22, 26, 30, 34];

  return (
    <div
      style={{
        position: "relative", width: "100%", height: "100%",
        background: "var(--bg-base)", overflow: "hidden",
        cursor: isGrabbing ? "grabbing" : "grab",
        userSelect: "none",
      }}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerUp}
      onPointerLeave={onPointerUp}
    >
      {/* ---- SVG Map ---- */}
      <svg
        ref={svgRef}
        viewBox={`${viewBox.x} ${viewBox.y} ${viewBox.w} ${viewBox.h}`}
        style={{ width: "100%", height: "100%", display: "block" }}
        onWheel={onWheel}
      >
        <defs>
          {/* Background grid pattern */}
          <pattern id="mapGrid" width="40" height="40" patternUnits="userSpaceOnUse">
            <path d="M 40 0 L 0 0 0 40" fill="none" stroke="rgba(51,90,130,0.12)" strokeWidth="0.6" />
          </pattern>

          {/* Glow filter for pins */}
          <filter id="pinGlowRed" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="4" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <filter id="pinGlowGreen" x="-80%" y="-80%" width="260%" height="260%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
          <filter id="landGlow" x="-5%" y="-5%" width="110%" height="110%">
            <feGaussianBlur stdDeviation="1.5" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>

          {/* Clip for SVG bounds */}
          <clipPath id="mapClip">
            <rect x="0" y="0" width={SVG_W} height={SVG_H} />
          </clipPath>
        </defs>

        {/* Background */}
        <rect x="0" y="0" width={SVG_W} height={SVG_H} fill="var(--bg-base)" />
        <rect x="0" y="0" width={SVG_W} height={SVG_H} fill="url(#mapGrid)" />

        <g clipPath="url(#mapClip)">
          {/* ---- Coordinate grid lines + labels ---- */}
          {gridLons.map(lon => {
            const [x] = geoToSvg(lon, LAT_MIN);
            return (
              <g key={`lon-${lon}`}>
                <line
                  x1={x} y1={0} x2={x} y2={SVG_H}
                  stroke="rgba(51,90,130,0.2)" strokeWidth="0.8" strokeDasharray="4 6"
                />
                <text x={x} y={SVG_H - 6} textAnchor="middle"
                  fill="rgba(51,90,130,0.6)" fontSize="9" fontFamily="monospace">
                  {lon}°E
                </text>
              </g>
            );
          })}
          {gridLats.map(lat => {
            const [, y] = geoToSvg(LON_MIN, lat);
            return (
              <g key={`lat-${lat}`}>
                <line
                  x1={0} y1={y} x2={SVG_W} y2={y}
                  stroke="rgba(51,90,130,0.2)" strokeWidth="0.8" strokeDasharray="4 6"
                />
                <text x={8} y={y + 3} textAnchor="start"
                  fill="rgba(51,90,130,0.6)" fontSize="9" fontFamily="monospace">
                  {lat}°N
                </text>
              </g>
            );
          })}

          {/* ---- India land mass fill ---- */}
          <path
            d={outlinePath}
            fill="rgba(10,22,44,0.92)"
            stroke="rgba(5,150,105,0.45)"
            strokeWidth="1.5"
            strokeLinejoin="round"
            filter="url(#landGlow)"
          />
          <path
            d={kashmirPath}
            fill="rgba(10,22,44,0.88)"
            stroke="rgba(5,150,105,0.3)"
            strokeWidth="1"
            strokeLinejoin="round"
          />

          {/* ---- Connection arcs from HQ (Bengaluru) to other zones ---- */}
          {(() => {
            const hq = zones.find(z => z.key === "bengaluru");
            if (!hq) return null;
            const [hx, hy] = geoToSvg(hq.center[1], hq.center[0]);
            return zones
              .filter(z => z.key !== "bengaluru")
              .map(z => {
                const [zx, zy] = geoToSvg(z.center[1], z.center[0]);
                const mx = (hx + zx) / 2;
                const my = (hy + zy) / 2 - 60;
                const isHighRisk = z.latest_grade === "F" || z.latest_grade === "C";
                const color = isHighRisk ? "rgba(220,38,38,0.25)" : "rgba(5,150,105,0.2)";
                return (
                  <path
                    key={z.key}
                    d={`M${hx},${hy} Q${mx},${my} ${zx},${zy}`}
                    fill="none"
                    stroke={color}
                    strokeWidth="1.2"
                    strokeDasharray="5 5"
                  />
                );
              });
          })()}

          {/* ---- Zone markers ---- */}
          {zones.map(zone => {
            const [lat, lon] = zone.center;
            const [cx, cy] = geoToSvg(lon, lat);
            const isHighRisk = zone.latest_grade === "F" || zone.latest_grade === "C";
            const isSelected = zone.key === selectedZoneKey;
            const isHovered = zone.key === hovered;
            const color = isHighRisk ? "#dc2626" : "#059669";
            const colorBright = isHighRisk ? "#f87171" : "#34d399";

            // Short display name
            const shortName = zone.name
              .replace(" Agricultural Zone", "")
              .replace(" Agricultural Buffer Zone", "")
              .replace(" Peripheral", "")
              .replace(" Farmland", "");

            return (
              <g
                key={zone.key}
                data-zone={zone.key}
                style={{ cursor: "pointer" }}
                onClick={e => { e.stopPropagation(); onSelectZone(zone.key); }}
                onMouseEnter={() => setHovered(zone.key)}
                onMouseLeave={() => setHovered(null)}
              >
                {/* Outer pulse ring (CSS animation via SVG animate) */}
                <circle cx={cx} cy={cy} r={isSelected ? 28 : 22} fill="none"
                  stroke={color} strokeWidth="1" opacity="0.2">
                  <animate attributeName="r" values={`${isSelected ? 22 : 16};${isSelected ? 34 : 26};${isSelected ? 22 : 16}`}
                    dur={isHighRisk ? "1.8s" : "2.5s"} repeatCount="indefinite" />
                  <animate attributeName="opacity" values="0.3;0;0.3"
                    dur={isHighRisk ? "1.8s" : "2.5s"} repeatCount="indefinite" />
                </circle>

                {/* Middle ring */}
                <circle cx={cx} cy={cy} r={isSelected ? 16 : 12} fill="none"
                  stroke={color} strokeWidth={isSelected ? 2 : 1.2} opacity="0.5">
                  <animate attributeName="r" values={`${isSelected ? 12 : 8};${isSelected ? 20 : 16};${isSelected ? 12 : 8}`}
                    dur={isHighRisk ? "1.8s" : "2.5s"} repeatCount="indefinite"
                    begin="0.4s" />
                  <animate attributeName="opacity" values="0.6;0.1;0.6"
                    dur={isHighRisk ? "1.8s" : "2.5s"} repeatCount="indefinite"
                    begin="0.4s" />
                </circle>

                {/* Core dot */}
                <circle
                  cx={cx} cy={cy}
                  r={isSelected ? 8 : isHovered ? 7 : 5.5}
                  fill={isSelected || isHovered ? colorBright : color}
                  stroke={isSelected ? "#ffffff" : colorBright}
                  strokeWidth={isSelected ? 2 : 1}
                  style={{ transition: "r 0.2s ease" }}
                />

                {/* Inner bright dot */}
                <circle cx={cx} cy={cy} r={isSelected ? 3 : 2} fill="#ffffff" opacity="0.9" />

                {/* Label card */}
                <g transform={`translate(${cx + 12}, ${cy - 28})`}
                  opacity={isSelected || isHovered ? 1 : 0.85}
                  style={{ transition: "opacity 0.2s" }}>
                  <rect
                    x={0} y={0} width={shortName.length * 6.3 + 16} height={34}
                    rx={5}
                    fill={isSelected ? color : "rgba(5,12,20,0.88)"}
                    stroke={color}
                    strokeWidth="1"
                  />
                  <text x={8} y={12}
                    fill={isSelected ? "#ffffff" : colorBright}
                    fontSize="8.5" fontFamily="monospace" fontWeight="700"
                    letterSpacing="0.04em">
                    {shortName.toUpperCase()}
                  </text>
                  <text x={8} y={26}
                    fill={isSelected ? "rgba(255,255,255,0.8)" : "rgba(148,168,192,0.9)"}
                    fontSize="7.5" fontFamily="monospace">
                    {zone.latest_grade}  ·  ABI {zone.latest_abi.toFixed(2)}  ·  {zone.overall_abi_change_pct > 0 ? "+" : ""}{zone.overall_abi_change_pct}%
                  </text>
                </g>
              </g>
            );
          })}
        </g>
      </svg>

      {/* ---- HUD overlays ---- */}
      {/* Top bar */}
      <div style={{
        position: "absolute", top: 12, left: 12, right: 12,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        pointerEvents: "none", zIndex: 20,
      }}>
        <div className="glass-card" style={{ padding: "5px 12px", display: "flex", alignItems: "center", gap: 6 }}>
          <span className="dot-pulse emerald" />
          <span className="section-label" style={{ color: "var(--emerald-400)" }}>Live Region Map</span>
        </div>
        <div className="glass-card" style={{ padding: "5px 12px" }}>
          <span className="section-label">{zones.length} zones · South Asia coverage</span>
        </div>
      </div>

      {/* Zoom controls */}
      <div style={{
        position: "absolute", bottom: 42, right: 12, zIndex: 20,
        display: "flex", flexDirection: "column", gap: 4,
        pointerEvents: "auto",
      }}>
        <button
          onClick={() => setViewBox(v => {
            const nw = Math.max(v.w * 0.75, 200), nh = Math.max(v.h * 0.75, 160);
            return { x: v.x + (v.w - nw) / 2, y: v.y + (v.h - nh) / 2, w: nw, h: nh };
          })}
          style={{
            width: 30, height: 30, borderRadius: 6, border: "1px solid var(--border-dim)",
            background: "rgba(5,12,20,0.9)", color: "var(--text-secondary)", fontSize: 16,
            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >+</button>
        <button
          onClick={() => setViewBox(v => {
            const nw = Math.min(v.w * 1.35, SVG_W), nh = Math.min(v.h * 1.35, SVG_H);
            return { x: Math.max(0, v.x - (nw - v.w) / 2), y: Math.max(0, v.y - (nh - v.h) / 2), w: nw, h: nh };
          })}
          style={{
            width: 30, height: 30, borderRadius: 6, border: "1px solid var(--border-dim)",
            background: "rgba(5,12,20,0.9)", color: "var(--text-secondary)", fontSize: 16,
            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
          }}
        >−</button>
        <button
          onClick={resetView}
          style={{
            width: 30, height: 30, borderRadius: 6, border: "1px solid var(--border-dim)",
            background: "rgba(5,12,20,0.9)", color: "var(--text-secondary)", fontSize: 11,
            cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
            fontFamily: "monospace",
          }}
        >⊡</button>
      </div>

      {/* Legend */}
      <div style={{
        position: "absolute", bottom: 12, left: 12, right: 12,
        display: "flex", justifyContent: "center",
        pointerEvents: "none", zIndex: 20,
      }}>
        <div className="glass-card" style={{
          padding: "5px 14px", display: "flex", alignItems: "center", gap: 16,
          fontSize: 9, fontFamily: "monospace", letterSpacing: "0.08em",
          textTransform: "uppercase", color: "var(--text-muted)",
        }}>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#dc2626", display: "inline-block" }} />
            Critical Alert
          </span>
          <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#059669", display: "inline-block" }} />
            Stable Zone
          </span>
          <span>Scroll to zoom · Drag to pan · Click to audit</span>
        </div>
      </div>
    </div>
  );
}
