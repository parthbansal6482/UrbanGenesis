"use client";

import React, { useEffect, useRef, useState } from "react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

interface ThreeMapProjectionProps {
  beforeImageUrl: string | null;
  afterImageUrl: string | null;
  opacity: number;
  isMask: boolean;
  sliderValue: number; // 0 (100% before) to 100 (100% after)
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
  const materialsRef = useRef<{ before: THREE.MeshPhongMaterial; after: THREE.MeshPhongMaterial } | null>(null);

  // Clipping plane references
  const clipPlaneBeforeRef = useRef<THREE.Plane | null>(null);
  const clipPlaneAfterRef = useRef<THREE.Plane | null>(null);
  const boundaryLineRef = useRef<THREE.Line | null>(null);

  // Update opacities dynamically
  useEffect(() => {
    if (materialsRef.current) {
      materialsRef.current.before.opacity = opacity;
      materialsRef.current.after.opacity = opacity;
    }
  }, [opacity]);

  // Synchronize 3D split-wipe transitions
  useEffect(() => {
    if (clipPlaneBeforeRef.current && clipPlaneAfterRef.current && boundaryLineRef.current) {
      const planeWidth = 5;
      
      // Calculate slider wipe position (moves from right (+2.5) to left (-2.5))
      // sliderValue = 0 (100% before) => line_x = 2.5
      // sliderValue = 100 (100% after) => line_x = -2.5
      const lineX = 2.5 - (sliderValue / 100) * planeWidth;
      
      boundaryLineRef.current.position.x = lineX;

      // Before plane normal is (-1, 0, 0)
      // keeps points where n.dot(p) + constant > 0 => -x + constant > 0 => x < constant
      // We want to show before plane to the left of the slider (x < lineX)
      // So constant = lineX
      clipPlaneBeforeRef.current.constant = lineX;

      // After plane normal is (1, 0, 0)
      // keeps points where x + constant > 0 => x > -constant
      // We want to show after plane to the right of the slider (x > lineX)
      // So constant = -lineX
      clipPlaneAfterRef.current.constant = -lineX;
    }
  }, [sliderValue]);

  useEffect(() => {
    if (!containerRef.current) return;

    const rect = containerRef.current.getBoundingClientRect();
    const width = rect.width || 500;
    const height = rect.height || 420;

    setLoading(true);

    // Scene
    const scene = new THREE.Scene();
    scene.background = null;

    // Camera
    const camera = new THREE.PerspectiveCamera(40, width / height, 0.1, 100);
    camera.position.set(0, 4.8, 7.5);

    // Renderer
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setSize(width, height);
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.localClippingEnabled = true;
    containerRef.current.appendChild(renderer.domElement);

    // Controls
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.05;
    controls.rotateSpeed = 0.5;
    controls.minDistance = 4.0;
    controls.maxDistance = 10;
    controls.maxPolarAngle = Math.PI / 2.3; // Limit camera tilt
    controls.enablePan = false;

    // Table pedestal base
    const pedestalGeo = new THREE.BoxGeometry(5.4, 0.2, 5.4);
    const pedestalMat = new THREE.MeshPhysicalMaterial({
      color: 0x0f172a, // Slate 900
      roughness: 0.25,
      metalness: 0.75,
      transparent: true,
      opacity: 0.85,
    });
    const pedestal = new THREE.Mesh(pedestalGeo, pedestalMat);
    pedestal.position.y = -0.11;
    scene.add(pedestal);

    // Grid details on pedestal
    const gridHelper = new THREE.GridHelper(5.4, 8, 0x059669, 0x1e293b);
    gridHelper.position.y = -0.01;
    scene.add(gridHelper);

    // Clipping planes setup
    const clipPlaneBefore = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
    const clipPlaneAfter = new THREE.Plane(new THREE.Vector3(1, 0, 0), 0);
    clipPlaneBeforeRef.current = clipPlaneBefore;
    clipPlaneAfterRef.current = clipPlaneAfter;

    // 3D Plane representing the flat map tile
    const planeGeo = new THREE.PlaneGeometry(5, 5);

    // Solid fallback materials
    const beforeMat = new THREE.MeshPhongMaterial({
      color: 0xffffff,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: opacity,
      clippingPlanes: [clipPlaneBefore],
      shininess: 20,
    });

    const afterMat = new THREE.MeshPhongMaterial({
      color: 0xffffff,
      side: THREE.DoubleSide,
      transparent: true,
      opacity: opacity,
      clippingPlanes: [clipPlaneAfter],
      shininess: 20,
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

    // Dynamic split wipe border line
    const boundaryGeo = new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(0, 0.02, -2.5),
      new THREE.Vector3(0, 0.02, 2.5),
    ]);
    const boundaryMat = new THREE.LineBasicMaterial({
      color: 0x059669, // Emerald 600
      linewidth: 3,
      transparent: true,
      opacity: 0.8,
    });
    const boundaryLine = new THREE.Line(boundaryGeo, boundaryMat);
    scene.add(boundaryLine);
    boundaryLineRef.current = boundaryLine;

    // Lights
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
    scene.add(ambientLight);

    const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
    dirLight.position.set(4, 8, 4);
    scene.add(dirLight);

    // Procedural Fallback blueprint texture generator
    const createFallbackTexture = (year: number, label: string) => {
      const fbCanvas = document.createElement("canvas");
      fbCanvas.width = 512;
      fbCanvas.height = 512;
      const fCtx = fbCanvas.getContext("2d");
      if (fCtx) {
        // Slate 900 base
        fCtx.fillStyle = "#0f172a";
        fCtx.fillRect(0, 0, 512, 512);

        // Technical blueprint grid
        fCtx.strokeStyle = "rgba(5, 150, 105, 0.15)"; // Emerald 600 thin
        fCtx.lineWidth = 1;
        for (let i = 0; i <= 512; i += 32) {
          fCtx.beginPath();
          fCtx.moveTo(i, 0); fCtx.lineTo(i, 512);
          fCtx.moveTo(0, i); fCtx.lineTo(512, i);
          fCtx.stroke();
        }

        // Diagnostic layout
        fCtx.fillStyle = "#059669";
        fCtx.font = "bold 15px monospace";
        fCtx.fillText("SAT4RISK // ENVIRONMENTAL MONITORING", 40, 60);

        fCtx.fillStyle = "#94a3b8"; // Slate 400
        fCtx.font = "bold 12px monospace";
        fCtx.fillText(`PERIOD: ${year}`, 40, 110);
        fCtx.fillText(`SENSOR: SENTINEL-2 L2A`, 40, 132);

        // Overlay status warning
        fCtx.fillStyle = "#dc2626"; // Red 600
        fCtx.font = "bold 12px monospace";
        fCtx.fillText(`// SATELLITE RASTER ABSENT FOR ${year}`, 40, 200);
        fCtx.fillText(`// MODE: ${label.toUpperCase()}`, 40, 222);

        // Tech crosshair circle in center
        fCtx.strokeStyle = "rgba(5, 150, 105, 0.5)";
        fCtx.lineWidth = 2;
        fCtx.beginPath();
        fCtx.arc(256, 330, 45, 0, Math.PI * 2);
        fCtx.stroke();
        
        fCtx.beginPath();
        fCtx.moveTo(256, 270); fCtx.lineTo(256, 390);
        fCtx.moveTo(196, 330); fCtx.lineTo(316, 330);
        fCtx.stroke();

        fCtx.fillStyle = "rgba(5, 150, 105, 0.8)";
        fCtx.font = "9px monospace";
        fCtx.textAlign = "center";
        fCtx.fillText("TARGET BOUNDS GRID ACTIVE", 256, 400);
      }
      return new THREE.CanvasTexture(fbCanvas);
    };

    // Load textures
    const textureLoader = new THREE.TextureLoader();
    textureLoader.setCrossOrigin("anonymous");

    const loadTexture = (
      url: string | null,
      year: number,
      material: THREE.MeshPhongMaterial,
      onComplete: () => void
    ) => {
      if (!url) {
        // Fallback procedural blueprint if URL is absent (e.g. true color not generated)
        material.map = createFallbackTexture(year, isMask ? "AI classification" : "satellite band");
        material.color.setHex(0xffffff);
        material.needsUpdate = true;
        onComplete();
        return;
      }

      const finalUrl = url.startsWith("http") ? url : `http://localhost:8000${url}`;

      const image = new Image();
      image.crossOrigin = "anonymous";
      image.onload = () => {
        let finalCanvas: HTMLCanvasElement | HTMLImageElement = image;

        if (isMask) {
          // Client-side transparency mapping for background class
          const canvas = document.createElement("canvas");
          canvas.width = image.width;
          canvas.height = image.height;
          const ctx = canvas.getContext("2d");
          if (ctx) {
            ctx.drawImage(image, 0, 0);
            const imgData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            const data = imgData.data;
            for (let i = 0; i < data.length; i += 4) {
              const r = data[i];
              const g = data[i + 1];
              const b = data[i + 2];
              if (r === 0 && g === 0 && b === 0) {
                data[i + 3] = 0; // Set alpha to 0 for black background pixels
              }
            }
            ctx.putImageData(imgData, 0, 0);
            finalCanvas = canvas;
          }
        }

        const texture = new THREE.CanvasTexture(finalCanvas);
        texture.colorSpace = THREE.SRGBColorSpace;
        material.map = texture;
        material.color.setHex(0xffffff);
        material.needsUpdate = true;
        onComplete();
      };

      image.onerror = () => {
        // Fallback procedural texture if image fails to load
        console.warn("Texture load error. Resolving custom blueprint map.");
        material.map = createFallbackTexture(year, "load failed");
        material.color.setHex(0xffffff);
        material.needsUpdate = true;
        onComplete();
      };

      image.src = finalUrl;
    };

    let loaded = 0;
    const onLoaded = () => {
      loaded++;
      if (loaded >= 2) setLoading(false);
    };

    // Extract years from before/after URL if possible, or fallback
    const extractYear = (url: string | null, fallback: number) => {
      if (!url) return fallback;
      const match = url.match(/_(\d{4})\.png/);
      return match ? parseInt(match[1]) : fallback;
    };

    const beforeYr = extractYear(beforeImageUrl, 2017);
    const afterYr = extractYear(afterImageUrl, 2025);

    loadTexture(beforeImageUrl, beforeYr, beforeMat, onLoaded);
    loadTexture(afterImageUrl, afterYr, afterMat, onLoaded);

    // Resize Observer
    const resizeObserver = new ResizeObserver((entries) => {
      if (!entries || entries.length === 0) return;
      const { width: w, height: h } = entries[0].contentRect;
      if (w > 0 && h > 0) {
        camera.aspect = w / h;
        camera.updateProjectionMatrix();
        renderer.setSize(w, h);
      }
    });
    resizeObserver.observe(containerRef.current);

    // Animation Loop
    let frameId: number;
    const animate = () => {
      frameId = requestAnimationFrame(animate);

      // Tilts/Wobble pedestal slightly for visual dynamism
      pedestal.rotation.y = 0.02 * Math.sin(performance.now() * 0.0005);

      controls.update();
      renderer.render(scene, camera);
    };

    animate();

    return () => {
      cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      if (renderer.domElement) {
        renderer.domElement.remove();
      }
      scene.clear();
      renderer.dispose();
    };
  }, [beforeImageUrl, afterImageUrl, isMask]);

  return (
    <div className="relative w-full h-full flex items-center justify-center bg-slate-900 rounded-xl overflow-hidden border border-slate-800 shadow-md">
      {/* Visual Workspace diagnostic labels */}
      <div className="absolute top-4 left-4 right-4 flex justify-between items-center pointer-events-none z-10">
        <span className="bg-slate-950/80 backdrop-blur-md border border-slate-800 text-[10px] text-slate-400 font-mono px-2.5 py-1 rounded-full uppercase tracking-wider">
          3D Tile Projection
        </span>
        {loading && (
          <span className="bg-emerald-950/80 backdrop-blur-md border border-emerald-800 text-[10px] text-emerald-400 font-mono px-2.5 py-1 rounded-full animate-pulse">
            Processing Raster...
          </span>
        )}
      </div>

      <div className="absolute inset-0 bg-[linear-gradient(rgba(255,255,255,0.01)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,0.01)_1px,transparent_1px)] bg-[size:16px_16px] pointer-events-none" />

      {/* WebGL Mount Point */}
      <div ref={containerRef} className="w-full h-full min-h-[380px] md:min-h-[440px] cursor-grab active:cursor-grabbing" />

      {/* Wipe slider indicators */}
      <div className="absolute bottom-4 left-4 right-4 flex justify-between text-[10px] font-mono text-slate-500 pointer-events-none uppercase tracking-widest">
        <span>Before</span>
        <span>After</span>
      </div>
    </div>
  );
}
