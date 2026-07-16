"use client";

import React, { useState, useEffect, useMemo, useRef } from "react";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";

// Lazy load to avoid SSR issues with browser APIs (canvas, etc.)
const LeafletMap = dynamic(() => import("../components/LeafletMap"), { ssr: false });
const SliderComparison = dynamic(() => import("../components/SliderComparison"), { ssr: false });

// ============================================================
// TYPES
// ============================================================
interface ZoneData {
  key: string;
  name: string;
  bbox: number[];
  center: number[];
  years: number[];
  satyukt_relevance: string;
  latest_grade: string;
  latest_abi: number;
  overall_abi_change_pct: number;
  cropland_loss_ha: number;
  encroachment_alert: boolean;
}

interface MetricDetails {
  latest_abi: number;
  overall_abi_change_pct: number;
  cropland_loss_ha: number;
  grade: string;
  label: string;
  description: string;
  encroachment_alert: boolean;
  encroachment?: {
    total_cropland_lost_ha: number;
    total_water_lost_ha: number;
  };
}

interface Transition {
  class_id: number;
  class_name: string;
  before_pct: number;
  after_pct: number;
  trend_shift_pct: number;
  status: "increase" | "decrease" | "stable";
}

interface TimeseriesRecord {
  year: number;
  abi: number;
  cropland_pixels: number;
  vegetation_pixels: number;
  water_pixels: number;
  buildings_pixels: number;
  soil_pixels: number;
  cropland_pct: number;
  vegetation_pct: number;
  water_pct: number;
  buildings_pct: number;
  soil_pct: number;
}

interface AnalysisResponse {
  is_mock?: boolean;
  zone_info: {
    key: string;
    name: string;
    bbox: number[];
    center: number[];
    years: number[];
    satyukt_relevance: string;
  };
  metrics: MetricDetails;
  comparison: {
    before_year: number;
    after_year: number;
    before_abi: number;
    after_abi: number;
    abi_change_pct: number;
  };
  transitions: Transition[];
  timeseries: TimeseriesRecord[];
  overlays: {
    before: { true_color: string | null; ndvi: string | null; mask: string | null };
    after: { true_color: string | null; ndvi: string | null; mask: string | null };
    encroachment_heatmap?: string | null;
  };
}

// ============================================================
// CONSTANTS
// ============================================================
const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// (Precomputed mock fallbacks removed to ensure actual backend errors are displayed)};

const CLASS_COLORS: Record<string, string> = {
  Buildings: "#dc2626",
  Cropland: "#d97706",
  "Dense Vegetation": "#16a34a",
  "Water Bodies": "#1E64C8",  // matches app.py CLASS_INFO color 4
  "Bare Soil": "#92400e",
};

function gradeClass(g: string): string {
  if (g === "F") return "f";
  if (g === "D") return "d";
  if (g === "C") return "c";
  if (g === "B") return "b";
  return "a";
}

// ============================================================
// LINE CHART (SVG)
// ============================================================
function LineChart({
  data, beforeYear, afterYear, isExpanded = false,
}: { data: TimeseriesRecord[]; beforeYear: number; afterYear: number; isExpanded?: boolean }) {
  // Memoize all SVG coordinate computations — only recompute when data or
  // isExpanded changes (not on every parent re-render).
  const { margin, W, H, gx, gy, gridTicks, linePts, areaPts } = useMemo(() => {
    const margin = isExpanded
      ? { top: 28, right: 24, bottom: 36, left: 60 }
      : { top: 18, right: 14, bottom: 28, left: 40 };
    const W = isExpanded ? 800 : 420;
    const H = isExpanded ? 360 : 150;
    const xW = W - margin.left - margin.right;
    const yH = H - margin.top - margin.bottom;

    if (!data.length) {
      return {
        margin, W, H, yH,
        gx: () => 0, gy: () => 0,
        gridTicks: [], linePts: "", areaPts: "", years: [],
      };
    }

    const years = data.map(d => d.year);
    const abis  = data.map(d => d.abi);
    const minVal = Math.min(...abis);
    const maxVal = Math.max(...abis);

    // Dynamic framing with 15% padding top and bottom to fit values beautifully
    const valRange = maxVal - minVal;
    const padding = valRange > 0 ? valRange * 0.15 : 0.05;
    const yMin = Math.max(0, minVal - padding);
    const yMax = maxVal + padding;
    const yRange = yMax - yMin;

    const tickCount = 4;
    const gridTicks = Array.from({ length: tickCount }, (_, i) => +(yMin + (i * yRange) / (tickCount - 1)).toFixed(2));

    const gx = (yr: number) => margin.left + (years.indexOf(yr) / (years.length - 1)) * xW;
    const gy = (v: number) => margin.top + yH - ((v - yMin) / (yRange || 1)) * yH;

    const linePts = data.map(d => `${gx(d.year).toFixed(1)},${gy(d.abi).toFixed(1)}`).join(" ");
    const areaPts = `${gx(years[0])},${margin.top + yH} ${linePts} ${gx(years[years.length - 1])},${margin.top + yH}`;

    return { margin, W, H, yH, gx, gy, gridTicks, linePts, areaPts, years };
  }, [data, isExpanded]);

  if (!data.length) return null;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      {gridTicks.map(v => (
        <g key={v}>
          <line x1={margin.left} y1={gy(v)} x2={W - margin.right} y2={gy(v)}
            stroke="rgba(28,25,23,0.08)" strokeWidth={isExpanded ? "2" : "1"} strokeDasharray="3 5" />
          <text x={margin.left - 8} y={gy(v) + 4} textAnchor="end"
            fill="#78716c" fontSize={isExpanded ? "12" : "8"} fontFamily="monospace" fontWeight="600">
            {v >= 1 ? v.toFixed(1) : v.toFixed(2)}
          </text>
        </g>
      ))}
      <polygon points={areaPts} fill="rgba(16, 185, 129, 0.04)" />
      <polyline fill="none" stroke="#059669" strokeWidth={isExpanded ? "4" : "2"} strokeLinecap="round" strokeLinejoin="round" points={linePts} />
      {data.map(d => {
        const cx = gx(d.year), cy = gy(d.abi);
        const sel = d.year === beforeYear || d.year === afterYear;
        return (
          <g key={d.year}>
            <text x={cx} y={H - (isExpanded ? 12 : 8)} textAnchor="middle" fill="#78716c"
              fontSize={isExpanded ? "13" : "9"} fontFamily="monospace" fontWeight="700">{d.year}</text>
            <circle cx={cx} cy={cy} r={sel ? (isExpanded ? 7 : 5) : (isExpanded ? 5 : 3.5)}
              fill={sel ? "#059669" : "#fafaf9"} stroke={sel ? "#047857" : "#059669"} strokeWidth={sel ? (isExpanded ? 3 : 2) : 1.5} />
            {sel && (
              <text x={cx} y={cy - (isExpanded ? 13 : 9)} textAnchor="middle" fill="#047857"
                fontSize={isExpanded ? "12" : "8"} fontFamily="monospace" fontWeight="700">{d.abi.toFixed(2)}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ============================================================
// ENCROACHMENT CHART — 3-series line chart (crop, built, water) — single axis
// ============================================================
function EncroachmentChart({ data, isExpanded = false }: { data: TimeseriesRecord[]; isExpanded?: boolean }) {
  // Memoize all coordinate & series computations — only recompute when data
  // or isExpanded changes (not on every parent re-render).
  const { margin, W, H, yBase, gx, gy, crops, buildings, water,
          cropPts, builtPts, waterPts, area, maxScale } = useMemo(() => {
    const margin = isExpanded
      ? { top: 28, right: 16, bottom: 32, left: 52 }
      : { top: 22, right: 12, bottom: 26, left: 46 };
    const W = isExpanded ? 680 : 455;
    const H = isExpanded ? 360 : 165;
    const xW = W - margin.left - margin.right;
    const yH = H - margin.top - margin.bottom;
    const yBase = margin.top + yH;

    if (!data.length) {
      return {
        margin, W, H, yBase,
        crops: [], buildings: [], water: [],
        cropPts: "", builtPts: "", waterPts: "", area: () => "",
        maxScale: 1000,
        gx: () => 0, gy: () => 0,
      };
    }

    const crops     = data.map(d => d.cropland_pixels  * 0.01);
    const buildings = data.map(d => d.buildings_pixels * 0.01);
    const water     = data.map(d => d.water_pixels     * 0.01);
    const maxVal    = Math.max(...crops, ...buildings, ...water);
    const maxScale  = maxVal < 1000 ? 1000 : Math.ceil(maxVal / 1000) * 1000;

    const gx = (i: number) => margin.left + (i / Math.max(data.length - 1, 1)) * xW;
    const gy = (v: number) => margin.top + yH - (v / maxScale) * yH;

    const pts = (vals: number[]) =>
      vals.map((v, i) => `${gx(i).toFixed(1)},${gy(v).toFixed(1)}`).join(" ");
    const area = (vals: number[]) =>
      `${gx(0).toFixed(1)},${yBase} ${pts(vals)} ${gx(vals.length - 1).toFixed(1)},${yBase}`;

    return {
      margin, W, H, yBase, gx, gy, crops, buildings, water,
      cropPts: pts(crops), builtPts: pts(buildings), waterPts: pts(water), area, maxScale,
    };
  }, [data, isExpanded]);

  if (!data.length) return null;

  const tickCount = 4;

  const fmt = (v: number) => v >= 1000 ? `${(v / 1000).toFixed(0)}k` : `${v}`;
  const sw  = isExpanded ? "2" : "1.5";    // stroke width
  const fs2 = isExpanded ? 10 : 7.5;
  const dr  = isExpanded ? 3 : 2.5;        // dot radius

  // Legend line swatch helper
  const swatch = (x: number, color: string) => (
    <line x1={x} y1="-3" x2={x + (isExpanded ? 14 : 10)} y2="-3"
      stroke={color} strokeWidth={sw} strokeLinecap="round" />
  );

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      {/* ---- Grid lines + left axis labels ---- */}
      {Array.from({ length: tickCount }, (_, i) => {
        const v = Math.round(((i + 1) / tickCount) * maxScale);
        const y = gy(v);
        return (
          <g key={`g-${i}`}>
            <line x1={margin.left} y1={y} x2={W - margin.right} y2={y}
              stroke="rgba(28,25,23,0.08)" strokeWidth="0.8" strokeDasharray="3 5" />
            <text x={margin.left - 6} y={y + 3.5} textAnchor="end"
              fill="#78716c" fontSize={fs2} fontFamily="monospace" fontWeight="600">
              {fmt(v)}
            </text>
          </g>
        );
      })}

      {/* ---- Y-axis rule ---- */}
      <line x1={margin.left} y1={margin.top} x2={margin.left} y2={yBase}
        stroke="rgba(28,25,23,0.12)" strokeWidth="1" />

      {/* ---- Area fills (back to front: crop → built → water) ---- */}
      <polygon points={area(crops)}     fill="rgba(245, 158, 11, 0.04)"  />
      <polygon points={area(buildings)} fill="rgba(248, 113, 113, 0.03)" />
      <polygon points={area(water)}     fill="rgba(56, 189, 248, 0.04)" />

      {/* ---- Polylines ---- */}
      <polyline fill="none" stroke="#f59e0b" strokeWidth={sw}
        strokeLinecap="round" strokeLinejoin="round" points={cropPts} />
      <polyline fill="none" stroke="#f87171" strokeWidth={sw}
        strokeLinecap="round" strokeLinejoin="round" points={builtPts} />
      <polyline fill="none" stroke="#38bdf8" strokeWidth={sw}
        strokeLinecap="round" strokeLinejoin="round" points={waterPts} />

      {/* ---- Dots (every 2nd point to avoid clutter, always first+last) ---- */}
      {data.map((d, i) => {
        const show = i === 0 || i === data.length - 1 || i % 2 === 0;
        if (!show) return null;
        return (
          <g key={`dots-${d.year}`}>
            <circle cx={gx(i)} cy={gy(crops[i])}     r={dr} fill="#f59e0b" stroke="#fef3c7" strokeWidth="0.8" />
            <circle cx={gx(i)} cy={gy(buildings[i])} r={dr} fill="#f87171" stroke="#fee2e2" strokeWidth="0.8" />
            <circle cx={gx(i)} cy={gy(water[i])}     r={dr} fill="#38bdf8" stroke="#e0f2fe" strokeWidth="0.8" />
          </g>
        );
      })}

      {/* ---- X-axis year labels (every 2nd) ---- */}
      {data.map((d, i) => (
        (i % 2 === 0 || data.length <= 10) && (
          <text key={`xl-${d.year}`}
            x={gx(i)} y={yBase + (isExpanded ? 16 : 13)} textAnchor="middle"
            fill="rgba(148,163,184,0.75)" fontSize={fs2} fontFamily="monospace" fontWeight="700">
            {d.year}
          </text>
        )
      ))}

      {/* ---- Legend ---- */}
      <g transform={`translate(${margin.left + 2}, ${margin.top - 13})`}
         style={{ fontFamily: "monospace", fontWeight: 700, fontSize: fs2 }}>
        {swatch(0, "#f59e0b")}
        <circle cx={isExpanded ? 7 : 5} cy="-3" r={isExpanded ? 2.5 : 2} fill="#f59e0b" stroke="#fef3c7" strokeWidth="0.6" />
        <text x={isExpanded ? 18 : 14} y="0" fill="rgba(212,174,92,0.9)">Cropland</text>

        {swatch(isExpanded ? 90 : 73, "#f87171")}
        <circle cx={isExpanded ? 97 : 78} cy="-3" r={isExpanded ? 2.5 : 2} fill="#f87171" stroke="#fee2e2" strokeWidth="0.6" />
        <text x={isExpanded ? 108 : 87} y="0" fill="rgba(248,113,113,0.9)">Built-up</text>

        {swatch(isExpanded ? 180 : 147, "#38bdf8")}
        <circle cx={isExpanded ? 187 : 152} cy="-3" r={isExpanded ? 2.5 : 2} fill="#38bdf8" stroke="#e0f2fe" strokeWidth="0.6" />
        <text x={isExpanded ? 198 : 161} y="0" fill="rgba(56,189,248,0.9)">Water</text>
      </g>
    </svg>
  );
}

// ============================================================
// LOCAL STORAGE PERSISTENCE HELPERS FOR CUSTOM REGIONS
// ============================================================
const getStoredCustomZones = (): ZoneData[] => {
  if (typeof window === "undefined") return [];
  try {
    const data = localStorage.getItem("farmguard_custom_zones");
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
};

const saveCustomZone = (zone: ZoneData, replaceYears = false) => {
  if (typeof window === "undefined") return;
  try {
    const existing = getStoredCustomZones();
    const index = existing.findIndex(z => z.key === zone.key);
    if (index >= 0) {
      // On force refresh (replaceYears=true): replace years to wipe forecasted data
      // Normally: merge years to preserve previously forecasted future years
      const finalYears = replaceYears
        ? zone.years
        : Array.from(new Set([...existing[index].years, ...zone.years])).sort((a, b) => a - b);
      existing[index] = {
        ...existing[index],
        ...zone,
        years: finalYears,
      };
      localStorage.setItem("farmguard_custom_zones", JSON.stringify(existing));
    } else {
      localStorage.setItem("farmguard_custom_zones", JSON.stringify([...existing, zone]));
    }
  } catch (e) {
    console.error("Failed to save custom zone to localStorage:", e);
  }
};

const deleteStoredCustomZone = (key: string) => {
  if (typeof window === "undefined") return;
  try {
    const existing = getStoredCustomZones();
    const updated = existing.filter(z => z.key !== key);
    localStorage.setItem("farmguard_custom_zones", JSON.stringify(updated));
  } catch (e) {
    console.error("Failed to delete custom zone from localStorage:", e);
  }
};

const getBboxPhysicalArea = (minLon: number, minLat: number, maxLon: number, maxLat: number): string => {
  const avgLat = (minLat + maxLat) / 2;
  const latRad = (avgLat * Math.PI) / 180;
  const widthKm = Math.abs(maxLon - minLon) * 111.32 * Math.cos(latRad);
  const heightKm = Math.abs(maxLat - minLat) * 111.32;
  const areaKm2 = widthKm * heightKm;
  const areaHa = areaKm2 * 100;

  if (areaKm2 >= 1.0) {
    return `${areaKm2.toFixed(2)} km² (~${Math.round(areaHa)} ha)`;
  } else {
    return `${areaHa.toFixed(1)} ha (~${areaKm2.toFixed(3)} km²)`;
  }
};

// ============================================================
// MAIN PAGE
// ============================================================
export default function Home() {
  const [zones, setZones] = useState<ZoneData[]>([]);
  const [selectedZoneKey, setSelectedZoneKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"map" | "comparison">("map");

  const [inputMode, setInputMode] = useState<"named" | "draw" | "coords">("named");
  const [customBbox, setCustomBbox] = useState<[number, number, number, number] | null>(null);
  const [coordsInput, setCoordsInput] = useState({ minLon: "", minLat: "", maxLon: "", maxLat: "" });
  const [coordsError, setCoordsError] = useState<string | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [zonesError, setZonesError] = useState<string | null>(null);

  const [beforeYear, setBeforeYear] = useState<number>(2017);
  const [afterYear, setAfterYear] = useState<number>(2025);
  const [vizMode, setVizMode] = useState<string>("AI Land Use Classification");
  const [sliderValue, setSliderValue] = useState<number>(50);

  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState<boolean>(false);
  const [loadingForecast, setLoadingForecast] = useState<boolean>(false);
  const [apiWarning, setApiWarning] = useState<string | null>(null);
  const [expandedChart, setExpandedChart] = useState<"line" | "encroachment" | null>(null);
  const [refreshTrigger, setRefreshTrigger] = useState<number>(0);
  const forceRefreshRef = useRef<boolean>(false);

  const currentZone = zones.find(z => z.key === selectedZoneKey) || null;

  const availableYears = useMemo(() => {
    // Always prefer the zone registry's years (which survive refresh and include forecasted years)
    if (currentZone) {
      return currentZone.years;
    }
    // Fallback: derive from last analysis response (e.g. brand-new custom bbox not yet in zones)
    if (analysis && analysis.zone_info && analysis.zone_info.years) {
      return analysis.zone_info.years;
    }
    return [2017, 2019, 2021, 2023];
  }, [currentZone, analysis]);

  // Clamp selected years when availableYears change (e.g. switching zones or modes)
  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (!availableYears || availableYears.length === 0) return;
    setBeforeYear(prev => {
      if (availableYears.includes(prev)) return prev;
      return availableYears.reduce((prevClose, curr) => 
        Math.abs(curr - prev) < Math.abs(prevClose - prev) ? curr : prevClose
      );
    });
    setAfterYear(prev => {
      if (availableYears.includes(prev)) return prev;
      return availableYears.reduce((prevClose, curr) => 
        Math.abs(curr - prev) < Math.abs(prevClose - prev) ? curr : prevClose
      );
    });
  }, [availableYears]);
  /* eslint-enable react-hooks/set-state-in-effect */

  const validateFrontendBbox = (minLon: number, minLat: number, maxLon: number, maxLat: number): string | null => {
    if (isNaN(minLon) || isNaN(minLat) || isNaN(maxLon) || isNaN(maxLat)) {
      return "All coordinates must be valid numbers.";
    }
    if (minLon < -180 || minLon > 180 || maxLon < -180 || maxLon > 180) {
      return "Longitude must be between -180 and 180.";
    }
    if (minLat < -90 || minLat > 90 || maxLat < -90 || maxLat > 90) {
      return "Latitude must be between -90 and 90.";
    }
    if (minLon >= maxLon) {
      return "min_lon must be less than max_lon.";
    }
    if (minLat >= maxLat) {
      return "min_lat must be less than max_lat.";
    }
    const area = (maxLon - minLon) * (maxLat - minLat);
    if (area > 0.25) {
      return `Bbox too large (${area.toFixed(3)} deg²). Max supported is 0.25 deg² (~50km x 50km).`;
    }
    if (area < 0.0001) {
      return `Bbox too small (${area.toFixed(6)} deg²). Min supported is 0.0001 deg².`;
    }
    return null;
  };

  const getBboxCacheKey = (minLon: number, minLat: number, maxLon: number, maxLat: number): string => {
    const rounded = [minLon, minLat, maxLon, maxLat].map(x => Number(x.toFixed(3)));
    return `bbox_${rounded[0]}_${rounded[1]}_${rounded[2]}_${rounded[3]}`;
  };

  const handleCoordChange = (field: string, value: string) => {
    const nextCoords = { ...coordsInput, [field]: value };
    setCoordsInput(nextCoords);

    if (nextCoords.minLon && nextCoords.minLat && nextCoords.maxLon && nextCoords.maxLat) {
      const minLon = parseFloat(nextCoords.minLon);
      const minLat = parseFloat(nextCoords.minLat);
      const maxLon = parseFloat(nextCoords.maxLon);
      const maxLat = parseFloat(nextCoords.maxLat);

      const err = validateFrontendBbox(minLon, minLat, maxLon, maxLat);
      setCoordsError(err);
      if (!err) {
        setCustomBbox([minLon, minLat, maxLon, maxLat]);
      }
    } else {
      setCoordsError(null);
    }
  };

  const handleAnalyzeCustomRegion = (minLon: number, minLat: number, maxLon: number, maxLat: number) => {
    const error = validateFrontendBbox(minLon, minLat, maxLon, maxLat);
    if (error) {
      setCoordsError(error);
      return;
    }
    const key = getBboxCacheKey(minLon, minLat, maxLon, maxLat);
    setSelectedZoneKey(key);
    const existingZone = zones.find(z => z.key === key);
    if (existingZone && existingZone.years.length > 0) {
      setBeforeYear(existingZone.years[0]);
      setAfterYear(existingZone.years[existingZone.years.length - 1]);
    } else {
      setBeforeYear(2017);
      setAfterYear(2023);
    }
    setActiveTab("comparison");
  };

  // ---- Fetch zones ----
  useEffect(() => {
    fetch(`${API_ORIGIN}/api/zones`)
      .then(r => { if (!r.ok) throw new Error("Failed to load zone registry"); return r.json(); })
      .then(d => {
        const stored = getStoredCustomZones();
        const uniqueStored = stored.filter(sz => !d.some((z: ZoneData) => z.key === sz.key));
        setZones([...d, ...uniqueStored]);
        setApiWarning(null);
        setZonesError(null);
      })
      .catch((err) => {
        const stored = getStoredCustomZones();
        setZones(stored);
        setZonesError(err.message || "Failed to connect to backend server");
      });
  }, []);

  // ---- Fetch analysis ----
  useEffect(() => {
    if (!selectedZoneKey) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Reset loading state to true synchronously when inputs change to display loading spinner
    setLoadingAnalysis(true);
    setAnalysisError(null);

    let active = true;

    const isCustom = selectedZoneKey.startsWith("bbox_");

    let promise;
    if (isCustom) {
      const parts = selectedZoneKey.split("_");
      const min_lon = parseFloat(parts[1]);
      const min_lat = parseFloat(parts[2]);
      const max_lon = parseFloat(parts[3]);
      const max_lat = parseFloat(parts[4]);

      console.log("Fetching custom bbox analysis:", {
        min_lon,
        min_lat,
        max_lon,
        max_lat,
        years: [beforeYear, afterYear],
        force_refresh: forceRefreshRef.current,
      });

      promise = fetch(`${API_ORIGIN}/api/analyse_bbox`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          min_lon,
          min_lat,
          max_lon,
          max_lat,
          years: [beforeYear, afterYear],
          force_refresh: forceRefreshRef.current,
        }),
      });
    } else {
      promise = fetch(`${API_ORIGIN}/api/analyse?zone=${selectedZoneKey}&before=${beforeYear}&after=${afterYear}&t=${refreshTrigger}`);
    }

    promise
      .then(r => {
        if (!active) return null;
        if (!r.ok) {
          return r.json().then(err => {
            throw new Error(err.detail || "Analysis failed");
          });
        }
        return r.json();
      })
      .then(d => {
        if (!active || !d) return;
        setAnalysis(d);
        setApiWarning(null);

        // Add custom bbox to the zones list if not already present
        if (d.zone_info.key.startsWith("bbox_")) {
          const isForceRefresh = forceRefreshRef.current;
          const newZone: ZoneData = {
            key: d.zone_info.key,
            name: d.zone_info.name,
            bbox: d.zone_info.bbox,
            center: d.zone_info.center,
            latest_grade: d.metrics.grade,
            latest_abi: d.metrics.latest_abi,
            overall_abi_change_pct: d.metrics.overall_abi_change_pct,
            cropland_loss_ha: d.metrics.cropland_loss_ha,
            encroachment_alert: d.metrics.encroachment_alert,
            years: d.zone_info.years,
            satyukt_relevance: d.zone_info.satyukt_relevance,
          };

          // On force refresh: replace years (wipes forecasted years from state + storage)
          // On normal fetch: merge years (preserves previously forecasted years)
          saveCustomZone(newZone, isForceRefresh);

          setZones(prevZones => {
            if (prevZones.some(z => z.key === d.zone_info.key)) {
              return prevZones.map(z => {
                if (z.key === d.zone_info.key) {
                  const finalYears = isForceRefresh
                    ? newZone.years   // replace: back to historical only
                    : Array.from(new Set([...z.years, ...newZone.years])).sort((a, b) => a - b); // merge
                  return { ...z, ...newZone, years: finalYears };
                }
                return z;
              });
            }
            return [...prevZones, newZone];
          });

          // On force refresh, also reset year selectors to the returned historical range
          if (isForceRefresh) {
            setBeforeYear(d.zone_info.years[0]);
            setAfterYear(d.zone_info.years[d.zone_info.years.length - 1]);
          }
        }
      })
      .catch((err) => {
        if (!active) return;
        setAnalysisError(err.message || "Failed to fetch analysis data");
        setAnalysis(null);
      })
      .finally(() => {
        if (!active) return;
        setLoadingAnalysis(false);
        forceRefreshRef.current = false;
      });

    return () => {
      active = false;
    };
  }, [selectedZoneKey, beforeYear, afterYear, refreshTrigger]);

  const handleSelectZone = (key: string) => {
    setSelectedZoneKey(key);
    const z = zones.find(z => z.key === key);
    if (z) { setBeforeYear(z.years[0]); setAfterYear(z.years[z.years.length - 1]); }
    setActiveTab("comparison");
    setVizMode("AI Land Use Classification");
    setSliderValue(50);
    setInputMode("named");
  };

  const handleDeleteCustomZone = (key: string) => {
    if (!key || !key.startsWith("bbox_")) return;

    if (!window.confirm("Are you sure you want to completely delete the data and cache for this custom region?")) {
      return;
    }

    setLoadingAnalysis(true);

    fetch(`${API_ORIGIN}/api/analyse_bbox/${key}`, {
      method: "DELETE",
    })
      .then(res => {
        if (!res.ok) throw new Error("Failed to delete custom region data on backend");
        return res.json();
      })
      .then(() => {
        deleteStoredCustomZone(key);
        setZones(prev => {
          const updated = prev.filter(z => z.key !== key);
          if (updated.length > 0) {
            const nextZone = updated[0];
            setSelectedZoneKey(nextZone.key);
            setBeforeYear(nextZone.years[0]);
            setAfterYear(nextZone.years[nextZone.years.length - 1]);
          } else {
            setSelectedZoneKey(null);
          }
          return updated;
        });
        setAnalysis(null);
        setAnalysisError(null);
        setCustomBbox(null);
      })
      .catch(err => {
        console.error("Failed to delete custom zone:", err);
        alert(`Error deleting custom region: ${err.message || err}`);
      })
      .finally(() => {
        setLoadingAnalysis(false);
      });
  };

  const handleRunCustomForecast = () => {
    if (!selectedZoneKey || !selectedZoneKey.startsWith("bbox_")) return;

    const parts = selectedZoneKey.split("_");
    const min_lon = parseFloat(parts[1]);
    const min_lat = parseFloat(parts[2]);
    const max_lon = parseFloat(parts[3]);
    const max_lat = parseFloat(parts[4]);

    setLoadingForecast(true);
    setLoadingAnalysis(true);
    setAnalysisError(null);

    fetch(`${API_ORIGIN}/api/forecast_bbox`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        min_lon,
        min_lat,
        max_lon,
        max_lat,
        years: [beforeYear, afterYear],
        force_refresh: false,
      }),
    })
      .then(res => {
        if (!res.ok) {
          return res.json().then(err => {
            throw new Error(err.detail || "Forecasting failed");
          });
        }
        return res.json();
      })
      .then(d => {
        setAnalysis(d);
        // Automatically set audited/future year to 2041 to show the forecast immediately
        setBeforeYear(2017);
        setAfterYear(2041);
        
        // Update the zones registry so that the new years list is stored
        setZones(prev => {
          const updated = prev.map(z => {
            if (z.key === selectedZoneKey) {
              return {
                ...z,
                years: d.zone_info.years,
                latest_grade: d.metrics.grade,
                latest_abi: d.metrics.latest_abi,
                overall_abi_change_pct: d.metrics.overall_abi_change_pct,
              };
            }
            return z;
          });
          // Update custom zones storage
          const stored = getStoredCustomZones();
          const updatedStored = stored.map(z => {
            if (z.key === selectedZoneKey) {
              return {
                ...z,
                years: d.zone_info.years,
                latest_grade: d.metrics.grade,
                latest_abi: d.metrics.latest_abi,
                overall_abi_change_pct: d.metrics.overall_abi_change_pct,
              };
            }
            return z;
          });
          localStorage.setItem("farmguard_custom_zones", JSON.stringify(updatedStored));
          return updated;
        });
      })
      .catch(err => {
        console.error("Forecasting failed:", err);
        setAnalysisError(err.message || "Forecasting failed. Try a smaller/different region.");
      })
      .finally(() => {
        setLoadingForecast(false);
        setLoadingAnalysis(false);
      });
  };



  const getOverlayUrl = (which: "before" | "after") => {
    if (!analysis) return null;
    const yr = which === "before" ? beforeYear : afterYear;
    if (yr > 2023 && (vizMode === "True Color Satellite Image" || vizMode === "NDVI Vegetation Map")) {
      return null;
    }
    let url = null;
    if (vizMode === "Infrastructure Encroachment Heatmap") {
      if (which === "before") {
        url = analysis.overlays.before.mask;
      } else {
        url = analysis.overlays.encroachment_heatmap || null;
      }
    } else {
      const ov = analysis.overlays[which];
      if (vizMode === "True Color Satellite Image") url = ov.true_color;
      else if (vizMode === "NDVI Vegetation Map") url = ov.ndvi;
      else url = ov.mask;
    }

    if (url) {
      // Use a dynamic cache buster containing refreshTrigger if it has been activated, allowing manual cache invalidation
      const buster = refreshTrigger > 0
        ? `resnet34_v1_${refreshTrigger}`
        : "resnet34_v1";
      return `${url}?t=${buster}`;
    }
    return url;
  };

  // ============================================================
  // RENDER
  // ============================================================
  return (
    <div
      style={{
        height: "100dvh", maxHeight: "100dvh",
        display: "flex", flexDirection: "column",
        overflow: "hidden", background: "var(--bg-base)",
      }}
      className="bg-grid"
    >
      {/* Scanning line removed */}

      {/* ==================================================
          HEADER
      ================================================== */}
      <header style={{
        flexShrink: 0,
        background: "rgba(250, 250, 249, 0.9)",
        borderBottom: "1px solid var(--border-dim)",
        backdropFilter: "blur(8px)",
        zIndex: 30,
      }}>
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 20px", gap: 16,
        }}>
          {/* Brand */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{
              width: 34, height: 34, borderRadius: 8,
              background: "rgba(5,150,105,0.15)",
              border: "1px solid rgba(5,150,105,0.4)",
              display: "flex", alignItems: "center", justifyContent: "center",
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2" strokeLinecap="round">
                <path d="M12 2L2 7l10 5 10-5-10-5z" />
                <path d="M2 17l10 5 10-5" />
                <path d="M2 12l10 5 10-5" />
              </svg>
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <h1 style={{ fontSize: 17, fontWeight: 800, letterSpacing: "-0.02em", color: "var(--text-primary)", lineHeight: 1 }}>
                  FarmGuard
                </h1>
              </div>
              <p style={{
                marginTop: 2, fontSize: 9, fontFamily: "monospace",
                letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--text-muted)",
              }}>
                Satellite Farmland Encroachment &amp; Environmental Risk System
              </p>
            </div>
          </div>

          {/* Status bar */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            {apiWarning && (
              <div style={{
                display: "flex", alignItems: "center", gap: 6,
                background: "rgba(245,158,11,0.1)", border: "1px solid rgba(245,158,11,0.25)",
                borderRadius: 6, padding: "5px 10px", fontSize: 10, fontFamily: "monospace", color: "var(--amber-400)",
              }}>
                <span className="dot-pulse amber" />
                {apiWarning}
              </div>
            )}
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              background: "rgba(5,150,105,0.08)", border: "1px solid rgba(5,150,105,0.2)",
              borderRadius: 6, padding: "5px 10px", fontSize: 10, fontFamily: "monospace", color: "var(--emerald-400)",
            }}>
              <span className="dot-pulse emerald" />
              SENTINEL-2 L2A ACTIVE
            </div>
          </div>
        </div>
        {/* Header glow line removed */}
      </header>

      {/* ==================================================
          MAIN SPLIT
      ================================================== */}
      <main style={{
        flex: 1, display: "grid",
        gridTemplateColumns: "1fr 460px",
        minHeight: 0, overflow: "hidden",
      }}>

        {/* ================================================
            LEFT — VISUAL WORKSPACE
        ================================================ */}
        <section style={{
          display: "flex", flexDirection: "column",
          position: "relative", minHeight: 0,
          borderRight: "1px solid var(--border-dim)",
          overflow: "hidden",
        }}>
          {/* Tab bar */}
          <div style={{
            position: "absolute", top: 12, left: 12, zIndex: 20,
            display: "flex",
            background: "rgba(250, 250, 249, 0.92)",
            backdropFilter: "blur(10px)",
            border: "1px solid var(--border-dim)",
            borderRadius: 8, padding: 3, gap: 2,
          }}>
            <button className={`tab-btn ${activeTab === "map" ? "active" : ""}`}
              onClick={() => setActiveTab("map")}>
              Region Map
            </button>
            <button
              className={`tab-btn ${activeTab === "comparison" ? "active" : ""}`}
              onClick={() => {
                if (!selectedZoneKey && zones.length > 0) {
                  handleSelectZone(zones[0].key);
                }
                setActiveTab("comparison");
              }}>
              Image Comparison
            </button>
          </div>

          {/* View */}
          <div style={{ flex: 1, position: "relative", minHeight: 0 }}>
            {loadingAnalysis ? (
              <div style={{
                position: "absolute",
                top: 0, left: 0, right: 0, bottom: 0,
                background: "rgba(250, 250, 249, 0.97)",
                display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center",
                gap: 24, zIndex: 100,
                border: "1px dashed rgba(5, 150, 105, 0.15)",
                borderRadius: 8
              }}>
                <div style={{ position: "relative", width: 100, height: 100, display: "flex", alignItems: "center", justifyContent: "center" }}>
                  {/* Radar outer scan line */}
                  <div className="radar-scan-line" style={{
                    position: "absolute",
                    width: 100, height: 100, borderRadius: "50%",
                    border: "2px solid rgba(5, 150, 105, 0.1)",
                    borderTopColor: "var(--emerald-400)",
                  }} />
                  {/* Inner ping ring */}
                  <div className="radar-ping-ring" style={{
                    position: "absolute",
                    width: 70, height: 70, borderRadius: "50%",
                    background: "rgba(5, 150, 105, 0.03)",
                    border: "1px dashed rgba(5, 150, 105, 0.2)",
                  }} />
                  {/* Center glowing green dot representing the satellite pin */}
                  <div style={{
                    width: 12, height: 12, borderRadius: "50%",
                    background: "var(--emerald-400)",
                    zIndex: 2,
                  }} />
                </div>
                
                <div style={{ textAlign: "center" }}>
                  <h3 style={{
                    fontSize: 13, fontWeight: 700,
                    color: "var(--text-primary)", margin: "0 0 6px 0",
                    fontFamily: "monospace", letterSpacing: "0.15em",
                    textTransform: "uppercase"
                  }}>
                    Telemetry Acquisition Active
                  </h3>
                  <p className="radar-text-pulse" style={{
                    fontSize: 10, color: "var(--text-secondary)",
                    margin: 0, fontFamily: "monospace"
                  }}>
                    {selectedZoneKey && selectedZoneKey.startsWith("bbox_") 
                      ? "Ingesting Sentinel-2 satellite imagery & land cover tiles..." 
                      : "Retrieving precomputed regional analytics & overlays..."
                    }
                  </p>
                </div>
              </div>
            ) : activeTab === "map" ? (
              <LeafletMap
                zones={zones}
                selectedZoneKey={selectedZoneKey}
                onSelectZone={handleSelectZone}
                inputMode={inputMode}
                drawnBbox={customBbox}
                onDrawComplete={(bbox) => {
                  setCustomBbox(bbox);
                  if (bbox) {
                    setCoordsInput({
                      minLon: bbox[0].toFixed(6),
                      minLat: bbox[1].toFixed(6),
                      maxLon: bbox[2].toFixed(6),
                      maxLat: bbox[3].toFixed(6),
                    });
                    setCoordsError(null);
                  }
                }}
              />
            ) : (
              <SliderComparison
                beforeImageUrl={getOverlayUrl("before")}
                afterImageUrl={getOverlayUrl("after")}
                beforeYear={beforeYear}
                afterYear={afterYear}
                isMask={vizMode === "AI Land Use Classification" || vizMode === "Infrastructure Encroachment Heatmap"}
                sliderValue={sliderValue}
                onSliderChange={setSliderValue}
                showSlider={vizMode !== "Infrastructure Encroachment Heatmap"}
                isMock={analysis?.is_mock || false}
                vizMode={vizMode}
              />
            )}
          </div>
        </section>

        {/* ================================================
            RIGHT — SIDEBAR
        ================================================ */}
        <section style={{
          display: "flex", flexDirection: "column",
          background: "var(--bg-surface)", overflow: "hidden", minHeight: 0,
        }}>
          {/* Setup panel — hidden in comparison mode */}
          {activeTab === "map" && (
          <div style={{
            flexShrink: 0, padding: "18px 18px 14px",
            borderBottom: "1px solid var(--border-dim)",
          }}>
            <p className="section-label" style={{ marginBottom: 14 }}>Analysis Setup</p>

            {/* Mode selection toggle */}
            <div style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr 1fr",
              background: "rgba(15, 23, 42, 0.05)",
              border: "1px solid var(--border-dim)",
              borderRadius: 8,
              padding: 3,
              gap: 4,
              marginBottom: 14,
            }}>
              <button
                className={`tab-btn ${inputMode === "named" ? "active" : ""}`}
                style={{ fontSize: 10, padding: "6px 2px", textAlign: "center" }}
                onClick={() => setInputMode("named")}
              >
                Named Zone
              </button>
              <button
                className={`tab-btn ${inputMode === "draw" ? "active" : ""}`}
                style={{ fontSize: 10, padding: "6px 2px", textAlign: "center" }}
                onClick={() => setInputMode("draw")}
              >
                Draw on Map
              </button>
              <button
                className={`tab-btn ${inputMode === "coords" ? "active" : ""}`}
                style={{ fontSize: 10, padding: "6px 2px", textAlign: "center" }}
                onClick={() => setInputMode("coords")}
              >
                Coordinates
              </button>
            </div>

            {/* Zone selector */}
            {inputMode === "named" && (
              <div style={{ marginBottom: 12 }}>
                <label htmlFor="zone-select" className="section-label"
                  style={{ display: "block", marginBottom: 6, color: "var(--text-secondary)" }}>
                  Target Buffer Zone
                </label>
                {zonesError ? (
                  <div className="glass-card" style={{ padding: "8px 12px", border: "1px solid rgba(220, 38, 38, 0.25)", background: "var(--red-dim)", borderRadius: 8, marginBottom: 8 }}>
                    <p style={{ color: "var(--red-500)", fontSize: 11, margin: 0, fontFamily: "monospace" }}>
                      ⚠️ Error: {zonesError}
                    </p>
                  </div>
                ) : (
                  <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                    <select id="zone-select" value={selectedZoneKey || ""}
                      onChange={e => handleSelectZone(e.target.value)}
                      style={{ flex: 1 }}>
                      <option value="" disabled>Select a Region…</option>
                      {zones.map(z => <option key={z.key} value={z.key}>{z.name}</option>)}
                    </select>
                    {selectedZoneKey && (
                      <>
                        <button
                          title={selectedZoneKey.startsWith("bbox_") ? "Re-analyze this custom bounding box" : "Refresh map data and bust cache"}
                          disabled={loadingAnalysis}
                          onClick={() => {
                            setLoadingAnalysis(true);
                            forceRefreshRef.current = true;
                            setRefreshTrigger(prev => prev + 1);
                          }}
                          style={{
                            background: "var(--emerald-dim)",
                            border: "1px solid var(--border-active)",
                            borderRadius: 8,
                            padding: "8px 10px",
                            color: "var(--emerald-400)",
                            cursor: "pointer",
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            opacity: loadingAnalysis ? 0.5 : 1,
                            height: 35,
                            width: 36,
                            flexShrink: 0,
                            transition: "all 0.15s ease",
                          }}
                        >
                          {loadingAnalysis ? (
                            <div style={{
                              width: 14, height: 14, borderRadius: "50%",
                              border: "1.5px solid var(--border-dim)",
                              borderTopColor: "var(--emerald-400)",
                              animation: "spin 0.8s linear infinite"
                            }} />
                          ) : (
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                            </svg>
                          )}
                        </button>
                        {selectedZoneKey.startsWith("bbox_") && (
                          <button
                            title="Delete this custom bounding box data"
                            disabled={loadingAnalysis}
                            onClick={() => handleDeleteCustomZone(selectedZoneKey)}
                            style={{
                              background: "rgba(220, 38, 38, 0.05)",
                              border: "1px solid rgba(220, 38, 38, 0.22)",
                              borderRadius: 8,
                              padding: "8px 10px",
                              color: "var(--red-400)",
                              cursor: "pointer",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              opacity: loadingAnalysis ? 0.5 : 1,
                              height: 35,
                              width: 36,
                              flexShrink: 0,
                              transition: "all 0.15s ease",
                            }}
                          >
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                              <polyline points="3 6 5 6 21 6" />
                              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                              <line x1="10" y1="11" x2="10" y2="17" />
                              <line x1="14" y1="11" x2="14" y2="17" />
                            </svg>
                          </button>
                        )}
                      </>
                    )}
                  </div>
                )}

                {analysis?.is_mock && (
                  <div className="glass-card animate-pulse" style={{
                    marginTop: 8,
                    padding: "8px 12px",
                    border: "1px solid rgba(217, 119, 6, 0.25)",
                    background: "rgba(217, 119, 6, 0.05)",
                    borderRadius: 8,
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                  }}>
                    <span className="dot-pulse amber" style={{ width: 8, height: 8 }} />
                    <span style={{ fontSize: 10, color: "#b45309", fontWeight: 700, fontFamily: "monospace", letterSpacing: "0.02em" }}>
                      SIMULATED DATA ACTIVE
                    </span>
                  </div>
                )}
              </div>
            )}

            {inputMode === "draw" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 12 }}>
                {!customBbox ? (
                  <div className="glass-card" style={{ padding: "10px 12px", border: "1px dashed var(--border-dim)", borderRadius: 8 }}>
                    <p style={{ fontSize: 11, color: "var(--text-secondary)", margin: 0 }}>
                      📍 Switch to the <strong>Region Map</strong> tab and drag a rectangle on the map to draw your region.
                    </p>
                  </div>
                ) : (
                  <div className="glass-card" style={{ padding: "10px 12px", borderRadius: 8, display: "flex", flexDirection: "column", gap: 8 }}>
                    <p style={{ fontSize: 11, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
                      ✅ Region Captured:
                    </p>
                    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6, fontSize: 9, fontFamily: "monospace", color: "var(--text-secondary)" }}>
                      <div>Min Lon: {customBbox[0].toFixed(4)}</div>
                      <div>Min Lat: {customBbox[1].toFixed(4)}</div>
                      <div>Max Lon: {customBbox[2].toFixed(4)}</div>
                      <div>Max Lat: {customBbox[3].toFixed(4)}</div>
                    </div>
                    <div style={{ fontSize: 10, fontFamily: "monospace", color: "var(--emerald-400)", borderTop: "1px dashed var(--border-dim)", paddingTop: 6, marginTop: 2 }}>
                      Estimated Area: {getBboxPhysicalArea(customBbox[0], customBbox[1], customBbox[2], customBbox[3])}
                    </div>
                    {coordsError && (
                      <p style={{ color: "var(--red-400)", fontSize: 10, margin: 0, fontFamily: "monospace" }}>
                        ⚠️ {coordsError}
                      </p>
                    )}
                    <div style={{ display: "flex", gap: 6, marginTop: 4 }}>
                      <button
                        className="tab-btn active"
                        style={{ flex: 1, padding: "6px", borderRadius: 6, fontSize: 10, fontWeight: 700 }}
                        disabled={!!coordsError}
                        onClick={() => handleAnalyzeCustomRegion(customBbox[0], customBbox[1], customBbox[2], customBbox[3])}
                      >
                        Analyze Bbox
                      </button>
                      <button
                        className="tab-btn"
                        style={{ padding: "6px 10px", borderRadius: 6, fontSize: 10, borderColor: "var(--red-400)", color: "var(--red-400)" }}
                        onClick={() => {
                          setCustomBbox(null);
                          setCoordsInput({ minLon: "", minLat: "", maxLon: "", maxLat: "" });
                          setCoordsError(null);
                        }}
                      >
                        Clear
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {inputMode === "coords" && (
              <div style={{ display: "flex", flexDirection: "column", gap: 10, marginBottom: 12 }}>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div>
                    <label className="section-label" style={{ display: "block", marginBottom: 4, color: "var(--text-secondary)" }}>Min Longitude</label>
                    <input
                      type="number"
                      step="any"
                      placeholder="e.g. 73.75"
                      value={coordsInput.minLon}
                      onChange={e => handleCoordChange("minLon", e.target.value)}
                      style={{ width: "100%", padding: "6px 10px", background: "var(--bg-base)", border: "1px solid var(--border-dim)", borderRadius: 6, color: "var(--text-primary)", fontSize: 12 }}
                    />
                  </div>
                  <div>
                    <label className="section-label" style={{ display: "block", marginBottom: 4, color: "var(--text-secondary)" }}>Min Latitude</label>
                    <input
                      type="number"
                      step="any"
                      placeholder="e.g. 20.08"
                      value={coordsInput.minLat}
                      onChange={e => handleCoordChange("minLat", e.target.value)}
                      style={{ width: "100%", padding: "6px 10px", background: "var(--bg-base)", border: "1px solid var(--border-dim)", borderRadius: 6, color: "var(--text-primary)", fontSize: 12 }}
                    />
                  </div>
                  <div>
                    <label className="section-label" style={{ display: "block", marginBottom: 4, color: "var(--text-secondary)" }}>Max Longitude</label>
                    <input
                      type="number"
                      step="any"
                      placeholder="e.g. 73.85"
                      value={coordsInput.maxLon}
                      onChange={e => handleCoordChange("maxLon", e.target.value)}
                      style={{ width: "100%", padding: "6px 10px", background: "var(--bg-base)", border: "1px solid var(--border-dim)", borderRadius: 6, color: "var(--text-primary)", fontSize: 12 }}
                    />
                  </div>
                  <div>
                    <label className="section-label" style={{ display: "block", marginBottom: 4, color: "var(--text-secondary)" }}>Max Latitude</label>
                    <input
                      type="number"
                      step="any"
                      placeholder="e.g. 20.15"
                      value={coordsInput.maxLat}
                      onChange={e => handleCoordChange("maxLat", e.target.value)}
                      style={{ width: "100%", padding: "6px 10px", background: "var(--bg-base)", border: "1px solid var(--border-dim)", borderRadius: 6, color: "var(--text-primary)", fontSize: 12 }}
                    />
                  </div>
                </div>

                {coordsError && (
                  <p style={{ color: "var(--red-400)", fontSize: 10, margin: 0, fontFamily: "monospace" }}>
                    ⚠️ {coordsError}
                  </p>
                )}

                {!coordsError && coordsInput.minLon && coordsInput.minLat && coordsInput.maxLon && coordsInput.maxLat && (
                  <div style={{ fontSize: 10, fontFamily: "monospace", color: "var(--emerald-400)", borderTop: "1px dashed var(--border-dim)", paddingTop: 6, marginTop: 2, marginBottom: 2 }}>
                    Estimated Area: {getBboxPhysicalArea(
                      parseFloat(coordsInput.minLon),
                      parseFloat(coordsInput.minLat),
                      parseFloat(coordsInput.maxLon),
                      parseFloat(coordsInput.maxLat)
                    )}
                  </div>
                )}

                <button
                  className="tab-btn active"
                  style={{ width: "100%", padding: "8px", borderRadius: 6, fontSize: 11, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em" }}
                  disabled={!!coordsError || !coordsInput.minLon || !coordsInput.minLat || !coordsInput.maxLon || !coordsInput.maxLat}
                  onClick={() => {
                    const minLon = parseFloat(coordsInput.minLon);
                    const minLat = parseFloat(coordsInput.minLat);
                    const maxLon = parseFloat(coordsInput.maxLon);
                    const maxLat = parseFloat(coordsInput.maxLat);
                    handleAnalyzeCustomRegion(minLon, minLat, maxLon, maxLat);
                  }}
                >
                  Analyze Coordinates
                </button>
              </div>
            )}

            {(currentZone || (selectedZoneKey && selectedZoneKey.startsWith("bbox_"))) && (<>
              {/* Year selectors */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
                <div>
                  <label htmlFor="before-yr" className="section-label"
                    style={{ display: "block", marginBottom: 6, color: "var(--text-secondary)" }}>
                    Baseline Year
                  </label>
                  <select id="before-yr" value={beforeYear} onChange={e => setBeforeYear(Number(e.target.value))}>
                    {availableYears.map(yr => <option key={yr} value={yr} disabled={yr >= afterYear}>{yr}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor="after-yr" className="section-label"
                    style={{ display: "block", marginBottom: 6, color: "var(--text-secondary)" }}>
                    Audited Year
                  </label>
                  <select id="after-yr" value={afterYear} onChange={e => setAfterYear(Number(e.target.value))}>
                    {availableYears.map(yr => <option key={yr} value={yr} disabled={yr <= beforeYear}>{yr}</option>)}
                  </select>
                </div>
              </div>

              {/* Viz mode */}
              <div style={{ marginBottom: 12 }}>
                <label htmlFor="viz-mode" className="section-label"
                  style={{ display: "block", marginBottom: 6, color: "var(--text-secondary)" }}>
                  Raster Overlay Mode
                </label>
                <select id="viz-mode" value={vizMode} onChange={e => setVizMode(e.target.value)}>
                  <option value="AI Land Use Classification">AI Land Use Classification</option>
                  <option value="True Color Satellite Image">True Color Satellite Image</option>
                  <option value="NDVI Vegetation Map">NDVI Vegetation Map</option>
                  <option value="Infrastructure Encroachment Heatmap">Infrastructure Encroachment Heatmap</option>
                </select>
              </div>
            </>)}
          </div>
          )}

          {/* Metrics panel — only shown in Image Comparison mode */}
          {activeTab === "comparison" && (
          <div style={{ flex: 1, overflowY: "auto", padding: "18px 18px" }}>

            {/* Compact comparison-mode controls — shown only in Image Comparison tab */}
            {activeTab === "comparison" && (
              <div style={{
                marginBottom: 14,
                padding: "12px 14px",
                background: "rgba(5, 150, 105, 0.04)",
                border: "1px solid var(--border-dim)",
                borderRadius: 10,
                display: "flex",
                flexDirection: "column",
                gap: 10,
              }}>

                {/* Zone selector + actions */}
                <div>
                  <label htmlFor="cmp-zone-select" className="section-label"
                    style={{ display: "block", marginBottom: 6, color: "var(--text-secondary)" }}>
                    Target Region
                  </label>
                  {zonesError ? (
                    <div className="glass-card" style={{ padding: "8px 12px", border: "1px solid rgba(220, 38, 38, 0.25)", background: "var(--red-dim)", borderRadius: 8 }}>
                      <p style={{ color: "var(--red-500)", fontSize: 11, margin: 0, fontFamily: "monospace" }}>
                        ⚠️ {zonesError}
                      </p>
                    </div>
                  ) : (
                    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
                      <select id="cmp-zone-select" value={selectedZoneKey || ""}
                        onChange={e => handleSelectZone(e.target.value)}
                        style={{ flex: 1 }}>
                        <option value="" disabled>Select a Region…</option>
                        {zones.map(z => <option key={z.key} value={z.key}>{z.name}</option>)}
                      </select>
                      {selectedZoneKey && (
                        <>
                          {/* Refresh / re-analyze */}
                          <button
                            title={selectedZoneKey.startsWith("bbox_") ? "Re-analyze this custom bounding box" : "Refresh map data and bust cache"}
                            disabled={loadingAnalysis}
                            onClick={() => {
                              setLoadingAnalysis(true);
                              forceRefreshRef.current = true;
                              setRefreshTrigger(prev => prev + 1);
                            }}
                            style={{
                              background: "var(--emerald-dim)",
                              border: "1px solid var(--border-active)",
                              borderRadius: 8,
                              padding: "8px 10px",
                              color: "var(--emerald-400)",
                              cursor: "pointer",
                              display: "flex", alignItems: "center", justifyContent: "center",
                              opacity: loadingAnalysis ? 0.5 : 1,
                              height: 35, width: 36, flexShrink: 0,
                              transition: "all 0.15s ease",
                            }}
                          >
                            {loadingAnalysis ? (
                              <div style={{
                                width: 14, height: 14, borderRadius: "50%",
                                border: "1.5px solid var(--border-dim)",
                                borderTopColor: "var(--emerald-400)",
                                animation: "spin 0.8s linear infinite"
                              }} />
                            ) : (
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
                              </svg>
                            )}
                          </button>
                          {/* Delete (custom bbox only) */}
                          {selectedZoneKey.startsWith("bbox_") && (
                            <button
                              title="Delete this custom bounding box data"
                              disabled={loadingAnalysis}
                              onClick={() => handleDeleteCustomZone(selectedZoneKey)}
                              style={{
                                background: "rgba(220, 38, 38, 0.05)",
                                border: "1px solid rgba(220, 38, 38, 0.22)",
                                borderRadius: 8,
                                padding: "8px 10px",
                                color: "var(--red-400)",
                                cursor: "pointer",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                opacity: loadingAnalysis ? 0.5 : 1,
                                height: 35, width: 36, flexShrink: 0,
                                transition: "all 0.15s ease",
                              }}
                            >
                              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                                <polyline points="3 6 5 6 21 6" />
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                                <line x1="10" y1="11" x2="10" y2="17" />
                                <line x1="14" y1="11" x2="14" y2="17" />
                              </svg>
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  )}
                  {analysis?.is_mock && (
                    <div className="glass-card animate-pulse" style={{
                      marginTop: 8, padding: "8px 12px",
                      border: "1px solid rgba(217, 119, 6, 0.25)",
                      background: "rgba(217, 119, 6, 0.05)",
                      borderRadius: 8, display: "flex", alignItems: "center", gap: 8,
                    }}>
                      <span className="dot-pulse amber" style={{ width: 8, height: 8 }} />
                      <span style={{ fontSize: 10, color: "#b45309", fontWeight: 700, fontFamily: "monospace", letterSpacing: "0.02em" }}>
                        SIMULATED DATA ACTIVE
                      </span>
                    </div>
                  )}
                </div>

                {/* Year selectors — only when a zone is selected */}
                {selectedZoneKey && (<>
                {/* Year selectors row */}

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div>
                    <label htmlFor="cmp-before-yr" className="section-label"
                      style={{ display: "block", marginBottom: 4, color: "var(--text-secondary)", fontSize: 9 }}>
                      Baseline Year
                    </label>
                    <select id="cmp-before-yr" value={beforeYear} onChange={e => setBeforeYear(Number(e.target.value))}
                      style={{ fontSize: 11, padding: "5px 8px" }}>
                      {availableYears.map(yr => <option key={yr} value={yr} disabled={yr >= afterYear}>{yr}</option>)}
                    </select>
                  </div>
                  <div>
                    <label htmlFor="cmp-after-yr" className="section-label"
                      style={{ display: "block", marginBottom: 4, color: "var(--text-secondary)", fontSize: 9 }}>
                      Audited Year
                    </label>
                    <select id="cmp-after-yr" value={afterYear} onChange={e => setAfterYear(Number(e.target.value))}
                      style={{ fontSize: 11, padding: "5px 8px" }}>
                      {availableYears.map(yr => <option key={yr} value={yr} disabled={yr <= beforeYear}>{yr}</option>)}
                    </select>
                  </div>
                </div>

                {/* Viz mode selector */}
                <div>
                  <label htmlFor="cmp-viz-mode" className="section-label"
                    style={{ display: "block", marginBottom: 4, color: "var(--text-secondary)", fontSize: 9 }}>
                    Overlay Mode
                  </label>
                  <select id="cmp-viz-mode" value={vizMode} onChange={e => setVizMode(e.target.value)}
                    style={{ fontSize: 11, padding: "5px 8px", width: "100%" }}>
                    <option value="AI Land Use Classification">AI Land Use Classification</option>
                    <option value="True Color Satellite Image">True Color Satellite Image</option>
                    <option value="NDVI Vegetation Map">NDVI Vegetation Map</option>
                    <option value="Infrastructure Encroachment Heatmap">Infrastructure Encroachment Heatmap</option>
                  </select>
                </div>

                {/* Forecast button — shown when custom bbox has no future years predicted yet */}
                {selectedZoneKey && selectedZoneKey.startsWith("bbox_") && !availableYears.some(yr => yr > 2023) && (
                  <button
                    onClick={handleRunCustomForecast}
                    disabled={loadingForecast || loadingAnalysis}
                    style={{
                      width: "100%",
                      padding: "10px 14px",
                      background: "linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.2) 100%)",
                      border: "1px solid rgba(16, 185, 129, 0.35)",
                      borderRadius: 8,
                      color: "var(--emerald-400)",
                      fontFamily: "monospace",
                      fontWeight: 700,
                      fontSize: 11,
                      textTransform: "uppercase",
                      letterSpacing: "0.06em",
                      cursor: "pointer",
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      gap: 8,
                      transition: "all 0.2s ease",
                      opacity: (loadingForecast || loadingAnalysis) ? 0.6 : 1,
                      boxShadow: "0 0 12px rgba(16, 185, 129, 0.05)",
                    }}
                    onMouseEnter={(e) => {
                      if (!loadingForecast && !loadingAnalysis) {
                        e.currentTarget.style.background = "linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.3) 100%)";
                        e.currentTarget.style.borderColor = "var(--emerald-400)";
                        e.currentTarget.style.boxShadow = "0 0 16px rgba(16, 185, 129, 0.15)";
                      }
                    }}
                    onMouseLeave={(e) => {
                      if (!loadingForecast && !loadingAnalysis) {
                        e.currentTarget.style.background = "linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.2) 100%)";
                        e.currentTarget.style.borderColor = "rgba(16, 185, 129, 0.35)";
                        e.currentTarget.style.boxShadow = "0 0 12px rgba(16, 185, 129, 0.05)";
                      }
                    }}
                  >
                    {loadingForecast ? (
                      <>
                        <div style={{
                          width: 12, height: 12, borderRadius: "50%",
                          border: "1.5px solid var(--border-dim)",
                          borderTopColor: "var(--emerald-400)",
                          animation: "spin 0.8s linear infinite"
                        }} />
                        Predicting up to 2041...
                      </>
                    ) : (
                      <><span>🔮</span> Predict Future Years (to 2041)</>
                    )}
                  </button>
                )}
                </>)}
              </div>
            )}

            {analysisError ? (
              <div style={{
                display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center",
                height: "100%", gap: 12, textAlign: "center",
                padding: 16,
              }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: "rgba(220,38,38,0.1)", border: "1px solid rgba(220,38,38,0.25)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="1.5">
                    <circle cx="12" cy="12" r="10" />
                    <line x1="12" y1="8" x2="12" y2="12" />
                    <line x1="12" y1="16" x2="12.01" y2="16" />
                  </svg>
                </div>
                <p className="section-label" style={{ color: "var(--red-400)", fontWeight: 700, margin: 0 }}>
                  Analysis Failed
                </p>
                <p style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.6, margin: 0 }}>
                  {analysisError}
                </p>
              </div>
            ) : !selectedZoneKey ? (
              <div style={{
                display: "flex", flexDirection: "column",
                alignItems: "center", justifyContent: "center",
                height: "100%", gap: 12, textAlign: "center",
              }}>
                <div style={{
                  width: 48, height: 48, borderRadius: 12,
                  background: "var(--emerald-dim)", border: "1px solid rgba(5,150,105,0.25)",
                  display: "flex", alignItems: "center", justifyContent: "center",
                }}>
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="1.5">
                    <circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" />
                  </svg>
                </div>
                <p className="section-label" style={{ maxWidth: 220, lineHeight: 1.8, color: "var(--text-muted)" }}>
                  Select a farmland region or click a zone pin on the map to begin risk analysis
                </p>
              </div>
            ) : loadingAnalysis ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                <div className="skeleton" style={{ height: 86, borderRadius: 10 }} />
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div className="skeleton" style={{ height: 76, borderRadius: 10 }} />
                  <div className="skeleton" style={{ height: 76, borderRadius: 10 }} />
                  <div className="skeleton" style={{ height: 76, borderRadius: 10 }} />
                  <div className="skeleton" style={{ height: 76, borderRadius: 10 }} />
                  <div className="skeleton" style={{ height: 56, borderRadius: 10, gridColumn: "1 / -1" }} />
                </div>
                <div className="skeleton" style={{ height: 52, borderRadius: 10 }} />
                <div className="skeleton" style={{ height: 110, borderRadius: 10 }} />
                <div className="skeleton" style={{ height: 110, borderRadius: 10 }} />
              </div>
            ) : analysis ? (
              <div className="fade-in" style={{ display: "flex", flexDirection: "column", gap: 14 }}>

                {/* Zone header */}
                <div className="glass-card" style={{
                  padding: "14px 16px",
                  borderColor: (analysis.metrics.grade === "F" || analysis.metrics.grade === "C") ? "rgba(220,38,38,0.3)" : "rgba(5,150,105,0.25)",
                }}>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 10 }}>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <h3 style={{
                        fontSize: 12, fontWeight: 800, fontFamily: "monospace",
                        textTransform: "uppercase", letterSpacing: "0.06em",
                        color: "var(--text-primary)",
                        overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                      }}>{analysis.zone_info.name}</h3>
                      <p style={{
                        marginTop: 4, fontSize: 9, fontFamily: "monospace",
                        color: "var(--text-muted)", lineHeight: 1.6,
                      }}>{analysis.zone_info.satyukt_relevance}</p>
                    </div>
                    <div className={`grade-badge ${gradeClass(analysis.metrics.grade)}`}>
                      {analysis.metrics.grade}
                    </div>
                  </div>
                  <div style={{ marginTop: 12, display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {(analysis.metrics.grade === "F" || analysis.metrics.grade === "C") ? (
                      <span className="badge-alert"><span className="dot-pulse red" />Encroachment Alert</span>
                    ) : (
                      <span className="badge-stable"><span className="dot-pulse emerald" />Buffer Stable</span>
                    )}
                    <span className="badge-neutral">{beforeYear} → {afterYear}</span>
                    <span className="badge-neutral">{analysis.metrics.label}</span>
                  </div>
                </div>

                {/* KPI cards */}
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div className="metric-card">
                    <span className="section-label" style={{ display: "block", marginBottom: 6 }}>
                      ABI Ratio ({afterYear})
                    </span>
                    <span style={{
                      display: "block", fontSize: 22, fontWeight: 900, fontFamily: "monospace",
                      letterSpacing: "-0.02em",
                      color: analysis.metrics.latest_abi < 0.3 ? "var(--red-400)"
                        : analysis.metrics.latest_abi < 0.5 ? "var(--amber-400)" : "var(--emerald-400)",
                    }}>{analysis.metrics.latest_abi.toFixed(3)}</span>
                    <span style={{ fontSize: 9, fontFamily: "monospace", color: "var(--text-muted)" }}>warn &lt;0.5 · critical &lt;0.3</span>
                  </div>

                  <div className="metric-card">
                    <span className="section-label" style={{ display: "block", marginBottom: 6 }}>Net Cropland Change</span>
                    <span style={{
                      display: "block", fontSize: 22, fontWeight: 900, fontFamily: "monospace",
                      color: "var(--red-400)", letterSpacing: "-0.02em",
                    }}>
                      {analysis.metrics.cropland_loss_ha.toLocaleString()}
                      <span style={{ fontSize: 12 }}> ha</span>
                    </span>
                    <span style={{ fontSize: 9, fontFamily: "monospace", color: "var(--text-muted)" }}>net loss/gain since 2017</span>
                  </div>

                  {analysis.metrics.encroachment && (
                    <>
                      <div className="metric-card">
                        <span className="section-label" style={{ display: "block", marginBottom: 6 }}>🚜 Cropland Built Over</span>
                        <span style={{
                          display: "block", fontSize: 22, fontWeight: 900, fontFamily: "monospace",
                          color: "var(--red-400)", letterSpacing: "-0.02em",
                        }}>
                          {analysis.metrics.encroachment.total_cropland_lost_ha.toLocaleString()}
                          <span style={{ fontSize: 12 }}> ha</span>
                        </span>
                        <span style={{ fontSize: 9, fontFamily: "monospace", color: "var(--text-muted)" }}>paved over by infrastructure</span>
                      </div>

                      <div className="metric-card">
                        <span className="section-label" style={{ display: "block", marginBottom: 6 }}>💧 Water Paved Over</span>
                        <span style={{
                          display: "block", fontSize: 22, fontWeight: 900, fontFamily: "monospace",
                          color: "var(--sky-400)", letterSpacing: "-0.02em",
                        }}>
                          {analysis.metrics.encroachment.total_water_lost_ha.toLocaleString()}
                          <span style={{ fontSize: 12 }}> ha</span>
                        </span>
                        <span style={{ fontSize: 9, fontFamily: "monospace", color: "var(--text-muted)" }}>filled/paved over by buildings</span>
                      </div>
                    </>
                  )}

                  <div className="metric-card" style={{ gridColumn: "1 / -1" }}>
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <div>
                        <span className="section-label" style={{ display: "block", marginBottom: 3 }}>
                          Buffer Change ({beforeYear} vs {afterYear})
                        </span>
                        <span style={{ fontSize: 10, fontFamily: "monospace", color: "var(--text-secondary)", fontWeight: 600 }}>
                          Overall ABI Shift
                        </span>
                      </div>
                      <span style={{
                        fontSize: 20, fontWeight: 900, fontFamily: "monospace",
                        color: analysis.comparison.abi_change_pct < 0 ? "var(--red-400)" : "var(--emerald-400)",
                      }}>
                        {analysis.comparison.abi_change_pct > 0 ? "+" : ""}
                        {analysis.comparison.abi_change_pct}%
                      </span>
                    </div>
                  </div>
                </div>

                {/* Description */}
                <div className="glass-card" style={{ padding: "10px 14px", fontSize: 11, lineHeight: 1.7, color: "var(--text-secondary)", fontStyle: "italic" }}>
                  &ldquo;{analysis.metrics.description}&rdquo;
                </div>

                {/* Trend chart */}
                <motion.div
                  layoutId="line-chart-card"
                  onClick={() => setExpandedChart("line")}
                  whileHover={{ scale: 1.02, y: -2 }}
                  whileTap={{ scale: 0.98 }}
                  className="glass-card"
                  style={{ padding: "12px 14px", cursor: "pointer" }}
                >
                  <span className="section-label" style={{ display: "block", marginBottom: 8 }}>
                    ABI Ratio Trend Timeline
                  </span>
                  <LineChart data={analysis.timeseries} beforeYear={beforeYear} afterYear={afterYear} />
                </motion.div>

                <motion.div
                  layoutId="encroachment-chart-card"
                  onClick={() => setExpandedChart("encroachment")}
                  whileHover={{ scale: 1.02, y: -2 }}
                  whileTap={{ scale: 0.98 }}
                  className="glass-card"
                  style={{ padding: "12px 14px", cursor: "pointer" }}
                >
                  <span className="section-label" style={{ display: "block", marginBottom: 8 }}>
                    Farmland & Water vs. Built-up Timeline
                  </span>
                  <EncroachmentChart data={analysis.timeseries} />
                </motion.div>

                {/* Land cover transitions */}
                <div className="glass-card" style={{ overflow: "hidden" }}>
                  <div style={{
                    padding: "10px 14px", borderBottom: "1px solid var(--border-dim)",
                    display: "flex", justifyContent: "space-between", alignItems: "center",
                  }}>
                    <span className="section-label">Land Cover Shifts</span>
                    <span className="section-label">{beforeYear} vs {afterYear}</span>
                  </div>
                  {analysis.transitions.map(t => (
                    <div key={t.class_name} className="transition-row">
                      <div style={{ display: "flex", alignItems: "center", gap: 8, flex: 1, minWidth: 0 }}>
                        <span style={{
                          width: 8, height: 8, borderRadius: 2, flexShrink: 0,
                          background: CLASS_COLORS[t.class_name] || "#475569",
                        }} />
                        <span style={{
                          fontSize: 11, fontWeight: 600, color: "var(--text-primary)",
                          overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                        }}>{t.class_name}</span>
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 10, fontFamily: "monospace", flexShrink: 0 }}>
                        <span style={{ fontSize: 10, color: "var(--text-muted)" }}>{t.before_pct.toFixed(1)}%</span>
                        <span style={{ fontSize: 9, color: "var(--text-label)" }}>→</span>
                        <span style={{ fontSize: 10, fontWeight: 700, color: "var(--text-primary)" }}>{t.after_pct.toFixed(1)}%</span>
                        <span style={{
                          fontSize: 10, fontWeight: 800, minWidth: 40, textAlign: "right",
                          color: t.trend_shift_pct > 0.1 ? "var(--emerald-400)"
                            : t.trend_shift_pct < -0.1 ? "var(--red-400)"
                            : "var(--text-muted)",
                        }}>
                          {t.trend_shift_pct > 0 ? "+" : ""}{t.trend_shift_pct.toFixed(1)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </div>

                <div style={{ height: 8 }} />
              </div>
            ) : null}
          </div>
          )}
        </section>
      </main>

      {/* Expanded Chart Lightbox Overlay */}
      <AnimatePresence>
        {expandedChart && analysis && (
          <>
            {/* Backdrop */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => setExpandedChart(null)}
              style={{
                position: "fixed",
                inset: 0,
                background: "rgba(15, 23, 42, 0.4)",
                backdropFilter: "blur(12px)",
                zIndex: 999,
                cursor: "pointer",
              }}
            />

            {/* Modal */}
            <div
              style={{
                position: "fixed",
                inset: 0,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                zIndex: 1000,
                pointerEvents: "none",
              }}
            >
              <motion.div
                layoutId={expandedChart === "line" ? "line-chart-card" : "encroachment-chart-card"}
                style={{
                  pointerEvents: "auto",
                  width: "95%",
                  maxWidth: 860,
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border-dim)",
                  borderRadius: 16,
                  padding: "32px 36px",
                  boxShadow: "0 20px 40px -15px rgba(15, 23, 42, 0.15), 0 0 0 1px rgba(15, 23, 42, 0.05)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 16,
                }}
              >
                {/* Header */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="section-label" style={{ fontSize: 13, letterSpacing: "0.06em", color: "var(--text-primary)" }}>
                    {expandedChart === "line" ? "ABI Ratio Trend Timeline" : "Farmland & Water vs. Built-up Timeline"}
                  </span>
                  <button
                    onClick={() => setExpandedChart(null)}
                    style={{
                      background: "rgba(15, 23, 42, 0.05)",
                      border: "1px solid var(--border-dim)",
                      color: "var(--text-secondary)",
                      borderRadius: "50%",
                      width: 28,
                      height: 28,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      cursor: "pointer",
                    }}
                  >
                    ✕
                  </button>
                </div>

                {/* Expanded Chart */}
                <div style={{ flex: 1, minHeight: 0 }}>
                  {expandedChart === "line" ? (
                    <LineChart data={analysis.timeseries} beforeYear={beforeYear} afterYear={afterYear} isExpanded={true} />
                  ) : (
                    <EncroachmentChart data={analysis.timeseries} isExpanded={true} />
                  )}
                </div>
              </motion.div>
            </div>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}
