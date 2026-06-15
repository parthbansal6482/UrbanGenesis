"use client";

import React, { useState, useEffect } from "react";
import ThreeGlobe from "../components/ThreeGlobe";
import ThreeMapProjection from "../components/ThreeMapProjection";

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
    before: {
      true_color: string | null;
      ndvi: string | null;
      mask: string | null;
    };
    after: {
      true_color: string | null;
      ndvi: string | null;
      mask: string | null;
    };
  };
}

const API_ORIGIN = "http://localhost:8000";

// Fallback zones data in case API is offline
const FALLBACK_ZONES: ZoneData[] = [
  {
    key: "nashik_north",
    name: "Nashik North Agricultural Zone",
    bbox: [73.72, 20.05, 73.98, 20.25],
    center: [20.15, 73.85],
    years: [2017, 2019, 2021, 2023, 2025],
    satyukt_relevance: "Grape and onion belt. Sat4Risk flood zone. MRV baseline.",
    latest_grade: "C",
    latest_abi: 0.584,
    overall_abi_change_pct: -15.2,
    cropland_loss_ha: 1420.5,
    encroachment_alert: false,
  },
  {
    key: "vijayawada_west",
    name: "Vijayawada West Farmland",
    bbox: [80.45, 16.45, 80.70, 16.65],
    center: [16.55, 80.575],
    years: [2017, 2019, 2021, 2023, 2025],
    satyukt_relevance: "Krishna delta cropland. Insurance client region.",
    latest_grade: "B",
    latest_abi: 1.124,
    overall_abi_change_pct: -4.8,
    cropland_loss_ha: 520.1,
    encroachment_alert: false,
  },
  {
    key: "hubli_outskirts",
    name: "Hubli Peripheral Agricultural Zone",
    bbox: [74.95, 15.28, 75.20, 15.48],
    center: [15.38, 75.075],
    years: [2017, 2019, 2021, 2023, 2025],
    satyukt_relevance: "Karnataka agri zone. Satyukt active partner region.",
    latest_grade: "F",
    latest_abi: 0.285,
    overall_abi_change_pct: -38.6,
    cropland_loss_ha: 4120.4,
    encroachment_alert: true,
  },
  {
    key: "bengaluru",
    name: "Bengaluru Agricultural Buffer Zone",
    bbox: [77.45, 12.83, 77.75, 13.1],
    center: [12.965, 77.6],
    years: [2017, 2019, 2021, 2023, 2025],
    satyukt_relevance: "Satyukt headquarters regional cropland buffer tracker.",
    latest_grade: "F",
    latest_abi: 0.124,
    overall_abi_change_pct: -44.4,
    cropland_loss_ha: 9435.5,
    encroachment_alert: true,
  },
];

export default function Home() {
  const [zones, setZones] = useState<ZoneData[]>([]);
  const [selectedZoneKey, setSelectedZoneKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"globe" | "projection">("globe");

  // Analysis criteria states
  const [beforeYear, setBeforeYear] = useState<number>(2017);
  const [afterYear, setAfterYear] = useState<number>(2025);
  const [vizMode, setVizMode] = useState<string>("AI Land Use Classification");
  const [sliderValue, setSliderValue] = useState<number>(50);
  const [opacity, setOpacity] = useState<number>(0.85);

  // Analysis result
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState<boolean>(false);
  const [apiWarning, setApiWarning] = useState<string | null>(null);

  // Class colors definition
  const classColors: { [key: string]: string } = {
    Buildings: "bg-[#DC2626]",
    Cropland: "bg-[#D4A017]",
    "Dense Vegetation": "bg-[#228B22]",
    "Water Bodies": "bg-[#1E64C8]",
    "Bare Soil": "bg-[#D2B48C]",
  };

  // Fetch zones on mount
  useEffect(() => {
    fetch(`${API_ORIGIN}/api/zones`)
      .then((res) => {
        if (!res.ok) throw new Error("Backend offline");
        return res.json();
      })
      .then((data) => {
        setZones(data);
        setApiWarning(null);
      })
      .catch((err) => {
        console.warn("FastAPI backend offline, loading local simulation fallback data.", err);
        setZones(FALLBACK_ZONES);
        setApiWarning("API Server offline. Displaying local simulation dataset.");
      });
  }, []);

  // Fetch analysis data when zone or years change
  useEffect(() => {
    if (!selectedZoneKey) return;
    setLoadingAnalysis(true);

    fetch(
      `${API_ORIGIN}/api/analyse?zone=${selectedZoneKey}&before=${beforeYear}&after=${afterYear}`
    )
      .then((res) => {
        if (!res.ok) throw new Error("Analysis failed");
        return res.json();
      })
      .then((data) => {
        setAnalysis(data);
      })
      .catch((err) => {
        console.warn("FastAPI analysis endpoint offline, fabricating simulated metrics.", err);
        // Create simulated local analysis response
        const activeZone = zones.find((z) => z.key === selectedZoneKey);
        if (activeZone) {
          const years = activeZone.years;
          const timeseries: TimeseriesRecord[] = years.map((yr, idx) => {
            const stepRatio = idx / (years.length - 1);
            let abiVal = 1.2 - stepRatio * 0.8;
            if (activeZone.key === "vijayawada_west") abiVal = 1.3 - stepRatio * 0.15;
            if (activeZone.key === "nashik_north") abiVal = 0.8 - stepRatio * 0.22;
            
            // Adjust pixels based on zone key
            const baseBuild = activeZone.key === "bengaluru" ? 5000000 : 2000000;
            const b_px = Math.round(baseBuild * (1 + stepRatio * 0.5));
            const c_px = Math.round(3000000 * (1 - stepRatio * 0.45));
            const v_px = Math.round(800000 * (1 - stepRatio * 0.2));
            const w_px = Math.round(500000 * (1 + Math.sin(idx) * 0.1));
            const s_px = 2000000;
            const total = b_px + c_px + v_px + w_px + s_px;

            return {
              year: yr,
              abi: Number(abiVal.toFixed(3)),
              cropland_pixels: c_px,
              vegetation_pixels: v_px,
              water_pixels: w_px,
              buildings_pixels: b_px,
              soil_pixels: s_px,
              cropland_pct: Number(((c_px / total) * 100).toFixed(2)),
              vegetation_pct: Number(((v_px / total) * 100).toFixed(2)),
              water_pct: Number(((w_px / total) * 100).toFixed(2)),
              buildings_pct: Number(((b_px / total) * 100).toFixed(2)),
              soil_pct: Number(((s_px / total) * 100).toFixed(2)),
            };
          });

          const recBefore = timeseries.find((t) => t.year === beforeYear) || timeseries[0];
          const recAfter = timeseries.find((t) => t.year === afterYear) || timeseries[timeseries.length - 1];

          // Set dummy overlay URLs
          // Since server is offline, we'll try to fallback to place-hold visuals or nothing
          const beforeOverlayName = vizMode === "True Color Satellite Image" ? "true_color" : vizMode === "NDVI Vegetation Map" ? "ndvi_map" : "mask_rgb";
          const afterOverlayName = vizMode === "True Color Satellite Image" ? "true_color" : vizMode === "NDVI Vegetation Map" ? "ndvi_map" : "mask_rgb";

          const mockAnalysis: AnalysisResponse = {
            zone_info: {
              key: activeZone.key,
              name: activeZone.name,
              bbox: activeZone.bbox,
              center: activeZone.center,
              years: activeZone.years,
              satyukt_relevance: activeZone.satyukt_relevance,
            },
            metrics: {
              latest_abi: activeZone.latest_abi,
              overall_abi_change_pct: activeZone.overall_abi_change_pct,
              cropland_loss_ha: activeZone.cropland_loss_ha,
              grade: activeZone.latest_grade,
              label: activeZone.latest_grade === "F" ? "Critical Encroachment Alert" : activeZone.latest_grade === "C" ? "Elevated Risk Buffer" : "Stable Farmland Buffer",
              description: `Agricultural buffer encroached by urban expansion. Sat4Risk risk evaluation triggers MRV audits.`,
              encroachment_alert: activeZone.encroachment_alert,
            },
            comparison: {
              before_year: beforeYear,
              after_year: afterYear,
              before_abi: recBefore.abi,
              after_abi: recAfter.abi,
              abi_change_pct: Number((((recAfter.abi - recBefore.abi) / recBefore.abi) * 100).toFixed(1)),
            },
            transitions: [
              { class_id: 1, class_name: "Buildings", before_pct: recBefore.buildings_pct, after_pct: recAfter.buildings_pct, trend_shift_pct: recAfter.buildings_pct - recBefore.buildings_pct, status: recAfter.buildings_pct > recBefore.buildings_pct + 0.1 ? "increase" : "stable" },
              { class_id: 2, class_name: "Cropland", before_pct: recBefore.cropland_pct, after_pct: recAfter.cropland_pct, trend_shift_pct: recAfter.cropland_pct - recBefore.cropland_pct, status: recAfter.cropland_pct < recBefore.cropland_pct - 0.1 ? "decrease" : "stable" },
              { class_id: 3, class_name: "Dense Vegetation", before_pct: recBefore.vegetation_pct, after_pct: recAfter.vegetation_pct, trend_shift_pct: recAfter.vegetation_pct - recBefore.vegetation_pct, status: recAfter.vegetation_pct < recBefore.vegetation_pct - 0.1 ? "decrease" : "stable" },
              { class_id: 4, class_name: "Water Bodies", before_pct: recBefore.water_pct, after_pct: recAfter.water_pct, trend_shift_pct: recAfter.water_pct - recBefore.water_pct, status: "stable" },
              { class_id: 5, class_name: "Bare Soil", before_pct: recBefore.soil_pct, after_pct: recAfter.soil_pct, trend_shift_pct: recAfter.soil_pct - recBefore.soil_pct, status: "stable" },
            ],
            timeseries: timeseries,
            overlays: {
              before: {
                true_color: `/static/${activeZone.key}/true_color_${beforeYear}.png`,
                ndvi: `/static/${activeZone.key}/ndvi_map_${beforeYear}.png`,
                mask: `/static/${activeZone.key}/mask_rgb_${beforeYear}.png`,
              },
              after: {
                true_color: `/static/${activeZone.key}/true_color_${afterYear}.png`,
                ndvi: `/static/${activeZone.key}/ndvi_map_${afterYear}.png`,
                mask: `/static/${activeZone.key}/mask_rgb_${afterYear}.png`,
              },
            },
          };
          setAnalysis(mockAnalysis);
        }
      })
      .finally(() => {
        setLoadingAnalysis(false);
      });
  }, [selectedZoneKey, beforeYear, afterYear, vizMode, zones]);

  // Handle zone selection from dropdown or map pins
  const handleSelectZone = (key: string) => {
    setSelectedZoneKey(key);
    // Find zone to reset before/after year clamp
    const zoneObj = zones.find((z) => z.key === key);
    if (zoneObj && zoneObj.years.length > 0) {
      setBeforeYear(zoneObj.years[0]);
      setAfterYear(zoneObj.years[zoneObj.years.length - 1]);
    }
    setActiveTab("projection"); // switch workspace view to focus on the 3D Map Projection
  };

  const currentZone = zones.find((z) => z.key === selectedZoneKey) || null;

  // Determine overlay image paths for before and after
  const beforeOverlayUrl = analysis
    ? vizMode === "True Color Satellite Image"
      ? analysis.overlays.before.true_color
      : vizMode === "NDVI Vegetation Map"
      ? analysis.overlays.before.ndvi
      : analysis.overlays.before.mask
    : null;

  const afterOverlayUrl = analysis
    ? vizMode === "True Color Satellite Image"
      ? analysis.overlays.after.true_color
      : vizMode === "NDVI Vegetation Map"
      ? analysis.overlays.after.ndvi
      : analysis.overlays.after.mask
    : null;

  // SVG Line Chart calculations
  const renderLineChart = () => {
    if (!analysis || analysis.timeseries.length === 0) return null;

    const data = analysis.timeseries;
    const margin = { top: 20, right: 20, bottom: 30, left: 35 };
    const width = 450;
    const height = 180;

    const xMax = width - margin.left - margin.right;
    const yMax = height - margin.top - margin.bottom;

    const years = data.map((d) => d.year);
    const abis = data.map((d) => d.abi);

    const maxAbi = Math.max(...abis, 2.0);
    const minAbi = 0.0;

    // Mapping helpers
    const getX = (year: number) => {
      const idx = years.indexOf(year);
      return margin.left + (idx / (years.length - 1)) * xMax;
    };

    const getY = (abi: number) => {
      return margin.top + yMax - ((abi - minAbi) / (maxAbi - minAbi)) * yMax;
    };

    // Build SVG points
    const points = data.map((d) => `${getX(d.year)},${getY(d.abi)}`).join(" ");

    // Build gradient fill points
    const areaPoints = `${getX(years[0])},${margin.top + yMax} ` + 
                       points + 
                       ` ${getX(years[years.length - 1])},${margin.top + yMax}`;

    return (
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto mt-2">
        <defs>
          <linearGradient id="abiGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10B981" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Background Y Gridlines */}
        {[0.5, 1.0, 1.5, 2.0].map((val) => {
          const y = getY(val);
          return (
            <g key={val}>
              <line x1={margin.left} y1={y} x2={width - margin.right} y2={y} stroke="#f1f5f9" strokeWidth="1" />
              <text x={margin.left - 8} y={y + 4} textAnchor="end" className="text-[9px] fill-slate-400 font-mono">
                {val.toFixed(1)}
              </text>
            </g>
          );
        })}

        {/* X Axis Labels */}
        {data.map((d) => {
          const x = getX(d.year);
          return (
            <g key={d.year}>
              <line x1={x} y1={margin.top} x2={x} y2={margin.top + yMax} stroke="#f8fafc" strokeWidth="1.5" />
              <text x={x} y={margin.top + yMax + 16} textAnchor="middle" className="text-[10px] fill-slate-500 font-semibold font-mono">
                {d.year}
              </text>
            </g>
          );
        })}

        {/* Area Gradient Fill */}
        <polygon points={areaPoints} fill="url(#abiGrad)" />

        {/* Trend line */}
        <polyline fill="none" stroke="#059669" strokeWidth="2.5" points={points} />

        {/* Highlight points */}
        {data.map((d) => {
          const cx = getX(d.year);
          const cy = getY(d.abi);
          const isSelected = d.year === beforeYear || d.year === afterYear;
          return (
            <g key={d.year}>
              <circle
                cx={cx}
                cy={cy}
                r={isSelected ? 6 : 4}
                className={`${isSelected ? "fill-emerald-600 stroke-white stroke-2" : "fill-white stroke-emerald-500 stroke-1.5"} cursor-pointer hover:r-7 transition-all`}
              />
              <text x={cx} y={cy - 9} textAnchor="middle" className="text-[9px] fill-slate-900 font-bold bg-white px-1">
                {d.abi.toFixed(2)}
              </text>
            </g>
          );
        })}
      </svg>
    );
  };

  return (
    <div className="flex-1 flex flex-col font-sans">
      {/* Header bar */}
      <header className="sticky top-0 bg-white border-b border-slate-200/90 z-20 px-6 py-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <span className="text-2xl">🌾</span>
            <h1 className="text-xl font-extrabold text-slate-900 tracking-tight">FarmGuard</h1>
            <span className="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wide">
              Satyukt Technology
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Satellite Deep-Learning Farmland Encroachment & Environmental Risk MRV Auditor
          </p>
        </div>

        {apiWarning && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5 flex items-center gap-2 text-xs text-amber-800">
            <span className="animate-ping w-2 h-2 rounded-full bg-amber-500 flex-shrink-0" />
            <span>{apiWarning}</span>
          </div>
        )}
      </header>

      {/* Main split-screen panel */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-0 overflow-hidden">
        
        {/* Left Side: 3D Visual Workspace (Takes 7 columns) */}
        <section className="lg:col-span-7 bg-[#f8fafc] border-r border-slate-200 flex flex-col min-h-[400px] lg:min-h-0 relative">
          
          {/* Workspace Controls */}
          <div className="absolute top-4 left-4 z-10 flex bg-white border border-slate-200/80 p-1 rounded-lg shadow-xs pointer-events-auto">
            <button
              onClick={() => setActiveTab("globe")}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                activeTab === "globe"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              🌐 3D Globe View
            </button>
            <button
              onClick={() => {
                if (!selectedZoneKey) {
                  // select first zone if none selected
                  if (zones.length > 0) handleSelectZone(zones[0].key);
                } else {
                  setActiveTab("projection");
                }
              }}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                activeTab === "projection"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              🗺️ 3D Area Projection
            </button>
          </div>

          {/* Interactive WebGL Container */}
          <div className="flex-1 w-full relative">
            {activeTab === "globe" ? (
              <ThreeGlobe
                zones={zones}
                selectedZoneKey={selectedZoneKey}
                onSelectZone={handleSelectZone}
              />
            ) : (
              <ThreeMapProjection
                beforeImageUrl={beforeOverlayUrl}
                afterImageUrl={afterOverlayUrl}
                opacity={opacity}
                isMask={vizMode === "AI Land Use Classification"}
                sliderValue={sliderValue}
              />
            )}
          </div>
        </section>

        {/* Right Side: Sidebar Controls and Metrics (Takes 5 columns) */}
        <section className="lg:col-span-5 bg-white flex flex-col divide-y divide-slate-100 overflow-y-auto max-h-[calc(100vh-80px)]">
          
          {/* Section 1: Region & Configuration Selectors */}
          <div className="p-6 space-y-4">
            <h2 className="text-sm font-bold text-slate-400 uppercase tracking-wider">Analysis Setup</h2>

            {/* Zone Selector */}
            <div className="space-y-1.5">
              <label htmlFor="zone-select" className="text-xs font-bold text-slate-700">Select Farmland Zone</label>
              <select
                id="zone-select"
                value={selectedZoneKey || ""}
                onChange={(e) => handleSelectZone(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 font-semibold focus:outline-hidden focus:ring-1 focus:ring-emerald-500"
              >
                <option value="" disabled>-- Choose a Region --</option>
                {zones.map((zone) => (
                  <option key={zone.key} value={zone.key}>
                    {zone.name}
                  </option>
                ))}
              </select>
            </div>

            {currentZone && (
              <>
                {/* Year Selectors */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label htmlFor="before-year" className="text-xs font-bold text-slate-700">Before Year</label>
                    <select
                      id="before-year"
                      value={beforeYear}
                      onChange={(e) => setBeforeYear(Number(e.target.value))}
                      className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 font-semibold focus:outline-hidden"
                    >
                      {currentZone.years.map((yr) => (
                        <option key={yr} value={yr} disabled={yr >= afterYear}>
                          {yr}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label htmlFor="after-year" className="text-xs font-bold text-slate-700">After Year</label>
                    <select
                      id="after-year"
                      value={afterYear}
                      onChange={(e) => setAfterYear(Number(e.target.value))}
                      className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 font-semibold focus:outline-hidden"
                    >
                      {currentZone.years.map((yr) => (
                        <option key={yr} value={yr} disabled={yr <= beforeYear}>
                          {yr}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Visualization mode dropdown */}
                <div className="space-y-1.5">
                  <label htmlFor="viz-mode" className="text-xs font-bold text-slate-700">Comparison Projection Overlay</label>
                  <select
                    id="viz-mode"
                    value={vizMode}
                    onChange={(e) => setVizMode(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 font-semibold focus:outline-hidden focus:ring-1 focus:ring-emerald-500"
                  >
                    <option value="AI Land Use Classification">🌾 AI Land Use Classification</option>
                    <option value="True Color Satellite Image">📸 True Color Satellite Image</option>
                    <option value="NDVI Vegetation Map">🌱 NDVI Vegetation Index</option>
                  </select>
                </div>

                {/* Opacity and wipe sliders */}
                {activeTab === "projection" && (
                  <div className="space-y-4 pt-2">
                    {/* Split Wipe Slider */}
                    <div className="space-y-1.5">
                      <div className="flex justify-between items-center">
                        <label htmlFor="wipe-slider" className="text-xs font-bold text-slate-700">3D Split-Wipe Transition</label>
                        <span className="text-[10px] font-mono text-slate-500 font-semibold bg-slate-100 px-2 py-0.5 rounded-sm">
                          {sliderValue}% After
                        </span>
                      </div>
                      <input
                        id="wipe-slider"
                        type="range"
                        min="0"
                        max="100"
                        value={sliderValue}
                        onChange={(e) => setSliderValue(Number(e.target.value))}
                        className="w-full accent-emerald-600 h-1.5 bg-slate-100 rounded-lg appearance-none cursor-pointer"
                      />
                    </div>

                    {/* Opacity Slider */}
                    <div className="space-y-1.5">
                      <div className="flex justify-between items-center">
                        <label htmlFor="opacity-slider" className="text-xs font-bold text-slate-700">Overlay Transparency (Opacity)</label>
                        <span className="text-[10px] font-mono text-slate-500 font-semibold bg-slate-100 px-2 py-0.5 rounded-sm">
                          {Math.round(opacity * 100)}%
                        </span>
                      </div>
                      <input
                        id="opacity-slider"
                        type="range"
                        min="0"
                        max="100"
                        value={opacity * 100}
                        onChange={(e) => setOpacity(Number(e.target.value) / 100)}
                        className="w-full accent-emerald-600 h-1.5 bg-slate-100 rounded-lg appearance-none cursor-pointer"
                      />
                    </div>
                  </div>
                )}
              </>
            )}
          </div>

          {/* Section 2: Metrics Card & Report */}
          <div className="p-6">
            {!selectedZoneKey ? (
              <div className="text-center py-12 px-6">
                <span className="text-3xl block mb-2">👆</span>
                <p className="text-sm font-semibold text-slate-500">
                  Select a farmland zone in the setup panel or click on the 3D Earth pins to run satellite analytics.
                </p>
              </div>
            ) : loadingAnalysis ? (
              <div className="flex flex-col items-center justify-center py-20 gap-3">
                <div className="w-8 h-8 rounded-full border-4 border-slate-100 border-t-emerald-600 animate-spin" />
                <span className="text-xs font-bold text-slate-400 font-mono tracking-widest uppercase">
                  Processing SAR & Spectral Bands...
                </span>
              </div>
            ) : analysis ? (
              <div className="space-y-6">
                {/* Custom Grade Badge & Status Header */}
                <div
                  className={`border rounded-xl p-4 transition-all ${
                    analysis.metrics.grade === "F"
                      ? "bg-red-50/50 border-red-200"
                      : analysis.metrics.grade === "C"
                      ? "bg-amber-50/50 border-amber-200"
                      : "bg-emerald-50/50 border-emerald-200"
                  }`}
                >
                  <div className="flex justify-between items-start gap-4">
                    <div>
                      <h3 className="text-base font-extrabold text-slate-900">
                        {analysis.zone_info.name}
                      </h3>
                      <p className="text-xs font-semibold text-slate-500 mt-0.5">
                        Satyukt relevance: {analysis.zone_info.satyukt_relevance}
                      </p>
                    </div>
                    {/* Status Badge */}
                    <div
                      className={`text-center font-black rounded-lg text-lg min-w-12 py-1 px-2.5 ${
                        analysis.metrics.grade === "F"
                          ? "bg-red-100 text-red-700"
                          : analysis.metrics.grade === "C"
                          ? "bg-amber-100 text-amber-700"
                          : "bg-emerald-100 text-emerald-700"
                      }`}
                    >
                      {analysis.metrics.grade}
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-2 items-center">
                    {analysis.metrics.encroachment_alert ? (
                      <span className="alert-pulse inline-flex items-center gap-1 bg-red-100 text-red-800 text-[10px] font-extrabold px-2.5 py-1 rounded-full border border-red-200 uppercase tracking-wider">
                        ⚠️ Critical Encroachment Alert
                      </span>
                    ) : (
                      <span className="stable-pulse inline-flex items-center gap-1 bg-emerald-100 text-emerald-800 text-[10px] font-extrabold px-2.5 py-1 rounded-full border border-emerald-200 uppercase tracking-wider">
                        ✅ Buffer Zone Stable
                      </span>
                    )}

                    <span className="bg-slate-100 text-slate-700 text-[10px] font-bold px-2.5 py-1 rounded-full border border-slate-200 uppercase tracking-wider">
                      Period: {beforeYear} → {afterYear}
                    </span>
                  </div>
                </div>

                {/* Grid of Key Indicators */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="border border-slate-200 rounded-xl p-4">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">
                      ABI Ratio ({afterYear})
                    </span>
                    <span className="text-2xl font-black text-slate-900 block mt-1">
                      {analysis.metrics.latest_abi.toFixed(3)}
                    </span>
                    <span className="text-[11px] font-semibold text-slate-500 mt-1 block">
                      Warning: &lt;0.5 • Critical: &lt;0.3
                    </span>
                  </div>

                  <div className="border border-slate-200 rounded-xl p-4">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">
                      Cropland Loss
                    </span>
                    <span className="text-2xl font-black text-slate-900 block mt-1 text-red-600">
                      -{analysis.metrics.cropland_loss_ha.toFixed(1)} ha
                    </span>
                    <span className="text-[11px] font-semibold text-slate-500 mt-1 block">
                      Estimated loss since 2017
                    </span>
                  </div>

                  <div className="border border-slate-200 rounded-xl p-4 col-span-2">
                    <div className="flex justify-between items-center">
                      <div>
                        <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">
                          Buffer Change ({beforeYear} vs {afterYear})
                        </span>
                        <span className="text-lg font-black text-slate-900 mt-1 block">
                          Overall ABI Shift
                        </span>
                      </div>
                      <div
                        className={`text-lg font-black ${
                          analysis.comparison.abi_change_pct < 0 ? "text-red-600" : "text-emerald-600"
                        }`}
                      >
                        {analysis.comparison.abi_change_pct > 0 ? "+" : ""}
                        {analysis.comparison.abi_change_pct}%
                      </div>
                    </div>
                  </div>
                </div>

                {/* Audit Description */}
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs leading-relaxed text-slate-600 italic">
                  &ldquo;{analysis.metrics.description}&rdquo;
                </div>

                {/* Timeseries SVG Trend Chart */}
                <div className="border border-slate-200 rounded-xl p-4">
                  <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">
                    ABI ratio trend timeline
                  </span>
                  {renderLineChart()}
                </div>

                {/* Class Shift Table */}
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <div className="bg-slate-50 px-4 py-3 border-b border-slate-200 flex justify-between items-center">
                    <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest">
                      Land cover shifts (%)
                    </span>
                    <span className="text-[10px] font-bold text-slate-500">
                      {beforeYear} vs {afterYear}
                    </span>
                  </div>
                  <div className="divide-y divide-slate-100">
                    {analysis.transitions.map((trans) => (
                      <div key={trans.class_name} className="px-4 py-3 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className={`w-3 h-3 rounded-xs ${classColors[trans.class_name] || "bg-slate-400"}`} />
                          <span className="font-semibold text-slate-700">{trans.class_name}</span>
                        </div>
                        <div className="flex items-center gap-6">
                          <span className="font-mono text-slate-400">{trans.before_pct.toFixed(1)}%</span>
                          <span className="font-mono text-slate-400">→</span>
                          <span className="font-mono text-slate-900 font-semibold">{trans.after_pct.toFixed(1)}%</span>
                          <span
                            className={`font-mono font-bold w-14 text-right ${
                              trans.trend_shift_pct > 0.05
                                ? "text-emerald-600"
                                : trans.trend_shift_pct < -0.05
                                ? "text-red-600"
                                : "text-slate-400"
                            }`}
                          >
                            {trans.trend_shift_pct > 0 ? "+" : ""}
                            {trans.trend_shift_pct.toFixed(1)}%
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      </main>
    </div>
  );
}
