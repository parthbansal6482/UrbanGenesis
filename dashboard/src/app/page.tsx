"use client";

import React, { useState, useEffect } from "react";
import dynamic from "next/dynamic";

// Dynamically import ThreeJS components to prevent SSR canvas size and window reference bugs
const ThreeGlobe = dynamic(() => import("../components/ThreeGlobe"), { ssr: false });
const ThreeMapProjection = dynamic(() => import("../components/ThreeMapProjection"), { ssr: false });

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

// Fallback simulated data in case FastAPI server is offline
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

  // Filter criteria states
  const [beforeYear, setBeforeYear] = useState<number>(2017);
  const [afterYear, setAfterYear] = useState<number>(2025);
  const [vizMode, setVizMode] = useState<string>("AI Land Use Classification");
  const [sliderValue, setSliderValue] = useState<number>(50);
  const [opacity, setOpacity] = useState<number>(0.85);

  // Loaded analysis response
  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState<boolean>(false);
  const [apiWarning, setApiWarning] = useState<string | null>(null);

  // Color classes for dashboard tags
  const classColors: { [key: string]: string } = {
    Buildings: "bg-[#DC2626]",
    Cropland: "bg-[#D4A017]",
    "Dense Vegetation": "bg-[#228B22]",
    "Water Bodies": "bg-[#1E64C8]",
    "Bare Soil": "bg-[#D2B48C]",
  };

  // Fetch zones list
  useEffect(() => {
    fetch(`${API_ORIGIN}/api/zones`)
      .then((res) => {
        if (!res.ok) throw new Error("API Offline");
        return res.json();
      })
      .then((data) => {
        setZones(data);
        setApiWarning(null);
      })
      .catch((err) => {
        console.warn("FastAPI offline, launching simulation fallback.", err);
        setZones(FALLBACK_ZONES);
        setApiWarning("API Server Offline. Simulating local dataset.");
      });
  }, []);

  // Fetch metrics when selection modifies
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
        console.warn("FastAPI analytics offline, fabricating metrics locally.", err);
        const activeZone = zones.find((z) => z.key === selectedZoneKey);
        if (activeZone) {
          const years = activeZone.years;
          const timeseries: TimeseriesRecord[] = years.map((yr, idx) => {
            const stepRatio = idx / (years.length - 1);
            let abiVal = 1.2 - stepRatio * 0.8;
            if (activeZone.key === "vijayawada_west") abiVal = 1.3 - stepRatio * 0.15;
            if (activeZone.key === "nashik_north") abiVal = 0.8 - stepRatio * 0.22;
            
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

  // Select zone handler
  const handleSelectZone = (key: string) => {
    setSelectedZoneKey(key);
    const zoneObj = zones.find((z) => z.key === key);
    if (zoneObj && zoneObj.years.length > 0) {
      setBeforeYear(zoneObj.years[0]);
      setAfterYear(zoneObj.years[zoneObj.years.length - 1]);
    }
    setActiveTab("projection");
  };

  const currentZone = zones.find((z) => z.key === selectedZoneKey) || null;

  // Resolve active projection texture links
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

  // Custom vector line chart
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

    const getX = (year: number) => {
      const idx = years.indexOf(year);
      return margin.left + (idx / (years.length - 1)) * xMax;
    };

    const getY = (abi: number) => {
      return margin.top + yMax - ((abi - minAbi) / (maxAbi - minAbi)) * yMax;
    };

    const points = data.map((d) => `${getX(d.year)},${getY(d.abi)}`).join(" ");

    const areaPoints = `${getX(years[0])},${margin.top + yMax} ` + 
                       points + 
                       ` ${getX(years[years.length - 1])},${margin.top + yMax}`;

    return (
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto mt-2">
        <defs>
          <linearGradient id="abiGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10B981" stopOpacity="0.25" />
            <stop offset="100%" stopColor="#10B981" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Y-Axis lines */}
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

        {/* X-Axis ticks */}
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

        <polygon points={areaPoints} fill="url(#abiGrad)" />
        <polyline fill="none" stroke="#059669" strokeWidth="2.5" points={points} />

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
                className={`${isSelected ? "fill-emerald-600 stroke-white stroke-2" : "fill-white stroke-emerald-500 stroke-1.5"} cursor-pointer`}
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
      {/* Top Navigation Bar */}
      <header className="sticky top-0 bg-white border-b border-slate-200/90 z-20 px-6 py-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-xl font-extrabold text-slate-900 tracking-tight">FarmGuard</h1>
            <span className="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5 rounded-md uppercase tracking-wide font-mono">
              SATYUKT TECHNOLOGY
            </span>
          </div>
          <p className="text-xs text-slate-500 mt-1 font-mono uppercase tracking-wider">
            Satellite Farmland Encroachment & Environmental Risk Auditor
          </p>
        </div>

        {apiWarning && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5 flex items-center gap-2 text-xs text-amber-800 font-mono">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0 animate-ping" />
            <span>{apiWarning}</span>
          </div>
        )}
      </header>

      {/* Main Split Window */}
      <main className="flex-1 grid grid-cols-1 lg:grid-cols-12 gap-0 overflow-hidden">
        
        {/* Left Side: 3D Visual Workspace */}
        <section className="lg:col-span-7 bg-[#f8fafc] border-r border-slate-200 flex flex-col min-h-[420px] lg:min-h-0 relative">
          
          {/* Flat glass selector tab */}
          <div className="absolute top-4 left-4 z-10 flex bg-white/90 backdrop-blur-md border border-slate-200/80 p-1 rounded-lg shadow-xs pointer-events-auto">
            <button
              onClick={() => setActiveTab("globe")}
              className={`px-3 py-1.5 rounded-md text-[11px] font-mono uppercase tracking-wider transition-all ${
                activeTab === "globe"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Globe Map
            </button>
            <button
              onClick={() => {
                if (!selectedZoneKey) {
                  if (zones.length > 0) handleSelectZone(zones[0].key);
                } else {
                  setActiveTab("projection");
                }
              }}
              className={`px-3 py-1.5 rounded-md text-[11px] font-mono uppercase tracking-wider transition-all ${
                activeTab === "projection"
                  ? "bg-slate-900 text-white shadow-xs"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              Area Projection
            </button>
          </div>

          {/* ThreeJS Visual Layer */}
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

        {/* Right Side: Sidebar Controls and Metrics */}
        <section className="lg:col-span-5 bg-white flex flex-col divide-y divide-slate-100 overflow-y-auto max-h-[calc(100vh-80px)]">
          
          {/* Setup Configurator */}
          <div className="p-6 space-y-4">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-widest font-mono">Analysis Setup</h2>

            {/* Zone Selector */}
            <div className="space-y-1.5">
              <label htmlFor="zone-select" className="text-xs font-bold text-slate-700 font-mono uppercase">Target Buffer Zone</label>
              <select
                id="zone-select"
                value={selectedZoneKey || ""}
                onChange={(e) => handleSelectZone(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 font-semibold focus:outline-hidden focus:ring-1 focus:ring-emerald-500 font-mono"
              >
                <option value="" disabled>Select a Region</option>
                {zones.map((zone) => (
                  <option key={zone.key} value={zone.key}>
                    {zone.name.toUpperCase()}
                  </option>
                ))}
              </select>
            </div>

            {currentZone && (
              <>
                {/* Year Selection */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-1.5">
                    <label htmlFor="before-year" className="text-xs font-bold text-slate-700 font-mono uppercase">Baseline Year</label>
                    <select
                      id="before-year"
                      value={beforeYear}
                      onChange={(e) => setBeforeYear(Number(e.target.value))}
                      className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 font-semibold focus:outline-hidden font-mono"
                    >
                      {currentZone.years.map((yr) => (
                        <option key={yr} value={yr} disabled={yr >= afterYear}>
                          {yr}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className="space-y-1.5">
                    <label htmlFor="after-year" className="text-xs font-bold text-slate-700 font-mono uppercase">Audited Year</label>
                    <select
                      id="after-year"
                      value={afterYear}
                      onChange={(e) => setAfterYear(Number(e.target.value))}
                      className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 font-semibold focus:outline-hidden font-mono"
                    >
                      {currentZone.years.map((yr) => (
                        <option key={yr} value={yr} disabled={yr <= beforeYear}>
                          {yr}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                {/* Projection Overlay Modes */}
                <div className="space-y-1.5">
                  <label htmlFor="viz-mode" className="text-xs font-bold text-slate-700 font-mono uppercase">Raster Overlay Mode</label>
                  <select
                    id="viz-mode"
                    value={vizMode}
                    onChange={(e) => setVizMode(e.target.value)}
                    className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-sm text-slate-900 font-semibold focus:outline-hidden focus:ring-1 focus:ring-emerald-500 font-mono"
                  >
                    <option value="AI Land Use Classification">AI Land Use Classification</option>
                    <option value="True Color Satellite Image">True Color Satellite Image</option>
                    <option value="NDVI Vegetation Map">NDVI Vegetation Map</option>
                  </select>
                </div>

                {/* Sliders for split wipe and opacity */}
                {activeTab === "projection" && (
                  <div className="space-y-4 pt-2">
                    {/* Swipe slider */}
                    <div className="space-y-1.5">
                      <div className="flex justify-between items-center">
                        <label htmlFor="wipe-slider" className="text-xs font-bold text-slate-700 font-mono uppercase">Split-Wipe Divider</label>
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

                    {/* Opacity slider */}
                    <div className="space-y-1.5">
                      <div className="flex justify-between items-center">
                        <label htmlFor="opacity-slider" className="text-xs font-bold text-slate-700 font-mono uppercase">Texture Opacity</label>
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

          {/* Metrics Panel */}
          <div className="p-6">
            {!selectedZoneKey ? (
              <div className="text-center py-12 px-6">
                <p className="text-xs font-bold text-slate-400 font-mono tracking-widest uppercase">
                  Select a farmland region in the setup panel or click on the 3D Globe pins to inspect risk metrics.
                </p>
              </div>
            ) : loadingAnalysis ? (
              <div className="flex flex-col items-center justify-center py-20 gap-3">
                <div className="w-6 h-6 rounded-full border-2 border-slate-100 border-t-emerald-600 animate-spin" />
                <span className="text-[10px] font-bold text-slate-400 font-mono tracking-wider uppercase">
                  Fetching Sentinel Bands...
                </span>
              </div>
            ) : analysis ? (
              <div className="space-y-6">
                {/* Grading header */}
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
                      <h3 className="text-sm font-bold text-slate-900 font-mono uppercase">
                        {analysis.zone_info.name}
                      </h3>
                      <p className="text-[11px] text-slate-500 mt-1 font-mono uppercase tracking-wider">
                        Relevance: {analysis.zone_info.satyukt_relevance}
                      </p>
                    </div>
                    {/* Grade Badge */}
                    <div
                      className={`text-center font-black rounded-lg text-lg min-w-10 py-0.5 px-2 font-mono ${
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
                      <span className="alert-pulse inline-flex items-center bg-red-100 text-red-800 text-[9px] font-bold px-2.5 py-1 rounded-full border border-red-200 uppercase tracking-widest font-mono">
                        Encroachment Alert Active
                      </span>
                    ) : (
                      <span className="stable-pulse inline-flex items-center bg-emerald-100 text-emerald-800 text-[9px] font-bold px-2.5 py-1 rounded-full border border-emerald-200 uppercase tracking-widest font-mono">
                        Buffer Zone Stable
                      </span>
                    )}

                    <span className="bg-slate-100 text-slate-700 text-[9px] font-bold px-2.5 py-1 rounded-full border border-slate-200 uppercase tracking-widest font-mono">
                      Period: {beforeYear} to {afterYear}
                    </span>
                  </div>
                </div>

                {/* Key indicators layout */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="border border-slate-200 rounded-xl p-4">
                    <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest block font-mono">
                      ABI Ratio ({afterYear})
                    </span>
                    <span className="text-xl font-bold text-slate-900 block mt-1 font-mono">
                      {analysis.metrics.latest_abi.toFixed(3)}
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block font-mono">
                      Warning: &lt;0.5 • Critical: &lt;0.3
                    </span>
                  </div>

                  <div className="border border-slate-200 rounded-xl p-4">
                    <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest block font-mono">
                      Cropland Loss
                    </span>
                    <span className="text-xl font-bold text-slate-900 block mt-1 text-red-600 font-mono">
                      -{analysis.metrics.cropland_loss_ha.toFixed(1)} ha
                    </span>
                    <span className="text-[10px] text-slate-400 mt-1 block font-mono">
                      Estimated loss since 2017
                    </span>
                  </div>

                  <div className="border border-slate-200 rounded-xl p-4 col-span-2">
                    <div className="flex justify-between items-center">
                      <div>
                        <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest block font-mono">
                          Buffer Change ({beforeYear} vs {afterYear})
                        </span>
                        <span className="text-sm font-bold text-slate-950 mt-1 block font-mono uppercase">
                          Overall ABI Shift
                        </span>
                      </div>
                      <div
                        className={`text-base font-bold font-mono ${
                          analysis.comparison.abi_change_pct < 0 ? "text-red-600" : "text-emerald-600"
                        }`}
                      >
                        {analysis.comparison.abi_change_pct > 0 ? "+" : ""}
                        {analysis.comparison.abi_change_pct}%
                      </div>
                    </div>
                  </div>
                </div>

                {/* Description */}
                <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 text-xs leading-relaxed text-slate-600 italic">
                  &ldquo;{analysis.metrics.description}&rdquo;
                </div>

                {/* Trend Chart */}
                <div className="border border-slate-200 rounded-xl p-4">
                  <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest block font-mono">
                    ABI Ratio Trend Timeline
                  </span>
                  {renderLineChart()}
                </div>

                {/* Class Shift Metrics Table */}
                <div className="border border-slate-200 rounded-xl overflow-hidden">
                  <div className="bg-slate-50 px-4 py-3 border-b border-slate-200 flex justify-between items-center">
                    <span className="text-[9px] font-bold text-slate-400 uppercase tracking-widest font-mono">
                      Land Cover Shifts (%)
                    </span>
                    <span className="text-[9px] font-bold text-slate-500 font-mono">
                      {beforeYear} vs {afterYear}
                    </span>
                  </div>
                  <div className="divide-y divide-slate-100">
                    {analysis.transitions.map((trans) => (
                      <div key={trans.class_name} className="px-4 py-3 flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className={`w-2.5 h-2.5 rounded-xs ${classColors[trans.class_name] || "bg-slate-400"}`} />
                          <span className="font-semibold text-slate-700">{trans.class_name}</span>
                        </div>
                        <div className="flex items-center gap-6">
                          <span className="font-mono text-slate-400">{trans.before_pct.toFixed(1)}%</span>
                          <span className="font-mono text-slate-400">→</span>
                          <span className="font-mono text-slate-900 font-semibold">{trans.after_pct.toFixed(1)}%</span>
                          <span
                            className={`font-mono font-bold w-12 text-right ${
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
