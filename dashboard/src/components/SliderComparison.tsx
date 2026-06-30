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
  ctx.fillText(`// SATELLITE RASTER ABSENT FOR ${year}`, 28, 108);
  ctx.fillText(`// MODE: ${label.toUpperCase()}`, 28, 128);

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
}: SliderComparisonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);
  const [beforeSrc, setBeforeSrc] = useState<string | null>(null);
  const [afterSrc, setAfterSrc] = useState<string | null>(null);
  const [loadingBefore, setLoadingBefore] = useState(true);
  const [loadingAfter, setLoadingAfter] = useState(true);
  // Natural aspect ratio of the loaded raster — drives canvas width
  const [imgAspectRatio, setImgAspectRatio] = useState<number | null>(null);

  // ---- Load / process images ----
  const processImage = useCallback((
    url: string | null,
    year: number,
    maskMode: boolean,
    captureAspect: boolean,
    onDone: (src: string) => void
  ) => {
    const fallbackLabel = maskMode ? "AI classification" : "satellite band";

    if (!url) {
      // Fallback canvas is always 512×512 — ratio 1:1
      if (captureAspect) setImgAspectRatio(1);
      setTimeout(() => onDone(makeBlueprintDataUrl(year, fallbackLabel)), 0);
      return;
    }

    const finalUrl = url.startsWith("http") ? url : `${API_ORIGIN}${url}`;
    const img = new Image();

    img.onload = () => {
      // Capture natural dimensions from the before image so canvas fits exactly
      if (captureAspect && img.naturalWidth && img.naturalHeight) {
        setImgAspectRatio(img.naturalWidth / img.naturalHeight);
      }
      onDone(finalUrl);
    };

    img.onerror = () => {
      if (captureAspect) setImgAspectRatio(1);
      onDone(makeBlueprintDataUrl(year, "load error"));
    };
    img.src = finalUrl;
  }, []);

  useEffect(() => {
    let active = true;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- Reset loading state to true synchronously when inputs change to display loading spinner
    setLoadingBefore(true);
    // Reset ratio on source change so old ratio doesn't flash
    setImgAspectRatio(null);
    processImage(beforeImageUrl, beforeYear, isMask, true, src => {
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
    processImage(afterImageUrl, afterYear, isMask, false, src => {
      if (active) {
        setAfterSrc(src);
        setLoadingAfter(false);
      }
    });
    return () => {
      active = false;
    };
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

  const isBeforeMask = isMask && beforeSrc ? !beforeSrc.startsWith("data:") : false;
  const isAfterMask = isMask && afterSrc ? !afterSrc.startsWith("data:") : false;

  return (
    <div
      style={{
        position: "relative", width: "100%", height: "100%",
        background: "var(--bg-base)", overflow: "hidden",
        display: "flex", flexDirection: "column", alignItems: "center",
      }}
    >
      {/* ---- Loading indicator only — tab bar already labels this view ---- */}
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
        onPointerDown={showSlider ? onPointerDown : undefined}
        onPointerMove={showSlider ? onPointerMove : undefined}
        onPointerUp={showSlider ? onPointerUp : undefined}
        onPointerLeave={showSlider ? onPointerUp : undefined}
        className="bg-grid"
        style={{
          flex: 1,
          position: "relative",
          overflow: "hidden",
          cursor: showSlider ? "ew-resize" : "default",
          userSelect: "none",
          // Shrink width to match the image's natural aspect ratio — no side gaps
          ...(imgAspectRatio
            ? { width: "auto", aspectRatio: String(imgAspectRatio), maxWidth: "100%" }
            : { width: "100%" }),
        }}
      >
        {showSlider ? (
          <>
            {/* BEFORE image — full width, clipped on the right */}
            {beforeSrc && (
              <div style={{
                position: "absolute", inset: 0,
                clipPath: `inset(0 ${100 - sliderValue}% 0 0)`,
              }}>
                <img
                  src={beforeSrc}
                  alt={`Before ${beforeYear}`}
                  draggable={false}
                  style={{
                    width: "100%", height: "100%",
                    objectFit: "fill",
                    opacity,
                    display: "block",
                    userSelect: "none",
                    mixBlendMode: isBeforeMask ? "screen" : "normal",
                  }}
                />
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
                  draggable={false}
                  style={{
                    width: "100%", height: "100%",
                    objectFit: "fill",
                    opacity,
                    display: "block",
                    userSelect: "none",
                    mixBlendMode: isAfterMask ? "screen" : "normal",
                  }}
                />
              </div>
            )}

            {/* ---- Year labels: outside clip containers so they're never cut off ---- */}
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

            <div
              style={{
                position: "absolute",
                top: 0, bottom: 0,
                left: `${sliderValue}%`,
                width: 2,
                background: "var(--emerald-500)",
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
          /* Single full-width Encroachment Heatmap overlay view */
          afterSrc && (
            <div style={{ position: "absolute", inset: 0 }}>
              <img
                src={afterSrc}
                alt="Encroachment Heatmap"
                draggable={false}
                style={{
                  width: "100%", height: "100%",
                  objectFit: "fill",
                  opacity,
                  display: "block",
                  userSelect: "none",
                }}
              />
              <div
                style={{
                  position: "absolute", top: 52, right: 14,
                  pointerEvents: "none",
                }}
              >
                <span className="badge-neutral" style={{ fontSize: 10, padding: "4px 10px", color: "var(--red-400)", border: "1px solid rgba(220,38,38,0.25)", background: "rgba(220,38,38,0.05)" }}>
                  Encroachment Heatmap
                </span>
              </div>
            </div>
          )
        )}
      </div>


    </div>
  );
}
