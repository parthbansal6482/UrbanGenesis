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
}

// ============================================================
// FALLBACK BLUEPRINT IMAGE GENERATOR
// ============================================================
function makeBlueprintDataUrl(year: number, label: string): string {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d")!;

  // Deep dark base
  ctx.fillStyle = "#050c14";
  ctx.fillRect(0, 0, 512, 512);

  // Grid
  ctx.strokeStyle = "rgba(5,150,105,0.1)";
  ctx.lineWidth = 0.8;
  for (let i = 0; i <= 512; i += 24) {
    ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, 512); ctx.stroke();
    ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(512, i); ctx.stroke();
  }

  // Header band
  ctx.fillStyle = "rgba(5,150,105,0.1)";
  ctx.fillRect(0, 0, 512, 68);

  ctx.fillStyle = "#34d399";
  ctx.font = "bold 12px monospace";
  ctx.textAlign = "center";
  ctx.fillText("SAT4RISK // FARMGUARD SURVEILLANCE", 256, 26);

  ctx.fillStyle = "rgba(52,211,153,0.55)";
  ctx.font = "9.5px monospace";
  ctx.fillText(`PERIOD: ${year}  ·  SENTINEL-2 L2A`, 256, 48);

  // Alert text
  ctx.fillStyle = "rgba(239,68,68,0.85)";
  ctx.font = "bold 10.5px monospace";
  ctx.textAlign = "left";
  ctx.fillText(`// SATELLITE RASTER ABSENT FOR ${year}`, 28, 108);
  ctx.fillText(`// MODE: ${label.toUpperCase()}`, 28, 128);

  // Crosshair
  ctx.strokeStyle = "rgba(5,150,105,0.45)";
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(256, 310, 56, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(256, 236); ctx.lineTo(256, 384);
  ctx.moveTo(182, 310); ctx.lineTo(330, 310);
  ctx.stroke();

  // Bottom label
  ctx.fillStyle = "rgba(52,211,153,0.65)";
  ctx.font = "8px monospace";
  ctx.textAlign = "center";
  ctx.fillText("TARGET BOUNDS GRID ACTIVE · AWAITING RASTER INPUT", 256, 390);

  return canvas.toDataURL("image/png");
}

// ============================================================
// COMPONENT
// ============================================================
export default function SliderComparison({
  beforeImageUrl,
  afterImageUrl,
  beforeYear,
  afterYear,
  opacity = 1.0,
  isMask,
  sliderValue,
  onSliderChange,
}: SliderComparisonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);
  const [beforeSrc, setBeforeSrc] = useState<string | null>(null);
  const [afterSrc, setAfterSrc] = useState<string | null>(null);
  const [loadingBefore, setLoadingBefore] = useState(true);
  const [loadingAfter, setLoadingAfter] = useState(true);

  // ---- Load / process images ----
  const processImage = useCallback((
    url: string | null,
    year: number,
    maskMode: boolean,
    onDone: (src: string) => void
  ) => {
    const fallbackLabel = maskMode ? "AI classification" : "satellite band";

    if (!url) {
      // Generate fallback in next tick so we're in browser context
      setTimeout(() => onDone(makeBlueprintDataUrl(year, fallbackLabel)), 0);
      return;
    }

    const finalUrl = url.startsWith("http") ? url : `http://localhost:8000${url}`;
    const img = new Image();
    img.crossOrigin = "anonymous";

    img.onload = () => {
      if (!maskMode) {
        onDone(finalUrl);
        return;
      }
      // Mask: make black pixels transparent
      const cv = document.createElement("canvas");
      cv.width = img.width;
      cv.height = img.height;
      const cx = cv.getContext("2d")!;
      cx.drawImage(img, 0, 0);
      const id = cx.getImageData(0, 0, cv.width, cv.height);
      for (let i = 0; i < id.data.length; i += 4) {
        if (id.data[i] === 0 && id.data[i + 1] === 0 && id.data[i + 2] === 0) {
          id.data[i + 3] = 0;
        }
      }
      cx.putImageData(id, 0, 0);
      onDone(cv.toDataURL("image/png"));
    };

    img.onerror = () => onDone(makeBlueprintDataUrl(year, "load error"));
    img.src = finalUrl;
  }, []);

  useEffect(() => {
    setLoadingBefore(true);
    processImage(beforeImageUrl, beforeYear, isMask, src => {
      setBeforeSrc(src);
      setLoadingBefore(false);
    });
  }, [beforeImageUrl, beforeYear, isMask, processImage]);

  useEffect(() => {
    setLoadingAfter(true);
    processImage(afterImageUrl, afterYear, isMask, src => {
      setAfterSrc(src);
      setLoadingAfter(false);
    });
  }, [afterImageUrl, afterYear, isMask, processImage]);

  // ---- Drag logic ----
  const updateFromPointer = useCallback((clientX: number) => {
    if (!containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pct = Math.max(0, Math.min(100, ((clientX - rect.left) / rect.width) * 100));
    onSliderChange(pct);
  }, [onSliderChange]);

  const onPointerDown = useCallback((e: React.PointerEvent) => {
    isDragging.current = true;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    updateFromPointer(e.clientX);
  }, [updateFromPointer]);

  const onPointerMove = useCallback((e: React.PointerEvent) => {
    if (!isDragging.current) return;
    updateFromPointer(e.clientX);
  }, [updateFromPointer]);

  const onPointerUp = useCallback(() => { isDragging.current = false; }, []);

  const isLoading = loadingBefore || loadingAfter;

  return (
    <div
      style={{
        position: "relative", width: "100%", height: "100%",
        background: "var(--bg-base)", overflow: "hidden",
        display: "flex", flexDirection: "column",
      }}
    >
      {/* ---- Top HUD ---- */}
      <div style={{
        position: "absolute", top: 12, left: 12, right: 12,
        display: "flex", justifyContent: "space-between", alignItems: "center",
        zIndex: 20, pointerEvents: "none",
      }}>
        <div className="glass-card" style={{ padding: "5px 12px", display: "flex", alignItems: "center", gap: 6 }}>
          <span className="dot-pulse sky" style={{ background: "var(--sky-500)" }} />
          <span className="section-label" style={{ color: "var(--sky-400)" }}>Before / After Comparison</span>
        </div>
        {isLoading && (
          <div className="glass-card" style={{ padding: "5px 12px", display: "flex", alignItems: "center", gap: 6 }}>
            <div className="spinner" style={{ width: 12, height: 12 }} />
            <span className="section-label" style={{ color: "var(--emerald-400)" }}>Loading raster…</span>
          </div>
        )}
      </div>

      {/* ---- Image comparison area ---- */}
      <div
        ref={containerRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerLeave={onPointerUp}
        style={{
          flex: 1,
          position: "relative",
          overflow: "hidden",
          cursor: "ew-resize",
          userSelect: "none",
        }}
      >
        {/* BEFORE image — full width, clipped on the right */}
        {beforeSrc && (
          <div style={{
            position: "absolute", inset: 0,
            clipPath: `inset(0 ${100 - sliderValue}% 0 0)`,
          }}>
            <img
              src={beforeSrc}
              alt={`Before ${beforeYear}`}
              style={{
                width: "100%", height: "100%",
                objectFit: "contain",
                opacity,
                display: "block",
              }}
            />
            {/* Before year label */}
            <div
              style={{
                position: "absolute", top: 52, left: 14,
                pointerEvents: "none",
              }}
            >
              <span className="badge-neutral" style={{ fontSize: 10, padding: "4px 10px" }}>
                {beforeYear}
              </span>
            </div>
          </div>
        )}

        {/* AFTER image — full width, clipped on the left */}
        {afterSrc && (
          <div style={{
            position: "absolute", inset: 0,
            clipPath: `inset(0 0 0 ${sliderValue}%)`,
          }}>
            <img
              src={afterSrc}
              alt={`After ${afterYear}`}
              style={{
                width: "100%", height: "100%",
                objectFit: "contain",
                opacity,
                display: "block",
              }}
            />
            {/* After year label */}
            <div
              style={{
                position: "absolute", top: 52, right: 14,
                pointerEvents: "none",
              }}
            >
              <span className="badge-neutral" style={{ fontSize: 10, padding: "4px 10px" }}>
                {afterYear}
              </span>
            </div>
          </div>
        )}

        {/* ---- Divider line ---- */}
        <div
          style={{
            position: "absolute",
            top: 0, bottom: 0,
            left: `${sliderValue}%`,
            width: 2,
            background: "linear-gradient(to bottom, transparent, var(--emerald-400), transparent)",
            transform: "translateX(-50%)",
            zIndex: 10,
            pointerEvents: "none",
          }}
        />

        {/* ---- Drag handle ---- */}
        <div
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
            boxShadow: "0 0 16px rgba(5,150,105,0.5)",
            display: "flex", alignItems: "center", justifyContent: "center",
            cursor: "ew-resize",
            pointerEvents: "none",
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M5 4L2 8l3 4M11 4l3 4-3 4" stroke="#34d399" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        {/* ---- Before/After edge labels at bottom ---- */}
        <div style={{
          position: "absolute", bottom: 52, left: 14,
          pointerEvents: "none", zIndex: 12,
        }}>
          <span style={{
            fontSize: 9, fontFamily: "monospace", fontWeight: 700,
            letterSpacing: "0.08em", textTransform: "uppercase",
            color: "var(--text-muted)",
          }}>← Before</span>
        </div>
        <div style={{
          position: "absolute", bottom: 52, right: 14,
          pointerEvents: "none", zIndex: 12,
        }}>
          <span style={{
            fontSize: 9, fontFamily: "monospace", fontWeight: 700,
            letterSpacing: "0.08em", textTransform: "uppercase",
            color: "var(--text-muted)",
          }}>After →</span>
        </div>
      </div>

      {/* ---- Slider track at bottom ---- */}
      <div
        style={{
          flexShrink: 0,
          padding: "10px 16px",
          background: "rgba(5,12,20,0.95)",
          borderTop: "1px solid var(--border-dim)",
          display: "flex", alignItems: "center", gap: 12,
        }}
      >
        <span style={{ fontSize: 9, fontFamily: "monospace", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em", flexShrink: 0 }}>
          {beforeYear}
        </span>
        <input
          type="range"
          min="0" max="100"
          value={sliderValue}
          onChange={e => onSliderChange(Number(e.target.value))}
          style={{ flex: 1 }}
        />
        <span style={{ fontSize: 9, fontFamily: "monospace", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.08em", flexShrink: 0 }}>
          {afterYear}
        </span>
        <span style={{
          fontSize: 10, fontFamily: "monospace", fontWeight: 700,
          color: "var(--emerald-400)",
          background: "var(--emerald-dim)",
          border: "1px solid rgba(5,150,105,0.25)",
          borderRadius: 4, padding: "2px 8px", flexShrink: 0,
          minWidth: 40, textAlign: "center",
        }}>
          {Math.round(sliderValue)}%
        </span>
      </div>
    </div>
  );
}
