"use client";

import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

interface ThreeMapProjectionProps {
  beforeImageUrl: string | null;
  afterImageUrl: string | null;
  opacity: number;
  isMask: boolean;
  sliderValue: number; // 0 (full before) to 100 (full after)
}

export default function ThreeMapProjection({
  beforeImageUrl,
  afterImageUrl,
  opacity,
  isMask,
  sliderValue,
}: ThreeMapProjectionProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(false);
  const materialsRef = useRef<{
    before: THREE.MeshStandardMaterial;
    after: THREE.MeshStandardMaterial;
  } | null>(null);
  const clipBeforeRef = useRef<THREE.Plane | null>(null);
  const clipAfterRef = useRef<THREE.Plane | null>(null);
  const boundaryRef = useRef<THREE.Line | null>(null);

  // Sync opacity
  useEffect(() => {
    if (materialsRef.current) {
      materialsRef.current.before.opacity = opacity;
      materialsRef.current.after.opacity = opacity;
    }
  }, [opacity]);

  // Sync split-wipe
  useEffect(() => {
    const PLANE_W = 5;
    if (clipBeforeRef.current && clipAfterRef.current && boundaryRef.current) {
      const lineX = 2.5 - (sliderValue / 100) * PLANE_W;
      boundaryRef.current.position.x = lineX;
      clipBeforeRef.current.constant = lineX;
      clipAfterRef.current.constant = -lineX;
    }
  }, [sliderValue]);

  useEffect(() => {
    if (!containerRef.current) return;
    const el = containerRef.current;
    const rect = el.getBoundingClientRect();
    const W = rect.width || 640;
    const H = rect.height || 480;

    setLoading(true);

    // =========================================================
    // SCENE
    // =========================================================
    const scene = new THREE.Scene();
    scene.background = null;
    scene.fog = new THREE.FogExp2(0x050c14, 0.04);

    const camera = new THREE.PerspectiveCamera(36, W / H, 0.1, 100);
    camera.position.set(0, 5.5, 8);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(W, H);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.localClippingEnabled = true;
    renderer.shadowMap.enabled = true;
    el.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.04;
    controls.rotateSpeed = 0.45;
    controls.minDistance = 3.5;
    controls.maxDistance = 12;
    controls.maxPolarAngle = Math.PI / 2.2;
    controls.enablePan = false;

    // =========================================================
    // BASE PLATFORM
    // =========================================================
    const baseGeo = new THREE.BoxGeometry(5.6, 0.22, 5.6);
    const baseMat = new THREE.MeshStandardMaterial({
      color: 0x050c14,
      roughness: 0.6,
      metalness: 0.4,
    });
    const baseMesh = new THREE.Mesh(baseGeo, baseMat);
    baseMesh.position.y = -0.12;
    baseMesh.receiveShadow = true;
    scene.add(baseMesh);

    // Grid on base
    const gridHelper = new THREE.GridHelper(5.6, 10, 0x059669, 0x0d1826);
    gridHelper.position.y = 0.002;
    scene.add(gridHelper);

    // =========================================================
    // CLIPPING PLANES
    // =========================================================
    const clipBefore = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
    const clipAfter = new THREE.Plane(new THREE.Vector3(1, 0, 0), 0);
    clipBeforeRef.current = clipBefore;
    clipAfterRef.current = clipAfter;

    // =========================================================
    // MAP PLANES
    // =========================================================
    const planeGeo = new THREE.PlaneGeometry(5, 5, 1, 1);

    const beforeMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      side: THREE.DoubleSide,
      transparent: true,
      opacity,
      clippingPlanes: [clipBefore],
      roughness: 0.85,
      metalness: 0.05,
    });

    const afterMat = new THREE.MeshStandardMaterial({
      color: 0xffffff,
      side: THREE.DoubleSide,
      transparent: true,
      opacity,
      clippingPlanes: [clipAfter],
      roughness: 0.85,
      metalness: 0.05,
    });

    materialsRef.current = { before: beforeMat, after: afterMat };

    const beforeMesh = new THREE.Mesh(planeGeo, beforeMat);
    beforeMesh.rotation.x = -Math.PI / 2;
    beforeMesh.position.y = 0.01;
    scene.add(beforeMesh);

    const afterMesh = new THREE.Mesh(planeGeo, afterMat);
    afterMesh.rotation.x = -Math.PI / 2;
    afterMesh.position.y = 0.012;
    scene.add(afterMesh);

    // Boundary divider line
    const boundaryGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0.03, -2.6),
      new THREE.Vector3(0, 0.03, 2.6),
    ]);
    const boundaryMat = new THREE.LineBasicMaterial({
      color: 0x34d399,
      transparent: true,
      opacity: 0.85,
    });
    const boundaryLine = new THREE.Line(boundaryGeo, boundaryMat);
    scene.add(boundaryLine);
    boundaryRef.current = boundaryLine;

    // =========================================================
    // LIGHTING
    // =========================================================
    scene.add(new THREE.AmbientLight(0x0a1628, 1.5));

    const sun = new THREE.DirectionalLight(0xffffff, 1.0);
    sun.position.set(4, 10, 4);
    sun.castShadow = true;
    scene.add(sun);

    const rim = new THREE.DirectionalLight(0x2563eb, 0.2);
    rim.position.set(-4, 3, -4);
    scene.add(rim);

    const emeraldPt = new THREE.PointLight(0x059669, 0.4, 10);
    emeraldPt.position.set(0, -1, 0);
    scene.add(emeraldPt);

    // =========================================================
    // PROCEDURAL FALLBACK BLUEPRINT TEXTURE
    // =========================================================
    const createFallback = (year: number, label: string) => {
      const c = document.createElement("canvas");
      c.width = 512; c.height = 512;
      const ctx = c.getContext("2d")!;

      // Deep dark base
      ctx.fillStyle = "#050c14";
      ctx.fillRect(0, 0, 512, 512);

      // Blueprint grid
      ctx.strokeStyle = "rgba(5,150,105,0.1)";
      ctx.lineWidth = 0.8;
      for (let i = 0; i <= 512; i += 24) {
        ctx.beginPath(); ctx.moveTo(i, 0); ctx.lineTo(i, 512); ctx.stroke();
        ctx.beginPath(); ctx.moveTo(0, i); ctx.lineTo(512, i); ctx.stroke();
      }

      // Header band
      ctx.fillStyle = "rgba(5,150,105,0.12)";
      ctx.fillRect(0, 0, 512, 70);

      ctx.fillStyle = "#34d399";
      ctx.font = "bold 13px monospace";
      ctx.textAlign = "center";
      ctx.fillText("SAT4RISK // FARMGUARD SURVEILLANCE", 256, 28);

      ctx.fillStyle = "rgba(52,211,153,0.6)";
      ctx.font = "10px monospace";
      ctx.fillText(`PERIOD: ${year}  ·  SENSOR: SENTINEL-2 L2A`, 256, 50);

      // Warning text
      ctx.fillStyle = "#ef4444";
      ctx.font = "bold 11px monospace";
      ctx.textAlign = "left";
      ctx.fillText(`// SATELLITE RASTER ABSENT FOR ${year}`, 32, 120);
      ctx.fillText(`// MODE: ${label.toUpperCase()}`, 32, 144);

      // Crosshair
      ctx.strokeStyle = "rgba(5,150,105,0.5)";
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.arc(256, 320, 55, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(256, 248); ctx.lineTo(256, 392); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(184, 320); ctx.lineTo(328, 320); ctx.stroke();

      ctx.fillStyle = "rgba(52,211,153,0.7)";
      ctx.font = "9px monospace";
      ctx.textAlign = "center";
      ctx.fillText("TARGET BOUNDS GRID ACTIVE", 256, 400);

      return new THREE.CanvasTexture(c);
    };

    // =========================================================
    // TEXTURE LOADING
    // =========================================================
    const textureLoader = new THREE.TextureLoader();
    textureLoader.setCrossOrigin("anonymous");

    const extractYear = (url: string | null, fallback: number) => {
      if (!url) return fallback;
      const m = url.match(/_(\d{4})\.png/);
      return m ? parseInt(m[1]) : fallback;
    };

    const loadTexture = (
      url: string | null,
      year: number,
      mat: THREE.MeshStandardMaterial,
      done: () => void
    ) => {
      if (!url) {
        mat.map = createFallback(year, isMask ? "AI classification" : "satellite");
        mat.needsUpdate = true;
        done(); return;
      }

      const finalUrl = url.startsWith("http") ? url : `http://localhost:8000${url}`;
      const img = new Image();
      img.crossOrigin = "anonymous";

      img.onload = () => {
        let src: HTMLCanvasElement | HTMLImageElement = img;

        if (isMask) {
          const cv = document.createElement("canvas");
          cv.width = img.width; cv.height = img.height;
          const cx = cv.getContext("2d")!;
          cx.drawImage(img, 0, 0);
          const id = cx.getImageData(0, 0, cv.width, cv.height);
          for (let i = 0; i < id.data.length; i += 4) {
            if (id.data[i] === 0 && id.data[i + 1] === 0 && id.data[i + 2] === 0) {
              id.data[i + 3] = 0;
            }
          }
          cx.putImageData(id, 0, 0);
          src = cv;
        }

        const tex = new THREE.CanvasTexture(src);
        tex.colorSpace = THREE.SRGBColorSpace;
        mat.map = tex;
        mat.color.setHex(0xffffff);
        mat.needsUpdate = true;
        done();
      };

      img.onerror = () => {
        mat.map = createFallback(year, "load error");
        mat.needsUpdate = true;
        done();
      };

      img.src = finalUrl;
    };

    let loaded = 0;
    const onDone = () => { if (++loaded >= 2) setLoading(false); };

    loadTexture(beforeImageUrl, extractYear(beforeImageUrl, 2017), beforeMat, onDone);
    loadTexture(afterImageUrl, extractYear(afterImageUrl, 2025), afterMat, onDone);

    // Apply initial clip plane positions
    const initLineX = 2.5 - (sliderValue / 100) * 5;
    clipBefore.constant = initLineX;
    clipAfter.constant = -initLineX;
    boundaryLine.position.x = initLineX;

    // =========================================================
    // RESIZE
    // =========================================================
    const resizer = new ResizeObserver(entries => {
      const e = entries[0];
      if (!e) return;
      const { width: w, height: h } = e.contentRect;
      if (w > 0 && h > 0) {
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      }
    });
    resizer.observe(el);

    // =========================================================
    // ANIMATION
    // =========================================================
    let frameId: number;
    const animate = () => {
      frameId = requestAnimationFrame(animate);
      baseMesh.rotation.y = 0.018 * Math.sin(performance.now() * 0.0004);
      controls.update();
      renderer.render(scene, camera);
    };
    animate();

    return () => {
      cancelAnimationFrame(frameId);
      resizer.disconnect();
      renderer.domElement.remove();
      scene.clear();
      renderer.dispose();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Only re-initialize Three.js scene when assets change, not on slider/opacity updates
  }, [beforeImageUrl, afterImageUrl, isMask]);

  return (
    <div
      style={{
        position: "relative",
        width: "100%", height: "100%",
        background: "var(--bg-base)",
        overflow: "hidden",
        display: "flex", alignItems: "center", justifyContent: "center",
      }}
    >
      {/* Overlay labels */}
      <div
        style={{
          position: "absolute", top: 14, left: 14, right: 14,
          display: "flex", justifyContent: "space-between", alignItems: "center",
          pointerEvents: "none", zIndex: 20,
        }}
      >
        <div className="glass-card" style={{ padding: "5px 12px", display: "flex", alignItems: "center", gap: 6 }}>
          <span className="dot-pulse sky" />
          <span className="section-label" style={{ color: "var(--sky-400)" }}>3D Tile Projection</span>
        </div>

        {loading && (
          <div className="glass-card" style={{ padding: "5px 12px", display: "flex", alignItems: "center", gap: 6 }}>
            <div className="spinner" style={{ width: 12, height: 12 }} />
            <span className="section-label" style={{ color: "var(--emerald-400)" }}>Processing Raster…</span>
          </div>
        )}
      </div>

      {/* Before/After labels at bottom corners */}
      <div
        style={{
          position: "absolute", bottom: 14, left: 14, right: 14,
          display: "flex", justifyContent: "space-between",
          pointerEvents: "none", zIndex: 20,
        }}
      >
        <span className="badge-neutral">← Before</span>
        <span className="badge-neutral">After →</span>
      </div>

      {/* Canvas */}
      <div
        ref={containerRef}
        style={{ width: "100%", height: "100%", cursor: "grab" }}
      />
    </div>
  );
}
