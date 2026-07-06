"use client";

import React, { useState, useRef, useCallback, useEffect } from "react";

// ============================================================
// TYPES
// ============================================================
interface SliderComparisonProps {
  beforeImageUrl: string | null;
  afterImageUrl: string | null;
  beforeYear: number;
  afterYear: number;
  opacity?: number;
  isMask: boolean;
  sliderValue: number;          // 0–100: position of divider (% from left)
  onSliderChange: (v: number) => void;
  showSlider?: boolean;
  isMock?: boolean;
}

// ============================================================
// FALLBACK BLUEPRINT IMAGE GENERATOR
// ============================================================
function makeBlueprintDataUrl(year: number, label: string): string {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d")!;

  // Off-white base
  ctx.fillStyle = "#fafaf9";
  ctx.fillRect(0, 0, 512, 512);

  // Grid
  ctx.strokeStyle = "rgba(15, 23, 42, 0.05)";
  ctx.lineWidth = 0.8;
  for (let i = 0; i <= 512; i += 24) {
    ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, 512); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(512, i); ctx.stroke();
  }

  // Header band
  ctx.fillStyle = "rgba(5, 150, 105, 0.06)";
  ctx.fillRect(0, 0, 512, 68);

  ctx.fillStyle = "#059669";
  ctx.font = "bold 12px monospace";
  ctx.textAlign = "center";
  ctx.fillText("SAT4RISK // FARMGUARD SURVEILLANCE", 256, 26);

  ctx.fillStyle = "#475569";
  ctx.font = "9.5px monospace";
  ctx.fillText(`PERIOD: ${year}  ·  SENTINEL-2 L2A`, 256, 48);

  // Alert text
  ctx.fillStyle = "#dc2626";
  ctx.font = "bold 10.5px monospace";
  ctx.textAlign = "left";
  if (year > 2023) {
    ctx.fillText(`// SATELLITE DATA NOT AVAILABLE FOR ${year}`, 28, 108);
    ctx.fillText(`// REASON: FUTURE PREDICTION YEAR`, 28, 128);
  } else {
    ctx.fillText(`// SATELLITE RASTER ABSENT FOR ${year}`, 28, 108);
    ctx.fillText(`// MODE: ${label.toUpperCase()}`, 28, 128);
  }

  // Crosshair
  ctx.strokeStyle = "rgba(5, 150, 105, 0.3)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(256, 310, 56, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(256, 236); ctx.lineTo(256, 384);
  ctx.moveTo(182, 310); ctx.lineTo(330, 310);
  ctx.stroke();

  // Bottom label
  ctx.fillStyle = "#475569";
  ctx.font = "8px monospace";
  ctx.textAlign = "center";
  ctx.fillText("TARGET BOUNDS GRID ACTIVE · AWAITING RASTER INPUT", 256, 390);

  return canvas.toDataURL("image/png");
}

const API_ORIGIN = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function SliderComparison({
  beforeImageUrl,
  afterImageUrl,
  beforeYear,
  afterYear,
  opacity = 1.0,
  isMask,
  sliderValue,
  onSliderChange,
  showSlider = true,
  isMock = false,
}: SliderComparisonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [beforeSrc, setBeforeSrc] = useState<string | null>(null);
  const [afterSrc, setAfterSrc] = useState<string | null>(null);
  const [loadingBefore, setLoadingBefore] = useState(true);
  const [loadingAfter, setLoadingAfter] = useState(true);

  // ---- Zoom & Pan states ----
  const [zoomScale, setZoomScale] = useState(1.0);
  const [panOffset, setPanOffset] = useState({ x: 0, y: 0 });

  // Refs/state for tracking drag status separately
  const isDraggingSlider = useRef(false);
  const [isPanning, setIsPanning] = useState(false);
  const panStart = useRef({ x: 0, y: 0 });
  const initialPanOffset = useRef({ x: 0, y: 0 });

  // ---- Load / process images ----
  const processImage = useCallback((
    url: string | null,
    year: number,
    maskMode: boolean,
    onDone: (src: string) => void
  ) => {
    const fallbackLabel = maskMode ? "AI classification" : "satellite band";

    if (!url) {
      setTimeout(() => onDone(makeBlueprintDataUrl(year, fallbackLabel)), 0);
      return;
    }

    const finalUrl = url.startsWith("http") ? url : `${API_ORIGIN}${url}`;
    const img = new Image();

    img.onload = () => {
      onDone(finalUrl);
    };

    img.onerror = () => {
      onDone(makeBlueprintDataUrl(year, "load error"));
    };
    img.src = finalUrl;
  }, []);

  useEffect(() => {
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Reset loading state to true synchronously when inputs change to display loading spinner
    setLoadingBefore(true);
    processImage(beforeImageUrl, beforeYear, isMask, src => {
      if (active) {
        setBeforeSrc(src);
        setLoadingBefore(false);
      }
    });
    return () => {
      active = false;
    };
  }, [beforeImageUrl, beforeYear, isMask, processImage]);

  useEffect(() => {
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Reset loading state to true synchronously when inputs change to display loading spinner
    setLoadingAfter(true);
    processImage(afterImageUrl, afterYear, isMask, src => {
      if (active) {
        setAfterSrc(src);
        setLoadingAfter(false);
      }
    });
    return () => {
      active = false;
    };
  }, [afterImageUrl, afterYear, isMask, processImage]);

  // ---- Non-passive Wheel Zoom handler ----
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleWheel = (e: WheelEvent) => {
      e.preventDefault();
      const zoomFactor = 1.08;
      setZoomScale(prev => {
        let next = prev;
        if (e.deltaY < 0) {
          next = Math.min(prev * zoomFactor, 5.0);
        } else {
          next = Math.max(prev / zoomFactor, 0.5);
        }
        return next;
      });
    };

    container.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      container.removeEventListener("wheel", handleWheel);
    };
  }, []);

  // ---- Drag & Pan Pointer logic ----
  const updateFromPointer = useCallback((clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
    onSliderChange(pct);
  }, [onSliderChange]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    const target = e.target as HTMLElement;
    
    // Ignore clicks on buttons so their onClick event triggers normally
    if (target.closest("button") !== null) {
      return;
    }

    // Check if clicked directly on slider handle or slider line
    const isHandleClick = target.closest(".slider-handle-trigger") !== null;

    if (showSlider && isHandleClick) {
      isDraggingSlider.current = true;
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      updateFromPointer(e.clientX);
    } else {
      setIsPanning(true);
      (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
      panStart.current = { x: e.clientX, y: e.clientY };
      initialPanOffset.current = { ...panOffset };
    }
  }, [showSlider, updateFromPointer, panOffset]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (isDraggingSlider.current) {
      updateFromPointer(e.clientX);
    } else if (isPanning) {
      const dx = e.clientX - panStart.current.x;
      const dy = e.clientY - panStart.current.y;
      setPanOffset({
        x: initialPanOffset.current.x + dx,
        y: initialPanOffset.current.y + dy,
      });
    }
  }, [updateFromPointer, isPanning]);

  const onPointerUp = useCallback(() => {
    isDraggingSlider.current = false;
    setIsPanning(false);
  }, []);

  const isLoading = loadingBefore || loadingAfter;
  const isBeforeMask = isMask && beforeSrc ? !beforeSrc.startsWith("data:") : false;
  const isAfterMask = isMask && afterSrc ? !afterSrc.startsWith("data:") : false;

  // Shared hardware-accelerated transform styles for standard layout containing
  const transformStyle: React.CSSProperties = {
    width: "100%",
    height: "100%",
    objectFit: "contain",
    transform: `translate(${panOffset.x}px, ${panOffset.y}px) scale(${zoomScale})`,
    transformOrigin: "center",
    display: "block",
    userSelect: "none",
    // Only animate on zoom adjustments, not live dragging
    transition: isPanning ? "none" : "transform 0.12s ease-out",
  };

  return (
    <div
      style={{
        position: "relative", width: "100%", height: "100%",
        background: "var(--bg-base)", overflow: "hidden",
        display: "flex", flexDirection: "column", alignItems: "center",
      }}
    >
      {/* ---- Simulation warning badge ---- */}
      {isMock && (
        <div style={{
          position: "absolute", top: 12, left: "50%",
          transform: "translateX(-50%)", zIndex: 30,
          pointerEvents: "none",
        }}>
          <span className="glass-card" style={{
            display: "inline-block",
            fontSize: 9, fontFamily: "monospace", fontWeight: 800,
            padding: "4px 10px", borderRadius: 6,
            color: "#b45309",
            border: "1px solid rgba(217, 119, 6, 0.25)",
            background: "rgba(217, 119, 6, 0.05)",
            letterSpacing: "0.06em",
          }}>
            ⚠️ SIMULATED DATA
          </span>
        </div>
      )}

      {/* ---- Loading indicator only ---- */}
      {isLoading && (
        <div style={{
          position: "absolute", top: 12, right: 12,
          zIndex: 20, pointerEvents: "none",
        }}>
          <div className="glass-card" style={{ padding: "5px 12px", display: "flex", alignItems: "center", gap: 6 }}>
            <div className="spinner" style={{ width: 12, height: 12 }} />
            <span className="section-label" style={{ color: "var(--emerald-500)" }}>Loading raster…</span>
          </div>
        </div>
      )}

      <div
        ref={containerRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
        className="bg-grid"
        style={{
          flex: 1,
          width: "100%",
          height: "100%",
          position: "relative",
          overflow: "hidden",
          cursor: isPanning ? "grabbing" : (showSlider ? "grab" : "default"),
          userSelect: "none",
        }}
      >
        {showSlider ? (
          <>
            {/* BEFORE image — full width viewport, clipped on the right */}
            {beforeSrc && (
              <div style={{
                position: "absolute", inset: 0,
                clipPath: `inset(0 ${100 - sliderValue}% 0 0)`,
                pointerEvents: "none",
              }}>
                <img
                  src={beforeSrc}
                  alt={`Before ${beforeYear}`}
                  draggable={false}
                  style={{
                    ...transformStyle,
                    opacity,
                    mixBlendMode: isBeforeMask ? "screen" : "normal",
                  }}
                />
              </div>
            )}

            {/* AFTER image — full width viewport, clipped on the left */}
            {afterSrc && (
              <div style={{
                position: "absolute", inset: 0,
                clipPath: `inset(0 0 0 ${sliderValue}%)`,
                pointerEvents: "none",
              }}>
                <img
                  src={afterSrc}
                  alt={`After ${afterYear}`}
                  draggable={false}
                  style={{
                    ...transformStyle,
                    opacity,
                    mixBlendMode: isAfterMask ? "screen" : "normal",
                  }}
                />
              </div>
            )}

            {/* ---- Year labels: outside clip containers ---- */}
            <div style={{
              position: "absolute", top: 12, left: 14,
              pointerEvents: "none", zIndex: 12,
            }}>
              <span className="glass-card" style={{
                display: "inline-block",
                fontSize: 10, fontFamily: "monospace", fontWeight: 700,
                padding: "3px 10px", borderRadius: 6,
                color: "var(--text-primary)",
                letterSpacing: "0.06em",
              }}>{beforeYear}</span>
            </div>
            <div style={{
              position: "absolute", top: 12, right: 14,
              pointerEvents: "none", zIndex: 12,
            }}>
              <span className="glass-card" style={{
                display: "inline-block",
                fontSize: 10, fontFamily: "monospace", fontWeight: 700,
                padding: "3px 10px", borderRadius: 6,
                color: "var(--text-primary)",
                letterSpacing: "0.06em",
              }}>{afterYear}</span>
            </div>

            {/* Vertical Split Line */}
            <div
              className="slider-handle-trigger"
              style={{
                position: "absolute",
                top: 0, bottom: 0,
                left: `${sliderValue}%`,
                width: 4,
                background: "var(--emerald-500)",
                transform: "translateX(-50%)",
                zIndex: 10,
                cursor: "ew-resize",
              }}
            />

            {/* ---- Drag handle circular pill ---- */}
            <div
              className="slider-handle-trigger"
              style={{
                position: "absolute",
                top: "50%",
                left: `${sliderValue}%`,
                transform: "translate(-50%, -50%)",
                zIndex: 15,
                width: 36, height: 36,
                borderRadius: "50%",
                background: "var(--bg-base)",
                border: "2px solid var(--emerald-500)",
                boxShadow: "0 0 16px rgba(5,150,105,0.4)",
                display: "flex", alignItems: "center", justifyContent: "center",
                cursor: "ew-resize",
              }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M5 4L2 8l3 4M11 4l3 4-3 4" stroke="#059669" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </div>

            {/* ---- Before/After direction labels at bottom ---- */}
            <div style={{
              position: "absolute", bottom: 14, left: 14,
              pointerEvents: "none", zIndex: 12,
            }}>
              <span className="glass-card" style={{
                display: "inline-block",
                fontSize: 9, fontFamily: "monospace", fontWeight: 700,
                letterSpacing: "0.08em", textTransform: "uppercase",
                padding: "3px 8px", borderRadius: 5,
                color: "var(--text-secondary)",
              }}>← Before</span>
            </div>
            <div style={{
              position: "absolute", bottom: 14, right: 14,
              pointerEvents: "none", zIndex: 12,
            }}>
              <span className="glass-card" style={{
                display: "inline-block",
                fontSize: 9, fontFamily: "monospace", fontWeight: 700,
                letterSpacing: "0.08em", textTransform: "uppercase",
                padding: "3px 8px", borderRadius: 5,
                color: "var(--text-secondary)",
              }}>After →</span>
            </div>
          </>
        ) : (
          /* Single full-width Encroachment Heatmap view (also supports zoom & pan) */
          afterSrc && (
            <div style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
              <img
                src={afterSrc}
                alt="Encroachment Heatmap"
                draggable={false}
                style={transformStyle}
              />
              <div
                style={{
                  position: "absolute", top: 12, right: 14,
                  pointerEvents: "none", zIndex: 12,
                }}
              >
                <span className="badge-neutral" style={{ fontSize: 10, padding: "4px 10px", color: "var(--red-400)", border: "1px solid rgba(220,38,38,0.25)", background: "rgba(220,38,38,0.05)" }}>
                  Encroachment Heatmap
                </span>
              </div>
            </div>
          )
        )}

        {/* ---- Zoom / Reset controls HUD ---- */}
        <div style={{
          position: "absolute", bottom: 48, right: 12, zIndex: 30,
          display: "flex", flexDirection: "column", gap: 4,
          pointerEvents: "auto",
        }}>
          <button
            onClick={(e) => { e.stopPropagation(); setZoomScale(z => Math.min(z * 1.25, 5.0)); }}
            className="glass-card"
            style={{
              width: 30, height: 30, borderRadius: 6, border: "1px solid var(--border-dim)",
              background: "#fafaf9", color: "var(--text-secondary)", fontSize: 16,
              cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
              fontWeight: "bold", outline: "none",
            }}
            title="Zoom In"
          >+</button>
          <button
            onClick={(e) => { e.stopPropagation(); setZoomScale(z => Math.max(z * 0.8, 0.5)); }}
            className="glass-card"
            style={{
              width: 30, height: 30, borderRadius: 6, border: "1px solid var(--border-dim)",
              background: "#fafaf9", color: "var(--text-secondary)", fontSize: 16,
              cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
              fontWeight: "bold", outline: "none",
            }}
            title="Zoom Out"
          >−</button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              setZoomScale(1.0);
              setPanOffset({ x: 0, y: 0 });
            }}
            className="glass-card"
            style={{
              width: 30, height: 30, borderRadius: 6, border: "1px solid var(--border-dim)",
              background: "#fafaf9", color: "var(--text-secondary)", fontSize: 11,
              cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center",
              fontFamily: "monospace", outline: "none",
            }}
            title="Reset View"
          >⊡</button>
        </div>
      </div>
    </div>
  );
}
