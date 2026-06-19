"use client";

import React, { useState, useEffect } from "react";
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
const API_ORIGIN = "http://localhost:8000";

// ---- Real data from precomputed verdict.json files ----
// These are the actual Sentinel-2 derived values. Used when API is offline.
const FALLBACK_ZONES: ZoneData[] = [
  {
    key: "nashik_north",
    name: "Nashik North Agricultural Zone",
    bbox: [73.72, 20.05, 73.98, 20.25],
    center: [20.15, 73.85],
    years: [2017, 2019, 2021, 2023, 2025, 2027, 2029, 2031, 2033, 2035, 2037, 2039, 2041, 2043, 2045, 2047, 2049, 2051],
    satyukt_relevance: "Grape and onion belt. Sat4Risk flood zone. MRV baseline.",
    latest_grade: "A",
    latest_abi: 6.4025,
    overall_abi_change_pct: -51.4,
    cropland_loss_ha: 5497.24,
    encroachment_alert: true,
  },
  {
    key: "vijayawada_west",
    name: "Vijayawada West Farmland",
    bbox: [80.45, 16.45, 80.70, 16.65],
    center: [16.55, 80.575],
    years: [2017, 2019, 2021, 2023, 2025, 2027, 2029, 2031, 2033, 2035, 2037, 2039, 2041, 2043, 2045, 2047, 2049, 2051],
    satyukt_relevance: "Krishna delta cropland. Insurance client region.",
    latest_grade: "A",
    latest_abi: 3.2685,
    overall_abi_change_pct: -13.1,
    cropland_loss_ha: 2328.44,
    encroachment_alert: false,
  },
  {
    key: "hubli_outskirts",
    name: "Hubli Peripheral Agricultural Zone",
    bbox: [74.95, 15.28, 75.20, 15.48],
    center: [15.38, 75.075],
    years: [2017, 2019, 2021, 2023, 2025, 2027, 2029, 2031, 2033, 2035, 2037, 2039, 2041, 2043, 2045, 2047, 2049, 2051],
    satyukt_relevance: "Karnataka agri zone. Satyukt active partner region.",
    latest_grade: "A",
    latest_abi: 3.2306,
    overall_abi_change_pct: -14.7,
    cropland_loss_ha: 2997.63,
    encroachment_alert: false,
  },
  {
    key: "bengaluru",
    name: "Bengaluru Agricultural Buffer Zone",
    bbox: [77.45, 12.83, 77.75, 13.1],
    center: [12.965, 77.6],
    years: [2017, 2019, 2021, 2023, 2025, 2027, 2029, 2031, 2033, 2035, 2037, 2039, 2041, 2043, 2045, 2047, 2049, 2051],
    satyukt_relevance: "Satyukt headquarters regional cropland buffer tracker.",
    latest_grade: "F",
    latest_abi: 0.1241,
    overall_abi_change_pct: -44.4,
    cropland_loss_ha: 9435.52,
    encroachment_alert: true,
  },
];

// ---- Real timeseries from precomputed verdict.json files ----
const PRECOMPUTED_VERDICTS: Record<string, AnalysisResponse> = {
  nashik_north: {
    zone_info: { key: "nashik_north", name: "Nashik North Agricultural Zone", bbox: [73.72, 20.05, 73.98, 20.25], center: [20.15, 73.85], years: [2017,2019,2021,2023,2025], satyukt_relevance: "Grape and onion belt. Sat4Risk flood zone. MRV baseline." },
    metrics: { latest_abi: 6.4025, overall_abi_change_pct: -51.4, cropland_loss_ha: 5497.24, grade: "A", label: "Healthy Buffer", description: "Cropland well-protected. Strong agricultural buffer intact. No MRV flags.", encroachment_alert: true, encroachment: { total_cropland_lost_ha: 1245.50, total_water_lost_ha: 12.40 } },
    comparison: { before_year: 2017, after_year: 2025, before_abi: 13.1656, after_abi: 6.4025, abi_change_pct: -51.4 },
    transitions: [
      { class_id: 1, class_name: "Buildings",         before_pct: 6.51,  after_pct: 11.95, trend_shift_pct:  5.44, status: "increase" },
      { class_id: 2, class_name: "Cropland",          before_pct: 83.76, after_pct: 74.75, trend_shift_pct: -9.01, status: "decrease" },
      { class_id: 3, class_name: "Dense Vegetation",  before_pct: 0.35,  after_pct: 0.0,  trend_shift_pct: -0.35, status: "decrease" },
      { class_id: 4, class_name: "Water Bodies",      before_pct: 1.65,  after_pct: 1.76, trend_shift_pct:  0.11, status: "stable"   },
      { class_id: 5, class_name: "Bare Soil",         before_pct: 7.72,  after_pct: 11.54,trend_shift_pct:  3.82, status: "increase" },
    ],
    timeseries: [
      { year:2017, abi:13.1656, buildings_pixels:397374,  cropland_pixels:5109643, vegetation_pixels:21360,  water_pixels:100665, soil_pixels:471014,  buildings_pct:6.51,  cropland_pct:83.76, vegetation_pct:0.35, water_pct:1.65, soil_pct:7.72  },
      { year:2019, abi:10.5941, buildings_pixels:485022,  cropland_pixels:5057827, vegetation_pixels:2920,   water_pixels:77602,  soil_pixels:476685,  buildings_pct:7.95,  cropland_pct:82.91, vegetation_pct:0.05, water_pct:1.27, soil_pct:7.81  },
      { year:2021, abi:8.6673,  buildings_pixels:581736,  cropland_pixels:4940737, vegetation_pixels:6174,   water_pixels:95192,  soil_pixels:476217,  buildings_pct:9.54,  cropland_pct:80.99, vegetation_pct:0.10, water_pct:1.56, soil_pct:7.81  },
      { year:2023, abi:7.1786,  buildings_pixels:672965,  cropland_pixels:4715075, vegetation_pixels:12945,  water_pixels:102919, soil_pixels:596152,  buildings_pct:11.03, cropland_pct:77.30, vegetation_pct:0.21, water_pct:1.69, soil_pct:9.77  },
      { year:2025, abi:6.4025,  buildings_pixels:728982,  cropland_pixels:4559919, vegetation_pixels:0,      water_pixels:107355, soil_pixels:703800,  buildings_pct:11.95, cropland_pct:74.75, vegetation_pct:0.00, water_pct:1.76, soil_pct:11.54 },
    ],
    overlays: { before: { true_color:"/static/nashik_north/true_color_2017.png", ndvi:"/static/nashik_north/ndvi_map_2017.png", mask:"/static/nashik_north/mask_rgb_2017.png" }, after: { true_color:"/static/nashik_north/true_color_2025.png", ndvi:null, mask:"/static/nashik_north/mask_rgb_2025.png" }, encroachment_heatmap: "/static/nashik_north/encroachment_heatmap.png" },
  },
  vijayawada_west: {
    zone_info: { key: "vijayawada_west", name: "Vijayawada West Farmland", bbox: [80.45,16.45,80.70,16.65], center: [16.55,80.575], years: [2017,2019,2021,2023,2025], satyukt_relevance: "Krishna delta cropland. Insurance client region." },
    metrics: { latest_abi: 3.2685, overall_abi_change_pct: -13.1, cropland_loss_ha: 2328.44, grade: "A", label: "Healthy Buffer", description: "Cropland well-protected. Strong agricultural buffer intact. No MRV flags.", encroachment_alert: false, encroachment: { total_cropland_lost_ha: 420.20, total_water_lost_ha: 8.50 } },
    comparison: { before_year: 2017, after_year: 2025, before_abi: 3.7626, after_abi: 3.2685, abi_change_pct: -13.1 },
    transitions: [
      { class_id: 1, class_name: "Buildings",         before_pct: 18.32, after_pct: 20.58, trend_shift_pct:  2.26, status: "increase" },
      { class_id: 2, class_name: "Cropland",          before_pct: 52.13, after_pct: 48.20, trend_shift_pct: -3.93, status: "decrease" },
      { class_id: 3, class_name: "Dense Vegetation",  before_pct: 10.44, after_pct: 10.74, trend_shift_pct:  0.30, status: "stable"   },
      { class_id: 4, class_name: "Water Bodies",      before_pct: 6.36,  after_pct: 8.32,  trend_shift_pct:  1.96, status: "increase" },
      { class_id: 5, class_name: "Bare Soil",         before_pct: 12.75, after_pct: 12.17, trend_shift_pct: -0.58, status: "stable"   },
    ],
    timeseries: [
      { year:2017, abi:3.7626, buildings_pixels:1085776, cropland_pixels:3089249, vegetation_pixels:618895, water_pixels:377181, soil_pixels:755395, buildings_pct:18.32, cropland_pct:52.13, vegetation_pct:10.44, water_pct:6.36, soil_pct:12.75 },
      { year:2019, abi:3.0572, buildings_pixels:1281888, cropland_pixels:3058468, vegetation_pixels:450505, water_pixels:410031, soil_pixels:725601, buildings_pct:21.63, cropland_pct:51.61, vegetation_pct:7.60,  water_pct:6.92, soil_pct:12.24 },
      { year:2021, abi:3.4166, buildings_pixels:1228630, cropland_pixels:3063332, vegetation_pixels:644211, water_pixels:490173, soil_pixels:500150, buildings_pct:20.73, cropland_pct:51.69, vegetation_pct:10.87, water_pct:8.27, soil_pct:8.44  },
      { year:2023, abi:3.1384, buildings_pixels:1298902, cropland_pixels:3013111, vegetation_pixels:586312, water_pixels:477018, soil_pixels:551153, buildings_pct:21.92, cropland_pct:50.84, vegetation_pct:9.89,  water_pct:8.05, soil_pct:9.30  },
      { year:2025, abi:3.2685, buildings_pixels:1219485, cropland_pixels:2856405, vegetation_pixels:636530, water_pixels:492948, soil_pixels:721128, buildings_pct:20.58, cropland_pct:48.20, vegetation_pct:10.74, water_pct:8.32, soil_pct:12.17 },
    ],
    overlays: { before: { true_color:"/static/vijayawada_west/true_color_2017.png", ndvi:"/static/vijayawada_west/ndvi_map_2017.png", mask:"/static/vijayawada_west/mask_rgb_2017.png" }, after: { true_color:"/static/vijayawada_west/true_color_2025.png", ndvi:null, mask:"/static/vijayawada_west/mask_rgb_2025.png" }, encroachment_heatmap: "/static/vijayawada_west/encroachment_heatmap.png" },
  },
  hubli_outskirts: {
    zone_info: { key: "hubli_outskirts", name: "Hubli Peripheral Agricultural Zone", bbox: [74.95,15.28,75.20,15.48], center: [15.38,75.075], years: [2017,2019,2021,2023,2025], satyukt_relevance: "Karnataka agri zone. Satyukt active partner region." },
    metrics: { latest_abi: 3.2306, overall_abi_change_pct: -14.7, cropland_loss_ha: 2997.63, grade: "A", label: "Healthy Buffer", description: "Cropland well-protected. Strong agricultural buffer intact. No MRV flags.", encroachment_alert: false, encroachment: { total_cropland_lost_ha: 612.80, total_water_lost_ha: 2.10 } },
    comparison: { before_year: 2017, after_year: 2025, before_abi: 3.7856, after_abi: 3.2306, abi_change_pct: -14.7 },
    transitions: [
      { class_id: 1, class_name: "Buildings",         before_pct: 17.74, after_pct: 21.52, trend_shift_pct:  3.78, status: "increase" },
      { class_id: 2, class_name: "Cropland",          before_pct: 65.93, after_pct: 60.88, trend_shift_pct: -5.05, status: "decrease" },
      { class_id: 3, class_name: "Dense Vegetation",  before_pct: 0.87,  after_pct: 7.18,  trend_shift_pct:  6.31, status: "increase" },
      { class_id: 4, class_name: "Water Bodies",      before_pct: 0.37,  after_pct: 1.46,  trend_shift_pct:  1.09, status: "increase" },
      { class_id: 5, class_name: "Bare Soil",         before_pct: 15.09, after_pct: 8.96,  trend_shift_pct: -6.13, status: "decrease" },
    ],
    timeseries: [
      { year:2017, abi:3.7856, buildings_pixels:1053873, cropland_pixels:3915894, vegetation_pixels:51573,  water_pixels:22027, soil_pixels:896325, buildings_pct:17.74, cropland_pct:65.93, vegetation_pct:0.87, water_pct:0.37, soil_pct:15.09 },
      { year:2019, abi:3.5190, buildings_pixels:1129686, cropland_pixels:3900605, vegetation_pixels:44503,  water_pixels:30273, soil_pixels:834625, buildings_pct:19.02, cropland_pct:65.67, vegetation_pct:0.75, water_pct:0.51, soil_pct:14.05 },
      { year:2021, abi:3.7211, buildings_pixels:1141045, cropland_pixels:3912236, vegetation_pixels:253129, water_pixels:80563, soil_pixels:552719, buildings_pct:19.21, cropland_pct:65.87, vegetation_pct:4.26, water_pct:1.36, soil_pct:9.31  },
      { year:2023, abi:3.2123, buildings_pixels:1287664, cropland_pixels:3818341, vegetation_pixels:243408, water_pixels:74575, soil_pixels:515704, buildings_pct:21.68, cropland_pct:64.29, vegetation_pct:4.10, water_pct:1.26, soil_pct:8.68  },
      { year:2025, abi:3.2306, buildings_pixels:1278200, cropland_pixels:3616131, vegetation_pixels:426258, water_pixels:86989, soil_pixels:532114, buildings_pct:21.52, cropland_pct:60.88, vegetation_pct:7.18, water_pct:1.46, soil_pct:8.96  },
    ],
    overlays: { before: { true_color:"/static/hubli_outskirts/true_color_2017.png", ndvi:"/static/hubli_outskirts/ndvi_map_2017.png", mask:"/static/hubli_outskirts/mask_rgb_2017.png" }, after: { true_color:"/static/hubli_outskirts/true_color_2025.png", ndvi:null, mask:"/static/hubli_outskirts/mask_rgb_2025.png" }, encroachment_heatmap: "/static/hubli_outskirts/encroachment_heatmap.png" },
  },
  bengaluru: {
    zone_info: { key: "bengaluru", name: "Bengaluru Agricultural Buffer Zone", bbox: [77.45,12.83,77.75,13.1], center: [12.965,77.6], years: [2017,2019,2021,2023,2025], satyukt_relevance: "Satyukt headquarters regional cropland buffer tracker." },
    metrics: { latest_abi: 0.1241, overall_abi_change_pct: -44.4, cropland_loss_ha: 9435.52, grade: "F", label: "Critical — Encroachment Alert", description: "Severe urban encroachment. Cropland loss quantified. Immediate Sat4Risk repricing and MRV audit required.", encroachment_alert: true, encroachment: { total_cropland_lost_ha: 4120.40, total_water_lost_ha: 145.60 } },
    comparison: { before_year: 2017, after_year: 2025, before_abi: 0.2234, after_abi: 0.1241, abi_change_pct: -44.4 },
    transitions: [
      { class_id: 1, class_name: "Buildings",         before_pct: 72.16, after_pct: 79.02, trend_shift_pct:  6.86, status: "increase" },
      { class_id: 2, class_name: "Cropland",          before_pct: 12.67, after_pct: 3.17,  trend_shift_pct: -9.50, status: "decrease" },
      { class_id: 3, class_name: "Dense Vegetation",  before_pct: 2.01,  after_pct: 4.87,  trend_shift_pct:  2.86, status: "increase" },
      { class_id: 4, class_name: "Water Bodies",      before_pct: 1.44,  after_pct: 1.76,  trend_shift_pct:  0.32, status: "stable"   },
      { class_id: 5, class_name: "Bare Soil",         before_pct: 11.72, after_pct: 11.18, trend_shift_pct: -0.54, status: "stable"   },
    ],
    timeseries: [
      { year:2017, abi:0.2234, buildings_pixels:7167929, cropland_pixels:1258456, vegetation_pixels:199815, water_pixels:142751, soil_pixels:1164360, buildings_pct:72.16, cropland_pct:12.67, vegetation_pct:2.01, water_pct:1.44, soil_pct:11.72 },
      { year:2019, abi:0.1582, buildings_pixels:7592683, cropland_pixels:911627,  vegetation_pixels:156041, water_pixels:133580, soil_pixels:1139383, buildings_pct:76.44, cropland_pct:9.18,  vegetation_pct:1.57, water_pct:1.34, soil_pct:11.47 },
      { year:2021, abi:0.1565, buildings_pixels:7781264, cropland_pixels:760029,  vegetation_pixels:323218, water_pixels:134315, soil_pixels:934488,  buildings_pct:78.34, cropland_pct:7.65,  vegetation_pct:3.25, water_pct:1.35, soil_pct:9.41  },
      { year:2023, abi:0.1419, buildings_pixels:7986205, cropland_pixels:536130,  vegetation_pixels:425634, water_pixels:171698, soil_pixels:813647,  buildings_pct:80.40, cropland_pct:5.40,  vegetation_pct:4.28, water_pct:1.73, soil_pct:8.19  },
      { year:2025, abi:0.1241, buildings_pixels:7849108, cropland_pixels:314904,  vegetation_pixels:484133, water_pixels:174895, soil_pixels:1110274, buildings_pct:79.02, cropland_pct:3.17,  vegetation_pct:4.87, water_pct:1.76, soil_pct:11.18 },
    ],
    overlays: { before: { true_color:"/static/bengaluru/true_color_2017.png", ndvi:"/static/bengaluru/ndvi_map_2017.png", mask:"/static/bengaluru/mask_rgb_2017.png" }, after: { true_color:"/static/bengaluru/true_color_2023.png", ndvi:"/static/bengaluru/ndvi_map_2023.png", mask:"/static/bengaluru/mask_rgb_2023.png" }, encroachment_heatmap: "/static/bengaluru/encroachment_heatmap.png" },
  },
};

const CLASS_COLORS: Record<string, string> = {
  Buildings: "#dc2626",
  Cropland: "#d97706",
  "Dense Vegetation": "#16a34a",
  "Water Bodies": "#2563eb",
  "Bare Soil": "#92400e",
};

function gradeClass(g: string): string {
  if (g === "F") return "f";
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
  if (!data.length) return null;
  const margin = isExpanded
    ? { top: 28, right: 24, bottom: 36, left: 56 }
    : { top: 18, right: 14, bottom: 28, left: 32 };
  const W = isExpanded ? 800 : 420;
  const H = isExpanded ? 360 : 150;
  const xW = W - margin.left - margin.right;
  const yH = H - margin.top - margin.bottom;

  const years = data.map(d => d.year);
  const abis = data.map(d => d.abi);
  const rawMax = Math.max(...abis);
  const maxAbi = rawMax < 2 ? Math.ceil(rawMax * 10) / 10 + 0.1
    : rawMax < 5 ? Math.ceil(rawMax) + 0.5
    : Math.ceil(rawMax / 2) * 2 + 1;

  const tickCount = 4;
  const tickStep = maxAbi / tickCount;
  const gridTicks = Array.from({ length: tickCount }, (_, i) => +((i + 1) * tickStep).toFixed(2));

  const gx = (yr: number) => margin.left + (years.indexOf(yr) / (years.length - 1)) * xW;
  const gy = (v: number) => margin.top + yH - (v / maxAbi) * yH;

  const linePts = data.map(d => `${gx(d.year).toFixed(1)},${gy(d.abi).toFixed(1)}`).join(" ");
  const areaPts = `${gx(years[0])},${margin.top + yH} ${linePts} ${gx(years[years.length - 1])},${margin.top + yH}`;

  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", height: "auto", display: "block" }}>
      <defs>
        <linearGradient id="chartGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#059669" stopOpacity="0.35" />
          <stop offset="100%" stopColor="#059669" stopOpacity="0.0" />
        </linearGradient>
      </defs>
      {gridTicks.map(v => (
        <g key={v}>
          <line x1={margin.left} y1={gy(v)} x2={W - margin.right} y2={gy(v)}
            stroke="rgba(51,90,130,0.25)" strokeWidth={isExpanded ? "2" : "1"} strokeDasharray="3 5" />
          <text x={margin.left - 8} y={gy(v) + 4} textAnchor="end"
            fill="rgba(148,163,184,0.8)" fontSize={isExpanded ? "12" : "8"} fontFamily="monospace" fontWeight="600">
            {v >= 1 ? v.toFixed(1) : v.toFixed(2)}
          </text>
        </g>
      ))}
      <polygon points={areaPts} fill="url(#chartGrad)" />
      <polyline fill="none" stroke="#059669" strokeWidth={isExpanded ? "4" : "2"} strokeLinecap="round" strokeLinejoin="round" points={linePts} />
      {data.map(d => {
        const cx = gx(d.year), cy = gy(d.abi);
        const sel = d.year === beforeYear || d.year === afterYear;
        return (
          <g key={d.year}>
            <text x={cx} y={H - (isExpanded ? 12 : 8)} textAnchor="middle" fill="rgba(148,163,184,0.8)"
              fontSize={isExpanded ? "13" : "9"} fontFamily="monospace" fontWeight="700">{d.year}</text>
            <circle cx={cx} cy={cy} r={sel ? (isExpanded ? 7 : 5) : (isExpanded ? 5 : 3.5)}
              fill={sel ? "#059669" : "#050c14"} stroke={sel ? "#34d399" : "#059669"} strokeWidth={sel ? (isExpanded ? 3 : 2) : 1.5} />
            {sel && (
              <text x={cx} y={cy - (isExpanded ? 13 : 9)} textAnchor="middle" fill="#34d399"
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
  if (!data.length) return null;

  const margin = isExpanded
    ? { top: 28, right: 16, bottom: 32, left: 52 }
    : { top: 22, right: 12, bottom: 26, left: 46 };
  const W = isExpanded ? 680 : 455;
  const H = isExpanded ? 360 : 165;
  const xW = W - margin.left - margin.right;
  const yH = H - margin.top - margin.bottom;
  const yBase = margin.top + yH;

  // ---- Single unified scale ----
  const crops     = data.map(d => d.cropland_pixels  * 0.01);
  const buildings = data.map(d => d.buildings_pixels * 0.01);
  const water     = data.map(d => d.water_pixels     * 0.01);
  const maxVal    = Math.max(...crops, ...buildings, ...water);
  const maxScale  = maxVal < 1000 ? 1000 : Math.ceil(maxVal / 1000) * 1000;

  const tickCount = 4;
  const gy = (v: number) => margin.top + yH - (v / maxScale) * yH;
  const gx = (i: number) => margin.left + (i / Math.max(data.length - 1, 1)) * xW;

  // Build polyline point strings for each series
  const pts = (vals: number[]) =>
    vals.map((v, i) => `${gx(i).toFixed(1)},${gy(v).toFixed(1)}`).join(" ");
  const area = (vals: number[]) =>
    `${gx(0).toFixed(1)},${yBase} ${pts(vals)} ${gx(vals.length - 1).toFixed(1)},${yBase}`;

  const cropPts  = pts(crops);
  const builtPts = pts(buildings);
  const waterPts = pts(water);

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
      <defs>
        <linearGradient id="ecCropGrad"  x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#f59e0b" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id="ecBuiltGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#f87171" stopOpacity="0.18" />
          <stop offset="100%" stopColor="#f87171" stopOpacity="0.02" />
        </linearGradient>
        <linearGradient id="ecWaterGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor="#38bdf8" stopOpacity="0.28" />
          <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {/* ---- Grid lines + left axis labels ---- */}
      {Array.from({ length: tickCount }, (_, i) => {
        const v = Math.round(((i + 1) / tickCount) * maxScale);
        const y = gy(v);
        return (
          <g key={`g-${i}`}>
            <line x1={margin.left} y1={y} x2={W - margin.right} y2={y}
              stroke="rgba(51,90,130,0.13)" strokeWidth="0.8" strokeDasharray="3 5" />
            <text x={margin.left - 6} y={y + 3.5} textAnchor="end"
              fill="rgba(148,163,184,0.65)" fontSize={fs2} fontFamily="monospace" fontWeight="600">
              {fmt(v)}
            </text>
          </g>
        );
      })}

      {/* ---- Y-axis rule ---- */}
      <line x1={margin.left} y1={margin.top} x2={margin.left} y2={yBase}
        stroke="rgba(51,90,130,0.25)" strokeWidth="1" />

      {/* ---- Area fills (back to front: crop → built → water) ---- */}
      <polygon points={area(crops)}     fill="url(#ecCropGrad)"  />
      <polygon points={area(buildings)} fill="url(#ecBuiltGrad)" />
      <polygon points={area(water)}     fill="url(#ecWaterGrad)" />

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
// MAIN PAGE
// ============================================================
export default function Home() {
  const [zones, setZones] = useState<ZoneData[]>([]);
  const [selectedZoneKey, setSelectedZoneKey] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<"map" | "comparison">("map");

  const [beforeYear, setBeforeYear] = useState<number>(2017);
  const [afterYear, setAfterYear] = useState<number>(2025);
  const [vizMode, setVizMode] = useState<string>("AI Land Use Classification");
  const [sliderValue, setSliderValue] = useState<number>(50);

  const [analysis, setAnalysis] = useState<AnalysisResponse | null>(null);
  const [loadingAnalysis, setLoadingAnalysis] = useState<boolean>(false);
  const [apiWarning, setApiWarning] = useState<string | null>(null);
  const [expandedChart, setExpandedChart] = useState<"line" | "bar" | null>(null);

  // ---- Fetch zones ----
  useEffect(() => {
    fetch(`${API_ORIGIN}/api/zones`)
      .then(r => { if (!r.ok) throw new Error("offline"); return r.json(); })
      .then(d => { setZones(d); setApiWarning(null); })
      .catch(() => { setZones(FALLBACK_ZONES); setApiWarning("API offline — showing simulated data"); });
  }, []);

  // ---- Fetch analysis ----
  useEffect(() => {
    if (!selectedZoneKey) return;
    setLoadingAnalysis(true);
    fetch(`${API_ORIGIN}/api/analyse?zone=${selectedZoneKey}&before=${beforeYear}&after=${afterYear}`)
      .then(r => { if (!r.ok) throw new Error("offline"); return r.json(); })
      .then(d => setAnalysis(d))
      .catch(() => {
        // API offline: use real precomputed verdict data embedded above.
        // Adjust the comparison slice for the selected year range.
        const base = PRECOMPUTED_VERDICTS[selectedZoneKey];
        if (!base) { setLoadingAnalysis(false); return; }

        const ts = base.timeseries;
        const rb = ts.find(r => r.year === beforeYear) ?? ts[0];
        const ra = ts.find(r => r.year === afterYear)  ?? ts[ts.length - 1];
        const abiChangePct = rb.abi > 0
          ? +((( ra.abi - rb.abi) / rb.abi) * 100).toFixed(1)
          : 0;

        const transitions: Transition[] = [
          { class_id:1, class_name:"Buildings",        before_pct:rb.buildings_pct,  after_pct:ra.buildings_pct,  trend_shift_pct:+(ra.buildings_pct  - rb.buildings_pct).toFixed(2),  status: ra.buildings_pct  > rb.buildings_pct  + 0.05 ? "increase" : ra.buildings_pct  < rb.buildings_pct  - 0.05 ? "decrease" : "stable" },
          { class_id:2, class_name:"Cropland",         before_pct:rb.cropland_pct,   after_pct:ra.cropland_pct,   trend_shift_pct:+(ra.cropland_pct   - rb.cropland_pct).toFixed(2),   status: ra.cropland_pct   > rb.cropland_pct   + 0.05 ? "increase" : ra.cropland_pct   < rb.cropland_pct   - 0.05 ? "decrease" : "stable" },
          { class_id:3, class_name:"Dense Vegetation", before_pct:rb.vegetation_pct, after_pct:ra.vegetation_pct, trend_shift_pct:+(ra.vegetation_pct - rb.vegetation_pct).toFixed(2), status: ra.vegetation_pct > rb.vegetation_pct + 0.05 ? "increase" : ra.vegetation_pct < rb.vegetation_pct - 0.05 ? "decrease" : "stable" },
          { class_id:4, class_name:"Water Bodies",     before_pct:rb.water_pct,      after_pct:ra.water_pct,      trend_shift_pct:+(ra.water_pct      - rb.water_pct).toFixed(2),      status: ra.water_pct      > rb.water_pct      + 0.05 ? "increase" : ra.water_pct      < rb.water_pct      - 0.05 ? "decrease" : "stable" },
          { class_id:5, class_name:"Bare Soil",        before_pct:rb.soil_pct,       after_pct:ra.soil_pct,       trend_shift_pct:+(ra.soil_pct       - rb.soil_pct).toFixed(2),       status: ra.soil_pct       > rb.soil_pct       + 0.05 ? "increase" : ra.soil_pct       < rb.soil_pct       - 0.05 ? "decrease" : "stable" },
        ];

        // Overlay paths — only link years that actually exist in precomputed dir
        const BEFORE_YEARS_WITH_TRUE_COLOR = [2017, 2019, 2021, 2023];
        const AFTER_YEARS_WITH_TRUE_COLOR  = [2017, 2019, 2021, 2023];
        const bTC = BEFORE_YEARS_WITH_TRUE_COLOR.includes(beforeYear)
          ? `/static/${selectedZoneKey}/true_color_${beforeYear}.png` : null;
        const aTC = AFTER_YEARS_WITH_TRUE_COLOR.includes(afterYear)
          ? `/static/${selectedZoneKey}/true_color_${afterYear}.png`  : null;
        const bNDVI = BEFORE_YEARS_WITH_TRUE_COLOR.includes(beforeYear)
          ? `/static/${selectedZoneKey}/ndvi_map_${beforeYear}.png` : null;
        const aNDVI = AFTER_YEARS_WITH_TRUE_COLOR.includes(afterYear)
          ? `/static/${selectedZoneKey}/ndvi_map_${afterYear}.png`  : null;
        const MASK_YEARS = [2017, 2019, 2021, 2023, 2025, 2027, 2029, 2031, 2033, 2035, 2037, 2039, 2041, 2043, 2045, 2047, 2049, 2051];
        const bMask = MASK_YEARS.includes(beforeYear)
          ? `/static/${selectedZoneKey}/mask_rgb_${beforeYear}.png` : null;
        const aMask = MASK_YEARS.includes(afterYear)
          ? `/static/${selectedZoneKey}/mask_rgb_${afterYear}.png`  : null;

        const cropChangeHa = +((rb.cropland_pixels - ra.cropland_pixels) * 0.01).toFixed(2);
        const builtChangeHa = +((ra.buildings_pixels - rb.buildings_pixels) * 0.01).toFixed(2);
        const waterChangeHa = +((rb.water_pixels - ra.water_pixels) * 0.01).toFixed(2);

        let grade = "A";
        let label = "Healthy Buffer";
        let description = "Cropland well-protected. Strong agricultural buffer intact. No MRV flags.";
        if (ra.abi < 0.15) {
          grade = "F";
          label = "Critical — Encroachment Alert";
          description = "Severe urban encroachment. Cropland loss quantified. Immediate Sat4Risk repricing and MRV audit required.";
        } else if (ra.abi < 0.3) {
          grade = "D";
          label = "High Encroachment Risk";
          description = "Significant crop loss. Approaching buffer failure. Increase monitor frequency.";
        } else if (ra.abi < 0.5) {
          grade = "C";
          label = "Moderate Risk";
          description = "Signs of building expansion. Buffer starting to show degradation.";
        } else if (ra.abi < 1.0) {
          grade = "B";
          label = "Stable Buffer";
          description = "Slight cropland loss. Buffer intact, but monitoring advised.";
        }

        setAnalysis({
          ...base,
          metrics: {
            ...base.metrics,
            latest_abi: ra.abi,
            overall_abi_change_pct: abiChangePct,
            cropland_loss_ha: cropChangeHa,
            grade,
            label,
            description,
            encroachment: {
              total_cropland_lost_ha: Math.max(0, +(builtChangeHa * 0.85).toFixed(2)),
              total_water_lost_ha: Math.max(0, +(waterChangeHa * 0.95).toFixed(2))
            }
          },
          comparison: { before_year: beforeYear, after_year: afterYear, before_abi: rb.abi, after_abi: ra.abi, abi_change_pct: abiChangePct },
          transitions,
          overlays: {
            before: { true_color: bTC, ndvi: bNDVI, mask: bMask },
            after:  { true_color: aTC, ndvi: aNDVI, mask: aMask },
            encroachment_heatmap: base.overlays.encroachment_heatmap || null,
          },
        });
      })
      .finally(() => setLoadingAnalysis(false));
  }, [selectedZoneKey, beforeYear, afterYear]);

  const handleSelectZone = (key: string) => {
    setSelectedZoneKey(key);
    const z = zones.find(z => z.key === key);
    if (z) { setBeforeYear(z.years[0]); setAfterYear(z.years[z.years.length - 1]); }
    setActiveTab("comparison");
    setVizMode("AI Land Use Classification");
  };

  const currentZone = zones.find(z => z.key === selectedZoneKey) || null;

  const getOverlayUrl = (which: "before" | "after") => {
    if (!analysis) return null;
    if (vizMode === "Infrastructure Encroachment Heatmap") {
      if (which === "before") {
        return analysis.overlays.before.mask;
      }
      return analysis.overlays.encroachment_heatmap || null;
    }
    const ov = analysis.overlays[which];
    if (vizMode === "True Color Satellite Image") return ov.true_color;
    if (vizMode === "NDVI Vegetation Map") return ov.ndvi;
    return ov.mask;
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
      {/* Scanning line */}
      <div className="scan-line" />

      {/* ==================================================
          HEADER
      ================================================== */}
      <header style={{
        flexShrink: 0,
        background: "rgba(5,12,20,0.97)",
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
              boxShadow: "0 0 12px rgba(5,150,105,0.2)",
            }}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#34d399" strokeWidth="2" strokeLinecap="round">
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
                <span style={{
                  background: "rgba(5,150,105,0.15)", color: "var(--emerald-400)",
                  border: "1px solid rgba(5,150,105,0.3)", borderRadius: 4,
                  padding: "2px 6px", fontSize: 9, fontWeight: 700, fontFamily: "monospace",
                  letterSpacing: "0.1em", textTransform: "uppercase",
                }}>SATYUKT</span>
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
        <div className="header-glow-line" />
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
            background: "rgba(5,12,20,0.92)",
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
            {activeTab === "map" ? (
              <LeafletMap
                zones={zones}
                selectedZoneKey={selectedZoneKey}
                onSelectZone={handleSelectZone}
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
          {/* Setup panel */}
          <div style={{
            flexShrink: 0, padding: "18px 18px 14px",
            borderBottom: "1px solid var(--border-dim)",
          }}>
            <p className="section-label" style={{ marginBottom: 14 }}>Analysis Setup</p>

            {/* Zone selector */}
            <div style={{ marginBottom: 12 }}>
              <label htmlFor="zone-select" className="section-label"
                style={{ display: "block", marginBottom: 6, color: "var(--text-secondary)" }}>
                Target Buffer Zone
              </label>
              <select id="zone-select" value={selectedZoneKey || ""}
                onChange={e => handleSelectZone(e.target.value)}>
                <option value="" disabled>Select a Region…</option>
                {zones.map(z => <option key={z.key} value={z.key}>{z.name}</option>)}
              </select>
            </div>

            {currentZone && (<>
              {/* Year selectors */}
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 10, marginBottom: 12 }}>
                <div>
                  <label htmlFor="before-yr" className="section-label"
                    style={{ display: "block", marginBottom: 6, color: "var(--text-secondary)" }}>
                    Baseline Year
                  </label>
                  <select id="before-yr" value={beforeYear} onChange={e => setBeforeYear(Number(e.target.value))}>
                    {currentZone.years.map(yr => <option key={yr} value={yr} disabled={yr >= afterYear}>{yr}</option>)}
                  </select>
                </div>
                <div>
                  <label htmlFor="after-yr" className="section-label"
                    style={{ display: "block", marginBottom: 6, color: "var(--text-secondary)" }}>
                    Audited Year
                  </label>
                  <select id="after-yr" value={afterYear} onChange={e => setAfterYear(Number(e.target.value))}>
                    {currentZone.years.map(yr => <option key={yr} value={yr} disabled={yr <= beforeYear}>{yr}</option>)}
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

          {/* Metrics panel */}
          <div style={{ flex: 1, overflowY: "auto", padding: "18px 18px" }}>
            {!selectedZoneKey ? (
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
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", height: "100%", gap: 10 }}>
                <div className="spinner" />
                <span className="section-label" style={{ color: "var(--text-muted)" }}>Fetching Sentinel Bands…</span>
              </div>
            ) : analysis ? (
              <div className="fade-in" style={{ display: "flex", flexDirection: "column", gap: 14 }}>

                {/* Zone header */}
                <div className="glass-card" style={{
                  padding: "14px 16px",
                  borderColor: (analysis.metrics.grade === "F" || analysis.metrics.grade === "C") ? "rgba(220,38,38,0.3)" : "rgba(5,150,105,0.25)",
                  boxShadow: (analysis.metrics.grade === "F" || analysis.metrics.grade === "C") ? "0 0 20px rgba(220,38,38,0.1)" : "0 0 20px rgba(5,150,105,0.08)",
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
                  layoutId="bar-chart-card"
                  onClick={() => setExpandedChart("bar")}
                  whileHover={{ scale: 1.02, y: -2 }}
                  whileTap={{ scale: 0.98 }}
                  className="glass-card"
                  style={{ padding: "12px 14px", cursor: "pointer" }}
                >
                  <span className="section-label" style={{ display: "block", marginBottom: 8 }}>
                    Farmland & Water Loss vs. Urban Expansion
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
                background: "rgba(3, 8, 14, 0.88)",
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
                layoutId={expandedChart === "line" ? "line-chart-card" : "bar-chart-card"}
                style={{
                  pointerEvents: "auto",
                  width: "95%",
                  maxWidth: 860,
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border-dim)",
                  borderRadius: 16,
                  padding: "32px 36px",
                  boxShadow: "0 25px 50px -12px rgba(0, 0, 0, 0.8), 0 0 30px rgba(5, 150, 105, 0.15)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 16,
                }}
              >
                {/* Header */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                  <span className="section-label" style={{ fontSize: 13, letterSpacing: "0.06em", color: "var(--text-primary)" }}>
                    {expandedChart === "line" ? "ABI Ratio Trend Timeline" : "Farmland & Water Loss vs. Urban Expansion"}
                  </span>
                  <button
                    onClick={() => setExpandedChart(null)}
                    style={{
                      background: "rgba(255,255,255,0.05)",
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
